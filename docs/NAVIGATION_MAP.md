# Navigation map — every route, what it carries, and what is still unresolved

Written 2026-07-31. Companion to `docs/UXUI_AUDIT.md` (which covers look) — this covers *structure*:
what exists, what overlaps, and what is genuinely load-bearing versus kept alive out of habit.

The gate for this document is `tests/nav_consistency.py`: it asserts all six pages ship one nav,
that the five pillars and the Explore menu match this file, and that no route is unreachable.
If you change the nav, change that test too — otherwise the map silently rots.

---

## 1. The shape

**Five pillars** (primary nav) — the executive journey, in order:

| # | Pillar | Route | What it answers |
|---|--------|-------|-----------------|
| — | Home | `#home` | Everything at once: the command-center readout |
| ① | Macro | `#overview` | What is happening to the economy and our segments |
| ② | Acquisition | `data.html` | The loan book itself — the numbers |
| ③ | Assistance | `#assist` | Who needs help now |
| ④ | Risk | `#exposure` | What is getting riskier |
| ⑤ | Competition | `#acq` | Where the existing network is under pressure |

**Explore ▾** (secondary menu) — the six routes that are tools rather than steps:
`#trend` (Risk trend) · `#map` (Map view) · `#provinces` (Provinces 3D) ·
`data.html?branches` (Branches) · `#market` (Market assessment) · `#sim` (Simulator).

**Standalone pages:** `province.html?p=` (3D district relief) · `rayong-catchment.html?city=`
(3D buildings) · `branch-explorer.html?lat=&lng=` (per-branch 3D) · `status.html` (site health).

**Legacy, deliberately kept:** `#branches` — superseded by `data.html?branches`, which does strictly
more. Kept alive for old bookmarks and asserted as legacy by the gate, so it can never be mistaken
for an orphan.

---

## 2. Can the National map (`#map`) be retired?

**No.** The premise was that if the five pillars already carry the map's data, the map is redundant.
They do not. Audited all 23 lenses:

**Five lenses have no home anywhere else.** Retiring `#map` would delete them outright:

| Lens | Where its data lives | Why it is map-only |
|------|---------------------|--------------------|
| `poirel` | `poi_relevance.json` | Read by `app.js` and nothing else |
| `occrisk` | per-branch occupation risk | Exists only as a map popup value |
| `macx` | per-branch macro exposure | Exists only as a map popup value |
| `dpico` | district PICO coverage | District grain exists only on the map |
| `doutnum` | district outnumbered | District grain exists only on the map |

**Of the remaining 18, only three have full parity elsewhere** (`workers`, `pickups`, `informal`).
Everything else is capped to a top-N list somewhere else in the app — top 40, 25, 15, 12, 6 or 1.
Two examples of how big that gap is: `peerdev` shows **20 of 2,015** branches outside the map;
`brisk` shows **15 of 2,015**.

`data.html`'s "Lens rankings" section claims to carry "the same per-branch and per-district lens
scores the National map colors its dots with". It covers **5 of 23**, capped at top-40, and one of
its four chips reads `d.o` — a retired field no live lens uses. That claim should be narrowed to
what it actually does.

`data.html` also has **no spatial visual at all**, by design. So even for the lenses it does carry,
it answers "which branches rank highest" and never "where are they" — a different question.

**Verdict: keep `#map`.** The honest follow-up is not retirement but reducing overlap — decide per
lens whether the map or a pillar is its home, and stop half-carrying 18 of them in two places.

---

## 3. The six items — all resolved (2026-08-01)

All six were closed in one pass. Kept here with what was actually done, because three of the six
turned out to be **misdiagnosed** and the corrections are worth more than the original notes.

1. ✅ **The `acq` namespace trap.** Identifiers prefixed `acq` belonged to **Competition** (`#acq`)
   while the nav item reading "Acquisition" points at `data.html`. Renamed to two prefixes, because
   two different things were hiding under one: `comp*` for the Competition VIEW (`compjump`,
   `.compsec`, `.compsub`, `competition-impact`) and `gap*` for the coverage-GAP board inside it
   (`gapboard`/`gapchips`/`gaptbl`/`gapregions`/`gapreadout`/`gapcompnote`, `gapRegion`/`gapRows`/
   `gapLegs`/`gapScore`/`gapCSV`, `GAPN`/`buildGapNorms`/`drawGapBoard`/`drawGapRegions`). Plus
   `renderAcq`→`renderCompetition`, `data-acq`→`data-jump`, and `reAcq`→`reAmphoe` — that one was
   named after the wrong board entirely. **The route is untouched**: `#acq`, `data-v="acq"`,
   `id="v-acq"`, the `acq:` keys and `tests/validate_data.py`'s `KNOWN_GO` literal all survive,
   because the route is load-bearing in bookmarks.
2. ✅ **Overview was a wall** — 24 `<h2>`, zero `<details>`, no jump-nav. Now six `<details class="ovsec">`
   plus `#ovjump`, copying the Competition pattern rather than inventing a second one:
   `sec-ov-macro` · `sec-ov-collateral` · `sec-ov-agri` (open) / `sec-ov-labour` · `sec-ov-business` ·
   `sec-ov-hazard` (collapsed). Content is UNMOVED — DOM order is byte-identical, so no renderer
   changed target. The jump-nav handler now delegates on `.jumpnav [data-jump]` instead of binding
   `#compjump` by id, so the next pillar to adopt the pattern does not silently get dead chips.
3. ✅ **`loan_tape_derived.json` written and never read** — retired. `ingest_loan_tape.py` and the file
   are deleted; the real path is `ingest_real_tape.py` → `build_tape_layers.py` → `tape_real.json`.
4. ✅ **Badge collisions on `data.html`.** `L` marked both "The loan book" and "Lens rankings", and the
   loan book was `L` nationally but `฿` at province level. The loan book is now `฿` everywhere and
   `L` belongs to Lens rankings alone. Badges: ฿ / R / P / L — no collisions.
5. ✅ **"Four unread layers" — only ONE was actually unread.** `pico_census` is read by `build_amphoe`,
   `build_baac_credit`, `build_dbd_formation` and `build_peer_province`; `provenance_sidecar` by
   `build_provenance`; `rayong_province` by `build_catchment_poi`, `build_platform`, `build_rayong`
   and it is gated in `tests/run.sh`. Those three are pipeline INPUTS that happen to live under
   `platform/data`, not orphaned UI layers — the original note confused "no page reads it" with
   "nothing reads it". Only `catchments_r2` was genuinely unread, and its silence was causing a real
   lie: because `rayong-catchment.html` could not consult the manifest, every failure printed "3D
   buildings for X haven't been pulled yet", which is FALSE for 74 of 77 provinces (all are served
   from R2; only 3 are also in git). The page now reads the manifest and distinguishes "not pulled"
   from "didn't load", and uses the manifest's `baseUrl` as a CDN fallback.
6. ✅ **Branch names failing `norm_branch()`** — see the commit that closed it for the measured
   before/after. The defect was as much the SILENCE as the misses.

---

## 4. What was fixed getting here

- Two contradictory journeys collapsed into one five-pillar chain (`① of ⑤` … `⑤ of ⑤`).
- Three orphan routes (`#trend`, `#market`, `#sim`) made reachable via Explore ▾.
- Explore's active state never lit up: `#navMoreMenu` is re-parented to `<body>` to escape the nav's
  overflow clipping, so the old `'#nav a'` selector could not see it. Widened to
  `'#nav a[data-v],#navMoreMenu a[data-v]'`.
- `status.html` had a different nav and different naming; unified.
- Three duplicated Home readouts removed (dead `renderHomeRegions` stub and its empty card, the
  `renderRivalIos` alias that double-rendered `#acq`, and `renderHomeDefend` reprinting the full
  Competition table).
- `tests/nav_consistency.py` added and negative-tested against four staged regressions plus an
  orphan-route case.
