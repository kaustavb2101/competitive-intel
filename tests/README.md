# tests/ — AutoX branch-intelligence QA harness

One entrypoint verifies every change to the static platform and the data pipeline. It runs entirely
offline except for the **npm registry** (to self-host deck.gl/leaflet, which the sandbox/CDN cannot
load). **No data pulls** ever happen here.

```bash
tests/run.sh            # full gate: check + render + health + visual   (what CI runs)
tests/run.sh check      # determinism + JS syntax only (fast, no chromium/npm)
tests/run.sh render     # headless-render every page -> tests/.work/render/
tests/run.sh health     # page-health smoke on the last renders
tests/run.sh visual     # compare last renders to tests/baseline/*.png
tests/run.sh baseline   # (re)generate tests/baseline/*.png — run after an INTENDED visual change
```

## What it checks

**1. Determinism + syntax gate (`check`)** — offline.
- `derive.py --check`, `build_province.py --check`, `bake_catchment_heights.py --check` — the
  committed `platform/data/**` must reproduce byte-for-byte from `source-data/`.
- `node --check` on `platform/app.js` and on every inline `<script>` of every `platform/*.html`
  (extracted by `lib/extract_inline_js.py`) — catches JS syntax errors before a browser runs them.

**2. Headless render (`render`)** — npm registry only.
- `lib/render.sh` vendors the npm-installed deck.gl 8.9.35 + leaflet 1.9.4 bundles into a temp
  `platform/_qa_vendor/`, makes a temp copy of each page with the unpkg CDN refs swapped to the
  local bundles **and** a small error/init probe injected, serves `platform/` over http (so
  `fetch('data/…')` works), and screenshots with software WebGL (swiftshader). Cleans up after.
- Basemap raster tiles (cartocdn) are proxy-blocked → **blank basemap is expected**. Building
  geometry, polygons, scatter, text and UI chrome still render.

**3. Page-health smoke (`health`)** — `lib/health.sh` per page asserts:
- no uncaught JS error was captured (the injected `#__qa` probe mirrors errors into the DOM so
  `chrome --dump-dom` can read them back);
- the required library initialised (`deck.DeckGL` / `L.map`);
- the screenshot is non-blank (`lib/pixvar.py`: enough distinct luminances + non-trivial non-blank
  fraction — a crashed/solid page fails);
- at least the expected number of `<canvas>` elements exist;
- every required DOM hook id from the manifest exists and is non-empty.

**4. Visual regression (`visual`)** — `lib/diffpng.py` compares each fresh render to the committed
baseline within a mean-per-pixel tolerance (`QA_VISUAL_TOL`, default 12; swiftshader AA is not
bit-exact). Dimension mismatch fails immediately.

## Pages covered

See `pages.manifest` (the single source of truth — TAB-separated). One row per renderable view,
including the `?params` each needs:

| id                | page + params                                  | lib     |
|-------------------|------------------------------------------------|---------|
| index             | `index.html` (Overview tab — no map)           | none    |
| national          | `index.html#map` (National tab)                | leaflet |
| branch-explorer   | `branch-explorer.html?lat=&lng=&n=` (real pt)  | webgl   |
| province-rayong   | `province.html?p=rayong`                        | webgl   |
| province-chonburi | `province.html?p=chon-buri`                     | webgl   |
| rayong-province   | `rayong-province.html`                          | webgl   |
| rayong-catchment  | `rayong-catchment.html`                         | webgl   |

Add a page by adding a manifest row, running `tests/run.sh baseline`, eyeballing the new PNG, and
committing it.

## Layout

```
tests/
  run.sh              # the single entrypoint (phases: check|render|health|visual|baseline|all)
  package.json        # pins deck.gl@8.9.35 + leaflet@1.9.4 (self-hosted bundles)
  pages.manifest      # every page + params + health hooks
  baseline/*.png      # committed visual-regression reference renders
  lib/
    render.sh           # vendor deps + swap CDN refs + serve + screenshot + dump DOM
    health.sh           # per-page health assertions
    pixvar.py           # pure-stdlib PNG non-blank measure (no PIL/numpy)
    diffpng.py          # pure-stdlib PNG mean-diff for visual regression
    extract_inline_js.py# pull inline <script> blocks out for `node --check`
  .cache/             # npm-installed node_modules (gitignored)
  .work/              # fresh renders + dumped DOM (gitignored)
```

## Env knobs
`QA_BUDGET` (virtual-time ms, default 12000), `QA_SIZE` (default `1100,800`),
`QA_VISUAL_TOL` (default 12).
