# AutoX · เงินไชโย — Credit Intelligence Platform

One Vercel app. No build step. Static files; data served from `data/`.

## Routes (one nav bar across all)
- **index.html** — Overview · National map (lens switcher) · Acquisition · Branches
- **rayong-province.html** — Rayong 3D deep-dive: extruded district polygons, 57 branches, live competitors, "what impacts them"
- **rayong-catchment.html** — Mueang Rayong catchment explorer: 3,631 extruded buildings, reachable-population card, acquisition leads + recommendations

```
index.html  rayong-province.html  rayong-catchment.html
app.js  styles.css  vercel.json
data/
  branches.json        national (2,015 branches)
  meta.json            commodity board, macro, white-space
  rayong_province.json districts + branches + competitors + POI
  rayong_catchment.json buildings + branches + competitors + POI + landmarks
```

## Deploy to Vercel (pick one)
- **CLI:** `npx vercel --prod` from this folder → prints the live URL.
- **Drag-drop:** vercel.com → Add New → Project → upload this folder.
- **Git:** push the folder to a repo, import in Vercel. No framework, no build command.

## Refreshing data
Re-run the enrichment loop, regenerate the files in `data/`, redeploy. The app always reads `data/`.

## Notes
- National map = Leaflet (light, mobile-safe). Rayong pages = deck.gl 3D (one scene per page, fresh GL context).
- Reachable population in the catchment view is a dasymetric estimate (building floor-area × occupancy), not a street-network isochrone.
- Pages must be served over http (Vercel) — opening the raw file won't fetch the data.
- Keep behind Vercel access protection if branch-level detail is sensitive.
