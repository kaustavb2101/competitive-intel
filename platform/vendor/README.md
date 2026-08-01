# platform/vendor — the two map libraries, committed

These are unmodified copies of published releases. They are here because the four map pages used to
load them from `unpkg.com` at runtime, which meant a CDN outage, a corporate proxy, or a slow route
out of Thailand rendered the National map and every 3D scene **blank with no explanation** — a
failure indistinguishable from a broken page. Nothing here is our code; do not edit these files.

| file | package | version | SHA256 |
|---|---|---|---|
| `deck.gl-8.9.35.min.js` | `deck.gl` | 8.9.35 | `6ddd95ee72dafb70693f02816accf8a665fa73c40f3fb1a09cb5aa7208377fea` |
| `leaflet/leaflet.js` | `leaflet` | 1.9.4 | `db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a` |
| `leaflet/leaflet.css` | `leaflet` | 1.9.4 | `a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6` |

Each was fetched from unpkg and then **independently re-fetched from jsdelivr and byte-compared**, so
the hashes above reflect two separate CDNs agreeing, not one download. `.gitattributes` exempts this
whole tree from line-ending normalisation (`platform/vendor/** -text`) — without that, git would
rewrite `leaflet.css` on commit and the hash would no longer match upstream.

Re-verify at any time:

```bash
sha256sum platform/vendor/deck.gl-8.9.35.min.js platform/vendor/leaflet/leaflet.js platform/vendor/leaflet/leaflet.css
```

`leaflet/images/` holds the five sprite PNGs (`layers`, `layers-2x`, `marker-icon`,
`marker-icon-2x`, `marker-shadow`). `leaflet.css` resolves them **relative to itself**, so the
`images/` folder must stay beside `leaflet.css` — moving one without the other silently breaks the
layer-control and marker icons.

## Who loads what

| page | library |
|---|---|
| `index.html` | Leaflet (National map, 2,015 branches) |
| `province.html` | deck.gl |
| `rayong-catchment.html` | deck.gl |
| `branch-explorer.html` | deck.gl |

`tests/run.sh` asserts both bundles are present **and** that no page has drifted back to a
`unpkg` / `jsdelivr` / `cdnjs` `<script>` or `<link>`, so a regression fails the gate rather than
quietly reintroducing the runtime dependency.

## To upgrade a version

1. Download the new bundle from unpkg **and** jsdelivr, byte-compare them.
2. Replace the file (keep the version in the filename for deck.gl) and update the table above.
3. Update the path in the page's `<script>` tag and in `tests/run.sh` / `tests/lib/render.sh`.
4. `tests/package.json` still carries the version pin of record for both packages.
5. Run `tests/run.sh` — the render + health phases will catch an incompatible major.

## What is still third-party at runtime

Vendoring these two removed the libraries from the critical path; it did **not** make the pages
offline. Still fetched from the network at view time, by design:

- **Basemap raster tiles** — `basemaps.cartocdn.com`. Blocked in QA renders on purpose (blank
  basemap, geometry still draws), so a tile outage degrades the map rather than breaking it.
- **IBM Plex Sans Thai / IBM Plex Mono** — Google Fonts. A failure here falls back to a system font.
