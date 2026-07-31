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

## 3. Still unresolved

Ordered by how much confusion each causes, worst first.

1. **The `acq` namespace trap.** ~70 identifiers named `acq*` belong to **Competition** (`#acq`),
   while the nav item reading "Acquisition" points at `data.html`. Anyone reading the code will
   wire the wrong thing to the wrong pillar. Rename the identifiers, not the route (the route is
   load-bearing in bookmarks).
2. **Overview is a wall.** `#overview` has 24 `<h2>` sections, zero `<details>`, and no jump-nav.
   `#acq` solved the same problem with 6 `<details>` plus a jump-nav. Apply that pattern.
3. **`loan_tape_derived.json` is written and never read.** `ingest_loan_tape.py` produces it; no
   page consumes it. Either surface it or retire the write — right now it is a maintained fiction.
4. **Badge collisions on `data.html`.** `L` marks both "The loan book" and "Lens rankings"; the loan
   book is badged `L` nationally but `฿` further down. Badges must be unique or they are noise.
5. **Four data layers are shipped but unread:** `catchments_r2`, `pico_census`, `provenance_sidecar`,
   `rayong_province`. Same question as (3) — surface or retire.
6. **~95 branch names do not match `norm_branch()`**, so they silently fail to join. Small, but it
   is a silent failure, which is the worst kind.

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
