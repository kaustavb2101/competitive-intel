> **Provenance:** consolidated from the sibling **TMLI** effort (`kaustavb2101/watcher`) and vendored into competitive-intel on 2026-07-09. Paths written for the `autox-credit-intel/` root map to this repo root; where this repo is more evolved (e.g. `platform/data/`), trust the live code.

# WORKFLOWS.md — every runnable procedure (Claude Code copy-paste)

Ordered as you'll actually use them. All paths relative to repo root `autox-credit-intel/`.
Env vars: `GOOGLE_MAPS_API_KEY` (geocoder + scout only; census needs nothing).

## W0 · First session in Claude Code
```bash
cd autox-credit-intel && claude
```
Say: *"Read CLAUDE.md, docs/INSIGHTS.md and docs/PROGRESS_LOG.md, then summarize current state and
propose the next cycle."* Everything else below it can run for you.

## W1 · Put it on GitHub (unlocks automation) — do once
```bash
git init && git add -A && git commit -m "initial: platform + committee + docs"
gh repo create autox-credit-intel --private --source=. --push
# no gh CLI? create an empty PRIVATE repo on github.com, then:
# git remote add origin <url> && git branch -M main && git push -u origin main
```
Then on github.com → repo → Settings → Secrets and variables → Actions →
new secret `GOOGLE_MAPS_API_KEY` (Places API enabled, key restricted to it).
The workflow `.github/workflows/committee.yml` then runs on demand (Actions tab → committee-loop →
Run workflow) and every Monday 02:00 UTC: census → geocoder loop → scout → derive → commits back.

## W2 · Verify locally / deploy
```bash
cd platform && python3 -m http.server 8000        # open http://localhost:8000 (http, never file://)
cd platform && npx vercel --prod                  # team "Kaustav Bagchi's projects"; static, no build
```
If Vercel is Git-connected (Root Directory = `platform`), every committee commit auto-deploys.
Recommended: enable Vercel access protection (data is sensitive). After deploy, Claude-chat can read
build/runtime logs to co-debug.

## W3 · One committee cycle by hand (what "run it" means)
```bash
cd committee
python3 census.py --in ../source-data/branches_final.json      # DIW factories + DLT vehicles, no key
export GOOGLE_MAPS_API_KEY=...                                 # for the next two
python3 run_cycle.py --member geocoder --batch 50              # gated geocode batch
python3 scout.py --in ../source-data/branches_final.json --provinces ระยอง ชลบุรี เชียงใหม่
cd ../pipeline && python3 derive.py                            # refresh platform/data
```
Then commit: `git add -A && git commit -m "committee: manual cycle" && git push`.

## W4 · Continuous background daemon (alternative to Actions)
```bash
cd committee && GOOGLE_MAPS_API_KEY=... nohup python3 daemon.py > daemon.out 2>&1 &
```
Loops census → geocoder → scout → derive with backoff. Tuning env: `CYCLE_SLEEP_SEC` (900),
`CENSUS_EVERY_N` (24), `GEOCODE_BATCH` (50), `SCOUT_PROVINCES`. Always-on options in `deploy/`:
Dockerfile (`--restart=always`), systemd unit, Procfile (Render/Railway/Fly worker).

## W5 · Finish the geocoding backlog (~1,505 branches, ≈$48 once)
```bash
cd committee && python3 run_cycle.py --member geocoder --batch 100 --loop --max-cycles 20
```
Gate auto-rejects ambiguous matches into ITERATION_LOG's manual-review queue (e.g. @chaiyo30730 pending).
Watch `SCORECARD.json` → `precise` climb from 378. Rule: never regress a metric.

## W6 · Scale the Competitor Scout nationally
```bash
cd committee && python3 scout.py --in ../source-data/branches_final.json \
  --provinces นครราชสีมา ขอนแก่น อุดรธานี อุบลราชธานี สงขลา ภูเก็ต เชียงราย พิษณุโลก นครสวรรค์
```
Prioritize high-white-space provinces first (meta.json → leads). Census `competitor_census.json`
joins to branches as `competitors_prov`. Next refinement: subtract rival density from white space —
change is in `pipeline/derive.py` (document it in the UI when done).

## W7 · Monthly data refresh (or let Actions do it)
```bash
cd committee && python3 census.py --in ../source-data/branches_final.json   # DLT rotates monthly URLs; handled
cd ../pipeline && python3 derive.py && cd ../platform && npx vercel --prod
```
Also refresh WB Pink Sheet / OAE / HDX drought via `pipeline/autox_enrich_loop.py` (source registry
with TTLs; `--watch --interval 86400` self-refreshes).

## W8 · True 15-min isochrone upgrade (catchment view)
Replace walk-radius circles with a street-network polygon: get a free OpenRouteService key →
POST `https://api.openrouteservice.org/v2/isochrones/foot-walking` (range [300,600,900]s) per focal
branch → swap the `rings` PolygonLayer in `platform/rayong-catchment.html` for the returned GeoJSON →
recompute reachable pop = building floor-area **inside the polygon** × occupancy → update the footnote
to "street-network isochrone (foot-walking)".

## W9 · Replicate the Rayong deep-dive for another province
1. `pipeline/pull_wide.py` with the new urban bbox → building footprints (urban cores only).
2. Rebuild district polygons + rollups (containment against `adm2` geoBoundaries; pattern in PROGRESS_LOG).
3. `committee/scout.py --provinces <จังหวัด>` for rivals; DIW/DLT joins already national.
4. Assemble pages via `pipeline/build_platform.py`; add nav links. Candidates: Chonburi (EEC sibling),
   Chiang Mai (top white-space lead).

## W10 · The Calibrator (when loan-book data arrives)
Get per-branch loan volume + delinquency for even 50–100 branches → correlate against demand components
and white space → fit weights (replace equal weighting in `derive.py`) → validate the segment thesis
(crop vs livestock exposure) → log as a committee member with the same gate discipline.
This is the single highest-value unlock in the whole project.

## Guardrails (apply to every workflow)
- Members write **delta files**; only the Validator-gated merge touches `source-data/branches_final.json`.
- Never regress a SCORECARD metric; append every cycle to `ITERATION_LOG.md`.
- Keep Measured / Context / Estimated labels intact in the UI; provenance on every new field.
- Private repo; deploy `platform/` only; rotate the old DATA_GO_TH_TOKEN (exposed; now unneeded).
