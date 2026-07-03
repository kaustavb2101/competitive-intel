# DATA ACQUISITION PLAN — turning ESTIMATED into MEASURED

> **Audit date:** 2026-07-02 · **Auditor:** data-gap committee agent (branch `agent/data-gap-plan`)
> **Goal:** rank every ESTIMATED / proxy field currently shipped in `platform/data/` and name the
> real MEASURED source that would replace or upgrade it, with an honest channel assessment
> (what can be automated from where, and what cannot be automated at all).
> **Mandate:** nothing here invents data. Every replacement source below is a real, named dataset.
> Where a dataset id could not be verified from this sandbox (because egress is blocked — see §0),
> that is stated explicitly rather than guessed.

---

## 0. Channel definitions — and what THIS session actually observed

| Channel | Meaning |
|---|---|
| **[SANDBOX-NOW]** | Pullable from this cloud sandbox in the current session. |
| **[CI]** | Runnable from a GitHub Actions runner: unrestricted egress but a **foreign IP** — works for Overture / World Bank / HDX / OAE-catalog-class hosts, does NOT work for the geo-blocked data.go.th / DLT family. |
| **[THAI-IP]** | Owner's desktop on a Thai residential connection only (geo/Cloudflare-blocked hosts). |
| **[OWNER]** | Needs a manual internal export or a human decision — cannot be automated at all. |

### 0.1 HONEST FINDING: this session has ZERO external egress

The repo's reachability matrix (`docs/DATA_SOURCES.md`) documents Overpass, HDX,
`catalog.oae.go.th` and `thedocs.worldbank.org` as REACHABLE from the sandbox. That matrix was
measured in an earlier session. **In THIS session (2026-07-02 ~01:01 UTC) the egress proxy denies
every external host at policy level** — verified, exact errors:

```
$ curl -sS "https://catalog.oae.go.th/api/3/action/package_search?q=ราคา&rows=5"
curl: (56) CONNECT tunnel failed, response 403

$ curl -sI https://data.humdata.org/api/3/action/site_read      -> CONNECT tunnel failed, response 403
$ curl -sI https://thedocs.worldbank.org/                        -> CONNECT tunnel failed, response 403
$ curl -sI "https://maps.mail.ru/osm/tools/overpass/api/interpreter?...": CONNECT tunnel failed, response 403
$ curl -sI http://catalog.oae.go.th/... (plain HTTP)             -> 403 from proxy

$ curl -sS "$HTTPS_PROXY/__agentproxy/status"   (excerpt)
  {"kind": "connect_rejected",
   "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)",
   "host": "catalog.oae.go.th:443"}

WebFetch tool: catalog.oae.go.th -> HTTP 403; thedocs.worldbank.org -> HTTP 403;
               even https://example.com -> HTTP 403 (proves it is session policy, not the sites).
```

The proxy's own runbook (`/root/.ccr/README.md`) states: *"403/407 from the proxy: the destination
host is not allowed by your organization's egress policy for this session. Do not retry or route
around it — report the blocked host."* Reported here, not routed around.

**Consequence:** the [SANDBOX-NOW] channel is **empty in this session**. Items that DATA_SOURCES.md
documents as sandbox-reachable are tagged **[SANDBOX*/CI]** below: expected to work from a sandbox
session with normal egress AND from a GitHub Actions runner; re-probe with `curl -sI` at the start
of any session before relying on them. This is also why Deliverable 2 (the OAE pull) was attempted
and could not be executed — full log in §2.

---

## 1. Ranked inventory — every ESTIMATED / proxy field shipped in `platform/data/`

Ranking = impact on the two standing objectives ÷ effort to land. "Impact" names the objective it
sharpens (**#1 portfolio risk**, **#2 where to expand**).

### Summary ladder (top → bottom)

| # | Estimated thing | Measured replacement | Channel | Impact | Effort |
|---|---|---|---|---|---|
| P1 | Entire `loan_tape_derived.json` (SYNTHETIC) | Real no-PII loan-tape export per `pipeline/loan_tape_schema.md` | **[OWNER]** | #1, transformative | Pipeline: none (exists). Owner: M |
| P2 | `collateral_density` proxy + province-inherited `veh` | DLT vehicle registrations by province/district (gdcatalog.dlt.go.th) | **[THAI-IP]** | #1 + #2, high | S (script exists) |
| P3 | `crop_stress.price_stress` GLOBAL WB proxy | OAE farm-gate prices "ราคาที่เกษตรกรขายได้" (catalog.oae.go.th CKAN; data.go.th mirror) | **[SANDBOX*/CI]** or [THAI-IP] | #1, high | S–M |
| P4 | Competitor census 21.9% lower bound | Operators' own store-locator census (`pull_competitor_branches.py`) | **[THAI-IP]** | #2, high | S–M (script exists) |
| P5 | `exit_whitespace` sub-scale-operator inference | BoT / MoF registered-operator lists (post Q1-2026 registration deadline) | **[THAI-IP]** (CI untested) | #2, high | M |
| P6 | `occupation_risk` Overture-sample occupation mix | NSO LFS industry×province + NSO 2022 Business & Industrial Census (scaffold ready) | **[THAI-IP]** | #1, medium-high | S (scaffold exists) |
| P7 | Catchment reachable-pop dasymetric estimate | Street-network 15-min isochrones (self-hosted OSRM/Valhalla over Geofabrik Thailand extract) | **[CI]** | #2, medium | M |
| P8 | `collateral_outlook` GLOBAL gold YoY leg | Thai Gold Traders Association daily prices (goldtraders.or.th) | **[THAI-IP]** (CI untested) | #1, medium | S |
| P9 | Risk-trend has 1 vintage (no measured deltas) | A 2nd+ snapshot after ANY refresh above (`timeseries.py`) | any of the above | #1, medium | S |
| P10 | 75/77 provinces lack building footprints | Overture buildings per province + PMTiles hosting (`pull_overture_buildings.py`, `RUN_TILES.sh`) | **[CI]** or desktop | #2, medium | M |
| P11 | `tourism_score` on MOTS 2024 vintage | MOTS 2025 province tourism revenue release | **[THAI-IP]** | #2, low-med | S |
| P12 | Drought = rainfall-anomaly proxy (HDX) | GISTDA drought-index rasters; refresh HDX WFP rainfall each vintage | HDX **[SANDBOX*/CI]**; GISTDA [THAI-IP] | #1, low-med | S refresh / M GISTDA |

Composites that stay honestly ESTIMATED even after the above (they are models, not measurements):
`opportunity_score`, `branch_risk`/`province_risk`, `segment_exposure`, `poi_relevance` weights,
`occupation_risk` weighting, `agri_pd`/`merchant_pd`/`merchant_demand` segment scores. The plan
upgrades their INPUT legs; the composite labels stay ESTIMATED until P1 lets us calibrate them
against real outcomes (see §3).

### P1 — the real loan tape (the single biggest estimate in the product)  [OWNER]
- **(a) What it estimates today:** `platform/data/loan_tape_derived.json` is 100% SYNTHETIC
  (`meta.SYNTHETIC=true`) — vintage 90+ aging curves, branch ROI/payback, HHI concentration, PD
  calibration are all placeholders. Downstream, every "which segment is getting riskier" read is a
  proxy because we have no measured defaults.
- **(b) Measured source:** an internal AutoX no-PII export matching the committed contract
  `pipeline/loan_tape_schema.md` (loans + monthly branch-AUM, join on branch `code`). Not a public
  dataset — it is AutoX's own book.
- **(c) Channel:** **[OWNER]** — cannot be automated, period. Needs Kaustav to request the export
  (risk/IT + PII governance). The pipeline side is already done: `ingest_loan_tape.py --real`
  validates the contract and drops the SYNTHETIC stamp.
- **(d) Impact/effort:** Objective #1 goes from proxy to measured in one file; also unlocks
  calibrating `agri_pd`/`branch_risk`/`poi_relevance` weights against real 90+ rates (§3).
  Pipeline effort zero. **Rank 1 by a wide margin.**

### P2 — DLT vehicle registrations (collateral supply, measured)  [THAI-IP]
- **(a) What it estimates:** `collateral_density` in the branch master = z-scored OSM
  vehicle-shop(0.6)+gold-shop(0.4) counts — an explicit DLT-blocked stand-in
  (`docs/DATA_SOURCES.md` §Score definitions). `amphoe.json` `veh` is province-INHERITED, not
  district-measured. `collateral_outlook`'s moto-share leg uses the committed
  `vehicles_by_province.json`, which needs a refresh.
- **(b) Measured source:** DLT registered-vehicle stock, by province and (where published) by
  registration office/district — `gdcatalog.dlt.go.th/en/dataset/` (DLT's own CKAN catalog,
  separate from data.go.th) and the data.go.th `vehicles_dlt` topic already wired in
  `pipeline/autox_dgt_ingest.py` (queries "รถจดทะเบียน กรมการขนส่งทางบก").
- **(c) Channel:** **[THAI-IP]** — stat.dlt.go.th/web.dlt.go.th DNS-fail/503 and data.go.th is
  Cloudflare geo-blocked from any foreign IP (so [CI] does NOT work). Runbook already exists:
  `docs/TONIGHT_CHECKLIST.md`, script `autox_dgt_ingest.py`, fold-in `ingest_gov.py`.
- **(d) Impact/effort:** collateral TAM per district measured for BOTH objectives; effort S because
  every script exists — it only needs to be executed from the Thai laptop. **Rank 2.**

### P3 — OAE Thai farm-gate crop prices (this plan's Deliverable-2 target)  [SANDBOX*/CI] or [THAI-IP]
- **(a) What it estimates:** `crop_stress.json` `price_stress` = planting-area-weighted **World Bank
  Pink Sheet GLOBAL** price YoY — labelled "a DIRECTION proxy, NOT Thai farm-gate" in its meta.
  Global rice/rubber/palm move with, but are not equal to, Thai farm-gate; the entire agri-stress
  price leg (and the double-stress flag's price condition) rides on this proxy.
- **(b) Measured source:** OAE "ราคาที่เกษตรกรขายได้" (prices farmers actually received, monthly,
  by commodity). Known access routes:
  1. `catalog.oae.go.th` CKAN — `GET /api/3/action/package_search?q=ราคาที่เกษตรกรขายได้`; the
     enrichment loop already uses this catalog for production trends (package ids like
     `dataoae1104` rice, `dataoae1404` rubber in `autox_enrich_loop.py`). The exact farm-gate
     package id could **not be verified from this session** (egress blocked, §0.1) — resolve it
     with the search call above; do not hardcode a guessed id.
  2. data.go.th mirror — the `crop_price_oae` topic in `autox_dgt_ingest.py` (this is how the
     committed `source-data/crop_prices.json` was produced).
  - **Important nuance found in this audit:** `source-data/crop_prices.json` IS already measured
    OAE farm-gate — but its vintage is **BE 2562 (2019 CE)**, seven years stale, which is exactly
    why `build_crop_stress.py` uses the current-month World Bank proxy for direction instead.
    The gap is **freshness**, not existence. The pull must land a current-vintage series
    (monthly, latest 13+ months so a YoY can be computed) as `source-data/oae_farmgate_prices.json`.
- **(c) Channel:** **[SANDBOX*/CI]** — `catalog.oae.go.th` is documented reachable from a foreign
  datacenter IP (nginx, not Cloudflare-geoblocked; DATA_SOURCES.md line "OAE agriculture ✅"), so a
  GitHub Actions runner should reach it even when a sandbox session (like this one) cannot.
  Fallback **[THAI-IP]** via data.go.th. **Attempted in this session and blocked** — §2 has the
  exact errors and the ready-to-run recipe.
- **(d) Impact/effort:** upgrades the price leg of objective #1's headline layer from
  GLOBAL-proxy to MEASURED-Thai for rice/rubber/oil-palm (and adds sugarcane/cassava/maize, which
  today are area-mapped but unpriced — `meta.coverage.planting_area_crops_no_price`). Effort S–M
  (one pull + a preference branch in `build_crop_stress.py`). **Rank 3.**

### P4 — full competitor branch census  [THAI-IP]
- **(a) What it estimates:** `competitor_coverage.json` states found-vs-expected coverage is
  **21.9%** (MTC 11.3%, Tidlor 39%, Srisawad 49%) — the Google-Places + Overture census is an
  honest lower bound, and `expected` per brand is ESTIMATED-from-public-reports (IR citations).
  This lower bound feeds `opportunity_score.competitor_gap` and `exit_whitespace.big4_competitors`.
- **(b) Measured source:** the operators' own store-locator endpoints (Srisawad, Muangthai Capital,
  Ngern Tid Lor, Heng Leasing branch finders) — the complete self-published branch lists.
  `pipeline/pull_competitor_branches.py` (--discover/--pull/--merge) is already built for exactly
  this.
- **(c) Channel:** **[THAI-IP]** — competitor corporate sites are WAF-blocked from foreign IPs
  (DATA_SOURCES.md reachability row "competitor sites ❌"), so [CI] is out.
- **(d) Impact/effort:** turns the #2-objective competitor-density leg from a 22% sample into a
  near-census; effort S–M (script exists). **Rank 4.**

### P5 — registered-operator lists → real "exit" universe  [THAI-IP]
- **(a) What it estimates:** `exit_whitespace.json` is an ESTIMATED PROXY — "where AutoX could
  capture share if sub-scale operators exit" inferred from big-4 scarcity × our white-space. Its
  own meta admits we do NOT census the sub-scale operators that would actually exit.
- **(b) Measured source:** the regulator's own registries, which after the **Q1-2026 BoT
  registration deadline** define the compliant universe: the BoT list of licensed vehicle-title /
  personal-loan operators (bot.or.th licensee lists) and the Ministry of Finance **pico-finance
  licensee list** (published monthly by the Fiscal Policy Office, fpo.go.th / 1359.go.th).
  Registered-then-disappeared = a measured exit; district gaps in the registry = measured
  white-space.
- **(c) Channel:** **[THAI-IP]**. bot.or.th/fpo.go.th were not reachability-tested from a working
  sandbox (this session cannot test anything, §0.1); Thai-gov WAF behaviour makes [THAI-IP] the
  safe assumption. Test `curl -sI https://www.bot.or.th` from a normal-egress session before
  assuming [CI].
- **(d) Impact/effort:** converts the weakest #2-objective layer from inference to registry-backed;
  effort M (new parser for a Thai XLS/PDF list; geocode to amphoe). **Rank 5.**

### P6 — NSO occupation / establishment measures  [THAI-IP]
- **(a) What it estimates:** `occupation_risk.json` = MEASURED Overture occupation shares (a
  sample/lower bound of establishments, not employment) × ESTIMATED stressed-sector weights.
  `branch_labor.json`'s NSO legs are province-level only.
- **(b) Measured source:** NSO Labour Force Survey employed-by-industry × province (data.go.th,
  the `employment` topic already in `autox_dgt_ingest.py`) + the **NSO 2022 Business & Industrial
  Census** (establishments + workers by industry × area) — `ingest_gov.py` already carries a
  drop-in distiller scaffold for the census CSV (inert until the file lands in `pipeline/dgt_out/`).
- **(c) Channel:** **[THAI-IP]** (all data.go.th).
- **(d) Impact/effort:** replaces the establishment-sample denominator with measured employment for
  objective #1's occupation lens; effort S — scaffolding is committed, just run the pull. **Rank 6.**

### P7 — true 15-minute isochrones  [CI]
- **(a) What it estimates:** the catchment scenes' "reachable population" is a dasymetric
  walk-radius estimate (floor-area × occupancy inside a fixed radius) — flagged as the #3 item in
  CLAUDE.md "Where to go next".
- **(b) Measured source:** street-network isochrones computed on the real OSM road graph —
  self-host OSRM or Valhalla in a CI job over the Geofabrik Thailand extract
  (`download.geofabrik.de/asia/thailand-latest.osm.pbf`) and bake 15-min polygons per branch.
  (Public ORS API keys also work but rate-limit at 2,015 branches; self-host avoids that.)
- **(c) Channel:** **[CI]** — Geofabrik + a local router need no Thai IP. (Blocked in THIS session
  like everything else, §0.1.)
- **(d) Impact/effort:** replaces the estimate with a network-measured catchment for objective #2
  site decisions; effort M (one containerized CI job + a bake script). **Rank 7.**

### P8 — Thai gold price for the collateral outlook  [THAI-IP] (CI untested)
- **(a) What it estimates:** `collateral_outlook.json`'s gold leg applies **World Bank GLOBAL gold
  YoY** nationally — meta labels it "a DIRECTION proxy for Thai gold-pawn collateral".
- **(b) Measured source:** Thai Gold Traders Association (สมาคมค้าทองคำ) daily bar/ornament buy-sell
  prices — `goldtraders.or.th` (the reference price every Thai gold shop uses); THB-denominated, so
  it also captures the FX component the global proxy misses.
- **(c) Channel:** likely **[THAI-IP]**; untestable from this session — probe `curl -sI
  https://www.goldtraders.or.th` from a normal-egress session first.
- **(d) Impact/effort:** small, honest upgrade to a #1-objective layer; effort S (one scraper +
  meta relabel). **Rank 8.**

### P9 — a second vintage (measured deltas)  [any refresh channel]
- **(a) What it estimates:** nothing is falsely labelled — but the Risk-trend tab has ONE snapshot,
  so every "getting riskier" statement is a level, not a measured change.
- **(b) Measured source:** not a new dataset — run `pipeline/timeseries.py` after ANY of P2/P3/P6
  refreshes so `deltas.json` carries real vintage-over-vintage movement.
- **(c) Channel:** rides on whichever channel lands a refresh first.
- **(d) Impact/effort:** S; unlocks the whole TIME dimension of objective #1. **Rank 9.**

### P10 — building footprints for the other 75 provinces  [CI]
- **(a) What it estimates/lacks:** only Rayong + Bangkok ship catchment buildings; other provinces
  show the "buildings haven't been pulled yet" notice. Building heights are baked ESTIMATES even
  where footprints are measured.
- **(b) Measured source:** Overture Maps buildings per province bbox — `pull_overture_buildings.py
  --province <slug>` (bboxes already committed in `province_bbox.json`), plus the
  `build_building_tiles.py` → PMTiles/CDN route (`docs/BUILDING_TILES.md`).
- **(c) Channel:** **[CI]** or desktop — Overture S3/Azure endpoints are foreign-IP-friendly.
- **(d) Impact/effort:** visual/coverage completeness for #2; effort M (compute + hosting).
  **Rank 10.**

### P11 — MOTS tourism revenue 2025 vintage  [THAI-IP]
- **(a)** `tourism_score` uses MOTS **2024** province tourism revenue; 2025 saw the first tourist
  decline (−7.2%), so the vintage materially mis-states tourism-dependent merchant demand.
- **(b)** MOTS/กระทรวงการท่องเที่ยวฯ province tourism statistics 2025 release (mots.go.th; also
  mirrored on data.go.th).
- **(c)** **[THAI-IP]**. **(d)** low-medium impact on the merchant lens; effort S. **Rank 11.**

### P12 — drought leg upgrades  [SANDBOX*/CI] + [THAI-IP]
- **(a)** `drought` in crop_stress is a rainfall-anomaly proxy (HDX WFP `rain_3mo_anom`) — honest
  "measured proxy", but rainfall ≠ agricultural drought.
- **(b)** (i) keep the HDX WFP rainfall resource fresh each vintage (resource id already wired in
  `autox_enrich_loop.py`: `76a5bb85-9a55-4cda-afcb-6cb4fa2739cc`) — **[SANDBOX*/CI]**; (ii) upgrade
  to GISTDA drought-index products (drought.gistda.or.th) for a soil/vegetation-measured index —
  **[THAI-IP]** (untested).
- **(d)** low-medium; effort S for the refresh, M for GISTDA. **Rank 12.**

---

## 2. Deliverable-2 execution log — OAE farm-gate pull: ATTEMPTED, BLOCKED, SKIPPED

Per the committee instruction ("if the OAE portal is unreachable after a genuine attempt, say so
with the exact errors and skip the code changes"), here is the record:

1. **Attempted** `https://catalog.oae.go.th/api/3/action/package_search?q=ราคา&rows=5` (curl via the
   session proxy) → `curl: (56) CONNECT tunnel failed, response 403`; proxy status endpoint logged
   `connect_rejected … "gateway answered 403 to CONNECT (policy denial or upstream failure)",
   host: catalog.oae.go.th:443`.
2. **Attempted** plain-HTTP `http://catalog.oae.go.th/...` → `403` from the proxy.
3. **Cross-checked** it is not OAE-specific: `data.humdata.org`, `thedocs.worldbank.org`, the
   Overpass mirror `maps.mail.ru` — all `CONNECT tunnel failed, response 403`.
4. **Attempted the alternate fetch path** (WebFetch tool, separate infrastructure):
   `catalog.oae.go.th` → HTTP 403; `thedocs.worldbank.org` → HTTP 403; control probe
   `https://example.com` → HTTP 403. The control probe proves this is a **session-wide egress
   policy denial**, not the OAE portal being down or geo-blocking us.
5. The proxy runbook explicitly forbids retrying/routing around policy 403s, so no workaround was
   attempted.

**Decision:** Deliverable-2 code changes were **skipped** (per instruction — the graceful-fallback
wiring without the measured file to test against would be untestable guess-code). No stub, no
placeholder file, no fabricated prices.

### Ready-to-run recipe (for the first session/runner with egress — est. 30–60 min)
1. **Find the dataset (do not hardcode a guessed id):**
   `GET https://catalog.oae.go.th/api/3/action/package_search?q=ราคาที่เกษตรกรขายได้&rows=20`
   — pick the monthly farm-gate price package covering rice (ข้าว), rubber (ยางพารา), sugarcane
   (อ้อย), oil palm (ปาล์มน้ำมัน), cassava (มันสำปะหลัง), maize (ข้าวโพด). Then
   `package_show?id=…` → CSV/XLSX resource URLs (or `datastore_search` if datastore-backed).
2. **Land** `source-data/oae_farmgate_prices.json`:
   `{"meta": {"source": "<portal URL>", "dataset_id": "...", "resource_url": "...",
   "vintage": "<latest BE year+month in the data>", "pulled": "<date>", "label": "MEASURED —
   OAE farm-gate (ราคาที่เกษตรกรขายได้)"}, "commodities": {"rice": {"latest": …, "prior_year": …,
   "yoy": …, "unit": "…", "series_label_th": "…"}, …}}` — YoY computed from the series itself,
   latest month vs same month prior year. Fallback route if the catalog moves: the
   `crop_price_oae` topic in `autox_dgt_ingest.py` from the Thai laptop.
3. **Wire** `pipeline/build_crop_stress.py`: if `source-data/oae_farmgate_prices.json` exists AND
   its vintage is current (guard against a stale file — the 2562/2019 lesson from
   `crop_prices.json`), use its per-crop YoY for `crop_yoy` and set
   `meta.fields.price_stress = "MEASURED — Thai farm-gate (OAE), YoY %"`, keeping the World Bank
   board as the labelled GLOBAL-proxy fallback when the file is absent (deterministic both ways;
   `--check` must pass in both states, mirroring the skip-pass pattern used by
   `build_occupation_risk.py`).
4. Re-run `python3 build_crop_stress.py` + `bash tests/run.sh check`; snapshot with
   `timeseries.py` so the proxy→measured transition is a recorded vintage change, not silent drift.

---

## 3. What CANNOT be automated — say it plainly

- **The loan tape (P1).** No public source exists for AutoX's own book. Owner export or nothing.
  Until then every default/PD number in the product is a labelled proxy, and `loan_tape_derived.json`
  stays stamped SYNTHETIC.
- **A measured AutoX NPL.** `peer_npl.json` is peer-reported context (Tidlor/MTC/SAWAD); it can
  never become an AutoX number by pulling harder — only P1 fixes that.
- **Composite score calibration.** `agri_pd`, `branch_risk`, `opportunity_score`, `poi_relevance`
  weights are judgement models. More measured INPUTS (P2–P6) make them better-fed, but they stay
  ESTIMATED until P1 provides real outcomes to calibrate weights against. Do not relabel them
  MEASURED on input upgrades alone.
- **Competitor "expected" branch counts.** Cited from IR/annual reports by hand; a human reads the
  next annual report. (P4's store-locator census reduces how much this matters.)
- **Sub-scale-operator exits in real time.** Even with P5's registries, an operator quietly closing
  a shopfront is not in any dataset; exit_whitespace keeps an ESTIMATED component forever.
- **Anything data.go.th / DLT from any cloud IP.** Cloudflare geo-block is on the network path, not
  auth — no token, runner region trick, or retry fixes it. Thai residential IP only.
- **This sandbox, this session.** Zero egress (§0.1). Everything network-dependent in this plan
  routes through [CI], [THAI-IP], or [OWNER] until a sandbox session with normal egress recurs.
