#!/usr/bin/env bash
# AutoX credit-intelligence — single test entrypoint.
#
# Phases (run all by default; pass a phase name to run just one):
#   check    determinism gate: pipeline --check + node --check on app.js & every page's inline JS
#            + data integrity (validate_data.py over platform/data/*.json)
#   render   headless-render every page in tests/pages.manifest (map libs vendored in platform/vendor/)
#   health   per-page smoke: no uncaught errors, lib init, non-blank canvas, DOM hooks present
#   visual   compare fresh renders to tests/baseline/*.png within tolerance
#   overflow layout audit: does the text fit inside its box, at desktop AND phone width
#   baseline (re)generate tests/baseline/*.png from current pages (use when a change is intended)
#
# Usage:
#   tests/run.sh                 # check + render + health + visual + overflow  (the CI gate)
#   tests/run.sh check           # offline, no chromium needed beyond python
#   tests/run.sh baseline        # refresh committed baselines
#
# Network: NONE. deck.gl + Leaflet are committed under platform/vendor/, so the whole suite —
# determinism, render, health, visual — runs fully offline. NO data pulls, no npm registry.
set -u
TESTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$TESTS")"
PLATFORM="$REPO/platform"
PIPE="$REPO/pipeline"
LIB="$TESTS/lib"
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
skip(){ printf '%s[SKIP]%s %s\n' "$YLW" "$RST" "$1"; }
hdr(){ printf '\n%s== %s ==%s\n' "$YLW" "$1" "$RST"; }

manifest_rows(){ grep -vE '^\s*#' "$MANIFEST" | grep -vE '^\s*$'; }

# ---------------------------------------------------------------------------
# deck.gl + Leaflet are COMMITTED under platform/vendor/ (since 2026-08-01), so there is nothing to
# install and the whole suite is network-free. This asserts the bundles are present and — the part
# that matters — that no page has drifted back to a CDN <script>/<link>, which would make the render
# phase silently depend on the network again.
deps(){
  local missing=0
  for f in vendor/deck.gl-8.9.35.min.js vendor/leaflet/leaflet.js vendor/leaflet/leaflet.css; do
    [ -s "$PLATFORM/$f" ] || { bad "vendored bundle missing: platform/$f"; missing=1; }
  done
  [ "$missing" = 0 ] || return 1
  if grep -lE '<(script|link)[^>]*(unpkg\.com|cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com)' "$PLATFORM"/*.html >/dev/null 2>&1; then
    bad "a page loads a map library from a CDN again — vendor it into platform/vendor/ instead:"
    grep -lE '<(script|link)[^>]*(unpkg\.com|cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com)' "$PLATFORM"/*.html | sed 's/^/         /'
    return 1
  fi
  ok "map libraries vendored (platform/vendor/), no CDN <script>/<link> on any page"
}

# ---------------------------------------------------------------------------
phase_check(){
  hdr "determinism + syntax gate"
  ( cd "$PIPE" && python3 derive.py --check >/dev/null 2>&1 ) && ok "derive.py --check" || bad "derive.py --check (platform/data drifted from source-data)"
  ( cd "$PIPE" && python3 build_province.py --check >/dev/null 2>&1 ) && ok "build_province.py --check" || bad "build_province.py --check (province files drifted)"
  ( cd "$PIPE" && python3 build_regions.py --check >/dev/null 2>&1 ) && ok "build_regions.py --check" || bad "build_regions.py --check (regions.json drifted from provinces/*.json + competitors_census.json)"
  ( cd "$PIPE" && python3 build_amphoe.py --check >/dev/null 2>&1 ) && ok "build_amphoe.py --check" || bad "build_amphoe.py --check (amphoe.json drifted from source-data)"
  ( cd "$PIPE" && python3 build_amphoe_geo.py --check >/dev/null 2>&1 ) && ok "build_amphoe_geo.py --check" || bad "build_amphoe_geo.py --check (amphoe_geo.json drifted from th_amphoe.geojson)"
  ( cd "$PIPE" && python3 build_province_geo.py --check >/dev/null 2>&1 ) && ok "build_province_geo.py --check" || bad "build_province_geo.py --check (province_geo.json drifted from amphoe_geo.json/amphoe.json)"
  # NOTE: bake_catchment_heights.py --check was removed from the gate once rayong_catchment.json
  # became an Overture PULL artifact (pull_overture_buildings.py, ~124k buildings). Like branches.json
  # and the competitor census, a network-pulled file is not byte-reproducible offline, so it does not
  # belong in the determinism gate. The baker remains as a tool (and exports bldg_height, which the
  # Overture puller imports for estimated heights).
  ( cd "$PIPE" && python3 timeseries.py --check >/dev/null 2>&1 ) && ok "timeseries.py --check" || bad "timeseries.py --check (snapshot/deltas drifted from source-data)"
  ( cd "$PIPE" && python3 build_vintage_digest.py --check >/dev/null 2>&1 ) && ok "build_vintage_digest.py --check" || bad "build_vintage_digest.py --check (vintage_digest.json drifted from deltas.json/snapshots_index.json — run: python3 pipeline/build_vintage_digest.py)"
  ( cd "$PIPE" && python3 build_occupations.py --check >/dev/null 2>&1 ) && ok "build_occupations.py --check" || bad "build_occupations.py --check (branch_occupations.json drifted from overture_places.json)"
  ( cd "$PIPE" && python3 build_occupation_leads.py --check >/dev/null 2>&1 ) && ok "build_occupation_leads.py --check" || bad "build_occupation_leads.py --check (occupation_leads.json drifted from occupation_places_named.json)"
  ( cd "$PIPE" && python3 build_amphoe_occupations.py --check >/dev/null 2>&1 ) && ok "build_amphoe_occupations.py --check" || bad "build_amphoe_occupations.py --check (amphoe_occupations.json drifted from overture_places.json)"
  ( cd "$PIPE" && python3 build_occupation_risk.py --check >/dev/null 2>&1 ) && ok "build_occupation_risk.py --check" || bad "build_occupation_risk.py --check (occupation_risk.json drifted from branch_occupations.json/crop_stress.json)"
  ( cd "$PIPE" && python3 build_poi_relevance.py --check >/dev/null 2>&1 ) && ok "build_poi_relevance.py --check" || bad "build_poi_relevance.py --check (poi_relevance.json drifted from branch_occupations.json/branches.json k10)"
  ( cd "$PIPE" && python3 build_branch_workforce.py --check >/dev/null 2>&1 ) && ok "build_branch_workforce.py --check" || bad "build_branch_workforce.py --check (branch_workforce.json drifted from branch_occupations/branch_labor/crop_stress/spam2010)"
  ( cd "$PIPE" && python3 build_branch_agri.py --check >/dev/null 2>&1 ) && ok "build_branch_agri.py --check" || bad "build_branch_agri.py --check (branch_agri.json drifted from spam2010/crop_prices/branches_final)"
  # deterministic, network-free builders over COMMITTED inputs — added to close a silent-drift gap
  # (each --check reproduces its committed output byte-for-byte; all inputs are git-tracked source-data).
  ( cd "$PIPE" && python3 build_farmgate_prices.py --check >/dev/null 2>&1 ) && ok "build_farmgate_prices.py --check" || bad "build_farmgate_prices.py --check (source-data/farmgate_prices.json drifted from source-data/nabc_prices.json)"
  ( cd "$PIPE" && python3 build_crop_stress.py --check >/dev/null 2>&1 ) && ok "build_crop_stress.py --check" || bad "build_crop_stress.py --check (crop_stress.json drifted from crop_prov_area.json/commodity_board.json/farmgate_prices.json/branches_final.json)"
  ( cd "$PIPE" && python3 build_farm_income_impact.py --check >/dev/null 2>&1 ) && ok "build_farm_income_impact.py --check" || bad "build_farm_income_impact.py --check (farm_income_impact.json drifted from crop_prov_area.json/doae_planted_area.json/crop_margin.json/agri_income_by_province.json/farm_household.json/branches_final.json)"
  ( cd "$PIPE" && python3 check_commodity_board.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "check_commodity_board.py --check"
  elif [ "$rc" -eq 3 ]; then skip "check_commodity_board.py --check (commodities.json/commodities_protein.json absent — not drift)"
  else bad "check_commodity_board.py --check (commodity_board.json yoy/vintage drifted from its MEASURED Pink Sheet source commodities.json/commodities_protein.json — run: python3 pipeline/check_commodity_board.py)"
  fi
  ( cd "$PIPE" && python3 build_assist_radar_price.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_assist_radar_price.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_assist_radar_price.py --check (tape_real.json/crop_stress.json/farmgate_prices.json absent — not data drift)"
  else bad "build_assist_radar_price.py --check (assist_price_radar.json drifted from tape_real.json/crop_stress.json/farmgate_prices.json)"
  fi
  ( cd "$PIPE" && python3 build_assist_branch_radar.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_assist_branch_radar.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_assist_branch_radar.py --check (assist_price_radar.json/branch_agri.json/branches.json absent — not data drift)"
  else bad "build_assist_branch_radar.py --check (assist_branch_radar.json drifted from assist_price_radar.json/branch_agri.json/tape_geo_occ.json)"
  fi
  ( cd "$PIPE" && python3 build_rival_book_impact.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_rival_book_impact.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_rival_book_impact.py --check (rival_density.json/tape_geo_occ.json/branches.json absent — not data drift)"
  else bad "build_rival_book_impact.py --check (rival_book_impact.json drifted from rival_density.json/tape_geo_occ.json/branches.json)"
  fi
  ( cd "$PIPE" && python3 build_building_tiles.py --check >/dev/null 2>&1 ) && ok "build_building_tiles.py --check" || bad "build_building_tiles.py --check (tiles_config.json drifted from branches.json/competitors_census.json)"
  ( cd "$PIPE" && python3 build_sfi_credit.py --check >/dev/null 2>&1 ) && ok "build_sfi_credit.py --check" || bad "build_sfi_credit.py --check (sfi_credit.json drifted from source-data/fpo_sfi_npl.csv/fpo_sfi_credit.csv)"
  ( cd "$PIPE" && python3 build_peer_npl.py --check >/dev/null 2>&1 ) && ok "build_peer_npl.py --check" || bad "build_peer_npl.py --check (peer_npl.json drifted — the AutoX anchor from platform/data/tape_real.json or the cited peer constants; run: python3 pipeline/build_peer_npl.py)"
  ( cd "$PIPE" && python3 build_rayong.py --check >/dev/null 2>&1 ) && ok "build_rayong.py --check" || bad "build_rayong.py --check (rayong_province.json drifted from source-data branches_final/rayong_competitors/factories_by_district/vehicles_by_province/employment_by_province)"
  ( cd "$PIPE" && python3 build_branch_cropland.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_branch_cropland.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_branch_cropland.py --check (source-data/doae_planted_area.json absent — not data drift)"
  else bad "build_branch_cropland.py --check (branch_cropland.json drifted from spam2010/crop_landuse/doae_planted_area)"
  fi
  ( cd "$PIPE" && python3 build_province_cropland.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_province_cropland.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_province_cropland.py --check (source-data/doae_planted_area.json absent — not data drift)"
  else bad "build_province_cropland.py --check (province_cropland.json drifted from doae_planted_area)"
  fi
  ( cd "$PIPE" && python3 build_oae_agstats.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_oae_agstats.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_oae_agstats.py --check (source-data/staging/oae_agstats.json absent — not data drift)"
  else bad "build_oae_agstats.py --check (oae_agstats.json drifted from source-data/staging/oae_agstats.json)"
  fi
  ( cd "$PIPE" && python3 build_flood_hazard.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_flood_hazard.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_flood_hazard.py --check (source-data/gistda_flood_hazard.json or an input layer absent — not data drift)"
  else bad "build_flood_hazard.py --check (flood_hazard.json drifted from gistda_flood_hazard.json/amphoe.json/branches.json)"
  fi
  ( cd "$PIPE" && python3 build_pico_census.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_pico_census.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_pico_census.py --check (source-data/datagoth/fpo_pico.csv absent — Thai-IP pull, not committed)"
  else bad "build_pico_census.py --check (pico_census.json drifted from source-data/datagoth/fpo_pico.csv)"
  fi
  ( cd "$PIPE" && python3 build_pico_district.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_pico_district.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_pico_district.py --check (source-data/datagoth/fpo_pico.csv absent — Thai-IP pull, not committed)"
  else bad "build_pico_district.py --check (pico_district.json drifted from fpo_pico.csv/amphoe.json)"
  fi
  ( cd "$PIPE" && python3 build_pico_competitors.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_pico_competitors.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_pico_competitors.py --check (pico_census.json absent — upstream FPO pull, not committed)"
  else bad "build_pico_competitors.py --check (pico_competitors.json drifted from pico_census.json/branches.json)"
  fi
  ( cd "$PIPE" && python3 build_branch_pico.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_branch_pico.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_branch_pico.py --check (an input layer branches/amphoe/pico_district absent — not data drift)"
  else bad "build_branch_pico.py --check (branch_pico.json drifted from amphoe.json/pico_district.json — per-branch PICO district join)"
  fi
  ( cd "$PIPE" && python3 build_dbd_formation.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_dbd_formation.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_dbd_formation.py --check (source-data/datagoth/dbd_newco.csv absent — re-pullable pull_datagoth input, not committed)"
  else bad "build_dbd_formation.py --check (dbd_formation.json drifted from source-data/datagoth/dbd_newco.csv)"
  fi
  ( cd "$PIPE" && python3 build_baac_credit.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_baac_credit.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_baac_credit.py --check (owner-side xlsx absent, layer not generated, or pandas/openpyxl missing — not data drift)"
  else bad "build_baac_credit.py --check (baac_credit.json drifted from source-data/datagoth/baac_credit.xlsx)"
  fi
  ( cd "$PIPE" && python3 build_occupation_income_individual.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_occupation_income_individual.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_occupation_income_individual.py --check (ilostat_labour.json or household_income_by_province.json absent — not data drift)"
  else bad "build_occupation_income_individual.py --check (occupation_income_individual.json drifted from ilostat_labour.json/household_income_by_province.json)"
  fi
  ( cd "$PIPE" && python3 pull_oae_yield.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "pull_oae_yield.py --check"
  elif [ "$rc" -eq 3 ]; then skip "pull_oae_yield.py --check (committed oae_yield.json or gitignored raw scratch source-data/.oae_yield_raw/ absent — network-pulled input, not drift)"
  else bad "pull_oae_yield.py --check (oae_yield.json drifted from a fresh parse of the cached raw CSVs)"
  fi
  ( cd "$PIPE" && python3 pull_oae_farm_economics.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "pull_oae_farm_economics.py --check"
  elif [ "$rc" -eq 3 ]; then skip "pull_oae_farm_economics.py --check (committed oae_farm_economics.json or gitignored raw PDF source-data/.oae_farm_econ_raw/ absent — network-pulled input, not drift)"
  else bad "pull_oae_farm_economics.py --check (oae_farm_economics.json drifted from a fresh parse of the cached raw PDF)"
  fi
  ( cd "$PIPE" && python3 pull_nso_wages.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "pull_nso_wages.py --check"
  elif [ "$rc" -eq 3 ]; then skip "pull_nso_wages.py --check (committed nso_wages.json or gitignored raw scratch source-data/.nso_wage_raw/ absent — network-pulled input, not drift)"
  else bad "pull_nso_wages.py --check (nso_wages.json drifted from a fresh parse of the cached raw CSV)"
  fi
  ( cd "$PIPE" && python3 build_nso_wage_anchor.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_nso_wage_anchor.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_nso_wage_anchor.py --check (source-data/nso_wages.json absent — not data drift)"
  else bad "build_nso_wage_anchor.py --check (nso_wage_anchor.json drifted from source-data/nso_wages.json)"
  fi
  ( cd "$PIPE" && python3 pull_bot_credit.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "pull_bot_credit.py --check"
  elif [ "$rc" -eq 3 ]; then skip "pull_bot_credit.py --check (committed bot_credit.json or gitignored raw source-data/.bot_credit_raw/ absent — network-pulled input, not drift)"
  else bad "pull_bot_credit.py --check (bot_credit.json drifted from a fresh parse of the cached raw FSR2024.pdf/report984.html)"
  fi
  ( cd "$PIPE" && python3 build_credit_anchor.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_credit_anchor.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_credit_anchor.py --check (source-data/bot_credit.json absent — network-pulled input, not drift)"
  else bad "build_credit_anchor.py --check (credit_anchor.json drifted from source-data/bot_credit.json)"
  fi
  ( cd "$PIPE" && python3 build_crop_farmer_income.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_crop_farmer_income.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_crop_farmer_income.py --check (oae_yield.json/farmgate_prices/doae_planted_area/nabc_agri absent — not data drift)"
  else bad "build_crop_farmer_income.py --check (crop_farmer_income.json drifted from oae_yield.json/farmgate_prices.json/doae_planted_area.json/nabc_agri.json)"
  fi
  ( cd "$PIPE" && python3 build_vehicle_registry.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_vehicle_registry.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_vehicle_registry.py --check (source-data/datagoth/mot_vehicles.csv absent — re-pullable pull_datagoth input, not committed)"
  else bad "build_vehicle_registry.py --check (vehicle_registry.json drifted from source-data/datagoth/mot_vehicles.csv)"
  fi
  ( cd "$PIPE" && python3 build_vehicle_fleet.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_vehicle_fleet.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_vehicle_fleet.py --check (source-data/datagoth/mot_vehicles.csv absent — re-pullable pull_datagoth input, not committed)"
  else bad "build_vehicle_fleet.py --check (vehicle_fleet.json drifted from source-data/datagoth/mot_vehicles.csv)"
  fi
  ( cd "$PIPE" && python3 build_branch_vehicles.py --check >/dev/null 2>&1 ) && ok "build_branch_vehicles.py --check" || bad "build_branch_vehicles.py --check (branch_vehicles.json drifted from vehicles_by_province/branch_population)"
  ( cd "$PIPE" && python3 build_branch_recommendations.py --check >/dev/null 2>&1 ) && ok "build_branch_recommendations.py --check" || bad "build_branch_recommendations.py --check (branch_recommendations.json drifted from the per-branch layers)"
  ( cd "$PIPE" && python3 build_regional_outlook.py --check >/dev/null 2>&1 ) && ok "build_regional_outlook.py --check" || bad "build_regional_outlook.py --check (regional_outlook.json drifted from the per-branch/rec layers)"
  ( cd "$PIPE" && python3 build_branch_density.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_branch_density.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_branch_density.py --check (source-data/perimeter_counts.json absent — not data drift)"
  else bad "build_branch_density.py --check (branch_density.json drifted from source-data/perimeter_counts.json/branches.json)"
  fi
  ( cd "$PIPE" && python3 build_fuel_prices.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_fuel_prices.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_fuel_prices.py --check (source-data/fuel_prices.json absent — not data drift)"
  else bad "build_fuel_prices.py --check (fuel_prices.json drifted from source-data/fuel_prices.json)"
  fi
  ( cd "$PIPE" && python3 build_farmgate_platform.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_farmgate_platform.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_farmgate_platform.py --check (source-data/farmgate_prices.json absent — not data drift)"
  else bad "build_farmgate_platform.py --check (platform/data/farmgate_prices.json drifted from source-data/farmgate_prices.json)"
  fi
  ( cd "$PIPE" && python3 build_commodity_history.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_commodity_history.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_commodity_history.py --check (source-data/commodity_history.json absent — owner-side Pink Sheet parse, not data drift)"
  else bad "build_commodity_history.py --check (commodity_history.json drifted from source-data/commodity_history.json — run: python3 pipeline/build_commodity_history.py)"
  fi
  # Accumulated history for the feeds whose source only publishes "now". Gated BEFORE the live
  # board, which reads this layer to decide which feeds have a drawable series.
  ( cd "$PIPE" && python3 build_feed_history.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_feed_history.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_feed_history.py --check (source-data/feed_history.json absent — run: python3 pipeline/append_history.py --from-git)"
  else bad "build_feed_history.py --check (feed_history.json drifted from the accumulator — run: python3 pipeline/build_feed_history.py)"
  fi
  # The live board reads every other layer's meta stamp, so it drifts whenever an upstream feed is
  # re-pulled — which is exactly what it is for, and exactly why it must be gated: a stale
  # live_board.json would report a fresh feed as old (or worse, an old one as fresh).
  ( cd "$PIPE" && python3 build_live_board.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_live_board.py --check"
  else bad "build_live_board.py --check (live_board.json is behind its upstream feeds' stamps — run: python3 pipeline/build_live_board.py)"
  fi
  # --- PR#2 enrichment layers (vehicle/EV collateral erosion + hydrology + labour) ---------------
  # All deterministic + network-free over committed source-data. Each SKIPs (exit 3) when its upstream
  # pull is absent (dlt CSV mirror is NOT committed — 20MB) or its output is not yet generated — never a
  # data-drift FAIL. branch_fuel.json is intentionally NOT committed (coordinate-dependent; CI Python
  # 3.11 generates it, mirroring branch_cropland/branch_density), so it SKIPs here too.
  ( cd "$PIPE" && python3 build_vehicle_flow.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_vehicle_flow.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_vehicle_flow.py --check (dlt mirror absent/<12mo — not data drift)"
  else bad "build_vehicle_flow.py --check (vehicle_flow_by_province.json drifted from the dlt mirror)"
  fi
  ( cd "$PIPE" && python3 build_truck_flow.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_truck_flow.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_truck_flow.py --check (dlt mirror absent/<24mo or output not generated — not data drift)"
  else bad "build_truck_flow.py --check (truck_flow.json drifted from the dlt mirror)"
  fi
  # collateral_flow projects the COMMITTED vehicle_flow_by_province.json (not the gitignored raw), so
  # unlike its siblings above it byte-reproduces here rather than SKIPping.
  ( cd "$PIPE" && python3 build_collateral_flow.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_collateral_flow.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_collateral_flow.py --check (vehicle_flow_by_province.json absent — not data drift)"
  else bad "build_collateral_flow.py --check (collateral_flow.json drifted from vehicle_flow_by_province.json)"
  fi
  ( cd "$PIPE" && python3 build_ev_penetration.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_ev_penetration.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_ev_penetration.py --check (dlt mirror absent or output not generated — not data drift)"
  else bad "build_ev_penetration.py --check (ev_penetration.json drifted from the dlt mirror)"
  fi
  ( cd "$PIPE" && python3 build_ev_exposure.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_ev_exposure.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_ev_exposure.py --check (scurve_by_province.json absent or output not generated — not data drift)"
  else bad "build_ev_exposure.py --check (ev_exposure.json drifted from source-data/scurve_by_province.json)"
  fi
  ( cd "$PIPE" && python3 build_vehicle_collateral.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_vehicle_collateral.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_vehicle_collateral.py --check (dlt mirror dataset_1_1_04 absent or output not generated — not data drift)"
  else bad "build_vehicle_collateral.py --check (vehicle_collateral.json drifted from the dlt mirror / brand_trends.json)"
  fi
  ( cd "$PIPE" && python3 build_brand_trends.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_brand_trends.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_brand_trends.py --check (dlt CSVs absent or output not generated — not data drift)"
  else bad "build_brand_trends.py --check (brand_trends.json drifted from the dlt CSVs)"
  fi
  ( cd "$PIPE" && python3 build_vehicle_models.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_vehicle_models.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_vehicle_models.py --check (dlt model-grain mirror absent or output not generated — not data drift)"
  else bad "build_vehicle_models.py --check (vehicle_models.json drifted from the dlt model-grain mirror)"
  fi
  # vehicle_mix / used_vehicle_value project COMMITTED source-data (vehicle_mix_province.json, bot_uvpi.json),
  # so both byte-reproduce here — they were previously outside the gate, leaving app-consumed committed
  # layers unprotected against silent drift. vehicle_brands reads the OWNER-SIDE gitignored dlt mirror, so it
  # SKIPs in CI like its dlt-fed siblings above.
  ( cd "$PIPE" && python3 build_vehicle_mix.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_vehicle_mix.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_vehicle_mix.py --check (source-data/vehicle_mix_province.json absent — not data drift)"
  else bad "build_vehicle_mix.py --check (vehicle_mix.json drifted from source-data/vehicle_mix_province.json)"
  fi
  ( cd "$PIPE" && python3 build_used_vehicle_value.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_used_vehicle_value.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_used_vehicle_value.py --check (source-data/bot_uvpi.json absent — BOT pull, not data drift)"
  else bad "build_used_vehicle_value.py --check (used_vehicle_value.json drifted from source-data/bot_uvpi.json)"
  fi
  ( cd "$PIPE" && python3 build_vehicle_brands.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_vehicle_brands.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_vehicle_brands.py --check (source-data/dlt/raw mirror absent — owner-side dlt pull, not committed)"
  else bad "build_vehicle_brands.py --check (vehicle_brands.json drifted from the dlt raw mirror)"
  fi
  ( cd "$PIPE" && python3 build_napprang.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_napprang.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_napprang.py --check (oae_napprang.json absent or output not generated — not data drift)"
  else bad "build_napprang.py --check (napprang.json drifted from source-data/oae_napprang.json)"
  fi
  ( cd "$PIPE" && python3 build_labour_context.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_labour_context.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_labour_context.py --check (ilostat_labour.json absent or output not generated — not data drift)"
  else bad "build_labour_context.py --check (labour_context.json drifted from source-data/ilostat_labour.json)"
  fi
  ( cd "$PIPE" && python3 build_branch_fuel.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_branch_fuel.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_branch_fuel.py --check (fuel_stations.json absent or branch_fuel.json not generated — not data drift)"
  else bad "build_branch_fuel.py --check (branch_fuel.json drifted from source-data/fuel_stations.json/branches.json)"
  fi
  ( cd "$PIPE" && python3 build_branch_risk.py --check >/dev/null 2>&1 ) && ok "build_branch_risk.py --check" || bad "build_branch_risk.py --check (branch_risk.json drifted from household_risk/crop_stress/occupation_risk/branches.json)"
  ( cd "$PIPE" && python3 build_opportunity_score.py --check >/dev/null 2>&1 ) && ok "build_opportunity_score.py --check" || bad "build_opportunity_score.py --check (opportunity_score.json drifted from amphoe.json/crop_stress.json/competitors)"
  ( cd "$PIPE" && python3 build_competitor_coverage.py --check >/dev/null 2>&1 ) && ok "build_competitor_coverage.py --check" || bad "build_competitor_coverage.py --check (competitor_coverage.json drifted from the competitor census)"
  ( cd "$PIPE" && python3 check_peer_constants.py --check >/dev/null 2>&1 ) && ok "check_peer_constants.py --check" || bad "check_peer_constants.py --check (peer scoreboard constants in build_peer_npl.py/build_competitor_coverage.py drifted from docs/RESEARCH_DIGEST.md §B — run: python3 pipeline/check_peer_constants.py)"
  ( cd "$PIPE" && python3 check_autox_targets.py --check >/dev/null 2>&1 ) && ok "check_autox_targets.py --check" || bad "check_autox_targets.py --check (AutoX ROE target in build_peer_scoreboard.py drifted from the CLAUDE.md brief — run: python3 pipeline/check_autox_targets.py)"
  ( cd "$PIPE" && python3 build_competitor_census.py --check >/dev/null 2>&1 ) && ok "build_competitor_census.py --check" || bad "build_competitor_census.py --check (competitors_census.json drifted from official-locator/national/overture censuses)"
  ( cd "$PIPE" && python3 build_rival_density.py --check >/dev/null 2>&1 ) && ok "build_rival_density.py --check" || bad "build_rival_density.py --check (rival_density.json drifted from amphoe.json/competitors_census.json/th_amphoe.geojson)"
  ( cd "$PIPE" && python3 build_peer_scoreboard.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_peer_scoreboard.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_peer_scoreboard.py --check (source-data/set_peers.json absent — SET pull, not data drift)"
  else bad "build_peer_scoreboard.py --check (peer_scoreboard.json drifted from source-data/set_peers.json)"
  fi
  ( cd "$PIPE" && python3 build_rival_reputation.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_rival_reputation.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_rival_reputation.py --check (source-data/competitor_ratings.json absent — Google Places pull, not data drift)"
  else bad "build_rival_reputation.py --check (rival_reputation.json drifted from source-data/competitor_ratings.json)"
  fi
  ( cd "$PIPE" && python3 build_rival_pulse.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_rival_pulse.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_rival_pulse.py --check (rival_promos/app_reviews sources absent — network pulls, not data drift)"
  else bad "build_rival_pulse.py --check (rival_pulse.json drifted from source-data/rival_promos.json + app_reviews.json)"
  fi
  ( cd "$PIPE" && python3 build_rival_watch.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_rival_watch.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_rival_watch.py --check (rival_pulse/rival_ads/search_demand absent — upstream pulls, not data drift)"
  else bad "build_rival_watch.py --check (rival_watch.json drifted from rival_pulse.json + rival_ads.json + search_demand.json)"
  fi
  ( cd "$PIPE" && python3 build_google_ads.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_google_ads.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_google_ads.py --check (source-data/google_ads_raw.json absent — network pull, not data drift)"
  else bad "build_google_ads.py --check (rival_ads.json drifted from source-data/google_ads_raw.json — run: python3 pipeline/build_google_ads.py)"
  fi
  ( cd "$PIPE" && python3 build_social_themes.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_social_themes.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_social_themes.py --check (youtube_comments/app_reviews/apple_reviews/pantip_threads absent — network pulls, not data drift)"
  else bad "build_social_themes.py --check (social_themes.json drifted from the demand+supply sources — run: python3 pipeline/build_social_themes.py)"
  fi
  ( cd "$PIPE" && python3 build_pantip_panel.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_pantip_panel.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_pantip_panel.py --check (source-data/pantip_threads.json absent — network pull, not data drift)"
  else bad "build_pantip_panel.py --check (pantip_panel.json drifted from source-data/pantip_threads.json — run: python3 pipeline/build_pantip_panel.py)"
  fi
  ( cd "$PIPE" && python3 build_rival_youtube.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_rival_youtube.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_rival_youtube.py --check (source-data/rival_youtube_raw.json absent — network pull, not data drift)"
  else bad "build_rival_youtube.py --check (rival_youtube.json drifted from source-data/rival_youtube_raw.json — run: python3 pipeline/build_rival_youtube.py)"
  fi
  ( cd "$PIPE" && python3 build_rival_universe.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_rival_universe.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_rival_universe.py --check (source-data/rival_universe.json absent)"
  else bad "build_rival_universe.py --check (rival_universe.json drifted from source-data/rival_universe.json + app_reviews.json — run: python3 pipeline/build_rival_universe.py)"
  fi
  # Deterministic, network-free builders over COMMITTED inputs — source-data/ (now INCLUDING the
  # committed source-data/staging/ aggregates, 21 tracked files) and, for the *_book layers, the
  # committed platform/data layers they roll up. Each carries --check and byte-reproduces here (rc 0);
  # rc 3 = an optional / owner-pulled input absent (SKIP, honest — not drift); any other code = the
  # committed output drifted from its named source (FAIL — regenerate it). Driven from an explicit
  # name|source table (not a bare-name loop) so each FAIL message points at the ACTUAL source rather
  # than blanket-blaming source-data/staging/, and so a grep for "build_X.py --check" over this file
  # finds every gated builder below (a bare loop hid these 20 from gate-coverage audits):
  #   build_crop_margin.py --check   build_drought_district.py --check   build_province_lfs.py --check
  #   build_region_debt.py --check   build_amphoe_crops.py --check       build_tape_layers.py --check
  #   build_collateral_census.py --check
  #   build_impact_cards.py --check  build_income_impact.py --check      build_scenarios.py --check
  #   build_commodities.py --check   build_product_segments.py --check   ingest_ocsb_cane.py --check
  #   build_thai_price_history.py --check  build_farm_household.py --check  build_debt_source.py --check
  #   build_crop_mix.py --check      build_farm_book.py --check           build_collateral_book.py --check
  #   build_macro_book.py --check
  # NOTE: this is a `while read <<'HEREDOC'` (not a pipe), so it runs in the current shell and ok/bad
  # keep incrementing pass/failc — same counter semantics as the bare `for` loop it replaced.
  while IFS='|' read -r ing src; do
    [ -z "$ing" ] && continue
    ( cd "$PIPE" && python3 "$ing.py" --check >/dev/null 2>&1 ); rc=$?
    if [ "$rc" -eq 0 ]; then ok "$ing.py --check"
    elif [ "$rc" -eq 3 ]; then skip "$ing.py --check (an input absent — optional/owner-pulled source, not data drift)"
    else bad "$ing.py --check ($ing output drifted from $src — run: python3 pipeline/$ing.py)"
    fi
  done <<'INGESTS'
build_crop_margin|source-data/farmgate_prices.json + staging/oae_crop_costs.json
build_drought_district|source-data/staging/drought_district.json
build_province_lfs|source-data/staging/nso_lfs.json
build_region_debt|source-data/staging/bot_hhdebt.json
build_amphoe_crops|source-data/staging/amphoe_crops_*.json + doae_amphoe_crops.json
build_tape_layers|source-data/staging/real_tape_aggregates.json
build_collateral_census|source-data/staging/collateral_census_agg.json
build_impact_cards|source-data/branches_final.json + commodity_board.json + employment_by_province.json
build_income_impact|source-data/commodity_board.json + crop_prov_area.json + energy_prices.json
build_scenarios|source-data/commodity_board.json
build_commodities|source-data/commodity_board.json + crop_prov_area.json + doae_fruit_area.json
build_product_segments|source-data/staging/ tape aggregates
ingest_ocsb_cane|source-data/ocsb_cane.json + ocsb_canearea.csv
build_thai_price_history|source-data/nabc_history.json + ocsb_cane.json
build_farm_household|source-data/oae_household/*.csv
build_debt_source|source-data/nso_debt_by_source.json
build_crop_mix|source-data/crop_prov_area.json + ocsb_cane.json
build_farm_book|platform/data book layers (tape_geo_occ/crop_mix/crop_stress/income_impact/crop_margin/napprang)
build_collateral_book|source-data/staging/real_tape_aggregates.json
build_macro_book|platform/data book layers (collateral_book/province_lfs/dbd_formation/region_debt/sfi_credit)
INGESTS
  # macro_indicators projects COMMITTED Thai-official series (nesdc_gdp / tpso_cpi / bot_current_account /
  # bot_tourist_arrivals), so it byte-reproduces here; it was outside the gate, leaving the Macro-backdrop
  # layer (macro_indicators.json) unprotected against silent drift.
  ( cd "$PIPE" && python3 build_macro_indicators.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_macro_indicators.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_macro_indicators.py --check (a bot/nesdc/tpso source-data series absent — network pull, not data drift)"
  else bad "build_macro_indicators.py --check (macro_indicators.json drifted from nesdc_gdp/tpso_cpi/bot_current_account/bot_tourist_arrivals)"
  fi
  ( cd "$PIPE" && python3 build_rival_threat.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_rival_threat.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_rival_threat.py --check (rival_reputation.json absent — Google Places pull, not data drift)"
  else bad "build_rival_threat.py --check (rival_threat.json drifted from competitor_coverage.json/rival_reputation.json — run: python3 pipeline/build_rival_threat.py)"
  fi
  ( cd "$PIPE" && python3 build_rival_threat_region.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_rival_threat_region.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_rival_threat_region.py --check (rival_reputation.json absent — Google Places pull, not data drift)"
  else bad "build_rival_threat_region.py --check (rival_threat_region.json drifted from peer_province.json/rival_reputation.json — run: python3 pipeline/build_rival_threat_region.py)"
  fi
  ( cd "$PIPE" && python3 build_peer_province.py --check >/dev/null 2>&1 ) && ok "build_peer_province.py --check" || bad "build_peer_province.py --check (peer_province.json drifted from rival_density.json — run: python3 pipeline/build_peer_province.py)"
  ( cd "$PIPE" && python3 build_province_pressure.py --check >/dev/null 2>&1 ) && ok "build_province_pressure.py --check" || bad "build_province_pressure.py --check (province_pressure.json drifted from province_stress_index.json/peer_province.json — run: python3 pipeline/build_province_pressure.py)"
  ( cd "$PIPE" && python3 build_rival_pressure.py --check >/dev/null 2>&1 ) && ok "build_rival_pressure.py --check" || bad "build_rival_pressure.py --check (rival_pressure.json drifted from branches.json/competitors_census.json)"
  ( cd "$PIPE" && python3 ingest_heng.py --check >/dev/null 2>&1 ) && ok "ingest_heng.py --check" || bad "ingest_heng.py --check (Heng official-locator merge drifted from source-data/heng_branches.json — run: python3 pipeline/ingest_heng.py)"
  ( cd "$PIPE" && python3 build_cluster_brief.py --check >/dev/null 2>&1 ) && ok "build_cluster_brief.py --check" || bad "build_cluster_brief.py --check (cluster_brief.json drifted from branch_occupations/branches/meta board/crop_stress)"
  ( cd "$PIPE" && python3 build_exit_whitespace.py --check >/dev/null 2>&1 ) && ok "build_exit_whitespace.py --check" || bad "build_exit_whitespace.py --check (exit_whitespace.json drifted from amphoe.json/competitors)"
  ( cd "$PIPE" && python3 build_expansion_plan.py --check >/dev/null 2>&1 ) && ok "build_expansion_plan.py --check" || bad "build_expansion_plan.py --check (expansion_plan.json drifted from amphoe.json/branches.json)"
  ( cd "$PIPE" && python3 build_search_demand.py --check >/dev/null 2>&1 ) && ok "build_search_demand.py --check" || bad "build_search_demand.py --check (search_demand.json drifted from source-data/google_trends.json/provinces index)"
  ( cd "$PIPE" && python3 build_branch_peers.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_branch_peers.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_branch_peers.py --check (numpy not installed — dependency missing, not data drift; pip install --break-system-packages numpy)"
  else bad "build_branch_peers.py --check (branch_peers.json drifted from branches.json/branch_risk.json/household_risk)"
  fi
  ( cd "$PIPE" && python3 build_branch_leads.py --check >/dev/null 2>&1 ) && ok "build_branch_leads.py --check" || bad "build_branch_leads.py --check (branch_leads.json drifted from branch_occupations/branches/branch_labor/occupation_risk/crop_stress)"
  ( cd "$PIPE" && python3 build_macro_exposure.py --check >/dev/null 2>&1 ) && ok "build_macro_exposure.py --check" || bad "build_macro_exposure.py --check (macro_exposure.json drifted from branch_occupations/commodity_board/crop_stress/household_risk)"
  ( cd "$PIPE" && python3 build_macro_sensitivity.py --check >/dev/null 2>&1 ) && ok "build_macro_sensitivity.py --check" || bad "build_macro_sensitivity.py --check (macro_sensitivity.json drifted from branches.json/crop_stress.json/commodity_board.json)"
  ( cd "$PIPE" && python3 build_lead_sites.py --check >/dev/null 2>&1 ) && ok "build_lead_sites.py --check" || bad "build_lead_sites.py --check (lead_sites.json drifted from osm_layers.json/branches.json/branch_leads.json)"
  ( cd "$PIPE" && python3 build_catchment_poi.py --check >/dev/null 2>&1 ) && ok "build_catchment_poi.py --check" || bad "build_catchment_poi.py --check (catchment_poi.json drifted from osm_layers.json)"
  ( cd "$PIPE" && python3 slim_catchment.py --check >/dev/null 2>&1 ) && ok "slim_catchment.py --check" || bad "slim_catchment.py --check (a committed *_catchment.json is not the slim canonical form — run: python3 pipeline/slim_catchment.py)"
  scp_out=$( cd "$PIPE" && python3 build_scene_places.py --check 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_scene_places.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_scene_places.py --check ($(echo "$scp_out" | tail -1))"
  else bad "build_scene_places.py --check (a <city>_places.json drifted — run: python3 pipeline/build_scene_places.py)"; fi
  np_out=$( cd "$PIPE" && python3 build_national_places.py --check 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_national_places.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_national_places.py --check ($(echo "$np_out" | tail -1))"
  else bad "build_national_places.py --check (national_places.json drifted — run: python3 pipeline/build_national_places.py)"; fi
  bp_out=$( cd "$PIPE" && python3 build_branch_population.py --check 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_branch_population.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_branch_population.py --check ($(echo "$bp_out" | tail -1))"
  else bad "build_branch_population.py --check (branch_population.json drifted from th_amphoe.geojson/amphoe.json/master)"
  fi
  cl_out=$( cd "$PIPE" && python3 build_crop_landuse.py --check 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_crop_landuse.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_crop_landuse.py --check ($(echo "$cl_out" | tail -1))"
  else bad "build_crop_landuse.py --check (crop_landuse.json drifted from spam2010_th_cropgrid.json/th_amphoe.geojson/amphoe.json)"
  fi
  ( cd "$PIPE" && python3 build_contested_pop.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_contested_pop.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_contested_pop.py --check (rasterio/WorldPop raster missing — dependency gap, not data drift; pip install --break-system-packages rasterio)"
  else bad "build_contested_pop.py --check (contested_pop.json drifted from branches.json/competitors_census.json/worldpop raster)"
  fi
  ( cd "$PIPE" && python3 ingest_tmli.py --check >/dev/null 2>&1 ) && ok "ingest_tmli.py --check" || bad "ingest_tmli.py --check (TMLI measured province layers drifted from source-data/tmli/)"
  ( cd "$PIPE" && python3 build_household_risk.py --check >/dev/null 2>&1 ) && ok "build_household_risk.py --check" || bad "build_household_risk.py --check (household_risk_by_province.json drifted from source-data NSO SES layers)"
  ( cd "$PIPE" && python3 build_occupation_income.py --check >/dev/null 2>&1 ) && ok "build_occupation_income.py --check" || bad "build_occupation_income.py --check (occupation_income.json drifted from source-data/household_income_by_province.json)"
  ( cd "$PIPE" && python3 build_factory_income.py --check >/dev/null 2>&1 ) && ok "build_factory_income.py --check" || bad "build_factory_income.py --check (factory_income_by_province.json drifted from source-data/household_income_by_province.json)"
  ( cd "$PIPE" && python3 build_agri_income.py --check >/dev/null 2>&1 ) && ok "build_agri_income.py --check" || bad "build_agri_income.py --check (agri_income_by_province.json drifted from source-data/household_income_by_province.json)"
  ( cd "$PIPE" && python3 build_sme_income.py --check >/dev/null 2>&1 ) && ok "build_sme_income.py --check" || bad "build_sme_income.py --check (sme_income_by_province.json drifted from source-data/household_income_by_province.json)"
  ( cd "$PIPE" && python3 build_province_stress.py --check >/dev/null 2>&1 ) && ok "build_province_stress.py --check" || bad "build_province_stress.py --check (province_stress_index.json drifted from household_risk_by_province.json/unemployment_by_province.json)"
  ( cd "$PIPE" && python3 build_province_risk.py --check >/dev/null 2>&1 ) && ok "build_province_risk.py --check" || bad "build_province_risk.py --check (province_risk.json drifted from branch_risk.json/branches.json)"
  ( cd "$PIPE" && python3 build_segment_exposure.py --check >/dev/null 2>&1 ) && ok "build_segment_exposure.py --check" || bad "build_segment_exposure.py --check (segment_exposure.json drifted from branches.json)"
  ( cd "$PIPE" && python3 build_collateral_outlook.py --check >/dev/null 2>&1 ) && ok "build_collateral_outlook.py --check" || bad "build_collateral_outlook.py --check (collateral_outlook.json drifted from commodity_board/vehicles_by_province/branches.json)"
  ( cd "$PIPE" && python3 build_branch_labor.py --check >/dev/null 2>&1 ) && ok "build_branch_labor.py --check" || bad "build_branch_labor.py --check (branch_labor.json drifted from branch_occupations/amphoe/NSO province layers)"
  ( cd "$PIPE" && python3 build_decision_queue.py --check >/dev/null 2>&1 ) && ok "build_decision_queue.py --check" || bad "build_decision_queue.py --check (decision_queue.json drifted from rival_pressure/branch_peers/macro_sensitivity/crop_stress/opportunity_score/exit_whitespace)"
  # build_provenance runs LAST — it censuses every other layer's meta + byte size, so it must
  # reproduce against the just-verified committed data tree.
  ( cd "$PIPE" && python3 build_provenance.py --check >/dev/null 2>&1 ) && ok "build_provenance.py --check" || bad "build_provenance.py --check (provenance.json drifted from platform/data/*.json — run: python3 pipeline/build_provenance.py)"

  # The data-pull workflows re-derive their fan-out by running rederive_drift.py, which discovers
  # what to rebuild by PARSING the --check invocations in THIS file. That makes run.sh's syntax load-
  # bearing for those jobs: reshape the lines above and the parser could quietly match nothing, the
  # pulls would stop re-deriving, and every data PR would go back to arriving red — with no error
  # anywhere to say why. --selftest fails if the parse drops below its floor, so that breaks here
  # instead, next to the change that caused it.
  ( cd "$PIPE" && python3 rederive_drift.py --selftest >/dev/null 2>&1 ) && ok "rederive_drift.py --selftest" || bad "rederive_drift.py --selftest (it can no longer read the --check set out of tests/run.sh — the data-pull workflows would silently stop re-deriving; fix RE_EXPLICIT/RE_HEREDOC in pipeline/rederive_drift.py)"

  # resolve_derived_conflicts.sh auto-resolves merge conflicts and the committee/auto-merge jobs call
  # it before pushing STRAIGHT TO MASTER, so its two abort paths are the only thing between an
  # unattended job and a wrongly-resolved conflict in source-data/ or in code. Fixture-based, seconds.
  bash "$REPO/tests/test_resolve_derived_conflicts.sh" >/dev/null 2>&1 && ok "resolve_derived_conflicts.sh (41 fixture cases)" || bad "resolve_derived_conflicts.sh fixture tests (run: bash tests/test_resolve_derived_conflicts.sh)"

  # The union-mergers decide what happens to data that CANNOT BE RE-PULLED — feed_history holds the
  # only copy of yesterday's gauge reading, swarm_runs the only record of a run. Each ships its own
  # fixtures; neither was actually being run by this gate, so a regression in either would have
  # surfaced as silently deleted telemetry during an unattended merge. Seconds, offline.
  ( cd "$PIPE" && python3 merge_feed_history.py --selftest >/dev/null 2>&1 ) \
    && ok "merge_feed_history.py --selftest (accumulator union + later-pull tie-break)" \
    || bad "merge_feed_history.py --selftest (run: python3 pipeline/merge_feed_history.py --selftest)"
  ( cd "$PIPE" && python3 merge_swarm_runs.py --selftest >/dev/null 2>&1 ) \
    && ok "merge_swarm_runs.py --selftest (run-log union)" \
    || bad "merge_swarm_runs.py --selftest (run: python3 pipeline/merge_swarm_runs.py --selftest)"

  # pr-automerge.yml merges generated PRs to master unattended and master auto-deploys, so its
  # eligibility rule and its "did the gate really pass on THIS head" rule are the last thing
  # between a bot commit and the live site. A workflow cannot be tested by running it, so this
  # extracts both embedded Python blocks from the YAML and exercises them. Fixture-based, seconds.
  python3 "$REPO/tests/test_pr_automerge_logic.py" >/dev/null 2>&1 && ok "pr-automerge.yml logic (24 fixture cases)" || bad "pr-automerge.yml fixture tests (run: python3 tests/test_pr_automerge_logic.py)"

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

  # nav consistency + route reachability. The main nav is hand-copied into six pages with no build
  # step to keep them honest, and index.html builds one section per hash route with nothing
  # asserting those routes are linked. Both failure modes had already shipped silently: status.html
  # sat on pre-five-pillar labels for a week, and #branches/#provinces/#market rendered perfectly
  # while being reachable only by typed URL. Verified to FAIL on nav drift, a dropped Explore entry,
  # a reordered pillar, and a newly-orphaned route.
  if python3 "$TESTS/nav_consistency.py"; then
    ok "nav_consistency.py (one nav across 6 pages, no orphan routes)"
  else
    bad "nav_consistency.py (nav drift or an unreachable route — see report above)"
  fi

  # orphan-DATA-LAYER gate: the sibling of the orphan-route check above. Asserts every committed
  # platform/data/*.json leaf is actually consumed — fetched by a page OR read by a downstream
  # builder — not just deterministically reproduced. Catches the branch_density failure: a layer
  # that byte-reproduces perfectly yet nothing reads, aging gate-green in silence for months.
  if python3 "$TESTS/orphan_layers.py"; then
    ok "orphan_layers.py (every committed data layer is consumed by a page or a builder)"
  else
    bad "orphan_layers.py (a committed data layer has no consumer — see report above)"
  fi

  # data-integrity sub-check: assert platform/data/*.json is internally sane (offline, stdlib).
  # The determinism/syntax checks above don't look INSIDE the data; this does. Its own per-check
  # report is shown so a failure points at the exact integrity violation (an IPO-readiness gate).
  if python3 "$TESTS/validate_data.py"; then
    ok "validate_data.py (platform/data integrity)"
  else
    bad "validate_data.py (platform/data integrity — see report above)"
  fi

  # deploy-probe self-test: the SAME code path the nightly live site-health check runs (check_site_health.py),
  # but pointed at the local committed tree (--local platform, LocalFetcher = filesystem only, pure stdlib,
  # NO network). It asserts every deploy probe validator (_shape_*) still ACCEPTS its real committed payload,
  # every critical page carries the AutoX wordmark, and no probed data file is missing/oversized. Added
  # because the ~40 probes are hand-authored by the intelligence loop yet had NO repo-gate guard: a future
  # edit that broke a validator against the real data would ship silently and only surface on the nightly
  # LIVE run (a filed GitHub issue), not here. All probed data files + the probed pages are git-tracked,
  # so this reproduces on a clean checkout; it FAILs only on a genuine probe/payload regression.
  hc_out="$( python3 "$PIPE/check_site_health.py" --local "$PLATFORM" 2>&1 )"; rc=$?
  if [ "$rc" -eq 0 ]; then
    ok "check_site_health.py --local (deploy probe validators accept the committed payloads)"
  else
    printf '%s\n' "$hc_out" | grep -E '\[FAIL\]|ERROR|Traceback' | head -12 | sed 's/^/      /'
    bad "check_site_health.py --local (a deploy probe validator rejects its committed payload — see above)"
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

# Layout audit — the one class of defect the other four phases structurally cannot see. `check`
# reads bytes, `render` only asks whether a page painted, `visual` diffs against a baseline that a
# new section changes legitimately. None of them asks whether the text fits inside its box. This
# does, at desktop AND phone width. Added after PR #259 shipped a Risk-tab panel that pushed a
# 390px phone to 494px of horizontal page scroll and every gate stayed green.
phase_overflow(){
  hdr "visual overflow audit (bleed / clip / page-x / collide)"
  if ! command -v node >/dev/null 2>&1; then skip "overflow (node not installed)"; return 0; fi
  local port=8791
  python3 -m http.server "$port" --directory "$PLATFORM" >/dev/null 2>&1 &
  local srv=$!
  local i=0
  while [ $i -lt 40 ]; do
    curl -s -o /dev/null "http://localhost:$port/" 2>/dev/null && break
    i=$((i+1)); sleep 0.25
  done
  local out rc
  out="$(node "$TESTS/visual_overflow.js" "http://localhost:$port" 2>&1)"; rc=$?
  kill "$srv" 2>/dev/null; wait "$srv" 2>/dev/null
  printf '%s\n' "$out"
  # exit 2 is "could not run" (playwright missing) — an environment gap, not a layout defect.
  if [ "$rc" -eq 0 ]; then ok "visual overflow (no findings)"
  elif [ "$rc" -eq 2 ]; then skip "visual overflow (could not run)"
  else bad "visual overflow (findings above)"; fi
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
  overflow) phase_overflow ;;
  baseline) phase_baseline ;;
  all)      phase_check; phase_render; phase_health; phase_visual; phase_overflow ;;
  *) echo "unknown phase: $PHASE (use: check|render|health|visual|overflow|baseline|all)"; exit 2 ;;
esac

printf '\n%s========================================%s\n' "$YLW" "$RST"
printf 'RESULT: %s%d passed%s, %s%d failed%s\n' "$GRN" "$pass" "$RST" "$RED" "$failc" "$RST"
[ "$failc" -eq 0 ]
