# TONIGHT CHECKLIST — the Thai-laptop / Thai-IP pulls

> **Read this first.** Everything below is **blocked from Claude's sandbox (foreign IP)** and must be
> run **from Kaustav's laptop on a Thai/residential connection**. That single fact is the biggest
> reason to keep working in Claude Code locally. Each step is copy-pasteable. Run from the repo root
> unless a step says otherwise.
>
> **Honesty rule (mandatory):** these pulls replace *proxies* with *measured* data. After folding any
> of them in, re-run the derive/build steps so the app's "measured vs proxy/estimated" labels stay true.

---

## 0. One-time setup (do this before any pull)

```bash
# from the repo root
cd /path/to/competitive-intel
pip install --break-system-packages shapely openlocationcode openpyxl pdfplumber requests

# ROTATE the data.go.th token first — the old one was exposed in chat. Issue a new one at
# https://data.go.th (your account → API key), then set it for this shell (do NOT commit it):
export DATA_GO_TH_TOKEN="<your-new-token>"

# optional: persist it so pipeline scripts auto-load it (gitignored)
echo "DATA_GO_TH_TOKEN=$DATA_GO_TH_TOKEN" >> pipeline/.env

# also update it in Vercel (project thailand-labor-intel) — it lives there too:
#   npx vercel env rm DATA_GO_TH_TOKEN production   # remove the exposed one
#   npx vercel env add DATA_GO_TH_TOKEN production   # paste the new one
```

Sanity-check you actually have a Thai route (these 403/timeout from the sandbox, should 200 for you):

```bash
curl -sS -o /dev/null -w "%{http_code}\n" "https://data.go.th"
```

---

## 1. data.go.th pull — DLT vehicles, DIW factories, NSO employment, OAE crops

This is the big one. The puller is crash-proof and resumes; it writes CSVs to `pipeline/dgt_out/`.

```bash
cd pipeline
python3 autox_dgt_ingest.py          # writes ./dgt_out/*.csv + manifest.json
```

What it sweeps (topics already wired in `autox_dgt_ingest.py`): **factories_diw**, **vehicles_dlt**,
**crop_area_oae**, **crop_price_oae**, **employment** (ภาวะการทำงาน / ผู้ประกันตน), **estates_ieat**.
A "★" in the report means a genuinely national table (≥20 provinces).

**Priority targets to confirm landed national (these matter most):**
- **DLT vehicle registrations** by province/district — cars vs **motorcycles** vs pickups vs trucks.
  (Motorcycle title ≈ 50% of the book, car/pickup ≈ 25% — collateral mix drives recovery value.)
- **DIW factories** — widen beyond what we have, especially factory zones (Pluak Daeng / Nikhom)
  where OSM has ~nothing.

Then fold the raw CSVs into clean source-data layers and re-project to the app:

```bash
cd pipeline
python3 ingest_gov.py                 # dgt_out/*.csv -> source-data/{factories,vehicles,employment,crop_*}.json
python3 ingest_gov.py --check         # verify byte-exact
python3 derive.py                     # re-project master -> platform/data
python3 build_province.py             # provinces pick up the new vehicle/factory/employment totals
python3 build_amphoe.py               # district whitespace/risk pick up new gov counts
```

---

## 2. NSO Census Table 6 — occupations by district

The "who works here" proxy is currently OSM POIs. NSO Census **Table 6** (occupation by amphoe) is the
real thing. It is **not** auto-targeted by the puller yet — pull it explicitly.

```bash
cd pipeline
# Browse the NSO population/housing census on data.go.th and grab the Table 6 resource_id(s):
#   search terms: "สำมะโนประชากร อาชีพ" / "ผู้มีงานทำ จำแนกตามอาชีพ อำเภอ"
# Quick datastore pull of a known resource_id (paginates automatically):
python3 - <<'PY'
import os, json, urllib.request, urllib.parse
KEY=os.environ["DATA_GO_TH_TOKEN"]; BASE="https://data.go.th/api/3/action"
RID="<census-table6-resource-id>"   # <-- paste from data.go.th
def api(a,**p):
    r=urllib.request.Request(f"{BASE}/{a}?"+urllib.parse.urlencode(p),
        headers={"api-key":KEY}); 
    import json; return json.load(urllib.request.urlopen(r,timeout=60))
rows=[]; off=0
while True:
    d=api("datastore_search",resource_id=RID,limit=10000,offset=off)
    recs=d["result"]["records"]; rows+=recs
    if len(recs)<10000: break
    off+=10000
json.dump(rows, open("dgt_out/nso_census_table6.json","w"), ensure_ascii=False)
print(len(rows),"rows -> dgt_out/nso_census_table6.json")
PY
```

Then add an occupations distiller to `ingest_gov.py` (one new `--check`-gated layer keyed by
province|district), re-run `ingest_gov.py` and the `build_*` steps above.

---

## 3. OSM — roads / water / landuse / buildings (Overpass)

For catchment widening and the future 15-min isochrone. The Overpass **mirror** is reachable even
from the sandbox, but rate limits are kinder on a residential IP — pull the big boxes locally.

```bash
cd pipeline
# buildings (existing scripts) — widen beyond Mueang Rayong:
python3 pull_wide.py                  # current bbox: 12.655,101.155,12.725,101.310
# edit the bbox in pull_wide.py for Ban Chang / Klaeng town, re-run, then:
python3 bake_catchment_heights.py     # bake per-building type/height
python3 bake_catchment_heights.py --check

# roads/water/landuse: add Overpass queries (mirror endpoint already in the scripts):
#   ENDPOINT = https://maps.mail.ru/osm/tools/overpass/api/interpreter
#   way["highway"]({bbox});            # roads (for isochrone network)
#   (way["natural"="water"]({bbox}); relation["natural"="water"]({bbox}););
#   (way["landuse"]({bbox}); relation["landuse"]({bbox}););
```

---

## 3b. Overture Places — granular occupation/employment near every branch

Replaces the province-level NSO number + the OSM "who works nearby" *proxy* with a MEASURED,
point-level establishment census (Overture Maps Places, free, no geo-block). Each place → 1 of 14
occupation buckets; we count them within 10 km of every branch. Needs the Overture CLI
(`pip install overturemaps`).

### A. WIDE Rayong (quick, single pull)

```bash
cd pipeline
# 1) pull places (WIDE Rayong by default; --preset national for the whole country, large pull)
python3 pull_overture_places.py --bbox "12.62,101.13,12.74,101.33"   # -> source-data/overture_places.json
# 2) roll up into per-branch 10km occupation mix (deterministic, feeds the app)
python3 build_occupations.py                                          # -> platform/data/branch_occupations.json
python3 build_occupations.py --check                                  # must pass (gate runs this)
# 3) commit BOTH the source layer and the derived file together:
git add ../source-data/overture_places.json ../platform/data/branch_occupations.json
git commit -m "data: Overture Places occupation layer + per-branch 10km rollup"
git push origin claude/new-session-wto26j
```

### B. WHOLE COUNTRY — TILED + RESUMABLE (use this for the national harvest)

The plain `--preset national` pull is too slow to finish in one sitting and loses everything on
Ctrl-C. Use `pull_overture_national.py` instead: it tiles Thailand into ~1.0-degree cells, writes
each tile atomically into `source-data/.overture_tiles/` (gitignored), records completed tiles in a
manifest, and SKIPS done tiles on rerun. Stop/restart as many times as you like — it resumes.

```bash
cd pipeline
# pull incomplete tiles (resumes if interrupted); auto-merges once ALL tiles are complete.
python3 pull_overture_national.py
# ...if it dies or you Ctrl-C, just run it again — it picks up where it left off:
python3 pull_overture_national.py
# RERUN UNTIL this shows "0 remaining":
python3 pull_overture_national.py --status
# (if all tiles were already done before the final auto-merge, force the merge:)
python3 pull_overture_national.py --merge-only   # -> source-data/overture_places.json
#                                                    + platform/data/competitors_overture.json

# then the SAME deterministic rollups as above (the gate runs both --check):
python3 build_occupations.py            # -> platform/data/branch_occupations.json
python3 build_amphoe_occupations.py     # -> platform/data/amphoe_occupations.json

# commit the merged source layer + derived files (NOT the .overture_tiles/ cache — it is gitignored):
git add ../source-data/overture_places.json ../platform/data/branch_occupations.json \
        ../platform/data/amphoe_occupations.json ../platform/data/competitors_overture.json
git commit -m "data: national Overture occupation layer (tiled pull) + per-branch/-district rollups"
git push origin claude/new-session-wto26j
```

Flags: `--tile-deg N` (cell size, default 1.0), `--bbox S,W,N,E` (override national),
`--merge-only`, `--status`. The state dir `source-data/.overture_tiles/` is gitignored —
never commit the per-tile geojsonseq cache.

The branch-explorer "Who works nearby" panel auto-switches from *estimated · proxy* to
*measured · Overture* the moment `branch_occupations.json` is present.

---

## 4. Agri ground-truth — farm-gate prices, reservoirs, flood

`build_crop_stress.py` currently uses the **World Bank GLOBAL price board** as a *direction proxy* —
NOT Thai farm-gate. Replace it with real Thai data (this sharpens objective #1 directly).

```bash
cd pipeline
# Farm-gate prices: OAE "ราคาที่เกษตรกรขายได้" — already a puller topic (crop_price_oae). Confirm it
# landed per-province in dgt_out, then distill into source-data/crop_prices_farmgate.json via ingest_gov.py.

# Reservoir storage (RID/กรมชลประทาน) + flood extent (GISTDA / กรมป้องกันฯ):
#   search data.go.th: "ปริมาณน้ำ อ่างเก็บน้ำ" (reservoir), "พื้นที่น้ำท่วม" (flood)
#   pull via the same datastore snippet in §2, save to dgt_out/, distill to a province layer.

# Then point build_crop_stress.py at the farm-gate layer (replace the global proxy term) and:
python3 build_crop_stress.py
python3 build_crop_stress.py --check
```

After this, flip the crop-stress UI label from "global price direction proxy" to "Thai farm-gate (measured)".

---

## 5. Competitor census — Google Places, brand × province (all 77)

Today competitors are hand-curated for **Rayong only** (30). Automate per province so every province
deep-dive is competitor-aware. Google Places **is reachable** (works from the sandbox too) but the key
is yours.

```bash
cd pipeline
export GOOGLE_PLACES_KEY="<your-places-key>"
# Extend save_competitors.py from a static list to a live Text Search per (brand, province):
#   brands: Srisawad ศรีสวัสดิ์ | Muangthai Capital เมืองไทย แคปปิตอล | Ngern Tid Lor เงินติดล้อ | Krungsri Auto
#   for each province center: textsearch ?query="<brand> <province_th>"&key=$GOOGLE_PLACES_KEY
#   dedup by place_id, tag brand+province, write source-data/competitors_by_province.json
python3 save_competitors.py           # writes the competitor JSON
# then build_province.py will attach competitors where available.
```

---

## 6. Loan tape — the ONE command (objective #1, biggest portfolio-risk unlock)

When the real export exists (no PII; schema = `pipeline/loan_tape_schema.md`), drop the two files in
`source-data/` and run **one command**. This flips the four outputs from SYNTHETIC to **measured**.

```bash
cd pipeline
# Export from core banking per the schema -> source-data/loan_tape.json + branch_aum_monthly.json
python3 ingest_loan_tape.py --tape ../source-data/loan_tape.json \
                            --aum  ../source-data/branch_aum_monthly.json \
                            --real
# It validates (enums/ranges/join-rate/status sanity), FAILS LOUDLY on problems, and on success writes
# platform/data/loan_tape_derived.json stamped `measured` (not SYNTHETIC):
#   (a) vintage 90+ aging curves  (b) per-branch ROI/payback  (c) HHI concentration  (d) PD calibration
```

(Until then, `python3 ingest_loan_tape.py` with no args regenerates from the SYNTHETIC tape.)

---

## 7. After ANY pull — verify, then hand back

```bash
# from the repo root — the determinism + syntax gate MUST pass before committing
bash tests/run.sh check

# serve locally and click every tab (http, not file://)
cd platform && python3 -m http.server 8000   # http://localhost:8000
```

Then upload the new `source-data/*.json` (and, if you want Claude to re-derive, the raw
`pipeline/dgt_out/`) back into Claude Code, or commit them yourself. **Do not commit `DATA_GO_TH_TOKEN`,
the Places key, or any real loan tape** — the synthetic tape and tokens are gitignored on purpose.

---

### Quick reference — IDs (also in NEXT_STEPS.md)
- Vercel team: `team_pYNrbLMZobN80m4jD7WPWybD` ("Kaustav Bagchi's projects")
- Token lives in Vercel project `thailand-labor-intel` (`prj_VLpR8SIHOSwe5NXuqMjQaTBwwJFc`).
- Overpass mirror: `https://maps.mail.ru/osm/tools/overpass/api/interpreter`


---
## ⏰ Deferred reminder (set 2026-07-01)
- **Rotate DATA_GO_TH_TOKEN** — user deferred on 2026-06-29; revisit ~2 days later. (Old token was exposed in chat.)
- **Regenerate the OpenRouteService key** — it was pasted in chat on 2026-06-29; regenerate after the isochrone is wired.

---
## 8. Real per-province GPP (NESDC) — replace the vendored TMLI knowledge-base guess

**Found 2026-07-02 audit:** `source-data/tmli/provincial-gpp.js` claims "NESDC OFFICIAL DATA" but
its own metadata admits only **1 of 77** provinces (Mukdahan) is CKAN-verified; the other 76 are
round-number estimates. `gpp_by_province.json` is corrected to label this MIXED/mostly-ESTIMATED and
is **not** wired into any `platform/data` layer. To make it real:

```bash
# from a Thai IP — same CKAN dataset family as the verified Mukdahan resource
# (resource ffabdf4f-b326-4d2d-8ede-a4514bf20339), browse:
#   https://data.go.th/api/3/action/package_search?q=GPP   (44 datasets, NESDC Provincial Accounts)
# find the resource_id for EACH province's GPP table (or a single national table keyed by province),
# pull via the same datastore_search snippet as §2 (Census Table 6), save to
#   pipeline/dgt_out/nesdc_gpp_by_province.json
# then extend ingest_gov.py (or ingest_tmli.py) with a real distiller that overwrites
# source-data/gpp_by_province.json with per-province CKAN-verified rows (source: 'CKAN-NESDC-2566'
# for every row, not just Mukdahan), and re-run:
cd pipeline
python3 derive.py
python3 build_province.py
```

Only after every row carries a genuine CKAN resource id should the app surface GPP as MEASURED.
