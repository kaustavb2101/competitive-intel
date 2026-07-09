#!/usr/bin/env bash
# =============================================================================
# wsl_data_pull.sh — run the GEOBLOCKED Thai-gov data pull from a Thai IP (WSL).
#
# The sandbox / cloud runners sit on a foreign IP, so data.go.th, DLT, NSO and
# OAE all return 403. Run THIS from WSL on Kaustav's laptop (Thai network) to
# pull that data, fold it into the app, re-run the gate, and push it as a data
# branch you can open a PR from.
#
# USAGE (from WSL):
#   cp .env.example .env         # then edit .env, paste your (rotated) token
#   bash scripts/wsl_data_pull.sh
#
# Nothing here hardcodes a secret — the token is read from .env or the
# DATA_GO_TH_TOKEN environment variable. Never commit your real .env.
# =============================================================================
set -euo pipefail

REPO_URL="https://github.com/kaustavb2101/competitive-intel.git"
STAMP="$(date +%Y-%m-%d)"
BRANCH="data/gov-pull-$(date +%Y%m%d-%H%M)"

say(){ printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
die(){ printf '\n\033[1;31m❌ %s\033[0m\n' "$*"; exit 1; }

# ── 0. prereqs ───────────────────────────────────────────────────────────────
command -v git     >/dev/null || die "git missing → sudo apt update && sudo apt install -y git"
command -v python3 >/dev/null || die "python3 missing → sudo apt install -y python3 python3-pip"
command -v pip3    >/dev/null || die "pip3 missing → sudo apt install -y python3-pip"

# ── 1. locate the repo (run from inside it, or it clones to ~/competitive-intel)
if [ -f "CLAUDE.md" ] && [ -d "pipeline" ]; then
  REPO="$(pwd)"
elif [ -d "$HOME/competitive-intel/.git" ]; then
  REPO="$HOME/competitive-intel"; cd "$REPO"; git pull --ff-only || true
else
  say "Cloning repo to ~/competitive-intel"
  git clone "$REPO_URL" "$HOME/competitive-intel"
  REPO="$HOME/competitive-intel"; cd "$REPO"
fi
cd "$REPO"
say "Repo: $REPO"

# ── 2. python deps (per CLAUDE.md) ───────────────────────────────────────────
say "Installing Python deps"
pip3 install --break-system-packages -q shapely openlocationcode openpyxl pdfplumber requests 2>/dev/null \
  || pip3 install -q shapely openlocationcode openpyxl pdfplumber requests

# ── 3. token check — auto-locate .env wherever you saved it ──────────────────
# The loader only reads the repo-root .env, but people often drop it in pipeline/.
# If root .env is missing but one exists in pipeline/ (or ~), copy it up — no manual move.
if [ ! -f .env ]; then
  for cand in pipeline/.env "$HOME/.env" ~/competitive-intel/pipeline/.env; do
    if [ -f "$cand" ]; then say "Found .env at $cand → copying to repo root"; cp "$cand" .env; break; fi
  done
fi
if [ -z "${DATA_GO_TH_TOKEN:-}" ] && ! grep -q '^DATA_GO_TH_TOKEN=' .env 2>/dev/null; then
  die "No token found. Run:  cp .env.example .env  then edit .env and paste your rotated DATA_GO_TH_TOKEN (or: export DATA_GO_TH_TOKEN=...)"
fi
echo "   ✓ token present (value not shown)"

# ── 4. reachability sanity check (must be a THAI IP) ─────────────────────────
say "Checking data.go.th reachability (needs a Thai IP)…"
code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 https://data.go.th || echo 000)"
echo "   data.go.th → HTTP $code"
[ "$code" = "403" ] && echo "   ⚠️  403 = still geoblocked. Are you on a Thai network? A VPN set to Thailand also works."

# ── 5. pull the GEOBLOCKED gov data (DLT vehicles / DIW factories / NSO / OAE)
say "Pulling data.go.th (autox_dgt_ingest.py → pipeline/dgt_out/*.csv)"
( cd pipeline && python3 autox_dgt_ingest.py )
say "Folding CSVs into source-data (ingest_gov.py)"
( cd pipeline && python3 ingest_gov.py )

# ── 6. refresh the cloud-reachable LIVE feeds too (work anywhere; harmless) ───
say "Refreshing live feeds (NABC prices/agri · BIS+WorldBank macro · Bangchak fuel)"
( cd pipeline
  python3 pull_nabc_prices.py --stamp "$STAMP" || echo "   (nabc prices skipped)"
  python3 pull_nabc_agri.py   --stamp "$STAMP" || echo "   (nabc agri skipped)"
  python3 pull_macro.py       --stamp "$STAMP" || echo "   (macro skipped)"
  python3 pull_fuel_prices.py --stamp "$STAMP" || echo "   (fuel skipped)"
)

# ── 7. re-project the master + rebuild every downstream layer ────────────────
say "Rebuilding derived layers"
( cd pipeline
  for b in derive.py \
           build_branch_agri.py build_branch_vehicles.py build_branch_workforce.py build_occupations.py \
           build_crop_stress.py build_province.py build_amphoe.py \
           build_macro_sensitivity.py build_branch_recommendations.py build_regional_outlook.py \
           timeseries.py build_provenance.py; do
    if [ -f "$b" ]; then echo "   • $b"; python3 "$b"; fi
  done
)

# ── 8. QA gate (must pass before we push) ────────────────────────────────────
say "Running QA gate"
bash tests/run.sh check

# ── 9. commit to a data branch + push (open a PR from it) ────────────────────
say "Committing to $BRANCH"
git checkout -b "$BRANCH"
git add source-data platform/data
git commit -m "Gov data refresh — DLT vehicles / DIW factories / NSO / OAE + live prices ($STAMP)"
git push -u origin "$BRANCH"

printf '\n\033[1;32m✅ Done. Open a PR:\033[0m\n   https://github.com/kaustavb2101/competitive-intel/compare/%s?expand=1\n' "$BRANCH"
