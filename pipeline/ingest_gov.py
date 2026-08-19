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
from lib.regionmap import canonical, REGION, norm_district


def to_int(x):
    try:
        return int(float(str(x or 0).replace(",", "").strip() or 0))
    except Exception:
        return 0


def build_factories():
    """National DIW factory registry -> per-district factory & worker counts."""
    fp = _biggest("factories_diw__factype3__*.csv")   # one authoritative file (no double-count on re-pull)
    districts = collections.defaultdict(lambda: {"fac": 0, "workers": 0})
    provinces = collections.defaultdict(lambda: {"fac": 0, "workers": 0})
    with open(fp, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            p = canonical((r.get("จังหวัด") or "").strip())
            d = norm_district(r.get("อำเภอ"), p)
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
    # Coverage diagnostic: diff the province keys we actually captured against regionmap's canonical
    # 77 so a missing province is NAMED in the output (not silently a downstream null). The known gap
    # is กรุงเทพมหานคร (Bangkok) — NSO does not publish it in this informal/formal table under that
    # key; a Thai-IP repull should check whether the raw names it differently (กทม.). This is what
    # leaves Bangkok's 170 branches with an HONEST NULL informal_pct in build_branch_labor.py.
    present = set(prov.keys())
    missing = sorted(set(REGION.keys()) - present)
    extra = sorted(present - set(REGION.keys()))
    return {"source": "NSO ภาวะการทำงานของประชากร (data.go.th) — workers by province; measured",
            "year_be": latest, "provinces": dict(sorted(prov.items())),
            "coverage": {"n_provinces": len(prov), "n_canonical": len(REGION),
                         "missing_provinces": missing, "extra_provinces": extra,
                         "note": "provinces in regionmap's canonical 77 absent from this NSO pull; "
                                 "branches in a missing province keep an HONEST NULL informal_pct."}}


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


# ---------------------------------------------------------------------------
# NSO 2022 Business & Industrial Census occupation/establishment distiller.
#
# SCAFFOLDING — drop-in ready, INERT until the pull lands. The NSO census is a
# BLOCKED data.go.th pull (see docs/IMPROVEMENT_BACKLOG.md "Blocked"): it cannot
# be fetched from the sandbox's foreign IP. This code transforms the export the
# moment Kaustav drops it into pipeline/dgt_out/ from his Thai network — it never
# fabricates a value and is a clean no-op (clear skip message) when the file is
# absent (the sandbox case), so the existing four layers stay byte-identical.
#
# EXPECTED INPUT (drop one CSV into pipeline/dgt_out/):
#   filename glob : nso_census__bizind__*.csv   (the largest match wins, like the
#                   other layers, so a re-pull never double-counts)
#   encoding      : UTF-8 (BOM tolerated — read with utf-8-sig)
#   one row per (province, district, business-activity category), Thai headers:
#     จังหวัด        province name (Thai, ISO code, or English — folded by canonical())
#     อำเภอ          district/amphoe name (folded by norm_district(); MAY be blank
#                    for province-level-only census tables — such rows still roll
#                    up into the province total, just not into any district)
#     ประเภทกิจกรรม  business-activity / occupation category label, e.g. a TSIC
#                    section name ("การผลิต" manufacturing, "การขายส่งและการขายปลีก"
#                    wholesale/retail trade, "ที่พักแรมและบริการด้านอาหาร" etc.)
#                    Alt header accepted: หมวดธุรกิจ.
#     จำนวนสถานประกอบการ  establishment count for that cell (int; commas tolerated).
#                    Alt headers accepted: จำนวน, สถานประกอบการ.
#     จำนวนคนทำงาน   (OPTIONAL) persons engaged / workers for that cell (int).
#                    Alt headers accepted: คนทำงาน, คนงานรวม.
#
# OUTPUT (matches the factories_by_district / vehicles_by_province fold-in style):
#   source-data/occupations_by_district.json
#     {source, year_be?, n_establishments, categories:[...sorted unique labels...],
#      districts:{ "<prov>|<district>": {"estab":N, "workers":N,
#                  "by_category": {"<cat>": {"estab":N, "workers":N}, ...}}, ... },
#      provinces:{ "<prov>": { ...same shape... }, ... } }
#   Every count traces to a real census cell — nothing is invented or modelled.
# ---------------------------------------------------------------------------
def _first_field(row, names):
    """Return the first present, non-None header value among aliases (or '')."""
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
    return ""


def build_occupations_census():
    """NSO Business & Industrial Census -> per-district / per-province establishment
    (occupation) counts by business-activity category. Returns None (skip) when the
    census CSV has not been dropped into dgt_out/ — never crashes, never fabricates."""
    files = glob.glob(os.path.join(DGT, "nso_census__bizind__*.csv"))
    if not files:
        print("NSO occupation source absent (data.go.th blocked from sandbox) — no "
              "nso_census__bizind__*.csv in dgt_out/; skipping occupations_by_district.json. "
              "Drop the NSO 2022 census export there (Thai-IP pull) to build it.")
        return None
    fp = max(files, key=os.path.getsize)   # largest = most complete (no double-count on re-pull)

    def _cell():
        return {"estab": 0, "workers": 0, "by_category": collections.defaultdict(
            lambda: {"estab": 0, "workers": 0})}
    districts = collections.defaultdict(_cell)
    provinces = collections.defaultdict(_cell)
    categories = set()
    years = []
    with open(fp, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            p = canonical((_first_field(r, ("จังหวัด",)) or "").strip())
            if not p:
                continue
            d = norm_district(_first_field(r, ("อำเภอ",)), p)   # may resolve to '' for province-only rows
            cat = (_first_field(r, ("ประเภทกิจกรรม", "หมวดธุรกิจ")) or "").strip()
            n = to_int(_first_field(r, ("จำนวนสถานประกอบการ", "จำนวน", "สถานประกอบการ")))
            w = to_int(_first_field(r, ("จำนวนคนทำงาน", "คนทำงาน", "คนงานรวม")))
            yr = to_int(_first_field(r, ("ปี", "ปีพ.ศ.")))
            if yr:
                years.append(yr)
            if cat:
                categories.add(cat)
            prov = provinces[p]
            prov["estab"] += n
            prov["workers"] += w
            if cat:
                prov["by_category"][cat]["estab"] += n
                prov["by_category"][cat]["workers"] += w
            if d:
                dist = districts[f"{p}|{d}"]
                dist["estab"] += n
                dist["workers"] += w
                if cat:
                    dist["by_category"][cat]["estab"] += n
                    dist["by_category"][cat]["workers"] += w

    def _freeze(d):   # defaultdict -> plain sorted dict for deterministic JSON
        return {k: {"estab": v["estab"], "workers": v["workers"],
                    "by_category": {c: dict(v["by_category"][c])
                                    for c in sorted(v["by_category"])}}
                for k, v in sorted(d.items())}

    out = {
        "source": "NSO สำมะโนธุรกิจและอุตสาหกรรม (Business & Industrial Census, data.go.th) "
                  "— establishment counts by activity & district; measured, not OSM proxy",
        "n_establishments": sum(v["estab"] for v in provinces.values()),
        "categories": sorted(categories),
        "districts": _freeze(districts),
        "provinces": _freeze(provinces),
    }
    if years:
        out["year_be"] = max(years)
    return out


# factories_by_district.json is NO LONGER written here. It is now produced by
# build_factories_by_district.py from source-data/factory_census_national.json — the DIW department
# CKAN census that refreshes weekly from CI (any IP), superseding this data.go.th path which is
# geoblocked to Kaustav's Thai laptop. build_factories() is kept for reference / a manual laptop
# rebuild, but is intentionally out of LAYERS so a future ingest_gov run can't clobber the
# CI-refreshable, gate-checked census projection with the stale aggregator pull.
LAYERS = {"vehicles_by_province.json": build_vehicles,
          "employment_by_province.json": build_employment,
          "crop_prices.json": build_crop_prices}

# Optional, drop-in-ready layers: built only when their source pull is present in
# dgt_out/. Their builder returns None to signal "absent — skip" so run() leaves
# the file untouched (the existing four mandatory LAYERS stay byte-identical when
# the NSO census has not been dropped in). Add future blocked-pull distillers here.
OPTIONAL_LAYERS = {"occupations_by_district.json": build_occupations_census}


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

    # Optional drop-in layers (built only when their pull is present in dgt_out/).
    # A None return means "input absent" -> skip silently-but-clearly, leaving any
    # committed file untouched. In --check, an absent input means there is nothing
    # to verify, so it cannot drift the gate.
    for name, builder in OPTIONAL_LAYERS.items():
        obj = builder()
        if obj is None:
            continue
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
        print(f"wrote source-data/{name}: {len(obj.get('districts', {}))} districts · "
              f"{len(obj.get('provinces', {}))} provinces · {len(obj.get('categories', []))} categories")
    return drift


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="fold dgt_out gov pull into source-data layers")
    ap.add_argument("--check", action="store_true", help="verify committed layers match a fresh build")
    raise SystemExit(run(check=ap.parse_args().check))
