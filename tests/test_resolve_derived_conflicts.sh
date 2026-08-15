#!/bin/bash
# Exercise pipeline/resolve_derived_conflicts.sh against every branch of its control flow.
#
# This is tested because the resolver AUTO-PUSHES TO MASTER (the committee and auto-merge jobs call
# it before landing) and auto-resolves conflicts on generated files. Logic with that much reach must
# not rot silently — in particular the two abort paths, which are the only thing standing between an
# unattended job and a wrongly-resolved conflict in source-data/ or in code.
#
# The fixture mirrors the real repo's shape in miniature: source-data/ holds inputs, and
# platform/data/provenance.json is a PURE FUNCTION of them that both sides regenerate — which is
# exactly why it conflicts on every merge. It uses a stand-in for rederive_drift.py so the test runs
# in seconds; the real driver is verified separately by its own --check gate.
#
#     bash tests/test_resolve_derived_conflicts.sh          # run from the repo root
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-$HERE/../pipeline/resolve_derived_conflicts.sh}"
R="$(mktemp -d)/resolver-fixture"
trap 'rm -rf "$(dirname "$R")"' EXIT
PASS=0; FAIL=0
ok(){ echo "  [PASS] $1"; PASS=$((PASS+1)); }
no(){ echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

setup(){
  rm -rf "$R"; mkdir -p "$R/pipeline" "$R/source-data" "$R/platform/data" "$R/docs"; cd "$R" || exit 1
  git init -q; git config user.email t@t; git config user.name t; git config commit.gpgsign false
  cp "$SRC" pipeline/resolve_derived_conflicts.sh
  cp "$HERE/../pipeline/merge_append_log.py" pipeline/merge_append_log.py
  cp "$HERE/../pipeline/merge_feed_history.py" pipeline/merge_feed_history.py
  cp "$HERE/../pipeline/merge_swarm_runs.py" pipeline/merge_swarm_runs.py
  cp "$HERE/../pipeline/pick_newer_stamp.py" pipeline/pick_newer_stamp.py
  printf '# PROGRESS LOG\n\nReverse-chronological.\n\n## 2026-08-01 — the entry both sides start from\n\nbody\n' > docs/PROGRESS_LOG.md
  # stand-in for rederive_drift.py: provenance is a deterministic census of source-data
  cat > pipeline/rederive_drift.py <<'PY'
import json, os, sys, hashlib
rows = {}
for f in sorted(os.listdir("source-data")):
    b = open(os.path.join("source-data", f), "rb").read()
    rows[f] = {"bytes": len(b), "sha": hashlib.sha256(b).hexdigest()[:12]}
with open("platform/data/provenance.json", "w", newline="\n") as fh:
    fh.write(json.dumps({"layers": rows}, sort_keys=True) + "\n")
print("re-derived provenance from", len(rows), "sources")
sys.exit(0)
PY
  echo '{"diesel": 36.0}'   > source-data/fuel.json
  echo '{"rice": 12.0}'     > source-data/crops.json
  echo 'x = 1'              > pipeline/code.py
  python3 pipeline/rederive_drift.py >/dev/null
  git add -A && git commit -qm base
}

# a branch that changes one source file and regenerates provenance — the normal case
diverge(){ # <branch> <file> <content>
  git checkout -q -B "$1" master
  echo "$3" > "$2"
  python3 pipeline/rederive_drift.py >/dev/null
  git add -A && git commit -qm "$1"
}

echo "=== 1. conflict confined to platform/data/ (the provenance collision) ==="
setup
diverge mobile source-data/fuel.json  '{"diesel": 37.11}'
diverge laptop source-data/crops.json '{"rice": 13.5}'
git merge --no-commit --no-ff mobile >/dev/null 2>&1
C=$(git diff --name-only --diff-filter=U); git merge --abort
echo "  plain merge conflicts on: $(echo $C)"
[ "$C" = "platform/data/provenance.json" ] && ok "reproduced the real-world collision" || no "fixture did not collide as expected"
bash pipeline/resolve_derived_conflicts.sh mobile; rc=$?
[ "$rc" -eq 0 ] && ok "resolver exit 0" || no "resolver exit $rc"
[ -z "$(git status --porcelain)" ] && ok "tree clean (committed the merge)" || no "tree dirty after resolve"
git merge-base --is-ancestor mobile HEAD && ok "master side is now an ancestor (branch is mergeable)" || no "did not actually merge"
# both sessions' edits must survive: the conflict was never about their data
grep -q 37.11 source-data/fuel.json  && ok "kept the other session's fuel edit"  || no "lost the other session's fuel edit"
grep -q 13.5  source-data/crops.json && ok "kept this branch's crops edit"       || no "lost this branch's crops edit"
# and the generated file must be a true function of the merged sources, not a text-merge artefact
cp platform/data/provenance.json /tmp/committed.json
python3 pipeline/rederive_drift.py >/dev/null
cmp -s /tmp/committed.json platform/data/provenance.json && ok "provenance reproduces byte-exactly from the merged sources" || no "provenance is a merge artefact, not a rebuild"

echo
echo "=== 2. conflict in source-data/ (accumulator risk) must ABORT ==="
setup
diverge mobile source-data/fuel.json '{"diesel": 37.11}'
diverge laptop source-data/fuel.json '{"diesel": 35.02}'
BEFORE=$(git rev-parse HEAD)
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok "exit 2 (needs a human)" || no "exit $rc, expected 2"
[ "$(git rev-parse HEAD)" = "$BEFORE" ] && ok "branch left untouched" || no "branch was modified"
[ -z "$(git status --porcelain)" ] && ok "no merge left half-applied" || no "left a dirty tree"

echo
echo "=== 3. conflict in code must ABORT ==="
setup
diverge mobile pipeline/code.py 'x = 2'
diverge laptop pipeline/code.py 'x = 3'
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok "exit 2 (needs a human)" || no "exit $rc, expected 2"
[ -z "$(git status --porcelain)" ] && ok "no merge left half-applied" || no "left a dirty tree"

echo
echo "=== 4. already up to date is a no-op ==="
setup
git checkout -q -B laptop master
bash pipeline/resolve_derived_conflicts.sh master >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "exit 0" || no "exit $rc"

echo
echo "=== 5. clean merge still re-derives (an auto-merged generated file is not a rebuilt one) ==="
setup
git checkout -q -B mobile master; echo 'y = 9' > pipeline/other.py; git add -A; git commit -qm mobile
diverge laptop source-data/crops.json '{"rice": 13.5}'
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "exit 0" || no "exit $rc"
cp platform/data/provenance.json /tmp/c2.json; python3 pipeline/rederive_drift.py >/dev/null
cmp -s /tmp/c2.json platform/data/provenance.json && ok "provenance still reproduces" || no "provenance drifted"

echo
echo "=== 6. dirty tree refuses ==="
setup; git checkout -q -B laptop master; echo dirt >> source-data/fuel.json
bash pipeline/resolve_derived_conflicts.sh master >/dev/null 2>&1; rc=$?
[ "$rc" -eq 1 ] && ok "exit 1 (refuses to merge over uncommitted work)" || no "exit $rc, expected 1"

echo
echo "=== 7. runs from a copy OUTSIDE the repo, on a branch that does not contain it ==="
# This is the pr-autoresolve case, and it shipped broken: that job checks out each PR branch, which
# replaces the working tree with that branch's files. Every branch cut before the resolver existed
# therefore loses it mid-loop, and `bash pipeline/resolve_derived_conflicts.sh` died with "No such
# file or directory" — silently skipping exactly the old PRs that most needed refreshing.
setup
OUTSIDE="$(dirname "$R")/resolver-copy.sh"; cp "$SRC" "$OUTSIDE"
diverge mobile source-data/fuel.json  '{"diesel": 37.11}'
diverge laptop source-data/crops.json '{"rice": 13.5}'
git rm -q pipeline/resolve_derived_conflicts.sh; git commit -qm "branch predates the resolver"
bash "$OUTSIDE" mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "exit 0 (found the repo via git, not via \$0)" || no "exit $rc"
[ ! -e pipeline/resolve_derived_conflicts.sh ] && ok "resolved a branch that still lacks the script" || no "fixture did not reproduce the absence"
grep -q 37.11 source-data/fuel.json && ok "merged the other session's edit anyway" || no "did not merge"

echo
echo "=== 8. PROGRESS_LOG top-insertion collision union-merges instead of blocking ==="
# Three of the six open PRs on 2026-08-07 were blocked on nothing but this: both sides append a new
# entry at the top of a reverse-chron log, and git calls independent insertions a conflict.
setup
git checkout -q -B mobile master
printf '# PROGRESS LOG\n\nReverse-chronological.\n\n## 2026-08-06 — master entry\n\nm\n\n## 2026-08-01 — the entry both sides start from\n\nbody\n' > docs/PROGRESS_LOG.md
git commit -qam mobile
git checkout -q -B laptop master
printf '# PROGRESS LOG\n\nReverse-chronological.\n\n## 2026-08-06 — branch entry\n\nb\n\n## 2026-08-01 — the entry both sides start from\n\nbody\n' > docs/PROGRESS_LOG.md
git commit -qam laptop
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "exit 0 (resolved, not escalated)" || no "exit $rc, expected 0"
grep -q "master entry" docs/PROGRESS_LOG.md && ok "kept the other session's entry" || no "lost the other session's entry"
grep -q "branch entry" docs/PROGRESS_LOG.md && ok "kept this branch's entry"      || no "lost this branch's entry"
grep -q "the entry both sides start from" docs/PROGRESS_LOG.md && ok "kept the shared entry" || no "dropped the shared entry"
[ "$(grep -c '^## ' docs/PROGRESS_LOG.md)" -eq 3 ] && ok "exactly 3 entries (no duplication)" || no "entry count is $(grep -c '^## ' docs/PROGRESS_LOG.md), expected 3"
[ -z "$(git status --porcelain)" ] && ok "committed the merge" || no "left a dirty tree"

echo
echo "=== 9. BOTH sides rewording one shared entry is a real conflict and must still ABORT ==="
# The union is safe because each pre-existing entry gets its own 3-way merge. One side editing an
# old entry is taken; both sides editing it differently is a disagreement about the same words and
# has to reach a human rather than being silently decided.
setup
git checkout -q -B mobile master
printf '# PROGRESS LOG\n\nReverse-chronological.\n\n## 2026-08-06 — master entry\n\nm\n\n## 2026-08-01 — the entry both sides start from\n\nMASTER REWORD\n' > docs/PROGRESS_LOG.md
git commit -qam mobile
git checkout -q -B laptop master
printf '# PROGRESS LOG\n\nReverse-chronological.\n\n## 2026-08-06 — branch entry\n\nb\n\n## 2026-08-01 — the entry both sides start from\n\nBRANCH REWORD\n' > docs/PROGRESS_LOG.md
git commit -qam laptop
BEFORE=$(git rev-parse HEAD)
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok "exit 2 (needs a human)" || no "exit $rc, expected 2"
[ "$(git rev-parse HEAD)" = "$BEFORE" ] && ok "branch left untouched" || no "branch was modified"
[ -z "$(git status --porcelain)" ] && ok "no merge left half-applied" || no "left a dirty tree"

echo
echo "=== 10. the feed_history accumulator unions instead of blocking ==="
# The one source-data/ file that is auto-resolved, and only because picking a side DESTROYS data:
# ThaiWater and the pump price publish only "now", so a day dropped here cannot be re-pulled.
fh(){ # <date> <value> [<date> <value>] -> write source-data/feed_history.json
  python3 - "$@" <<'PY'
import json, sys
a = sys.argv[1:]
pts = {a[i]: float(a[i+1]) for i in range(0, len(a), 2)}
d = sorted(pts)
json.dump({"meta": {"n_points": len(d), "n_series": 1},
           "series": {"flood": {"label": "L", "unit": "u", "cadence": "daily", "source": "s",
                                "path": "p", "dates": d, "values": [pts[x] for x in d],
                                "first_seen": d[0], "n": len(d)}}},
          open("source-data/feed_history.json", "w", newline="\n"), indent=1, sort_keys=True)
PY
}
setup
fh 2026-08-04 132; python3 pipeline/rederive_drift.py >/dev/null; git add -A; git commit -qm "base history"
git checkout -q -B mobile master; fh 2026-08-04 132 2026-08-05 136
python3 pipeline/rederive_drift.py >/dev/null; git commit -qam mobile
git checkout -q -B laptop master; fh 2026-08-04 132 2026-08-06 140
python3 pipeline/rederive_drift.py >/dev/null; git commit -qam laptop
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "exit 0 (unioned, not escalated)" || no "exit $rc, expected 0"
DATES=$(python3 -c "import json;print(','.join(json.load(open('source-data/feed_history.json'))['series']['flood']['dates']))")
[ "$DATES" = "2026-08-04,2026-08-05,2026-08-06" ] && ok "kept every day from both sides" || no "dates are $DATES"
VALS=$(python3 -c "import json;print(','.join(str(v) for v in json.load(open('source-data/feed_history.json'))['series']['flood']['values']))")
[ "$VALS" = "132.0,136.0,140.0" ] && ok "values stayed aligned to their dates" || no "values are $VALS"

echo
echo "=== 11. two DIFFERENT readings for the same day resolve to the LATER PULL ==="
# This used to abort for a human, and that was right while the feeds pulled once a day: two
# different numbers for one date meant a real disagreement. At 4x/day it means the gauge moved
# between two honest reads, neither is wrong, and the later one is simply current. PR #414 sat
# blocked overnight on exactly this (flood_high 134.0 vs 133.0 on 2026-08-15) with nothing for a
# human to actually decide. Recency is established from each side's last commit touching the file
# — laptop is committed after mobile here, so laptop's reading is the one that survives.
setup
fh 2026-08-04 132; python3 pipeline/rederive_drift.py >/dev/null; git add -A; git commit -qm "base history"
# Commit stamps are pinned rather than taken from the clock. `git log --format=%ct` has one-second
# resolution, and two fixture commits land in the same second, which ties — and a tie deliberately
# falls back to `theirs` (master, the conservative side). Real pulls are minutes to hours apart, so
# pinning is what makes this fixture test the intended path instead of the tie-breaker's fallback.
git checkout -q -B mobile master; fh 2026-08-04 132 2026-08-05 136
python3 pipeline/rederive_drift.py >/dev/null
GIT_AUTHOR_DATE="2026-08-15T10:00:00Z" GIT_COMMITTER_DATE="2026-08-15T10:00:00Z" git commit -qam mobile
git checkout -q -B laptop master; fh 2026-08-04 132 2026-08-05 999
python3 pipeline/rederive_drift.py >/dev/null
GIT_AUTHOR_DATE="2026-08-15T10:10:00Z" GIT_COMMITTER_DATE="2026-08-15T10:10:00Z" git commit -qam laptop
bash pipeline/resolve_derived_conflicts.sh mobile > "$TMP/out11.txt" 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "exit 0 (resolved by recency, not escalated)" || no "exit $rc, expected 0"
GOT11=$(python3 -c "import json;d=json.load(open('source-data/feed_history.json'));s=d['series']['flood'];print(dict(zip(s['dates'],s['values'])).get('2026-08-05'))")
[ "$GOT11" = "999.0" ] && ok "kept the later pull's reading (999.0)" || no "kept $GOT11, expected 999.0"
grep -q "resolved by recency" "$TMP/out11.txt" \
  && ok "reported the dropped reading instead of silently discarding it" \
  || no "no override was reported (a dropped reading must never be silent)"

echo
echo "=== 12. a contested LABEL still needs a human, even though readings no longer do ==="
# The recency tie-break is only ever about measurements. Two different labels for one series is
# editorial — nobody's gauge moved — so it must still stop rather than pick the newer wording.
setup
fh 2026-08-04 132; python3 pipeline/rederive_drift.py >/dev/null; git add -A; git commit -qm "base history"
relabel(){ python3 - "$1" <<'PY'
import json, sys
p = "source-data/feed_history.json"
d = json.load(open(p))
d["series"]["flood"]["label"] = sys.argv[1]
json.dump(d, open(p, "w", newline="\n"), indent=1, sort_keys=True)
PY
}
git checkout -q -B mobile master; fh 2026-08-04 132 2026-08-05 136; relabel "Flood — mobile wording"
python3 pipeline/rederive_drift.py >/dev/null; git commit -qam mobile
git checkout -q -B laptop master; fh 2026-08-04 132 2026-08-06 140; relabel "Flood — laptop wording"
python3 pipeline/rederive_drift.py >/dev/null; git commit -qam laptop
BEFORE=$(git rev-parse HEAD)
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok "exit 2 (needs a human)" || no "exit $rc, expected 2"
[ "$(git rev-parse HEAD)" = "$BEFORE" ] && ok "branch left untouched" || no "branch was modified"

echo
echo "=== 13. a PULLED snapshot under platform/data/ keeps the NEWER reading, not the base's ==="
# The failure this pins is silent, which is why it needs a fixture rather than a code comment:
# thaiwater_flood.json lives under platform/data/ but no builder produces it, so the blanket
# "take the base's side, it will be recomputed" reverts it to yesterday and the re-derive never
# notices. The gate still passes — the tree IS self-consistent — and the live card just shows the
# older reading. Here the branch holds 08-07 and the base holds 08-06; the branch must win.
pulse(){ printf '{"meta": {"observed_to": "%s", "pulled": "%s"}, "n_high": %s}\n' "$1" "$1" "$2" \
         > platform/data/thaiwater_flood.json; }
setup
pulse 2026-08-05 4; git add -A; git commit -qm "base pulse"
git checkout -q -B mobile master; pulse 2026-08-06 7
python3 pipeline/rederive_drift.py >/dev/null; git commit -qam mobile
git checkout -q -B laptop master; pulse 2026-08-07 9
python3 pipeline/rederive_drift.py >/dev/null; git commit -qam laptop
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "exit 0 (resolved, not escalated)" || no "exit $rc, expected 0"
GOT=$(python3 -c "import json;d=json.load(open('platform/data/thaiwater_flood.json'));print(d['meta']['observed_to'],d['n_high'])")
[ "$GOT" = "2026-08-07 9" ] && ok "kept the newer 08-07 reading over the base's 08-06" \
                            || no "kept '$GOT', expected '2026-08-07 9'"

# ...and the reverse: when the BASE is newer, the base still wins. The rule is newer-wins, not
# always-keep-mine — otherwise a stale branch would clobber a fresher reading already on master.
setup
pulse 2026-08-05 4; git add -A; git commit -qm "base pulse"
git checkout -q -B mobile master; pulse 2026-08-09 11
python3 pipeline/rederive_drift.py >/dev/null; git commit -qam mobile
git checkout -q -B laptop master; pulse 2026-08-06 7
python3 pipeline/rederive_drift.py >/dev/null; git commit -qam laptop
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1
GOT=$(python3 -c "import json;d=json.load(open('platform/data/thaiwater_flood.json'));print(d['meta']['observed_to'],d['n_high'])")
[ "$GOT" = "2026-08-09 11" ] && ok "a stale branch does NOT clobber the newer base reading" \
                             || no "kept '$GOT', expected '2026-08-09 11'"

# A genuinely generated layer has no observation stamp, so it must take exactly the path it took
# before this rule existed — base's side, then rebuilt. This is the no-regression guard.
setup
diverge mobile source-data/fuel.json  '{"diesel": 37.11}'
diverge laptop source-data/crops.json '{"rice": 13.5}'
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "unstamped generated layer still resolves as before" || no "exit $rc"
python3 pipeline/rederive_drift.py > /dev/null
git diff --quiet -- platform/data/provenance.json \
  && ok "provenance reproduces from the merged sources" || no "provenance did not reproduce"

echo
echo "=== 14. the swarm's run log unions instead of blocking (the other half of PR #414) ==="
# source-data/swarm_runs.json had no merger at all, so it fell through to "REAL CONFLICT" and
# stopped the run — for an append-only audit trail where the two sides disagreed about nothing.
# Every row is the only record of a run that cannot be replayed, so neither side may be taken whole.
sw(){ python3 - "$@" <<'PY'
import json, sys
runs = [{"started": s, "finished": s, "n_ok": 10, "jobs": 6} for s in sys.argv[1:]]
doc = {"meta": {"generated_by": "pipeline/pull_swarm.py", "max_runs": 60, "n_runs": len(runs)},
       "runs": runs}
with open("source-data/swarm_runs.json", "w", newline="\n") as fh:
    fh.write(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
PY
}
setup
sw 2026-08-09T02:57:25Z; python3 pipeline/rederive_drift.py >/dev/null; git add -A; git commit -qm "base runs"
git checkout -q -B mobile master; sw 2026-08-09T02:57:25Z 2026-08-11T10:28:47Z
python3 pipeline/rederive_drift.py >/dev/null; git commit -qam mobile
git checkout -q -B laptop master; sw 2026-08-09T02:57:25Z 2026-08-14T10:36:23Z
python3 pipeline/rederive_drift.py >/dev/null; git commit -qam laptop
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "exit 0 (unioned, not escalated to a human)" || no "exit $rc, expected 0"
GOT=$(python3 -c "import json;print(' '.join(r['started'] for r in json.load(open('source-data/swarm_runs.json'))['runs']))")
[ "$GOT" = "2026-08-09T02:57:25Z 2026-08-11T10:28:47Z 2026-08-14T10:36:23Z" ] \
  && ok "kept every run from both sides, ordered by start stamp" \
  || no "got '$GOT' — a run record was lost"
python3 pipeline/rederive_drift.py >/dev/null
git diff --quiet -- platform/data/provenance.json \
  && ok "provenance reproduces from the unioned run log" || no "provenance did not reproduce"

# ...but a REWRITTEN run — same start stamp, different outcome — is not an append, and must stop.
setup
sw 2026-08-09T02:57:25Z; python3 pipeline/rederive_drift.py >/dev/null; git add -A; git commit -qm "base runs"
bend(){ python3 - "$1" <<'PY'
import json, sys
p = "source-data/swarm_runs.json"
d = json.load(open(p))
d["runs"][0]["n_ok"] = int(sys.argv[1])
with open(p, "w", newline="\n") as fh:
    fh.write(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
PY
}
git checkout -q -B mobile master; bend 3; python3 pipeline/rederive_drift.py >/dev/null; git commit -qam mobile
git checkout -q -B laptop master; bend 7; python3 pipeline/rederive_drift.py >/dev/null; git commit -qam laptop
BEFORE=$(git rev-parse HEAD)
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok "a rewritten run record still needs a human (exit 2)" || no "exit $rc, expected 2"
[ "$(git rev-parse HEAD)" = "$BEFORE" ] && ok "branch left untouched" || no "branch was modified"

echo
echo "=== 15. pick_newer_stamp's own unit cases ==="
setup
python3 pipeline/pick_newer_stamp.py --selftest >/dev/null 2>&1 \
  && ok "pick_newer_stamp --selftest (13 cases)" || no "pick_newer_stamp --selftest"

echo
echo "=== 16. the mergers' own unit cases ==="
python3 pipeline/merge_append_log.py   --selftest >/dev/null 2>&1 && ok "merge_append_log --selftest (13 cases)"   || no "merge_append_log --selftest failed"
python3 pipeline/merge_feed_history.py --selftest >/dev/null 2>&1 && ok "merge_feed_history --selftest (20 cases)" || no "merge_feed_history --selftest failed"
python3 pipeline/merge_swarm_runs.py   --selftest >/dev/null 2>&1 && ok "merge_swarm_runs --selftest (12 cases)"   || no "merge_swarm_runs --selftest failed"

echo
echo "==================== $PASS passed, $FAIL failed ===================="
[ "$FAIL" -eq 0 ]
