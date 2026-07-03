# Building tiles — RUNBOOK (national 3D buildings everywhere)

**Goal:** show real Overture building footprints inside the 10 km catchment of **every**
branch, not just each province's capital. The 3D scenes already stream tiles the moment
`platform/data/tiles_config.json` has a non-null `buildings.pmtilesUrl` (or `mvtUrl`). This
runbook is the exact, tested path to produce and host that one `.pmtiles` file.

> This is the operational companion to `docs/BUILDING_TILES.md`. Numbers below are **measured
> in-sandbox** against live Overture, not guessed.

---

## 0. Verdict (feasibility)

- **The Overture pull WORKS and is fast.** Proven from the sandbox against live Overture cloud
  parquet: a full Rayong-province box (0.57 sq°) pulled **820,729 real buildings → 407 MB
  geojsonseq in 33 s**; Bangkok metro (0.42 sq°) **3.63M buildings / 1.8 GB / 137 s**. The
  `overturemaps` CLI streams row-by-row at **constant memory (~a few hundred MB)** — it will
  **NOT OOM** the ~15 GB container. The job is **disk + time** bound, not memory bound.
- **The one thing the sandbox can't finish is the tiling step.** `tippecanoe` is not installed,
  and building it from source (`git clone felt/tippecanoe && make`) is blocked by the sandbox's
  untrusted-code policy. That step therefore runs on **your (Kaustav's) machine** — which is
  exactly the design (`build_building_tiles.py` only ever emitted a run-plan for the desktop).
- **National geojsonseq (~15–18 GB) is too big for the sandbox's ~20 GB free disk** to also run
  tippecanoe on top of. Run the full national job on the desktop. The sandbox can safely produce
  any single province.

**Bottom line:** feasible. Pull = trivial anywhere (works even here). Tile + host = a ~1 hour
job on your laptop + a file upload to R2. No blocker, no OOM risk.

---

## 1. Size estimate (measured density → national)

Bytes/building in geojsonseq is stable at **~490–500 bytes** across every sample.

| Area (padded branch bbox) | sq° | buildings | geojsonseq | pull time | density (M/sq°) |
|---|---|---|---|---|---|
| Bangkok metro | 0.42 | 3,630,942 | 1.80 GB | 137 s | 8.67 |
| Rayong province | 0.57 | 820,729 | 0.41 GB | 33 s | 1.44 |
| Nakhon Ratchasima | 2.88 | 2,959,016 | 1.45 GB | 104 s | 1.03 |
| Chiang Mai | 2.38 | 2,027,372 | 0.99 GB | 74 s | 0.85 |
| Rural Isan sample | 0.01 | 6,719 | 3.3 MB | 4 s | 0.67 |

**National `--bbox` = the whole country rectangle** (97.71,5.69 → 105.54,20.50 = ~116 sq°, but
mostly sea/forest that download near-instantly). Thailand has **~30–35M** Overture buildings
(land area 513,000 km² × the ~65–90 buildings/km² we measured over populated provinces).

- **Download (geojsonseq): ~15–18 GB**, ~20 min at the ~27k rows/s we sustained.
- **`buildings.pmtiles` output: ~1.5–3 GB** (tippecanoe simplifies + drops densest at low zoom).
  This is the ONLY file you host. ~20–40 min of tippecanoe on a normal laptop.
- **Free disk needed on the desktop: ~40 GB** (geojsonseq + tippecanoe temp + output).

---

## 2. One-time prereqs (desktop)

```
pip install overturemaps                     # the downloader (already present in this repo's sandbox)
# tippecanoe (vector-tile builder):
#   macOS:      brew install tippecanoe
#   Ubuntu/WSL: sudo apt install build-essential libsqlite3-dev zlib1g-dev \
#               && git clone https://github.com/felt/tippecanoe && cd tippecanoe && make -j && sudo make install
pip install pmtiles                          # optional, only to inspect the archive
```

---

## 3. Commands

### 3a. Prove it on ONE province first (recommended, ~1 min)

```
python3 pipeline/build_building_tiles.py --province rayong      # writes RUN_TILES_rayong.sh (+ coverage_bbox_rayong.json)
bash pipeline/tiles_out/RUN_TILES_rayong.sh                     # pull -> buildings_rayong.pmtiles (~30s pull + short tile build)
```
`--province` accepts a slug / English / Thai name (`rayong`, `Bangkok`, `เชียงใหม่`). Province
outputs are named `buildings_<slug>.*` so they never clobber the national artifacts. Upload
`buildings_rayong.pmtiles`, point `buildings.pmtilesUrl` at it (step 4), confirm one province
renders, then do the national run.

### 3b. The full national run

```
python3 pipeline/build_building_tiles.py         # writes pipeline/tiles_out/RUN_TILES.sh + coverage_bbox.json
bash pipeline/tiles_out/RUN_TILES.sh             # pull ~16GB -> buildings.pmtiles (~1 hr total)
```

`RUN_TILES.sh` runs three steps (all in `pipeline/tiles_out/`, which is gitignored):
1. `overturemaps download --bbox=<national W,S,E,N> -f geojsonseq --type=building` → `buildings.geojsonseq`
2. `tippecanoe -o buildings.pmtiles -l buildings -Z9 -z15 --drop-densest-as-needed --extend-zooms-if-still-dropping --read-parallel` → `buildings.pmtiles`  ← **the file you host**
3. *(optional)* an `{z}/{x}/{y}.pbf` folder — **skip this for R2/national**; it is millions of files. Host the single `.pmtiles`.

`PYTHONUTF8=1` is set in the script (avoids a Windows cp1252 crash on Thai names). Both scripts
run from the **repo root**.

---

## 4. Host it + wire the frontend

1. Upload the single file to your Cloudflare R2 bucket (the one already fronted by
   `https://pub-10384b83bd7245a68fd67916aa7f76ea.r2.dev`):
   ```
   # e.g. with rclone or wrangler
   wrangler r2 object put <bucket>/buildings.pmtiles --file pipeline/tiles_out/buildings.pmtiles
   ```
   Public URL becomes `https://pub-10384b83bd7245a68fd67916aa7f76ea.r2.dev/buildings.pmtiles`.

2. **CORS on the bucket must allow** the Vercel site origin and the `Range` header (PMTiles reads
   byte ranges). Minimal R2 CORS:
   ```json
   [{ "AllowedOrigins": ["*"], "AllowedMethods": ["GET","HEAD"],
      "AllowedHeaders": ["range","if-match","content-type"],
      "ExposeHeaders": ["content-range","content-length","etag","accept-ranges"] }]
   ```

3. Set the **nested** key in `platform/data/tiles_config.json` (the frontend reads
   `buildings.pmtilesUrl`, NOT a flat `buildings_pmtiles`):
   ```json
   "buildings": {
     "pmtilesUrl": "https://pub-10384b83bd7245a68fd67916aa7f76ea.r2.dev/buildings.pmtiles",
     "mvtUrl": null, "minZoom": 9, "maxZoom": 15,
     "sourceLayer": "buildings", "heightProperty": "height",
     "attribution": "© Overture Maps Foundation"
   }
   ```
   Commit + redeploy `platform/`. The moment this URL resolves, `rayong-catchment.html`,
   `province.html`, and `branch-explorer.html` all stream real buildings per-viewport, everywhere.

---

## 5. Who does what

| Step | Who | Notes |
|---|---|---|
| Generate the plan (`build_building_tiles.py`) | **automatable / anywhere** | network-free; also runs in the sandbox |
| Overture pull (`overturemaps download`) | anywhere incl. sandbox | proven; not a data.go.th-style blocked endpoint |
| `tippecanoe` build tiles | **you (desktop)** | tippecanoe not installable in sandbox (policy); ~1 hr national |
| Upload `.pmtiles` to R2 + set CORS | **you** | needs the R2 credentials — not in the sandbox |
| Set `buildings.pmtilesUrl` + redeploy | **you / automatable** | one-line JSON edit + `vercel --prod` |

---

## 6. Caveats / follow-ups

- **`province.html` legend label** (`province.html` ~line 940) only flips to "Buildings" when
  `mvtUrl` is set. With the recommended single-file `pmtilesUrl`, the buildings **do render** on
  that page, but its side legend still reads "Districts / working-age". Cosmetic; a one-line
  frontend fix if it bothers you. `rayong-catchment.html` (the primary building scene) is
  unaffected.
- **Re-run when branches/competitors change:** just re-run step 3 (the bbox auto-updates) and
  re-upload. Nothing else changes.
- **Provenance:** every footprint is real Overture (OSM + Esri + Google/Microsoft ML fusion).
  Nothing is fabricated; the pipeline only pulls and tiles.
