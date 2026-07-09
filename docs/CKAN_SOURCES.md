# CKAN_SOURCES.md — reachable Thai government open-data catalogs

The breakthrough (docs/INSIGHTS.md §3, re-verified 2026-07-09 from the cloud sandbox): the
`data.go.th` aggregator is Cloudflare-geoblocked to datacenter IPs, but several **departments' own
CKAN catalogs are not**. This is the live map of what a cloud runner / GitHub Action can actually pull,
so future sessions don't rediscover it or chase the laptop.

Probe: `GET https://<host>/api/3/action/package_search?q=&rows=0` (CKAN count endpoint).

## ✅ Reachable (HTTP 200 from the sandbox)
| Catalog | Host | Datasets | Highest-value contents |
|---|---|---|---|
| **DIW** factories | `diw-dataset.diw.go.th` | — | `factype3` (~67k category-3 factories, all 77 prov, with workers + registered capital). Used by `committee/census.py`. **MEASURED.** |
| **DLT** vehicles | `gdcatalog.dlt.go.th` | — | `dataset_1_1_04` (registered vehicles by province + type; national 44.29M — moto 23.4M / car 13.1M / pickup 6.96M). Resource URLs rotate monthly — resolve the newest CSV via the API. **MEASURED.** |
| **OAE** agriculture | `catalog.oae.go.th` | 57 | See below. **MEASURED.** |
| **NABC** live prices | `agriapi.nabc.go.th` (REST, not CKAN) | — | Daily Thai market prices — crops · livestock · fisheries. Already wired: `pull_nabc_prices.py` → `build_branch_agri.py` **and** `build_crop_stress.py` (preferred over the WB global proxy). **MEASURED.** |

### OAE (`catalog.oae.go.th`) — datasets worth pulling next
- `ai-drought-warning` — **SPEI drought index by amphoe** (per-district) — the natural measured upgrade
  for the rainfall-anomaly drought proxy in `build_crop_stress.py`. (format: HTML dashboard — needs a
  resource/scrape path.)
- `dataset66-15-03` — **net cash farm income** ฿/household (national; JSON) — objective-#1 context.
- `dataoae1104` / `dataoae1204` / `dataoae1304` / `dataoae1404` / `dataoae1504` — production quantity
  (rice / maize / cassava / rubber / oil palm), CSV/XLSX.
- `dataset-12-*` — households + planted area per crop (per-crop; mostly PDF).
- `farmer-family` — registered farmer households.

Note: OAE's CKAN is mostly **annual/national production & value** data, NOT a monthly per-crop
farm-gate PRICE series — that lives in OAE's price system. For prices, **NABC (daily, live) is already
the better source and is wired in**, so the "farm-gate price" gap is effectively closed.

## ❌ Blocked / not CKAN from the sandbox (2026-07-09)
| Catalog | Result |
|---|---|
| `data.go.th` (the aggregator) | geoblocked (Cloudflare) — the whole reason to use department catalogs |
| MOC commerce prices `data.moc.go.th` | 404 (no CKAN at this path — needs a different endpoint) |
| TMD weather `data.tmd.go.th` | 403 |
| NESDC `data.nesdc.go.th` | 502 (proxy tunnel) — GPP stays the vendored, partly-estimated file |
| DOAE `opendata.doae.go.th` | 404 |
| NSO `catalog.nso.go.th` | 418 |
| DEDE `data.dede.go.th` | SSL cert verify failed |
| LDD `catalog.ldd.go.th` | 502 |

Competitor corporate store-locators (muangthaicap / sawad / tidlor / hengleasing) are also blocked from
the datacenter IP — the national competitor census (`competitors_census.json`, 16,503 points) was
already pulled and can't refresh from CI. A real **loan-tape export** remains the only true owner-side
data unlock.
