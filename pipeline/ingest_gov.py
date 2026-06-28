#!/usr/bin/env python3
"""
ingest_gov.py — fold the data.go.th pull into clean source-data layers
=====================================================================
Turns the raw CSVs in pipeline/dgt_out/ (pulled by autox_dgt_ingest.py from a
Thai network) into deterministic, app-ready JSON in source-data/. Start with the
one genuinely national table we secured:

  DIW factype3 — 66,100 factories, all 77 provinces, with district + worker counts
    -> source-data/factories_by_district.json   (real factory & worker counts,
       keyed by province|district, + province rollups)

This is the "measured" replacement for the OSM `ind10` factory proxy. 99% of the
2,015 branches join to it by (province, district).

    python3 ingest_gov.py            # (re)build the layers from dgt_out
    python3 ingest_gov.py --check    # verify committed layers match a fresh build
"""
import os, csv, json, glob, argparse, collections, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DGT  = os.path.join(ROOT, "dgt_out")
SRC  = os.path.join(REPO, "source-data")
sys.path.insert(0, ROOT)
from regionmap import canonical, REGION


def norm_district(d):
    """Drop the อำเภอ/อ./เขต prefixes so DIW อำเภอ matches the branch `district`."""
    return (d or "").replace("อำเภอ", "").replace("อ.", "").replace("เขต", "").strip()


def to_int(x):
    try:
        return int(float(str(x or 0).replace(",", "").strip() or 0))
    except Exception:
        return 0


def build_factories():
    """National DIW factory registry -> per-district factory & worker counts."""
    files = glob.glob(os.path.join(DGT, "factories_diw__factype3__*.csv"))
    if not files:
        raise SystemExit("factype3 file not found in dgt_out/ — run autox_dgt_ingest.py first")
    districts = collections.defaultdict(lambda: {"fac": 0, "workers": 0})
    provinces = collections.defaultdict(lambda: {"fac": 0, "workers": 0})
    for fp in files:
        with open(fp, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                p = canonical((r.get("จังหวัด") or "").strip())
                d = norm_district((r.get("อำเภอ") or "").strip())
                if not p or not d:
                    continue
                w = to_int(r.get("คนงานรวม"))
                key = f"{p}|{d}"
                districts[key]["fac"] += 1
                districts[key]["workers"] += w
                provinces[p]["fac"] += 1
                provinces[p]["workers"] += w
    return {
        "source": "DIW โรงงาน (factype3, data.go.th) — national factory registry; measured, not OSM proxy",
        "n_factories": sum(v["fac"] for v in provinces.values()),
        "districts": dict(sorted(districts.items())),
        "provinces": dict(sorted(provinces.items())),
    }


LAYERS = {"factories_by_district.json": build_factories}


def run(check=False):
    drift = 0
    for name, builder in LAYERS.items():
        obj = builder()
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        path = os.path.join(SRC, name)
        if check:
            if not os.path.exists(path) or open(path, encoding="utf-8").read() != text:
                print(f"DRIFT: source-data/{name} differs from a fresh build"); drift = 1
            else:
                print(f"OK: source-data/{name} reproduces from dgt_out")
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        prov = obj.get("provinces", {})
        # quick regional sanity using regionmap
        reg = collections.Counter()
        for p, v in prov.items():
            reg[REGION.get(p, "Other")] += v["fac"]
        print(f"wrote source-data/{name}: {obj['n_factories']:,} factories, "
              f"{len(obj['districts'])} districts, {len(prov)} provinces")
        print("  factories by region:", dict(reg.most_common()))
    return drift


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="fold dgt_out gov pull into source-data layers")
    ap.add_argument("--check", action="store_true", help="verify committed layers match a fresh build")
    raise SystemExit(run(check=ap.parse_args().check))
