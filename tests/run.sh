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
skip(){ printf '%s[SKIP]%s %s\n' "$YLW" "$RST" "$1"; }
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
  ( cd "$PIPE" && python3 build_branch_cropland.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_branch_cropland.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_branch_cropland.py --check (source-data/doae_planted_area.json absent — not data drift)"
  else bad "build_branch_cropland.py --check (branch_cropland.json drifted from spam2010/crop_landuse/doae_planted_area)"
  fi
  ( cd "$PIPE" && python3 build_pico_census.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_pico_census.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_pico_census.py --check (source-data/datagoth/fpo_pico.csv absent — Thai-IP pull, not committed)"
  else bad "build_pico_census.py --check (pico_census.json drifted from source-data/datagoth/fpo_pico.csv)"
  fi
  ( cd "$PIPE" && python3 build_dbd_formation.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_dbd_formation.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_dbd_formation.py --check (source-data/datagoth/dbd_newco.csv absent — re-pullable pull_datagoth input, not committed)"
  else bad "build_dbd_formation.py --check (dbd_formation.json drifted from source-data/datagoth/dbd_newco.csv)"
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
  ( cd "$PIPE" && python3 build_crop_farmer_income.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_crop_farmer_income.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_crop_farmer_income.py --check (oae_yield.json/farmgate_prices/doae_planted_area/nabc_agri absent — not data drift)"
  else bad "build_crop_farmer_income.py --check (crop_farmer_income.json drifted from oae_yield.json/farmgate_prices.json/doae_planted_area.json/nabc_agri.json)"
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
  ( cd "$PIPE" && python3 build_vehicle_flow_transport.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_vehicle_flow_transport.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_vehicle_flow_transport.py --check (dlt mirror absent/<12mo — not data drift)"
  else bad "build_vehicle_flow_transport.py --check (vehicle_flow_transport_by_province.json drifted from the dlt mirror)"
  fi
  ( cd "$PIPE" && python3 build_truck_flow.py --check >/dev/null 2>&1 ); rc=$?
  if [ "$rc" -eq 0 ]; then ok "build_truck_flow.py --check"
  elif [ "$rc" -eq 3 ]; then skip "build_truck_flow.py --check (dlt mirror absent/<24mo or output not generated — not data drift)"
  else bad "build_truck_flow.py --check (truck_flow.json drifted from the dlt mirror)"
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
  ( cd "$PIPE" && python3 build_competitor_census.py --check >/dev/null 2>&1 ) && ok "build_competitor_census.py --check" || bad "build_competitor_census.py --check (competitors_census.json drifted from official-locator/national/overture censuses)"
  ( cd "$PIPE" && python3 build_rival_density.py --check >/dev/null 2>&1 ) && ok "build_rival_density.py --check" || bad "build_rival_density.py --check (rival_density.json drifted from amphoe.json/competitors_census.json/th_amphoe.geojson)"
  ( cd "$PIPE" && python3 build_peer_province.py --check >/dev/null 2>&1 ) && ok "build_peer_province.py --check" || bad "build_peer_province.py --check (peer_province.json drifted from rival_density.json — run: python3 pipeline/build_peer_province.py)"
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
