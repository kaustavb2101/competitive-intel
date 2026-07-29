#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_vehicle_flow_transport.py — PORTFOLIO RISK (objective #1): province-level
COMMERCIAL vehicle-collateral churn (registration/cessation/ownership-transfer flow),
distilled from DLT's land-transport-law "การดำเนินการทางทะเบียน" monthly releases
(dataset_stat_1_009 — trucks/buses, regulated under the Land Transport Act, พ.ร.บ.
การขนส่งทางบก — a separate legal regime + dataset from the car-law releases
build_vehicle_flow.py already distills, dataset_stat_1_008).

Same method as build_vehicle_flow.py (trailing-12mo sum, plain ratios), applied to a
different vehicle population: private/contract-hire TRUCKS (รถบรรทุก ส่วนบุคคล /
ไม่ประจำทาง) and BUSES (รถโดยสาร — 4 scheduled-route classes + international + private +
non-scheduled, all summed into one bucket since none individually is collateral-central
to a title-loan book) plus a "small" bucket (รถขนาดเล็ก, an unqualified land-transport-law
category — kept separate rather than guessed into truck/bus).

The source CSVs use a DIFFERENT termination column than dataset_stat_1_008's single
"รถแจ้งไม่ใช้ตลอดไป" (permanent non-use): two separate cessation columns, "รถแจ้งเลิกใช้ ม.79"
and "รถแจ้งเลิกใช้ ม.89" (cessation of use under Land Transport Act sections 79 / 89 — the
literal column headers, not a legal opinion on what distinguishes the two sections). Both
are summed into one dereg_count/dereg_rate, same as how build_vehicle_flow.py sums a
single column — this script does not claim to know why the source splits them.

100% MEASURED, no modelling beyond the sum + a plain ratio (documented in meta.formula).
Deterministic + network-free over the already-committed CSV mirror; --check byte-exact.
Exits 3 (SKIP, not drift) when the source directory is absent or has <12 usable months.

    python3 build_vehicle_flow_transport.py
    python3 build_vehicle_flow_transport.py --check
"""
import argparse, csv, glob, json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPE)
from lib.regionmap import canonical, REGION

RAW_DIR = os.path.join(ROOT, "source-data", "dlt", "raw", "dataset_stat_1_009")
OUT = os.path.join(ROOT, "source-data", "vehicle_flow_transport_by_province.json")
WINDOW = 12  # trailing months

THAI_MONTHS = {"มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5,
               "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10,
               "พฤศจิกายน": 11, "ธันวาคม": 12}

# vehicle-class bucket -> exact match against the CSV's "ประเภทรถ" column (values already
# arrive without a trailing space, unlike dataset_stat_1_008's "รย. N " substrings)
TRUCK_TYPES = {"รถบรรทุก ส่วนบุคคล", "รถบรรทุก ไม่ประจำทาง"}
BUS_TYPES = {"รถโดยสาร ประจำทาง ระหว่างประเทศ", "รถโดยสาร ประจำทาง หมวด 1",
             "รถโดยสาร ประจำทาง หมวด 2", "รถโดยสาร ประจำทาง หมวด 3",
             "รถโดยสาร ประจำทาง หมวด 4", "รถโดยสาร ส่วนบุคคล", "รถโดยสาร ไม่ประจำทาง"}
SMALL_TYPES = {"รถขนาดเล็ก"}


def _bucket(vtype):
    v = (vtype or "").strip()
    if v in TRUCK_TYPES:
        return "truck"
    if v in BUS_TYPES:
        return "bus"
    if v in SMALL_TYPES:
        return "small"
    return None  # unrecognized category — counted in "all" only, not silently guessed


def _to_int(x):
    try:
        return int(float(str(x or 0).replace(",", "").strip() or 0))
    except Exception:
        return 0


def _list_months():
    """Every dataset_stat_1_009 file, parsed to (be_year, month_num, path), sorted ascending."""
    out = []
    for path in glob.glob(os.path.join(RAW_DIR, "*.csv")):
        name = os.path.splitext(os.path.basename(path))[0]
        tail = name.split("__")[-1]  # "<ThaiMonth>_<BEyear>"
        try:
            mth, yr = tail.rsplit("_", 1)
            out.append((int(yr), THAI_MONTHS[mth], path))
        except (ValueError, KeyError):
            continue  # not a month file we recognize — skip, don't guess
    out.sort()
    return out


def build():
    months = _list_months()
    if len(months) < WINDOW:
        return None  # not enough real data to form a trailing-12mo window — ABSENT, no fabrication
    window = months[-WINDOW:]  # most recent WINDOW months

    prov = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for _, _, path in window:
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                p = canonical((row.get("จังหวัด") or "").strip())
                if p not in REGION:
                    continue
                processed = _to_int(row.get("รถที่ดำเนินการ"))
                dereg = _to_int(row.get("รถแจ้งเลิกใช้ ม.79")) + _to_int(row.get("รถแจ้งเลิกใช้ ม.89"))
                transferred = _to_int(row.get("รถโอน"))
                bucket = _bucket(row.get("ประเภทรถ"))
                for grp in filter(None, ["all", bucket]):
                    prov[p][grp]["processed"] += processed
                    prov[p][grp]["dereg_permanent"] += dereg
                    prov[p][grp]["transferred"] += transferred

    def _rates(d):
        proc = d.get("processed", 0)
        out = dict(d)
        out["dereg_rate"] = round(d.get("dereg_permanent", 0) / proc, 4) if proc else None
        out["transfer_rate"] = round(d.get("transferred", 0) / proc, 4) if proc else None
        return out

    provinces = {p: {bucket: _rates(dict(vals)) for bucket, vals in buckets.items()}
                 for p, buckets in sorted(prov.items())}

    lo = f"{window[0][1]:02d}-{window[0][0] - 543}"
    hi = f"{window[-1][1]:02d}-{window[-1][0] - 543}"
    return {
        "meta": {
            "title": "Commercial (truck/bus) vehicle registration-transaction flow by province, "
                     "trailing 12 months (MEASURED)",
            "generated_by": "pipeline/build_vehicle_flow_transport.py",
            "label": "MEASURED — DLT gdcatalog dataset_stat_1_009 (การดำเนินการทางทะเบียน, "
                     "land-transport-law registration actions — trucks/buses under พ.ร.บ.การขนส่งทางบก, "
                     "a separate legal regime + dataset from the car-law release), summed over the "
                     f"trailing 12 available monthly releases ({lo} → {hi}). dereg_rate/transfer_rate "
                     "are plain ratios over that window's own totals — no modelling.",
            "source": "gdcatalog.dlt.go.th dataset_stat_1_009 -> source-data/dlt/raw/dataset_stat_1_009/ "
                      "(pipeline/pull_dlt_all.py, pulled 2026-07-10)",
            "formula": "dereg_rate = cessation-of-use (รถแจ้งเลิกใช้ ม.79 + รถแจ้งเลิกใช้ ม.89, both "
                      "columns summed — the source splits cessation across two Land Transport Act "
                      "sections; this script sums both without claiming to distinguish their legal "
                      "meaning) / total-processed (รถที่ดำเนินการ) over the window — collateral-ageing/"
                      "scrappage proxy for commercial vehicles. transfer_rate = ownership-transfers "
                      "(รถโอน) / total-processed — used-vehicle-market liquidity proxy.",
            "buckets": "all (every land-transport-law category) / truck (รถบรรทุก ส่วนบุคคล + "
                       "ไม่ประจำทาง — private + contract-hire trucks) / bus (all 7 รถโดยสาร categories "
                       "summed — scheduled routes 1-4, international, private, non-scheduled) / "
                       "small (รถขนาดเล็ก, an unqualified land-transport-law category kept separate "
                       "rather than guessed into truck or bus)",
            "window_months": [f"{y}-{m:02d}" for y, m, _ in window],
            "n_provinces": len(provinces),
        },
        "provinces": provinces,
    }


def run(check=False):
    data = build()
    if data is None:
        print("SKIP: source-data/dlt/raw/dataset_stat_1_009/ absent or <12 months present "
              "— not data drift, run pull_dlt_all.py for a fresh mirror")
        return 3
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: source-data/vehicle_flow_transport_by_province.json")
            return 1
        print(f"OK: vehicle_flow_transport_by_province.json reproduces byte-exact ({data['meta']['n_provinces']} provinces)")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote source-data/vehicle_flow_transport_by_province.json ({data['meta']['n_provinces']} provinces)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
