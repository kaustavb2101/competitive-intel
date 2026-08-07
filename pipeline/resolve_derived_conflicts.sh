#!/usr/bin/env bash
# resolve_derived_conflicts.sh — bring a branch up to date with master without conflicting on
# generated data layers.
#
# THE PROBLEM
# -----------
# platform/data/ is generated but committed (Vercel serves it statically, so it has to be). Every
# branch that touches data regenerates provenance.json — a single-line census of all 441 files — so
# ANY two such branches conflict there, guaranteed, on a line git cannot 3-way merge. Working from
# two places at once (a laptop session and a phone session) makes that collision the normal case:
# master moves, and every open PR is blocked on a file nobody actually edited.
#
# THE INSIGHT
# -----------
# You never have to merge a generated file. The determinism gate proves, 132 times per run, that
# every layer in platform/data/ reproduces byte-exactly from committed sources. So a conflict there
# is not a disagreement to reconcile — it is two stale copies of a pure function. Throw both away,
# take master's, and recompute.
#
# THE RULE
# --------
#   conflicts confined to platform/data/**  -> take master's side, re-derive, done.
#   a conflict ANYWHERE else                -> a real disagreement. Abort untouched, leave it to a human.
#
# source-data/ is deliberately NOT auto-resolved even though some of it is derived. It also holds the
# raw pulls, and two of those (source-data/feed_history.json and its platform twin) are ACCUMULATORS
# for feeds that publish only "now" — ThaiWater gauges, the Bangchak pump price. Taking either side
# whole silently deletes a day of telemetry that cannot be re-pulled, because the file exists
# precisely because the API has no archive. That needs a date-keyed union by a human who can see what
# each side added, so a source-data conflict aborts rather than guessing.
#
#     bash pipeline/resolve_derived_conflicts.sh [base-ref]      # default origin/master
#
# Exit 0 = up to date (already, or resolved). 2 = a real conflict a human must settle. 1 = error.
set -uo pipefail

BASE="${1:-origin/master}"

# Find the repo from git, NOT from $0. This script is invoked from a copy that lives OUTSIDE the
# tree it operates on: pr-autoresolve checks out each PR branch in turn, and that replaces the
# working tree with THAT BRANCH's files — so any branch cut before this script existed deletes the
# script out from under the loop mid-run. Deriving the root from $0 would then point at whatever
# directory the surviving copy happens to sit in. Anchoring on the current repo instead makes the
# script relocatable, which is the property the caller actually needs.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || ROOT=""
[ -z "$ROOT" ] && ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || { echo "FATAL: cannot enter repo root '$ROOT'." >&2; exit 1; }

if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  echo "FATAL: base ref '$BASE' does not exist." >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "FATAL: working tree is dirty — refusing to merge on top of uncommitted work." >&2
  exit 1
fi

if git merge-base --is-ancestor "$BASE" HEAD; then
  echo "already contains $BASE — nothing to do."
  exit 0
fi

git merge --no-commit --no-ff "$BASE" >/dev/null 2>&1
CONFLICTS="$(git diff --name-only --diff-filter=U)"

if [ -z "$CONFLICTS" ]; then
  # Merged cleanly. Still re-derive: git can text-merge two generated files into a state that is
  # neither side's output and reproduces from nothing — a clean merge is not a rebuilt one.
  echo "clean merge — re-deriving anyway (an auto-merged generated file is not a rebuilt one)."
else
  OUTSIDE="$(echo "$CONFLICTS" | grep -v '^platform/data/' || true)"
  if [ -n "$OUTSIDE" ]; then
    echo "REAL CONFLICT — outside the generated layers, leaving it for a human:" >&2
    echo "$OUTSIDE" | sed 's/^/  /' >&2
    git merge --abort
    exit 2
  fi
  echo "$(echo "$CONFLICTS" | wc -l) generated layer(s) conflicted — taking $BASE's side, then re-deriving:"
  echo "$CONFLICTS" | sed 's/^/  /'
  # --theirs is the side being merged IN, i.e. the base. Whatever it holds is about to be
  # recomputed anyway; this only needs to produce a resolved index the re-derive can overwrite.
  echo "$CONFLICTS" | while IFS= read -r f; do
    [ -z "$f" ] && continue
    git checkout --theirs -- "$f" 2>/dev/null || git rm -q -- "$f"
    git add -- "$f" 2>/dev/null || true
  done
fi

python3 pipeline/rederive_drift.py || {
  echo "FATAL: re-derive did not converge — not committing a half-rebuilt tree." >&2
  git merge --abort 2>/dev/null || true
  exit 1
}

git add -u source-data platform/data
git commit --no-edit -q
echo "merged $BASE and re-derived. Branch is mergeable again."
