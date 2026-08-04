# SERVICE AUDIT — AutoX / เงินไชโย Credit-Intelligence Platform

> Emitted by the autonomous **market & service intelligence** loop. Audits the platform *as a
> service*: data freshness per layer, provenance coverage, broken data references, and heavy-JSON
> load weight. Every number here is read from the committed tree — nothing is estimated or invented.
> Regenerate the underlying ledger with `python3 pipeline/build_provenance.py`.

_Audit run: 2026-08-03 (c) · finding: with the data room re-confirmed clean this run — `build_provenance.py --check` reproduces exactly, the **live master production alias HTTP 200** on `/`, `/data/meta.json` and `/data/deltas.json` (one transient TLS-handshake blip on the first `deltas` fetch cleared on immediate retry — network flake, not a regression), and `site-health.yml` correctly targets the master production alias — a render-path re-scan of the surfaced-but-unprobed `data/*.json` reads (75 total, most secondary or graceful-degrading) closed the newest wave still uncovered: **`vehicle_models.json`** (the #275/#276 Macro "nameplate" wave, obj #1 collateral context — explicitly flagged as unprobed by the 2026-08-02 (c) audit below). It is load-bearing on **two** MEASURED render paths, not one: (1) the "which models, and which are growing" nameplate panel (`cb-nameplates`) GATES on `V.plates_last12` then renders the pickup/ppv `.top[]` boards (`plate/units/share_pct/yoy_pct`); (2) the **collateral pickup-definition verdict** (`renderYearTable`) takes this layer as the AUTHORITATIVE pickup count on AutoX's own nameplate rule (pickup+PPV nameplates in any class), falling back to the registrar's รย.3 truck class only when it is absent. The client loader itself sets `VMODELS=null` unless `Array.isArray(v.annual)`, so a truncated/gutted CDN deploy **silently** reverts BOTH surfaces to their fallback with no phone alert — the same "broken demo" blind spot the `collateral_book`/`macro_book`/`deltas` obj-#1 probes closed for their siblings. `check_site_health.py` now probes it (`_shape_vehicle_models`: fetch + parse + render-shape — asserts the `annual` array gate + a `plates_last12` dict carrying non-empty `pickup` AND `ppv` groups whose first `.top` row has a string `plate` and numeric `units`/`share_pct` — shape not values, robust to a future DLT-vintage refresh moving the counts). Verified: the real 21,829-byte payload accepted; twelve negatives reject non-dict / missing-or-empty-or-non-list `annual` / missing-or-empty `plates_last12` / missing pickup-or-ppv group / empty `.top` / row-missing-`plate` / non-numeric-`units` / missing-`share_pct`. Offline `--local platform` reports **116/116 HEALTHY** with `vehicle_models.json` served + shape-sane; the live alias serves it **HTTP 200** (21,829 bytes, matches local). Probe coverage **35 → 36** exec data layers. Determinism gate **121 passed · 0 failed** (data integrity 455/455 — the check phase does not read the probes). No `platform/data` file altered — probe-script-only, so no provenance regen needed. Next probe targets: the two sibling reads from the same nameplate wave still uncovered — `vehicle_brands.json` (`cb-vbrands`, gates on `national.by_type.ry3 && .ry1`, ESTIMATED province split) and `vehicle_mix.json` (`cb-mix`, gates on `national.stock && .new && types.length`, MEASURED). · against the committed tree (probe validator + `DATA_FILES` entry in `pipeline/check_site_health.py`)._

_Audit run: 2026-08-03 (b) · finding: with the data room otherwise clean this run — **0 broken data references** (all 3 `data/*`-shaped hits in `app.js` on a fresh scan resolve to `source-data/…` in comments, not missing SPA fetches), **0 surfaced layers >180d stale** (oldest ISO-dated `vehicle_collateral.json`/`ev_penetration.json` at 156d), and the **live master production alias HTTP 200** on `/`, `/data/meta.json` AND `/data/deltas.json` — a render-path re-scan of the FRONT-DOOR (#home) reads found the **last surfaced command-center read with no deploy probe**: `deltas.json` (the TIME dimension, obj #1 — which segments/branches are getting riskier between vintages). It drives BOTH the command-center "Movers" card (`renderHomeMovers` off `DELTAS.region` + `DELTAS.branches`) AND the whole Risk-trend (#trend) tab (`.board` YoY re-ratings + the region/branch mover rows). Its degradation is MORE insidious than a silent blank: a missing/truncated/404 file drops both surfaces to the CALM string _"Baseline captured — trends appear after the next data refresh"_ — **masquerading a broken deploy as the normal single-vintage baseline state**, hiding real obj-#1 risk movement with no phone alert. `check_site_health.py` now probes it (`_shape_deltas`: fetch + parse + render-shape — asserts the `baseline` gate + a blank-safe `to` vintage label, and when NOT in baseline mode a non-empty `branches` movers list carrying `n/comp`, a non-empty `region` list carrying `r/d_agri`, and the `board` YoY list the #trend tab reads; it stays GREEN in a legitimate single-vintage baseline so it can't false-alarm if the snapshot history is ever reset). Verified: ten tests — the real 80-branch/5-region payload AND a legitimate `baseline:true` file both accepted; eight negatives reject non-dict / missing-`baseline` / blank-`to` / empty-`branches` / branch-missing-`comp` / empty-`region` / region-missing-`d_agri` / non-list-`board` shapes. Offline `--local platform` reports **113/113 HEALTHY** with `deltas.json` served + shape-sane; the live alias serves it **HTTP 200** (16.3 KB). Probe coverage +1 exec check. Determinism gate **121 passed · 0 failed** (data integrity 455/455). No `platform/data` file altered — probe-script-only, so no provenance regen needed. · against the committed tree (probe validator + `DATA_FILES` entry in `pipeline/check_site_health.py`)._

_Audit run: 2026-08-02 (c) · finding: a render-path re-scan of the recently-landed **#258/#261 macro/collateral wave** found several new SPA-fetched layers still with **no deploy site-health probe** — `collateral_book`, `macro_book`, `farm_book`, `used_vehicle_value`, `vehicle_models`/`vehicle_brands`/`vehicle_mix`, `flood_hazard`, `thai_price_history` are all live-`fetch()`'d in `app.js`/`index.html` yet unprobed. The highest-value of them is **`collateral_book.json`** — the Overview/Macro tab's **section-leading collateral read** (obj #1): `renderCollateralBook` GATES the whole "Collateral value — what the titles are worth, and what we hold against them" section on `j.national && j.types` (else `host.style.display='none'`), and the load-bearing verdict sentence reads `N.os / N.core_share_pct / N.ltv_proxy_pct / N.ticket / N.eval_avg` plus the 8-row collateral-type table. MEASURED (real loan tape × DLT registrations); it live-degrades SILENTLY (a missing/truncated file just hides the primary obj-#1 collateral-value screen with no phone alert). `check_site_health.py` now probes it (`_shape_collateral_book`: fetch + parse + render-shape — asserts the display gate `national` KPI block with numeric `os/ltv_proxy_pct/ticket/eval_avg/core_share_pct` AND a non-empty `types` table whose rows carry `type/tier/os_share_pct` — shape not values, robust to a future tape/DLT vintage refresh). Verified: eight negative tests reject non-dict / missing-`national` / non-numeric-KPI / missing-or-empty-`types` / missing-`type` / missing-`tier` shapes while accepting the real payload; the offline `--local platform` path and the **live master production alias** both report **98/98 HEALTHY** with `collateral_book.json` served HTTP 200 (632 KB) and shape-sane. Probe coverage 97 → **98** exec checks. The rest of the data room re-confirmed clean this run: provenance `--check`-reproducible (**135 layers · 0 blank-vintage · 0 unlabelled**); live alias HTTP 200 on `/`, `/app.js`, `/data/meta.json`, `/data/branches.json`, `/data/competitor_coverage.json`; `site-health.yml` correctly targets the master production alias. Next probe targets: the sibling wave reads `macro_book` (`renderMacroBook` gates on `.national && .provinces`) and `farm_book` / `flood_hazard`. · against `platform/data/provenance.json` (**135 layers** · 0 unlabelled)._

_Audit run: 2026-08-02 (b) · finding: the live site-health probe covered 27 of the ~88 SPA-fetched `data/*.json` layers, and a full render-path re-scan this run found **two surfaced exec reads still with no deploy probe**, both live-degrading SILENTLY when their file is missing/truncated (no phone alert): (1) `contested_pop.json` — the command-center (#home) "MOST CONTESTED GROUND" front-door lead (`renderHomeWhitespace` reads `CPOP.top`) PLUS the National-map contested lens (index-aligned `.rows[i]=[pop10, contested_pop]`, obj #2); (2) `exit_whitespace.json` — the Competition (#acq) rival-fragility board under the Q1-2026 BoT registration deadline (`drawExitWhitespace` reads `.districts` + `meta.competitor_census`, obj #2, ESTIMATED), the last surfaced #acq competitive read with no probe. `check_site_health.py` now probes both (fetch + parse + render-shape: `contested_pop` asserts the `.top` leaderboard shape AND the exact 2015 index-aligned `.rows` length that a truncated build would silently misalign; `exit_whitespace` asserts a non-empty ~928-amphoe `.districts` board carrying the sort key + component split + the meta census block the readout headline reads — shape not values, robust to census growth). Verified: negative tests reject empty/short/mis-aligned shapes; the offline `--local platform` path and the **live master production alias** both report **95/95 HEALTHY** with both new files served HTTP 200 and shape-sane. The rest of the data room re-confirmed clean this run: provenance `--check`-reproducible (**130 layers · 435 files · 70 measured · 60 estimated · 0 unlabelled**); **0 broken data references** across 124 distinct `data/*.json` fetch refs; **0 genuine orphan signal layers** (the 3 non-geometry unreferenced files are legitimate build inputs / a retired stub); live alias HTTP 200 on `/`, `/app.js`, `/data/meta.json`, `/data/branches.json`, `/status_data.json`. Probe coverage 27 → **29** exec layers. · against `platform/data/provenance.json` (**130 layers · 435 files** · 70 measured · 60 estimated · 0 unlabelled)._

_Prior audit run: 2026-08-02 (a) · finding: the #248 macro/agri data wave landed three MEASURED, live-fetched survey/registry layers — `debt_source` (NSO household debt-by-source), `vehicle_fleet` (DLT registered-vehicle stock) and `farm_household` (OAE farm-household cash P&L) — that each stamp their freshness ONLY under a layer-specific key the extractor did not scan (`latest_year_ce` as an **integer** calendar year on the first two, `span` as a BE crop-year window on the third), so all three showed **blank** in the exec Data-room card despite carrying a real measured data-vintage. `_vintage_of()` now scans `latest_year_ce` (with int→str coercion) and `span`, placed LAST so any proper ISO/observation key still wins; `_parse_vintage` leaves each age-blank (a bare year / BE label is never coerced into a false age), exactly like the `vintage_individual='2025'` precedent. Verified the regenerated ledger changes **only these three** vintage cells (`'' → 2023`, `'' → 2025`, `'' → 2562/63..2566/67`) — counts (68 measured · 59 estimated · 0 unlabelled), labels, sources, files, and the freshness block (n_dated 24 / n_undated 103, correct — coarse labels are not ISO-dated) are byte-identical, and `build_provenance.py --check` reproduces exactly. `crop_mix` (the fourth new layer) correctly stays vintage-blank — it is a first-order DERIVED layer inheriting freshness from its measured inputs, the honest ABSENT state. Gate 113 passed · 0 failed, data integrity 448/448. · against `platform/data/provenance.json` (**127 layers · 432 files** · 68 measured · 59 estimated · 0 unlabelled)._

_Prior audit run: 2026-07-31 · finding: the live site-health probe's `_shape_competitor_coverage` validator asserted `.brands` + `meta.totals.found` but **not** `meta.national_standing` — the exec headline peer claim ("AutoX runs the 2nd-largest title-loan branch network"), which `drawCompCoverage` gates the whole readout on (`ns.autox_rank` + `ns.ranking`). A truncated deploy that dropped that block would silently vanish the headline with no phone alert; the probe now asserts it (shape, not counts). This run's fresh scan re-confirmed the rest of the data room is clean: provenance **118 layers · 60 measured · 58 estimated · 0 unlabelled** (`--check`-reproducible); freshness — 0 genuine dropped data-vintages across all 84 undated layers (the 7 date-shaped candidates are all the accepted pull-stamp / methodology-param blank set); **0 broken references** across 103 distinct `data/*.json` fetch refs; live master alias HTTP 200; determinism gate 100 passed · 0 failed. · against `platform/data/provenance.json` (**118 layers · 423 files** · 60 measured · 58 estimated · 0 unlabelled)._

_Prior audit run: 2026-07-30 · finding: `scenarios.json` (the LIVE/stress scenario engine, #sim) stamps its freshness only under `board_vintage` (= `2026M06`, the commodity/macro board month its MEASURED live drivers observe), which the extractor did not scan — so it showed **blank** in the exec Data-room card despite carrying a real measured vintage; the extractor now scans `board_vintage` and the cell surfaces (§1) · against `platform/data/provenance.json` (**115 layers · 420 files** · 57 measured · 58 estimated · 0 unlabelled — `build_provenance.py --check` reproduces exactly)._

_Prior audit run: 2026-07-28 · finding: the R2 catchment migration left **~2.2 GB of R2-duplicated building catchments committed to git** — the deployed data-room is **10× the size §4 last recorded** (§4, corrected that run) · against `platform/data/provenance.json` (114 layers · 419 files · 57 measured · 57 estimated · 0 unlabelled)._

**Deployment health (verified live this run, 2026-07-28):** the master production alias
(`competitive-intel-git-master-kaustav-bagchis-projects.vercel.app`) serves **HTTP 200** on `/`,
`/app.js`, `/status`, and the key data layers (`branches.json`, `meta.json`, `peer_province.json`,
`competitor_coverage.json`). Determinism gate **96 passed · 0 failed**; data integrity **446/446**;
all **77/77** province catchments present; **0** broken data references. No regression.

## Headline

The data room is healthy. **No broken data references, no missing fetches; provenance intact
(52 measured · 51 estimated · the single standing catchment family).** The one concrete gap this
run **fixed**: `peer_scoreboard.json` — the MEASURED SET listed-peer market scoreboard (obj #2, the
sharpest external competitive benchmark AutoX has) — stamps its real freshness date under the key
`price_asof` (`= 2026-07-17`, the SET price-observation date), which `build_provenance.py::_vintage_of()`
did not scan, so its vintage showed **blank** in the exec-facing Data-room card. Exactly the same
class of bug as the 2026-07-17 (6 keys), 2026-07-19 (3 keys) and 2026-07-24-am (`snapshot`) §1 fixes;
a full re-scan of every committed analytical layer's `meta` this run found `price_asof` to be the one
remaining **data-vintage** key still unscanned — so the extractor now scans it and the scoreboard
vintage surfaces like the rest. (Four other blank-vintage layers — `amphoe_crops`, `crop_margin`,
`region_debt`, `rival_universe` — carry only a **pull/verify** stamp, `retrieved` / `cost_ingested` /
`verified`, which the standing convention deliberately deprioritizes vs a data-observation vintage
[see the 2026-07-24-am note below], so their blank cells are the accepted honest ABSENT state, not a
bug.)

**Verified this run — the SET scoreboard cannot auto-refresh (a structural staleness, not a gap to
fix with a CI job):** every other live-pull layer family in the repo now has a scheduled `data-*.yml`
refresh job (the ThaiWater omission was closed 2026-07-24). The listed-peer scoreboard is the last
family **without** one — but unlike ThaiWater it is **genuinely blocked from CI**: `set.or.th`'s API
403s every external request (Akamai bot-protection) and even a headless-browser same-origin fetch from
this datacenter sandbox got `ERR_CONNECTION_RESET` (verified this run). So SET belongs with the
competitor corporate sites in the **owner-side / Thai-IP-only** refresh set, not the CI-refreshable
set — building a `data-set.yml` job would build a job that cannot pull. Surfacing the layer's own
`price_asof` observation date (this fix) is therefore exactly how the exec sees how current the
scoreboard is; a future refresh is owner-side (`pull_set_peers.py` from a browser that clears Akamai).

_Tree grew 96 → 104 layers since the last audit (drought_district, crop_drought, the two thaiwater
live-pulse layers, set/valuation and credit-anchor market layers, …). Re-verified this run: the
ledger reports 104 layers (52 measured · 51 estimated · 1 unlabelled = the standing 3D building-
catchment family, 77 files under one `family:true` row — structurally meta-less, an accepted standing
state, not a regression); every analytical layer is wired into a live `fetch()` or is a pipeline
input; and no `data/*.json` path referenced in `platform/*.html` + `app.js` fails to resolve._

## 1. Freshness per layer (the fix this run shipped)

**2026-08-02 (this run):** a full re-scan of every currently blank-vintage labelled layer's `meta`
for date-shaped keys *outside* the extractor's list found **three** MEASURED, live-fetched layers
(all new since the last audit, from the #248 macro/agri wave) still dropping a real **data-vintage**
from the Data-room card:

| Layer | Freshness key (was dropped) | Value now surfaced | Class |
|---|---|---|---|
| `debt_source.json` | `latest_year_ce` (int) | 2023 | MEASURED — NSO household debt-by-source survey, newest wave year |
| `vehicle_fleet.json` | `latest_year_ce` (int) | 2025 | MEASURED — DLT registered-vehicle stock, newest registry year |
| `farm_household.json` | `span` (BE crop-years) | 2562/63..2566/67 | MEASURED — OAE farm-household cash P&L survey, observation window |

`_vintage_of()` now also scans `latest_year_ce` (with int→str coercion — it is a bare calendar year,
not a date string, exactly the `vintage_individual` NSO-year precedent, just stored as an int) and
`span`, both placed **last** in the priority list (coarse, non-ISO labels — any proper ISO/observation
key still wins). `_parse_vintage` leaves all three age-blank, so the freshness pulse never coerces a
bare year or a BE crop-year window into a false age; the row's vintage cell simply surfaces the layer's
own committed label. A diff of the regenerated ledger confirms the change touches **only these three
vintage cells** — the 127-layer counts (68 measured · 59 estimated · 0 unlabelled), labels, sources,
the files block, and the freshness block (n_dated 24 / n_undated 103) are byte-identical, and
`build_provenance.py --check` passes on the recommitted ledger. No date is invented — each value is
read from the layer's own committed `meta`. `crop_mix.json` (the fourth new layer this wave) correctly
stays vintage-blank: it is a first-order DERIVED layer (province area × Thai farm-gate YoY × NSO
income) whose freshness is inherited from its measured inputs, so its blank cell is the honest ABSENT
state, not a bug.

---

**2026-07-30 (prior run):** live deployment re-verified green — the master production alias
(`competitive-intel-git-master-kaustav-bagchis-projects.vercel.app`) serves **HTTP 200** on `/`,
`/app.js`, `/data/branches.json`, `/data/meta.json`; the `site-health.yml` cron correctly targets that
alias. Determinism gate **96 passed · 0 failed**, data integrity **446/446**, provenance
`--check`-reproducible, **0** broken data references (the three unresolved `data/*.json` strings are a
code-comment path and two substring artifacts of `source-data/*`, none a live `fetch()`). A full
re-scan of every blank-vintage labelled layer's `meta` for date-shaped keys *outside* the extractor's
list found **one** layer still dropping a real **data-vintage** from the Data-room card:

| Layer | Freshness key (was dropped) | Value now surfaced | Class |
|---|---|---|---|
| `scenarios.json` | `board_vintage` | 2026M06 | MEASURED commodity/macro board month the LIVE scenarios observe (#sim scenario engine) |

`_vintage_of()` now also scans `board_vintage`, placed among the data-observation vintages (right
after `farmgate_vintage`, ahead of any pull timestamp — it is the board month the scenario engine's
own label commits to showing per card, a MEASURED data-vintage exactly like `price_vintage` /
`farmgate_vintage`, not a pull time). scenarios.json is fetched live (`app.js` `tmliFetch('scenarios')`,
rendered in `#sim`) so it appears in the exec Data-room card; it stamps freshness *only* under this
key, so without it the row showed **blank** despite a real measured vintage. Verified the change
touches **only this one** vintage cell (`'' → 2026M06`); a diff of the regenerated ledger confirms
every other field — the 115-layer counts (57 measured · 58 estimated · 0 unlabelled), labels, sources,
the files block — is byte-identical, and `build_provenance.py --check` passes on the recommitted
ledger. No date is invented — `2026M06` is read from the layer's own committed `meta.board_vintage`.
The standing accepted-blank set held: `amphoe_crops` (`retrieved`), `crop_margin` (`cost_ingested`),
`region_debt` (`retrieved`), `rival_universe` (`verified`) carry only a **pull/verify** stamp (the
convention deprioritizes those vs a data-observation vintage), and `tape_real`/`tape_geo_occ`'s
`mob_anchor` is a months-on-book methodology parameter, not a freshness date — so their blank cells
are the honest ABSENT state, not a bug. `board_vintage` was the one genuine dropped data-vintage.

---

**2026-07-25:** the tree grew 104 → **109 layers** (414 files) since the prior audit (new
market layers landed: `commodities`, `dbd_formation`, `credit_anchor`, `peer_npl`, `napprang`,
`vehicle_registry`, `province_lfs`, `nso_wage_anchor`, …). A full re-scan of every currently
blank-vintage labelled layer's `meta` for date-shaped freshness fields *not* in the extractor's key
list found **one** layer still dropping a real **data-vintage** from the Data-room card:

| Layer | Freshness key (was dropped) | Value now surfaced | Class |
|---|---|---|---|
| `commodities.json` | `farmgate_vintage` | 2026-07-24 | MEASURED Thai farm-gate price observation date (global Pink Sheet × Thai farm-gate × book-exposure board) |

`_vintage_of()` now also scans `farmgate_vintage`, placed among the data-vintage keys (right after
`price_asof`, ahead of any pull timestamp — it is the Thai farm-gate price *observation* date, a
MEASURED data-vintage exactly like `price_vintage` / `price_asof`, not a pull time). The commodities
board carries only this price date plus a divergence note in its `meta`, so without it the exec's
Data-room card showed the layer **blank** despite a fresh measured farm-gate vintage. Verified the
change touches **only this one** vintage cell (`'' → 2026-07-24`); a diff of the regenerated ledger
confirms every other field — the 109-layer counts (52 measured · 57 estimated · 0 unlabelled),
labels, sources, the files block — is byte-identical, and `build_provenance.py --check` passes on the
recommitted ledger. No date is invented — `2026-07-24` is read from the layer's own committed
`meta.farmgate_vintage`.

The same re-scan re-confirmed the standing accepted-blank set: `amphoe_crops` (`retrieved`),
`crop_margin` (`cost_ingested`), `region_debt` (`retrieved`) and `rival_universe` (`verified`) carry
only a **pull/verify** stamp, which the convention deliberately deprioritizes vs a data-observation
vintage, so their blank cells are the honest ABSENT state, not a bug; `brand_trends.note_be_to_ce`
is a BE→CE explainer note, not a vintage; `tape_real.mob_anchor` is a months-on-book methodology
parameter, not a freshness date. `commodities.farmgate_vintage` was the one genuine dropped
data-vintage this run.

**Freshest reachable inputs today** (read from the regenerated ledger): thaiwater flood/rain
2026-07-25 05:20/05:00, commodities farm-gate 2026-07-24, fuel prices 2026-07-22, macro indicators
2026-07-20, rival-pulse promo watch 2026-07-19, credit anchor 2026-07-18, SET peer scoreboard
2026-07-17. No stale live-input layer detected.

---

**2026-07-24 (pm, prior run):** a full re-scan of all analytical layers' `meta` blocks for date-shaped
freshness fields *not* in the extractor's key list found **one** layer still dropping a real
**data-vintage** from the Data-room card:

| Layer | Freshness key (was dropped) | Value now surfaced | Class |
|---|---|---|---|
| `peer_scoreboard.json` | `price_asof` | 2026-07-17 | MEASURED SET listed-peer market scoreboard (obj #2) |

`_vintage_of()` now also scans `price_asof`, placed among the data-vintage keys (right after
`price_vintage`, ahead of any pull timestamp — `price_asof` is the SET market-price observation date,
a data-observation vintage exactly like `observed_to` / `price_vintage`, not a pull time). Verified
the change touches **only this one** vintage cell (`'' → 2026-07-17`); a diff of the regenerated
ledger confirms every other field — the 104-layer counts (52 measured · 51 estimated · 1 unlabelled),
labels, sources, the files block — is byte-identical, and `build_provenance.py --check` passes on the
recommitted ledger. **Headless render self-review** of `index.html#home` (`data-errors:[]`, 0 JS
errors) shows the Data-room `peer_scoreboard.json` row now reads `2026-07-17 · 2 KB` (was blank). No
date is invented — `2026-07-17` is read from the layer's own committed `meta.price_asof`.

---

**2026-07-24 (am, prior run):** a full re-scan of all 104 layers' `meta` blocks for date-shaped
freshness fields *not* in the extractor's key list found **one** layer still dropping a real vintage
from the Data-room card:

| Layer | Freshness key (was dropped) | Value now surfaced | Class |
|---|---|---|---|
| `drought_district.json` | `snapshot` | 2026-06 | MODELLED OAE-SPEI per-amphoe drought (freshly surfaced, #141) |

`_vintage_of()` now also scans `snapshot`, placed among the data-vintage keys (after `price_vintage`,
ahead of any pull timestamp — `snapshot` is the SPEI reference month, a data vintage, not a pull
time; the layer's own `retrieved: 2026-07-20` pull date is intentionally **not** surfaced as the
freshness cell, matching how `observed_to` / `price_vintage` prefer the observation window over the
pull stamp). Verified the change touches **only this one** vintage cell (`'' → 2026-06`); a diff of
the regenerated ledger confirms every other field — counts, labels, sources, the files block — is
byte-identical, and `build_provenance.py --check` passes on the recommitted ledger. No date is
invented — `2026-06` is read from the layer's own committed `meta.snapshot`.

---

**2026-07-19 (prior run):** a full re-scan of all 96 layers' `meta` blocks for date-shaped freshness
fields *not* in the extractor's key list found **three** layers still dropping a real vintage from
the Data-room card:

| Layer | Freshness key (was dropped) | Value now surfaced | Class |
|---|---|---|---|
| `rival_pulse.json` | `promos_pulled_at` | 2026-07-19 | live rival promo/sentiment watch (freshest) |
| `pico_competitors.json` | `pico_vintage` | 2026-05-22 | FPO PICO-finance licence registry |
| `occupation_income_individual.json` | `vintage_individual` | 2025 | NSO LFS individual-income |

`_vintage_of()` now also scans `pico_vintage, vintage_individual, promos_pulled_at`. Verified the
change touches **only these three** vintage cells (`build_provenance.py --check` byte-exact; a diff
of the regenerated ledger confirms counts/labels/sources unchanged). No date is invented — each is
read from the layer's own committed `meta`. `rival_reputation.json` / `rival_threat.json` carry an
explicit `vintage: null` and correctly stay blank (no rating vintage was captured).

---

**2026-07-17 (prior run):** `_vintage_of()` previously scanned only `updated / vintage / as_of /
updated_to`. Six layers stamp their freshness under **other** real keys and were therefore showing
blank in the Data-room card despite carrying a date:

| Layer | Freshness key (was dropped) | Value now surfaced |
|---|---|---|
| `thaiwater_flood.json` | `observed_to` | 2026-07-11 08:40 |
| `thaiwater_rain.json` | `observed_to` | 2026-07-10 02:00 |
| `search_demand.json` | `pulled_at_utc` | 2026-07-04T00:45Z |
| `fuel_prices.json` | `pulled` | 2026-07-05 |
| `macro_indicators.json` | `pulled` | 2026-07-05 |
| `macro_sensitivity.json` | `price_vintage` | 2026M06 |

Extraction now scans (in priority order): `updated, vintage, as_of, updated_to, observed_to,
price_vintage, pico_vintage, vintage_individual, pulled_at_utc, pulled, promos_pulled_at`. A note
field that merely mentions a year
(`brand_trends.json::note_be_to_ce = "พ.ศ. − 543 = ค.ศ. …"`) is correctly **not** treated as a
vintage — the extractor keys off known freshness fields, not any date-shaped string.

Result: **23 of 96** layers now carry a captured vintage (was 20 before this run's three-key fix;
11 of 78 after the 2026-07-17 fix). The remaining 73 are derived/geometry layers whose freshness is
inherited from their inputs (no independent vintage); their vintage-blank state is honest, not a bug.

**Freshest reachable inputs today** (all measured except the rival watch, all recent): rival-pulse
promo pull 2026-07-19, credit anchor 2026-07-18, fuel prices 2026-07-17, thaiwater flood 2026-07-11,
thaiwater rain 2026-07-10, search demand 2026-07-04. No stale live-input layer detected.

## 2. Provenance coverage

- **115 layers · 420 files** (as of 2026-07-30). 57 measured · 58 estimated · **0 unlabelled** — the shame board is **clear**; `build_provenance.py --check` reproduces the ledger byte-for-byte. _(The narrative below records the 2026-07-17 run that first cleared the board at 83 layers · 314 files; the mechanism has held the board at 0 unlabelled through every layer added since — the tree has grown 83 → 114 layers with no regression.)_
- **Update 2026-07-17 (a), intelligence loop:** the board was **cut 6 → 2**. Four structural layers
  gained an honest self-declared `meta` stamp at the generator so they stay `--check`-reproducible:
  `meta.json` (`derive.py::build_meta` — MIXED, classifies ESTIMATED), `deltas.json` +
  `snapshots_index.json` (`timeseries.py::targets`), and the orphaned curated pilot aggregate
  `rayong_province.json` (hand-stamped — verified **no live `fetch()`**).
- **Update 2026-07-17 (b), intelligence loop — the sidecar mechanism (this run):** the last **2**
  unlabelled files — `branches.json` and `provinces/index.json` — are **top-level JSON arrays** that
  structurally cannot carry an inline `meta` block. `build_provenance.py` now consults a hand-authored
  **sidecar manifest** (`platform/data/provenance_sidecar.json`, keyed by relpath) for exactly those
  array-shaped layers, supplying the same `label/source/provenance` an inline block would. `branches.json`
  → **ESTIMATED** (MIXED: measured location/context + derived segment scores), inheriting meta.json's
  live vintage via a `vintage_from` key; `provinces/index.json` → **MEASURED** (a directory/index with
  measured rollups). The sidecar carries **provenance text only — zero data, zero numbers**; a file is
  upgraded only when an honest committed entry names it. **Shame board 2 → 0.** Honest by mechanism, not
  by fabrication — the board reports 314/314 labelled.

## 3. Broken data references — NONE

Cross-checked every `data/*.json` path referenced in `platform/*.html` + `app.js` (66 distinct)
against the committed tree. The only two that don't resolve —`perimeter_counts.json`,
`rayong_trees.json` — appear **exclusively in code comments** (describing a source path and an
optional scenery layer), never in a live `fetch()`. No functional break. The optional per-city
scenery layers (trees/rail/isochrone) are already allowlist-gated (`SCENERY_CITIES`, empty today)
so they issue no 404s — see PROGRESS_LOG 2026-07-12 (ux-loop).

## 4. Heavy-JSON load weight

**Corrected 2026-07-28 (was badly stale — the old figure read "242 MB across 309 files"):** the
git-tracked `platform/data` tree is now **2.5 GB across 497 JSON files**, overwhelmingly the 3D
building catchments — **77 `*_catchment.json` files totalling 2.28 GB** (avg **30.3 MB** each). The
five heaviest, all catchments, all lazy:

| File | Size | Load path |
|---|---|---|
| `chon-buri_catchment.json` | 34.6 MB | lazy — only on `rayong-catchment.html?city=chon-buri` |
| `chachoengsao_catchment.json` | 33.6 MB | lazy — only on that province's 3D scene |
| `saraburi_catchment.json` | 33.1 MB | lazy — only on that province's 3D scene |
| `khon-kaen_catchment.json` | 32.9 MB | lazy — only on that province's 3D scene |
| `rayong_catchment.json` | 32.6 MB | lazy — the Rayong pilot scene |

None load on the SPA's default routes — each is fetched only when its own heavy WebGL scene opens
(the deliberate one-route-per-GL-context split, CLAUDE.md), so command-center / overview / map stay
light. **Not a runtime regression.**

**Concrete finding this run — the R2 catchment migration is half-done, leaving ~2.2 GB redundantly
committed.** `catchments_r2.json` states the design plainly: _"Every province's `<slug>_catchment.json`
is served (R2, with the 3 pilot provinces also in git). The 3D scene fetches local-first then R2."_
The manifest lists only **3 provinces** as intended-git (`bangkok`, `chiang-mai`, `rayong`) with the
other **74 meant to be R2-only** — but on disk **all 77 catchments are still git-tracked** (2.28 GB).
So the repo and the Vercel deploy carry ~**2.2 GB of catchment data that R2 already serves**. Verified
live this run: R2 returns **HTTP 200** for the non-pilot catchments spot-checked
(`chon-buri`, `khon-kaen`, `roi-et`, `amnat-charoen`), and the scene's documented local-first→R2
fallback means removing the 74 git copies would shrink the repo/deploy by ~2.2 GB while scenes fall
back to the (verified-live) R2 objects. This is the biggest available deploy-weight win by far.

## Next service task (recommended)

**Done 2026-07-17 (b)** — the sidecar mechanism shipped (see §2): `build_provenance.py` now reads
`provenance_sidecar.json` for the two array-shaped layers, taking the board **2 → 0 / 314 files
100 % labelled**. Provenance coverage is now complete and self-sustaining (any future array-shaped
layer just adds a sidecar entry).

The next standing service target is now **§4's confirmed finding: finish the R2 catchment
migration** — untrack the **74 non-pilot `*_catchment.json` files (~2.2 GB)** that R2 already serves,
keeping only the 3 pilots (`bangkok`, `chiang-mai`, `rayong`) in git. Evidence is in place: R2 returns
200 for the non-pilot catchments (verified this run) and the scene fetches local-first→R2, so the
fallback is already wired. **This intelligence loop deliberately did NOT execute the removal** — a
~2.2 GB `git rm` changes the data source of 74 3D scenes (git → R2) and is an architecturally
significant, owner-reviewable change, not a small autonomous edit (and the owner is currently driving
the repo manually — see the 2026-07-28 cron-pause commit). Recommended owner-side action: `git rm`
the 74 R2-served catchments, keep `catchments_r2.json` + the 3 pilots, and headless-render two
non-pilot 3D scenes to confirm the R2 fallback renders before merging.

Aside from that one weight item, the data room is healthy: provenance 114/114 labelled and
`--check`-reproducible, 0 broken references, 77/77 catchments reachable, and the live deployment
green (see the deployment-health note under **Headline**).
