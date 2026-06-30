#!/usr/bin/env bash
# AutoX credit-intelligence — single test entrypoint.
#
# Phases (run all by default; pass a phase name to run just one):
#   check    determinism gate: pipeline --check + node --check on app.js & every page's inline JS
#            + data integrity (validate_data.py over platform/data/*.json)
#   render   headless-render every page in tests/pages.manifest with self-hosted deck.gl/leaflet
#   health   per-page smoke: no uncaught errors, lib init, non-blank canvas, DOM hooks present
#   visual   compare fresh renders to tests/baseline/*.png within tolerance
#   baseline (re)generate tests/baseline/*.png from current pages (use when a change is intended)
#
# Usage:
#   tests/run.sh                 # check + render + health + visual  (the CI gate)
#   tests/run.sh check           # offline, no chromium/npm needed beyond python
#   tests/run.sh baseline        # refresh committed baselines
#
# Network: ONLY the npm registry (to install deck.gl/leaflet into tests/.cache). NO data pulls.
set -u
TESTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$TESTS")"
PLATFORM="$REPO/platform"
PIPE="$REPO/pipeline"
LIB="$TESTS/lib"
CACHE="$TESTS/.cache"
WORK="$TESTS/.work"
BASE="$TESTS/baseline"
MANIFEST="$TESTS/pages.manifest"
BUDGET="${QA_BUDGET:-12000}"
SIZE="${QA_SIZE:-1100,800}"
VISUAL_TOL="${QA_VISUAL_TOL:-12}"   # max mean per-pixel RGB diff vs baseline

PHASE="${1:-all}"
RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; RST=$'\033[0m'
pass=0; failc=0
ok(){ printf '%s[PASS]%s %s\n' "$GRN" "$RST" "$1"; pass=$((pass+1)); }
bad(){ printf '%s[FAIL]%s %s\n' "$RED" "$RST" "$1"; failc=$((failc+1)); }
hdr(){ printf '\n%s== %s ==%s\n' "$YLW" "$1" "$RST"; }

manifest_rows(){ grep -vE '^\s*#' "$MANIFEST" | grep -vE '^\s*$'; }

# ---------------------------------------------------------------------------
deps(){
  if [ -f "$CACHE/node_modules/deck.gl/dist.min.js" ] && [ -f "$CACHE/node_modules/leaflet/dist/leaflet.js" ]; then
    return 0
  fi
  hdr "installing self-hosted deps (npm registry only)"
  mkdir -p "$CACHE"
  # npm --prefix reads package.json from the prefix dir, so seed it there from the committed pin.
  cp "$TESTS/package.json" "$CACHE/package.json"
  ( cd "$CACHE" && npm install --no-audit --no-fund --no-package-lock --loglevel=error ) || {
    bad "npm install failed (need deck.gl@8.9.35 + leaflet@1.9.4)"; return 1; }
  [ -f "$CACHE/node_modules/deck.gl/dist.min.js" ] || { bad "deck.gl bundle missing after install"; return 1; }
  ok "deps installed into tests/.cache/node_modules"
}

# ---------------------------------------------------------------------------
phase_check(){
  hdr "determinism + syntax gate"
  ( cd "$PIPE" && python3 derive.py --check >/dev/null 2>&1 ) && ok "derive.py --check" || bad "derive.py --check (platform/data drifted from source-data)"
  ( cd "$PIPE" && python3 build_province.py --check >/dev/null 2>&1 ) && ok "build_province.py --check" || bad "build_province.py --check (province files drifted)"
  ( cd "$PIPE" && python3 build_amphoe.py --check >/dev/null 2>&1 ) && ok "build_amphoe.py --check" || bad "build_amphoe.py --check (amphoe.json drifted from source-data)"
  # NOTE: bake_catchment_heights.py --check was removed from the gate once rayong_catchment.json
  # became an Overture PULL artifact (pull_overture_buildings.py, ~124k buildings). Like branches.json
  # and the competitor census, a network-pulled file is not byte-reproducible offline, so it does not
  # belong in the determinism gate. The baker remains as a tool (and exports bldg_height, which the
  # Overture puller imports for estimated heights).
  ( cd "$PIPE" && python3 timeseries.py --check >/dev/null 2>&1 ) && ok "timeseries.py --check" || bad "timeseries.py --check (snapshot/deltas drifted from source-data)"
  ( cd "$PIPE" && python3 build_occupations.py --check >/dev/null 2>&1 ) && ok "build_occupations.py --check" || bad "build_occupations.py --check (branch_occupations.json drifted from overture_places.json)"
  ( cd "$PIPE" && python3 build_amphoe_occupations.py --check >/dev/null 2>&1 ) && ok "build_amphoe_occupations.py --check" || bad "build_amphoe_occupations.py --check (amphoe_occupations.json drifted from overture_places.json)"
  ( cd "$PIPE" && python3 build_opportunity_score.py --check >/dev/null 2>&1 ) && ok "build_opportunity_score.py --check" || bad "build_opportunity_score.py --check (opportunity_score.json drifted from amphoe.json/crop_stress.json/competitors)"
  ( cd "$PIPE" && python3 build_competitor_coverage.py --check >/dev/null 2>&1 ) && ok "build_competitor_coverage.py --check" || bad "build_competitor_coverage.py --check (competitor_coverage.json drifted from the competitor census)"
  ( cd "$PIPE" && python3 ingest_tmli.py --check >/dev/null 2>&1 ) && ok "ingest_tmli.py --check" || bad "ingest_tmli.py --check (TMLI measured province layers drifted from source-data/tmli/)"
  ( cd "$PIPE" && python3 build_household_risk.py --check >/dev/null 2>&1 ) && ok "build_household_risk.py --check" || bad "build_household_risk.py --check (household_risk_by_province.json drifted from source-data NSO SES layers)"

  node --check "$PLATFORM/app.js" >/dev/null 2>&1 && ok "node --check app.js" || bad "node --check app.js (syntax error)"

  # every page: extract each inline <script> (that has no src) and node --check it.
  # skip the _qa_*.html render temp copies (gitignored; may linger between runs) so the gate is
  # deterministic regardless of leftover work files.
  for pg in "$PLATFORM"/*.html; do
    name="$(basename "$pg")"
    case "$name" in _qa_*) continue;; esac
    python3 "$LIB/extract_inline_js.py" "$pg" "$WORK/inline" >/dev/null 2>&1 || { bad "extract inline JS from $name"; continue; }
    nbad=0
    for js in "$WORK/inline/$name".*.js; do
      [ -f "$js" ] || continue
      node --check "$js" >/dev/null 2>&1 || { node --check "$js" 2>&1 | head -2 | sed 's/^/      /'; nbad=$((nbad+1)); }
    done
    [ "$nbad" -eq 0 ] && ok "node --check inline JS of $name" || bad "node --check inline JS of $name ($nbad block(s) failed)"
  done

  # data-integrity sub-check: assert platform/data/*.json is internally sane (offline, stdlib).
  # The determinism/syntax checks above don't look INSIDE the data; this does. Its own per-check
  # report is shown so a failure points at the exact integrity violation (an IPO-readiness gate).
  if python3 "$TESTS/validate_data.py"; then
    ok "validate_data.py (platform/data integrity)"
  else
    bad "validate_data.py (platform/data integrity — see report above)"
  fi
}

# ---------------------------------------------------------------------------
render_one(){  # <id> <pagequery> <outdir>
  bash "$LIB/render.sh" "$2" "$3/$1.png" "$BUDGET" "$SIZE" >/dev/null 2>&1
  [ -f "$3/$1.png" ]
}

phase_render(){
  deps || return 1
  hdr "headless render -> tests/.work/render"
  rm -rf "$WORK/render"; mkdir -p "$WORK/render"
  while IFS=$'\t' read -r id pathq gl mincanvas hooks; do
    [ -z "${id:-}" ] && continue
    if render_one "$id" "$pathq" "$WORK/render"; then ok "render $id ($pathq)"; else bad "render $id ($pathq)"; fi
  done < <(manifest_rows)
}

phase_health(){
  hdr "page-health smoke"
  while IFS=$'\t' read -r id pathq gl mincanvas hooks; do
    [ -z "${id:-}" ] && continue
    png="$WORK/render/$id.png"
    if [ ! -f "$png" ]; then bad "health $id (no render — run 'render' first)"; continue; fi
    printf '  %s:\n' "$id"
    if bash "$LIB/health.sh" "$png" "$gl" "$mincanvas" "$hooks"; then ok "health $id"; else bad "health $id"; fi
  done < <(manifest_rows)
}

phase_visual(){
  hdr "visual regression (tol mean-diff <= $VISUAL_TOL)"
  while IFS=$'\t' read -r id pathq gl mincanvas hooks; do
    [ -z "${id:-}" ] && continue
    fresh="$WORK/render/$id.png"; base="$BASE/$id.png"
    if [ ! -f "$fresh" ]; then bad "visual $id (no fresh render)"; continue; fi
    if [ ! -f "$base" ]; then bad "visual $id (no baseline — run 'tests/run.sh baseline')"; continue; fi
    d="$(python3 "$LIB/diffpng.py" "$base" "$fresh")"
    md="$(printf '%s' "$d" | sed -n 's/.*"mean_diff": *\([0-9.]*\).*/\1/p')"
    dm="$(printf '%s' "$d" | grep -o '"dim_mismatch": true')"
    if [ -n "$dm" ]; then bad "visual $id (dimension mismatch: $d)"; continue; fi
    if python3 -c "import sys;sys.exit(0 if float('${md:-999}')<=$VISUAL_TOL else 1)"; then
      ok "visual $id (mean_diff=$md)"
    else
      bad "visual $id (mean_diff=$md > $VISUAL_TOL)"
    fi
  done < <(manifest_rows)
}

phase_baseline(){
  deps || return 1
  hdr "(re)generating baselines -> tests/baseline"
  mkdir -p "$BASE"
  while IFS=$'\t' read -r id pathq gl mincanvas hooks; do
    [ -z "${id:-}" ] && continue
    if render_one "$id" "$pathq" "$BASE"; then
      rm -f "$BASE/$id.dom.html"   # keep only the png in baseline
      ok "baseline $id"
    else
      bad "baseline $id"
    fi
  done < <(manifest_rows)
  printf '\n%sBaselines written. Review the PNGs, then commit tests/baseline/*.png%s\n' "$YLW" "$RST"
}

# ---------------------------------------------------------------------------
mkdir -p "$WORK"
case "$PHASE" in
  check)    phase_check ;;
  render)   phase_render ;;
  health)   phase_health ;;
  visual)   phase_visual ;;
  baseline) phase_baseline ;;
  all)      phase_check; phase_render; phase_health; phase_visual ;;
  *) echo "unknown phase: $PHASE (use: check|render|health|visual|baseline|all)"; exit 2 ;;
esac

printf '\n%s========================================%s\n' "$YLW" "$RST"
printf 'RESULT: %s%d passed%s, %s%d failed%s\n' "$GRN" "$pass" "$RST" "$RED" "$failc" "$RST"
[ "$failc" -eq 0 ]
