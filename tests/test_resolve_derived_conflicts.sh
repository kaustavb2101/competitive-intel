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
  rm -rf "$R"; mkdir -p "$R/pipeline" "$R/source-data" "$R/platform/data"; cd "$R" || exit 1
  git init -q; git config user.email t@t; git config user.name t; git config commit.gpgsign false
  cp "$SRC" pipeline/resolve_derived_conflicts.sh
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
echo "==================== $PASS passed, $FAIL failed ===================="
[ "$FAIL" -eq 0 ]
