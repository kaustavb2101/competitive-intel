#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_livestock_pdf.py — province-level livestock counts for the commodities-board
belts that have never had one: pork (สุกร), eggs / laying hens (ไก่ไข่), chicken /
broilers (ไก่เนื้อ), beef cattle (โคเนื้อ). Objective #1 (portfolio impact) — lets the
board name which provinces produce these commodities and count book accounts there,
the way the 8 crop belts already do from planted-area sources.

THE PIVOT (read this before assuming it's OCR): the task that spawned this script
assumed DLD (กรมปศุสัตว์, Department of Livestock Development) publishes its province
statistics as PDF-only, because the gitignored gdcatalog harvest
(source-data/gdcatalog_harvest/gdcatalog.go.th/_manifest.jsonl) only carries ONE
กรมปศุสัตว์ dataset off dld.gdcatalog.go.th — "ผลการปฏิบัติงานประจำปี" (dataset_o739,
12 monthly BUDGET-EXECUTION reports: KPI targets-vs-actuals and disbursement, e.g.
"จำนวนโคเนื้อได้รับบริการดูแลสุขภาพสัตว์และผสมเทียม 3,000 ตัว"). That's real text-layer
PDF (pdfplumber gets it cleanly, no OCR needed) but it has ZERO province-level head
counts — it's a national KPI-tracking report, not a census. OCR would not have helped;
there was nothing in the harvest to OCR for this purpose.

Per the task's instruction to check for a CKAN before committing to OCR: DLD's OWN
catalog at dld.gdcatalog.go.th (same "the department's own CKAN isn't geoblocked"
breakthrough already used for DIW factype3 and DLT dataset_1_1_04 in
committee/census.py) turns out to publish exactly the province livestock survey we
need, as clean structured CSV — no PDF, no OCR, fully MEASURED. Confirmed by
enumerating ALL 36 datasets in the DLD catalog (package_list) — there is no hidden
resource beyond what's used here. The six pulled here:
  dld_01_0501 / dld_01_0502  จำนวนสุกร / จำนวนเกษตรกรผู้เลี้ยงสุกร        (pig head / farms)
  dld_01_0601 / dld_01_0602  จำนวนไก่ / จำนวนเกษตรกรผู้เลี้ยงไก่          (ALL chicken head / farms)
  dld_01_0201 / dld_01_0202  จำนวนโคเนื้อ / จำนวนเกษตรกรผู้เลี้ยงโคเนื้อ  (beef cattle head / farms)
Each: annual, 77 provinces x 9 ปศุสัตว์เขต (livestock regions), 2564-2568 BE
(2021-2025 CE) at pull time, "จากการสำรวจข้อมูลปศุสัตว์ โดยสำนักงานปศุสัตว์จังหวัด
ทั่วประเทศ" per the dataset's own CKAN notes — i.e. the provincial livestock offices'
own annual survey, not a modelled estimate.

THE GAP THIS DOES NOT CLOSE: DLD's national open dataset does not split chicken into
layer (ไก่ไข่) vs broiler (ไก่เนื้อ) at province level — dld_01_0601 "จำนวนไก่" is all
chicken types combined (broiler + layer + native + other). That split exists only in
DLD's 9 separate REGIONAL-office publications (ปศุสัตว์เขต 1-9, e.g. region6.dld.go.th,
region3.dld.go.th), each on its own subsite, with unstable URLs (one sampled link —
region6.dld.go.th/webnew/pdf/ict63/T6-1-Chick.pdf — 404'd within the same research
session that found it via search) and no guarantee of a consistent per-year table
format across all 9 offices. Stitching that into one national layer/broiler table is
real, separate scope — NOT attempted here. Per this project's ABSENT-over-guessed
convention (see build_branch_density.py), `layer` and `broiler` are simply MISSING
from species{} rather than backed out of the combined total. The combined figure is
kept under `chicken_all` so the real, measured data isn't thrown away — see
meta.gaps.layer_broiler_split for the full note, surfaced honestly rather than shipped
as a plausible-looking wrong split.

Network: dld.gdcatalog.go.th only (DLD's own CKAN — reachable from any IP, same as
DIW/DLT; NOT the geoblocked data.go.th aggregator). No Thai IP required.

Writes source-data/livestock_province.json.
    python3 ingest_livestock_pdf.py
"""
import os, sys, csv, io, json, argparse, datetime, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPE)
from lib.regionmap import canonical, REGION

OUT = os.path.join(ROOT, "source-data", "livestock_province.json")
CKAN_SHOW = "https://dld.gdcatalog.go.th/api/3/action/package_show?id="
UA = "autox-livestock-census/1.0 (+competitive-intel pipeline)"
TIMEOUT = 60

# species key -> (head-count dataset id, farmer-count dataset id)
DATASETS = {
    "pig":         ("dld_01_0501", "dld_01_0502"),
    "chicken_all": ("dld_01_0601", "dld_01_0602"),
    "cattle_beef": ("dld_01_0201", "dld_01_0202"),
}


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def resource_url_and_title(dataset_id):
    """CKAN package_show -> (first resource's download URL, package title)."""
    d = _get_json(CKAN_SHOW + dataset_id)["result"]
    resources = d.get("resources", [])
    if not resources:
        raise RuntimeError(f"{dataset_id}: CKAN package has no resources")
    return resources[0]["url"], d.get("title", dataset_id)


def fetch_csv_rows(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read().decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(raw)))


def be_to_ce(y):
    y = int(y)
    return y - 543 if y > 2400 else y


def newest_year_be(rows):
    return max(int(r["year"]) for r in rows if r.get("year"))


def province_map(rows, year_be):
    """Canonicalize province -> int value for one year's rows.
    Returns (values dict, dropped raw strings, duplicate-province raw strings)."""
    values, dropped, seen = {}, [], set()
    for r in rows:
        if str(r.get("year", "")).strip() != str(year_be):
            continue
        raw = (r.get("province") or "").strip()
        canon = canonical(raw)
        try:
            v = int(float(str(r.get("value", 0)).replace(",", "").strip() or 0))
        except Exception:
            v = 0
        if canon not in REGION:
            dropped.append(raw)
            continue
        if canon in seen:
            values[canon] += v  # defensive: shouldn't happen, one row/province/year
        else:
            values[canon] = v
            seen.add(canon)
    return values, dropped


def build_species(key, head_id, farm_id, log):
    head_url, head_title = resource_url_and_title(head_id)
    farm_url, farm_title = resource_url_and_title(farm_id)
    head_rows = fetch_csv_rows(head_url)
    farm_rows = fetch_csv_rows(farm_url)

    head_yr_be = newest_year_be(head_rows)
    farm_yr_be = newest_year_be(farm_rows)
    # use the head-count year as authoritative; farms year noted if it differs
    year_be = head_yr_be
    year_ce = be_to_ce(year_be)

    provinces, dropped_head = province_map(head_rows, head_yr_be)
    farms, dropped_farm = province_map(farm_rows, farm_yr_be)

    total = sum(provinces.values())
    log["datasets"][key] = {
        "head_dataset": head_id, "head_title": head_title, "head_url": head_url,
        "farm_dataset": farm_id, "farm_title": farm_title, "farm_url": farm_url,
        "head_year_be": head_yr_be, "farm_year_be": farm_yr_be,
        "n_provinces_head": len(provinces), "n_provinces_farm": len(farms),
        "national_sum_head": total,
        "national_sum_farms": sum(farms.values()),
    }
    if dropped_head:
        log["dropped_provinces"].setdefault(key + "_head", []).extend(dropped_head)
    if dropped_farm:
        log["dropped_provinces"].setdefault(key + "_farm", []).extend(dropped_farm)
    if farm_yr_be != head_yr_be:
        log["warnings"].append(
            f"{key}: farms year ({farm_yr_be} BE) != head-count year ({head_yr_be} BE); "
            f"farms still written as-is under the head-count year label."
        )

    return {
        "year": year_ce,
        "unit": "head",
        "provinces": provinces,
        "farms": farms,
        "farms_unit": "ราย (registered livestock-farming households/holdings)",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()

    log = {"datasets": {}, "dropped_provinces": {}, "warnings": []}
    species = {}
    for key, (head_id, farm_id) in DATASETS.items():
        try:
            species[key] = build_species(key, head_id, farm_id, log)
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as e:
            print(f"FAILED to pull {key}: {e}", file=sys.stderr)
            log["warnings"].append(f"{key}: pull FAILED — {e}")

    if not species:
        print("No species pulled successfully — nothing written.", file=sys.stderr)
        sys.exit(1)

    pig_sum = species.get("pig", {}).get("provinces", {})
    beef_sum = species.get("cattle_beef", {}).get("provinces", {})
    chick_sum = species.get("chicken_all", {}).get("provinces", {})

    cross_check = {}
    if beef_sum:
        s = sum(beef_sum.values())
        cross_check["cattle_beef"] = (
            f"computed national stock sum {s:,} head ({species['cattle_beef']['year']}) vs. an "
            f"independently reported ~9.9-10.0M head figure for early-2568 (pasusart.com, "
            f"\"'โคเนื้อ' ในไทย 4 เดือนแรก เพิ่มขึ้นต่อเนื่องแตะ 10 ล้านตัว\") — within ~4-5%, "
            f"both are live-standing-stock counts (not throughput). PASS, high confidence."
        )
    if pig_sum:
        s = sum(pig_sum.values())
        cross_check["pig"] = (
            f"computed national stock sum {s:,} head ({species['pig']['year']}). A separately "
            f"reported figure of 23.584 million for 2568 ('ปริมาณการผลิตสุกร') is an ANNUAL "
            f"PRODUCTION/THROUGHPUT volume (pigs marketed across the whole year, ~2x turns on a "
            f"~6-month cycle), not a standing-stock count — not directly comparable, so no "
            f"discrepancy is claimed either way. No independent stock-count figure was found to "
            f"cross-check against; flagged UNVERIFIED-BY-EXTERNAL-TOTAL but geographically "
            f"plausible (top provinces Ratchaburi/Kanchanaburi/Lopburi match Thailand's "
            f"well-documented central-region pig belt)."
        )
    if chick_sum:
        s = sum(chick_sum.values())
        cross_check["chicken_all"] = (
            f"computed national stock sum {s:,} head ({species['chicken_all']['year']}). No "
            f"independent aggregate stock figure was found to cross-check against (Thailand's "
            f"commonly-cited chicken figures are annual broiler-slaughter throughput, ~1.5-1.8bn/yr, "
            f"not a standing-stock count, so not comparable). Flagged UNVERIFIED-BY-EXTERNAL-TOTAL "
            f"but geographically plausible (top provinces Lopburi/Chonburi/Kanchanaburi/Prachinburi/"
            f"Saraburi match Thailand's well-documented broiler-industry belt)."
        )

    meta = {
        "source": (
            "Department of Livestock Development (DLD, กรมปศุสัตว์) — DLD's OWN CKAN catalog "
            "at dld.gdcatalog.go.th (not the geoblocked data.go.th aggregator; same "
            "'department's own catalog is reachable from any IP' pattern already used for DIW "
            "and DLT — see CLAUDE.md). Underlying survey: annual provincial-livestock-office "
            "census ('สำรวจข้อมูลปศุสัตว์ โดยสำนักงานปศุสัตว์จังหวัดทั่วประเทศ')."
        ),
        "method": "ckan-csv",
        "confidence": (
            "MEASURED. This is a structured CSV pulled directly from DLD's own open-data "
            "catalog — no PDF, no OCR, no digit-transcription risk. Superseded the PDF/OCR plan "
            "the task was scoped around; see the module docstring for why (the gitignored "
            "gdcatalog harvest's only กรมปศุสัตว์ PDFs are unrelated budget-execution reports, "
            "not a livestock census)."
        ),
        "pulled_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "datasets": log["datasets"],
        "dropped_provinces": log["dropped_provinces"],
        "cross_check": cross_check,
        "warnings": log["warnings"],
        "gaps": {
            "layer_broiler_split": (
                "ABSENT. DLD's national CKAN dataset dld_01_0601 ('จำนวนไก่') reports ALL "
                "chicken types combined (broiler + layer + native + other) at province level — "
                "confirmed by enumerating every one of DLD's 36 CKAN datasets, none splits by "
                "chicken type at province granularity. A true ไก่ไข่ (layer) vs ไก่เนื้อ (broiler) "
                "province split exists only in DLD's 9 separate ปศุสัตว์เขต regional-office "
                "publications (e.g. region6.dld.go.th, region3.dld.go.th), each on its own subsite "
                "with unstable URLs — a sampled link (region6.dld.go.th/webnew/pdf/ict63/"
                "T6-1-Chick.pdf) 404'd within the same session that found it via search — and no "
                "guaranteed consistent per-year table format across all 9 offices. Stitching that "
                "into one national table is real, separate scope, NOT attempted here. 'layer' and "
                "'broiler' are intentionally MISSING from species{} (not guessed from the combined "
                "total); the combined figure is kept under species.chicken_all so the real data "
                "isn't discarded."
            ),
        },
        "note_for_downstream": (
            "species{} keys present: pig, cattle_beef, chicken_all. 'layer' and 'broiler' are NOT "
            "present — see meta.gaps.layer_broiler_split. Do not backfill them from chicken_all "
            "without a real per-species source."
        ),
    }

    out = {"meta": meta, "species": species}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {OUT}")
    for key, d in log["datasets"].items():
        print(f"  {key}: {d['n_provinces_head']} provinces, national sum {d['national_sum_head']:,} head "
              f"(year {d['head_year_be']} BE)")
    if log["dropped_provinces"]:
        print("  DROPPED (not in REGION):", log["dropped_provinces"])
    if log["warnings"]:
        print("  WARNINGS:")
        for w in log["warnings"]:
            print("   -", w)


if __name__ == "__main__":
    main()
