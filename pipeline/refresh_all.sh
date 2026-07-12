#!/usr/bin/env bash
# AutoX credit-intelligence — one-command deterministic refresh of every derived data layer.
#
# Re-runs every NETWORK-FREE, DETERMINISTIC builder in dependency order, each immediately followed
# by its own --check (byte-exact reproduce gate). A routine "rebuild the platform/data layers from
# the master" is therefore a single command:
#
#     bash pipeline/refresh_all.sh
#
# Properties:
#   - network-free: pulls NOTHING. It only re-projects source-data -> platform/data. (Live pulls live
#     in autox_enrich_loop.py / the pull_* scripts and are deliberately NOT invoked here.)
#   - deterministic: each builder is re-run then --check'd; drift fails loudly.
#   - skip-pass: a builder whose OPTIONAL upstream source is absent is run anyway — these builders
#     pass quietly (occupations builders no-op without source-data/overture_places.json), so a missing
#     optional layer never breaks the refresh. ingest_tmli.py is run only if it exists in this tree.
#   - it does NOT touch app.js / HTML / styles.css; it only regenerates platform/data/*.json.
#
# After this completes clean, `bash tests/run.sh check` should be 0-failed (incl. the provenance gate).
#
# Exit: 0 if every builder + every --check passed; non-zero (count of failures) otherwise.
set -u

PIPE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$PIPE")"

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; RST=$'\033[0m'
pass=0; failc=0; skipc=0
ok()   { printf '%s[ OK ]%s %s\n'   "$GRN" "$RST" "$1"; pass=$((pass+1)); }
bad()  { printf '%s[FAIL]%s %s\n'   "$RED" "$RST" "$1"; failc=$((failc+1)); }
skip() { printf '%s[SKIP]%s %s\n'   "$YLW" "$RST" "$1"; skipc=$((skipc+1)); }
hdr()  { printf '\n%s== %s ==%s\n'  "$YLW" "$1" "$RST"; }

# build <script> <human-label>
# Runs `python3 <script>` (regenerate) then `python3 <script> --check` (verify byte-exact).
build() {
  local script="$1" label="$2"
  local path="$PIPE/$script"
  if [ ! -f "$path" ]; then
    skip "$label ($script not present in this tree — skipped)"
    return 0
  fi
  hdr "$label"
  if ( cd "$PIPE" && python3 "$script" ); then
    if ( cd "$PIPE" && python3 "$script" --check >/dev/null 2>&1 ); then
      ok "$label — rebuilt + --check byte-exact"
    else
      bad "$label — --check FAILED after rebuild (output drifted; investigate)"
    fi
  else
    # The plain run exited non-zero. Distinguish a genuine failure from a skip-pass: builders that
    # depend on an OPTIONAL upstream source (e.g. overture_places.json) refuse to overwrite when it
    # is absent — but their own --check passes QUIETLY in that case (nothing to drift). So if --check
    # succeeds, the missing optional source is the cause and we SKIP-PASS rather than fail the refresh.
    if ( cd "$PIPE" && python3 "$script" --check >/dev/null 2>&1 ); then
      skip "$label — optional upstream source absent (builder no-op; committed output unchanged)"
    else
      bad "$label — builder exited non-zero"
    fi
  fi
}

printf '%sAutoX refresh_all — deterministic, network-free re-build of platform/data/%s\n' "$YLW" "$RST"
printf 'repo: %s\n' "$REPO"

# --- dependency order -------------------------------------------------------
# 1) project the master -> platform/data (branches.json + meta.json). Everything below reads
#    source-data and/or these projected layers, so derive must run first.
build derive.py                    "derive.py            (master -> branches/meta)"
# 2) district + province intelligence (read branches_final + th_amphoe + gov layers).
build build_amphoe.py              "build_amphoe.py      (928-district whitespace + risk)"
build build_province.py            "build_province.py    (77-province deep-dives + index)"
# 3) per-province agri stress (OAE area + Pink Sheet proxy + HDX drought).
build build_crop_stress.py         "build_crop_stress.py (per-province agri stress)"
# per-branch MEASURED-corrected crop area (SPAM spatial x DOAE 2025 magnitude) — optional DOAE source.
build build_branch_cropland.py     "build_branch_cropland.py (per-branch measured crop area, optional DOAE src)"
# 4) MEASURED Overture occupation rollups — optional source; pass-quietly when absent.
build build_occupations.py         "build_occupations.py (branch occupation rollup, optional src)"
build build_amphoe_occupations.py  "build_amphoe_occupations.py (district occupation mix, optional src)"
# 5) composite expansion-opportunity score — reads amphoe + crop_stress + competitor census.
#    Must run AFTER build_amphoe + build_crop_stress so its inputs are current.
build build_opportunity_score.py   "build_opportunity_score.py (district opportunity composite)"
# 6) PR#2 enrichment layers — vehicle/EV collateral erosion + hydrology + labour. Deterministic +
#    network-free over committed source-data; each SKIP-passes when its upstream pull is absent (the
#    20MB dlt CSV mirror is not committed) or its output is not yet generated. branch_fuel.json is
#    intentionally NOT committed (coordinate-dependent; CI Python 3.11 generates it, like cropland).
build build_vehicle_flow.py            "build_vehicle_flow.py           (province vehicle-flow from dlt mirror, optional src)"
build build_vehicle_flow_transport.py  "build_vehicle_flow_transport.py (province transport-vehicle flow, optional src)"
build build_truck_flow.py              "build_truck_flow.py             (province truck-flow momentum, optional src)"
build build_ev_penetration.py          "build_ev_penetration.py         (province EV penetration, optional src)"
build build_ev_exposure.py             "build_ev_exposure.py            (province EV-exposure collateral risk)"
build build_brand_trends.py            "build_brand_trends.py           (vehicle-brand registration trends, optional src)"
build build_napprang.py                "build_napprang.py               (OAE off-season/dry-rice stress)"
build build_labour_context.py          "build_labour_context.py         (ILOSTAT labour repayment-capacity context)"
build build_branch_fuel.py             "build_branch_fuel.py            (per-branch measured fuel-station density, output not committed)"

# 7) tmli bridge — only if a builder exists in this tree (none today).
build ingest_tmli.py               "ingest_tmli.py       (tmli bridge, if present)"

# --- summary ----------------------------------------------------------------
printf '\n%s========================================%s\n' "$YLW" "$RST"
printf 'REFRESH SUMMARY: %s%d ok%s, %s%d failed%s, %s%d skipped%s\n' \
  "$GRN" "$pass" "$RST" "$RED" "$failc" "$RST" "$YLW" "$skipc" "$RST"
if [ "$failc" -eq 0 ]; then
  printf '%sAll builders reproduced byte-exact. Now run: bash tests/run.sh check%s\n' "$GRN" "$RST"
else
  printf '%s%d builder(s) failed — platform/data may have drifted; do NOT commit until clean.%s\n' "$RED" "$failc" "$RST"
fi
exit "$failc"
