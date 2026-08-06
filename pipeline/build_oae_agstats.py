#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_oae_agstats.py — per-province MEASURED crop AREA · YIELD · PRODUCTION (OAE Yearbook).

Distils the committed OAE (Office of Agricultural Economics) "Agricultural Statistics of Thailand"
yearbook staging file into a clean, canonical-77-province-keyed layer of per-province crop
productivity — planting/standing AREA, YIELD (kg/rai) and PRODUCTION (tonnes) — for the six major
field crops, plus the national farm-gate price timeseries.

WHY (objective #1, portfolio risk): the existing measured crop layers cover per-province AREA
(source-data/doae_planted_area.json, DOAE 2568 → branch_cropland.json) and crop PRICE (NABC/OAE
farm-gate cascade → crop_stress.json), but nothing surfaces per-province YIELD. Yield is the missing
income lever: two provinces with equal planted area but a 30% yield gap have very different farm-household
cash flow, and cash flow is what services an agri / vehicle-title loan. A below-national-benchmark yield
(or a multi-year yield decline) is a direct crop-household repayment-capacity signal for the agri book.
This layer makes that measured signal first-class and gate-protected; it does not score or model.

INPUT  source-data/staging/oae_agstats.json — COMMITTED (git-tracked, not a re-pullable cache). Parsed
       from the OAE 2567/2024 yearbook (catalog.oae.go.th + per-crop CKAN CSVs); carries per-province
       area/yield/production tables (rice main+second season, maize, cassava, sugarcane, oil palm,
       rubber) and a 10-year national farm-gate price series. Because the input is committed, this
       builder's --check ALWAYS runs in the determinism gate (no SKIP-on-absent branch) — a stronger
       guard than the re-pullable builders.

OUTPUT platform/data/oae_agstats.json — { meta, crops, by_province{prov:{crop:{...}}}, national,
       national_prices }. Every number is MEASURED (a straight read of the OAE yearbook); the only
       derived figures are yield_trend_pct (latest vs earliest measured year for that crop/province)
       and price yoy_pct (latest vs prior measured year), both transparent ratios of measured values.

NORMALISATION (honest, documented):
  - Region-total (เหนือ/ใต้/…) and national-total (รวมทั้งประเทศ) rows are excluded from by_province;
    the national-total rows feed the `national` benchmark block instead.
  - Five province names arrive with a doubled Thai sara-am vowel from the PDF parse (ำา instead of ำ:
    กำาแพงเพชร → กำแพงเพชร, ลำาปาง, ลำาพูน, หนองบัวลำาภู, อำานาจเจริญ). That exact two-char artifact is
    repaired before canonicalisation so those five provinces are not silently dropped. No other char edit.
  - The residual "อื่น ๆ" (others) catch-all rows carry no province and are counted as unmapped, never
    guessed into a province.
  - Thai Buddhist-Era years in the rice tables (2567/2568) are converted to CE (−543).

DETERMINISTIC + NETWORK-FREE. Carries --check (byte-exact reproduce). Provinces emitted in sorted
order; crops in a fixed order; only measured integers plus rounded ratios — no wall-clock, no RNG.

  python3 build_oae_agstats.py
  python3 build_oae_agstats.py --check
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.regionmap import canonical, REGION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IN = os.path.join(ROOT, "source-data", "staging", "oae_agstats.json")
OUT = os.path.join(ROOT, "platform", "data", "oae_agstats.json")

# out_key -> (staging table, area field to expose as area_rai, yield field, area basis label)
CROPS = [
    ("rice",        "rice_main_season_province_2567",         "planted_area_rai",   "yield_kg_per_rai_planted", "planted"),
    ("rice_second", "rice_second_season_province_2568",       "planted_area_rai",   "yield_kg_per_rai_planted", "planted"),
    ("maize",       "maize_province_area_yield_2022_2024",    "planted_area_rai",   "yield_kg_per_rai",         "planted"),
    ("cassava",     "cassava_province_area_yield_2023_2025",  "planted_area_rai",   "yield_kg_per_rai",         "planted"),
    ("sugarcane",   "sugarcane_province_area_yield_2023_2025", "harvested_area_rai", "yield_kg_per_rai",        "harvested"),
    ("oilpalm",     "oilpalm_province_area_yield_2022_2024",  "standing_area_rai",  "yield_kg_per_rai",         "standing"),
    ("rubber",      "rubber_province_area_yield_2022_2024",   "standing_area_rai",  "yield_kg_per_rai",         "standing"),
]
CROP_ORDER = [c[0] for c in CROPS]

# price series key in staging -> out crop key
PRICE_KEY = {"maize": "maize", "cassava": "cassava", "sugarcane": "sugarcane",
             "oilpalm": "oilpalm", "rubber": "rubber", "rice_main_season": "rice"}

AGG_TH = {"รวมทั้งประเทศ"}          # national total row marker


def _load():
    with open(IN, encoding="utf-8") as f:
        return json.load(f)


def _norm_prov(raw):
    """Repair the doubled sara-am PDF artifact then canonicalise. Returns a canonical province or None."""
    fixed = (raw or "").strip().replace("ำา", "ำ")
    c = canonical(fixed)
    return c if c in REGION else None


def _year_ce(row):
    if "year_ce" in row:
        return int(row["year_ce"])
    if "year_th" in row:                 # Buddhist Era -> CE
        return int(row["year_th"]) - 543
    return None


def _num(v):
    if v in (None, ""):
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def build():
    d = _load()
    tables = d["tables"]

    # by_province[prov][crop] = latest-year record; also stash per-year yields for the trend.
    by_prov = {}
    national = {}                        # crop -> latest-year national-total record
    per_crop_unmapped = {}

    for out_key, tname, area_f, yld_f, basis in CROPS:
        rows = tables.get(tname, [])
        # gather rows keyed by province -> {year: record}, plus national totals
        prov_years = {}
        nat_years = {}
        unmapped = 0
        for r in rows:
            rt = r.get("row_type")
            pth = (r.get("province_th") or "").strip()
            yr = _year_ce(r)
            if yr is None:
                continue
            rec = {"year": yr,
                   "yield_kg_rai": _num(r.get(yld_f)),
                   "area_rai": _num(r.get(area_f)),
                   "production_ton": _num(r.get("production_ton"))}
            if rt == "national_total" or pth in AGG_TH:
                nat_years[yr] = rec
                continue
            if rt == "region_total":
                continue
            prov = _norm_prov(pth)
            if prov is None:
                unmapped += 1
                continue
            prov_years.setdefault(prov, {})[yr] = rec
        per_crop_unmapped[out_key] = unmapped

        # national benchmark: latest year
        if nat_years:
            ny = max(nat_years)
            national[out_key] = nat_years[ny]

        # per province: latest-year headline + yield trend across measured years
        for prov, years in prov_years.items():
            latest = max(years)
            rec = dict(years[latest])
            yl = sorted(y for y, v in years.items() if v.get("yield_kg_rai"))
            if len(yl) >= 2:
                y0, y1 = yl[0], yl[-1]
                v0 = years[y0]["yield_kg_rai"]
                v1 = years[y1]["yield_kg_rai"]
                if v0:
                    rec["yield_trend_pct"] = round((v1 - v0) / v0 * 100, 1)
                    rec["yield_trend_years"] = [y0, y1]
            by_prov.setdefault(prov, {})[out_key] = rec

    # emit provinces sorted; crops in fixed order
    by_province = {}
    for prov in sorted(by_prov):
        crops = by_prov[prov]
        by_province[prov] = {k: crops[k] for k in CROP_ORDER if k in crops}

    national_out = {k: national[k] for k in CROP_ORDER if k in national}

    # national farm-gate price series -> latest + YoY
    ts = tables.get("farmgate_price_national_timeseries", {})
    national_prices = {}
    for sk, out_key in PRICE_KEY.items():
        series = ts.get(sk, [])
        pf = next((k for k in (series[-1].keys() if series else []) if "price" in k), None)
        if not series or not pf:
            continue
        unit = pf.replace("farmgate_price_", "")     # baht_per_kg | baht_per_ton
        pts = [{"year": int(x["year_ce"]), "price": x[pf]} for x in series if x.get(pf) is not None]
        pts.sort(key=lambda p: p["year"])
        rec = {"unit": unit, "series": pts}
        if pts:
            rec["latest_year"] = pts[-1]["year"]
            rec["latest"] = pts[-1]["price"]
            if len(pts) >= 2 and pts[-2]["price"]:
                rec["yoy_pct"] = round((pts[-1]["price"] - pts[-2]["price"]) / pts[-2]["price"] * 100, 1)
        national_prices[out_key] = rec

    src_meta = d.get("meta", {})
    n_prov = len(by_province)
    meta = {
        "generated_by": "pipeline/build_oae_agstats.py",
        "label": ("MEASURED per-province crop AREA · YIELD (kg/rai) · PRODUCTION (tonnes) for the six "
                  "major field crops, from the OAE Agricultural Statistics of Thailand yearbook, keyed "
                  "to the canonical 77 provinces. Yield is the per-province farm-household income lever "
                  "that the existing area-only / price-only crop layers do not carry."),
        "source": ("MEASURED — Office of Agricultural Economics (สศก.), Agricultural Statistics of "
                   "Thailand %s/%s yearbook + per-crop OAE CKAN CSVs (catalog.oae.go.th). Straight read "
                   "of the published provincial tables; not modelled, not derived."
                   % (src_meta.get("vintage_be", "2567"), src_meta.get("vintage_ce", 2024))),
        "provenance": "measured (national statistical yearbook, read verbatim per province)",
        "vintage_be": src_meta.get("vintage_be", "2567"),
        "vintage_ce": src_meta.get("vintage_ce", 2024),
        "retrieved": src_meta.get("retrieved"),
        "crop_years": {c[0]: None for c in CROPS},   # filled below from national/by_province
        "crop_area_basis": {out_key: basis for out_key, _t, _a, _y, basis in CROPS},
        "n_provinces": n_prov,
        "n_unmapped_rows_per_crop": per_crop_unmapped,
        "objective": ("Portfolio risk (objective #1): per-province yield vs the national benchmark, and "
                      "the multi-year yield direction, flag crop-household repayment-capacity stress the "
                      "area-only and price-only layers cannot see."),
        "gaps": [
            "YIELD and AREA basis differ by crop (documented in crop_area_basis): rice/maize/cassava = "
            "PLANTED area, sugarcane = HARVESTED, oil palm/rubber = STANDING. Compare a province only to "
            "the national benchmark of the SAME crop, never across crops.",
            "Second-season (นาปรัง) rice is a separate crop key `rice_second` and covers fewer provinces "
            "(irrigated command areas only) — it is not added into `rice` (main season, นาปี).",
            "national_prices is a NATIONAL farm-gate timeseries, not per-province — it gives the price "
            "direction, not a province's own realised price. crop_stress.json holds the price-stress read.",
            "Latest measured year varies by crop (rice 2024, maize/oilpalm/rubber 2024, cassava/sugarcane "
            "2025); each record carries its own `year`. yield_trend_pct spans that crop's measured years.",
            "Five provinces arrived with a doubled sara-am vowel (ำา) from the PDF parse and were repaired "
            "before mapping; 'อื่น ๆ' (others) rows carry no province and are excluded, never guessed.",
        ],
    }
    # record the headline year per crop (from national, else first province seen)
    for out_key in CROP_ORDER:
        yr = None
        if out_key in national_out:
            yr = national_out[out_key].get("year")
        else:
            for prov in by_province.values():
                if out_key in prov:
                    yr = prov[out_key].get("year"); break
        meta["crop_years"][out_key] = yr

    return {"meta": meta, "crops": CROP_ORDER, "by_province": by_province,
            "national": national_out, "national_prices": national_prices}


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8")
        except Exception: pass

    if not os.path.exists(IN):
        # committed input; absence is a real error, but keep the gate resilient like its siblings.
        if args.check:
            print("build_oae_agstats.py --check: SKIP (source-data/staging/oae_agstats.json absent)")
            sys.exit(3)
        sys.exit("oae_agstats.json staging file missing")

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_oae_agstats.py --check: SKIP (oae_agstats.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_oae_agstats.py --check: oae_agstats.json drifted — run "
                     "python3 pipeline/build_oae_agstats.py")
        print("build_oae_agstats.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    print("wrote %s (%d provinces, crops: %s, vintage %s/%s)"
          % (OUT, m["n_provinces"], ", ".join(obj["crops"]), m["vintage_be"], m["vintage_ce"]))
    for c in obj["crops"]:
        nat = obj["national"].get(c, {})
        pr = obj["national_prices"].get(c, {})
        print("  %-11s nat yield=%s kg/rai (%s)  price=%s %s yoy=%s%%"
              % (c, nat.get("yield_kg_rai"), nat.get("year"),
                 pr.get("latest"), pr.get("unit", ""), pr.get("yoy_pct")))


if __name__ == "__main__":
    main()
