# QA/UXUI audit — 2026-07-12

Automated Playwright audit of every route (desktop 1440×900 + mobile 390×844), served locally.
**Counts:** 1 blocker · 2 major · 3 minor · 3 polish. All 13 routes loaded; no page-level horizontal
scroll at 390px. This is the intake for the recursive UX-improvement loop.

## Findings (severity-ranked)

| # | Sev | Route | Category | Issue | Fix |
|---|-----|-------|----------|-------|-----|
| 1 | **BLOCKER** | branch-explorer.html | functional | Basemap dead (flat void) + 150+ `ERR_NAME_NOT_RESOLVED` console errors — deck.gl `TileLayer` doesn't expand the `{s}` subdomain token | Hardcode `a.basemaps.cartocdn.com` (as province/rayong pages do) — **✅ FIXED + verified (0 console errors)** |
| 2 | major | rayong-catchment.html | functional | `rayong_isochrone.json` + `rayong_trees.json` 404; reach-rings & trees toggles silently no-op | Isochrone toggle already self-hides when absent; now gate the optional-scenery fetches (iso/trees/rail) behind a per-city allowlist so no request fires until a file ships — **✅ FIXED (0 console 404s from scenery layers)** |
| 3 | major | index.html `#map` | mobile | Lens pills overlap the Leaflet zoom +/− at top-left (legibility + tap accuracy) | Move zoom control bottom-right; collapse lenses into a sheet on narrow viewports |
| 4 | minor | province.html | mobile | Top stat-chip toolbar clips off the right edge; chips unreachable | `overflow-x:auto` scroller |
| 5 | minor | (global) | consistency | SPA defaults light ("Paper Console"); 3D pages default dark; convention is dark-console | Persist one theme choice across pages |
| 6 | minor | (global) | accessibility | Light-theme `--dim #7A8598` on `#F4F6FA` ≈ 3.4:1 (below WCAG AA) on 10–11px microcopy | Darken to ~`#5B6678` |
| 7 | polish | index routes | functional | favicon 404 | Add a favicon |
| 8 | polish | index.html `#branches` | clarity | Opens straight into a search box, no headline/lead line (unlike every other route) | Add a header + one-line lead |

## Verdicts
- **Mobile-readiness: strong.** SPA reflows to single column, nav is a scrollable ~41px-target strip,
  healthy 3D pages init non-blank with bottom-sheet controls. Main blemishes: #map lens/zoom overlap
  and (now-fixed) branch-explorer.
- **"Leads with the answer": excellent** on content routes (`#home`/`#overview`/`#trend`/`#acq`/
  `#exposure` each open with a bold one-line answer + KPIs + ranked source-tagged actions; `#sim` is
  genuinely interactive). Only gap: `#branches`.

Fix the blocker (done) + the two majors and the platform is in very good shape.

## Fix log — recursive UX loop (2026-07-12, branch claude/ux-catchup)

Each item below is a REAL, surgical fix matching the dark instrument-console theme (accent `#5B7CFA`,
IBM Plex fonts). IDs match `committee/plan_cycle.py`'s uxui block (which flips `state` to done off these
lines) so the CEO `/status` dashboard reflects the progress.

- ux-favicon — ✅ FIXED 2026-07-12 — added `platform/favicon.svg` (dark rounded square + accent "AX" monogram) and `<link rel="icon" href="/favicon.svg">` in index.html, rayong-catchment.html, province.html, branch-explorer.html, status.html. Stops the favicon 404 (#7).
- ux-contrast — ✅ FIXED 2026-07-12 — light-theme `--dim` darkened `#7A8598` → `#5B6678` in styles.css (≈3.4:1 → ≈5.4:1 on `#F4F6FA`, clears WCAG AA for microcopy) (#6).
- ux-map-overlap — ✅ FIXED 2026-07-12 — added a `@media(max-width:430px)` rule in styles.css moving the Leaflet zoom `+/−` to the bottom-right on the `.maphero` map, clear of the floated lens pills (#3).
- ux-province-overflow — ✅ FIXED 2026-07-12 — province.html `#strip` stat-chip toolbar made a proper touch horizontal scroller: added `-webkit-overflow-scrolling:touch` + `white-space:nowrap` (already `overflow-x:auto`); chips no longer clip off the right edge on mobile (#4).
- ux-theme-persist — ✅ FIXED 2026-07-12 — every page already reads the persisted `autox-theme` from localStorage on load; province.html + branch-explorer.html defaulted dark while the SPA front door (index.html) and rayong-catchment.html default light — aligned those two to the SPA's light default so the first-load theme is consistent across pages (a saved choice still wins everywhere) (#5).
- ux-branches-lead — ✅ FIXED 2026-07-12 — `#branches` (index.html) now opens with a header + lead ("All 2,015 AutoX branches — search, sort, and open any branch's 3D scene.") like every other route (#8).
- ux-search-a11y — ✅ FIXED 2026-07-12 — the three SPA search boxes (`#branches`, `#provinces`, `#market`) were placeholder-only `text` inputs with no accessible name (WCAG 4.1.2); added `type="search"` (native × clear button on mobile) + `aria-label` to each, matching the scene search (`ssInput`) pattern already used in rayong-catchment.html.
- ux-theme-comment (NEW, polish) — the pre-paint theme-init comment on line 4 of index.html/rayong-catchment.html/rayong-province.html/status.html still reads "else saved, else dark" but the code now defaults `'light'` (post ux-theme-persist). Stale comment only, no user-facing effect — one-word fix "dark"→"light" when next touching those files.
- ux-isochrone-guard — ✅ FIXED 2026-07-12 — rayong-catchment.html no longer requests `<slug>_isochrone.json` / `<slug>_trees.json` unless the province is registered in `tiles_config.json`'s `scenery` list, so absent files no longer 404 in the console; the isochrone toggle already self-hides when `window.ISO` is empty (also hidden by default now), so no dead toggle (#2).
- ux-map-overlap-tablet — ✅ FIXED 2026-07-13 — the #3 zoom/lens-overlap fix only relocated the Leaflet zoom to bottom-right at ≤430px (phones); headless renders at 500/600/760px showed the lens pills still wrap to 2–3 rows and crowd/overlap the top-left zoom across the whole 431–760px band (foldables, tablets, landscape phones, split-screen). Extended the relocation `@media` breakpoint `430px → 760px` in styles.css so the zoom sits bottom-right (always clear) across the full phone+tablet range; desktop (>760px, verified clean at 1440px — pills fit one row) keeps the conventional top-left zoom (#3, tablet band).
- ux-skip-link — ✅ FIXED 2026-07-13 (NEW, a11y) — the `role="tablist"` nav has ~12 focusable stops on every route with no bypass (WCAG 2.4.1 Bypass Blocks, Level A gap). Added a "Skip to main content" link as the first `<body>` child in index.html (off-screen until keyboard focus, then overlays the fixed nav in accent `#5B7CFA`), gave `<main>` `id="main-content" tabindex="-1"`, and a tiny focus handler that `preventDefault`s so the SPA hash-router (unknown hash → falls back to `#home`) never fires. Zero visual change for pointer users; keyboard/SR users can now jump the nav.
- ux-color-scheme — ✅ FIXED 2026-07-16 — no page declared `color-scheme`, so native UA surfaces (scrollbars, form controls, the pre-paint canvas, iOS rubber-band overscroll) rendered in the OS default scheme — e.g. dark-console users got OS-default LIGHT scrollbars against the dark chrome. Added a CSS-only, theme-tracking pair in `styles.css`: `color-scheme:dark` on the canonical `:root` + `color-scheme:light` on `html[data-theme="light"]`. Keys off the `data-theme` attr the pre-paint script sets, so it applies from the first frame and auto-follows the toggle across all 5 styles.css pages (index/province/rayong-catchment/branch-explorer/status). Verified: computed `color-scheme` = light on default load, dark on `?theme=dark`; both themes render clean (0 console errors).
- ux-theme-color (NEW, polish) — no page sets `<meta name="theme-color">`, so the mobile browser UI bar / notch area doesn't match the app chrome. Correct fix must TRACK `data-theme` (not `prefers-color-scheme`, which the app ignores), so it needs a JS hook in the pre-paint script + theme-toggle handler on each page (not CSS-only) — deferred as a separate run to keep this one surgical.
- ux-map-overlap-residual — ✅ FIXED 2026-07-13 — headless renders of `#map` confirmed the residual: at 900px the lens row wraps to 2 rows and the Leaflet zoom `+/−` (56px top-left offset clears only 1 row) overlaps the 2nd-row "More lenses ▾" pill; it settles to one clean row by ~1050–1100px. Extended the zoom bottom-right relocation `@media` breakpoint `760px → 1080px` in styles.css so the zoom sits bottom-right (clear of any wrap) across the full phone+tablet+small-laptop band, with a cushion above the headless one-row transition; >1080px keeps the conventional top-left zoom (verified clean at 1100/1200px). Closes the last open `#map` overlap item (#3 residual band).
