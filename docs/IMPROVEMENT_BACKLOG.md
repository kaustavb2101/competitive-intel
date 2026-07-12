# IMPROVEMENT BACKLOG — the standing continuous-improvement loop

> This file is the queue for the **standing improvement loop** (a scheduled trigger that fires a
> fresh session every 4 hours). Each cycle: read this file → pick the single highest-value
> **UNBLOCKED, sandbox-safe** item → build it small + graceful → `bash tests/run.sh check` must pass
> → commit/push to `claude/new-session-wto26j` → log to `PROGRESS_LOG.md` → check the item off here and
> add 1–3 new ideas (self-enriching). One substantive improvement per cycle.

## Queue — follow-ups noticed 2026-07-12 (3) — AUDIT: DATA_SOURCES.md reachability matrix backfill
- [ ] **Before picking a "stale UX gap" item from this backlog, spot-check it against the live app
      first** (repeats the lesson already logged 2026-07-05 (7)/2026-07-04 (9) for stale `[ ]` UX
      entries specifically — this cycle found the SAME staleness class in a docs-audit-flavored entry,
      "provenance.json has no rendered surface," which was already false). A `grep -n "renderHomeDataRoom\|cc-dataroom"
      platform/app.js platform/index.html`-style check (or `git log -S"<claimed-missing-thing>"`) before
      starting implementation would have caught this in one command instead of a partial build +
      revert. Worth folding into the general "spot-check before building" backlog hygiene note rather
      than a one-off. *(LOW, trivial, process note)*
- [ ] **`docs/DATA_SOURCES.md`'s reachability matrix now covers every host actually hit by
      `pipeline/*.py`/`committee/*.py`, EXCEPT the Google Places API** (`maps.googleapis.com`, used by
      `pull_competitors.py`/`pull_google_places.py`) — the matrix's existing Google Places row cites
      "(places_search tool)" rather than the actual REST host the pipeline scripts call directly. Not
      wrong, just a slightly different framing (tool-call vs. raw HTTP) that a future pass could
      reconcile into one row. *(LOW, trivial, informational)*
- [ ] **The isochrone puller (`pull_isochrone.py`) has never been run — reachability of
      `api.openrouteservice.org`/`api.sphere.gistda.or.th` from this sandbox is genuinely unknown**,
      not just key-gated. If a future cycle gets a free-tier `ORS_KEY` (signup link is in the script's
      own docstring, no payment needed) it could resolve this to a real ✅/❌ instead of ⚠ UNTESTED —
      would unblock replacing the catchment's walk-radius estimate with a true isochrone (NEXT_STEPS.md
      item 4). Needs a human to obtain the key first; not sandbox-actionable on its own. *(MED, S, needs
      a human for the key)*

## Queue — follow-ups noticed 2026-07-12 — AUDIT: provenance.json census pointer
- [x] **`docs/DATA_PROVENANCE.md` §1's hand-written table backfill for the two-objectives-relevant set —
      DONE 2026-07-12 (2)** (added 4 rows — `branch_peers.json`, `branch_density.json`,
      `exit_whitespace.json`, `expansion_plan.json` — after reading each file's actual `meta` block
      directly; all four already carried strong in-file provenance/label/method stamps, so this is a
      docs-only "curated tour" backfill, not a provenance fix. `agri_income_by_province.json`/
      `fuel_prices.json`/`thaiwater_*.json` and ~30 others remain un-backfilled in this markdown table
      (still real + gated via `provenance.json`) — see the new follow-up below).
- [ ] **`docs/DATA_PROVENANCE.md` §1 still doesn't mention `agri_income_by_province.json`/
      `fuel_prices.json`/`thaiwater_*.json` and ~30 other now-shipped layers** (all of which DO carry
      real in-file `meta` and DO pass the gate — this is a "curated tour is incomplete" gap, not a
      "provenance is missing" gap, since `provenance.json`/the gate already cover everything). A future
      cycle could continue the file-by-file backfill (2026-07-12 (2) closed the top-4) or restructure §1
      to link out to each builder's own `meta` block instead of duplicating it in markdown. *(LOW-MED, M
      — lower-stakes now that the two-objectives-relevant set is documented and the gate is the real
      safety net)*
- [x] **`pipeline/build_provenance.py`'s `provenance.json` output — STALE, ALREADY SHIPPED, found
      2026-07-12 (3).** This entry was wrong: `renderHomeDataRoom()`/`#cc-dataroom-body` on the Home
      tab already renders exactly this (headline measured/estimated/unlabelled counts + a full
      per-layer table, framed positively), from a commit that landed before this entry was last
      touched. Discovered mid-build-attempt this cycle — reverted the in-progress duplicate
      (`git checkout --` on the 2 touched files) rather than ship a second copy. No code changed;
      checked off rather than re-built. See `docs/PROGRESS_LOG.md` 2026-07-12 (3) entry.
- [x] **`docs/DATA_SOURCES.md`'s reachability matrix re-verified end-to-end against every puller's
      actual request host — DONE 2026-07-12 (3)** (grepped every `pipeline/*.py`/`committee/*.py` for
      its literal request URL, diffed against the matrix table: no row was actively wrong this pass,
      but NABC/BIS/ThaiWater/ILOSTAT — all real, already-pulled REACHABLE sources, 2 of them named in
      CLAUDE.md's own REACHABLE bullet — had no row at all. Added 4 rows + a 5th distinguishing the
      ORS/GISTDA isochrone puller as ⚠ UNTESTED [no vendored key, never run] rather than ❌ BLOCKED
      [tried, failed]. Docs-only, gate reconfirmed 66/0 unchanged. Full writeup: `docs/PROGRESS_LOG.md`
      2026-07-12 (3) entry).

## Queue — follow-ups noticed 2026-07-11 (9) — ENRICH: truck_flow.json caution strip on #acq
- [ ] **The new `#acq` truck-watch strip and `#trend`'s full table both hardcode "worst 5"/"worst
      10"** off the same `TRUCKFLOW.provinces` sort — no shared constant/helper, just two
      independent `.slice(0,N)` calls in two render functions. Not a real duplication problem yet
      (the two views intentionally render at different granularity — strip vs table), but if a 3rd
      truck-flow surfacing point is ever added, worth extracting a `worstTruckFlow(n)` accessor
      instead of a 3rd copy of the sort. *(LOW, trivial, speculative)*
- [ ] **`#acq`'s new truck-watch strip only cross-links to `#trend`'s table one-way** — `#trend`'s
      truck section has no reciprocal "see the expansion-caution read on #acq" link. Minor, since
      `#trend` is the canonical/fuller view and `#acq` is the derived caution strip, but a 2-line
      addition if a future polish pass wants symmetric cross-nav between the risk and acquisition
      tabs. *(LOW, trivial, cosmetic)*
- [ ] **`truck_flow.json` is now surfaced in 3 places** (Overview pulse card, `#trend` full table,
      `#acq` caution strip) but still has no lens on the National map — unlike `hhdti`/`unemp`/
      `pstress`, it can't paint a branch-dot lens (it's province-only, not per-branch or per-amphoe),
      so this isn't a real gap, just worth noting the layer's now fully wired everywhere it
      structurally can be. *(LOW, trivial, informational — closes the truck_flow.json surfacing arc)*

## Queue — follow-ups noticed 2026-07-11 (8) — AUDIT: source-register doc backfill
- [x] **`docs/DATA_PROVENANCE.md` §1's own header still said "the ledger now covers all 34 top-level
      `platform/data/*.json` layers" from the 2026-07-01 audit — DONE 2026-07-12** (rather than
      hand-writing ~44 new rows for a 307-file tree — real risk of shipping a stale/inaccurate
      description in the one doc whose job is trustworthy provenance — found `pipeline/
      build_provenance.py` already exists and is already gated in `tests/run.sh`, deterministically
      censusing every layer's own `meta` stamp into `platform/data/provenance.json`. Rewrote the
      header to point there as the live, always-current audit [76 layers: 33 MEASURED/37 ESTIMATED/6
      UNLABELLED] and cross-checked the 6 "unlabelled" files against `validate_data.py`'s
      `PROVENANCE_EXEMPT` set — confirmed an exact match, i.e. every unlabelled file is a reviewed
      exemption, not an undetected gap. Gate 66/0, `validate_data.py` 468/468 unchanged. Full
      writeup: `docs/PROGRESS_LOG.md` 2026-07-12 entry).
- [x] **`docs/DATA_SOURCES.md`'s reachability matrix still lists `DLT (vehicles) | stat.dlt.go.th,
      web.dlt.go.th | ❌ BLOCKED` without noting the CLAUDE.md-documented 2026-07-09 breakthrough —
      DONE 2026-07-12, and turned out worse than "just missing a cross-reference": the same table's
      catch-all row also listed `gdcatalog` itself under still-❌-BLOCKED, directly contradicting the
      verified breakthrough** (split into two rows: the genuinely-still-blocked old `stat.dlt.go.th`
      portal, and a new ✅ row for `gdcatalog.dlt.go.th`/`diw-dataset.diw.go.th` citing the verified
      date + `committee/census.py`/the CI workflow that already uses them + CLAUDE.md/INSIGHTS.md
      cross-references. Gate reconfirmed 66/0 unchanged — docs-only. Full writeup: `docs/
      PROGRESS_LOG.md` 2026-07-12 entry).

## Queue — follow-ups noticed 2026-07-11 (7) — ENRICH: truck_flow.json national-rollup on #trend
- [x] **`truck_flow.json`'s worst-yoy provinces weren't surfaced on `#acq`/`#trend` — DONE
      2026-07-11 (7), closes half of the 2026-07-11 (6) follow-up** (`#trend` gained a
      "Contracting truck fleet · province watch list" audit-first table, same slot/pattern as the
      peer-twin-outlier and siege-table lists — worst-first by `net_flow_12m`, vintage-independent
      since the file carries its own trailing-12mo YoY, self-disabling when absent. นครปฐม leads
      at −703 net flow; 8/77 provinces negative, matching the (6) province.html count. Gate 66/0,
      `validate_data.py` 468/468 unchanged — UI-only. Headless-rendered `index.html#trend`
      1400×4200, `data-errors="[]"`, table + readout confirmed correct, no regression to the
      neighbouring peer/siege sections. Full writeup: `docs/PROGRESS_LOG.md` 2026-07-11 (7) entry).
- [x] **`#acq` still doesn't read `truck_flow.json` — DONE 2026-07-11 (9)** (compact "Truck-fleet
      watch · caution before expanding" strip added to `#acq`'s segment-whitespace section, right
      after "Most-stressed districts" — a short readout (not a table, since the file is province-
      resolution and doesn't join `#acq`'s amphoe tables), naming N/77 provinces + worst 5,
      cross-linking to `#trend`'s full 10-province table. Reuses the already-warmed
      `loadTruckFlow()`/`TRUCKFLOW` global. Gate 66/0, `validate_data.py` 468/468 unchanged —
      UI-only. Headless-rendered `index.html#acq` 1400×5200, `data-errors="[]"`, strip populated
      correctly (8/77 provinces, นครปฐม −703 leading, matching `#trend`'s figures), no regression
      to the neighbouring district-risk table. Full writeup: `docs/PROGRESS_LOG.md` 2026-07-11 (9)
      entry).
- [ ] **The new truck-watch table and the existing peer-twin/siege tables on `#trend` share the same
      "worst-first table + prose readout, self-disabling when absent" shape** (three near-identical
      render functions: `drawTruckTrend`/`drawPeerOutliers`/`drawSiegeTable`) — not yet a problem at
      3 call-sites, but if a 4th vintage-independent audit list is ever added to `#trend`, worth
      factoring a shared `renderAuditList({data, sortFn, rowFn, readoutFn, tblSel, roSel})` helper
      instead of hand-rolling a 4th copy. Same "near-duplicate render function" smell already logged
      for `drawAmphoeChoropleth`/`drawProvinceChoropleth` elsewhere in `app.js`. *(LOW, S, pure
      refactor, speculative until a 4th list lands)*

## Queue — follow-ups noticed 2026-07-11 (5) — VALIDATOR: truck_flow.json shape check
- [ ] **`check_truck_flow()` (new this cycle) only recomputes `net_flow_12m`** (pure arithmetic,
      `new_regis_12m - dereg_12m`) — it does NOT re-verify the count fields themselves against the
      raw DLT `dataset_stat_1_009` mirror (that's `build_truck_flow.py --check`'s job, which only
      runs when the mirror is on disk). If a future cycle wants a source-traceable check that also
      SKIP-passes gracefully, it would need to shell out to `build_truck_flow.py --check` from
      inside `validate_data.py` (no existing check does this — worth confirming that pattern is
      even desirable before adding it, since `tests/run.sh` already gates the byte-exact rebuild
      separately). *(LOW, trivial, informational)*
- [x] **`truck_flow.json`'s worst-yoy provinces weren't surfaced anywhere in the UI — DONE
      2026-07-11 (6)** (`province.html` now fetches the flat `truck_flow.json` alongside its
      other optional layers and `vehicleFlowImpacts()` gained a "Contracting truck fleet" watch
      callout keyed on `net_flow_12m<0` — new_regis trailing permanent deregistrations, a rarer
      and more decisive signal than the raw `new_regis_yoy_pct` sort [8/77 = 10% of provinces,
      vs. 32/77 negative-yoy which is too broad for a "watch" flag]; joined client-side by
      `province_th` name match [confirmed all 77 `provinces/*.json` files match a `truck_flow.json`
      `th` name, zero silent misses], same self-disabling-on-absent pattern as `crop_landuse.json`.
      Verified live logic (province-name join + threshold + message text) via a hand-run Node
      simulation against Chanthaburi [-56 net flow, fires correctly] and Rayong [+378, correctly
      silent] since this page's headless render harness is known-flaky (2026-07-03 (7)/2026-07-05/
      2026-07-10). Gate 66/0, `validate_data.py` 468/468 unchanged — zero `platform/data`/
      `source-data` values touched, UI-only wiring of an already-measured layer. `#acq`/`#trend`
      still don't read this file — a national-rollup surfacing is a separate, larger follow-up if
      wanted. Full writeup: `docs/DATA_REFRESH_LOG.md` 2026-07-11 (6) entry).
- [x] **`build_truck_flow.py` (Sprint 2 E0 (3), `694bb7a`) has no dedicated `validate_data.py`
      shape/sanity check — DONE 2026-07-11 (5)** (new `check_truck_flow()`: meta/provenance,
      non-empty provinces list, counts≥0, `net_flow_12m` recomputed and compared exactly,
      `new_regis_yoy_pct` finite-or-null, known region; SKIP-passes when absent. Since
      `truck_flow.json` isn't province-nested — it's its own flat top-level file — this is a
      standalone shape check rather than a join check like `_check_province_gov_join`. Verified
      it catches real drift via a hand-corrupt-then-restore of `net_flow_12m`. Gate 66/0,
      `validate_data.py` 468/468. Full writeup: `docs/PROGRESS_LOG.md` 2026-07-11 (5) entry).

## Queue — follow-ups noticed 2026-07-11 (4) — AUDIT: Sprint 2 commit-log backfill
- [x] **`docs/DATA_SOURCES.md`/`docs/DATA_PROVENANCE.md` don't yet cite `labour_context.json`'s
      ILOSTAT-via-ILO-mirror source path or `truck_flow.json`'s DLT `stat_1_009` — DONE 2026-07-11
      (8)** (two new rows in `DATA_PROVENANCE.md` §1 + two new cited sections in `DATA_SOURCES.md`,
      docs-only, gate reconfirmed 66/0 unchanged. Full writeup: `docs/DATA_REFRESH_LOG.md` 2026-07-11
      (8) entry).
- [ ] **Confirm whether "Sprint 2"-style commits are a recurring named workflow (not this loop)** —
      if so, worth a one-line note in `CLAUDE.md`'s Operating Model section pointing at whatever logs
      IT keeps (if any), so a future loop cycle doesn't have to re-discover "this diff isn't mine" via
      `git log` archaeology each time a gap is noticed. Needs Kaustav to confirm which workflow this
      is / whether it should own its own `PROGRESS_LOG.md` entries going forward. *(LOW, trivial,
      needs a human confirmation)*

## Queue — follow-ups noticed 2026-07-11 (3) — REFACTOR: gov.* join-check dedup
- [x] **`check_province_gov_joins()`/`check_province_factories_workers()` near-identical loops —
      DONE 2026-07-11 (3)** (new shared `_check_province_gov_join(field_sources)` in
      `tests/validate_data.py`; both callers now build a normalized `{gov_key: {"src":{th:expect},
      "default":...}}` map and delegate the compare loop. Zero behavior change — gate 66/0,
      `validate_data.py` 464/464 unchanged before/after; verified drift-detection still fires
      correctly via a hand-corrupt-then-restore of `bangkok.json`'s `gov.factories`. Closes the
      "near-identical gov-join-check functions" item open since 2026-07-10 (6)/carried through
      2026-07-11. Full writeup: `docs/PROGRESS_LOG.md` 2026-07-11 (3) entry).
- [ ] **The SAME duplicate-loop shape still exists on the frontend** — `drawAmphoeChoropleth()`/
      `drawProvinceChoropleth()` in `platform/app.js` (flagged repeatedly: 2026-07-03 (6)/(9),
      2026-07-04, 2026-07-04 (6), 2026-07-06 (3)) share the same "lazy-load polygons → colour-ramp by
      lens value → canvas GeoJSON layer → popup" shape but differ enough (categorical crop-lens
      branch, amphoe-id vs province-name keying, ◇ vs ● popup glyph, 0.5 vs 0.45 fillOpacity) that a
      clean merge needs real design care, not a 10-minute port. This cycle deliberately picked the
      backend (`validate_data.py`) version of this same smell instead, since it was fully mechanical
      and verifiable by re-running the gate — the frontend one is a better fit for a cycle with room
      to headless-render both `?lens=drisk#map` and `?lens=pstress#map` before/after to catch a
      subtle regression a text diff wouldn't. *(LOW-MED, S-M, pure refactor, needs visual
      verification)*
- [ ] **`_check_province_gov_join()`'s new normalized `field_sources` shape is a reusable pattern**
      for any FUTURE `gov.*` join check (a 9th field) — a future cycle adding one should build its
      own `{th_name: expected}` map and pass it in, rather than reaching for the old per-function
      hand-rolled loop this cycle just retired. *(LOW, trivial, informational — keeps the new
      pattern from being rediscovered from scratch)*

## Queue — follow-ups noticed 2026-07-11 (2) — AUDIT: provenance sweep + determinism-gate gap
- [x] **`platform/data/rayong_province.json`'s builder (`build_rayong.py --check`) was never wired
      into `tests/run.sh`'s determinism gate, unlike every sibling builder — DONE 2026-07-11 (2)**
      (one-line addition to `phase_check()`, same pattern as `derive.py`/`build_province.py`/etc.;
      confirmed the builder already reproduced byte-exact before wiring it in, so this was a pure
      gate-hardening fix, zero data changed. Notable because `rayong_province.json` also feeds
      `build_catchment_poi.py`'s curated POI source for every OTHER province's 3D scene, not just
      the retired `rayong-province.html` redirect stub — a silent hand-edit here would have gone
      undetected by CI. Gate 65/0, `validate_data.py` 464/464. Full writeup:
      `docs/DATA_REFRESH_LOG.md` 2026-07-11 (2) entry).
- [ ] **A broader `meta`/provenance sweep of all 67 non-geometry `platform/data/*.json` files found
      no other real gaps** (8 flagged by a keyword scan were all either already correctly on
      `PROVENANCE_EXEMPT` or carry a `generated_with`-keyed meta the scan's keyword list missed) —
      worth widening the recognized-provenance-key list (or `check_province_provenance()`-style
      checks) to also accept `generated_with`, purely so a future audit doesn't have to hand-verify
      the same 3 false positives (`decision_queue.json`, `occupation_risk.json`,
      `opportunity_score.json`) again. *(LOW, trivial, informational)*

## Queue — follow-ups noticed 2026-07-11
- [x] **`check_province_gov_joins()` and `check_province_factories_workers()` are now near-identical
      functions — DONE 2026-07-11 (3), see the entry above.** Same duplicate-helper smell already
      logged for `drawAmphoeChoropleth`/`drawProvinceChoropleth` on the frontend side (2026-07-03
      (6)/(9)) — that frontend twin is still open, carried forward as a new entry above.
- [ ] **All ~8 `gov.*` top-level joins in `provinces/<slug>.json` now have a value-level check** —
      the full set (vehicles/employment/unemployment/income/income_floor/vehicle_flow/
      vehicle_flow_transport/factories/workers) is closed as of this cycle. Worth a one-line note in
      `CLAUDE.md`'s `build_province.py` bullet or a comment atop `check_province_gov_joins()` so a
      future cycle doesn't re-propose "add a gov.* join check" as if there were still a gap — the
      next real gap here would only appear if `build_province.py` grows a 9th `gov.*` field.
      *(LOW, trivial, informational)*
- [x] **`docs/PROGRESS_LOG.md` Sprint 2 E0/UX commit-log gap (flagged 2026-07-10 (3), still open
      2026-07-10 (6)/2026-07-11) — DONE 2026-07-11 (4)** (read all 7 diffs — `8cf4f78`…`e53705d` +
      `2b1e835`/`d4759eb` — end-to-end, verified each headline claim live against the current tree,
      wrote a full backfill entry into `docs/PROGRESS_LOG.md`. No code/data changed, pure docs backfill.
      Gate reconfirmed 66/0 before and after. See `docs/PROGRESS_LOG.md` 2026-07-11 (4) entry).

## Queue — follow-ups noticed 2026-07-10 (6)
- [ ] **`check_province_gov_joins()` (new this cycle) does an exact whole-dict `==` compare, not a
      per-field range/type check** — this is deliberately stricter than `check_province_income_floor()`
      (which validates each field individually with a sane-range assertion) since these 4 fields are
      pure unmodified pass-throughs with no derived math, so a single dict-equality check is both
      simpler and catches strictly more (any key added/dropped/renamed too, not just an out-of-range
      value). Worth keeping in mind as the reference pattern if a 5th pure-pass-through `gov.*` field
      is ever added — prefer the dict-equality shape over re-deriving a range check unless the field
      involves real computation. *(LOW, trivial, informational)*
- [ ] **`docs/PROGRESS_LOG.md` still has no entries for the "Sprint 2 E0 (1)-(5)" / "Sprint 2 UX (P1)"
      commits now on this branch** (`8cf4f78`…`e53705d` and the newer `2b1e835`/`d4759eb` four-
      destination IA reorg + Overview reorder) — flagged once already (2026-07-10 (3) follow-up,
      still open) but the gap has grown: `git log --oneline -15` this cycle showed 2 more
      undocumented "Sprint 2 UX" commits landed since. These are real, gate-passing, and clearly a
      concurrent session/workflow's work (not this loop's) — a future AUDIT cycle should read the
      diffs end-to-end and either backfill the log or confirm with Kaustav whether that workflow
      should own its own logging. *(MED, S, informational — docs-debt, not a code defect, growing)*
- [x] **`build_province.py`'s `gov.factories`/`gov.workers` (from `factories_by_district.json`,
      province total) were the only 2 of the ~8 `gov.*` top-level joins still without ANY
      join-integrity check — DONE 2026-07-11** (new `check_province_factories_workers()` in
      `tests/validate_data.py`, same dict-pass-through shape as `check_province_gov_joins()`;
      SKIP-passes when `factories_by_district.json` is absent. Verified it catches real drift by
      hand-corrupting `bangkok.json`'s `gov.factories` to `999999`, confirming a `[FAIL]` naming the
      exact expected-vs-got, then restoring. Gate 64/0, `validate_data.py` 464/464. This closes the
      full set of `gov.*` top-level joins — see `docs/PROGRESS_LOG.md` 2026-07-11 entry).

## Queue — follow-ups noticed 2026-07-10 (3) — data-enrichment cycle: commodity_board traceability
- [x] **`source-data/commodity_board.json` had NO check tying its numbers to the raw World Bank Pink
      Sheet pulls that back it — DONE 2026-07-10 (3)** (`tests/validate_data.py`'s new
      `check_commodity_board()` cross-verifies all 11 rows' `yoy`/`stale` against
      `commodities.json`/`commodities_protein.json` exactly; the latter had ZERO pipeline consumers
      before this — now it does, via a check, not a builder. Gate 64/0, `validate_data.py` 462/462.
      Full writeup: `docs/DATA_REFRESH_LOG.md` 2026-07-10 (3) entry).
- [ ] **`commodity_board.json` is still hand-assembled, not regenerated by any pipeline script** —
      the new check (above) catches DRIFT between the board and the two raw files, but there is still
      no `build_commodity_board.py` that would let a future Pink Sheet re-pull (`pull_macro.py` or a
      new puller) flow through to the board automatically; someone still has to hand-edit
      `commodity_board.json` (numbers AND the editorial `note`/`reg`/`cls` prose per row) after any
      refresh, then re-run `validate_data.py` to confirm it still matches. A real builder is only
      worth it once `note`/`reg` (freeform Thai-market color, not derivable from a price number alone)
      have a defined generation rule — until then this is best done by hand + gated, not automated
      halfway. *(LOW-MED, M, needs a design decision on the editorial fields first)*
- [ ] **`commodities_protein.json`'s `shrimp` field is dated `2023M10`** while every other field in
      that file (and its sibling `commodities.json`) is `2026M06` — a genuinely stale sub-field in an
      otherwise-fresh pull. Not currently surfaced anywhere (`commodity_board.json` doesn't use
      `shrimp`), so no live number is wrong, but if a future cycle ever wires shrimp into the board
      (e.g. a fisheries/aquaculture collateral angle), re-pull it first rather than trusting the
      committed value. *(LOW, trivial, informational — noticed during the 2026-07-10 (3) audit)*

## Queue — follow-ups noticed 2026-07-10 (data-enrichment cycle: DLT vehicle-flow)
- [x] **DLT `dataset_stat_1_008` registration-action flow — DONE 2026-07-10** (`pull_dlt_all.py`'s
      full-catalog mirror, wave 10, had landed this dataset unprocessed; `build_vehicle_flow.py`
      distills the trailing-12mo dereg_rate/transfer_rate per province/vehicle-class →
      `source-data/vehicle_flow_by_province.json`, joined into `provinces/<slug>.json`'s
      `gov.vehicle_flow`, surfaced as an "Elevated motorcycle scrappage" callout on the province
      deep-dive for the ~top-decile provinces (dereg_rate≥1%). Gate 60/0, `validate_data.py` 453/453
      (+5 checks incl. a source↔join exact-match check). Full writeup: `docs/DATA_REFRESH_LOG.md`
      (2026-07-10 entry).
- [x] **`dataset_stat_1_009` (land-transport-law registration-action flow — trucks/buses) — DONE
      2026-07-10 (2)** (`build_vehicle_flow_transport.py` distills the already-mirrored 50 monthly
      files into `source-data/vehicle_flow_transport_by_province.json` [truck/bus/small buckets],
      joined into `provinces/<slug>.json`'s `gov.vehicle_flow_transport`, surfaced as an "Elevated
      commercial-truck scrappage" callout for `dereg_rate≥4.5%` [~top-decile, p90=4.66%]. Gate
      62/0, `validate_data.py` 458/458. While verifying the new callout, found and fixed that
      `province.html`'s `autoImpacts()` branch was DEAD CODE on all 77 provinces — see the new
      follow-up below. Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-10 (2) entry).)
- [x] **★ FIXED WHILE WIRING IN THE ITEM ABOVE — `province.html`'s `buildProvincePanels()` had a
      real bug: `const impacts = editorial ? f.impacts : autoImpacts()` never called
      `autoImpacts()` on any of the 77 provinces, because `source-data/province_narratives.json`
      now has non-empty `impacts` for every province (CLAUDE.md's "curated for Rayong today" note
      is stale — this went unnoticed for at least one prior cycle).** This silently hid BOTH the
      moto-scrappage callout (2026-07-10 (1)) and would have hidden this cycle's truck-scrappage
      callout too. Fixed by extracting the two DLT-flow watch-flags into their own
      `vehicleFlowImpacts()` and always appending them regardless of which branch renders — verified
      live in the rendered DOM (Sa Kaeo now shows "Elevated motorcycle scrappage" appended after its
      6 editorial lines; Nakhon Pathom, hand-checked via Node since this page's render is separately
      flaky, shows the truck line appended after 5 editorial lines). *(DONE — worth a CLAUDE.md
      correction on "curated for Rayong today" next time someone's touching that doc, since the
      narrative file has clearly grown past that scope; LOW, trivial, doc-only follow-up)*
- [ ] **`vehicle_flow_by_province.json`'s "top decile" narrative threshold (dereg_rate≥1%) was
      picked from this cycle's own computed p75/p90 (0.47%/1.47%), not recalculated per refresh** —
      if a future DLT re-pull shifts the national distribution meaningfully, the hardcoded 0.01
      constant in `province.html`'s `autoImpacts()` won't auto-adjust. Fine for now (a fixed
      absolute-rate bar is arguably MORE stable/comparable across refreshes than a shifting
      percentile), but worth a comment/awareness if it starts flagging 0 or 77 provinces after a
      future refresh. *(LOW, trivial, speculative)*
- [ ] **Headless render of `province.html?p=tak` hit the same pre-existing sandbox flakiness this
      page has shown in multiple prior cycles (2026-07-03 (7), 2026-07-05)** — verified the new
      narrative line is correct by reading `provinces/tak.json` by hand (`gov.vehicle_flow.moto.
      dereg_rate=0.041`) and `node --check`ing the extracted inline JS instead. The render-harness
      unreliability for this specific page (already logged twice) is now a 3rd occurrence — worth
      the `tests/lib/render.sh` retry-budget investigation flagged back on 2026-07-05 if a future
      cycle has spare scope. *(MED, S — blocks fast visual confidence on province-page cycles,
      not this cycle's own regression)*

## Queue — follow-ups noticed 2026-07-10
- [ ] **★ NEEDS KAUSTAV (repo Settings, not sandbox-fixable) — `data-fuel-prices.yml`/
      `data-nabc-prices.yml` both do real work then fail at `gh pr create`.** Both scheduled pullers ran
      for real (fresh Bangchak/NABC data pulled, `source-data/*.json` rebuilt, committed + pushed to a
      fresh `data/fuel-<run>`/`data/nabc-<run>` branch) then hit `GraphQL: GitHub Actions is not
      permitted to create or approve pull requests (createPullRequest)`. Fix is a one-click repo
      setting: **Settings → Actions → General → Workflow permissions → check "Allow GitHub Actions to
      create and approve pull requests"** — needs repo-admin access this loop doesn't have. Two real
      pushed data branches (`data/fuel-29058372866`, `data/nabc-29052534833`) are sitting PR-less on
      origin right now with genuinely fresh MEASURED prices; once the setting is flipped, either re-run
      the workflows or manually open PRs for those two existing branches. Flagged via `PushNotification`
      2026-07-10. *(HIGH, needs a human — do not attempt to change repo Settings from the loop)*
- [ ] **Re-check `data-macro.yml`/`data-oae-prices.yml`/`data-gov-census.yml`/`data-overture.yml`/
      `data-tiles.yml`'s first scheduled runs once enough wall-clock has passed** — all 5 still showed 0
      runs as of 2026-07-10 (crons hadn't ticked). Once they have, they likely hit the SAME `gh pr
      create` permission wall as fuel/nabc (all use the identical create-PR-from-Action pattern) —
      worth confirming, but almost certainly the same single repo-setting fix covers all of them at
      once, not 5 separate diagnoses. *(MED, S — just a status check, likely same root cause as above)*
- [ ] **`site-health.yml` had already filed GitHub issue #3 from the false-alarm run** (title "🚨 Site
      health check failed 2026-07-09") — now that the checker points at the real public alias, the next
      scheduled or manual run should close it automatically via the workflow's own "Close health issue
      on success" step. Not force-closed manually this cycle (didn't want to fake a health-check pass by
      hand); worth confirming issue #3 auto-closes on the next real run. *(LOW, trivial — self-resolving)*

## Queue — follow-ups noticed 2026-07-10 (2)
- [ ] **`renderHomeWhitespace()` (the "Where to expand" card) now has 4 stacked blocks** (top
      districts, top provinces, competitor coverage, contested ground) — same growth pattern the risk
      card just got the "Show N more" treatment for. Not urgent (4 is still comfortable per the
      pattern this cycle used — the risk card wasn't collapsed until 9), but if a 5th block lands,
      the exact `details.cc-more` CSS class + `<details>` markup this cycle added is already
      reusable verbatim — no new mechanism needed, just wrap the newer blocks. *(LOW, S, speculative)*
- [ ] **`dataset_stat_1_009` (land-transport-law registration-action flow — trucks/buses) still has
      no distiller**, same shape as `build_vehicle_flow.py`'s already-shipped `dataset_stat_1_008` (car
      law) distiller — the raw data is already mirrored (`pull_dlt_all.py`, 50 monthly files under
      `source-data/dlt/raw/dataset_stat_1_009/`). Lower priority than car/moto (already covered) since
      commercial-vehicle churn is less central to a title-loan book, but a same-pattern, same-effort
      pickup for a future enrichment cycle. *(LOW-MED, S)*
- [ ] **Re-verify PR #1's successors (PR #2, this branch's current open draft) don't go stale the way
      PR #1 did** — PR #1 sat open 11 days before merging, during which every `schedule:`-triggered
      workflow stayed dormant. PR #2 has been open since 2026-07-09 with no merge activity yet; not
      actionable from the loop (merging is Kaustav's call), but worth a status mention if a future
      cycle notices it's aged similarly. *(LOW, trivial, informational)*

## Rules for each cycle (read before picking)
- **Sandbox-only.** No item that needs a desktop/Thai-IP data pull (those live in `TONIGHT_CHECKLIST.md`).
  Anything that consumes pulled data must **degrade gracefully** when the data is absent.
- **Gate-gated.** If you can't get `tests/run.sh check` to 0 failed, revert ONLY the files you changed and
  pick a smaller item.
- **Shared working tree.** Other sessions may share this checkout — NEVER run `git clean -fd` or
  `git checkout -- .` (they destroy others' uncommitted work). Revert only files you yourself modified.
- **⛔ NO FABRICATION (absolute).** Never invent, guess, hallucinate, or synthesize a data value. Every
  number in `platform/data` must trace to a real source (committed `source-data/`, a real gov/OSM/Overture/TMLI
  pull) OR be explicitly labelled an ESTIMATED proxy/model with its method in the file's `meta`. If a value
  can't be sourced, leave it absent and log it — never fill a gap with a made-up number. When unsure if
  something is real, treat it as not-real and flag it rather than ship it.
- **Honest provenance.** Always label measured vs estimated (see CLAUDE.md).
- **Never** commit secrets or synthetic/generated geographic data; **only** push `claude/new-session-wto26j`.
- **Scope discipline.** Large/architectural/ambiguous ideas → write them here as a recommendation
  instead of building them. Prefer high-impact / low-effort.
- Serve the two standing objectives: **(1) portfolio risk**, **(2) where to expand**.

## Queue — UX / polish (from the UX committee; goal: beat DataProteins)
> Ranked by the committee. NOTE: some are IN FLIGHT in dedicated workflows — do not duplicate:
> `viz-richness-bangkok` owns rayong-catchment.html + index.html nav-3D; `design-system-polish` owns
> styles.css type/spacing. Loop should take the **app.js / page-structure / pipeline** items below.
> ⚠ **2026-07-04 (9) audit note:** this whole quick-wins list had gone stale — 6 of 8 items below were
> already shipped in commits dated 2026-06-30/07-01 but never checked off. Before picking a "new" UX
> item from this section, spot-check it against the live app (`bash tests/lib/render.sh 'index.html#<tab>'
> ...`) — a `git log -S"<label>"` on `platform/styles.css`/`app.js` is a fast way to confirm.
- [x] **QW2 — Fill the canvas — DONE 2026-06-30/07-01** (`f142cd0` fullbleed 2D + `5d006d6` consolidated
      the conflicting `main{max-width}` rules into one `--maxw`/`--maxw-wide` source of truth). Re-confirmed
      2026-07-04 (9): headless render of `index.html#map`/`#home` shows content edge-to-edge, no narrow column.
- [x] **QW3 — Fix the nav — DONE 2026-06-30** (`738c28b`: shortened labels — Home/Overview/National/Acquire/
      Exposure/Trend/3D map — tucked under a "More ▾", no fade mask). Re-confirmed 2026-07-04 (9): headless
      render shows all 8 top-level items fit on one row, nothing clipped.
- [x] **QW1 — Map = hero — DONE 2026-06-30** (`ff2e9af`: full-bleed 78vh Leaflet map, lens cards collapsed
      into one segmented pill row docked over the map with "ⓘ" info tooltips, "More lenses ▾" for the rest).
      Re-confirmed 2026-07-04 (9): headless render of `index.html#map` matches the spec exactly.
- [x] **QW5 — Home leads with the verdict — DONE 2026-06-30, since grown well past spec** (`af05be8`).
      Re-confirmed 2026-07-04 (9): Home now opens with a plain-language board-thesis line + Road-to-3,000
      bar + a ranked "THIS WEEK — do these first" defend/audit/tighten/expand queue (`decision_queue.json`),
      each row source-tagged — well beyond the original 2–3-sentence hero ask.
- [ ] **QW6 — 3D fails gracefully.** Replace the raw "Could not load buildings (Overpass blocked?) — all
      mirrors failed" with a calm styled status ("Building footprints unavailable — showing branch + POI layer")
      and keep rings + branch pin + POI dots rendered so the scene is never blank. *(HIGH, S)* **Still open on
      `rayong-catchment.html`** (owned by `viz-richness-bangkok`, not touched by the loop) — confirmed
      2026-07-04 (9): that page's data-load `.catch()` still shows a raw "Could not load … 3D data: {msg}"
      string. `branch-explorer.html` already ships the target pattern verbatim
      (`status('Building footprints unavailable — showing branch + POI layer', 'info')`) — the owning
      workflow can likely port that exact string/pattern instead of designing a new one.
- [x] **QW8 — Seed or hide Risk-trend — DONE 2026-06-30** (`44ca12d`: designed "baseline captured" state —
      flat sparkline skeletons + "Δ at next refresh" chip — renders whenever `deltas.json` is single-vintage
      or absent, never a blank apology). Re-confirmed 2026-07-04 (9) by reading the live `renderTrend()`/
      `renderTrendBaseline()` code path (a 2nd vintage hasn't landed yet, so this is still the active state).
- [ ] **QW4 (shared w/ design team) — Unify on ONE theme.** Make the indigo-console tokens canonical, delete
      the legacy `:root`/nav/`.mcard` block (~styles.css lines 1–98), confirm the SPA inherits it, use
      identical nav markup on every page so deck.gl pages feel in-product. *(HIGH, M — coordinate w/ design-sys)*
      Confirmed 2026-07-04 (9) still open: `platform/styles.css` still has two `:root{}` blocks (line 1 and
      line 119) — owned by `design-system-polish`, not touched by the loop.
- [ ] **Reduce prose** — explanatory sentences → captions; numbers + colour carry meaning. *(med, S)*
      Not independently re-checked 2026-07-04 (9) — unlike the QW items above, no single commit title
      claims this one done; leaving open rather than guessing.

### Bigger bets (from committee — schedule after quick wins)
- [ ] Promote a deck.gl 3D scene to a **landing hero** (clickable thumbnail/loop on Home + province headers). *(HIGH, M)*
- [ ] **Dock the floating 3D controls** into a designed frame (legend rail, basemap segmented top-right named
      Streets/Satellite/Dark, action pills grouped bottom-right, proper header band, kill the stuck loader crescent). *(HIGH, M)*
- [ ] **Standardize provenance** as one quiet chip (filled dot = measured, hollow = estimated, ≥11px AA),
      one legend per page; move caveats into a consistent "Method & caveats" expander everywhere. *(MED, M)*
- [x] **★ Rebuild dense tabs as 2-col dashboards — DONE 2026-06-30** (`af05be8` "UX wow layer: 2-col
      dashboards + home leads with the verdict"). Re-confirmed 2026-07-04 (9) via headless render: Home,
      Overview and Exposure all lay out as KPI-card column beside a lead table/board that fills the widened
      canvas. Acquisition intentionally stayed single-column full-width (matches this item's own spec — "leads
      with the full-width Road to 3,000 bar + leaderboard"), though today the opportunity-score leaderboard
      renders ABOVE the Road-to-3,000 section rather than after it — cosmetic ordering only, logged below.
- [ ] **Touch-target pass** behind `@media (pointer:coarse)` (not a 600px phone breakpoint) for the touch laptop. *(MED, S)*
- [x] **Acquisition tab section order — DONE 2026-07-05 (6)** (`platform/index.html`: swapped `sec-r3k`
      (Road to 3,000) and `sec-opp` (opportunity leaderboard) so the tab now matches the "2-col
      dashboards" bigger bet's own spec — full-width Road-to-3,000 bar first, leaderboard underneath;
      `#acqjump` chip order updated to match. Pure markup reorder, zero JS/data touched, ids/`open`
      state unchanged so no app.js call site was affected. Gate 52/0, headless-rendered `#acq` confirms
      the new order + `data-errors="[]"`).

## Queue — UX follow-ups noticed 2026-07-03 (2)
- [x] **`hhdti` (household DTI) lens is province-resolution but only paints branch dots — DONE
      2026-07-03 (7)** (`build_province_geo.py` groups the existing `amphoe_geo.json` polygons by
      province → `province_geo.json`; `hhdti`/`pstress` gained `prov:true` + a
      `drawProvinceChoropleth()` layer, same pattern as the district choropleth).

## Queue — enrichment / capabilities (serve the two objectives)
- [x] **★ Household debt-to-income RISK LENS (National map) — objective #1, MEASURED. DONE 2026-06-30** (build_household_risk.py
      → household_risk_by_province.json + National lens "MEASURED · NSO"; top DTI all Isan: Khon Kaen 1.15×, Amnat Charoen 1.14×).
- [x] **★ Surface the opportunity score on the Acquisition tab — objective #2. DONE 2026-06-30** (#acq "Where to open next"
      leaderboard: top-20 districts + whitespace/competitor-gap/agri-stress component bars; Vadhana 82, Bang Na 80).
- [x] **Composite expansion-opportunity score per district — DONE (pre-existing, found stale during the
      2026-07-04 (9) audit)** (`pipeline/build_opportunity_score.py` → `platform/data/opportunity_score.json`
      already fuses white-space + competitor-gap + province-inherited agri-stress + optional occupation-pull
      into one 0–100 composite, renormalizing weights over whichever optional inputs are present; surfaced
      on `#acq`'s "Where to open next" leaderboard, re-confirmed live via headless render 2026-07-04 (9)).
      This queue entry was a duplicate of already-shipped work — corrected instead of re-built.
- [x] **Occupation × risk cross-read — DONE 2026-06-30** (`build_occupation_risk.py` → `occupation_risk.json`,
      index-aligned to branches.json: per-branch ESTIMATED occ-stress = MEASURED Overture occupation shares ×
      ESTIMATED stressed-sector weighting [factory national slowdown lever + agriculture = province crop-stress],
      flag when score≥25 & ≥20 estab≤10km. National-map lens `Occupation × stress ◆▲` + branch-popup flag, both
      hide/omit gracefully when absent. Skip-pass `--check` when `branch_occupations.json` absent; validate_data.py
      check + tests/run.sh gated. Dark-until-data — lights up when the Overture pull lands.)
- [x] **Competitor coverage QA panel — DONE 2026-06-30** (#acq found-vs-expected per brand, cited expected; total coverage
      21.9% — MTC 11.3% (978/8673), Tidlor 39%, Srisawad 49%, Heng expected uncited/null. build_competitor_coverage.py gated).
- [x] **Competitor coverage QA panel — ALREADY SHIPPED, stale duplicate found 2026-07-05 (7).**
      This entry duplicated the `[x]` DONE 2026-06-30 item two lines above (same feature,
      `build_competitor_coverage.py`/`#acq` found-vs-expected panel) — confirmed via `grep`/`git log`
      before touching anything; no code changed, checked off rather than re-built.
- [x] **NSO census occupation distiller scaffolding in `ingest_gov.py` — ALREADY SHIPPED, stale
      duplicate found 2026-07-05 (7).** `build_occupations_census()` + `OPTIONAL_LAYERS` (commit
      `7fd4994`, 2026-06-30) already do exactly this: distill the blocked NSO 2022 Business &
      Industrial Census export into `source-data/occupations_by_district.json` (per-province/
      -district establishment + worker counts by business-activity category), returning `None`
      (silent skip, no crash, no fabrication) when `dgt_out/nso_census__bizind__*.csv` is absent —
      confirmed still absent in this sandbox, so the layer stays correctly dark. Verified via
      `git log -S"build_occupations_census"` + reading `ingest_gov.py`'s `run()` before touching
      anything; no code changed, checked off rather than re-built.
- [x] **Expand `validate_data.py`** coverage as new data layers land — DONE 2026-07-04 (3) (see below).
- [x] **National map: dedicated "Unemployment ▲" district lens — DONE 2026-07-03** (new `unemp` lens
      in `platform/app.js`'s `LENS` registry, mirrors the household-DTI dot-lens pattern; reads
      `d._amp.unemployment_rate` off the existing amphoe join, own 1-decimal-percent legend tagged
      measured · NSO LFS, lives in "More lenses ▾"; gate 31/0, headless-rendered + DOM-verified).
- [x] **Combine household DTI + unemployment into one province portfolio-stress index — DONE
      2026-07-03 (3)** (`build_province_stress.py` → `province_stress_index.json`: 0.5×DTI-percentile
      + 0.5×unemployment-percentile composite over the two already-MEASURED NSO layers; new National
      map lens "Province stress ▲ est" — #1 อำนาจเจริญ composite 98.05, #2 นครพนม 90.58).
- [x] **Backlog hygiene pass — DONE 2026-07-03** (deduped the stale `[ ]` Household-DTI-lens and
      `[ ]` opportunity-score entries that were describing work already shipped `[x]`; removed the
      stale `[ ]` P2 Road-to-3,000 rounding item at the bottom of this file, already fixed per the
      2026-07-01 Done entry).
- [ ] **Vendor `numpy`/`shapely`/`rasterio` into the sandbox's default setup** (session-start hook or
      environment Dockerfile) so `build_branch_peers.py --check` and `build_branch_population.py
      --check` run for real on cycle 1 instead of hitting `[SKIP]` (2026-07-03/2026-07-03(6) fixes stop
      them being misreported as failures, but a `[SKIP]`'d check still isn't as good as one that
      actually ran). *(LOW, S)* **UPDATE 2026-07-11 (3):** manually installed all three
      (`numpy==2.4.6`/`shapely`/`rasterio`) this cycle and confirmed all 4 previously-`[SKIP]`
      builders (`build_branch_peers.py`, `build_crop_landuse.py`, `build_branch_population.py`,
      `build_contested_pop.py`) reproduce byte-exact for real — 0 drift, closing the trust gap.
      Automating the install via `.claude/hooks/session-start.sh` was **attempted and blocked by
      the auto-mode permission classifier** (a `SessionStart` hook is a standing persistence
      mechanism and this cycle is an unattended run, not a real user turn approving it) — needs
      Kaustav to create it directly, or approve it in an interactive session. See
      `docs/DATA_REFRESH_LOG.md` 2026-07-11 (3) for the exact script content to paste in.
- [ ] **Document the "optional heavy dependency" pattern** (try/except ImportError → distinct exit code
      → `tests/run.sh` reports `[SKIP]` not `[FAIL]`) in `CLAUDE.md`'s pipeline conventions, so if a
      future script adds `scipy`/`pandas`/etc. it follows `build_branch_peers.py`'s 2026-07-03 fix
      instead of reintroducing a false-red gate. *(LOW, S)*
- [x] **Simulator: occupation-sensitivity lever — ALREADY SHIPPED, stale duplicate found 2026-07-05 (6).**
      Confirmed via `grep`+read before touching anything: the 2026-07-01 "factory-slowdown lever"
      (`platform/app.js` `simFactoryModel()`/`renderSimFactory()`/`SIM_FACTORY_KEYS`) already IS this —
      an ESTIMATED severity lever (0–100%) that models manufacturing-base branch exposure to a sector
      slowdown off the MEASURED `occupation_risk.json` composite, hidden gracefully when the Overture
      occupation pull is absent. No code changed; left checked rather than rebuilding duplicate UI.
- [x] **`unemp` lens: add a district (amphoe) polygon choropleth — DONE 2026-07-03 (2)** (added `unemp`
      to `drawAmphoeChoropleth()`'s `on` check + the `ageoLoaded` lazy-load trigger in `setLens()`;
      reuses `unemp`'s existing color/val from `LENS` and the amphoe-geo layer already warmed for
      dws/drisk — 2-line change, no new data. Gate 30/0; headless-rendered `?lens=unemp` confirms the
      district polygons now paint alongside branch dots).
- [x] **Sandbox setup gap: `numpy` isn't installed by default — DONE 2026-07-03** (`build_branch_peers.py`
      now catches `ImportError` and exits `3` with a clear "dependency missing, NOT data drift" message;
      `tests/run.sh` reads that exit code and reports `[SKIP]` instead of `[FAIL]`, so a fresh loop
      session without `numpy` no longer hits a false-red gate on cycle 1. Real drift still fails
      correctly — verified by hand-corrupting `branch_peers.json` and re-running with `numpy` installed.
      Vendoring `numpy` into the environment's default setup itself is still open — see below.)
- [x] **Combine household DTI + unemployment into a single province stress score for the National
      map — DONE 2026-07-03 (3), duplicate of the entry above** (same delivery: `pstress` lens).
- [x] **Fold NSO LFS `unemployment_rate` into `build_amphoe.py`'s `risk_proxy` — DONE 2026-07-02 (3)**
      (province-inherited `unemployment_rate` field + risk_proxy now 0.4·agri_stress + 0.25·collateral +
      0.15·merchant + 0.2·unemployment_stress [scaled 0-3.0%->0-100, clipped]; #acq risk table gained an
      Unemployment column; expansion_plan.json regenerated to match; gate 31/0).

## From the research digest (docs/RESEARCH_DIGEST.md — all cited)
- [x] **★ Model the BoT 28% title-loan rate cap — DONE 2026-06-30** (Simulator lever: book yield 28.2%→26.2% under the cap,
      −2.0 pts; moto/agri-vehicle/top-up compress; product mix labelled ESTIMATED, 28% cited; default OFF).
- [ ] **★ Model the BoT 28% title-loan rate cap** in the Simulator (effective 2 Dec 2025). Add a lever/scenario
      showing book yield + which segments compress at 28%. Real regulatory constraint (obj #1). *(HIGH, M, sandbox)*
- [x] **Competitor-exit white-space cue — DONE 2026-06-30** (#acq regulatory-tailwind card + ESTIMATED proxy: districts with
      AutoX demand but thin big-4 footprint; honest caveat that a true rival-fragility index needs a sub-scale-operator census).
- [ ] **Competitor-exit white-space cue** — non-compliant operators must register by Q1 2026 or exit; surface
      districts where sub-scale rivals may exit as fresh white-space (obj #2). Uses existing competitor census. *(MED, M)*
- [x] **Rice/rubber + drought "double-stress" flag — DONE 2026-06-30** (crop_stress.json double_stress flag + score, 20 provinces
      flagged; Overview badge; uses only existing signals, ESTIMATED-labelled, drought is the discriminating leg).
- [ ] **Rice/rubber + drought "double-stress" flag** in crop_stress / district risk — research shows rice+rubber
      prices softening AND >80% El Niño drought prob mid-2026; flag districts with both (obj #1). Uses existing
      crop_stress signals, label estimated. *(MED, M, sandbox)*
- [x] **Collateral-NPL context — DONE 2026-06-30** (Exposure peer-NPL benchmark: Tidlor 1.5% < MTC 2.53% < SAWAD 3.5–3.6%,
      cited, labelled PEER-reported / not an AutoX number; peer_npl.json).
- [ ] **Collateral-NPL context** — peer NPL ladder (Tidlor 1.5% < MTC 2.53% < SAWAD 3.5–3.6%) tracks collateral
      mix; annotate our collateral/segment views with this measured peer context (cited). *(LOW, S)*

## Blocked (need a desktop / Thai-IP pull — do NOT attempt in the loop)
- **★ DLT vehicle registrations by province — gdcatalog.dlt.go.th/en/dataset/** (separate from data.go.th). Highest-
  value new pull: replaces ESTIMATED collateral-supply/TAM per district with MEASURED data (both objectives).
- **OAE farm-gate crop prices** — replace the GLOBAL World Bank price proxy in build_crop_stress.py with real Thai
  farm-gate prices (sharpens obj #1).
- Occupation/competitor **deltas over time** — needs ≥2 vintage snapshots with the new layers.
- **NSO 2022 Business & Industrial Census** ingest — data is data.go.th (blocked from sandbox).
- More **cities** for the 3D showcase (Overture/Overpass pull) — Bangkok already pulled; others need a pull.
- Real **farm-gate** prices, isochrones (ORS/GISTDA), DLT/DIW gov refresh.

## Queue — follow-ups noticed 2026-07-03 (3)
- [ ] **`province_stress_index.json`'s equal 50/50 DTI/unemployment weighting is an editorial
      choice** (documented honestly in `meta.caveats`, not calibrated to realized loss) — once the
      real loan tape lands (`docs/TONIGHT_CHECKLIST.md` §6), correlate `composite_stress` against
      actual branch-level 90+ delinquency by province and re-weight if one leg dominates. *(LOW, S,
      blocked until real loan tape)*
- [ ] **`build_province_stress.py` could add a 3rd leg** once DLT vehicle registrations (the
      highest-value blocked pull, `docs/TONIGHT_CHECKLIST.md` §1) land — collateral-supply stress
      (motorcycle share of the province vehicle stock is already a MEASURED lens, `motomix`) is a
      third structurally-relevant, already-sourced signal that isn't in the composite yet. *(LOW, S)*

## Queue — follow-ups noticed 2026-07-03 (4)
- [ ] **`renderHomeThesis()`'s one-sentence board thesis still doesn't cite `PSTRESS_LIST[0]`** —
      only the risk CARD got the new "structurally riskiest" row this cycle; the top-of-page
      sentence's "risk to watch" clause still only checks `HHRISK_LIST[0]`/`CSTRESS_LIST[0]`. Once
      `province_stress_index.json` is the more defensible read (it blends two NSO legs, not one),
      consider swapping the thesis clause to lead with the composite instead of raw DTI, or adding a
      4th clause — small, same lazy-load chain (`loadProvinceStress` is already warmed on Home).
      *(LOW, S)*
- [ ] **`PSTRESS_LIST[0]` and `HHRISK_LIST[0]` can point at different provinces** (composite blends
      DTI+unemployment, DTI alone is unemployment-blind) — today's data has them agree
      (อำนาจเจริญ/ขอนแก่น both Isan, no direct clash visible on the rendered card), but nothing
      guards against the two rows reading as contradictory "riskiest province" claims if the two
      legs diverge on a future NSO refresh. Worth a short explanatory caption distinguishing
      "composite structural stress" from "raw household leverage" if it ever looks confusing in
      review. *(LOW, S)*
- [x] **Same rank-1-surfacing pattern could extend to the Exposure tab — DONE 2026-07-05**
      (`#exposure`'s `renderRiskReadouts()` gained a "Structurally riskiest · household DTI +
      unemployment" callout sourced from `PSTRESS_LIST[0]`, reusing the existing `ccRow()`/`TAG_E`
      helpers and `province_stress_index.json` plumbing — no new data/pipeline. Headless-rendered,
      no JS errors, gate 47/0).

## Queue — follow-ups noticed 2026-07-03 (5)
- [x] **`pstress` lens has the same "province-resolution but only branch dots" issue as `hhdti` —
      DONE 2026-07-03 (7), duplicate of the entry fixed above** (one `province_geo.json` +
      `drawProvinceChoropleth()` serves both lenses via the shared `prov:true` flag).
- [ ] **Stale comment at `platform/app.js`'s `initMap()` `deferForAmp` line ("the district lenses
      (dws/drisk) read d._amp") predates the `unemp` amp lens** and now also `isAmpLens()` — the
      comment still names only 2 of the (now 3, growing) amp lenses. Reword to describe the
      mechanism ("any amp:true lens") instead of enumerating keys, so it doesn't go stale again
      next time one is added. *(LOW, trivial)*

## Queue — follow-ups noticed 2026-07-03 (6)
- [ ] **`province_geo.json`'s province shapes are amphoe polygons GROUPED (not dissolved)** —
      internal amphoe boundary seams render as thin lines within a province (cosmetic only, the
      fill colour is uniform per province so it still reads as one shape at the National map's
      normal zoom). If `shapely` ever lands in the default sandbox setup (see the existing
      "vendor numpy/shapely/rasterio" backlog item), a true `unary_union` dissolve would produce
      cleaner single-ring province outlines — low priority, purely cosmetic. *(LOW, S,
      blocked-ish on shapely)*
- [ ] **`drawAmphoeChoropleth()` and `drawProvinceChoropleth()` are near-duplicate functions**
      (same canvas-layer lifecycle, colour-ramp, popup-binding shape, only the join key differs —
      amphoe `id` vs province name) — now that there are two resolutions of choropleth, a shared
      `drawChoropleth({features, keyFn, valFn, ...})` helper would remove the duplication before a
      3rd resolution (e.g. region-level) ever gets added. *(LOW, S, pure refactor)*
- [x] **The new province choropleth is effectively invisible at the National map's default
      country-wide zoom — DONE 2026-07-03 (9)** (`styleMarkers()` drops marker `fillOpacity` to 0.6
      specifically when `isProvLens(curLens)` is true; every other lens unchanged at 0.9).

## Queue — follow-ups noticed 2026-07-03 (7)
- [x] **`household_debt_by_province.json` carries its OWN `debt_to_income` + `stress_index` (BOT
      Q4/2024 regional)** that is never surfaced — DONE 2026-07-04 (2), audit found this isn't just
      "disagreement" — the BOT-attributed fields have no citable resource id, look editorially
      hand-grouped (same smell as the GPP file), and diverge 10-20x from the recomputed ratio the app
      actually uses. Relabelled UNVERIFIED in `ingest_tmli.py`/`PROVENANCE.md`/`NEXT_STEPS.md`
      /`DATA_PROVENANCE.md`; zero data values changed; confirmed no code path ever consumed the
      unverified fields. See `docs/DATA_REFRESH_LOG.md` (2026-07-04 (2)).
- [ ] **The new `gov.income` per-occupation breakdown (2026-07-03 (8)) could feed the Simulator's
      occupation-sensitivity lever** — a sector shock that also discounts by the province's
      lowest-earning-occupation share would sharpen the existing ESTIMATED factory-slowdown lever
      with a real NSO income floor. *(LOW, M)*
- [x] **`province.html`'s new "Income by occupation" panel has no equivalent on the Overview/Exposure
      tabs — DONE 2026-07-05 (7)** (new `pipeline/build_occupation_income.py` aggregates the
      already-MEASURED `household_income_by_province.json` into a national worst-first ranking by
      occupation category; `#exposure`'s `renderRiskReadouts()` gained a "Lowest-paid occupation
      nationally" callout — Transport ฿18,547/mo avg, worst แม่ฮ่องสอน ฿6,713/mo — same rank-1
      pattern as `PSTRESS_LIST[0]`. Gate 53/0, `validate_data.py` 433/433. See `docs/PROGRESS_LOG.md`
      2026-07-05 (7).)

## Queue — follow-ups noticed 2026-07-03 (9)
- [x] **The same "opaque dots tile over a polygon fill" issue likely applies to the amphoe
      (district) choropleth too — DONE 2026-07-04** (`styleMarkers()`'s dot-opacity thinning now
      checks `isProvLens(curLens)||isAmpLens(curLens)`, so `dws`/`drisk`/`unemp` get the same 0.6
      thinning `hhdti`/`pstress` got in 2026-07-03 (9); confirmed via headless render of
      `?lens=drisk#map` that the district fill now reads through the dots).
- [ ] **0.6 opacity was picked from the backlog's suggested 0.55–0.65 range, not measured against a
      contrast/legibility bar** — worth a quick visual check that dot fill-color is still readable at
      0.6 against both the light basemap and the reddest end of the stress ramp before calling the
      choropleth-visibility problem fully closed. *(LOW, trivial)*
- [ ] **`drawAmphoeChoropleth()` and `drawProvinceChoropleth()` are near-duplicate functions** — see
      the existing 2026-07-03 (6) backlog entry above; now that dot-opacity handling has ALSO grown a
      parallel `isAmpLens`/`isProvLens` branch in `styleMarkers()`, a shared `isPolyLens(k)` +
      `drawChoropleth({...})` helper would collapse three duplicated call-sites at once instead of one.
      *(LOW, S, pure refactor)*

## Queue — follow-ups noticed 2026-07-04
- [ ] **`isProvLens(curLens)||isAmpLens(curLens)` in `styleMarkers()` is the third call-site that now
      distinguishes "polygon-backed lens" from a plain branch/estab/comp lens** (the choropleth-draw
      call already does `drawAmphoeChoropleth(); drawProvinceChoropleth();` unconditionally and each
      no-ops internally) — the existing backlog item proposing a shared `isPolyLens(k)` helper
      (2026-07-03 (6)/(9)) would now collapse three OR-chains into one; worth doing together with the
      `drawAmphoeChoropleth`/`drawProvinceChoropleth` duplicate-function merge already queued.
      *(LOW, S, pure refactor)*
- [ ] **No amp/prov lens currently combines BOTH a district fill and a province fill on the same
      view** — if a future lens ever wants district-level detail nested inside a province-level
      rollup (e.g. show province stress shading with district risk dots atop it), `styleMarkers()`'s
      binary `polyDots?0.6:0.9` would need a 3rd tier; not needed today, just a note for whoever adds
      the next choropleth resolution. *(LOW, trivial, speculative — no action needed yet)*
- [ ] **Verify the 0.6 dot-opacity thinning reads legibly on the `unemp` lens specifically** — this
      cycle's headless check only screenshotted `drisk`; `unemp`'s legend/color ramp is visually
      similar but wasn't independently screenshotted, so it inherits the fix by code-path but not by
      pixel-verification. *(LOW, trivial)*

## Queue — follow-ups noticed 2026-07-04 (3)
- [ ] **The Overture 14-bucket taxonomy (`factory`/`auto`/`retail`/…) is now hand-copied in at least
      three places** — `build_national_places.py`/`build_scene_places.py` (via their shared
      `source-data/occupation_places_named.json` `buckets` list), `build_occupations.py`/
      `build_amphoe_occupations.py`'s branch/amphoe occupation shares, and now
      `tests/validate_data.py`'s new `KNOWN_PLACE_BUCKETS` constant. Nothing currently asserts these
      three copies stay in sync — a future taxonomy change (a 15th bucket, a rename) in the source
      Overture pull could silently diverge from what the validator expects vs. what
      `occupation_leads.json`/`branch_occupations.json` actually carry. Worth a single shared
      bucket-list constant (or a cross-check in `validate_data.py` comparing `KNOWN_PLACE_BUCKETS`
      against whatever bucket list `branch_occupations.json`'s meta declares) next time either
      taxonomy is touched. *(LOW, S)*
- [ ] **`_check_places_payload()` (new this cycle, `tests/validate_data.py`) and the existing
      `check_catchment_poi()` validate near-identical shapes** (meta+label+points-in-bbox) but with a
      swapped point order (`[lng,lat]` vs `[lat,lng]`) and slightly different meta-key names — same
      duplicate-helper smell already queued for `drawAmphoeChoropleth`/`drawProvinceChoropleth` on the
      frontend side (2026-07-03 (6)/(9)); a shared `_check_point_layer(payload, order=...)` could
      collapse both. *(LOW, S, pure refactor)*

## Queue — follow-ups noticed 2026-07-04 (4)
- [ ] **`branch_density.json`'s 134 `empty_0` branches are ALL in Bangkok/Rayong** (per the source
      `perimeter_counts.json` commit message) — a genuine capped-pull artifact, not a real "no
      buildings" reading. Once Bangkok/Rayong get true province-wide Overture catchments (the
      "more tiles" ask in `docs/TONIGHT_CHECKLIST.md` §A), re-run
      `pipeline/build_branch_density.py` — those 134 zeros should mostly clear. *(LOW, S, blocked
      until the Thai-laptop tile pull lands)*.
- [ ] **`bldgDensityPopupHTML()`'s bucket color/label ramp was picked to visually match the existing
      `poiRelevancePopupHTML()` palette, not independently contrast-checked** — same low-priority
      "not measured against a contrast bar" smell already logged for the 0.6 dot-opacity choice
      (2026-07-03 (9)). *(LOW, trivial)*
- [x] **`build_branch_density.py`'s bucket-tally self-check (`AssertionError` on drift) is the only
      builder in the pipeline that hard-crashes instead of failing `--check` cleanly — DONE
      2026-07-04 (5)** (new `BucketDriftError`, caught in `main()` → clean `CHECK FAIL: ...` +
      exit 1, same convention as every other builder; verified via a hand-corrupted-then-restored
      `perimeter_counts.json`. Gate 46/0.)

## Queue — follow-ups noticed 2026-07-04 (5)
- [x] **The bare-`assert`-on-malformed-data pattern fixed in `build_branch_density.py` this cycle
      also exists in `build_national_places.py`/`build_scene_places.py` — DONE 2026-07-04 (6)**
      (both now print `CHECK FAIL: ... malformed` + exit 1 instead of an uncaught `AssertionError`;
      zero behavior change on the happy/SKIP paths, verified by hand. Gate 46/0.)
- [ ] **The "vendor numpy/shapely/rasterio into the sandbox's default setup" backlog item (below,
      still open) cannot be done FROM the improvement loop itself** — a session-start-hook /
      `.claude/hooks` change is agent self-configuration, out of scope for a platform-improvement
      cycle and blocked by the auto-mode policy (confirmed this cycle: creating `.claude/hooks/`
      was denied as "self-modification... not user-authorized"). This needs Kaustav (or a session
      with explicit hook-authoring intent) to set it up once outside the standing loop, e.g. via the
      `session-start-hook` skill or the environment's Dockerfile/setup config — not a future loop
      cycle retrying the same path. *(LOW, S, needs a human/out-of-loop session, not blocked-data)*
- [ ] **`docs/PROGRESS_LOG.md` and `docs/DATA_REFRESH_LOG.md` have diverging numbering for the same
      day** (e.g. today's cycles are `(2)`–`(5)` in one file and `(2)`/`(4)` in the other, tracking
      independent counters) — not a bug, but a reader cross-referencing "2026-07-04 (4)" has to know
      which file it lives in. Worth a one-line convention note in `CLAUDE.md` (or a shared per-day
      counter) if this ever causes real confusion; no action needed today. *(LOW, trivial,
      speculative)*

## Queue — follow-ups noticed 2026-07-04 (6)
- [ ] **`_check_places_payload()`/`check_catchment_poi()` in `tests/validate_data.py` still validate
      near-identical shapes with swapped point order and different meta-key names** (this is the
      2026-07-04 (3) duplicate-helper note, still open) — now that BOTH `build_national_places.py`
      and `build_scene_places.py` share the identical "malformed → CHECK FAIL" one-liner added this
      cycle, a small shared `_fail_if_malformed(d, required_keys, label)` pipeline helper could also
      collapse that duplication alongside the validator-side one. *(LOW, trivial, pure refactor)*
- [ ] **`build_national_places.py`'s `GRID=0.02` national fallback density has never been visually
      compared against a per-city `_places.json` at the same zoom** — worth a quick headless render
      of a province WITHOUT a committed catchment file (relies on the national fallback) to confirm
      the POI mat still reads as "dense" and not visibly sparser than Rayong/Bangkok/Chiang Mai's
      per-city files, now that both builders share hardened malformed-data handling. *(LOW, S)*
- [ ] **Vendor `numpy`/`shapely`/`rasterio` into the sandbox's default setup** remains the single
      highest-value low-effort infra gap (see the existing entry above) — still needs a human/
      out-of-loop session (session-start-hook or environment Dockerfile), not another loop cycle
      retrying the same blocked path. *(LOW, S, needs a human/out-of-loop session)*

## Queue — follow-ups noticed 2026-07-04 (7)
- [ ] **`docs/DATA_SOURCES.md`'s OAE "Dec-2025 outlook" sentence (rice+rubber=2026 RISK crops;
      cassava/palm/chicken/durian firmer) is now the oldest un-re-verified citation in that file** —
      unlike the Pink Sheet block above it (just corrected to 2026M06), this line has never been
      checked against a fresher OAE pull. OAE (`catalog.oae.go.th`) is REACHABLE from this sandbox
      per the same doc's own reachability matrix — a future ENRICH cycle could pull the current OAE
      outlook note and either confirm or update this sentence with a real citation. *(LOW, S)*
- [x] **Add a lightweight doc/data consistency check to `tests/validate_data.py` — DONE 2026-07-04
      (8)** (new `check_doc_vintage()`: reads the live vintage off `meta.json.updated`, greps
      `DATA_SOURCES.md`'s "current read (VINTAGE prices)" header + `DATA_PROVENANCE.md`'s "currently
      `VINTAGE prices`" phrase, fails on mismatch; scoped to those two live-claim anchors, not a
      whole-doc scan, so it doesn't false-positive on the audit logs' legitimate historical mentions
      of the old stale vintage. Verified against a hand-corrupted vintage. Gate 47/0, validate_data
      421/421).

## Queue — follow-ups noticed 2026-07-04 (8)
- [ ] **`check_doc_vintage()`'s two anchors are hand-picked regexes tied to exact current phrasing**
      ("current read (...)" / "currently `...`") — if either doc's live-claim sentence is ever
      reworded (not just re-vintaged), the check fails loudly with a clear message telling the editor
      to update `_DOC_VINTAGE_ANCHORS`, which is the intended fail-safe behaviour, but it's worth
      knowing this is a deliberate trade-off (brittle-but-loud beats silent) if a future doc rewrite
      trips it for a non-drift reason. *(LOW, trivial, informational)*
- [ ] **The same vintage-drift class could recur for other cited-vintage docs** beyond the Pink
      Sheet (e.g. NSO SES/LFS vintages quoted in `docs/DATA_SOURCES.md`'s household-debt/unemployment
      sections, or the OAE "Dec-2025 outlook" line flagged as unverified in the 2026-07-04 (7)
      follow-up) — once one of those layers gets a real refresh, the same anchor-and-compare pattern
      (`check_doc_vintage()`) could extend to a 2nd vintage family. Not needed until a refresh
      actually happens. *(LOW, S, speculative)*
- [ ] **OAE outlook re-verification (from 2026-07-04 (7), still open)** — pull the current OAE
      (`catalog.oae.go.th`, REACHABLE) outlook note and confirm/update `docs/DATA_SOURCES.md`'s
      "OAE Dec-2025 outlook" sentence (rice+rubber=2026 RISK; cassava/palm/chicken/durian firmer),
      the oldest un-re-verified citation in that file. *(LOW, S)*

## Queue — follow-ups noticed 2026-07-05
- [x] **`renderHomeThesis()`'s board-thesis sentence still doesn't cite `PSTRESS_LIST[0]` — DONE
      2026-07-05 (4)** (thesis clause now prefers the DTI+unemployment composite, falling back to raw
      DTI then crop-stress as before; `loadProvinceStress().then()` now also re-renders the thesis so
      it updates once the composite lands. See `docs/PROGRESS_LOG.md` 2026-07-05 (4) entry).
- [ ] **`drawAmphoeChoropleth()`/`drawProvinceChoropleth()` near-duplicate functions** (flagged
      2026-07-03 (6)/(9), still open) — a shared `drawChoropleth({features,keyFn,valFn,...})` helper
      would remove the duplication before a 3rd choropleth resolution is added; this cycle's Exposure
      change reused `ccRow()` rather than duplicating markup, which is the same instinct applied
      preemptively — worth doing the equivalent consolidation on the choropleth pair. *(LOW, S, pure
      refactor)*
- [x] **A parallel "structurally riskiest" callout for objective #2 (expansion) — ALREADY SHIPPED,
      stale duplicate found during the 2026-07-05 (4) audit.** This entry asked for a rank-1
      "where is the clearest expansion signal right now" callout on `#acq` — but `renderAcqVerdict()`
      (`platform/app.js`, gold `#acq-verdict` card, shipped in commit `7fb5d5f`, well before this
      backlog note was written) already renders exactly that: "🏆 Open next: `<top district>` —
      `<score>`/100 opportunity · `<rivals>` rivals ≤5km" sourced from `opportunity_score.json`'s
      rank-1 district. Confirmed live via `grep`+`git log -S` before touching anything; no code
      changed, left checked rather than rebuilding duplicate UI.
- [x] **`provinces/<slug>.json`'s new `meta.provenance` block (2026-07-05) doesn't yet get its own
      `validate_data.py` check — DONE 2026-07-05 (5)** (new `check_province_provenance()`: reads all 77
      slugs off `provinces/index.json`, asserts `meta.generated_by` + `meta.provenance.
      {measured,editorial,estimated}` are present and non-empty on every file; verified it actually
      catches drift by hand-deleting one province's `provenance.editorial`, confirming a real FAIL,
      then restoring. Gate 52/0, `validate_data.py` 429/429).
- [ ] **Headless render of `province.html`/`rayong-catchment.html` is unreliable in this sandbox under
      software WebGL** (3 consecutive attempts this cycle all failed with `ERR_CONNECTION_REFUSED` or
      an empty screenshot, even after killing stray chrome/http.server processes between tries) — this
      echoes the already-documented `rayong-catchment.html` flakiness (2026-07-02 (2) log entry) but
      now also affects the plain-Leaflet-adjacent `province.html`. Worth a `tests/lib/render.sh`
      retry-loop (it already has a 4x retry per its own header comment — confirm it's actually being
      exercised) or a longer settle budget before concluding a render genuinely regressed vs. the
      harness just being flaky in this container. *(MED, S — blocks a fast confidence check on future
      province-page cycles)*

## Queue — follow-ups noticed 2026-07-05 (2)
- [ ] **`fuel_prices.json` only ever carries a single day's snapshot** (the Bangchak API has no
      in-API history) — `delta_tomorrow` is wired into the source file but not yet surfaced anywhere
      in the UI, and there's no YoY/trend read until the daily workflow (`data-fuel-prices.yml`,
      running since 2026-07-05) has accumulated enough committed snapshots to diff. Once ≥2 dated
      pulls exist, worth surfacing "diesel +X% since <date>" the same way `deltas.json` drives the
      Risk-trend card's sparklines. *(LOW, S, blocked on time — needs 2+ vintages)*
- [ ] **`renderHomeMacro()`'s new Fuel-prices row sits in the same card as "Key commodity moves"
      (World Bank) but has a structurally different vintage model** (daily point pull vs. monthly
      Pink Sheet) — today this is disambiguated only by the "Bangchak retail, daily" sub-label; if a
      3rd differently-cadenced macro source is ever added to this card, worth a shared "as of <date>"
      chip per sub-section instead of relying on prose alone. *(LOW, trivial, speculative)*

## Queue — follow-ups noticed 2026-07-05 (4)
- [ ] **Before picking a "stale UX gap" item from this backlog, `grep`/`git log -S` the claimed
      function name FIRST** — this cycle's audit found a 2nd instance (after the 2026-07-04 (9)
      audit found six) of a backlog entry describing a UI gap that was already shipped
      (`renderAcqVerdict()` for the objective-#2 rank-1 callout, live since `7fb5d5f`). A ~30-second
      grep before implementing would have caught it immediately; worth internalizing as a standing
      first-step for "UX gap noticed" items specifically, not just full backlog-hygiene passes.
      *(LOW, trivial, process note)*
- [ ] **`renderHomeThesis()`'s "strongest single opening" clause still doesn't distinguish the
      sequenced Road-to-3,000 plan (`EXPLAN.sequence[0]`) from the opportunity-score fallback
      (`OPPSCORE`) in its wording** — both render as "the strongest single opening is `<name>`" with
      no tag telling the reader which method produced it, unlike the "risk to watch" clause (now
      correctly distinguishes composite/DTI/crop-stress by construction). A small win once someone's
      touching this function again: only add the distinguishing word if a real ambiguity is reported
      — the two rarely disagree today. *(LOW, trivial, speculative)*
- [ ] **OAE outlook re-verification — NOT a CKAN item, re-scope before retrying (checked 2026-07-05
      (5))** — confirmed `catalog.oae.go.th` IS reachable from this sandbox (`package_search`/
      `group_list`/`package_list` all return 200), so the earlier "blocked" assumption was wrong. But a
      full sweep of the catalog's 57 datasets and its 8 groups (incl. `price` = ราคาสินค้าเกษตร) found
      **zero** discoverable outlook/forecast document — searches for แนวโน้ม/สถานการณ์สินค้าเกษตร/
      outlook all returned 0 results, and the `price` group itself has 0 packages tagged. The cited
      "OAE Dec-2025 outlook" sentence in `docs/DATA_SOURCES.md` almost certainly traces to a
      www.oae.go.th **news/press-release page**, not a CKAN dataset — a fundamentally different pull
      (HTML scrape of a Thai gov news site, no CKAN API to lean on) with real risk of citing the wrong
      page. Do NOT retry this as "just re-run pull_oae_prices.py's search pattern" — that pattern only
      finds farm-gate PRICE series, not qualitative outlook notes. If revisited, budget for finding the
      actual news URL first (may need a targeted web search, not a catalog query) before attempting any
      text extraction. *(LOW, M — harder than previously scoped, not a quick win)*
- [ ] **`pipeline/pull_oae_prices.py` — ROOT CAUSE FOUND 2026-07-05 (4), re-scope before touching
      again.** It's not stuck, throttled, or silently failing: `data-oae-prices.yml` (and every other
      `schedule:`-triggered workflow in this repo — `data-fuel-prices.yml`, `data-nabc-prices.yml`,
      `data-macro.yml`, `site-health.yml`) **has never run once**, because none of them are merged to
      `master` yet. Confirmed via the `github` MCP server: `list_workflows` shows only `QA` registered
      for this repo (it self-registers via its `push:`/`pull_request:` triggers, which don't require
      the default branch); `list_workflow_runs(data-oae-prices.yml)` returns a plain 404. `git fetch
      origin master && git ls-tree origin/master` confirms `master` still only has the pre-import
      single-page site (`index.html`, `vercel.json`, `.env`) — PR #1 ("Import platform…", open since
      2026-06-28) has never merged. GitHub Actions only discovers `schedule:` workflows from files
      present on the default branch, so nothing here can fire until that PR merges. The two "daily"
      pulls that DO exist today (`fuel_prices.json`, `nabc_prices.json`) were each landed by a single
      Claude session committing directly, not by their workflow executing — real data, but a **frozen
      one-time snapshot**, not an active recurring refresh; don't treat their `pulled:` date as
      "current" without checking. **Do NOT keep re-diagnosing the puller from the loop** — the fix is
      entirely outside this sandbox's scope (merging PR #1 is Kaustav's call, flagged via
      `PushNotification` this cycle); once merged, re-check `list_workflows`/`list_workflow_runs` to
      confirm the crons actually start firing, then this item can close. Full writeup:
      `docs/DATA_REFRESH_LOG.md` (2026-07-05 (4)). *(BLOCKED on a human merge decision, not sandbox-
      solvable — do not pick this up again until PR #1's status changes)*

## Queue — follow-ups noticed 2026-07-05 (6)
- [ ] **Is PR #1 still unmerged? — RE-CHECKED 2026-07-05 (7), still unmerged, no change.**
      `mcp__github__list_pull_requests(state=open)` shows PR #1 still open (not draft), and
      `mcp__github__actions_list(list_workflows)` still shows only `QA` registered — same state as
      2026-07-05 (4). Leaving this item open (not checking off) since the underlying blocker hasn't
      moved; a future cycle should keep re-checking early in ORIENT per the note below. *(LOW,
      trivial — just a status check, do first if picking a data-freshness item)*
- [ ] **`drawAmphoeChoropleth()`/`drawProvinceChoropleth()` near-duplicate functions — still open,
      re-scoped after inspection 2026-07-05 (6).** Read both functions this cycle before considering
      picking this up: they're less "near-duplicate" than the backlog title suggests — one is keyed by
      amphoe `id` (via `ampIndex()`) and supports a categorical dominant-crop branch (`cat:true`) with
      richer popups (branch count, crop share), the other is keyed by province `name` off `PGEO`
      features with a simpler popup and no categorical path. A shared `drawChoropleth({features,
      keyFn, valFn, popupFn, cat})` helper is still doable but is a real M-effort generalization, not
      the S/mechanical merge implied by the LOW/S tag carried since 2026-07-03 (6) — flag as MED effort
      if picked up, and diff-test both lenses (`hhdti`, `pstress`, `dws`, `drisk`, `unemp`, the
      dominant-crop lens) pixel-by-pixel before/after, since this paints on every National-map polygon
      lens. *(LOW→MED, re-scoped, pure refactor)*
- [ ] **`renderAcqVerdict()`'s hero card and the newly-reordered "Road to 3,000" section both open
      with a bold headline claim** (this cycle moved Road to 3,000 to lead the tab, right under the
      verdict card) — worth a quick look at whether the verdict card and the Road-to-3,000 summary
      line ever say something that reads as contradictory (e.g. verdict names a Central&BKK district
      while Road-to-3,000's biggest regional allocation is Isan) now that they sit back-to-back at the
      top of the page. Not observed as an actual conflict this cycle (screenshot showed Central&BKK
      district `วัฒนา` in the verdict vs. Isan +247 in Road to 3,000 — different questions, arguably
      fine as-is), just flagging the new visual adjacency for a future UX pass. *(LOW, trivial,
      speculative)*

## Queue — follow-ups noticed 2026-07-05 (7)
- [ ] **OAE farm-gate price pull — RE-CONFIRMED dead end 2026-07-05 (7), do not retry the CKAN
      search path again without a new plan.** Ran `pipeline/pull_oae_prices.py --selftest` (30/30
      parse-logic assertions pass, offline) then `--dry-run` (real network — `catalog.oae.go.th` is
      reachable) to re-check the 2026-07-05 (5) "harder than scoped" finding with fresh evidence.
      Queried `package_search` directly for the exact search term (`ราคาที่เกษตรกรขายได้`) plus 5
      broader terms (`ราคา`, `ราคาสินค้าเกษตร`, `ข้าวเปลือก`, `ยางแผ่นดิบ`, `farmgate`, `price`): the
      whole catalog returns at most **6** results for any of these, and **none** is a per-crop
      farm-gate price time series with a CSV/XLSX/datastore resource for our 6 target crops (rice,
      rubber, sugarcane, oil palm, cassava, maize) — the puller's own top-ranked match
      (`มูลค่าผลผลิตสินค้าเกษตรที่สำคัญ`, "value of important agri products") ships **JSON-only**
      metadata with no priced series inside, and the next-best match
      (`มูลค่าของผลไม้เมืองร้อน`, "value of tropical fruits") is off-topic (fruit, not our crops).
      This is not a transient catalog gap — it's the same conclusion the 2026-07-05 (5) audit reached
      (no discoverable outlook/forecast doc either), now confirmed for the *price* search path too.
      **Leave `build_crop_stress.py` on the World Bank GLOBAL proxy** (already honestly labelled) —
      a real fix needs either a Thai-IP `data.go.th` pull (`docs/TONIGHT_CHECKLIST.md` §4) or finding
      the actual OAE news/report URL by hand, not another sandbox CKAN search retry. *(BLOCKED —
      sandbox CKAN search path exhausted, needs a Thai-IP pull or manual URL discovery)*
- [x] **Two stale-duplicate backlog entries found and closed this cycle** (Competitor coverage QA
      panel; NSO census occupation distiller scaffolding) — see the `[x]` corrections above in the
      "Queue — enrichment / capabilities" section, both already shipped (`build_competitor_coverage.py`
      2026-06-30; `ingest_gov.py`'s `build_occupations_census()` commit `7fd4994` 2026-06-30) but never
      checked off. Zero code/data changed — pure backlog hygiene.

## Queue — follow-ups noticed 2026-07-10 (3)
- [x] **★ `docs/COMMITTEE_ASSESSMENT_2026-07-10.md` finding #3 — dws lens provenance mislabel —
      DONE 2026-07-10 (3)** (`LENS.dws` `tag:'m'`→`'e'` + `est:true`; `amphoePopupHTML()` rows/caption
      reworded "measured"→"est (measured inputs)". Zero data changed. Gate 61/0. See
      `docs/PROGRESS_LOG.md` 2026-07-10 (3).)
- [x] **Committee findings #4/#5 — DONE 2026-07-10 (4)** (`renderMacroIndicators()` idempotency guard
      via a `.mcard-bis` marker class so two quick tab switches no longer double-append the BIS/World
      Bank macro cards; Home's "Competitor coverage" row no longer says "lower-bound census" at 141%
      coverage — copy now switches to "network fully located for the official-locator brands — Heng
      still a sample" whenever `coverage_pct>=100`, matching `#market`'s own explanation. Deliberately
      did NOT touch `build_competitor_coverage.py`'s Srisawad `expected` figure itself — nulling a
      real cited number felt like hiding data rather than explaining it, and the actual visible defect
      (self-contradictory Home copy) is fully fixed without a data-schema change; left as a narrower
      follow-up below if a future cycle wants the pipeline-side polish too. Gate 61/0,
      `validate_data.py` 453/453 [unaffected, UI-only]. See `docs/PROGRESS_LOG.md` 2026-07-10 (4).)
- [x] **The committee report's other 8 "smallest first" build items — DONE, shipped in `917ff47`
      ("Sprint 1 trust fixes: vendor map libraries + committee P0 findings"), never checked off here —
      caught and reconciled 2026-07-10 (5) AUDIT.** Verified live (not just the commit message) before
      checking off: (1) findings #2/#7 — `platform/app.js:1946` `renderAcqVerdict()` now reads
      "🏆 Highest-composite district: `<name>`" with a bridge sentence pointing at the sequenced
      Road-to-3,000 plan as the canonical placement order; (2) finding #8 — `app.js:2787` zero-state
      copy replaces the red "0.0%" high-stress cards on `#exposure`/`#sim` with a neutral headroom
      read when nothing clears the threshold this vintage; (3) finding #1, vendoring Leaflet 1.9.4 +
      deck.gl 8.9.35 — `platform/vendor/{leaflet,deck.gl.min.js}` exist and all 4 pages
      (`index.html`/`province.html`/`rayong-catchment.html`/`branch-explorer.html`) load from
      `vendor/` not a CDN; `boot()`'s catch block now distinguishes a library-load failure from a
      data-load failure. `bash tests/run.sh check` reconfirmed green (64/0) after the checkoff — no
      code touched, this is a backlog-accuracy fix only, same audit pattern as 2026-07-04 (9)/
      2026-07-05 (7). See `docs/PROGRESS_LOG.md` 2026-07-10 (5).
- [ ] **`build_competitor_coverage.py`'s Srisawad `expected` figure is now nulled for the scope
      mismatch (fixed in `917ff47`)** — the totals/`coverage_pct` are computed over comparable brands
      only (102.9%), so the previously-flagged "457% invalid ratio" concern below is resolved; leaving
      this pointer in case a future reviewer wants to confirm the nulled-Srisawad shape reads cleanly
      on `#market`'s per-brand table (not independently re-verified pixel-by-pixel this cycle, only
      via the source JSON + app.js read path). *(LOW, trivial, informational — supersedes the item
      below)*
- [ ] **`renderMacroIndicators()`'s `.mcard-bis` idempotency-guard pattern (shipped `917ff47`) is
      worth reusing** — any other lazy-loaded card block that does `insertAdjacentHTML('beforeend',...)`
      on a host also written by a synchronous `innerHTML=` reset earlier in the same render function
      (same race: two quick renders before the async `.then()` fires) could have the identical
      double-append bug. Worth a quick `grep insertAdjacentHTML.*beforeend` audit of app.js next time
      someone's in this area — not done this cycle (scope discipline), just flagging the class of bug
      now that one instance is confirmed real. *(LOW-MED, S, speculative — audit only, no known 2nd
      instance yet)*
- [ ] **`docs/PROGRESS_LOG.md` has no entry for `917ff47` ("Sprint 1 trust fixes") or the 5
      subsequent `Sprint 2 E0 (1)–(5)` commits (`8cf4f78`…`e53705d`, household DTI/labour-context/
      truck-flow/macro-sensitivity joins into `build_amphoe.py`'s district risk score + a new
      `decision_queue.json`/`renderDecisionQueue()` surface)** — these commits are real, already on
      `origin/claude/new-session-wto26j`, and gate-passing (confirmed `bash tests/run.sh check` 64/0
      on the current HEAD), but appear to be from a different concurrent session/workflow ("Sprint 2")
      that hasn't written its own PROGRESS_LOG entries. Not backfilled this cycle — the loop only logs
      its own work, and writing a log entry for someone else's uninspected diff risks
      mischaracterizing it. Worth a future AUDIT cycle reading those 5 diffs end-to-end and writing the
      log entries their own convention calls for, OR flagging to Kaustav if "Sprint 2 E0" is a
      human-run workflow that should own its own logging. *(MED, S, informational — docs-debt, not a
      code defect)*

## Queue — follow-ups noticed 2026-07-09 (7)
- [x] **★ PR #1 merged — verify the newly-live scheduled workflows actually produce a green run —
      DONE 2026-07-10.** `list_workflow_runs` on all 9 non-QA workflows found 3 had already ticked, all
      3 failed. Fixed one for real (`site-health.yml`'s `BASE_URL` was an SSO-gated Vercel preview
      alias, not the public site — swapped to `competitive-intel-blue.vercel.app`, re-verified 29/29
      real checks pass). Root-caused but did not fix the other two (`data-fuel-prices.yml`/
      `data-nabc-prices.yml` — both do real work then fail at `gh pr create` on a repo Settings toggle,
      see the new item below). Full writeup: `docs/PROGRESS_LOG.md` (2026-07-10 entry).
- [ ] **Now that `master` has the full pipeline + committee, the sandbox-vs-CI story changes** — some
      backlog items previously scoped as "needs a Thai-IP pull, blocked" (DIW factories, DLT vehicles)
      are exactly what `data-gov-census.yml` now runs on a schedule from GitHub's own runners (already
      proven reachable per CLAUDE.md's CKAN breakthrough). Once that workflow has a green run, its
      *output* (fresh `factories_by_district.json`/`vehicles_by_province.json`) should get pulled back
      into this branch's `source-data/` and re-derived — a real, non-speculative data refresh, not
      just a workflow existing. *(MED, M, blocked until the workflow's first run lands)*
- [x] **Home's risk card (`renderHomeRisk()`) "more" toggle — DONE 2026-07-10 (2)** (had grown to 9
      stacked blocks, not 7 — audited fresh this cycle. Kept the 3 sharpest verdicts always visible
      [composite risk, DTI+unemployment, riskiest branch]; collapsed the remaining 6 into a native
      `<details class="cc-more">` "Show N more", reusing `methodBox()`'s existing disclosure idiom
      instead of building a new toggle+JS-state mechanism like the National map's "More lenses ▾" —
      simpler, zero new wiring. Print stylesheet forces it open so the exec one-pager keeps full
      content. Gate 61/0, `validate_data.py` 453/453 [unaffected, UI-only]. Headless-rendered
      `#home`: `data-errors="[]"`, screenshot confirms 3 lead rows + "Show 6 more ▾". See
      `docs/PROGRESS_LOG.md` 2026-07-10 (2).)

## Queue — follow-ups noticed 2026-07-05 (8)
- [x] **`occupation_income.json`'s national aggregate could feed the Simulator's occupation-
      sensitivity lever — DONE 2026-07-06 (3), scoped as an additive read rather than a formula
      change.** Rather than discounting `simFactoryModel()`'s existing uplift math (real regression
      risk to an already-shipped lever), added a new `pipeline/build_factory_income.py` →
      `platform/data/factory_income_by_province.json` (per-province NSO SES FactoryWorkers income +
      ratio_to_national) and a 4th, purely-additive "Below income-floor · measured" card
      (`simFactoryIncomeFloor()`) naming how many manufacturing-base branches sit in an
      already-below-average factory-income province. Zero change to the existing scenario numbers.
      Gate 54/0. See `docs/PROGRESS_LOG.md` 2026-07-06 (3).
- [ ] **`occupation_income.json` is unweighted-mean across provinces (a small province counts the
      same as Bangkok)** — labelled honestly in `meta.caveats`, but if this callout ever needs to
      answer "which occupation pays least for the AVERAGE WORKER nationally" rather than "for the
      average PROVINCE", it would need population-weighting (branch-count or NSO labor-force
      weights are already in the pipeline elsewhere, e.g. `unemployment_by_province.json`'s
      labor-force column) — not needed today, the province-level read is honest as scoped. *(LOW,
      S, speculative)*
- [x] **The Home command-center (`#home`) now surfaces the same "lowest-paid occupation
      nationally" fact — DONE 2026-07-06** (`renderHomeRisk()` gained the identical `OCCINC_LIST[0]`
      row already shipped on `#exposure`, wired `loadOccupationIncome()` into Home's lazy-load chain;
      zero new data/pipeline, pure UI reuse. Gate 53/0, headless-rendered `#home`, `data-errors="[]"`,
      no layout regression. See `docs/PROGRESS_LOG.md` 2026-07-06.)

## Queue — follow-ups noticed 2026-07-06
- [ ] **Home's risk card (`renderHomeRisk()`) now has 6 stacked blocks** (composite-risk verdict,
      DTI+unemployment structural read, lowest-paid occupation, riskiest single branch, worst
      crop-household stress, moto-heavy collateral) — each addition so far has been a small additive
      row, but the card is getting long enough that a future UX pass may want to demote 1-2 of the
      more niche reads (e.g. moto-collateral) behind a "more" toggle, the same way the National map's
      lens picker collapses into "More lenses ▾". Not a problem yet — flagging before it becomes one.
      *(LOW, S, speculative)*
- [x] **Audit whether any other Exposure-only rank-1 callout is still missing from Home — DONE
      2026-07-06 (2)** (compared `renderRiskReadouts()` against `renderHomeRisk()`/
      `renderHomeWhitespace()` block-by-block: Home's risk card already had parity/superset on every
      objective-#1 callout, but the objective-#2 side was missing "Most contested ground"
      (`renderContestedGround()`'s rank-1 fact, `contested_pop.json`, measured) — the flip side of the
      white-space callouts already on Home. Ported the rank-1 row + wired `loadContestedPop()` into
      Home's lazy-load chain, null-safe. Gate 53/0, headless-rendered, `data-errors="[]"`. See
      `docs/PROGRESS_LOG.md` 2026-07-06 (2).)
- [ ] **Is PR #1 still unmerged? — RE-CHECKED 2026-07-06, still unmerged, no change.**
      `mcp__github__list_pull_requests(state=open)` still shows PR #1 (`claude/new-session-wto26j` →
      `master`) open, not draft, created 2026-06-28. Every `schedule:`-triggered GitHub Actions
      workflow in this repo remains dormant until it merges (see the 2026-07-05 (4)/(6)/(7) writeups)
      — this is Kaustav's call, not sandbox-solvable. Re-check again next cycle before picking up any
      "why hasn't the scheduled puller fired" item. *(LOW, trivial — just a status check)*

## Queue — follow-ups noticed 2026-07-06 (3)
- [ ] **⚠ SECURITY — a real-looking `.env` file with non-empty API key values (`DATA_GO_TH_TOKEN`,
      `NSO_TOKEN`, `BOT_API_KEY_*`, `GISTDA_API_KEY`, `ORS_KEY`, `GOOGLE_PLACES_KEY`) is committed on
      `origin/master` and `origin/claude/brave-goodall-je1xfj`** (added via "Add files via upload" /
      "Rename .env.txt to .env", NOT this branch's history) — the file's own header comment says
      "the .env file is git-ignored — it stays on your machine and is NEVER committed", so this
      looks like an accidental upload rather than an intentional commit. Sandbox policy blocks
      reading/printing the values (confirmed this cycle — a `git show origin/master:.env` was denied
      by the auto-mode classifier as credential materialization), so provenance/validity of each key
      couldn't be further inspected from here. **Out of this loop's scope** (different branches,
      needs a human call: rotate every listed key, then either purge the blob from git history or
      accept it as already-exposed) — flagged to Kaustav via `PushNotification` this cycle, not
      something a future loop cycle should attempt to fix directly (this loop only ever touches
      `claude/new-session-wto26j`, and history-rewrite/key-rotation are both explicitly
      human-authorization-required actions). *(HIGH, needs a human, cross-branch — do not action
      from the loop)*

## Queue — follow-ups noticed 2026-07-06 (4)
- [x] **`build_factory_income.py`'s pattern (per-province occupation income → ratio_to_national)
      only covers `FactoryWorkers` — DONE 2026-07-09** (`pipeline/build_agri_income.py` mirrors it for
      the `Agriculture` column → `platform/data/agri_income_by_province.json`; Simulator's
      crop-price/rainfall what-if gained a 4th "Below income-floor · measured" card
      (`simAgriIncomeFloor()`), read-only context alongside the existing ESTIMATED agri-stress
      scenario. `OfficeStaff`/`SMEOwners`/`Transport` columns remain unused — see new follow-up below.
      Gate 55/0. See `docs/PROGRESS_LOG.md` 2026-07-09.)
- [ ] **`simFactoryIncomeFloor()`'s sample is tiny today (only 2 manufacturing-dominant branches
      nationally, per `occupation_risk.json`)** — same "dark-until-data" ceiling already logged for
      the underlying occupation-risk lens; this card will only become a meaningful read once the
      Overture occupation pull broadens past the current 2-branch sample. No action needed, just
      noting the same caveat applies one layer up. *(LOW, trivial, speculative)*
- [x] **`factory_income_by_province.json`'s per-province `ratio_to_national` could also surface on
      `province.html`'s "Who works nearby" income panel — DONE 2026-07-09 (2)** (`build_province.py`
      now joins `gov.income_floor.{factory,agri}_ratio_to_national` from the already-committed
      `factory_income_by_province.json`/`agri_income_by_province.json`; `province.html`'s Agriculture
      and Factory-workers income bars show a "(X% of national avg)" annotation. Gate 55/0. See
      `docs/PROGRESS_LOG.md` 2026-07-09 (2).)

## Queue — follow-ups noticed 2026-07-06 (2)
- [ ] **`CPOP.top[0]`'s contested share can be a rounded 100%** (as seen this cycle: a 4.59M-person
      catchment reads as fully contested) — worth double-checking whether a near-100% contested
      reading on Home's new "Most contested ground" row ever needs a distinguishing caveat (e.g. dense
      Bangkok catchments where every rival brand physically overlaps look identical to a hypothetical
      data bug) before treating it as fully self-explanatory; today's number is real and traces
      correctly to `contested_pop.json`, just flagging the visual for a future UX pass. *(LOW, trivial,
      speculative)*
- [ ] **Home's whitespace card (`renderHomeWhitespace()`) now has 4 stacked blocks** (top districts,
      top provinces, competitor coverage, contested ground) — same "card getting long" pattern already
      flagged for the risk card (2026-07-06 entry above); not a problem yet, but if a 5th block is ever
      added, worth doing the "more" toggle for both cards at once rather than one at a time. *(LOW, S,
      speculative)*
- [ ] **`renderHomeWhitespace()`'s new contested-ground row and `renderHomeHero()`'s existing
      "Open next in `<district>`" verdict could theoretically point at the same or an adjacent place**
      (a top-opportunity district that also happens to be heavily contested) — not observed as an
      actual conflict this cycle (contested-ground rank-1 was a dense Bangkok branch, unrelated to the
      Ko Pha-Ngan/Ko Kut Road-to-3,000 openings shown in the hero), just flagging the new visual
      adjacency the same way the 2026-07-05 (6) note did for the Acquisition tab's verdict card vs.
      Road-to-3,000. *(LOW, trivial, speculative)*

## Queue — follow-ups noticed 2026-07-09
- [x] **`build_agri_income.py`/`build_factory_income.py`'s pattern still left `SMEOwners` unused —
      DONE, shipped in `daf6d38` (logged this cycle, 2026-07-09 (4)).** New
      `pipeline/build_sme_income.py` → `platform/data/sme_income_by_province.json` (77 provinces,
      national_avg ฿33,299/mo, 47 below floor); `build_province.py`'s `gov.income_floor` join gained
      `sme_ratio_to_national`; `province.html`'s "Income by occupation" panel now annotates the SME
      owners row with "(X% of national avg)". `OfficeStaff`/`Transport` remain the only unused NSO
      SES columns — see the new follow-up below.
- [x] **`sme_income_by_province.json`'s `sme_ratio_to_national` only surfaces on `province.html` —
      the Exposure/collateral tabs had no income-floor read — DONE 2026-07-09 (5)** (`renderRiskReadouts()`
      gained a "Merchant segment income floor · SME owners" block, new `loadSmeIncome()`/
      `smeincHasData()`/`SMEINC_LIST` lazy-load pair mirroring `loadOccupationIncome()`'s shape; worst
      province + "N/77 below floor" count. Zero new pipeline/data. Gate 56/0, headless-rendered
      `#exposure`, `data-errors="[]"`. See `docs/PROGRESS_LOG.md` 2026-07-09 (5).)
- [ ] **`OfficeStaff`/`Transport` are now the only 2 of 5 NSO SES occupation columns with no
      `build_*_income.py` ratio layer** (`Agriculture`, `FactoryWorkers`, `SMEOwners` all wired as of
      `daf6d38`). Same builder shape, different column; only worth building once a concrete UI surface
      wants it (Simulator has no transport/office-staff lever today). *(LOW, S, speculative)*
- [ ] **`simAgriIncomeFloor()`'s scope is all agri-relevant provinces (`CSTRESS_LIST`), not just the
      currently high-agri-stress ones** — this is a deliberate design choice (mirrors
      `simFactoryIncomeFloor()`'s all-manufacturing-branches scope, gives a stable MEASURED baseline
      independent of the price/rain sliders), but worth a second look if a future reviewer expects
      the income-floor count to move when the crop-price/rainfall sliders are dragged — today it
      correctly does NOT move, by design (context, not scenario). *(LOW, trivial, informational)*
- [ ] **Is PR #1 still unmerged? — RE-CHECKED 2026-07-09, still unmerged, no change.**
      `mcp__github__list_pull_requests(state=open)` shows PR #1 (`claude/new-session-wto26j` →
      `master`) still open, not draft, created 2026-06-28 — same state as every prior recheck since
      2026-07-05 (4). Every `schedule:`-triggered GitHub Actions workflow remains dormant until it
      merges. Not re-flagging via `PushNotification` again (already surfaced repeatedly); a future
      cycle should keep re-checking early in ORIENT per the standing note, but stop re-notifying
      unless the state actually changes. *(LOW, trivial — just a status check)*

## Queue — follow-ups noticed 2026-07-09 (3)
- [ ] **★ `tests/baseline/*.png` (the `tests/run.sh visual` regression check) is stale since
      2026-06-29 and needs a human-reviewed refresh.** AUDIT this cycle (full writeup:
      `docs/PROGRESS_LOG.md` 2026-07-09 (3)): running the full `tests/run.sh` found the `visual`
      phase fails on **all 8** manifest pages (mean_diff 27–211, tolerance 12), including pages this
      cycle never touched (`index`/`national`/`risk-trend` at ~200+) — the baseline PNGs were captured
      once in the QA-harness-add commit and never regenerated across the 124 subsequent commits that
      redesigned the app (dark-theme overhaul, 2-col dashboards, nav rework, docked 3D control frame,
      etc.). `bash tests/run.sh check` (the mandated loop gate) is unaffected — it doesn't run
      `visual` — but the full suite and `tests/run.sh visual` specifically give 100% false-red today,
      which could mislead a future cycle into thinking a real change caused a regression (this cycle
      almost did). **Do not have the loop blindly run `tests/run.sh baseline` to fix this** — that
      regenerates the reference images from whatever's currently rendered, which only proves anything
      if a human (or a very deliberate side-by-side review) confirms the current renders are actually
      correct first; committing wrong-but-fresh baselines would make the check permanently
      rubber-stamp future regressions. Needs either Kaustav's sign-off on the 8 current renders, or a
      dedicated future cycle that renders all 8, screenshots them for review here in a message/
      artifact, and only then runs `baseline`. *(MED, S-to-run/M-to-verify, needs a
      human-in-the-loop review step)*
- [ ] **Is PR #1 still unmerged? — RE-CHECKED 2026-07-09 (2), still unmerged, no change.** Same
      `mcp__github__list_pull_requests(state=open)` check, same result as the entry directly above
      (checked twice this cycle, once at ORIENT and once before this new item). Not re-flagging.
      *(LOW, trivial — just a status check)*
- [x] **The new `gov.income_floor.{factory,agri}_ratio_to_national` field on `provinces/<slug>.json`
      has no dedicated `validate_data.py` check — DONE 2026-07-09 (6)** (new
      `check_province_income_floor()`: for all 77 provinces, asserts every present
      `gov.income_floor.{factory,agri,sme}_ratio_to_national` sits in a sane (0,5) range AND exactly
      matches the corresponding source file's own `ratio_to_national` for that province — closes the
      join-integrity gap, not just a value-range gap. Verified it actually catches drift by
      hand-corrupting `bangkok.json`, confirming a real FAIL, then restoring from git. Gate 56/0,
      `validate_data.py` 446/446. See `docs/PROGRESS_LOG.md` 2026-07-09 (6).)
- [ ] **`province.html`'s new "(X% of national avg)" ratio annotation color threshold (`<1` → red,
      else muted grey) was picked for readability, not contrast-checked** — same low-priority
      "not measured against a contrast bar" smell already logged for the National map's 0.6
      dot-opacity choice (2026-07-03 (9)) and the branch-density bucket colors (2026-07-04 (4)).
      *(LOW, trivial)*
- [ ] **`build_province.py`'s new income_floor join only covers Factory/Agriculture** — `Transport`/
      `SMEOwners`/`OfficeStaff` still have no corresponding `build_*_income.py` ratio layer (same gap
      flagged 2026-07-09 for the Simulator side); if a future cycle builds `build_transport_income.py`
      or `build_sme_income.py`, this cycle's join pattern (`build_province.py` reading
      `platform/data/<x>_income_by_province.json`) extends directly, no new mechanism needed.
      *(LOW, S, speculative — needs the builder first)*

## Queue — follow-ups noticed 2026-07-09 (5)
- [x] **The same rank-1-worst-province pattern could extend to Home (`renderHomeRisk()`) — DONE
      2026-07-09 (7)** (`renderHomeRisk()` gained the identical `SMEINC_LIST[0]` "Merchant segment
      income floor · SME owners" row already shipped on Exposure; wired `loadSmeIncome()` into Home's
      lazy-load chain, null-safe. Home's risk card is now a 7th stacked block deep — the "more" toggle
      idea flagged below/2026-07-06 is worth doing before an 8th block is added. Gate 59/0,
      headless-rendered `#home`, `data-errors="[]"`, real data confirmed in DOM. See
      `docs/PROGRESS_LOG.md` 2026-07-09 (7).)
- [ ] **`OfficeStaff`/`Transport` are still the only 2 of 5 NSO SES occupation columns with no
      `build_*_income.py` ratio layer** (Agriculture/FactoryWorkers/SMEOwners now all wired end-to-end
      — pipeline → province.html → Exposure for SME). Same builder shape, different column; only
      worth building once a concrete UI surface wants it (no Transport/office-staff lever exists in
      the Simulator or Exposure today). *(LOW, S, speculative)*
- [ ] **`renderRiskReadouts()`'s risk-readout block is now 4 stacked rank-1 callouts deep** (most-stressed
      provinces table, DTI+unemployment, lowest-paid occupation, SME income floor) before the riskiest-
      branches table — same "card getting long" pattern already flagged for Home's risk/whitespace cards
      (2026-07-06). Not a problem yet (each is a single compact `cc-row`, not a full card), but if a 5th
      rank-1 fact is ever added here, worth considering the same "more" toggle treatment. *(LOW, trivial,
      speculative)*
- [x] **Is PR #1 still unmerged? — CHANGED 2026-07-09 (7): MERGED at last.** See the top-of-file
      2026-07-09 (7) entry — `master` now has the full platform + all 9 `schedule:` workflows
      registered `active`. This item is closed; the new follow-up is tracking whether the crons
      actually produce a green run (below).

## Queue — follow-ups noticed 2026-07-09 (6)
- [ ] **`check_province_income_floor()` (new this cycle) reads all 77 `provinces/<slug>.json` files
      in full to do the join check** — same pattern `check_province_provenance()` already uses (no
      sampling, unlike `check_provinces()`'s `PROVINCE_SAMPLE`), so this isn't a new perf class, just
      noting the validator now has two full-77-file scanners; fine at today's file sizes (a few KB
      each) but worth remembering if `provinces/<slug>.json` ever grows much heavier. *(LOW, trivial,
      speculative)*
- [x] **The same source-vs-join verification pattern (`check_province_income_floor()`) could extend
      to `gov.vehicles`/`gov.employment`/`gov.unemployment`/`gov.income`** on `provinces/<slug>.json` —
      DONE 2026-07-10 (6)** (new `check_province_gov_joins()` in `tests/validate_data.py`: exact-dict
      compare of each of the 4 pass-through joins against their `source-data/*.json` row, keyed by
      Thai province name; SKIP-passes when no source layer present. Verified it catches real drift by
      hand-corrupting `bangkok.json`'s `unemployment_rate`, confirming a FAIL, then restoring. Gate
      64/0, `validate_data.py` 463/463. See `docs/PROGRESS_LOG.md` 2026-07-10 (6).)
- [ ] **Is PR #1 still unmerged? — RE-CHECKED 2026-07-09 (6), still unmerged, no change.**
      `mcp__github__list_pull_requests(state=open, head=claude/new-session-wto26j)` shows PR #1 still
      open, not draft, created 2026-06-28 — same state as every prior recheck since 2026-07-05 (4).
      Not re-notifying (no change). *(LOW, trivial — just a status check)*

## Done (most recent first)
- (loop will append here)
- **2026-07-10 (5) — AUDIT: backlog reconciliation, the committee's 8 "smallest first" items had
  already shipped in `917ff47` ("Sprint 1 trust fixes") but were never checked off.** See
  `docs/PROGRESS_LOG.md` 2026-07-10 (5).
- **2026-07-10 (3) — UX: fixed the dws (Opportunity/district white-space) map lens's MEASURED→
  ESTIMATED provenance mislabel** (committee finding #3). See `docs/PROGRESS_LOG.md` 2026-07-10 (3).
- **2026-07-10 — AUDIT: PR #1 merged — the standing "every scheduled workflow is dormant"
  blocker (tracked across 10+ recheck entries since 2026-07-05 (4)) is now CLOSED.**
  `mcp__github__list_pull_requests` shows PR #1 merged into `master` 2026-07-10 01:42 +07
  (commit `ad91123`); `master` now carries the full `platform/`/`pipeline/`/`.github/workflows/`
  tree. `list_workflows` confirms all **9** `schedule:` workflows (`data-fuel-prices`,
  `data-gov-census`, `data-macro`, `data-nabc-prices`, `data-oae-prices`, `data-overture`,
  `data-tiles`, `committee-geocode`, `site-health`) are now registered/active alongside `QA` —
  up from just `QA` at every prior recheck. None has fired yet (`list_workflow_runs` = 0 for
  `data-gov-census`/`data-overture`; first schedule tick is still pending — `data-gov-census` is
  weekly Mon 02:40 UTC). Attempted a manual `workflow_dispatch` on `data-gov-census.yml` (the
  highest-value pull — DIW factories + DLT vehicles via department CKAN catalogs, safe by
  design: throwaway copy of the master, writes only to a fresh `data/gov-census-<run_id>` branch
  + draft PR, never touches `master`/working branches) to get real data landing sooner than the
  weekly cron — got `403 Resource not accessible by integration` (this session's GitHub token
  isn't scoped for `workflow_dispatch`). Confirmed `source-data/factory_census_national.json` /
  `vehicle_census_province.json` genuinely don't exist yet, so nothing to fold in this cycle.
  **RE-DERIVE baseline**: fresh checkout, `bash tests/run.sh check` → 56 passed, 0 failed
  (`validate_data.py` 446/446) before touching anything; re-ran every builder named in the
  routine (`derive.py`, `build_amphoe.py`, `build_province.py`, `build_crop_stress.py`,
  `build_occupations.py`/`build_amphoe_occupations.py` — both correctly `SKIP` (no
  `overture_places.json` yet), `build_opportunity_score.py`, `ingest_tmli.py`) — all `--check`
  green, tree already fully in sync, zero data changed. Also noted a second open PR
  (`#2`, draft, `claude/new-session-wto26j` → `master`, CKAN round-2 + POI source-map docs) —
  unrelated to this finding, not touched. **Next step for whoever picks this up next:** either
  wait for the Monday 02:40 UTC cron, or have Kaustav manually dispatch `data-gov-census.yml`
  from the GitHub UI (he has the permission this session's token lacks) to pull DLT
  vehicles/DIW factories sooner — this is the single highest-value real-data unlock left,
  replacing an ESTIMATED collateral-supply/TAM proxy with MEASURED gov data (both objectives).
  Flagged to Kaustav via push notification this cycle. Full writeup: `docs/DATA_REFRESH_LOG.md`
  (2026-07-10 entry).
- **2026-07-09 (4) — AUDIT: logged a prior cycle's shipped-but-undocumented ENRICH (SME-owner income
  floor), closed the backlog item.** `daf6d38` (already committed + pushed) shipped
  `pipeline/build_sme_income.py` → `platform/data/sme_income_by_province.json` (77 provinces,
  national_avg ฿33,299/mo, 47 below floor), `build_province.py`'s `gov.income_floor` join gaining
  `sme_ratio_to_national`, and a `province.html` annotation on the SME-owners income row — but step 7
  (log + backlog checkoff) never ran. No code/data changed this cycle; re-verified fresh:
  `build_sme_income.py --check` + `build_province.py --check` byte-exact, `bash tests/run.sh check`
  56/0 (`validate_data.py` 445/445). PR #1 re-confirmed still open/unmerged (no change, not
  re-notified). Full writeup: `docs/PROGRESS_LOG.md` (2026-07-09 (4) entry).
- **2026-07-09 — ENRICH: MEASURED agriculture-worker income floor context on the Simulator
  (objective #1).** New `pipeline/build_agri_income.py` mirrors `build_factory_income.py`'s pattern
  for the NSO SES `Agriculture` income column → `platform/data/agri_income_by_province.json` (77
  provinces, national_avg ฿23,486/mo, 49 below the national floor). Simulator's crop-price/rainfall
  what-if gained a 4th, purely-additive "Below income-floor · measured" card
  (`simAgriIncomeFloor()`), read-only context alongside the existing ESTIMATED agri-stress scenario
  — zero change to existing scenario numbers. `validate_data.py` gained `check_agri_income()`;
  `tests/run.sh` gates the new builder's `--check`; `build_provenance.py` re-run (measured layers
  23→24). Gate 55/0. Headless-rendered `index.html#sim`: `data-errors="[]"`, new card renders real
  data, no layout regression. Re-confirmed PR #1 still unmerged (no change). Full writeup:
  `docs/PROGRESS_LOG.md` (2026-07-09 entry).
- **2026-07-06 — AUDIT: closed `docs/DATA_PROVENANCE.md`'s R6, the last open provenance-register
  gap.** The 7 OSM ground-bed geometry files (`rayong_landuse/roads/water/rail.json`,
  `bangkok_landuse/roads/water.json`) were genuine 100%-measured OSM data sitting on
  `tests/validate_data.py`'s `PROVENANCE_EXEMPT` list with zero in-file `meta` — same gap class R2/R3
  closed for the `*_catchment.json` building files on 2026-07-04, never done for the ground layers.
  Added real `meta.{city,source,bbox,note,n_features,committed_in}` to all 7 (facts read from git
  history + each pull script's own bbox/preset — zero fabrication, byte-diff confirms the underlying
  geometry arrays are unchanged). Updated `pull_rayong_ground.py`/`pull_rayong_extra.py`/
  `pull_city_3d.py` so future re-pulls keep emitting this meta. `PROVENANCE_EXEMPT` narrowed to just
  `rayong_province.json`; `provenance.json` regenerated (unlabelled 8→6, measured 20→22). Gate 53/0,
  `validate_data.py` 433/433. Re-confirmed PR #1 still unmerged (no change). Full writeup:
  `docs/DATA_REFRESH_LOG.md` (2026-07-06 entry).
- **2026-07-05 (7)/PROGRESS_LOG numbering — ENRICH: national lowest-paid-occupation callout on
  Exposure.** `pipeline/build_occupation_income.py` aggregates the already-MEASURED
  `household_income_by_province.json` (NSO SES 2566) into a national worst-first ranking by
  occupation category (national avg + concrete min/max province, not just an average).
  `#exposure` gained a "Lowest-paid occupation nationally" callout (Transport ฿18,547/mo avg,
  worst แม่ฮ่องสอน ฿6,713/mo). `--check`-gated, `validate_data.py` +5 checks (433/433), gate 53/0.
  Headless-rendered, `data-errors="[]"`, no regression. Full writeup: `docs/PROGRESS_LOG.md`
  2026-07-05 (7).
- **2026-07-05 (7) — AUDIT: RE-DERIVE baseline confirmed green, closed 2 stale backlog duplicates,
  re-confirmed the OAE farm-gate dead end + PR #1 unmerged status, both with no change.** Full
  writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-05 (7) entry).
- **2026-07-05 (4) — AUDIT: root-caused why the OAE puller (and every scheduled data workflow) has
  never fired.** Not a bug in the puller — `PR #1` (importing this whole platform on top of the old
  single-page site) has been open since 2026-06-28 and never merged to `master`, so `master` still
  has no `pipeline/`/`platform/`/`.github/workflows/` at all. GitHub Actions only discovers
  `schedule:`-triggered workflows from the default branch; confirmed via the `github` MCP
  (`list_workflows` shows only `QA` registered; `list_workflow_runs(data-oae-prices.yml)` → 404).
  Every `schedule:` workflow in this repo (`data-fuel-prices.yml`, `data-nabc-prices.yml`,
  `data-macro.yml`, `data-oae-prices.yml`, `site-health.yml`) has therefore never executed once; the
  two "daily" pulls that exist (`fuel_prices.json`, `nabc_prices.json`) were one-off manual commits,
  not live recurring refreshes. Docs-only fix (zero data/pipeline changed); flagged to Kaustav via
  push notification since merging PR #1 is a call only he can make. Full writeup:
  `docs/DATA_REFRESH_LOG.md` (2026-07-05 (4)).
- **2026-07-05 (3) — ENRICH: live Bangchak fuel prices wired into the Home macro card.** New
  `pipeline/build_fuel_prices.py` projects the already-committed `source-data/fuel_prices.json`
  (real Bangchak retail pull, unwired since commit `ea93b96` this morning) verbatim into
  `platform/data/fuel_prices.json`; `renderHomeMacro()` gained a measured "Fuel prices" row (diesel
  = pickup/farm collateral, gasohol95 = motorcycle collateral). `--check`-gated (SKIP when the pull
  is absent), `validate_data.py`/`build_provenance.py` extended. Gate 50/0, `validate_data.py`
  426/426. Headless-rendered `index.html#home`: `data-errors="[]"`, live diesel ฿37.5/L + gasohol
  ฿37.45/L render under "Key commodity moves". Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-05
  (3) entry).
- **2026-07-05 (2) — AUDIT: closed `docs/DATA_PROVENANCE.md`'s R1 provenance gap.** Every
  `platform/data/provinces/<slug>.json` (77 files) now carries its own `meta.generated_by` +
  `meta.provenance.{measured,editorial,estimated}` block naming every field's real source (PIP
  branches/POI, DIW factories, DLT vehicles, NSO workers/unemployment/income, deduped competitor
  census, editorial narratives) — mirrors `build_amphoe.py`'s existing pattern. `index.json`
  deliberately left a bare array (6+ frontend call sites fetch it directly as an array; wrapping it
  would be a breaking change for a docs-only gain). Zero data values changed — byte-diff confirms only
  the new `meta` key was added; `build_province.py --check` reproduces byte-exact. Gate: 47/0,
  validate_data 421/421. Headless-render of `province.html?p=rayong` was attempted 3x and failed each
  time under this sandbox's software WebGL (new follow-up logged above) — unrelated to this change
  (zero HTML/JS touched); the mandated `bash tests/run.sh check` gate is green. Full writeup:
  `docs/DATA_REFRESH_LOG.md` (2026-07-05 entry).
- **2026-07-05 — UX: structural household-leverage callout on the Exposure tab.** `renderRiskReadouts()`
  in `platform/app.js` gained a "Structurally riskiest · household DTI + unemployment" block (rank-1
  `PSTRESS_LIST[0]` from the already-MEASURED `province_stress_index.json`), inserted between "Most-
  stressed provinces" and "Riskiest branches". Reused existing `ccRow()`/`TAG_E` helpers and the
  existing `pstressHasData()`/`loadProvinceStress()` plumbing — no new data file, no new pipeline
  script, purely additive. Closes the 2026-07-03 (4)/(9) follow-up asking for this pattern on
  Exposure. Gate 47/0 (`validate_data.py` 421/421, unaffected — UI-only change). Headless-rendered
  `index.html#exposure`: `data-errors="[]"`, block renders real data (อำนาจเจริญ, DTI 1.14×,
  unemployment 2.8% NSO-measured, composite ▲98), no layout regression. Full writeup:
  `docs/PROGRESS_LOG.md` (2026-07-05 entry).
- **2026-07-04 (9) — AUDIT: backlog reconciliation, "Queue — UX / polish" had gone stale.** No code
  changed. Spot-checked the committee's quick-wins/bigger-bets list against the live app (headless
  renders of `#home`/`#map`/`#overview`/`#exposure`/`#acq` + `git log -S` on the claimed labels) and
  found 6 items already shipped in commits dated 2026-06-30/07-01 but never checked off: QW1 (map
  hero), QW2 (full-bleed canvas), QW3 (nav fix), QW5 (home verdict — since grown well past its
  original spec into a ranked decision queue), QW8 (Risk-trend baseline), and the "★ 2-col dashboards"
  bigger bet. Also found the separate "Composite expansion-opportunity score" enrichment item was a
  stale duplicate of the already-shipped `build_opportunity_score.py`/`opportunity_score.json`. Left
  genuinely-open items open (QW4/QW6 — both confirmed still outstanding and correctly owned by other
  workflows; "Reduce prose" — not independently verifiable either way, left as-is rather than
  guessing). A stale backlog risks a future cycle re-analyzing or re-building work that already
  shipped — this keeps the standing loop's queue trustworthy. `bash tests/run.sh check` unaffected
  (docs-only change): 47/0 before and after.
- **2026-07-04 (8) — AUDIT: closed the two remaining unsourced-catchment provenance gaps
  (`docs/DATA_PROVENANCE.md` R2/R3).** `rayong_catchment.json` and `chiang-mai_catchment.json`
  (180,000 real Overture building footprints each, commits `9482b0e`/`373b4f0`) shipped with
  **zero embedded `meta`** — source was known (git history) but a reader of the file couldn't tell.
  Added a real `meta` block to both (city/n_bldg/source/note/committed_in, same style as the
  already-provenanced `bangkok_catchment.json`) — zero building/geometry values changed, no
  fabrication (`n_bldg`/commit facts verified against `git log` before writing). Also caught that
  `bangkok_catchment.json`'s register row was itself stale (claimed "no source" when the file
  already has `meta.source`) — corrected the doc instead of the data. `PROVENANCE_EXEMPT` in
  `tests/validate_data.py` tightened (removed 2 entries that no longer need a blanket exemption);
  provenance gate now reads 276 sourced / 90 exempt (was 274/92). Gate: 47/0, `validate_data.py`
  421/421 (unchanged pass count — provenance-label fix, not a new check). `slim_catchment.py --check`
  confirmed unaffected. Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-04 (8) entry).
- **2026-07-04 (7) — AUDIT: `docs/DATA_SOURCES.md` + `docs/DATA_PROVENANCE.md` quoting the
  pre-refresh (stale) World Bank Pink Sheet vintage, corrected to the already-committed 2026M06
  data.** No data value changed — both docs were still asserting Dec-2025 figures (rice −19.5%, gold
  +62.7%, vintage label `2025M12`) two days after commit `adf5494` had already regenerated
  `source-data/commodities*.json` / `platform/data/meta.json` to the real 2026M06 values. Every
  replacement number was copied verbatim from the already-committed source files (no external pull,
  no fabrication). Gate: `bash tests/run.sh check` 46/0 before and after (docs-only change,
  `validate_data.py` 265/265 unaffected). Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-04 (7)
  entry).
- **2026-07-04 (4) — ENRICH: MEASURED building-density-within-10km layer (Overture, sitting unused
  since 2026-07-02) wired into the branch popup.** New `pipeline/build_branch_density.py` projects
  `source-data/perimeter_counts.json` (orphaned since commit `dda7816`, never consumed by any
  builder or `app.js`) → `platform/data/branch_density.json`; one new popup line, no new lens
  (scope discipline). Alignment safety verified by hand: `branches.json`'s `branches_fingerprint`
  at `dda7816` (2026-07-02) matches the fingerprint of today's `branches.json` exactly, despite two
  intervening data refreshes — the index alignment was never at risk. `validate_data.py` gained
  `check_branch_density()` (265/265, was 259/259); gate 46/0. Headless Playwright evaluation of the
  real in-page popup functions confirms branch #0 renders `buildings_10km=8, bucket=sparse_1_49`
  matching the data file exactly, zero JS errors. Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-04
  (4) entry).
- **2026-07-04 (3) — VALIDATOR: `national_places.json` + `<city>_places.json` Overture "dense POI"
  layers gained data-integrity coverage.** These files (`build_national_places.py`/
  `build_scene_places.py`, shipped by concurrent 3D-lane workflows) had a determinism gate in
  `tests/run.sh` but zero sanity check in `validate_data.py`. New `check_national_places()` /
  `check_scene_places()` validate meta/bucket-taxonomy/bbox/point-order/point-count, SKIP-pass when
  absent. Caught a false-positive in development (module's tighter `TH_LAT_MIN=5.5` bbox constant
  wrongly flagged ~1,800 genuine near-border factory points at lat 5.40–5.47 as "wrong order"; fixed
  by using the same wider 5.0–21.0 bbox already used by `check_catchment_poi`/`check_lead_sites`).
  Pure test-file change, no `platform/data`/`pipeline` touched. Gate 45/0, `validate_data.py` 259/259
  (+2 checks). Full writeup: `docs/PROGRESS_LOG.md` (2026-07-04 (3) entry).
- **2026-07-04 (2) — AUDIT: `household-debt.js`'s `debtToIncome`/`stressIndex` mislabelled MEASURED,
  actually UNVERIFIED.** No CKAN/BOT resource id cited (unlike every other TMLI-vendored layer);
  values hand-grouped under narrative headers (same smell as the 2026-07-02 GPP catch); diverges
  10-20x from the fully-cited ratio the app already computes and ships
  (`household_risk_by_province.json`). Confirmed the unverified fields were never consumed downstream
  — caught before any fabricated-looking number reached the app. Corrected provenance in
  `ingest_tmli.py`/`source-data/tmli/PROVENANCE.md`/`docs/NEXT_STEPS.md`/`docs/DATA_PROVENANCE.md`;
  zero data values changed (diffed: meta-only). Gate 42/0, `validate_data.py` 224/224 (unchanged —
  this source layer sits upstream of the gated `platform/data` tree). Full writeup:
  `docs/DATA_REFRESH_LOG.md` (2026-07-04 (2) entry).
- **2026-07-04 — UX: district (amp) lenses get the same choropleth dot-thinning as province lenses.**
  `platform/app.js`'s `styleMarkers()` now thins dot `fillOpacity` to 0.6 for `isProvLens(curLens)||
  isAmpLens(curLens)` (was province-only) so `dws`/`drisk`/`unemp`'s district choropleth reads through
  the dots the same way `hhdti`/`pstress`'s province choropleth was fixed to in 2026-07-03 (9). Gate
  42/0 (`validate_data.py` 224/224, unchanged). Headless-rendered `?lens=drisk#map` confirms the fill
  now shows; control render of `opportunity` confirms no regression. Full writeup: `PROGRESS_LOG.md`.
- **2026-07-03 (9) — UX: thinned branch-dot opacity so the province choropleth reads through.**
  `platform/app.js`'s `styleMarkers()` drops marker `fillOpacity` to 0.6 specifically when
  `isProvLens(curLens)` is true (`hhdti`/`pstress`); every other lens keeps 0.9, unchanged. Two-line
  change, no new data/files. Gate 40/0 (`validate_data.py` 211/211, untouched). Headless-rendered
  `index.html?lens=pstress#map` confirms the province fill now reads through the dot layer; a control
  render of the default `opportunity` lens confirms no regression elsewhere. Full writeup:
  `docs/PROGRESS_LOG.md` (2026-07-03 (9) entry).
- **2026-07-03 (8) — ENRICH: NSO SES 2566 per-occupation income surfaced on the province deep-dive.**
  `source-data/household_income_by_province.json` (already vendored + MEASURED, previously only
  consumed as an unweighted mean by `build_household_risk.py`) is now joined into
  `build_province.py`'s `gov` block (`gov.income`, per-province, all 5 NSO occupation categories +
  the existing mean) and rendered in `province.html`'s "Who works nearby" panel: an "Avg household
  income" row + a new "Income by occupation" mini-chart, tagged `measured · NSO SES 2566`
  (deliberately not crossed against the Overture 14-bucket occupation-mix taxonomy — different
  categories, would require an editorial mapping this cycle avoided). No fabrication — byte-identical
  source values; `build_province.py --check` 0 drift; gate 40/0. Headless dump-dom on
  `province.html?p=rayong` confirms `data-errors="[]"` + real sorted THB values render (the WebGL
  screenshot pass hit the known pre-existing swiftshader flakiness, unrelated to this change — see
  the 2026-07-03 (7) render note below). Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-03 (8)
  entry).
- **2026-07-03 (7) — ENRICH: province polygon choropleth for the hhdti/pstress lenses.** New
  `pipeline/build_province_geo.py` groups the already-committed `amphoe_geo.json` polygons by
  `amphoe.json` province_th (no dissolve, no re-simplification) → `platform/data/province_geo.json`
  (77 provinces, `--check`-gated, degrades to SKIP when inputs absent). `hhdti`/`pstress` gained a
  `prov:true` LENS flag + `isProvLens()`/`loadProvinceGeo()`/`drawProvinceChoropleth()` (mirrors the
  amphoe-choropleth pattern), wired into `initMap()`/`setLens()`/`styleMarkers()`. Purely additive,
  null-safe when the file is absent. `validate_data.py` gained `check_province_geo()` (193/193, was
  185/185); gate 37/0. Verified via headless Playwright load (not just a screenshot, since the
  dense opaque branch dots hide the polygon fill at country zoom): `PGEO` = 77 features and
  `provChoroLayer` attaches all 77 province polygons on both `?lens=hhdti` and `?lens=pstress`,
  zero JS errors. `tests/run.sh render` also surfaced a pre-existing, unrelated
  `rayong-catchment.html` render failure (3D page owned by a different in-flight workflow, not
  touched this cycle). Full writeup: `docs/PROGRESS_LOG.md` (2026-07-03 (7) entry).
- **2026-07-03 (6) — AUDIT: fixed a second false-red/false-green gate gap in
  `build_branch_population.py --check` (same bug class as the 2026-07-03 numpy fix, one level
  subtler).** The script has two valid build methods — MEASURED raster sum (needs `rasterio` + the
  committed WorldPop GeoTIFF) preferred, ESTIMATED area-weight (needs only `shapely`) as fallback —
  and only skip-passed `--check` when **both** were unavailable. With `shapely` installed but
  `rasterio` absent (a real sandbox state — `shapely` is a lighter, more commonly pre-installed
  dependency), `build()` silently succeeds via the areaweight fallback and produces a **different but
  valid** JSON than the raster-built file already committed, which `--check` then reported as
  `DRIFT` — a false failure that could have tempted a future cycle to "fix" it by overwriting the
  committed MEASURED file with an ESTIMATED one (exactly the kind of silent regression the
  no-fabrication mandate exists to prevent). Confirmed by installing `rasterio`
  (`pip install --break-system-packages rasterio`): `build_branch_population.py --check` then
  reproduces byte-exact (`method=raster`, 0 drift) — the committed data was never wrong, only the
  gate's partial-dependency handling was blind to a real environment configuration. Fix (code only,
  zero data changed): `run(check=True)` now compares the *committed* file's `meta.method` against
  what this environment can produce; on a method mismatch it prints a distinct `SKIP` (exit 3, same
  convention as the numpy fix) naming exactly which dependency to install to verify for real, instead
  of a `DRIFT` (exit 1); a genuine same-method byte mismatch still fails correctly (hand-corrupted the
  committed file with `rasterio` present and confirmed `--check` still reports `DRIFT`/exit 1, then
  restored from git). `tests/run.sh` now echoes the script's own `SKIP` reason instead of a hardcoded
  (now-inaccurate) "shapely not installed" message, since the missing dependency could be `rasterio`
  instead. Verified all three dependency states by hand (blocking `rasterio` only, blocking both,
  blocking neither) via `builtins.__import__` interception. Gate: 37/0 with `numpy`+`shapely`+
  `rasterio` all installed this cycle (both previously-`[SKIP]`'d checks — `build_branch_peers.py`
  and `build_branch_population.py` — ran for real and passed; was 35/0 with 2 `[SKIP]`s before).
  `validate_data.py` unaffected (181/181, no `platform/data`/`source-data` file touched). Full
  writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-03 (6) entry).
- **2026-07-03 (5) — REFACTOR: amp-lens gating now reads `LENS[k].amp` instead of a 4-site
  hand-maintained OR-chain.** New `isAmpLens(k)` helper in `platform/app.js`; replaced the
  `curLens==='dws'||curLens==='drisk'||curLens==='unemp'` (and `k===` equivalent) checks in
  `drawAmphoeChoropleth()`, `initMap()`'s `deferForAmp`, and both lazy-load triggers in `setLens()`.
  Pure refactor, behaviour-identical (today's `amp:true` lens set already equals the old hardcoded
  list). Removes the whole "dots paint, polygon doesn't" bug class for future amp lenses. Gate:
  35/0 (validate_data 181/181). Headless-rendered `?lens=unemp#map` + `?lens=drisk#map` confirm the
  choropleth still paints, no JS errors. Full writeup: `docs/PROGRESS_LOG.md` (2026-07-03 (5) entry).
- **2026-07-03 (4) — UX: structurally-riskiest province surfaced on the Command Center hero.**
  Added a "Structurally riskiest · DTI + unemployment" row to `renderHomeRisk()`'s risk card
  (`platform/app.js`) using `province_stress_index.json`'s rank-1 province (`PSTRESS_LIST[0]`),
  the same pattern `HHRISK_LIST[0]` already uses for the household-leverage hero line. Wired
  `loadProvinceStress()` into Home's lazy-load chain so it's no longer only reachable via the
  National map's pstress lens. Purely additive, null-safe when the file is absent. Gate: 33/0.
  Headless-rendered `index.html#home` confirms the row (อำนาจเจริญ, composite 98) renders cleanly
  with no JS errors. Full writeup: `docs/PROGRESS_LOG.md` (2026-07-03 (4) entry).
- **2026-07-03 (3) — ENRICH: combined province structural-stress index (household DTI +
  unemployment).** New `pipeline/build_province_stress.py` joins two already-committed MEASURED
  layers — `household_risk_by_province.json` (NSO SES 2566 debt-to-income, itself
  `build_household_risk.py`'s output) and `source-data/unemployment_by_province.json` (NSO Labour
  Force Survey) — into `platform/data/province_stress_index.json`: per province, `composite_stress`
  = 0.5×(DTI percentile) + 0.5×(unemployment percentile), 0–100, worst-first + ranked. All 77
  provinces joined cleanly (both sources already share the canonical 77 Thai-name key). Every
  MEASURED vs ESTIMATED distinction is explicit in `meta` (debt_to_income/unemployment_rate
  MEASURED; both percentiles + the composite ESTIMATED, equal-weighting called out as an editorial
  choice in `meta.caveats`, not calibrated to realized loss). Wired into the National map as a new
  "Province stress ▲ est" menu lens (`pstress` key in `app.js`'s `LENS` registry), following the
  exact `hhdti` lazy-load/legend/absent-guard pattern (own loader, own `lensAbsent` branch, own
  legend block honestly tagged "estimated · NSO SES + NSO LFS blend", warmed unconditionally in
  `initMap()` so `?lens=pstress` deep-links resolve — caught and fixed a first-pass bug via headless
  render where the deep-link path set `curLens` but never called the loader, leaving the legend
  stuck on its loading skeleton). `tests/validate_data.py` gained `check_province_stress()` (meta
  provenance, DTI/unemployment ≥0, percentiles+composite in [0,100], composite formula recomputed
  and compared, rank is a unique 1..77 sequence); `tests/run.sh` gates `build_province_stress.py
  --check`. Headless-rendered `index.html?lens=pstress#map` (screenshot + DOM) confirms the lens
  paints branch dots by composite score and the legend reads correctly — no uncaught JS errors.
  Gate: 32/0, `validate_data.py` 166/166 (was 162/162). Two near-duplicate backlog entries for this
  same idea both checked off. Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-03 (3) entry).
- **2026-07-03 (2) — AUDIT: fixed the `numpy`-missing false-red gate.** `build_branch_peers.py` now
  catches `ImportError` on `numpy` and exits `3` with a "dependency missing, not data drift" message
  instead of an uncaught traceback; `tests/run.sh` reads that code and reports `[SKIP]` (not
  `[FAIL]`), so a fresh sandbox session without `numpy` no longer misreports `branch_peers.json` as
  drifted on cycle 1. Zero data values changed (verified: hand-corrupting `branch_peers.json` and
  re-running with `numpy` installed still correctly fails as `DRIFT`/exit 1). Gate: 30/0 without
  `numpy`, 31/0 with it. Full writeup: `docs/DATA_REFRESH_LOG.md` (2026-07-03 entry).
- **2026-07-02 (3) — ENRICH: NSO unemployment_rate folded into `build_amphoe.py`'s `risk_proxy`.**
  Province-inherited `unemployment_rate` field added to every amphoe record; risk_proxy reweighted to
  0.4·agri_stress + 0.25·collateral + 0.15·merchant + 0.2·unemployment_stress (unemployment scaled
  0-3.0%→0-100, clipped), falling back to 2/3·agri + 1/3·unemployment for zero-branch amphoe.
  `expansion_plan.json` regenerated to match (drift); `branch_peers.json` reproduced byte-identical.
  #acq district-risk table gained an Unemployment column + updated formula copy. Gate: 31/0. Full
  writeup: `docs/PROGRESS_LOG.md` (2026-07-02 (3) entry).
- **2026-07-02 (2) — ENRICH: NSO Labour Force Survey unemployment rate → province deep-dive.**
  `unemployment_by_province.json` (already vendored + MEASURED, previously only surfaced per-branch
  in `branch_labor.json`) is now joined into `build_province.py`'s `gov` block for all 77 provinces
  and rendered in `province.html`'s "Who works nearby" panel (measured · NSO LFS tag). No fabrication
  — byte-identical source values, `build_province.py --check` 0 drift. Gate: 28/0, validate_data
  125/125. Rendered + DOM-verified `province.html?p=rayong` (0.72% Rayong). Full writeup:
  `docs/DATA_REFRESH_LOG.md` (2026-07-02 (2) entry).
- **2026-07-02 — AUDIT: corrected a mislabelled-MEASURED layer before it reached the app.**
  `source-data/gpp_by_province.json` (TMLI-vendored NESDC GPP) claimed MEASURED but only 1/77 rows
  (Mukdahan) is actually CKAN-verified; the other 76 are round-number estimates. Fixed
  `ingest_tmli.py` provenance + added per-row `source` field (values unchanged, byte-diff confirms
  only meta/source changed); corrected `docs/NEXT_STEPS.md` + `docs/DATA_PROVENANCE.md`; logged real
  per-province NESDC pull command in `docs/TONIGHT_CHECKLIST.md` §8. Full writeup:
  `docs/DATA_REFRESH_LOG.md` (2026-07-02 entry). Gate: 28/0, validate_data 125/125.
- **2026-07-01 — Recursive-loop wave (3 concurrent agents, disjoint files, all gate 24/0):**
  (1) **QW2 canvas-fill cleanup** — removed two redundant/conflicting `main{max-width}` rules so the
  already-present full-bleed block (line ~807, `--maxw:1320`) is the single source of truth (behaviour-preserving).
  (2) **Simulator factory-slowdown lever** — new severity slider on `#sim` driving an ESTIMATED occupation-stress
  uplift on manufacturing-dominant branches off the MEASURED `occupation_risk.json` (honest: only 2 branches are
  factory-dominant today; null-safe hide when absent). (3) **P2 Road-to-3,000 rounding** — Total now sums the
  rounded rows (984↔985 fixed). (4) **validate_data +12 checks** for opportunity_score / exit_whitespace / peer_npl
  (98 data checks now). (5) **NSO occupation-distiller** scaffold log-line aligned (inert until the pull lands).
- **2026-07-01 — 3D beauty round (reverted → root-caused):** an in-GL `PostProcessEffect` cinematic grade
  blanked the canvas on real GPU (compiled clean but failed at render) → reverted all 3 pages. Real cause of the
  "white" scene was the DEFAULT basemap being LIGHT (near-white) with pale light-mode building fills washing into
  it → switched all 3 3D pages to the DARK basemap by default (gold buildings pop on black; no white surface).
  LESSON: never ship an in-GL shader change without live visual verification (gate/node --check can't catch a
  runtime shader-compile blank).
- **2026-07-01 — Exec-narrative + interaction + perf:** Home board-thesis sentence + Road-to-3,000 bar; district
  white-space/risk leaderboard rows drill into the National map (fly-to + gold ping); O(1) branch-index for map
  lens repaints (killed O(n²)); print one-pager coverage for the thesis strip; lens help-icon contrast bump.
- **2026-06-30 — White blow-out ROOT-CAUSED & fixed.** The diffuse cap wasn't enough: the culprit was the
  view-dependent SPECULAR term, spiked by auto-orbit sweeping through the sun's reflection angle. Zeroed specular on
  every extruded building/relief/peg across rayong-catchment/branch-explorer/province (lighting now angle-independent
  → no orbit position can clamp to white) + defaulted auto-orbit OFF.
- **2026-06-30 — Competitor store-locator puller** (pipeline/pull_competitor_branches.py) — --discover/--pull/--merge,
  run-from-Thai-IP, harvests the COMPLETE census from operators' own branch-finders (the ~2.5k Google/Overture sets
  cover only ~22% of reality). NO fabrication: brands yielding 0 omitted, coords sanity-checked.
- **2026-06-30 — Streaming Overture building tiles (architecture).** pipeline/build_building_tiles.py (union of 10km buffers
  around all 2,015 branches + 2,556 competitors → Overture pull → tippecanoe → PMTiles/MVT; docs/BUILDING_TILES.md runbook),
  + deck.gl MVTLayer streaming-building layer in rayong-catchment/branch-explorer/province (reads platform/data/tiles_config.json;
  province SWAPS extruded relief for real building scenes when tiles present). Graceful no-op until operator hosts tiles. NEXT
  (desktop, Thai-IP): run RUN_TILES.sh, host the .pmtiles/MVT on a CDN, paste the URL into tiles_config.json.
- **2026-06-30 — White blow-out fixed on ALL 3D pages.** branch-explorer (sun 3.0→0.85, material diffuse 0.95→0.34) and
  province (sun 2.4→0.85, diffuse 0.95→0.34) still had the un-capped lighting that clamps light building colours to white on a
  GPU; applied the rayong-catchment cap everywhere (max lit ≈0.83×).
