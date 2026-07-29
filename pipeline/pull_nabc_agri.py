#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_nabc_agri.py — MEASURED per-province agriculture from NABC (farming households · land use).

Beyond prices (pull_nabc_prices.py), the NABC API (agriapi.nabc.go.th) also serves CURRENT,
per-province, MEASURED agri structure — cloud-reachable, no key:
  * farmer-family : number of FARMING HOUSEHOLDS per crop per province (oae_family) — 6 crops incl.
                    RUBBER (which the SPAM crop grid lacks). Real counts, not a model.
  * land-use      : agricultural land by type per province (rai): rice_fields, field_crop,
                    perennial_tree, vegetable_flower, other.
Both are the latest OAE vintage (2566/2023). This is the measured backbone that upgrades the agri
workforce estimate (real household counts replace the SPAM-rai national anchor) and adds rubber.

OUTPUT: source-data/nabc_agri.json — { farmer_family: {prov: {crop: households}}, land_use:
{prov: {type: rai}}, national roll-ups } keyed by CANONICAL Thai province (joins branches by prov).

  python3 pull_nabc_agri.py            # pull + write source-data/nabc_agri.json
  python3 pull_nabc_agri.py --stamp 2026-07-05
  python3 pull_nabc_agri.py --selftest # offline aggregate check
"""
import argparse, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.regionmap import canonical

OUT = os.path.join(ROOT, "source-data", "nabc_agri.json")
BASE = "https://agriapi.nabc.go.th/api"
UA = {"User-Agent": "Mozilla/5.0 (compatible; autox-credit-intel/1.0)"}
LU_TYPES = ["rice_fields", "field_crop", "perennial_tree", "vegetable_flower", "other"]


def _get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("NABC GET failed after %d tries: %s\n  %s" % (tries, last, url))


def _paginate(path):
    out, page = [], 1
    while True:
        d = _get("%s/%s%spage=%d" % (BASE, path, ("&" if "?" in path else "?"), page))
        rows = d.get("data") or []
        if not rows:
            break
        out.extend(rows)
        pg = d.get("pagination") or {}
        if page * 100 >= (pg.get("total") or 0):
            break
        page += 1
        time.sleep(0.25)
    return out


def aggregate(ff_rows, lu_rows):
    farmer_family = {}     # canonical prov -> {crop: households}
    for r in ff_rows:
        prov = canonical(r.get("province_name", ""))
        crop = r.get("commod")
        n = r.get("oae_family")
        if prov and crop and isinstance(n, (int, float)):
            farmer_family.setdefault(prov, {})
            farmer_family[prov][crop] = farmer_family[prov].get(crop, 0) + int(n)
    land_use = {}
    for r in lu_rows:
        prov = canonical(r.get("province_name", ""))
        if prov:
            land_use[prov] = {t: int(r.get(t) or 0) for t in LU_TYPES}
    # national roll-ups
    nat_ff = {}
    for prov, crops in farmer_family.items():
        for c, n in crops.items():
            nat_ff[c] = nat_ff.get(c, 0) + n
    return farmer_family, land_use, nat_ff


def build(ff_rows, lu_rows, stamp):
    farmer_family, land_use, nat_ff = aggregate(ff_rows, lu_rows)
    return {
        "meta": {
            "source": "NABC Agricultural Data Service (agriapi.nabc.go.th) — farmer-family + land-use; "
                      "OAE-sourced, cloud-reachable, no key.",
            "label": "MEASURED — per-province farming-household counts + agricultural land use (rai)",
            "generated_by": "pipeline/pull_nabc_agri.py",
            "pulled": stamp,
            "vintage": "2566 (2023)",
            "land_use_types": LU_TYPES,
            "n_provinces_ff": len(farmer_family),
            "n_provinces_lu": len(land_use),
            "national_households_by_crop": {k: nat_ff[k] for k in sorted(nat_ff)},
            "note": "farmer-family = number of farming households per crop per province (incl. rubber, "
                    "absent from SPAM). Keyed by canonical Thai province — joins branches by prov.",
        },
        "farmer_family": {k: farmer_family[k] for k in sorted(farmer_family)},
        "land_use": {k: land_use[k] for k in sorted(land_use)},
    }


SELFTEST_FF = [
    {"province_name": "กระบี่", "commod": "ยางพารา", "oae_family": 41167},
    {"province_name": "กระบี่", "commod": "ข้าว", "oae_family": 14},
]
SELFTEST_LU = [{"province_name": "กระบี่", "rice_fields": 100, "field_crop": 0,
                "perennial_tree": 50, "vegetable_flower": 0, "other": 10}]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default="")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        doc = build(SELFTEST_FF, SELFTEST_LU, "test")
        kb = canonical("กระบี่")
        assert doc["farmer_family"][kb]["ยางพารา"] == 41167, doc["farmer_family"]
        print("selftest OK:", kb, doc["farmer_family"][kb])
        return
    ff = _paginate("farmer-family/data")
    lu = _paginate("land-use/data")
    print("pulled farmer-family=%d rows, land-use=%d rows" % (len(ff), len(lu)), file=sys.stderr)
    doc = build(ff, lu, a.stamp)
    if not doc["farmer_family"]:
        sys.exit("pull_nabc_agri.py: no farmer-family data parsed.")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    m = doc["meta"]
    print("wrote %s" % OUT)
    print("  provinces: farmer-family %d, land-use %d" % (m["n_provinces_ff"], m["n_provinces_lu"]))
    print("  national farming households by crop:")
    for c, n in m["national_households_by_crop"].items():
        print("    %-22s %10s" % (c, "{:,}".format(n)))


if __name__ == "__main__":
    main()
