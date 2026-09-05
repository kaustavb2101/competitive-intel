# AutoX · เงินไชโย — Credit Intelligence Platform

One Vercel app. No build step. Static files; data served from `data/`.

## Routes (one nav bar across all)
- **index.html** — Overview · National map (lens switcher) · Acquisition · Branches
- **rayong-catchment.html** — unified **Rayong 3D** view: 3,631 extruded Mueang-core buildings (scenery), 59 branches with
  10km collateral catchment rings, color-coded POIs (toggleable legend), flat district context, a Region>Province>Branch
  cascade (populated nationwide from `data/provinces/index.json`, interactive for Rayong now), reachable-population card,
  acquisition leads + recommendations.
- **rayong-province.html** — retired redirect stub → `/rayong-catchment` (preserves old deep-links).

```
index.html  rayong-catchment.html  rayong-province.html(stub)
app.js  styles.css  vercel.json
data/
  branches.json        national (2,015 branches)
  meta.json            commodity board, macro, white-space
  provinces/           per-province deep-dives (build_province.py; rayong.json = pilot)
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
