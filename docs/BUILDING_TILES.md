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

> 💾 **Honest about size:** national buildings can be **many gigabytes** to download and
> can take a while. If you want to test first, open `RUN_TILES.sh` and replace the big
> `--bbox=...` with **one region's** bbox (e.g. just around Bangkok or Rayong), run it,
> check it looks right, then do the full national pull. Everything else stays the same.

### Step 3 — host it and tell the frontend where it is

1. Upload `pipeline/tiles_out/buildings.pmtiles` (or the whole `tiles/` folder) to a CDN
   bucket. Any of these work:
   - **Cloudflare R2** (recommended — cheap, supports the range requests `.pmtiles` needs)
   - **AWS S3** (+ CloudFront)
   - **Vercel Blob**
2. Copy the **public URL** of the uploaded file.
3. Paste it into `platform/data/tiles_config.json` so the map can read it, e.g.:
   ```json
   {
     "buildings_pmtiles": "https://YOUR-CDN/buildings.pmtiles"
   }
   ```
   *(If you used the `tiles/` folder instead, point at that folder's base URL — the map
   team will tell you the exact key to use.)*

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
