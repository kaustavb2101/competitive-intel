# QA Findings — AutoX / เงินไชโย Credit Intelligence

Regression / visual sweep. Findings only — no code or data was touched. Each finding is
`{severity, page/file, problem, repro, suggested fix}`. Severity: P0 = broken/integrity,
P1 = user-visible defect, P2 = cosmetic/fragility.

---

## 2026-06-30 — full sweep (branch `qa-sweep`, anchored to `claude/new-session-wto26j` @ bd1f668)

### Summary
- **`tests/run.sh check`: PASS** — 15/15 determinism+syntax gates, 37/37 data-integrity checks
  (`validate_data.py`), incl. the provenance gate ("every numeric platform/data layer is sourced
  or documented-exempt — no unsourced data shipped"). No P0.
- **Pages rendered & visually reviewed:** index/Command center, National (Leaflet),
  Risk trend, Acquisition, branch-explorer (deck.gl), province-rayong (deck.gl),
  province-chonburi (deck.gl). All render correctly. rayong-catchment could not be re-rendered
  headless (see P2-1) but its committed baseline confirms the page is healthy.
- **Integrity spot-check: CLEAN.** Two layers traced to real, honestly-tagged sources (details below).
- **Net:** 0 P0, 0 P1, 3 P2. The platform is in good shape; the three items are cosmetic /
  CI-fragility, not blockers.

### Integrity spot-check (hard rule — passed)
1. `platform/data/crop_stress.json` — `meta.generated_by = pipeline/build_crop_stress.py`;
   `crop_mix` tagged **MEASURED (OAE)**, `price_stress` explicitly tagged **PROXY/ESTIMATED**
   (World Bank Pink Sheet GLOBAL prices, "NOT Thai farm-gate"), `drought` from measured branch
   rainfall anomaly, formula fully disclosed in `meta.formula`. No fabricated values.
2. `platform/data/competitors_national.json` — `meta.source = "Google Places Text Search —
   measured competitor locations"`, 2,556 items each carrying a verifiable `place_id`, brands
   limited to the known set (Heng/Muangthai/Srisawad/Tidlor), honestly flagged "a lower bound,
   not a registry."
3. Cross-check of the Command-center commodity figures (Gold +62.7%, Sugar −25.9%, Rice −19.5%)
   traced byte-for-byte to `source-data/commodity_board.json` → `platform/data/meta.json`
   (vintage stamp `2025M12`). The Gold figure shown twice on Command center is the same sourced
   datum re-framed (collateral value ↑ / macro YoY), not a duplicated/invented number.

---

### P2-1 · rayong-catchment.html — heaviest deck.gl scene fails to render headless (CI fragility)
- **Problem:** The 3,631-extruded-building Mueang Rayong catchment scene (25 MB
  `data/rayong_catchment.json`) could not be screenshotted by `tests/lib/render.sh` across 3
  separate attempts (12 chrome passes total), including a reduced 900×650 window with a 30 s
  virtual-time budget. Each attempt returned an empty PNG **and** an empty DOM dump — chrome never
  settled within the wall clock under software WebGL (swiftshader). render.sh's own header already
  documents this scene as the intermittent-empty case; here it was empty on every retry.
- **Why it is NOT a page bug:** the committed `tests/baseline/rayong-catchment.png` is a correct,
  full render (3D buildings, competitor legend AutoX 59 / Srisawad 10 / Tidlor 9 / Muangthai 10,
  acquisition-leads + Top-gaps + recommendations panels, measured·OSM tags). The page is healthy;
  the headless harness wedges on it in low-power/sandbox environments.
- **Repro:** `bash tests/lib/render.sh 'rayong-catchment.html' /tmp/out.png 30000 900,650` →
  `FAIL render … (no screenshot produced)`; `.dom.html` is 0 bytes.
- **Severity rationale:** P2 — `tests/run.sh render`/`visual`/`health` (the full CI gate, not the
  `check` phase used for commits) can intermittently fail on this one page in constrained
  environments, producing a flaky red build. The deployed page itself is fine.
- **Suggested fix:** make the retry count / wall-clock for this row environment-tunable (e.g.
  honor a `QA_HEAVY_BUDGET` and bump retries to ~6 for catchment), or add a documented
  `QA_SKIP_HEAVY=1` escape hatch in `run.sh` so low-power CI can skip the 3,631-building scene
  while still gating the lighter pages. Do not lower the real budget for everyone.

### P2-2 · index.html #acq (Road to 3,000 table) — Headroom column total can exceed the sum of its rows
- **Problem:** In the "Road to 3,000" table the per-region **Headroom est** cells print
  `Math.round(o.headroom)` (app.js:584) while the **Total** prints `Math.round(c.totHr)` where
  `totHr` is the sum of the *un-rounded* per-region headrooms (app.js:591). Rounding-then-summing
  ≠ summing-then-rounding, so the displayed column does not always foot. In the current data the
  column reads 246 + 220 + 219 + 214 + 85 = **984** but the Total cell shows **985** — an
  off-by-one that an exec reading the table will notice.
- **Repro:** open `#acq`, read the Headroom est column vs its Total row; 984 vs 985.
- **Note:** purely a *display* artifact. The actual allocation (the **+ New** column) uses a
  largest-remainder method (app.js:543-547) and sums to exactly +985 / Total 3,000 — that math
  is correct. Only the Headroom est total is cosmetically inconsistent.
- **Suggested fix:** compute the Headroom-est total as the sum of the already-rounded per-region
  values (`regs.reduce((s,o)=>s+Math.round(o.headroom),0)`) so the column foots, or drop the
  Total cell for the Headroom-est column since it is an intermediate, not an allocated, quantity.

### P2-3 · standalone deep-dive pages — reduced nav bar vs the SPA (minor inconsistency, likely intentional)
- **Problem:** `branch-explorer.html`, `province.html`, `rayong-catchment.html` ship a trimmed top
  nav (Overview / National / Rayong 3D / Acquisition / Exposure / Provinces / Market / Branches)
  that omits Command center, Risk trend, Simulator, and Bangkok 3D — tabs that the SPA
  (`index.html`) front door does carry. A user who deep-links straight into a branch/province page
  has no one-click route back to Command center / Risk trend / Simulator from the nav.
- **Repro:** open `province.html?p=rayong` (or any branch-explorer link), compare the nav bar to
  `index.html`'s 13-tab bar.
- **Severity rationale:** P2 — almost certainly a deliberate "lighter nav on the heavy GL pages"
  choice (consistent with the deck.gl/Leaflet split rationale in CLAUDE.md), and the "← National"
  back-link is present. Flagged only so the omission is a conscious decision, not drift. If
  intentional, no change needed.
- **Suggested fix (if undesired):** add Command center / Risk trend / Simulator to the standalone
  pages' nav, or have those pages link back to the SPA hash routes (`index.html#home`, `#trend`,
  `#sim`).

---

### Pages confirmed clean (no findings)
- **Command center (`#home`)** — 4-column exec readout (Where to expand / Riskier / Macro / Risk
  movers), measured-vs-est tags throughout, Thai text legible, no overflow.
- **National (`#map`)** — Leaflet renders all 2,015 branch points (Thailand silhouette visible from
  the scatter; basemap tiles blank = expected/proxy-blocked). Branch + district lens cards carry
  full provenance text.
- **Risk trend (`#trend`)** — correct single-vintage graceful state ("Baseline captured (2025M12) —
  trends appear after the next data refresh"); intended degradation, not a blank panel.
- **Acquisition (`#acq`)** — Road-to-3,000 table well-formed; Now 2,015 + 985 = 3,000 foots; chip
  sub-nav present. (See P2-2 for the lone Headroom-total cosmetic.)
- **branch-explorer.html** — deck.gl scene draws branch label + 10 km ring + measured POI panel;
  shows the correct graceful banner "Building footprints unavailable — showing branch + POI layer"
  when the live OSM building pull is blocked (expected headless).
- **province.html?p=rayong / ?p=chon-buri** — deck.gl district polygons + branch scatter + 10 km
  rings + province-AWARE narrative (Rayong: EV transition / petrochemical; Chon Buri: Pattaya
  tourism / Laem Chabang port) — confirms the narrative generalization is real, not hardcoded.
