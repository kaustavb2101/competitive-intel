#!/usr/bin/env python3
"""
build_collateral_book.py — the collateral book, ranked by BAHT, at four grains, plus the full
vehicle-type mix and the DLT collateral base each branch actually sits in.

WHY THIS EXISTS
---------------
The owner's review hit the collateral section eight separate times (points 8-12, 14, 18, 19), and
every hit is a version of the same two complaints: the tables are top-N lists, and the things that
belong together are scattered across three different sections of the tab.

  point 12  "Give me the full mix to 100% and all provinces."
  point 14  "a very powerful dataset... AutoX focuses heavily on pickup and passenger cars.
             Motorcycles are a secondary focus due to smaller ticket size."
  point 18  truck fleet -- "why isn't it in the collateral section?"
  point 19  used-collateral pulse -- "This too should be in the collateral section no?"

Point 14 is not just a preference, and the tape settles it. Motorcycles are 33.3% of ACCOUNTS and
5.8% of OUTSTANDING; pickup and passenger car together are 54% of accounts and 60.7% of outstanding.
Motorcycles also carry the WORST 90+ rate of any vehicle class. So "secondary focus due to smaller
ticket size" is measured fact, and any table that ranks collateral by account count puts the least
important class on top. This layer ranks by baht everywhere, exactly like the farm book.

Trucks and the used-vehicle flow stop being their own sections here because they are not separate
subjects: TRUCK is simply another row of the same mix (4,834 accounts, THB1.84bn, the second-highest
appraised value per unit in the book), and the transfer/deregistration flow is what the resale market
for that mix is doing.

WHAT IS MEASURED AT WHICH GRAIN -- AND THE ONE HONEST GAP
--------------------------------------------------------
  national + region   OUR BOOK by vehicle type, MEASURED (tape vehicle_type / vehicle_x_georegion)
  province            OUR BOOK totals, MEASURED (tape province tab) joined to the MEASURED DLT
                      collateral base around it -- fleet mix, diesel share, electrified share,
                      truck flow -- for all 77 provinces
  branch              OUR BOOK totals, MEASURED (tape branch_full, 1,974 branches)

  THE GAP: the tape export carries vehicle type crossed with REGION, not with province or branch.
  So the per-province vehicle split of our own book is NOT in this file, and is NOT estimated into
  it either -- a province row shows what we lend (baht, ticket, appraised value, arrears) and what
  the local vehicle population looks like, and stops there. Splitting our book by type per province
  needs a `vehicle_x_province` cut in the next export; that ask is recorded in meta.export_asks
  alongside the outstanding branch_id one, rather than papered over with an allocation.

Deterministic + network-free + --check, per the house rule.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "..", "platform", "data")
STAGING = os.path.join(HERE, "..", "source-data", "staging", "real_tape_aggregates.json")
OUT = os.path.join(P, "collateral_book.json")

sys.path.insert(0, HERE)
from branchkey import master_index, norm_branch   # noqa: E402  ONE join definition — see branchkey.py
from lib.fingerprint import branches_fingerprint  # noqa: E402

# The book's own vehicle-type codes, with the labels a reader outside the credit team would use and
# the focus tier the owner stated. Order is the FOCUS order, not the account order — ranking by
# accounts would lead with motorcycles, which are 33% of accounts and 5.8% of the money.
TYPES = [
    ("PU",       "Pickup",           "core"),
    ("PA",       "Passenger car",    "core"),
    ("TRUCK",    "Truck",            "secondary"),
    ("VAN",      "Van",              "secondary"),
    ("TRACTOR",  "Tractor",          "secondary"),
    ("MC",       "Motorcycle",       "secondary"),
    ("Mortgage", "Property (mortgage)", "other"),
    ("Land",     "Land title",       "other"),
]
TYPE_LAB = {k: (lab, tier) for k, lab, tier in TYPES}
TYPE_ORDER = {k: i for i, (k, _, _) in enumerate(TYPES)}


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _p(name):
    return _load(os.path.join(P, name))


def _cur(v):
    """Current % = everything not in the X-day watch bucket and not 30+ overdue.

    The tape publishes early_pct (pre-30 watch) and dpd30p_pct (30+) but no current_pct, so it is
    reconstructed here and clamped — a cell whose two published shares exceed 100 is a rounding
    artefact, not a negative population.
    """
    e = v.get("early_pct")
    d = v.get("dpd30p_pct")
    if e is None or d is None:
        return None
    return round(max(0.0, 100.0 - float(e) - float(d)), 1)


def _core(v, n_key="n"):
    """The fields every grain shares. Ticket and the LTV proxy are the two DERIVED ones."""
    n = int(v.get(n_key) or 0)
    os_ = float(v.get("os_sum") or 0.0)
    ev = v.get("eval_avg")
    d = {
        "n": n,
        "os": int(round(os_)),
        "ticket": int(round(os_ / n)) if n else None,
        "eval_avg": int(round(ev)) if ev else None,
        "dpd90p_pct": v.get("dpd90p_pct"),
        "late180_pct": v.get("late180_pct"),
        "early_pct": v.get("early_pct"),
        "dpd30p_pct": v.get("dpd30p_pct"),
        "current_pct": _cur(v),
        "npat_margin_avg": v.get("npat_margin_avg"),
    }
    # LTV proxy: outstanding per account against APPRAISED value per account. Both MEASURED, the
    # ratio DERIVED. It is a proxy because outstanding amortises while the appraisal is at
    # origination — read it as "how much of the collateral's assessed value is still lent against",
    # not as a regulatory LTV.
    if d["ticket"] and d["eval_avg"]:
        d["ltv_proxy_pct"] = round(100.0 * d["ticket"] / d["eval_avg"], 1)
    else:
        d["ltv_proxy_pct"] = None
    return d


# Every one of these is a PER-ACCOUNT measure — a percentage OF ACCOUNTS, or a mean per account.
# The tape names the distinction itself: `npl_live_pct` is account-based and `npl_live_os_pct` is the
# outstanding-weighted twin. So rolling these up must weight by ACCOUNTS.
#
# Weighting them by outstanding instead is not a rounding difference, it silently changes the answer:
# it put national 90+ at 13.42% against the account-weighted 14.87%, and — worse — it averaged the
# per-account appraised value at THB395,607 by letting the mortgage and truck books dominate, which
# then divided into a THB121,682 ticket to produce a 30.8% national LTV proxy while every single type
# row sat near 50%. A summary line that no row underneath it agrees with is a bug, not a nuance.
PER_ACCT = ("dpd90p_pct", "late180_pct", "early_pct", "dpd30p_pct", "eval_avg", "npat_margin_avg")


def _roll(cells):
    """Account-weighted rollup of the per-account fields, plus the two plain sums."""
    agg = {"n": sum(int(v.get("n") or 0) for v in cells),
           "os_sum": sum(float(v.get("os_sum") or 0.0) for v in cells)}
    for f in PER_ACCT:
        w = sum(int(v.get("n") or 0) for v in cells if v.get(f) is not None)
        agg[f] = (round(sum(int(v["n"]) * float(v[f]) for v in cells
                            if v.get(f) is not None) / w, 2) if w else None)
    return agg


def _types_from(cells, total_os, total_n):
    """The full mix to 100% — point 12. Every type is emitted, never a top-N slice."""
    out = []
    for code, v in cells.items():
        lab, tier = TYPE_LAB.get(code, (code, "other"))
        row = _core(v)
        row.update({
            "type": code, "label": lab, "tier": tier,
            "os_share_pct": round(100.0 * row["os"] / total_os, 1) if total_os else None,
            "n_share_pct": round(100.0 * row["n"] / total_n, 1) if total_n else None,
        })
        out.append(row)
    out.sort(key=lambda r: (-r["os"], r["type"]))
    return out


def build():
    tape = _load(STAGING) or {}
    tabs = tape.get("tabs") or {}
    bgeo = tape.get("branch_geo") or {}

    real = _p("tape_real.json") or {}
    veh = _p("vehicle_collateral.json") or {}     # DLT car+pickup stock, diesel share, brand mix
    evp = _p("ev_penetration.json") or {}         # DLT electrified / BEV / diesel share, 77 prov
    truck = _p("truck_flow.json") or {}           # DLT truck new/transfer/dereg, 77 prov
    flow = _p("collateral_flow.json") or {}       # DLT used-vehicle transfer + dereg, by region
    fleet = _p("vehicle_fleet.json") or {}        # DLT national stock by class, 6-year series
    bveh = _p("branch_vehicles.json") or {}       # per-branch local fleet mix (ESTIMATED)

    # ---- national + region: OUR BOOK by vehicle type (MEASURED) --------------------------------
    vt = tabs.get("vehicle_type") or {}
    nat_os = sum(float(v.get("os_sum") or 0) for v in vt.values())
    nat_n = sum(int(v.get("n") or 0) for v in vt.values())
    types = _types_from(vt, nat_os, nat_n)

    reg_types = {}
    for key, v in (tabs.get("vehicle_x_georegion") or {}).items():
        code, reg = key.split("|", 1)
        reg_types.setdefault(reg, {})[code] = v

    # ---- province: our book (MEASURED) + the DLT collateral base around it (MEASURED) -----------
    ev_pv = {r["th"]: r for r in (evp.get("provinces") or []) if r.get("th")}
    veh_pv = {r["th"]: r for r in (veh.get("provinces") or []) if r.get("th")}
    tr_pv = {r["th"]: r for r in (truck.get("provinces") or []) if r.get("th")}
    # province -> region from the tape's own branch geo, so this file cannot disagree with the tape
    prov_reg = {}
    for g in bgeo.values():
        if g.get("prov") and g.get("region"):
            prov_reg.setdefault(g["prov"], g["region"])

    provinces = {}
    for th, v in (tabs.get("province") or {}).items():
        if th in ("(blank)", "(unjoined)", "(head office / direct sales)"):
            continue
        rec = _core(v)
        e, vh, tr = ev_pv.get(th) or {}, veh_pv.get(th) or {}, tr_pv.get(th) or {}
        rec.update({
            "region": prov_reg.get(th),
            # the local collateral BASE — what is out there to lend against and recover into
            "fleet_total": e.get("total"),
            "diesel_share_pct": vh.get("diesel_share_pct"),
            "electrified_pct": e.get("electrified_pct"),
            "bev_pct": e.get("bev_pct"),
            "pickup_stock": vh.get("pickup_total"),
            "car_pickup_stock": vh.get("car_pickup_total"),
            # trucks belong here, not in a business-backdrop section (point 18)
            "truck_new_12m": tr.get("new_regis_12m"),
            "truck_net_flow": tr.get("net_flow_12m"),
            "truck_new_yoy_pct": tr.get("new_regis_yoy_pct"),
        })
        provinces[th] = rec

    regions = {}
    for reg, cells in sorted(reg_types.items()):
        agg = _roll(cells.values())
        r_os, r_n = agg["os_sum"], agg["n"]
        rec = _core(agg)
        rec["types"] = _types_from(cells, r_os, r_n)
        rec["provinces"] = sum(1 for p in provinces.values() if p.get("region") == reg)
        # the two focus classes as one number, so a region row answers point 14 directly
        core_os = sum(t["os"] for t in rec["types"] if t["tier"] == "core")
        rec["core_share_pct"] = round(100.0 * core_os / r_os, 1) if r_os else None
        moto = next((t for t in rec["types"] if t["type"] == "MC"), None)
        rec["moto_os_share_pct"] = moto["os_share_pct"] if moto else None
        rec["moto_n_share_pct"] = moto["n_share_pct"] if moto else None
        regions[reg] = rec

    # ---- branch: our book (MEASURED) + the branch's own local fleet mix (ESTIMATED) -------------
    # branch_vehicles.json is a POSITIONAL array aligned to branches.json, not keyed by name, and it
    # stamps the branches_fingerprint it was built against. Verify that fingerprint before indexing
    # by position — a stale alignment would attach one branch's local fleet to another's book, which
    # is worse than showing no fleet column at all. On any mismatch the columns are simply absent.
    bmix, mix_basis = {}, "absent"
    master = _load(os.path.join(HERE, "..", "source-data", "branches_final.json"))
    mrows = master if isinstance(master, list) else (master or {}).get("branches", [])
    bvrows = bveh.get("branches") or []
    fp_want = (bveh.get("meta") or {}).get("branches_fingerprint")
    fp_have = branches_fingerprint(_p("branches.json") or []) if fp_want else None
    if mrows and bvrows and len(mrows) == len(bvrows) and fp_want and fp_want == fp_have:
        idx, _coll = master_index(mrows, lambda m: m.get("name"))
        pos = {}
        for i, m in enumerate(mrows):
            k = norm_branch(m.get("name"))
            if k and k not in pos:
                pos[k] = i
        for k, i in pos.items():
            bmix[k] = bvrows[i]
        mix_basis = "measured-stock, catchment-allocated (ESTIMATED)"

    branches = {}
    n_mix = 0
    for br, v in (tabs.get("branch_full") or {}).items():
        g = bgeo.get(br) or {}
        th = g.get("prov")
        if th not in provinces:
            continue
        row = _core(v)
        row["name"] = br
        # The branch's own share of the local vehicle POPULATION, in units — not its mix.
        #
        # branch_vehicles.json allocates the province stock to each 10km catchment by population
        # share, so every branch in a province gets the SAME percentage mix and only the absolute
        # count differs. Verified: the mix is identical across branches in all 77 provinces. Emitting
        # `fleet_pickup_pct` per branch would therefore print province data in a branch column and
        # invite a comparison between two branches that can never differ. The absolute count IS
        # branch-specific and does carry information (how big a collateral pool this branch sits in),
        # so that is what is carried, labelled ESTIMATED.
        bv = bmix.get(norm_branch(br)) or {}
        fl = bv.get("fleet") or {}
        row["fleet_est"] = bv.get("n_est")
        row["fleet_pickup_est"] = fl.get("pickup")
        if fl:
            n_mix += 1
        branches.setdefault(th, []).append(row)
    for th in branches:
        branches[th].sort(key=lambda r: (-r["os"], r["name"]))

    national = _core(_roll(vt.values()))
    core_os = sum(t["os"] for t in types if t["tier"] == "core")
    core_n = sum(t["n"] for t in types if t["tier"] == "core")
    moto = next((t for t in types if t["type"] == "MC"), None)
    national.update({
        "provinces": len(provinces),
        "branches": sum(len(v) for v in branches.values()),
        "types": len(types),
        "core_share_pct": round(100.0 * core_os / nat_os, 1) if nat_os else None,
        "core_n_share_pct": round(100.0 * core_n / nat_n, 1) if nat_n else None,
        "moto_os_share_pct": moto["os_share_pct"] if moto else None,
        "moto_n_share_pct": moto["n_share_pct"] if moto else None,
    })

    # ---- the resale market this mix recovers into (points 18 + 19, moved in from elsewhere) -----
    used = []
    for r in (flow.get("regions") or []):
        row = {"region": r.get("region")}
        for k in ("all", "car", "pickup", "moto"):
            c = r.get(k) or {}
            row[k] = {"transfer_rate": c.get("transfer_rate"), "dereg_rate": c.get("dereg_rate"),
                      "transferred": c.get("transferred"), "processed": c.get("processed")}
        used.append(row)
    used.sort(key=lambda r: r["region"] or "")

    return {
        "meta": {
            "title": "Collateral book by baht — mix to 100%, all provinces, our branches",
            "generated_by": "pipeline/build_collateral_book.py",
            "deterministic": True,
            "network_free": True,
            "label": (
                "MEASURED — our book (accounts, outstanding, appraised value, arrears buckets) comes "
                "from the real loan tape; the collateral BASE around each province (fleet, diesel "
                "share, electrified share, truck flow) comes from DLT registrations. Ticket, the LTV "
                "proxy and every share are DERIVED from those measured inputs. Per-branch local fleet "
                "mix is ESTIMATED (branch_vehicles.json)."
            ),
            "ranking": "outstanding baht at every grain — ranking by accounts would lead with "
                       "motorcycles, which are 33.3% of accounts and 5.8% of the money",
            "focus_note": (
                "Types are tiered per the owner's stated focus: pickup and passenger car are CORE, "
                "motorcycles SECONDARY on ticket size. The tape supports it — motorcycles carry the "
                "highest 90+ rate of any class as well as the smallest ticket."
            ),
            "grain_gap": (
                "The tape export crosses vehicle type with REGION only. The per-province and "
                "per-branch vehicle split of our own book is therefore absent from this file and is "
                "NOT estimated into it: province and branch rows carry measured totals plus the "
                "measured local vehicle population, and stop there."
            ),
            "export_asks": [
                "vehicle_x_province — our book's collateral mix per province (would complete the drill)",
                "vehicle_x_branch — the same per branch",
                "branch_id on every row — the branch join is by name today (99.73% matched)",
            ],
            "ltv_proxy_note": (
                "ltv_proxy_pct = outstanding per account / appraised value per account. Both inputs "
                "MEASURED, the ratio DERIVED. Outstanding amortises while the appraisal is struck at "
                "origination, so read it as how much of assessed value is still lent against — not a "
                "regulatory LTV."
            ),
            "sources": ["source-data/staging/real_tape_aggregates.json", "tape_real.json",
                        "vehicle_collateral.json", "ev_penetration.json", "truck_flow.json",
                        "collateral_flow.json", "vehicle_fleet.json", "branch_vehicles.json"],
            "mob_anchor": (tape.get("meta") or {}).get("mob_anchor"),
            "n_accounts": (tape.get("meta") or {}).get("n_accounts"),
            "dlt_fleet_vintage": (fleet.get("meta") or {}).get("latest_year_ce"),
            "n_provinces": len(provinces),
            "n_branches": sum(len(v) for v in branches.values()),
            "branch_fleet_basis": mix_basis,
            "branch_fleet_coverage": n_mix,
            "branches_fingerprint": fp_have,
        },
        "national": national,
        "regions": regions,
        "provinces": provinces,
        "branches": branches,
        "types": types,
        "used_flow": used,
        "fleet_classes": (fleet.get("classes") or []),
        "brand_mix": (veh.get("national_brand_mix") or {}),
        "brand_book": _brand_book(real, nat_os),
    }


def _brand_book(real, nat_os):
    """Every brand the tape carries, ranked by outstanding — point 8 ("I want to know about all the
    other brands as well"). The DLT brand mix says what the COUNTRY buys; this says what WE hold."""
    by = ((real.get("collateral") or {}).get("by_brand")) or {}
    rows = []
    for name, v in by.items():
        n = int(v.get("n") or 0)
        os_ = float(v.get("os_sum") or 0.0)
        ev = v.get("eval_avg")
        rows.append({
            "brand": name, "n": n, "os": int(round(os_)),
            "os_share_pct": round(100.0 * os_ / nat_os, 1) if nat_os else None,
            "ticket": int(round(os_ / n)) if n else None,
            "eval_avg": int(round(ev)) if ev else None,
            "ltv_proxy_pct": (round(100.0 * (os_ / n) / ev, 1) if n and ev else None),
            "dpd90p_pct": v.get("dpd90p_pct"), "late180_pct": v.get("late180_pct"),
        })
    rows.sort(key=lambda r: (-r["os"], r["brand"]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the committed file reproduces byte-for-byte")
    args = ap.parse_args()

    if not os.path.exists(STAGING):
        print("build_collateral_book.py: SKIP (real_tape_aggregates.json absent)")
        return 0

    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            print("DRIFT: platform/data/collateral_book.json missing — run build_collateral_book.py")
            return 1
        with open(OUT, encoding="utf-8") as f:
            if f.read() != payload:
                print("DRIFT: platform/data/collateral_book.json differs from a fresh build")
                return 1
        n = json.loads(payload)["national"]
        print("OK: collateral_book.json reproduces (THB%.2fbn, %d types, %d provinces, %d branches; "
              "core %.1f%% of baht on %.1f%% of accounts)"
              % (n["os"] / 1e9, n["types"], n["provinces"], n["branches"],
                 n["core_share_pct"] or 0, n["core_n_share_pct"] or 0))
        return 0

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    doc = json.loads(payload)
    n = doc["national"]
    print("wrote %s — THB%.2fbn across %s accounts, %d types to 100%%, %d provinces, %d branches"
          % (OUT, n["os"] / 1e9, f"{n['n']:,}", n["types"], n["provinces"], n["branches"]))
    print("  pickup + passenger car = %.1f%% of outstanding on %.1f%% of accounts; "
          "motorcycles %.1f%% of outstanding on %.1f%% of accounts"
          % (n["core_share_pct"], n["core_n_share_pct"], n["moto_os_share_pct"], n["moto_n_share_pct"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
