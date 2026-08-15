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
# source-data/ is deliberately NOT auto-resolved as a class, because it holds the raw pulls and
# taking either side whole would silently drop one. The ONE exception is
# source-data/feed_history.json, an accumulator for feeds that publish only "now" — ThaiWater
# gauges, the Bangchak pump price — where the API has no archive and the committed file is the only
# copy of yesterday. Picking a side there deletes a day of telemetry that cannot be re-pulled; the
# correct answer is a date-keyed union, which merge_feed_history.py does exactly (and refuses when
# the two sides report DIFFERENT values for the same series on the same date). Everything else
# under source-data/ still aborts rather than guessing.
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

  # APPEND-ONLY FILES. Three of them collide on every concurrent branch for the same reason:
  #   docs/PROGRESS_LOG.md           both sides insert a new entry at the top of a reverse-chron log
  #   source-data/feed_history.json  both sides append a day to an accumulator whose sources
  #                                  publish only "now" and keep no archive
  #   source-data/swarm_runs.json    both sides append a row to the swarm's own audit trail; the
  #                                  runs are not re-playable, so either side taken whole loses one
  # None is a disagreement — each side holds something the other never saw. The mergers union them,
  # but each does a real 3-way merge per entry / per (series, date) / per run first and REFUSES
  # (exit 3) if both sides changed the same one differently. Anything they refuse stays in OUTSIDE
  # and aborts the run exactly as before, so no contested text or measurement is ever auto-decided.
  #
  # The ONE exception, added after PR #414 sat blocked overnight on it: feed_history's per-date
  # measurement clash. At 4x/day two pulls of the same gauge on the same date legitimately differ,
  # neither is wrong, and paging a human to say "take the later one" every time is not automation.
  # That case now resolves to the later pull — established below from git, never guessed inside the
  # merger — and prints what it dropped. A contested LABEL still stops, because that is editorial.
  if [ -n "$OUTSIDE" ]; then
    REMAINING=""
    STAGE="$(mktemp -d)"
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      MERGER=""; MERGER_ARGS=""
      case "$f" in
        docs/PROGRESS_LOG.md)            MERGER=pipeline/merge_append_log.py ;;
        source-data/swarm_runs.json)     MERGER=pipeline/merge_swarm_runs.py ;;
        source-data/feed_history.json)
          MERGER=pipeline/merge_feed_history.py
          # WHICH SIDE IS THE LATER PULL. The merger refuses when both sides recorded a different
          # value for the same series on the same date, and at 4x/day that is now routine: the
          # gauge simply moved between two honest reads. The right answer is the later reading,
          # but nothing INSIDE the file proves recency — so establish it here, where git can,
          # from the last commit that touched this file on each side. HEAD is the PR branch
          # (ours); $BASE is master (theirs). Equal stamps or missing history fall back to
          # theirs, which is master, which is the more conservative of the two.
          OURS_T="$(git log -1 --format=%ct HEAD -- "$f" 2>/dev/null || echo 0)"
          THEIRS_T="$(git log -1 --format=%ct "$BASE" -- "$f" 2>/dev/null || echo 0)"
          if [ "${OURS_T:-0}" -gt "${THEIRS_T:-0}" ]; then PREFER=ours; else PREFER=theirs; fi
          MERGER_ARGS="--prefer-on-conflict $PREFER"
          echo "  feed_history: later pull is '$PREFER' (ours=${OURS_T:-0} theirs=${THEIRS_T:-0})"
          ;;
      esac
      if [ -n "$MERGER" ] && [ -f "$MERGER" ]; then
        git show ":1:$f" > "$STAGE/base"   2>/dev/null || : > "$STAGE/base"
        git show ":2:$f" > "$STAGE/ours"   2>/dev/null || : > "$STAGE/ours"
        git show ":3:$f" > "$STAGE/theirs" 2>/dev/null || : > "$STAGE/theirs"
        if python3 "$MERGER" --base "$STAGE/base" --ours "$STAGE/ours" \
                             --theirs "$STAGE/theirs" --out "$f" $MERGER_ARGS; then
          git add -- "$f"
          echo "union-merged $f (append-only — kept both sides' rows)"
          continue
        fi
      fi
      REMAINING="${REMAINING}${f}
"
    done <<EOF
$OUTSIDE
EOF
    rm -rf "$STAGE"
    OUTSIDE="$(echo "$REMAINING" | grep -v '^$' || true)"
    CONFLICTS="$(git diff --name-only --diff-filter=U)"
  fi

  if [ -n "$OUTSIDE" ]; then
    echo "REAL CONFLICT — outside the generated layers, leaving it for a human:" >&2
    echo "$OUTSIDE" | sed 's/^/  /' >&2
    git merge --abort
    exit 2
  fi
  if [ -n "$CONFLICTS" ]; then
    echo "$(echo "$CONFLICTS" | wc -l) generated layer(s) conflicted — taking $BASE's side, then re-deriving:"
    echo "$CONFLICTS" | sed 's/^/  /'
  fi
  # --theirs is the side being merged IN, i.e. the base. Whatever it holds is about to be
  # recomputed anyway; this only needs to produce a resolved index the re-derive can overwrite.
  #
  # EXCEPT for the pulled snapshots. thaiwater_flood.json / thaiwater_rain.json live under
  # platform/data/ but have no builder behind them — they ARE the pull. Taking the base's side of
  # one reverts it to the older reading, and no re-derive will ever put the newer one back: the
  # gate stays green because the tree is self-consistent, the live card just quietly shows
  # yesterday while feed_history (which accumulates separately) keeps today. pick_newer_stamp.py
  # reads each side's OWN declared observation date and keeps the newer; with no stamp on both
  # sides it answers "theirs", so every genuinely generated layer takes exactly the path it did
  # before. Seen for real on 2026-08-07 landing two ThaiWater PRs — four files would have reverted.
  STAGE2="$(mktemp -d)"
  echo "$CONFLICTS" | while IFS= read -r f; do
    [ -z "$f" ] && continue
    SIDE=theirs
    if [ -f pipeline/pick_newer_stamp.py ]; then
      git show ":2:$f" > "$STAGE2/ours"   2>/dev/null || : > "$STAGE2/ours"
      git show ":3:$f" > "$STAGE2/theirs" 2>/dev/null || : > "$STAGE2/theirs"
      PICKED="$(python3 pipeline/pick_newer_stamp.py --ours "$STAGE2/ours" \
                       --theirs "$STAGE2/theirs" 2>/tmp/pick_why)" || PICKED=theirs
      if [ "$PICKED" = "ours" ]; then
        SIDE=ours
        echo "  kept OUR $f — $(cat /tmp/pick_why)"
      fi
    fi
    git checkout "--$SIDE" -- "$f" 2>/dev/null || git rm -q -- "$f"
    git add -- "$f" 2>/dev/null || true
  done
  rm -rf "$STAGE2"
fi

python3 pipeline/rederive_drift.py || {
  echo "FATAL: re-derive did not converge — not committing a half-rebuilt tree." >&2
  git merge --abort 2>/dev/null || true
  exit 1
}

git add -u source-data platform/data
git commit --no-edit -q
echo "merged $BASE and re-derived. Branch is mergeable again."
