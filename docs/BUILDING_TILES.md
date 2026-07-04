# Building tiles — national 3D buildings for the map

**What this gives you:** real building footprints (with heights) for the whole country,
covering the 10 km area around **every AutoX branch (2,015) and every competitor branch**.
The map team plugs these into the 3D map as a *streaming tile layer* — the buildings load
in only for the area you're looking at, so the map stays fast even though the data is national.

**Where the buildings come from:** [Overture Maps](https://overturemaps.org) — a real, open
buildings dataset (it fuses OpenStreetMap + Esri + Google/Microsoft ML buildings). **Nothing
is invented.** This pipeline only *pulls* real footprints. It never makes up buildings.

> ⚠️ **Run this from your Thai laptop / network.** The Overture download is large and the
> sandbox can't reach it from a foreign IP. Your normal Thai connection is fine.

---

## One-time setup (install three tools)

1. **Overture CLI** (the downloader):
   ```
   pip install overturemaps
   ```
2. **tippecanoe** (turns the download into map tiles). On Windows the easiest path is WSL
   (Ubuntu) or a Mac/Linux box; tippecanoe is a felt/tippecanoe build tool:
   - macOS: `brew install tippecanoe`
   - Ubuntu/WSL: `sudo apt install build-essential libsqlite3-dev zlib1g-dev && git clone https://github.com/felt/tippecanoe && cd tippecanoe && make -j && sudo make install`
3. **pmtiles** *(optional — only to inspect the result):* `pip install pmtiles` or the
   [pmtiles CLI](https://github.com/protomaps/go-pmtiles).

---

## The 3 steps

### Step 1 — generate the plan (do this in the repo, on any machine)

```
python3 pipeline/build_building_tiles.py
```

This prints the coverage and writes two files into `pipeline/tiles_out/` (which is
**gitignored** — never committed, because the tiles are large and live on a CDN):

- `coverage_bbox.json` — the area to download and how many points it covers.
- `RUN_TILES.sh` — the exact commands for step 2, with the bbox already filled in.

### Step 2 — pull buildings and build the tiles (on your Thai network)

From the **repo root**, run the generated script:

```
bash pipeline/tiles_out/RUN_TILES.sh
```

It does three things:
1. **Downloads** real Overture buildings for the national area → `buildings.geojsonseq`
2. **Builds** a single tile file → `buildings.pmtiles`
3. *(optional)* also builds a folder of tiles (`tiles/{z}/{x}/{y}.pbf`) for static hosts
   that can't serve `.pmtiles`.

> 💾 **Honest about size:** the national geojsonseq download is **~15–18 GB** (~30–35M real
> Overture footprints at ~500 bytes each); the finished `buildings.pmtiles` is **~1.5–3 GB**.
> The pull streams (constant memory — it will not OOM); it is **disk + time** bound (~20 min
> download + ~20–40 min tippecanoe on a normal laptop). Make sure you have ~40 GB free disk.
>
> **Want to test first? Generate a small ONE-province plan** instead of hand-editing the bbox:
> ```
> python3 pipeline/build_building_tiles.py --province rayong
> bash pipeline/tiles_out/RUN_TILES_rayong.sh
> ```
> This writes `RUN_TILES_rayong.sh` (its outputs are named `buildings_rayong.*` so they never
> clobber the national ones). A full province is tiny — Rayong is ~0.8M buildings / ~400 MB /
> ~30 s to download. Upload `buildings_rayong.pmtiles`, point `buildings.pmtilesUrl` at it,
> confirm one province renders, then run the full national plan. `--province` accepts a slug,
> English, or Thai name (e.g. `rayong`, `Bangkok`, `เชียงใหม่`).

### Step 3 — host it and tell the frontend where it is

1. Upload `pipeline/tiles_out/buildings.pmtiles` (or the whole `tiles/` folder) to a CDN
   bucket. Any of these work:
   - **Cloudflare R2** (recommended — cheap, supports the range requests `.pmtiles` needs)
   - **AWS S3** (+ CloudFront)
   - **Vercel Blob**
2. Copy the **public URL** of the uploaded file.
3. Paste it into `platform/data/tiles_config.json`. The frontend reads the **nested**
   `buildings.pmtilesUrl` key (NOT a flat `buildings_pmtiles`), so set it exactly like this
   (replace the WHOLE `buildings` block):
   ```json
   "buildings": {
     "pmtilesUrl": "https://pub-10384b83bd7245a68fd67916aa7f76ea.r2.dev/buildings.pmtiles",
     "mvtUrl": null,
     "minZoom": 9,
     "maxZoom": 15,
     "sourceLayer": "buildings",
     "heightProperty": "height",
     "attribution": "© Overture Maps Foundation"
   }
   ```
   > 🚨 **Delete the `coverageBbox` line.** The current config carries a Rayong-pilot
   > `coverageBbox` that gates streaming to Rayong only — with a **national** archive you must
   > remove it, or all 76 other provinces will get no streamed buildings. The block above
   > already omits it: replace the entire `buildings` block with exactly what's shown (no
   > `coverageBbox`, no `coverageNote`) and every province streams nationwide.
   *(If you used the `tiles/` folder instead of the single `.pmtiles`, set
   `buildings.mvtUrl` to that folder's `{z}/{x}/{y}.pbf` template and leave `pmtilesUrl`
   null — the frontend prefers `mvtUrl` when both are set. Avoid the `tiles/` folder for the
   FULL national pull: it is millions of files. For R2, host the single `buildings.pmtiles`.)*

That's it. The map's 3D building layer will start streaming real buildings nationwide.

---

## Re-running later

When AutoX adds branches or you refresh competitors, just run **Step 1** again to get a
fresh `RUN_TILES.sh` (the bbox updates automatically), then **Step 2** and re-upload.

## Sanity check (for CI / the dev team)

```
python3 pipeline/build_building_tiles.py --check
```

Network-free; confirms the coverage area is sane (2,015 branches + competitors present,
bbox finite and inside Thailand) and exits 0. Safe to wire into the test gate.
