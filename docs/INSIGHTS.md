> **Provenance:** consolidated from the sibling **TMLI** effort (`kaustavb2101/watcher`) and vendored into competitive-intel on 2026-07-09. Paths written for the `autox-credit-intel/` root map to this repo root; where this repo is more evolved (e.g. `platform/data/`), trust the live code.

# INSIGHTS.md — everything this project has learned

Consolidated from the full conversation history. Read alongside CLAUDE.md.
Tags: [MEASURED] = hard data · [CONTEXT] = sourced, area-level · [DECISION] = settled choice, don't re-litigate.

## 1. Market & strategy findings

- **[MEASURED] North is the real under-served demand.** White space (demand percentile − presence
  percentile): North **+9** with 66 high-WS branches; South +1; East +2; Central&BKK −1; **Isan −4
  (over-covered relative to measured demand)**. Top individual leads: Rayong, Chiang Mai, Kamphaeng Phet.
- **[MEASURED] Worker lending is structurally an East + Central play.** Industrial density (OSM then
  confirmed by DIW): East/Central dominate; Isan ~nil. Isan is the agri book, not the worker book.
- **[CONTEXT] "Farmers" are not one segment — the segments diverge.** WB Pink Sheet (Dec-2025): crops
  DOWN (rice −19.5%, rubber −13.5%, sugar −25.9%, palm −17.6%) while protein/forestry UP (chicken +25.6%,
  beef +18.4%, fishmeal +14.1%, logs +11.9%). **Gold +62.7%** → lifts gold-collateral value and pawn
  competition. Rice belt (Isan/North/Central plains) carries real income pressure; livestock/aqua households
  are the buffer. OAE 2026 outlook: rice + rubber = risk crops; cassava/palm/chicken/durian firmer.
- **[CONTEXT] Macro backdrop:** GDP 2026 ~1.6%; household debt 86.8% (Sep-25); inflation ~0.3%;
  tourists 2025 32.9M (−7.2%, first drop); ฿44bn co-payment scheme; credit contracting.
- **[MEASURED] Rayong deep-dive (the flagship template):**
  - DIW authoritative: **2,201 factories · 139,484 workers · ฿2.0tn registered capital.**
    Pluak Daeng = **399 factories / 36,327 workers** (OSM showed ~0 — proxy failure proven).
    Mueang Rayong 570 factories/25k workers; Nikhom Phatthana 563/38k.
  - DLT authoritative: **878,348 registered vehicles, 511,079 motorcycles (58%)** = the real
    title-collateral pool (motorcycle title ≈ 50% of AutoX book, car/pickup ≈ 25%).
  - Income: EEC core, ฿400/day min wage (top tier ≈ ฿10,400/mo), EEC pay 10–25% above Bangkok,
    national avg ฿15,972/mo (Q3-25). Workers: skilled technicians, contract line labour, migrants.
  - **What impacts these people:** EV transition is THE swing factor (BYD/Great Wall plants create jobs,
    threaten ICE parts suppliers); US tariffs (18% of exports); petrochemical cycle; ฿400 wage →
    automation; deep vehicle dependence (title-loan relevant).
  - Competitors cluster in **Mueang Rayong (Thapma/Choeng Noen/Noen Phra) + Map Ta Phut**: ~2.8 rival
    branches per AutoX in the urban core. AutoX is strong on the factory edge, thin in the urban centre.
  - Play: infill Thapma–Choeng Noen corridor; lead with vehicle-title + gold; compete on speed
    (same-day) not rate; hold the factory edge as the defensible base.
- **[MEASURED] Competition (3 provinces so far):** Rayong 30, Chonburi 24, Chiang Mai 20 rival branches
  (Srisawad / Muangthai / Tidlor / Krungsri), brand-classified, deduped by place_id.
- **[MEASURED] Estate white-space:** WHA Eastern Seaboard IE 2 has **0** AutoX ≤10km; Southern IE
  Songkhla 1; several others ≤3 → factory-worker white space list lives in meta.json.

## 2. The honest-assessment verdict (still true)

- This is an **external market-intelligence layer**, not a risk tool: **zero AutoX loan-book data** is in
  it. Nothing is validated against a single real branch outcome. [DECISION] External-first, perfect it,
  then plug internal data (the Calibrator member exists for that day).
- **[DECISION] Abstract per-branch PD scores were rejected by Kaustav** ("far-fetched"). agri_pd etc.
  were retired from the acquisition surface. Commodity/drought/macro appear as labeled area **context**
  only. The model that survives scrutiny: **white space = demand percentile − presence percentile**, from
  five measured components (vehicle shops, gold shops, fresh markets, industrial [now DIW], working-age pop),
  equally weighted **because nothing exists to calibrate weights against yet**.
- Geocoding is the quietest data-quality lever: baseline 354/2,015 building-precise (18%); tambon-centroid
  errors up to **10.8 km** proven. Every proximity number sharpens as this rises. Now 378 after 3 batches.
- Three-tier honesty is a product feature: **Measured / Context / Estimated**, visually distinct in the UI,
  with provenance and the geocode caveat stated on the Overview.

## 3. The geo-block breakthrough (the most reusable insight)

**data.go.th is Cloudflare-geo-blocked to Thai IPs — but the departments' OWN catalogs are not.**
- **DIW factories:** `diw-dataset.diw.go.th` (CKAN) → `factype3` = 67,416 category-3 factories,
  all 77 provinces, each with registered capital, workers, horsepower. Also `fac-eec-class3`.
- **DLT vehicles:** `gdcatalog.dlt.go.th` (CKAN) → `dataset_1_1_04` = cumulative registered vehicles by
  **province AND type**. National: 23.2M motorcycles / 12.6M cars / 6.96M pickups.
  ⚠ Resource URLs **rotate monthly** — always resolve the newest CSV via the API (census.py does this).
- MOT catalog (`datagov.mot.go.th`) is reachable but its files link back to blocked data.go.th — dead end.
- **Consequence: NOTHING in this project needs a Thai IP anymore.** The whole pipeline runs from any
  cloud host / GitHub Actions. (The DATA_GO_TH_TOKEN is therefore unnecessary; still rotate it — it was
  exposed in chat.)
- Reachable: Overpass mirrors (maps.mail.ru fast), Google Places, HDX, OAE CKAN, World Bank docs.
  Blocked: all data.go.th hosts, DLT direct hosts, IMF, FRED, competitor corporate sites, envilink.

## 4. Engineering lessons (paid for in crashes)

- **Never inline >1MB data + heavy WebGL in one HTML** → "uncaught script error" on mobile.
  Externalize JSON, fetch at runtime, serve over **http** (file:// blocks fetch).
- **One WebGL scene per page.** Leaflet (national 2,015 pts, canvas renderer) and deck.gl (3D Rayong
  views) live on separate routes with fresh GL contexts, one shared nav. [DECISION]
- OSM layer coords are **[lng, lat]** — this caused a real bug once (empty Rayong POI clip).
- OSM building coverage: good in urban cores (Mueang Rayong 3,631 footprints), **~zero in factory
  zones** → catchment 3D building view is urban-only; district-polygon 3D covers the rest.
- Thai text in deck.gl TextLayer needs `fontFamily:'IBM Plex Sans Thai'` + `characterSet:'auto'`.
- deck.gl TileLayer bounds come from `props.tile.boundingBox`.
- Reachable-population is a **dasymetric estimate** (building floor-area × ~1 person/45m² within walk
  radii) — honest but not a street-network isochrone; the upgrade path is a routing API (ORS/Valhalla).
- pip in this class of sandbox needs `--break-system-packages`.
- Theme: dark instrument console, IBM Plex Sans Thai + Mono; accent #5B7CFA; agri #C8433B,
  merchant #1C8C7D, collateral #7A4FE0, gold/opportunity #E6B450.

## 5. The committee (how quality improves recursively)

Members: Orchestrator (run_cycle.py) · Geocoder · Competitor Scout · Industry Census (DIW+DLT) ·
Calibrator (future — needs loan book) · Validator (the gate).
Protocol per cycle: **small batch → member proposes deltas → Validator gates (Thailand bbox, brand token,
name/token match, max-shift, dedup, no-regression) → merge → scorecard + log → repeat.** Rejections are
kept as a manual-review queue, never silently dropped.
Proven across 6 logged iterations: precise 354→378; factories OSM-proxy→DIW-authoritative (95% joined);
vehicles proxy→DLT-authoritative (77 provinces); competition 1→3 provinces measured; 1 bad geocode match
correctly rejected and held (@chaiyo30730, name mismatch).
Scale math: ~1,505 imprecise branches remain; Places Text Search ≈ $32/1k → ≈ **$48 one-time** to finish
geocoding. Scout to all 77 provinces is a similar bounded spend. Census members are free (gov CKAN).

## 6. Environment truths (so Claude Code doesn't rediscover them)

- Claude-chat has **read-only Vercel** (team `team_pYNrbLMZobN80m4jD7WPWybD`; projects incl.
  autox-calibration, thailand-labor-intel which holds the now-unneeded DATA_GO_TH_TOKEN) and **no GitHub
  connection** — nothing was ever pushed or deployed from chat; all state lives in this repo folder.
- Claude Code CAN: run git, push to GitHub, run `npx vercel --prod`, run the daemon, hit all the portals
  above. That's why the project moves there.
- Deploy boundary: **only `platform/` is the website.** `source-data/` (branch coords + phones) and
  `pipeline/`/`committee/` must not be published. Repo should be **private**; consider Vercel access
  protection (branch-level detail is sensitive pre-IPO).
