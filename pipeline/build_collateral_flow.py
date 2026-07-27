#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_collateral_flow.py — PORTFOLIO RISK (objective #1): the used-vehicle collateral pulse for
AutoX's PRIMARY title classes — motorcycles, cars and pickups — REGIONALLY.

The commercial-fleet sibling build_truck_flow.py (DLT transport-law log, dataset_stat_1_009)
already surfaces trucks/buses. But the CAR-LAW registration log (dataset_stat_1_008) — which
covers cars/pickups/MOTORCYCLES, i.e. the classes that actually secure a title-loan book
(motorcycle title ≈ 50% of AutoX's book, car/pickup ≈ 25%) — was distilled into
source-data/vehicle_flow_by_province.json by build_vehicle_flow.py and then left with NO
downstream consumer and NO exec surface. This script projects that committed intermediate into
platform/data so the primary-collateral pulse reaches the app, mirroring truck_flow.

WHY REGIONAL, NOT PER-PROVINCE (the honesty crux):
The per-province transfer_rate / dereg_rate in the intermediate are geographically CONFOUNDED by
central metropolitan registration. Verified in the committed data: the dense Bangkok-ring provinces
(Pathum Thani 0.45%, Nonthaburi 0.61%, Samut Prakan 0.60% moto transfer rate; 0.03-0.06% dereg)
are artifactually DEFLATED while Bangkok is inflated (10.35% / 2.84%), because transfers and
deregistrations for the metro cluster clear at the Bangkok DLT office. Ranking provinces on these
ratios would present an administrative artifact as a collateral-market signal. Aggregating to the
5 macro regions CANCELS that fixed within-metro bias (the metro transfers land in the same region
they belong to), yielding a coherent moto-transfer band of 5.2-7.3% and a dereg band of 0.19-1.58%.
So — exactly like the regional household-debt card — REGION is the honest grain here. (The clean
per-province signal would be YoY momentum, which cancels the fixed bias the way build_truck_flow
does; that needs the >=24-month raw DLT mirror, which is gitignored/owner-side, so it is out of
scope for this CI-reproducible projection.)

Reads the ALREADY-COMMITTED source-data/vehicle_flow_by_province.json (NOT the gitignored raw
mirror), so this projection is fully deterministic + network-free and its --check byte-reproduces
in CI (it does not SKIP). 100% MEASURED sums + plain ratios; no modelling, nothing invented.

    python3 build_collateral_flow.py
    python3 build_collateral_flow.py --check     # byte-exact reproduce (exit 0), SKIP (exit 3) if input absent
"""
import argparse, json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPE)
from regionmap import canonical, REGION

IN = os.path.join(ROOT, "source-data", "vehicle_flow_by_province.json")
OUT = os.path.join(ROOT, "platform", "data", "collateral_flow.json")

TYPES = ["all", "car", "pickup", "moto"]        # the title-loan collateral classes (all = every รย. class)
CORE = ["moto", "car", "pickup"]                # composition denominator (exclude "all", which is the union)


def _rate(num, den):
    return round(num / den, 4) if den else None


def _be_window(months):
    """['2568-03', ..., '2569-02'] (Buddhist-Era) -> ('2025-03', '2026-02') Common-Era, or None."""
    if not months:
        return None
    def ce(m):
        y, mm = m.split("-")
        return "%d-%s" % (int(y) - 543, mm)
    return [ce(months[0]), ce(months[-1])]


def build():
    src = json.load(open(IN, encoding="utf-8"))
    prov = src.get("provinces") or {}
    smeta = src.get("meta") or {}

    reg = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))   # region -> type -> field -> sum
    nat = defaultdict(lambda: defaultdict(int))                        # type -> field -> sum
    for name, bytype in prov.items():
        r = REGION.get(canonical(name))
        if not r:
            continue
        for t in TYPES:
            e = bytype.get(t)
            if not e:
                continue
            for f in ("processed", "transferred", "dereg_permanent"):
                reg[r][t][f] += int(e.get(f, 0))
                nat[t][f] += int(e.get(f, 0))

    def pack(agg, t):
        p, x, d = agg[t]["processed"], agg[t]["transferred"], agg[t]["dereg_permanent"]
        return {"processed": p, "transferred": x, "dereg_permanent": d,
                "transfer_rate": _rate(x, p), "dereg_rate": _rate(d, p)}

    regions = []
    for r in sorted(reg.keys()):
        row = {"region": r}
        for t in TYPES:
            row[t] = pack(reg[r], t)
        regions.append(row)
    # attrition-first ordering: worst moto dereg_rate on top (region name as the deterministic tiebreak)
    regions.sort(key=lambda o: (-(o["moto"]["dereg_rate"] or 0.0), o["region"]))

    national = {t: pack(nat, t) for t in TYPES}
    core_proc = sum(nat[t]["processed"] for t in CORE)
    national_mix = {t: round(100.0 * nat[t]["processed"] / core_proc, 1) if core_proc else None for t in CORE}

    window = _be_window(smeta.get("window_months"))

    return {
        "meta": {
            "title": "Used-collateral pulse (motorcycle / car / pickup) by region — registration-transaction flow (measured)",
            "generated_by": "pipeline/build_collateral_flow.py",
            "label": "MEASURED — DLT car-law registration actions (gdcatalog dataset_stat_1_008), the "
                     "motorcycle/car/pickup classes that secure a title-loan book, aggregated to the 5 macro "
                     "regions. Trailing-12-month sums + plain ratios; no modelling, nothing invented.",
            "source": "source-data/vehicle_flow_by_province.json (pipeline/build_vehicle_flow.py over the "
                      "gdcatalog.dlt.go.th dataset_stat_1_008 mirror)",
            "grain": "region",
            "grain_why": "per-province transfer_rate/dereg_rate are confounded by central metropolitan "
                         "registration (the Bangkok-ring provinces are artifactually deflated, Bangkok "
                         "inflated); aggregating to region cancels that fixed within-metro bias, so region "
                         "is the honest grain. See the module docstring for the verified figures.",
            "window": window,
            "fields": {
                "processed": "MEASURED — total car-law registration actions in the window (the base)",
                "transferred": "MEASURED — ownership transfers (รถโอน) — used-market liquidity, which sets how "
                               "easily repossessed collateral clears",
                "dereg_permanent": "MEASURED — permanent deregistrations (รถแจ้งไม่ใช้ตลอดไป) — the collateral "
                                   "base leaving the fleet (scrappage/ageing/export)",
                "transfer_rate": "MEASURED — transferred / processed",
                "dereg_rate": "MEASURED — dereg_permanent / processed (collateral-attrition intensity)",
            },
            "why": "motorcycles are ~50% of AutoX's title-loan book and car/pickup ~25%; a more active used "
                   "market (higher transfer intensity) means repossessed collateral clears faster, while a "
                   "higher permanent-deregistration rate marks where the collateral base is attriting faster. "
                   "A backdrop read on the footprint we already run — NOT an open/close/expand cue.",
            "national": national,
            "national_mix_pct": national_mix,
            "n_regions": len(regions),
            "sort": "worst moto dereg_rate (collateral attrition) first",
            "provenance": "MEASURED. Government registry sums only; regional aggregation + two plain ratios, "
                          "nothing modelled or invented.",
            "caveats": [
                "REGIONAL grain only — per-province ratios are confounded by central metro registration; do not "
                "rank provinces on this layer.",
                "A single trailing-12-month LEVEL snapshot (%s), not a YoY momentum trend — read the levels, not a "
                "direction. A clean per-province momentum cut needs the >=24-month raw DLT mirror (owner-side)."
                % ("%s..%s" % (window[0], window[1]) if window else "window in source meta"),
                "Registration actions are a proxy for the vehicle market/fleet, not AutoX's own book.",
            ],
        },
        "regions": regions,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN):
        print("build_collateral_flow.py: source-data/vehicle_flow_by_province.json absent "
              "(run build_vehicle_flow.py over the DLT mirror) — SKIP.")
        sys.exit(3)
    data = build()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            print("build_collateral_flow.py --check: SKIP (collateral_flow.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_collateral_flow.py --check: drifted — re-run the builder.")
        print("build_collateral_flow.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    n = data["meta"]["national"]["moto"]
    mix = data["meta"]["national_mix_pct"]
    print("wrote %s — %d regions; national moto transfer %.2f%% / dereg %.3f%%; mix moto %.1f%% car %.1f%% pickup %.1f%%" % (
        OUT, data["meta"]["n_regions"], (n["transfer_rate"] or 0) * 100, (n["dereg_rate"] or 0) * 100,
        mix["moto"], mix["car"], mix["pickup"]))
    for r in data["regions"]:
        m = r["moto"]
        print("   %-12s moto xfer %.2f%%  dereg %.3f%%  (proc %d)" % (
            r["region"], (m["transfer_rate"] or 0) * 100, (m["dereg_rate"] or 0) * 100, m["processed"]))


if __name__ == "__main__":
    main()
