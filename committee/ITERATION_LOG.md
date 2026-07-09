# ITERATION LOG — data-quality committee

Append-only. Each entry: what a member changed, what the validator accepted/rejected, metric delta.

## Iteration 0 — baseline — 2026-06-28
- branches: 2015
- precise geocode (places/pluscode): 354 (18%)  ← accuracy metric
- tambon-centroid: 1505 · zip: 155 · province: 1  ← the imprecise backlog
- competition measured: 1 province (Rayong, 30 rival branches)  ← richness metric
- factory source: OSM `ind10` proxy (DIW census pending Thai IP)
- demand weights: equal, uncalibrated
- honest gap: 0 branches carry AutoX internal performance data (external layer only)

## Iteration 1 — geocoder — 2026-06-28  (run live in chat, Places-verified)
- batch: 10 branches (Rayong / Chonburi / Chiang Mai, high white-space)
- Geocoder → Validator gate (brand token + name/token match + ≤12km shift + inside Thailand)
- **accepted: 9 · rejected: 1**
- precise: 354 → 362 (+8; one candidate was already precise, confirmed)
- enrichment captured: phone + hours + rating for 9 branches (rich-data bonus)
- biggest correction: เงินไชโย ชากกระปอก was **10.8 km** off its tambon centroid — exactly the error class the committee targets
- rejected (manual-review queue):
    - @chaiyo30730 เงินไชโยสาขาหมู่บ้านเจริญสินธานี: name/token mismatch (Places returned "สิรัชชาธานี") — held, not merged
- output: `source-data/branch_geo_corrections.json`

### Next
- Continue Geocoder in batches of 50 across the 1,505 tambon-centroid branches (Claude Code, Thai IP + Places/Geocoding key).
- Stand up Competitor Scout (province-by-province rival pull) → raise competition from 1 province.
- Then Industry Census (DIW/DLT from Thai IP) to replace the OSM factory proxy.

## Iteration 2 — census — 2026-06-28  (the geo-block, cracked)
- **Problem said to be impossible:** DIW/DLT geo-blocked to Thai IPs from data.go.th.
- **Solution found:** DIW publishes to its OWN CKAN portal `diw-dataset.diw.go.th`, which is NOT
  geo-blocked — reachable from this foreign sandbox (and from GitHub Actions / any cloud host).
- Pulled `factype3` (national category-3 registry): **67,416 factories, all 77 provinces**, each with
  registered capital, worker count, horsepower. Also `fac-eec-class3` (Chonburi/Rayong/Chachoengsao detail).
- Aggregated by province+district (914 districts) and **joined to 1,915/2,015 branches (95%)** →
  new fields `factory_diw`, `workers_diw`, `capital_diw`.
- **Rayong now authoritative:** 2,201 factories · 139,484 workers · ฿2.0tn capital.
  Pluak Daeng = 399 factories / 36,327 workers where OSM showed ~0. The demand model's industrial
  signal now uses DIW instead of the OSM proxy.
- Members added: `census.py` (reachable anywhere), `daemon.py` (continuous background loop),
  `deploy/` (Docker / systemd / Procfile). Workflow now runs the census in CI.
- **Still open:** DLT vehicle registrations remain Thai-IP-only (DLT hosts down/blocked). Everything
  else runs from any IP.

## Iteration 3 - census(vehicles) - 2026-06-28  (DLT cracked)
- DLT direct hosts blocked, but its OWN catalog gdcatalog.dlt.go.th (+ datagov.mot.go.th) is reachable - same side-door as DIW.
- Cumulative registered vehicles by province AND type (dataset_1_1_04): 23.2M motorcycles, 12.6M cars, 6.96M pickups nationally.
  Rayong: 878,348 vehicles, 511,079 motorcycles (58%) = the real title-collateral pool. Joined to 1,928 branches.
- census.py now pulls DIW factories AND DLT vehicles; both run from any IP.

## Iteration 4 - scout - 2026-06-28
- Competitor Scout pulled rivals for Chonburi (24) + Chiang Mai (20) via Places, brand-classified + deduped.
  Competition now measured in 3 provinces (with Rayong 30). Joined as competitors_prov. scout.py built; daemon rotates it.

## Iteration 5 - geocoder(batch 2) - 2026-06-28
- Geocoded 8 more branches -> precise 354 -> 369 (+15 vs baseline). Gate still rejecting bad matches (@chaiyo30730 held).

## Iteration 6 - live run (census + geocoder batch 3) - 2026-06-28
- census.py ran end-to-end LIVE: 67,416 DIW factories (95% joined) + DLT vehicles 77 provinces (1,928 joined).
  Fixed: DLT resource URLs rotate monthly -> census.py now resolves the newest CSV dynamically.
- geocoder batch 3 (Nonthaburi/Udon/Korat/Chiang Mai/Samut Prakan): accepted 10, rejected 0.
  precise 369 -> 378. First Isan branches now building-precise.
