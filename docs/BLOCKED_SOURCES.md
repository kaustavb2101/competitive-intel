# Blocked-source ledger — what CI can and cannot pull

> **Why this file exists.** The integration loop repeatedly rediscovers the same wall: the highest-value
> data unlocks left are all gated behind a network block or a missing key, so run after run burns its
> whole budget re-probing the same hosts before concluding "blocked, skip, log". This ledger captures
> that knowledge **with live HTTP evidence** so a future run (or Kaustav) can read the state in seconds
> instead of re-deriving it. It is the honest companion to `docs/DATAGOTH_CATALOG.md` (which lists what
> _was_ pulled from a Thai IP) — this file lists what **cannot** be pulled from CI **now**, and the exact
> owner-side action that unblocks each.
>
> **Provenance of the evidence below:** every status code was measured live from this GitHub-Actions /
> cloud sandbox on the date stamped. Re-verify any row in one paste with the probe block at the bottom —
> a `403`/`000` that flips to `200` means the block lifted and the integration is now doable.

_Last probed: **2026-09-05** (from the cloud runner). Prior probe 2026-09-04 — every `403`/`000`
status below is **unchanged** since (nothing flipped open, so no integration became CI-doable). The one
refinement this pass: **NSO's own CKAN `catalog.nso.go.th` is CI-reachable (`200`)** — it was framed as
"vendored" rather than a live department-CKAN path, so it now sits in the reachable-from-CI list below,
**with the caveat that its household-debt vintage is staler than what the app already ships** (so it is
reachable but not a refresh source — see that note). Earlier refinement (2026-09-04): the GISTDA row was
probing the *landing* host, not the API host the puller actually calls._

## The one-screen summary

- **Everything reachable from CI is already integrated.** DIW factories, DLT/MOT vehicles, DBD company
  formation, FPO PICO competitor registry, NABC farm-gate prices, Overture/OSM, World Bank, ILOSTAT
  labour context, NSO SES/LFS (vendored) — all distilled into committed, `--check`-gated,
  provenance-stamped layers. See `docs/AUTONOMY_PLAN.md` (0 open) and `docs/DATAGOTH_CATALOG.md`.
- **What's left is blocked, and the blocks are owner-side, not code-side.** No amount of CI work opens
  them; they need Kaustav's Thai residential IP, a real core-banking export, or a secret wired into the
  workflow env. They are listed below, most-valuable first.

## Blocked frontier sources (re-measured 2026-09-04; unchanged vs 2026-07-17 except the GISTDA host refinement)

| Source | Signal (objective) | Host probed | Status | Why blocked | Owner-side unblock |
|---|---|---|---|---|---|
| ~~**Real loan tape**~~ | vintage 90+ aging, branch ROI, PD calibration — **direct portfolio risk (#1)** | (core banking export, no host) | ✅ **UNBLOCKED 2026-07-21** | — | **DONE.** 382,735 real accounts landed via `ingest_real_tape.py` → `build_tape_layers.py` → `tape_real.json` + `tape_geo_occ.json`. This row is kept struck-through rather than deleted because it was named "the single highest-leverage unlock left" for months and its absence would read as an oversight. The open question is now refresh **cadence**, not existence. |
| **BAAC personal credit** by province | formal-credit **penetration** (inverse of title-loan demand, #1) | `data.go.th/api/3/action/package_show?id=baac02_2567` | **403** | data.go.th **aggregator** is Cloudflare geo-blocked to datacenter IPs. BAAC's own host (`catalog.baac.or.th`) is unreachable (`000`). Pulled once from a Bangkok IP 2026-07-12 (21 KB) but the raw cache is gitignored + **never distilled**, so nothing is committed and it cannot be rebuilt from CI. | Re-pull `baac_credit` via `pull_datagoth.py` from the Thai laptop, **commit the raw CSV** (or a distilled `baac_credit_by_province.json`), then a CI builder can distill it deterministically. |
| **SME-bank credit** outstanding by province | SME formal-credit penetration (#1) | `data.go.th/api/3/action/package_show?id=smedbank-outprovince` | **403** | Same aggregator geo-block; `opendata.smebank.co.th` unreachable (`000`). Same never-distilled state as BAAC. | Same as BAAC — Thai-IP pull + commit, then distill. |
| **GISTDA 40m satellite crop-area** | measured per-branch crop-area to **supersede the SPAM baseline** in `build_branch_cropland.py` (#1) | `api.sphere.gistda.or.th` (API host, what the puller calls); `sphere.gistda.or.th` (landing) | API host **000**; landing intermittent (**200/000**); **`GISTDA_SPHERE_KEY` still absent** | **Doubly blocked (2026-09-04).** The check-crop / isochrone **API host `api.sphere.gistda.or.th` is unreachable from CI (`000`, stable across re-probes)**, *and* the repo secret is not mapped into this run's env. NB: the 2026-07-17 "host **200**, reachable" read probed the *landing* page `sphere.gistda.or.th` (intermittent), not the API host — corrected here so a future run doesn't chase a CI path that dies at the host. | Run the puller from Kaustav's Thai machine (which reaches `api.sphere.gistda.or.th` directly), **and** map `GISTDA_SPHERE_KEY` into the env. Mapping the key alone will **not** unblock CI while the API host returns `000`. |
| **NESDC GPP** per province | economic vitality backdrop (#1) — currently ⚠ ESTIMATED (only 1/77 CKAN-verified, see NEXT_STEPS §0a) | `opendata.nesdc.go.th` | host **200**, but **no clean dataset** | The reachable `opendata.nesdc.go.th` is a government-wide **project** catalog; a keyword search (`GPP`, `ผลิตภัณฑ์มวลรวมจังหวัด`) returns 0 relevant datastores. GPP is published as Excel/PDF SNA tables on `www.nesdc.go.th`, not as a CKAN datastore. | Obtain the per-province GPP SNA table (Excel) and vendor it into `source-data/`, then a builder can replace the estimated `gpp_by_province.json`. Do **not** ship the current estimated file labelled MEASURED. |
| **Excise vehicle-tax** collections | motorcycle/car-sales proxy = collateral flow (#1) | `catalog.excise.go.th` | **000** | Host unreachable from CI (connection failure, not just geo-403). The vehicle **stock** signal is already covered by the committed DLT/MOT layers, so this is a nice-to-have, not a gap. | Thai-IP pull via `pull_datagoth.py --only excise_moto_tax excise_car_tax`, commit + distill. |
| **data.go.th aggregator** (general) | ~30 dataset families | `data.go.th/api/3/action/*` | **403** | Cloudflare geo-block to datacenter IPs. Department **own** CKANs (DIW, MOT) are the CI-reachable path and are already used. | Thai-IP pull for any family without a reachable department mirror. |
| **DLT own host** | vehicle registrations by district | `gdcatalog.dlt.go.th` | unreachable | Documented in `DATAGOTH_CATALOG.md`; MOT (`datagov.mot.go.th`, **200**) is the working substitute and is already distilled. | None needed — MOT substitute is live. |

## Reachable from CI (for contrast — all already integrated)

`datagov.mot.go.th` (200), `catalog.oae.go.th`, `agriapi.nabc.go.th`, `thedocs.worldbank.org`,
`stats.bis.org`, the Overpass mirror, DIW `diw-dataset.diw.go.th`, `catalog.nso.go.th` (200 — see the
NSO note directly below), and the department CKANs behind the committed vehicle/factory/DBD/PICO layers.
If a new run wants to _refresh_ these, note that most already have a scheduled workflow (NABC prices,
fuel prices) — check `.github/workflows/` before pulling by hand.

**NSO own CKAN `catalog.nso.go.th` — reachable from CI, but NOT a refresh source for household debt
(verified 2026-09-05).** It returns real JSON (`success:true`) exactly like the DIW/MOT department CKANs
— the "geo-blocked, Thai-IP-only" framing applied only to the `data.go.th` **aggregator**, not to NSO's
own catalog, and `nso_unemployment` is already pulled from it in CI (`build_labour_context.py`). BUT the
household-debt package `0705_08_0009` (`หนี้สินเฉลี่ยต่อครัวเรือน`) tops out at survey year **2564
(2021)**, which is **older** than the **SES 2566 (2023)** figure the app already ships (vendored,
`source-data/household_debt_by_province.json`, CKAN-citable via `nso-ses-debt-2566.json`). So re-pulling
household debt from `catalog.nso.go.th` would *regress* the vintage — do not "refresh" off it. **Precise
recheck trigger:** a per-province **SES 2566 or newer** (e.g. 2568) debt resource appearing on
`catalog.nso.go.th` package `0705_08_0009` (or a sibling SES package) — only then is a CI-side refresh of
the debt layer an actual improvement over the vendored file. Until then this is a live-but-staler
mirror, logged so future runs stop treating NSO as a Thai-IP-only unlock.

## Re-verify in one paste

```bash
for u in \
  "https://data.go.th/api/3/action/package_show?id=baac02_2567" \
  "https://data.go.th/api/3/action/package_show?id=smedbank-outprovince" \
  "https://catalog.excise.go.th/api/3/action/datastore_search?resource_id=a8d9115a-708d-420d-b796-e96b373ad1b8&limit=1" \
  "https://api.sphere.gistda.or.th/services/route/isochrone" \
  "https://opendata.nesdc.go.th/api/3/action/package_search?q=GPP&rows=1" \
  "https://catalog.nso.go.th/api/3/action/package_show?id=0705_08_0009" \
  "https://datagov.mot.go.th/api/3/action/package_search?q=test&rows=1" ; do
  echo "$(curl -s -o /dev/null -w '%{http_code}' -m 8 -A 'Mozilla/5.0' "$u")  $u"
done
[ -n "$GISTDA_SPHERE_KEY" ] && echo "GISTDA key: present" || echo "GISTDA key: absent"
```

A row that flips `403`/`000` → `200` (or the GISTDA key appearing) means that integration is now doable
from CI — pick it up.
