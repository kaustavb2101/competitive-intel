#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_tape_layers.py — project the REAL loan-tape aggregates into the app (objective #1, MEASURED)

  in : source-data/staging/real_tape_aggregates.json  (ingest_real_tape.py — no-PII aggregates)
       platform/data/drought_district.json            (OAE SPEI by amphoe — the FIRING trigger)
       platform/data/amphoe_crops.json                (district crop rows — names what's at stake)
  out: platform/data/tape_real.json
       sections: ltv_ladder · vintage_curve (months-on-book normalized) · occupations ·
       provinces · collateral (brand/age) · npat_frontier · branch_audit ·
       assistance_radar (Tier1 = X-days slipping / Tier2 = current-but-exposed, by province,
       drought-triggered, with the stressed crops named)

Deterministic + network-free; `--check` byte-compares; exit 3 SKIP when the staging file is
absent (the tape is an owner-side ingest, like the other pull-fed staging inputs).

Provenance: MEASURED (real tape aggregates; cells n>=30) joined to MEASURED drought (OAE SPEI)
and MEASURED crop rows (OAE amphoe surveys). The radar's priority ORDER is an ESTIMATED ranking
formula over those measured inputs — labelled as such in meta.
"""
import argparse
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_TAPE = os.path.join(ROOT, "source-data", "staging", "real_tape_aggregates.json")
IN_DROUGHT = os.path.join(ROOT, "platform", "data", "drought_district.json")
IN_CROPS = os.path.join(ROOT, "platform", "data", "amphoe_crops.json")
OUT = os.path.join(ROOT, "platform", "data", "tape_real.json")


def build():
    tape = json.load(open(IN_TAPE, encoding="utf-8"))
    tabs, tmeta = tape["tabs"], tape["meta"]

    # --- province drought stress (share of districts severe+, worst SPEI) ---
    pd_stat = collections.defaultdict(lambda: [0, 0, 0.0])
    if os.path.exists(IN_DROUGHT):
        for d in json.load(open(IN_DROUGHT, encoding="utf-8"))["districts"]:
            p = pd_stat[d["province_th"]]
            p[0] += 1
            if d.get("cls") in ("severe", "extreme"):
                p[1] += 1
            if d.get("spei") is not None:
                p[2] = min(p[2], d["spei"])

    # --- what the stressed districts grow (top crops by planted rai in severe+ districts) ---
    crop_by_prov = collections.defaultdict(collections.Counter)
    if os.path.exists(IN_CROPS):
        for r in json.load(open(IN_CROPS, encoding="utf-8"))["rows"]:
            if r.get("drought") in ("severe", "extreme") and r.get("planted_rai"):
                crop_by_prov[r["province_th"]][r.get("crop_th") or r["crop"]] += r["planted_rai"]

    # --- assistance radar: farmer cells x drought ---
    radar = []
    for key, v in tabs.get("prov_x_occ", {}).items():
        prov, occ = key.split("|", 1)
        if occ != "เกษตร" or prov == "(unjoined)":
            continue
        ds = pd_stat.get(prov)
        if not ds or not ds[0] or v["n"] < 100:
            continue
        sev = ds[1] / ds[0]
        if sev <= 0:
            continue
        tier1 = round(v["n"] * v["early_pct"] / 100.0)
        tier2 = v["n"] - tier1 - round(v["n"] * v["dpd30p_pct"] / 100.0)
        crops = [c for c, _ in crop_by_prov.get(prov, collections.Counter()).most_common(3)]
        radar.append({
            "province": prov, "n_farmers": v["n"], "tier1_slipping": tier1,
            "tier2_current_exposed": tier2, "dpd30p_pct": v["dpd30p_pct"],
            "os_thb": v["os_sum"], "districts_severe_pct": round(sev * 100, 1),
            "worst_spei": round(ds[2], 2), "stressed_crops": crops,
            "priority": round(sev * (v["early_pct"] + 0.5 * v["dpd30p_pct"]) * v["n"] / 1000, 1),
        })
    radar.sort(key=lambda r: (-r["priority"], r["province"]))

    # --- NPAT frontier: occupation x region cells (risk vs return) ---
    frontier = []
    for key, v in tabs.get("occ_x_region", {}).items():
        occ, reg = key.split("|", 1)
        if occ == "(blank)" or reg == "(blank)":
            continue
        frontier.append({"occupation": occ, "region": reg, "n": v["n"],
                         "dpd30p_pct": v["dpd30p_pct"], "npat_margin_avg": v["npat_margin_avg"]})
    frontier.sort(key=lambda r: (-r["n"]))

    # --- branch audit: worst dpd30+ with n>=100 (our own branches; internal tool) ---
    audit = [{"branch": b, "n": v["n"], "dpd30p_pct": v["dpd30p_pct"], "fpd_pct": v["fpd_pct"],
              "early_pct": v["early_pct"]}
             for b, v in tabs.get("branch", {}).items() if v["n"] >= 100]
    audit.sort(key=lambda r: (-r["dpd30p_pct"], r["branch"]))

    # --- collateral: brand x coll-age depreciation-adjacent view (eval_avg per age band) ---
    coll = collections.defaultdict(dict)
    for key, v in tabs.get("brand_x_collage", {}).items():
        brand, age = key.split("|", 1)
        if "eval_avg" in v and v["n"] >= 50 and brand != "(blank)" and age != "(blank)":
            coll[brand][age] = {"n": v["n"], "eval_avg": v["eval_avg"],
                                "dpd30p_pct": v["dpd30p_pct"]}
    top_brands = sorted(coll, key=lambda b: -sum(x["n"] for x in coll[b].values()))[:14]

    headline = ""
    if radar:
        r0 = radar[0]
        headline = ("REAL tape: %s accounts. Assistance radar #1: %s — %d farmers slipping "
                    "(X-days) + %d current-but-exposed under %s%% severe-drought districts."
                    % ("{:,}".format(tmeta["n_accounts"]), r0["province"],
                       r0["tier1_slipping"], r0["tier2_current_exposed"],
                       r0["districts_severe_pct"]))

    return {
        "meta": {
            "title": "Real loan tape — measured portfolio truth (objective #1)",
            "generated_by": "pipeline/build_tape_layers.py",
            "label": "MEASURED — real AutoX loan-tape aggregates (no-PII, cells n>=30; raw stays "
                     "on the owner's disk) x MEASURED OAE drought + amphoe crops. The radar "
                     "priority ORDER is an ESTIMATED ranking over those measured inputs.",
            "source": tmeta.get("source"),
            "n_accounts": tmeta.get("n_accounts"),
            "branch_join_pct": (tmeta.get("branch_join") or {}).get("pct"),
            "mob_anchor": tmeta.get("mob_anchor"),
            "fpd_note": tmeta.get("fpd_note"),
            "triggers": {"drought": "FIRING — OAE SPEI severe/extreme districts",
                         "crop_margin": "armed, not firing (all joined crops clear cost)",
                         "fuel": "armed — wire to fuel_prices trend"},
        },
        "headline": headline,
        "ltv_ladder": tabs.get("ltv_range", {}),
        "vintage_curve": tabs.get("vintage_curve", {}),
        "occupations": tabs.get("occupation", {}),
        "occ_x_income": tabs.get("occ_x_income", {}),
        "provinces": tabs.get("province", {}),
        "income_tiers": tabs.get("income_tier", {}),
        "vehicle_types": tabs.get("vehicle_type", {}),
        "product_groups": tabs.get("product_group", {}),
        "collateral_brands": {b: coll[b] for b in top_brands},
        "npat_frontier": frontier[:60],
        "branch_audit": audit[:25],
        "assistance_radar": radar[:20],
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN_TAPE):
        if args.check:
            print("build_tape_layers.py --check: SKIP (no real-tape staging — owner-side ingest)")
            sys.exit(3)
        sys.exit("build_tape_layers.py: run ingest_real_tape.py first")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_tape_layers.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_tape_layers.py --check: drifted — re-run the builder.")
        print("build_tape_layers.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d radar rows, %d audit branches, %d frontier cells"
          % (OUT, len(obj["assistance_radar"]), len(obj["branch_audit"]),
             len(obj["npat_frontier"])))
    print("headline:", obj["headline"])


if __name__ == "__main__":
    main()
