#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_ev_penetration.py — MEASURED per-province EV penetration from the DLT fuel-type table.

Source: source-data/dlt/raw/dataset_1_1_04/ — cumulative registered vehicles per PROVINCE ×
vehicle type × FUEL TYPE, as of the vintage in the filename (28 Feb 2026 at first pull). This is
the measured province-level EV read — no brand classification needed: ไฟฟ้า = BEV,
เบนซิน/ดีเซล-ไฟฟ้า = hybrid, …เสียบปลั๊ก = PHEV.

Why (objective #1): pairs with ev_exposure.json (ICE-parts workers) — where the EV fleet is
actually arriving vs where the exposed workforce sits. Diesel share per province is also the
measured base of the diesel-pickup collateral watch.

Deterministic over the committed CSV; --check byte-exact; exits 3 (SKIP) when the mirror is absent.

  python3 build_ev_penetration.py
  python3 build_ev_penetration.py --check
"""
import argparse, csv, glob, io, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_GLOB = os.path.join(ROOT, "source-data", "dlt", "raw", "dataset_1_1_04", "*.csv")
OUT = os.path.join(ROOT, "platform", "data", "ev_penetration.json")

BEV = {"ไฟฟ้า"}
PHEV_MARK = "เสียบปลั๊ก"
HYBRID_MARK = "-ไฟฟ้า"          # เบนซิน-ไฟฟ้า / ดีเซล-ไฟฟ้า (minus the PHEV mark)
DIESEL_MARK = "ดีเซล"

THAI_MONTHS = {"มกราคม": "01", "กุมภาพันธ์": "02", "มีนาคม": "03", "เมษายน": "04", "พฤษภาคม": "05",
               "มิถุนายน": "06", "กรกฎาคม": "07", "สิงหาคม": "08", "กันยายน": "09", "ตุลาคม": "10",
               "พฤศจิกายน": "11", "ธันวาคม": "12"}


def _vintage(fn):
    base = os.path.basename(fn)
    m = re.search(r"(\d{1,2})_(%s)_(25\d\d)" % "|".join(THAI_MONTHS), base)
    if not m:
        return base
    return "%d-%s-%02d" % (int(m.group(3)) - 543, THAI_MONTHS[m.group(2)], int(m.group(1)))


def build():
    fn = sorted(glob.glob(SRC_GLOB))[-1]
    rows = list(csv.reader(io.StringIO(open(fn, encoding="utf-8-sig", errors="replace").read())))[1:]
    prov = {}
    for r in rows:
        if len(r) < 5:
            continue
        p, fuel, n = r[2].strip(), r[3].strip(), r[4]
        try:
            n = int(n)
        except ValueError:
            continue
        if not p:
            continue
        e = prov.setdefault(p, {"total": 0, "bev": 0, "phev": 0, "hybrid": 0, "diesel": 0})
        e["total"] += n
        if fuel in BEV:
            e["bev"] += n
        elif PHEV_MARK in fuel:
            e["phev"] += n
        elif HYBRID_MARK in fuel:
            e["hybrid"] += n
        elif DIESEL_MARK in fuel and HYBRID_MARK not in fuel:
            e["diesel"] += n
    out = []
    for p, e in prov.items():
        t = e["total"] or 1
        out.append({"th": p, **e,
                    "bev_pct": round(100.0 * e["bev"] / t, 2),
                    "electrified_pct": round(100.0 * (e["bev"] + e["phev"] + e["hybrid"]) / t, 2),
                    "diesel_pct": round(100.0 * e["diesel"] / t, 1)})
    out.sort(key=lambda r: (-r["bev_pct"], r["th"]))
    nat = {k: sum(r[k] for r in out) for k in ("total", "bev", "phev", "hybrid", "diesel")}
    return {
        "meta": {
            "title": "EV penetration per province — registered fleet by fuel type (DLT, measured)",
            "generated_by": "pipeline/build_ev_penetration.py",
            "label": "MEASURED — DLT cumulative registrations by province × fuel type. BEV = ไฟฟ้า; "
                     "electrified adds hybrid + PHEV. No brand classification involved.",
            "source": "source-data/dlt/raw/dataset_1_1_04 (pull_dlt_all.py mirror)",
            "vintage": _vintage(fn),
            "national": {**nat, "bev_pct": round(100.0 * nat["bev"] / nat["total"], 2)},
            "n_provinces": len(out),
        },
        "provinces": out,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not glob.glob(SRC_GLOB):
        print("build_ev_penetration.py: DLT mirror dataset_1_1_04 absent — run pull_dlt_all.py (SKIP).")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_ev_penetration.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_ev_penetration.py --check: drifted — re-run the builder.")
        print("build_ev_penetration.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    d = json.loads(payload)
    print("wrote %s — vintage %s, national BEV %.2f%%" % (OUT, d["meta"]["vintage"], d["meta"]["national"]["bev_pct"]))
    for r in d["provinces"][:5]:
        print("   %s BEV %.2f%% (electrified %.2f%%)" % (r["th"], r["bev_pct"], r["electrified_pct"]))


if __name__ == "__main__":
    main()
