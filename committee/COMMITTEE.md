# COMMITTEE.md — the data-quality committee

A standing committee that revamps the platform toward full accuracy and rich data by running a
**recursive, gated loop**: small batch → member improves it → validator gates it → log → repeat.
One verifiable improvement per cycle. Never regress a metric. Everything stays labeled
measured / context / estimated.

## Members (each owns one dimension)

1. **Orchestrator (Chair)** — `run_cycle.py`
   Reads `SCORECARD.json`, picks the next smallest highest-value task, assigns it, enforces the rules,
   updates the scorecard + `ITERATION_LOG.md`. The recursion controller. Batch size starts small
   (10) and grows as confidence grows.

2. **Geocoder** — `geocoder.py`
   Raises **location accuracy**: tambon/zip centroid → precise coordinates (Google Places/Geocoding,
   or OSM/Nominatim). Also captures enrichment (phone, hours, rating). Metric: **% precise**.

3. **Competitor Scout** — `scout.py`  (built)
   Raises **competitive richness**: pulls rival branches (Srisawad, Muangthai, Tidlor, Krungsri, …)
   province by province. Metric: **provinces with measured competition** (baseline: 1 — Rayong).

4. **Industry Census** — `census.py`  ✅ built · runs from ANY IP
   Authoritative **DIW factory registry** via DIW's own CKAN (`diw-dataset.diw.go.th`, not the blocked
   data.go.th) — 67,416 factories, 77 provinces, with capital + workers + horsepower. Joined to 95% of
   branches. DLT vehicles also solved via gdcatalog.dlt.go.th (any IP). Metric: **% branches on authoritative factory data** (now 95%).

5. **Calibrator** — (to add) `calibrator.py`
   Refines the demand model (component weights) and — once AutoX internal data exists — validates
   scores against real branch outcomes. For now: sensitivity/robustness + documentation.
   Metric: **robustness**, later **predictive validity**.

6. **Validator (QA)** — `validator.py`
   The gate every change passes before merge. Checks: coordinate bounds (inside Thailand),
   name/token match, max-shift threshold, dedup, **no-regression** on the scorecard, honesty labels intact.
   Metric: **tests passing**; every rejection is logged with a reason (never silently dropped).

## The recursive protocol (one cycle)
```
1. Orchestrator reads SCORECARD.json → picks next task (smallest batch, best value/effort).
2. Assigned member produces a candidate delta file  (never edits the master directly).
3. Validator runs the gate  → accepted / rejected  (rejections logged with reason).
4. Accepted deltas merged into source-data master  → SCORECARD updated → ITERATION_LOG appended.
5. Repeat.  Grow batch size as the accept-rate stays high.
```

## Rules (non-negotiable)
- **One verifiable improvement per cycle.** No sweeping rewrites.
- **Never regress a metric.** If the scorecard would drop, the change is rejected.
- **Master data is append/merge, never blind-overwrite.** Deltas are separate files first.
- **Keep rejections.** They're the manual-review queue, not garbage.
- **Label everything** measured / context / estimated. Accuracy claims must be checkable.
- **Provenance on every field** (source + date).

## Continuous background operation
`committee/daemon.py` loops forever (census → geocoder → derive → sleep). Run it under Docker/systemd/
a cloud worker — see `deploy/`. Because DIW is reachable anywhere, this needs no Thai IP (only DLT does).

## How to run one cycle (Claude Code or CI)
```bash
cd committee
export GOOGLE_MAPS_API_KEY=...        # or configure Nominatim in geocoder.py
python3 run_cycle.py --member geocoder --batch 10     # one gated cycle
python3 run_cycle.py --member geocoder --batch 50 --loop   # keep iterating recursively
```
Then regenerate `platform/data/` from the updated master and redeploy (see docs/ARCHITECTURE.md).

## Current standing (see SCORECARD.json + ITERATION_LOG.md)
- Iteration 0 (baseline): 354/2,015 precise (18%), competition in 1 province, factories = OSM proxy.
- Iteration 1 (done, in chat): geocoded 10 branches → +8 precise, 1 rejected by gate, enrichment captured.
- Next: continue Geocoder in batches of 50 across the 1,505 tambon-centroid branches; stand up Competitor Scout.
