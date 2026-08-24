#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_oae_yield.py — OAE crop YIELD per rai (kg/rai) for the 5 field crops (objective #1).

Pulls the newest OAE yield-per-rai (ผลผลิตต่อไร่ / ผลผลิตต่อเนื้อที่เก็บเกี่ยว) for rice, maize,
cassava, rubber and oil palm from the OAE CKAN catalog (catalog.oae.go.th) and lands a DISTILLED
source-data/oae_yield.json (committed). This is the yield leg of the crop-farmer-income build
(build_crop_farmer_income.py): gross farmer income = area × YIELD × farm-gate price.

WHAT IS MEASURED, AND AT WHAT LEVEL (be honest — it differs by crop):
  - RICE (dataoae1104): a PER-PROVINCE CSV exists (ข้าวนาปี, main wet-season crop) → we land the
    real per-province yield for all 77 provinces, plus a production-weighted national figure.
  - MAIZE / CASSAVA / RUBBER / OIL PALM (dataoae1204/1304/1404/1504): only a NATIONAL (ระดับประเทศ)
    CSV is machine-readable; the per-province breakdown is PDF-only (a confirmed dead end). So for
    these four crops we land ONLY the national yield — the downstream build applies it to every
    province and TAGS that leg as national-applied-to-province. Nothing is invented.
  Sugarcane has NO OAE yield dataset at all — EXCLUDED (noted in build meta.gaps).

SCHEMA DRIFT handled (incl. OAE's 2026 catalog migration): column roles are resolved from the header
case-insensitively via COL_ALIASES, never by fixed index — value = amount|values|value|Value|data;
attribute = attribute|Attribute|item; province = province_name|province; year = year_th|year;
subcommod = subcommod|subcom. rubber & oil-palm national production moved from CSV to XLSX (parsed via
openpyxl); oil palm reports yield as ผลผลิตต่อเนื้อที่ให้ผล (per fruit-bearing area). maize carries
รุ่น 1 / รุ่น 2 / รวมทุกฤดูปลูก sub-seasons — we target the รวมทุกฤดูปลูก (combined-season) national file.

FLOW (network — run from a host that can reach catalog.oae.go.th; CI runners can):
  1. package_show?id=<stable dataset slug>  (never a rotating resource id).
  2. Pick the newest matching per-province (rice) or national (others) CSV.
  3. Parse the yield-per-rai rows; canonicalise province names via regionmap.canonical().
  4. Write the distilled JSON with full provenance; vintage read FROM THE DATA (the BE year present).
  Raw CSVs are cached in the gitignored source-data/.oae_yield_raw/ scratch dir for audit only.

DETERMINISM / PROVENANCE:
  - `pulled` comes ONLY from --stamp (required for a real write); no wall clock in data values, so a
    re-run with the same upstream + same --stamp is byte-identical.
  - Fails loudly and writes nothing if rice parses <50 provinces, or any of the 5 crops yields no
    number (never demote the honest layer with a junk file).

Run:
  python3 pull_oae_yield.py --stamp 2026-07-18     # real pull + write
  python3 pull_oae_yield.py                         # default --stamp = today (embedded verbatim)
  python3 pull_oae_yield.py --dry-run              # resolve + list the chosen CSV per crop only
"""
import argparse
import csv
import datetime
import io
import json
import os
import ssl
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPE)
from lib.regionmap import canonical, REGION

OUT = os.path.join(ROOT, "source-data", "oae_yield.json")
RAW_DIR = os.path.join(ROOT, "source-data", ".oae_yield_raw")
BASE = "https://catalog.oae.go.th"
PKG = BASE + "/api/3/action/package_show?id=%s"
CA = "/root/.ccr/ca-bundle.crt"
UA = {"User-Agent": "Mozilla/5.0"}
MIN_RICE_PROV = 50

# Yield-per-rai attribute labels (Thai) across the 5 datasets. เพาะปลูก (per PLANTED area) is
# deliberately NOT here — we want per-HARVESTED/tapped/bearing area (เก็บเกี่ยว / กรีดได้ /
# ให้ผล / ต่อไร่). Oil palm reports ผลผลิตต่อเนื้อที่ให้ผล (per fruit-BEARING area).
YIELD_ATTRS = {"ผลผลิตต่อเนื้อที่เก็บเกี่ยว", "ผลผลิตต่อไร่",
               "ผลผลิตต่อเนื้อที่กรีดได้", "ผลผลิตต่อเนื้อที่ให้ผล"}
# Column ROLES are resolved case-insensitively from the header, never by fixed index. OAE's 2026
# catalog migration renamed columns and moved rubber/oil-palm from CSV to XLSX, so a role now has
# several spellings across the 5 datasets: value = amount|values|value|Value|data; attribute =
# attribute|Attribute|item; province = province_name|province; subcommod = subcommod|subcom.
COL_ALIASES = {
    "value": ("amount", "values", "value", "data"),
    "attr":  ("attribute", "item"),
    "year":  ("year_th", "year"),
    "prov":  ("province_name", "province"),
    "sub":   ("subcommod", "subcom"),
}
PROD_ATTR = "ผลผลิต"            # rice: production (tons), for the weighted national yield
HARV_ATTR = "เนื้อที่เก็บเกี่ยว"  # rice: harvested area (rai), for the weighted national yield
SKIP_PROV = ("ประเทศไทย", "", "รวม", "รวมทั้งประเทศ")
FMT_EXT = {"CSV": "csv", "XLSX": "xlsx"}   # accepted resource formats -> raw-cache extension

# Each crop: dataset slug + mode. name_include/name_exclude filter the resource list.
CROPS = {
    "rice":    {"dataset": "dataoae1104", "mode": "province",
                "name_include": "ข้าวนาปี", "name_exclude": "ระดับประเทศ",
                "commod_th": "ข้าว"},
    "maize":   {"dataset": "dataoae1204", "mode": "national",
                "name_include": "รวมทุกฤดูปลูก ระดับประเทศ", "commod_th": "ข้าวโพดเลี้ยงสัตว์"},
    "cassava": {"dataset": "dataoae1304", "mode": "national",
                "name_include": "ระดับประเทศ", "commod_th": "มันสำปะหลัง"},
    "rubber":  {"dataset": "dataoae1404", "mode": "national",
                "name_include": "ระดับประเทศ", "commod_th": "ยางพารา"},
    "oilpalm": {"dataset": "dataoae1504", "mode": "national",
                "name_include": "ระดับประเทศ", "commod_th": "ปาล์มน้ำมัน"},
}
CROP_ORDER = ["rice", "maize", "cassava", "rubber", "oilpalm"]


def _ctx():
    return ssl.create_default_context(cafile=CA) if os.path.exists(CA) else None


def _get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                  timeout=90, context=_ctx()).read()


def _be_year(name):
    """Highest 4-digit BE year token in a resource name (e.g. '... ปี 2567' -> 2567)."""
    toks = []
    cur = ""
    for ch in name:
        if ch.isdigit():
            cur += ch
        else:
            if len(cur) == 4:
                toks.append(int(cur))
            cur = ""
    if len(cur) == 4:
        toks.append(int(cur))
    be = [t for t in toks if 2500 <= t <= 2600]
    return max(be) if be else 0


def _resolve(cfg):
    """Return (url, name, fmt) of the newest matching CSV/XLSX resource for a crop config."""
    meta = json.loads(_get(PKG % cfg["dataset"]))
    inc, exc = cfg.get("name_include"), cfg.get("name_exclude")
    cands = []
    for r in meta["result"].get("resources", []):
        nm = r.get("name", "")
        fmt = r.get("format", "").upper()
        if (fmt in FMT_EXT
                and (inc is None or inc in nm)
                and (exc is None or exc not in nm)):
            # fmt_rank: CSV (1) sorts ahead of XLSX (0) under reverse=True at equal year+name, so a
            # dataset still offering CSV is preferred over its XLSX twin.
            cands.append((_be_year(nm), nm, 1 if fmt == "CSV" else 0, r["url"], fmt))
    if not cands:
        return None
    cands.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)  # newest year, name, CSV-before-XLSX
    top = cands[0]
    return top[3], top[1], top[4]


def _parse_bytes(raw, fmt):
    """Decode a raw CSV/XLSX resource into stripped-cell rows (skipping blank rows)."""
    if fmt == "XLSX":
        import openpyxl  # only the XLSX crops (rubber, oil palm) need it; CI installs it for the swarm
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c).strip() for c in row]
            if any(cells):
                rows.append(cells)
        wb.close()
        return rows
    text = raw.decode("utf-8-sig", errors="replace")
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text)) if any(r)]


def _rows(url, fmt):
    raw = _get(url)
    return raw, _parse_bytes(raw, fmt)


def _cols(hdr):
    """Resolve column ROLE -> index from the header, case-insensitively, via COL_ALIASES."""
    low = {h.strip().lower(): i for i, h in enumerate(hdr)}
    return {role: next((low[n] for n in names if n in low), None)
            for role, names in COL_ALIASES.items()}


def _num(s):
    try:
        return float(str(s).replace(",", "").strip() or 0)
    except ValueError:
        return None


def _parse_province(rows):
    """Rice per-province: {canonical: yield_kg_rai} + weighted national + BE year."""
    col = _cols(rows[0])
    ip, ia, iv, iy = col["prov"], col["attr"], col["value"], col["year"]
    if None in (ip, ia, iv):
        sys.exit("pull_oae_yield.py: rice CSV header unexpected: %s" % rows[0])
    provinces, prod, harv = {}, {}, {}
    be = 0
    for r in rows[1:]:
        if len(r) <= max(ip, ia, iv):
            continue
        pname = r[ip]
        if pname in SKIP_PROV:
            continue
        c = canonical(pname)
        if not c or c not in REGION:
            continue
        attr = r[ia]
        v = _num(r[iv])
        if v is None:
            continue
        if iy is not None and len(r) > iy:
            yv = _num(r[iy])
            if yv:
                be = max(be, int(yv))
        if attr in YIELD_ATTRS:
            provinces[c] = round(v)
        elif attr == PROD_ATTR:
            prod[c] = v
        elif attr == HARV_ATTR:
            harv[c] = v
    tot_prod = sum(prod.get(c, 0) for c in provinces)   # tons
    tot_harv = sum(harv.get(c, 0) for c in provinces)   # rai
    national = round(tot_prod * 1000.0 / tot_harv) if tot_harv else None
    return provinces, national, be


def _parse_national(rows, commod_th):
    """Non-rice: national yield from the latest BE year; prefer รวม (combined-season) subcommod."""
    col = _cols(rows[0])
    ia, iv, iy, isub = col["attr"], col["value"], col["year"], col["sub"]
    if None in (ia, iv, iy):
        sys.exit("pull_oae_yield.py: national CSV/XLSX header unexpected: %s" % rows[0])
    yields = []   # (be_year, subcommod, value)
    for r in rows[1:]:
        if len(r) <= max(ia, iv, iy):
            continue
        if r[ia] not in YIELD_ATTRS:
            continue
        by = _num(r[iy])
        v = _num(r[iv])
        if by is None or v is None:
            continue
        sub = r[isub] if (isub is not None and len(r) > isub) else commod_th
        yields.append((int(by), sub, v))
    if not yields:
        return None, 0
    latest = max(y[0] for y in yields)
    cand = [(sub, v) for by, sub, v in yields if by == latest]

    def rank(sv):
        sub, _ = sv
        if "รวม" in sub:            # combined-season total (maize รวมรุ่น) — the headline figure
            return (0, sub)
        if sub == commod_th:        # subcommod == commodity (rubber, oil palm)
            return (1, sub)
        return (2, sub)             # single specific subcommod (cassava โรงงาน)

    cand.sort(key=rank)
    return round(cand[0][1]), latest


def _crop_entry(name, cfg, rows):
    """Build one crop's distilled entry from its parsed CSV rows (offline-safe)."""
    if cfg["mode"] == "province":
        provinces, national, be = _parse_province(rows)
        if len(provinces) < MIN_RICE_PROV:
            sys.exit("pull_oae_yield.py: rice parsed %d provinces (<%d) — abort."
                     % (len(provinces), MIN_RICE_PROV))
        scope = "per-province (measured, %d provinces) + production-weighted national" % len(provinces)
    else:
        national, be = _parse_national(rows, cfg["commod_th"])
        provinces = {}
        scope = "national only (per-province is PDF-only at OAE — national applied to provinces downstream)"
    if national is None:
        sys.exit("pull_oae_yield.py: %s yielded no national number — abort." % name)
    ce = be - 543 if be else None
    vintage = "%d (CE %s)" % (be, ce) if be else "unknown"
    return {
        "commod_th": cfg["commod_th"],
        "national": national,
        "provinces": {c: provinces[c] for c in sorted(provinces)},
        "yield_scope": scope,
        "vintage": vintage,
        "dataset": cfg["dataset"],
    }, vintage


def _assemble(crops, vintage_by_crop, resolved, formats, stamp):
    return {
        "meta": {
            "title": "OAE crop yield per rai (kg/rai) — 5 field crops (portfolio risk, objective #1)",
            "generated_by": "pipeline/pull_oae_yield.py",
            "label": "MEASURED — OAE ผลผลิตต่อไร่ / ผลผลิตต่อเนื้อที่เก็บเกี่ยว yield per rai (kg/rai). "
                     "Rice is per-province (77) + a production-weighted national; maize/cassava/rubber/"
                     "oil palm are NATIONAL only (per-province is PDF-only at OAE, a confirmed dead end).",
            "source": BASE,
            "dataset_ids": {n: CROPS[n]["dataset"] for n in CROP_ORDER},
            "resources": resolved,
            "formats": formats,
            "unit": "kg/rai (กก./ไร่)",
            "vintage_by_crop": vintage_by_crop,
            "pulled": stamp,
            "provenance": "MEASURED. Nothing modelled. Sugarcane EXCLUDED (no OAE yield dataset).",
            "consumer": "pipeline/build_crop_farmer_income.py (yield leg of gross farmer income).",
        },
        "crops": crops,
    }


def build_live(stamp, dry_run=False):
    """Network pull: resolve + download each crop's CSV/XLSX, cache the raw, distil."""
    os.makedirs(RAW_DIR, exist_ok=True)
    crops, vintage_by_crop, resolved, formats = {}, {}, {}, {}
    for name in CROP_ORDER:
        cfg = CROPS[name]
        r = _resolve(cfg)
        if not r:
            sys.exit("pull_oae_yield.py: no CSV/XLSX resource for %s (%s) — abort."
                     % (name, cfg["dataset"]))
        url, res_name, fmt = r
        resolved[name] = res_name
        formats[name] = fmt
        if dry_run:
            print("  %-8s [%s] (%s) %s" % (name, cfg["mode"], fmt, res_name))
            continue
        raw, rows = _rows(url, fmt)
        with open(os.path.join(RAW_DIR, "%s.%s" % (name, FMT_EXT[fmt])), "wb") as f:
            f.write(raw)
        crops[name], vintage_by_crop[name] = _crop_entry(name, cfg, rows)
    if dry_run:
        return None
    return _assemble(crops, vintage_by_crop, resolved, formats, stamp)


def build_from_raw(stamp, resolved, formats):
    """Offline re-derive from the cached raw CSV/XLSX files (for --check byte-reproduce)."""
    crops, vintage_by_crop = {}, {}
    for name in CROP_ORDER:
        fmt = formats.get(name, "CSV")
        raw = open(os.path.join(RAW_DIR, "%s.%s" % (name, FMT_EXT[fmt])), "rb").read()
        rows = _parse_bytes(raw, fmt)
        crops[name], vintage_by_crop[name] = _crop_entry(name, CROPS[name], rows)
    return _assemble(crops, vintage_by_crop, resolved, formats, stamp)


def _dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default=datetime.date.today().isoformat(),
                    help="YYYY-MM-DD pull date embedded in meta.pulled (default: today)")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve + list the chosen CSV per crop; no download parse, no write")
    ap.add_argument("--check", action="store_true",
                    help="OFFLINE: re-derive from the cached raw CSVs + committed meta and "
                         "byte-compare against source-data/oae_yield.json; exit 1 on drift, "
                         "exit 3 SKIP if the committed file or the gitignored raw scratch is absent")
    args = ap.parse_args()

    if args.check:
        prev = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else None
        fmts = (prev or {}).get("meta", {}).get("formats", {})
        raws = [os.path.join(RAW_DIR, "%s.%s" % (n, FMT_EXT[fmts.get(n, "CSV")])) for n in CROP_ORDER]
        if prev is None or not all(os.path.exists(p) for p in raws):
            print("pull_oae_yield.py --check: SKIP (committed oae_yield.json or gitignored raw "
                  "scratch source-data/.oae_yield_raw/ absent — network-pulled input, not drift)")
            sys.exit(3)
        data = build_from_raw(prev["meta"]["pulled"], prev["meta"]["resources"], prev["meta"]["formats"])
        if _dumps(data) != open(OUT, encoding="utf-8").read():
            sys.exit("pull_oae_yield.py --check: oae_yield.json drifted from a fresh parse of the "
                     "cached raw CSVs — re-run python3 pipeline/pull_oae_yield.py")
        print("pull_oae_yield.py --check: OK (byte-exact from cached raw)")
        return

    if args.dry_run:
        build_live(args.stamp, dry_run=True)
        return
    data = build_live(args.stamp)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(_dumps(data))
    print("wrote %s" % OUT)
    for n in CROP_ORDER:
        c = data["crops"][n]
        print("  %-8s national=%-6s provinces=%-3d vintage=%s"
              % (n, c["national"], len(c["provinces"]), c["vintage"]))


if __name__ == "__main__":
    main()
