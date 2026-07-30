# SERVICE AUDIT — AutoX / เงินไชโย Credit-Intelligence Platform

> Emitted by the autonomous **market & service intelligence** loop. Audits the platform *as a
> service*: data freshness per layer, provenance coverage, broken data references, and heavy-JSON
> load weight. Every number here is read from the committed tree — nothing is estimated or invented.
> Regenerate the underlying ledger with `python3 pipeline/build_provenance.py`.

_Audit run: 2026-07-30 · latest finding: `scenarios.json` (the LIVE/stress scenario engine, #sim) stamps its freshness only under `board_vintage` (= `2026M06`, the commodity/macro board month its MEASURED live drivers observe), which the extractor did not scan — so it showed **blank** in the exec Data-room card despite carrying a real measured vintage; the extractor now scans `board_vintage` and the cell surfaces (§1) · against `platform/data/provenance.json` (**115 layers · 420 files** · 57 measured · 58 estimated · 0 unlabelled — `build_provenance.py --check` reproduces exactly)._

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

**2026-07-30 (this run):** live deployment re-verified green — the master production alias
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
