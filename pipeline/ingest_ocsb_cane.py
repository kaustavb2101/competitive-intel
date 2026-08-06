#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ingest_ocsb_cane.py — MEASURED sugarcane area, crush and price (OCSB + provincial open data).

Sugarcane was the single largest hole in the commodities board. Every other crop on that board had a
measured Thai belt and most had a measured Thai farm-gate move; SUGAR had neither. Its belt came from
SPAM 2010 — a MODELLED, fifteen-year-old raster — and its farm-gate column was blank, so the board
could only show the World Bank world sugar price falling with no way to say who in Thailand carries it.
Sugarcane is not in DOAE's farmer registry either (cane growers register with OCSB, not DOAE), so the
19-crop DOAE expansion did not reach it.

Two measured sources close it, and this script folds both into one layer:

  1. AREA + CRUSH — the Office of the Cane and Sugar Board's own CKAN (`opendata.ocsb.go.th`,
     resources served from `catalog.ocsb.go.th`). `canearea.csv` carries per-province harvested cane
     area (rai), cane delivered (tonnes), the mill-supplied subset, and yield, for TEN production
     years 2556/57 -> 2565/66. The latest year is 47 cane provinces / 11.4m rai. All 47 province
     names join `regionmap.canonical()` cleanly.
  2. PRICE — the announced cane price in บาท/กก. for BE 2563..2568 (2020..2025). Thailand's cane
     price is ADMINISTERED: OCSB announces one ราคาอ้อยขั้นต้น / ขั้นสุดท้าย per season on a ~10-CCS
     basis, so this is a national price that happens to be republished on a provincial portal
     (Amnat Charoen's, via gdcatalog) rather than a province-specific one. It is currently FALLING.

The SPAM-2010 raster it replaces understates national cane area by ~1.7x (1.06m ha modelled vs the
1.82m ha OCSB actually measures), which is why the Sugar belt on the board looked thin.

    python3 ingest_ocsb_cane.py --pull    # refresh source-data/ocsb_canearea.csv from OCSB CKAN
    python3 ingest_ocsb_cane.py           # CSVs -> source-data/ocsb_cane.json
    python3 ingest_ocsb_cane.py --check   # verify the layer reproduces byte-exact

Provenance: MEASURED throughout. Area/crush = OCSB administrative returns (mills report deliveries),
production year 2565/66. Price = the officially announced cane price, NOT a survey mean.
"""
import argparse, csv, io, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from lib.regionmap import canonical

AREA_CSV = os.path.join(ROOT, "source-data", "ocsb_canearea.csv")
PRICE_CSV = os.path.join(ROOT, "source-data", "ocsb_caneprice.csv")
OUT = os.path.join(ROOT, "source-data", "ocsb_cane.json")

CKAN = "https://opendata.ocsb.go.th/api/3/action/package_search?rows=100"
RAI_PER_HA = 6.25
BE_OFFSET = 543


def _num(v):
    """OCSB pads every numeric cell (' 2,882 '). Blank/non-numeric -> 0.0, never a crash."""
    try:
        return float((v or "").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _read(path):
    """Both files ship UTF-8 with a BOM; fall back to the Thai cp874 legacy encoding."""
    raw = io.open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "cp874"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise SystemExit("%s: undecodable" % path)


def pull():
    """Re-resolve canearea.csv through the OCSB CKAN API (its resource URLs rotate)."""
    with urllib.request.urlopen(CKAN, timeout=90) as r:
        cat = json.load(r)
    url = None
    for pkg in cat["result"]["results"]:
        for res in pkg.get("resources", []):
            if (res.get("url") or "").rstrip("/").lower().endswith("canearea.csv"):
                url = res["url"]
                break
        if url:
            break
    if not url:
        sys.exit("OCSB CKAN: no resource ending in canearea.csv (the catalog moved)")
    with urllib.request.urlopen(url, timeout=90) as r:
        data = r.read()
    with open(AREA_CSV, "wb") as f:
        f.write(data)
    print("pulled %s -> %s (%s B)" % (url, AREA_CSV, format(len(data), ",")))
    print("NOTE: ocsb_caneprice.csv is not on the OCSB CKAN — it comes from the gdcatalog harvest "
          "and is committed as-is; --pull leaves it untouched.")


def areas():
    rows = list(csv.DictReader(io.StringIO(_read(AREA_CSV))))
    years = sorted({(r.get("ProductionYear") or "").strip() for r in rows} - {""})
    latest = years[-1]

    series, provinces, regions, unmatched = [], {}, {}, []
    for y in years:
        cur = [r for r in rows if (r.get("ProductionYear") or "").strip() == y]
        series.append({
            "year": y,
            "year_ce": int(y.split("/")[0]) - BE_OFFSET,
            "n_provinces": len(cur),
            "area_rai": int(round(sum(_num(r.get("CaneArea")) for r in cur))),
            "cane_tonnes": int(round(sum(_num(r.get("Cane")) for r in cur))),
        })

    for r in (r for r in rows if (r.get("ProductionYear") or "").strip() == latest):
        raw_name = (r.get("Province_Name") or "").strip()
        prov = canonical(raw_name)
        if not prov:
            unmatched.append(raw_name)
            continue
        rai = _num(r.get("CaneArea"))
        rec = provinces.setdefault(prov, {"area_rai": 0.0, "cane_tonnes": 0.0, "mill_area_rai": 0.0})
        rec["area_rai"] += rai
        rec["cane_tonnes"] += _num(r.get("Cane"))
        rec["mill_area_rai"] += _num(r.get("CaneAreafactory"))
        regions[prov] = (r.get("Region_Name") or "").strip()

    out = {}
    for prov, rec in sorted(provinces.items()):
        rai = rec["area_rai"]
        out[prov] = {
            "area_rai": int(round(rai)),
            "area_ha": round(rai / RAI_PER_HA, 1),
            "cane_tonnes": int(round(rec["cane_tonnes"])),
            # OCSB's own Yield column is per-row; recompute so a province that appears twice rolls up
            # consistently instead of inheriting one of its rows' figures.
            "yield_t_per_rai": round(rec["cane_tonnes"] / rai, 2) if rai else None,
            "ocsb_region": regions.get(prov, ""),
        }
    return latest, series, out, sorted(set(unmatched))


def prices():
    rows = list(csv.DictReader(io.StringIO(_read(PRICE_CSV))))
    series, unit = [], ""
    for r in rows:
        be = (r.get("ปี") or "").strip()
        if not be.isdigit():
            continue
        unit = unit or (r.get("หน่วย") or "").strip()
        series.append({"year_be": int(be), "year_ce": int(be) - BE_OFFSET,
                       "price": round(_num(r.get("ข้อมูล")), 3)})
    series.sort(key=lambda s: s["year_be"])
    if len(series) < 2:
        return None
    cur, prev = series[-1], series[-2]
    yoy = round((cur["price"] / prev["price"] - 1) * 100, 1) if prev["price"] else None
    return {
        "unit": unit,
        "series": series,
        "latest_year_ce": cur["year_ce"],
        "latest_price": cur["price"],
        "prev_price": prev["price"],
        "yoy": yoy,
        "basis": "administered — OCSB announces one national cane price per season (~10 CCS); this "
                 "is not a province-specific or survey price",
        "source": "ราคาอ้อย, Amnat Charoen provincial open data (gdcatalog.go.th), republishing the "
                  "announced OCSB cane price",
    }


def build():
    latest, series, provs, unmatched = areas()
    price = prices()
    nat_rai = sum(p["area_rai"] for p in provs.values())
    nat_t = sum(p["cane_tonnes"] for p in provs.values())
    return {
        "meta": {
            "title": "MEASURED sugarcane area, crush and administered price (OCSB)",
            "generated_by": "pipeline/ingest_ocsb_cane.py",
            "sources": [
                "OCSB CKAN opendata.ocsb.go.th -> catalog.ocsb.go.th/canearea.csv (area, crush, yield)",
                "ราคาอ้อย via gdcatalog.go.th provincial open data (announced cane price)",
            ],
            "provenance": "MEASURED. Area and crush are OCSB administrative returns from the mills, "
                          "not a survey or a raster; the price is the officially ANNOUNCED cane "
                          "price, not a farm-gate survey mean. Sugarcane is absent from the DOAE "
                          "farmer registry (cane growers register with OCSB), so this is the only "
                          "measured cane belt available and it replaces the SPAM-2010 modelled one.",
            "production_year": latest,
            "production_year_ce": int(latest.split("/")[0]) - BE_OFFSET,
            "n_provinces": len(provs),
            "unmatched_province_names": unmatched,
            "spam_note": "SPAM 2010 modelled 1,056,457 ha of Thai cane; OCSB measures %s ha in %s — "
                         "the modelled raster understates the belt by ~%.1fx."
                         % (format(int(round(nat_rai / RAI_PER_HA)), ","), latest,
                            (nat_rai / RAI_PER_HA) / 1056457.0),
        },
        "national": {
            "area_rai": nat_rai,
            "area_ha": round(nat_rai / RAI_PER_HA, 1),
            "cane_tonnes": nat_t,
            "yield_t_per_rai": round(nat_t / nat_rai, 2) if nat_rai else None,
        },
        "area_series": series,
        "price": price,
        "provinces": provs,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pull", action="store_true", help="refresh ocsb_canearea.csv from the OCSB CKAN")
    ap.add_argument("--check", action="store_true", help="verify the layer reproduces byte-exact")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if args.pull:
        pull()
        if not args.check:
            return
    for p in (AREA_CSV, PRICE_CSV):
        if not os.path.exists(p):
            if args.check:
                print("ingest_ocsb_cane.py --check: SKIP (%s absent)" % os.path.basename(p))
                sys.exit(3)
            sys.exit("%s missing — run: python3 ingest_ocsb_cane.py --pull" % p)

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != payload:
            sys.exit("ingest_ocsb_cane.py --check: ocsb_cane.json drifted — "
                     "run python3 pipeline/ingest_ocsb_cane.py")
        print("ingest_ocsb_cane.py --check: OK (byte-exact)")
        return
    # newline="\n": the Windows default translates every \n to \r\n, which inflates the byte sizes
    # build_provenance.py censuses and diverges the local tree from the LF blob CI actually reads.
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    o = json.loads(payload)
    print("wrote %s" % OUT)
    print("  %s: %s provinces, %s rai (%s ha), %s t cane, yield %s t/rai"
          % (o["meta"]["production_year"], o["meta"]["n_provinces"],
             format(o["national"]["area_rai"], ","), format(int(o["national"]["area_ha"]), ","),
             format(o["national"]["cane_tonnes"], ","), o["national"]["yield_t_per_rai"]))
    p = o["price"]
    if p:
        print("  price %s %s (%s) vs %s prior -> %+.1f%% YoY"
              % (p["latest_price"], p["unit"], p["latest_year_ce"], p["prev_price"], p["yoy"]))
    top = sorted(o["provinces"].items(), key=lambda kv: -kv[1]["area_rai"])[:5]
    print("  top belts: " + ", ".join("%s %s rai" % (k, format(v["area_rai"], ",")) for k, v in top))


if __name__ == "__main__":
    main()
