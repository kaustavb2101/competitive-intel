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


def _biggest(pattern):
    """Pick the largest CSV matching a glob (the most complete national table)."""
    files = glob.glob(os.path.join(DGT, pattern))
    if not files:
        raise SystemExit(f"no file matching {pattern} in dgt_out/ — run autox_dgt_ingest.py")
    return max(files, key=os.path.getsize)


def build_vehicles():
    """National DLT registrations -> per-province vehicle stock (car/pickup/moto/EV)."""
    prov = collections.defaultdict(lambda: {"total": 0, "car": 0, "pickup": 0, "moto": 0, "ev": 0})
    with open(_biggest("vehicles_dlt__dataset_1_1_04__*.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            p = canonical((r.get("จังหวัด") or "").strip())
            if not p:
                continue
            n = to_int(r.get("จำนวนรถ"))
            vtype = (r.get("ประเภทรถ") or ""); legal = (r.get("ประเภทกฎหมาย") or ""); fuel = (r.get("ประเภทเชื้อเพลิง") or "")
            prov[p]["total"] += n
            if "จักรยานยนต์" in legal or "จักรยานยนต์" in vtype:
                prov[p]["moto"] += n
            elif "รย. 1" in vtype or "นั่งส่วนบุคคล" in vtype:
                prov[p]["car"] += n
            elif "รย. 3" in vtype or "บรรทุกส่วนบุคคล" in vtype:
                prov[p]["pickup"] += n
            if fuel.strip() == "ไฟฟ้า":
                prov[p]["ev"] += n
    return {"source": "DLT รถจดทะเบียน (data.go.th) — national vehicle stock by province; measured",
            "n_vehicles": sum(v["total"] for v in prov.values()),
            "provinces": dict(sorted(prov.items()))}


def build_employment():
    """NSO labour force -> per-province formal/informal workers (latest year)."""
    rows = list(csv.DictReader(open(_biggest("employment__skn_nso8__*.csv"), encoding="utf-8-sig")))
    years = [to_int(r.get("ปี")) for r in rows if to_int(r.get("ปี"))]
    latest = max(years) if years else 0
    prov = collections.defaultdict(lambda: {"formal": 0, "informal": 0})
    for r in rows:
        if to_int(r.get("ปี")) != latest:
            continue
        p = canonical((r.get("จังหวัด") or "").strip())
        if not p:
            continue
        n = to_int(r.get("จำนวน")); kind = (r.get("ประเภทแรงงาน") or "")
        if "นอกระบบ" in kind:
            prov[p]["informal"] += n
        else:
            prov[p]["formal"] += n
    return {"source": "NSO ภาวะการทำงานของประชากร (data.go.th) — workers by province; measured",
            "year_be": latest, "provinces": dict(sorted(prov.items()))}


def build_crop_prices():
    """National OAE crop-price series -> latest price + YoY per commodity."""
    rows = list(csv.DictReader(open(_biggest("crop_price_oae__35__*.csv"), encoding="utf-8-sig")))
    # group by commodity -> list of (year,month,week,price)
    series = collections.defaultdict(list)
    for r in rows:
        c = (r.get("PROD_TYPE") or "").strip()
        try:
            price = float(str(r.get("PRICE") or "").replace(",", ""))
        except Exception:
            continue
        y, mo, wk = to_int(r.get("YEAR")), to_int(r.get("MONTH_C")), to_int(r.get("WEEK_C"))
        if c:
            series[c].append((y, mo, wk, price))
    out = {}
    for c, pts in series.items():
        pts.sort()
        latest = pts[-1]; ly = latest[0]
        prev = [p for p in pts if p[0] == ly - 1]      # same idea, a year earlier
        last_price = latest[3]
        yoy = round(100 * (last_price - prev[-1][3]) / prev[-1][3], 1) if prev and prev[-1][3] else None
        out[c] = {"price": round(last_price, 2), "year_be": ly, "yoy": yoy}
    return {"source": "OAE ราคาที่เกษตรกรขายได้ (data.go.th) — national crop prices; measured",
            "commodities": dict(sorted(out.items()))}


LAYERS = {"factories_by_district.json": build_factories,
          "vehicles_by_province.json": build_vehicles,
          "employment_by_province.json": build_employment,
          "crop_prices.json": build_crop_prices}


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
        metric = next((k for k in ("fac", "total", "formal") if prov and k in next(iter(prov.values()))), None)
        if metric and prov:
            reg = collections.Counter()
            for p, v in prov.items():
                reg[REGION.get(p, "Other")] += v.get(metric, 0)
            print(f"wrote source-data/{name}: {len(prov)} provinces · {metric} by region: "
                  f"{ {r: f'{c:,}' for r, c in reg.most_common()} }")
        else:
            n = len(obj.get("commodities", obj.get("districts", prov)))
            print(f"wrote source-data/{name}: {n} entries")
    return drift


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="fold dgt_out gov pull into source-data layers")
    ap.add_argument("--check", action="store_true", help="verify committed layers match a fresh build")
    raise SystemExit(run(check=ap.parse_args().check))
