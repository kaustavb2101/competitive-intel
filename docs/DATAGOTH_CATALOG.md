# data.go.th + NSO open-data catalog (Thai-IP pull)

**The unlock:** `data.go.th` and the department CKANs are Cloudflare geo-blocked to foreign/datacenter
IPs (so they fail from GitHub Actions and the cloud sandbox) but are **reachable from Kaustav's Thai
residential IP**. `pipeline/pull_datagoth.py` pulls the verified datasets below from the Thai laptop.
No auth token is required by any source.

```bash
cd pipeline && python3 pull_datagoth.py            # pull every registered source
python3 pull_datagoth.py --list                    # show the registry
python3 pull_datagoth.py --only fpo_pico diw_factories
```
Raw files cache to `source-data/datagoth/` (gitignored; re-pullable) with a `manifest.json` recording
each source URL, fetch time, byte size and status for honest provenance. First run: **10/12 sources OK.**

## Verified sources (pulled 2026-07-12 from a Bangkok IP)

| id | Signal | Org | Granularity | Status |
|---|---|---|---|---|
| `fpo_pico` | **Licensed PICO-finance operators — direct competitor registry (name, province, full address, phone, license date)** | FPO | province + address | ✅ 768 KB |
| `dbd_newco` | New company registrations (business-formation demand) | DBD | subdistrict, monthly | ✅ 5.4 MB |
| `smebank_credit` | SME-bank credit outstanding by province | SME Bank | province, monthly | ✅ |
| `diw_factories` | Class-3 factory registry (name/addr/capital/workers/HP) | DIW | subdistrict | ✅ 44 MB |
| `mot_vehicles` | Registered vehicles (collateral base) | MOT | province/type | ✅ 172 KB |
| `excise_moto_tax` | Motorcycle-tax collections (moto-sales proxy) | Excise | national, monthly | ✅ 597 KB |
| `excise_car_tax` | Car-tax collections (car-sales proxy) | Excise | national, monthly | ✅ 1 MB |
| `baac_credit` | BAAC personal credit by area | BAAC | province | ✅ 21 KB |
| `nso_household_debt` | SES household debt | NSO | region | ✅ 73 KB |
| `nso_unemployment` | Unemployment rate | NSO | region | ✅ |
| `osmep_sme_growth` | MSME counts / growth | OSMEP | province | ⚠ 404 (package id needs refresh) |
| `nso_agri_income_debt` | Agri income & debt by province | NSO | province | ⚠ HTTP 500 (retry/resource) |

> **✅ = the 2026-07-12 pull succeeded; it does NOT mean the source is distilled into a committed
> layer.** Distilled + shipped: `fpo_pico` → `pico_census.json`, `dbd_newco` → `dbd_formation.json`,
> `diw_factories` → factory layers, `mot_vehicles` → vehicle layers. **Pulled but never distilled:**
> `baac_credit`, `smebank_credit` (the formal-credit **penetration** signal). Their raw CSVs are in the
> gitignored `source-data/datagoth/` cache, so nothing is committed — and the data.go.th aggregator is
> now **403 from CI** (re-verified 2026-07-17), so they **cannot be rebuilt from the cloud**. To finish
> them, re-pull from the Thai IP and **commit** the raw CSV (or a distilled per-province layer). Full
> blocked-source status + owner-side unblocks: **`docs/BLOCKED_SOURCES.md`**.

## Access notes
- **data.go.th CKAN** (`https://data.go.th/api/3/action/`) — open, CKAN 2.10.1, no token. ~30 distinct
  high-relevance national/multi-province dataset families; every province also self-publishes NSO/DLT/OAE
  indicators as single-province CSVs.
- **NSO** — `catalog.nso.go.th` (NSO's own CKAN, 913 datasets) works **with a browser User-Agent**;
  `catalogapi.nso.go.th/api/index?table=…` is intermittently CloudWAF-blocked (worked for some tables
  from the Thai IP; falls back to the CKAN resources / the data.go.th `org=nso` mirror otherwise).
- **DLT** own host `gdcatalog.dlt.go.th` is unreachable from this connection — use MOT
  (`datagov.mot.go.th`) or Excise vehicle-tax as the vehicle-volume signal instead.
- **NESDC / Bank of Thailand** are not on data.go.th (GPP comes from the 77 province orgs; household
  debt from NSO SES + FPO, not BOT).

## Next: distill into province/branch layers
The raw pulls are inputs. Downstream builders normalize them into the committed province/district layers
(e.g. fold `fpo_pico` into the competitor census, `mot_vehicles`/excise into collateral, `dbd_newco`
into demand/whitespace) — always keyed on the canonical 77 Thai province names / 928 amphoe.
