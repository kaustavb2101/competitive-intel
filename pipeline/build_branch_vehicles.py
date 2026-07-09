#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_branch_vehicles.py — per-branch VEHICLE COLLATERAL profile (AutoX's title-loan asset base).

WHY
---
AutoX lends against vehicles, so "what collateral sits in each branch's catchment" is core.
DLT publishes vehicle STOCK per province (car / pickup / motorcycle / EV — vehicles_by_province.json,
MEASURED). This layer projects that onto each branch's 10km catchment by its share of the province's
perimeter population, giving a per-branch collateral mix + a title-loan-able collateral score —
pickup-heavy rural catchments (prime title collateral) vs motorcycle-heavy or car-heavy urban ones.

WHAT EACH BRANCH GETS (10km perimeter)
--------------------------------------
  * est_fleet   — estimated vehicles in the catchment by type {car, pickup, moto, ev}, = province
                  stock × (branch perimeter population / province perimeter population).
  * mix         — the province collateral mix (pickup/car/moto/ev %), MEASURED (DLT).
  * dom         — dominant collateral type.
  * pickup_share — % of the fleet that is pickups (prime title-loan collateral, agri/rural signal).
  * collateral_score — 0-100, title-loan-able asset density in the catchment (pickup + car weighted
                  above motorcycles), normalised across branches. An acquisition/collateral signal.

HONEST SCOPE — this uses the vehicle-STOCK-by-province DLT feed. It does NOT yet carry: trucks,
agricultural vehicles (harvesters/tractors), BRANDS, or registration TRENDS (time series) — those
live in richer DLT datasets on data.go.th that are geo-blocked from the cloud sandbox and must be
pulled from a Thai IP (see pull_dlt_vehicles.py). When that lands, this builder extends to carry it.

PROVENANCE: mix MEASURED (DLT province stock); catchment allocation ESTIMATED (population-weighted).

DETERMINISTIC + NETWORK-FREE. Inputs committed (branches.json, vehicles_by_province.json,
branch_population.json). --check gated. INDEX-ALIGNED + fingerprinted.

  python3 build_branch_vehicles.py          # build/refresh platform/data/branch_vehicles.json
  python3 build_branch_vehicles.py --check  # byte-exact reproduce gate
"""
import argparse, json, os, sys

from fingerprint import branches_fingerprint
from regionmap import canonical

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
VEHICLES = os.path.join(ROOT, "source-data", "vehicles_by_province.json")
POP = os.path.join(ROOT, "platform", "data", "branch_population.json")
OUT = os.path.join(ROOT, "platform", "data", "branch_vehicles.json")

TYPES = ["car", "pickup", "moto", "ev"]
LABELS = {"car": "Passenger car", "pickup": "Pickup truck", "moto": "Motorcycle", "ev": "EV"}
# title-loan-able collateral weight per type: pickups are the prime AutoX asset, cars next, motos
# low value, EV folded into car-equivalent. Used only for the collateral_score (stated, not fitted).
COLLAT_W = {"pickup": 1.0, "car": 0.7, "moto": 0.15, "ev": 0.7}


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build():
    branches = _load(BRANCHES)
    branches = branches if isinstance(branches, list) else branches.get("items", branches)
    veh = _load(VEHICLES).get("provinces", {})
    # canonicalise the province vehicle table so it joins to branch province names
    veh_canon = {}
    for prov, d in veh.items():
        veh_canon[canonical(prov)] = d
    popdoc = _load(POP)
    pops = popdoc.get("values") if isinstance(popdoc, dict) else None
    if not pops or len(pops) != len(branches):
        pops = [1] * len(branches)   # fall back to equal weight if the pop layer is absent/misaligned

    prov_of = [canonical(b.get("v", "") or b.get("prov", "")) for b in branches]
    # province perimeter-population sum, for the population-weighted allocation
    prov_pop = {}
    for i, pr in enumerate(prov_of):
        prov_pop[pr] = prov_pop.get(pr, 0) + (pops[i] or 0)

    # first pass: raw title-loan-able collateral density (for the 0-100 normalisation)
    raw = []
    fleets = []
    for i, b in enumerate(branches):
        pr = prov_of[i]
        v = veh_canon.get(pr)
        share = (pops[i] or 0) / prov_pop[pr] if prov_pop.get(pr) else 0.0
        fleet = {t: int(round((v.get(t, 0) if v else 0) * share)) for t in TYPES}
        fleets.append(fleet)
        raw.append(sum(fleet[t] * COLLAT_W[t] for t in TYPES))
    pos = sorted(x for x in raw if x > 0)
    p95 = pos[int(0.95 * (len(pos) - 1))] if pos else 1.0

    out_branches = []
    for i, b in enumerate(branches):
        pr = prov_of[i]
        v = veh_canon.get(pr)
        fleet = fleets[i]
        tot = sum(fleet[t] for t in TYPES)
        # mix = province stock mix (measured), independent of the allocation
        if v:
            vtot = sum(v.get(t, 0) for t in TYPES) or 1
            mix = {t: round(100.0 * v.get(t, 0) / vtot, 1) for t in TYPES}
        else:
            mix = {t: 0.0 for t in TYPES}
        dom = max(("car", "pickup", "moto"), key=lambda t: fleet.get(t, 0)) if tot else None
        collateral_score = round(min(100.0, 100.0 * raw[i] / p95), 1) if p95 else 0.0
        out_branches.append({
            "fleet": fleet,
            "mix": mix,
            "dom": dom,
            "pickup_share": mix["pickup"],
            "collateral_score": collateral_score,
            "n_est": tot,
        })

    stock_note = _load(VEHICLES).get("source", "DLT vehicle stock by province")
    return {
        "meta": {
            "title": "Per-branch vehicle collateral profile — AutoX title-loan asset base",
            "generated_by": "pipeline/build_branch_vehicles.py",
            "types": TYPES,
            "labels": LABELS,
            "collateral_weights": COLLAT_W,
            "source_stock": stock_note,
            "provenance": {
                "mix": "MEASURED — DLT vehicle stock by province (car/pickup/moto/ev).",
                "est_fleet": "ESTIMATED — province stock allocated to each 10km catchment by its "
                             "share of the province's perimeter population.",
                "collateral_score": "ESTIMATED — title-loan-able density (pickup>car>moto weighted), "
                                    "normalised 0-100 across branches.",
            },
            "missing": "trucks, agricultural vehicles (harvester/tractor), BRANDS and registration "
                       "TRENDS need the richer DLT data.go.th pull (pull_dlt_vehicles.py, Thai IP).",
            "branches_fingerprint": branches_fingerprint(branches),
            "n_branches": len(branches),
            "label": "collateral mix MEASURED (DLT province); catchment allocation ESTIMATED.",
        },
        "branches": out_branches,
    }


def serialize(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_branch_vehicles.py --check: branch_vehicles.json missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_branch_vehicles.py --check: branch_vehicles.json drifted — re-run "
                     "python3 pipeline/build_branch_vehicles.py.")
        print("build_branch_vehicles.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    from collections import Counter
    dom = Counter(b["dom"] for b in obj["branches"] if b["dom"])
    kb = os.path.getsize(OUT) / 1024.0
    print(f"wrote {OUT}  ({kb:.1f} KB)")
    print("  dominant collateral type across branches:", dict(dom))
    hi = sum(1 for b in obj["branches"] if b["collateral_score"] >= 60)
    print(f"  {hi} branches with high collateral density (score ≥ 60)")


if __name__ == "__main__":
    main()
