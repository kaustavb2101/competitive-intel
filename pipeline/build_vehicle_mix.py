#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_vehicle_mix.py — VEHICLE-MIX layer (owner review points 11/12/18): the composition of all
new vehicle registrations, the full mix to 100% for every province, and the truck/bus classes
(Land Transport Act) alongside the car-law ones — with the new-vs-stock GAP that shows which
classes are growing or shrinking as a share of the fleet.

  in : source-data/vehicle_mix_province.json   (ingest_dlt_mix.py — owner-side, gitignored raw
       mirror upstream of it, NOT this file; this file IS committed)
  out: platform/data/vehicle_mix.json

Deterministic + network-free over the committed staging file; `--check` byte-exact. Exits 3
(SKIP, not drift) when the staging file is absent — mirrors build_tape_layers.py's convention.

Method (100% MEASURED, no modelling beyond sums + plain ratios):
  stock mix       — each vehicle class's SHARE of that geography's total registered STOCK
                     (Motor Vehicle Act only — dataset_1_1_04 has no Land-Transport-Act truck/bus
                     stock; those classes carry stock_share=null, never a fabricated 0).
  new-reg mix      — each class's share of trailing-12mo NEW registrations (รถจดใหม่ป้ายแดง),
                     Motor Vehicle Act + Land Transport Act combined — the full mix to 100%.
  gap_pp           — new_share_pct - stock_share_pct, in percentage points; null wherever
                     stock_share is null (no stock denominator to compare against).
  fuel mix         — diesel / petrol / EV / hybrid / gas / other shares of the STOCK (fuel type is
                     only published in the stock file).
  Region and national rollups are SUMMED COUNTS, never a mean of province percentages.

Every share list is asserted to sum to 100.0 (+/-0.1) before writing — a silent mis-add would be a
correctness bug, so this fails loud instead of shipping a mix that only looks like it hits 100.

    python3 build_vehicle_mix.py
    python3 build_vehicle_mix.py --check
"""
import argparse
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPE)
from lib.regionmap import REGION  # noqa: E402

IN = os.path.join(ROOT, "source-data", "vehicle_mix_province.json")
OUT = os.path.join(ROOT, "platform", "data", "vehicle_mix.json")

FUEL_BUCKETS = ["diesel", "petrol", "ev", "hybrid", "gas", "other"]
TOL = 0.1  # percentage-point tolerance for the sums-to-100 assertion


def _class_sort_key(cid):
    if cid.startswith("ry") and cid[2:].isdigit():
        return (0, int(cid[2:]), cid)
    if cid == "other":
        return (2, 0, cid)
    return (1, 0, cid)


def _pct(n, total):
    return round(n / total * 100.0, 2) if total else None


def _assert_sums_100(shares, where):
    total = sum(v for v in shares if v is not None)
    if total == 0 and not any(v is not None for v in shares):
        return  # nothing to sum (empty geography) — nothing to assert
    assert abs(total - 100.0) <= TOL, f"shares do not sum to 100 ({total:.3f}) at {where}"


def _fill(d, keys):
    """Return a plain dict with every key present (0 if absent) — stable key set across geos."""
    return {k: int(d.get(k, 0)) for k in keys}


def _add(dst, src):
    for k, v in src.items():
        dst[k] = dst.get(k, 0) + v


def _geo_block(stock, stock_fuel, new, stock_ids, all_ids):
    stock_total = sum(stock.values())
    new_total = sum(new.values())

    stock_out = {}
    for cid in stock_ids:
        stock_out[cid] = {"count": stock[cid], "share_pct": _pct(stock[cid], stock_total)}
    _assert_sums_100([v["share_pct"] for v in stock_out.values()], "stock")

    new_out = {}
    for cid in all_ids:
        new_out[cid] = {"count": new.get(cid, 0), "share_pct": _pct(new.get(cid, 0), new_total)}
    _assert_sums_100([v["share_pct"] for v in new_out.values()], "new")

    gap_pp = {}
    for cid in all_ids:
        s = stock_out.get(cid, {}).get("share_pct")
        n = new_out[cid]["share_pct"]
        gap_pp[cid] = round(n - s, 2) if (s is not None and n is not None) else None

    fuel_total = sum(stock_fuel.values())
    fuel_out = {b: {"count": stock_fuel[b], "share_pct": _pct(stock_fuel[b], fuel_total)} for b in FUEL_BUCKETS}
    _assert_sums_100([v["share_pct"] for v in fuel_out.values()], "fuel")

    return {
        "stock_total": stock_total,
        "stock": stock_out,
        "new_total": new_total,
        "new": new_out,
        "gap_pp": gap_pp,
        "fuel": fuel_out,
    }


def build():
    if not os.path.exists(IN):
        return None
    with open(IN, encoding="utf-8") as f:
        staging = json.load(f)

    provs_in = staging["provinces"]
    class_labels = staging["meta"]["class_labels"]
    all_ids = sorted(class_labels.keys(), key=_class_sort_key)
    # a class "has stock" iff it actually appears as a key in at least one province's raw
    # stock dict (ingest backfills every MVA class to 0 in every province; Land-Transport-Act
    # classes are never inserted there at all) — derived from the data, not assumed by prefix.
    stock_ids_set = set()
    for p in provs_in.values():
        stock_ids_set.update(p["stock"].keys())
    stock_ids = sorted(stock_ids_set, key=_class_sort_key)

    provinces = {}
    region_stock = defaultdict(lambda: defaultdict(int))
    region_fuel = defaultdict(lambda: defaultdict(int))
    region_new = defaultdict(lambda: defaultdict(int))
    nat_stock, nat_fuel, nat_new = defaultdict(int), defaultdict(int), defaultdict(int)

    for p, rec in sorted(provs_in.items()):
        region = REGION.get(p)
        if region is None:
            continue  # defensive; ingest already dropped anything unresolved
        stock = _fill(rec["stock"], stock_ids)
        stock_fuel = _fill(rec["stock_fuel"], FUEL_BUCKETS)
        new = _fill(rec["new"], all_ids)

        provinces[p] = _geo_block(stock, stock_fuel, new, stock_ids, all_ids)

        _add(region_stock[region], stock)
        _add(region_fuel[region], stock_fuel)
        _add(region_new[region], new)
        _add(nat_stock, stock)
        _add(nat_fuel, stock_fuel)
        _add(nat_new, new)

    regions = {}
    for region in sorted(region_stock.keys()):
        regions[region] = _geo_block(
            dict(region_stock[region]), dict(region_fuel[region]), dict(region_new[region]),
            stock_ids, all_ids)

    national = _geo_block(dict(nat_stock), dict(nat_fuel), dict(nat_new), stock_ids, all_ids)

    # ---- PPV overlay (AutoX house definition: "for autox, our PU (pickup) includes PPV in as
    # well") — a DERIVED OVERLAY, not a partition member. It deliberately double-counts vehicles
    # that are already inside ry1 (PPVs register as รย.1 because they seat <=7, not รย.3), which
    # is exactly why it lives beside `national`, not inside `types`/the class partition, and why
    # it never touches _assert_sums_100. National only — the source series has no province split,
    # so this must NOT be pushed into provinces{} or regions{} (no data supports it there).
    ppv = staging["ppv_new_national"]
    ry3_new = national["new"]["ry3"]
    ry3_new_count = ry3_new["count"]
    ry3_new_share_pct = ry3_new["share_pct"]
    ry3_stock = national["stock"]["ry3"]
    pu_new_count = ry3_new_count + ppv["total"]
    national["pu_incl_ppv"] = {
        "new_count": pu_new_count,
        "new_share_pct": _pct(pu_new_count, national["new_total"]),
        "stock_count": ry3_stock["count"],       # UNCHANGED from ry3 — PPV stock is not measurable
        "stock_share_pct": ry3_stock["share_pct"],
        "stock_caveat": "PPV stock is embedded in the 12.6M-vehicle ry1 class and is not "
                         "separately measurable — DLT publishes no model-level stock file.",
        "definition": "AutoX house definition: pickup (รย.3) plus pickup-based SUVs (PPV). PPVs "
                       "register as รย.1 because they seat 7 or fewer, so they are identified by "
                       "nameplate at model grain, not by registration class.",
        "granularity": "national only — no province or region breakdown is possible",
        "by_nameplate": dict(sorted(ppv["by_nameplate"].items())),
    }

    # A flatter, page-friendly restatement of the same overlay: the AutoX-basis PU count/share next
    # to the plain รย.3 count/share it replaces, plus a one-line note naming the definition. Additive
    # only — pu_incl_ppv above is untouched, and this key is new so nothing existing can regress.
    national["autox_pu"] = {
        "count": pu_new_count,
        "share_pct": _pct(pu_new_count, national["new_total"]),
        "ry3_count": ry3_new_count,
        "ry3_share_pct": ry3_new_share_pct,
        "note": "AutoX house definition: PU = รย.3 (pickup) nameplate + PPV nameplate (Fortuner, "
                "MU-X, Pajero Sport, Everest, Terra, GWM Tank 300/500, Trailblazer, SW4, Land "
                "Cruiser FJ) in any registration class, replacing the plain รย.3 class count/share.",
    }

    types = [{"id": cid, "label": class_labels[cid]["label"], "law": class_labels[cid]["law"],
              "has_stock": cid in stock_ids_set} for cid in all_ids]

    return {
        "meta": {
            "title": "Vehicle mix — stock vs new-registration composition, all classes to 100% (MEASURED)",
            "generated_by": "pipeline/build_vehicle_mix.py",
            "label": "MEASURED — DLT gdcatalog. stock = dataset_1_1_04 (Motor Vehicle Act cumulative "
                     "registered stock, one snapshot). new = dataset_stat_1_008 (Motor Vehicle Act) + "
                     "dataset_stat_1_009 (Land Transport Act truck/bus), new red-plate registrations "
                     "(รถจดใหม่ป้ายแดง) summed over the trailing 12 months common to both releases. "
                     "Land-Transport-Act classes have NO stock figure in this mirror (dataset_1_1_04 does "
                     "not cover them) — their stock_share and gap_pp are null, not a fabricated zero; "
                     "their new-registration share IS measured and included in the new mix.",
            "formula": "share_pct = class count / geography total, *100, rounded to 2dp; every stock "
                      "list and every new-registration list is asserted to sum to 100.0 (+/-0.1). "
                      "gap_pp = new_share_pct - stock_share_pct, null where stock_share_pct is null. "
                      "fuel share_pct is against the STOCK total (fuel type is only published in the "
                      "stock file). Region/national totals are summed COUNTS, never a mean of "
                      "province percentages.",
            "stock_asof": staging["meta"]["stock_asof"],
            "new_window_months": staging["meta"]["new_window_months"],
            "new_window_label": staging["meta"]["new_window_label"],
            "ppv_window_months": ppv["window_months"],  # own trailing-12, see national.pu_incl_ppv
            "excluded_stub_months": staging["meta"].get("excluded_stub_months", []),  # catalog-stub
            # PPV months dropped from the window above (see ingest_dlt_mix.py's ppv_stub_rule) —
            # carried through so the exclusion is auditable on the page, not just in staging.
            "fuel_buckets": FUEL_BUCKETS,
            "n_provinces": len(provinces),
            "n_regions": len(regions),
            "n_classes": len(types),
            "n_classes_with_stock": sum(1 for t in types if t["has_stock"]),
        },
        "types": types,
        "national": national,
        "regions": regions,
        "provinces": provinces,
    }


def run(check=False):
    data = build()
    if data is None:
        print("SKIP: source-data/vehicle_mix_province.json absent "
              "— not data drift, run ingest_dlt_mix.py from the owner side first")
        return 3
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: platform/data/vehicle_mix.json")
            return 1
        print(f"OK: vehicle_mix.json reproduces byte-exact "
              f"({data['meta']['n_provinces']} provinces, {data['meta']['n_classes']} classes)")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote platform/data/vehicle_mix.json "
          f"({data['meta']['n_provinces']} provinces, {data['meta']['n_classes']} classes, "
          f"{data['meta']['n_classes_with_stock']} with a stock figure)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
