# PROGRESS LOG — AutoX / เงินไชโย Credit Intelligence

Reverse-chronological. Most recent first. "Decision" entries explain *why* a path was taken so you
don't re-litigate settled choices.

---

## 2026-06-28 — Unified Vercel platform + Rayong catchment explorer

**State now:** One deployable static app in `platform/` with a shared nav across all routes.
Validated locally (all routes serve 200). NOT yet deployed (Claude has read-only Vercel access;
Kaustav deploys).

- Built `rayong-catchment.html` — the "DataProteins-style" view Kaustav asked for: 3,631 real OSM
  building footprints extruded in deck.gl over the Mueang Rayong core, AutoX branches as gold labelled
  pins, 25 live competitors as brand-coloured dots, POI scatter, named landmarks as chips.
  - LEFT card = reachable population at 5/10/15-min walk (recomputes when you tap a branch) + catchment context.
  - RIGHT card = verdict (contested: 25 competitors vs 9 AutoX ≈ 2.8:1), top-5 gaps (tap to fly), 3 recommendations.
  - Top strip = brand counts (AutoX / Srisawad / Tidlor / Muangthai / 7-Eleven+ / vehicle / markets).
- **Decision — reachable population is a dasymetric ESTIMATE**, not a true isochrone: building floor-area
  within walk radii (400/800/1200 m) × local occupancy (~1 person / 45 m²). Honest, matches the reference's
  method family. A true street-network isochrone needs a routing API → see NEXT_STEPS.
- **Decision — buildings are urban-core only.** OSM building coverage is good in Mueang Rayong town but
  ~0 in the factory zones (Pluak Daeng returned 0 buildings). So the catchment view is the *urban* catchment;
  for factory zones fall back to the province district-polygon 3D view.
- **Decision — multi-page, not single-DOM SPA for the 3D scenes.** Three WebGL scenes in one page crashed
  on Kaustav's phone ("uncaught script error"). Each 3D view is its own route → fresh GL context → stable.
  Still one Vercel deployment, one nav bar. `build_platform.py` assembles the Rayong pages.
- Moved Rayong payloads into `platform/data/` and externalized them (pages `fetch()` their JSON instead of
  inlining), with a loading state + error message on fetch failure.
- Added shared `#nav` to `index.html` + hash deep-linking (`index.html#map` opens the Map tab) so the nav is
  consistent and the Rayong pages can link back into specific SPA tabs.

## 2026-06-28 (earlier) — Rayong province 3D deep-dive

- Built `rayong-province.html`: deck.gl extruded **district polygons** (8 Rayong amphoe), switchable
  elevation metric (Workers / Factories / Vehicles), 57 branches, 30 live competitors, estates, POI.
  Bottom-sheet intel panel with tabs: What impacts them / Workers & income / Districts / Competitors / Nearest.
- **Decision — dropped the abstract per-branch "agri_pd" PD score for Rayong.** Kaustav found it too
  far-fetched for a single province; he wanted concrete facts (nearest POI, worker counts, income, factories,
  competitors). The PD score still exists nationally (Overview/National), but Rayong leads with real numbers.
- Pulled real income/worker facts (cited): Rayong = EEC core, ฿400/day min wage (top tier ≈ ฿10,400/mo),
  EEC pay 10–25% above Bangkok, national avg ฿15,972/mo (Q3-25). Anchors: Map Ta Phut petrochemicals,
  automotive (Toyota/Ford/BMW/Mitsubishi) pivoting to **EV** (Chinese BYD/Great Wall plants). 475k skilled
  workers needed in EEC by ~2030. "For daily life you rely on a motorbike or car" → vehicle-dependent =
  title-loan relevant.
- **"What impacts these people" narrative:** EV transition is THE swing factor (threatens ICE auto-parts
  workers, creates EV jobs); plus US tariffs (18% exports to US), petrochemical cycle, ฿400 min wage,
  automation/Thailand 4.0, vehicle dependence.
- Per-district rollups: Mueang Rayong (17 br, 472k working-age, vehicle hub), **Pluak Daeng (factory core,
  ind10≈148, 4 estates — Amata/Eastern Seaboard)**, Nikhom Phatthana, Ban Chang (near Map Ta Phut),
  and rural east (Klaeng / Wang Chan / Khao Chamao / Ban Khai).
- Pulled 30 live competitors via Google Places: Srisawad ×10, Muangthai Capital ×10, Ngern Tid Lor ×9,
  Krungsri Auto ×1 — cluster hard in Mueang Rayong (Thapma/Choeng Noen/Noen Phra) + Map Ta Phut.

## Earlier sessions — national build (condensed)

- Geocoded all 2,015 branches from the Chaiyo locator API; 354 building-precise, rest tambon/zip centroid.
- Built `branches_final.json` master (46 fields): demand, industrial/bank/atm/cvs/etc. POI-within-10km,
  nearest industrial estate, district working-age pop (UNFPA/HDX), drought anomaly (WFP/HDX),
  and segment scores **agri_pd, merchant_demand, merchant_pd, collateral_density, tourism_score**.
- **Decision — segments diverge (core analytical insight).** "Farmers" aren't monolithic: CROP households
  (rice/rubber/sugar/palm) are stressed (double-digit price declines on the WB Pink Sheet), but
  LIVESTOCK/FISHERIES/FORESTRY households are resilient (chicken +25.6%, beef +18.4%, fishmeal +14.1%,
  logs +11.9%); gold +62.7%. agri_pd = crop-price stress × drought, urban-suppressed, minus a regional
  livestock-income buffer.
- **Decision — worker lending is structurally an East+Central play.** Real industrial density: East ind10≈71,
  Central&BKK≈67, vs Isan≈1, South≈2, North≈9. Separate from Isan agri risk.
- Built the national static platform (Overview / National map / Acquisition / Branches) after a heavy
  inline-data 3D engine threw "uncaught script error" on mobile → rearchitected to slim external data + Leaflet.
- White-space found: estates with ≤3 AutoX within 10km (WHA Eastern Seaboard IE 2 has own=0), merchant
  white-space (high vendor demand, few branches), collateral-rich white-space.

---

## Known-good checkpoints
- `platform/` serves 200 on all routes via `python3 -m http.server` (last verified 2026-06-28).
- All embedded JS passes `node --check`.
- `branches_final.json` = 2,015 records, 46 fields, ~99% joined on district population.

## Open threads (see NEXT_STEPS.md for detail)
1. Deploy to Vercel + verify production (Claude can read logs once it's live).
2. Run blocked gov data from Thai IP → DLT vehicles, DIW factories → fold into the loop.
3. True 15-min isochrone (routing API) to replace the catchment walk-radius estimate.
4. Widen the catchment view beyond Mueang Rayong where OSM building coverage allows.
5. Province-precise livestock/aquaculture mapping (DLD/DOF data not in OAE datastore).
