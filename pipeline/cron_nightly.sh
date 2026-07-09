#!/usr/bin/env bash
# cron_nightly.sh — one nightly refresh of the AutoX credit-intelligence dataset.
#
# WHAT IT DOES (in order, each step guarded so one failure never aborts the rest):
#   1. loads DATA_GO_TH_TOKEN from the repo-root .env (gitignored) so the data.go.th pull can auth
#   2. runs ONE enrichment iteration (autox_enrich_loop.py) — refreshes OSM/commodities + the guarded
#      data.go.th stage (DLT vehicles, OAE prices, DLD/DOF/RFD) + re-derives platform/data
#   3. runs the offline gate (tests/run.sh check) — a green gate is the guard for step 4
#   4. if REMOTE_PUSH=1 AND the gate is green AND data actually changed: commits the refreshed data
#      and pushes, so the Vercel site redeploys with fresh numbers. Default is push ON; set
#      REMOTE_PUSH=0 to refresh + commit locally only and push by hand.
#
# Cron provides the daily cadence, so this runs a SINGLE iteration (not --watch).
#
# INSTALL — WSL cron (fires only while WSL is open; see the Task Scheduler note below for a laptop):
#     sudo service cron start                 # once per WSL session (or enable it to autostart)
#     crontab -e
#   add (runs 02:30 daily; adjust the repo path to yours):
#     30 2 * * * /mnt/c/Users/Kaustav\ Bagchi/competitive-intel/pipeline/cron_nightly.sh >> /mnt/c/Users/Kaustav\ Bagchi/competitive-intel/pipeline/cron_nightly.log 2>&1
#
# MORE RELIABLE ON A LAPTOP — Windows Task Scheduler (fires even when WSL is closed; it opens WSL to
# run this). Create a Basic Task → Daily 02:30 → Action "Start a program":
#     Program:   wsl.exe
#     Arguments: bash -lc "'/mnt/c/Users/Kaustav Bagchi/competitive-intel/pipeline/cron_nightly.sh'"
#   Tick "Run whether user is logged on or not" and "Wake the computer to run this task".
#
# SECRETS: put the token in <repo>/.env as  DATA_GO_TH_TOKEN=xxxx  (the file is gitignored). This
# script never prints the token and never commits it.
set -uo pipefail

# repo root = parent of this script's dir (works regardless of cwd / how cron invokes it)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
cd "$REPO" || { echo "cannot cd to repo $REPO"; exit 1; }

PUSH="${REMOTE_PUSH:-1}"
STAMP="$(date '+%Y-%m-%d %H:%M:%S')"
echo "=== cron_nightly $STAMP  (repo: $REPO) ==="

# 1. load the token (and any other env) from the gitignored .env, without echoing values
if [ -f "$REPO/.env" ]; then
  set -a; . "$REPO/.env"; set +a
  [ -n "${DATA_GO_TH_TOKEN:-}" ] && echo "token: loaded from .env" || echo "token: .env has no DATA_GO_TH_TOKEN (gov pull will skip)"
else
  echo "token: no .env (gov pull will skip — OSM/commodity refresh still runs)"
fi

# 2. one enrichment iteration (self-guards its own network stages)
echo "--- enrichment iteration ---"
python3 pipeline/autox_enrich_loop.py || echo "WARN: enrichment iteration returned non-zero (continuing)"

# 3. offline determinism + integrity gate — the guard for pushing
echo "--- gate ---"
if bash tests/run.sh check > "$HERE/cron_gate.out" 2>&1; then
  GATE_OK=1; echo "gate: PASS ($(grep -c '\[PASS\]' "$HERE/cron_gate.out") checks)"
else
  GATE_OK=0; echo "gate: FAIL — NOT pushing. Tail:"; tail -5 "$HERE/cron_gate.out"
fi

# 4. commit + push the refreshed data, only when green and something changed
if [ "$PUSH" = "1" ] && [ "${GATE_OK:-0}" = "1" ]; then
  # stage only data + master refresh artifacts (never .env, never the local logs)
  git add source-data platform/data 2>/dev/null || true
  if git diff --cached --quiet; then
    echo "push: no data changes — nothing to commit"
  else
    BR="$(git rev-parse --abbrev-ref HEAD)"
    git commit -q -m "Nightly data refresh ($STAMP)" \
      -m "Automated refresh via pipeline/cron_nightly.sh (OSM/commodities + data.go.th where reachable)." || true
    if git push origin "$BR" 2>&1 | tail -2; then
      echo "push: pushed to $BR"
    else
      echo "push: FAILED (network?) — commit is local; will retry next run"
    fi
  fi
elif [ "$PUSH" != "1" ]; then
  echo "push: disabled (REMOTE_PUSH=0) — data refreshed locally only"
fi
echo "=== cron_nightly done $(date '+%H:%M:%S') ==="
