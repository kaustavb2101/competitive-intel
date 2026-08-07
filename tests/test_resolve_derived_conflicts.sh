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
echo "=== 9. an EDITED shared log entry is a real conflict and must still ABORT ==="
# The union is only valid because the file is append-only. If a side reworded someone else's entry
# that assumption is void, and this must fall back to the human path rather than silently picking.
setup
git checkout -q -B mobile master
printf '# PROGRESS LOG\n\nReverse-chronological.\n\n## 2026-08-06 — master entry\n\nm\n\n## 2026-08-01 — the entry both sides start from\n\nbody\n' > docs/PROGRESS_LOG.md
git commit -qam mobile
git checkout -q -B laptop master
printf '# PROGRESS LOG\n\nReverse-chronological.\n\n## 2026-08-06 — branch entry\n\nb\n\n## 2026-08-01 — the entry both sides start from\n\nREWORDED\n' > docs/PROGRESS_LOG.md
git commit -qam laptop
BEFORE=$(git rev-parse HEAD)
bash pipeline/resolve_derived_conflicts.sh mobile >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok "exit 2 (needs a human)" || no "exit $rc, expected 2"
[ "$(git rev-parse HEAD)" = "$BEFORE" ] && ok "branch left untouched" || no "branch was modified"
[ -z "$(git status --porcelain)" ] && ok "no merge left half-applied" || no "left a dirty tree"

echo
echo "=== 10. merge_append_log.py's own unit cases ==="
python3 pipeline/merge_append_log.py --selftest >/dev/null 2>&1 && ok "--selftest (9 cases)" || no "--selftest failed"

echo
echo "==================== $PASS passed, $FAIL failed ===================="
[ "$FAIL" -eq 0 ]
