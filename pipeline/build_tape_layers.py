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
# Owner-provided cost structure (2026-07-24, MEASURED management figures): standard portfolio
# yield 23.99%, but the Land collateral book yields only 15%; operating cost 8% of book; cost of
# funds 2.5%. Gross spread = yield - opex - CoF (credit loss layered on top via the 90+/NPL lens).
COST = {"yield_standard": 23.99, "yield_land": 15.0, "opex": 8.0, "cof": 2.5}
IN_DROUGHT = os.path.join(ROOT, "platform", "data", "drought_district.json")
IN_CROPS = os.path.join(ROOT, "platform", "data", "amphoe_crops.json")
OUT = os.path.join(ROOT, "platform", "data", "tape_real.json")


def _rows(tabs, tab, names, top=None, minn=50):
    """Flatten a 'a|b' cross-tab into sorted rows, dropping blank/thin cells."""
    out = []
    for key, v in tabs.get(tab, {}).items():
        parts = key.split("|", 1)
        if len(parts) != 2 or "(blank)" in parts or "(unjoined)" in parts or v["n"] < minn:
            continue
        row = {names[0]: parts[0], names[1]: parts[1], "n": v["n"], "os_sum": v["os_sum"],
               "dpd90p_pct": v["dpd90p_pct"], "npl_live_pct": v["npl_live_pct"],
               "late180_pct": v["late180_pct"]}
        if "eval_avg" in v:
            row["eval_avg"] = v["eval_avg"]
        out.append(row)
    out.sort(key=lambda r: -r["n"])
    return out[:top] if top else out


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

    # --- assistance radar: farmer cells x drought (tiers keyed on the X-days window) ---
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
            "tier2_current_exposed": tier2, "dpd90p_pct": v["dpd90p_pct"],
            "npl_live_os_pct": v["npl_live_os_pct"], "dpd30p_pct": v["dpd30p_pct"],
            "os_thb": v["os_sum"], "districts_severe_pct": round(sev * 100, 1),
            "worst_spei": round(ds[2], 2), "stressed_crops": crops,
            "priority": round(sev * (v["early_pct"] + 0.5 * v["dpd30p_pct"]) * v["n"] / 1000, 1),
        })
    radar.sort(key=lambda r: (-r["priority"], r["province"]))

    # --- SEGMENTS HIT MOST (owner ask 2026-07-24): the ranked hit-list — which segments are
    #     hurting NOW (90+ severity), what's rolling toward them (30-89), and what's slipping
    #     (X-days momentum). Score is an ESTIMATED ordering over MEASURED shares. ---
    def hit_rows(tab, keysplit):
        rows = []
        for key, v in tabs.get(tab, {}).items():
            parts = key.split("|", 1)
            if len(parts) != 2 or "(blank)" in parts or "(unjoined)" in parts or v["n"] < 300:
                continue
            score = round(v["dpd90p_pct"] + 0.5 * v["roll_pct"] + 0.25 * v["early_pct"], 2)
            rows.append({keysplit[0]: parts[0], keysplit[1]: parts[1], "n": v["n"],
                         "dpd90p_pct": v["dpd90p_pct"], "roll_pct": v["roll_pct"],
                         "early_pct": v["early_pct"], "npl_live_os_pct": v["npl_live_os_pct"],
                         "os_sum": v["os_sum"], "score": score})
        rows.sort(key=lambda r: (-r["score"], -r["n"]))
        return rows
    segments_hit = {
        "occ_x_region": hit_rows("occ_x_region", ("occupation", "region"))[:20],
        "prov_x_occ": hit_rows("prov_x_occ", ("province", "occupation"))[:20],
        "occ_x_income": hit_rows("occ_x_income", ("occupation", "income_tier"))[:15],
        "score_note": "score = 90+% + 0.5×(30-89%) + 0.25×(X-days%) — ESTIMATED ordering "
                      "over MEASURED shares; cells under 300 accounts excluded",
    }

    # --- AGRI IMPACT (owner ask: clear focus on agri factors vs the loan book) ---
    occ_tab = tabs.get("occupation", {})
    agri = occ_tab.get("เกษตร")
    book_n = tmeta.get("n_accounts") or sum(v["n"] for v in occ_tab.values())
    agri_by_prov = []
    for key, v in tabs.get("prov_x_occ", {}).items():
        prov, occ = key.split("|", 1)
        if occ != "เกษตร" or prov == "(unjoined)" or v["n"] < 100:
            continue
        ds = pd_stat.get(prov) or [0, 0, 0.0]
        sev = round(ds[1] * 100.0 / ds[0], 1) if ds[0] else None
        agri_by_prov.append({
            "province": prov, "n": v["n"], "os_sum": v["os_sum"],
            "dpd90p_pct": v["dpd90p_pct"], "roll_pct": v["roll_pct"],
            "early_pct": v["early_pct"], "npl_live_os_pct": v["npl_live_os_pct"],
            "districts_severe_pct": sev, "worst_spei": round(ds[2], 2) if ds[0] else None,
            "top_crops": [c for c, _ in crop_by_prov.get(prov, collections.Counter()).most_common(3)],
        })
    agri_by_prov.sort(key=lambda r: (-(r["dpd90p_pct"] or 0), -r["n"]))
    agri_impact = {
        "benchmark": {
            "agri": agri,
            "book_avg": {k: round(sum(v[k] * v["n"] for v in occ_tab.values()) /
                                  max(1, sum(v["n"] for v in occ_tab.values())), 2)
                         for k in ("dpd90p_pct", "roll_pct", "early_pct")},
            "agri_share_of_accounts_pct": round(agri["n"] * 100.0 / book_n, 1) if agri else None,
        },
        "by_province": agri_by_prov,
        "note": "MEASURED tape cells x MEASURED OAE drought/crops. Farmer accounts vs the "
                "whole-book average on every delinquency lens.",
    }

    # --- NPAT frontier: occupation x region cells (risk vs return, 90+ lens) ---
    frontier = []
    for key, v in tabs.get("occ_x_region", {}).items():
        occ, reg = key.split("|", 1)
        if occ == "(blank)" or reg == "(blank)":
            continue
        frontier.append({"occupation": occ, "region": reg, "n": v["n"],
                         "dpd90p_pct": v["dpd90p_pct"], "dpd30p_pct": v["dpd30p_pct"],
                         "npat_margin_avg": v["npat_margin_avg"]})
    frontier.sort(key=lambda r: (-r["n"]))

    # --- branch audit: worst 90+ with n>=100 (our own branches; internal tool) ---
    audit = [{"branch": b, "n": v["n"], "dpd90p_pct": v["dpd90p_pct"],
              "roll_pct": v["roll_pct"], "fpd_pct": v["fpd_pct"], "early_pct": v["early_pct"]}
             for b, v in tabs.get("branch", {}).items() if v["n"] >= 100]
    audit.sort(key=lambda r: (-r["dpd90p_pct"], r["branch"]))

    # --- collateral: brand x coll-age depreciation-adjacent view (eval_avg per age band) ---
    coll = collections.defaultdict(dict)
    for key, v in tabs.get("brand_x_collage", {}).items():
        brand, age = key.split("|", 1)
        if "eval_avg" in v and v["n"] >= 50 and brand != "(blank)" and age != "(blank)":
            coll[brand][age] = {"n": v["n"], "eval_avg": v["eval_avg"],
                                "dpd30p_pct": v["dpd30p_pct"]}
    top_brands = sorted(coll, key=lambda b: -sum(x["n"] for x in coll[b].values()))[:14]

    # --- BUCKET LADDER + two-book split (owner ask 2026-07-24): monitor Current -> NPL, and
    #     SEPARATE the 180+ legacy workout stock from the live book (it is late-stage collections
    #     inventory, not fresh underwriting risk; leaving it in distorts every ratio) ---
    LADDER = ["1.Current", "2.X_Days", "3.30_dpd", "4.60_dpd",
              "5.90_dpd", "6.120_dpd", "7.150_dpd", "8.180+_dpd"]
    db = tabs.get("dpd_bucket", {})
    ladder = [{"bucket": b, "n": db[b]["n"], "os_sum": db[b]["os_sum"]} for b in LADDER if b in db]
    live = [x for x in ladder if not x["bucket"].startswith("8.")]
    legacy = next((x for x in ladder if x["bucket"].startswith("8.")), {"n": 0, "os_sum": 0.0})
    live_n = sum(x["n"] for x in live)
    live_os = sum(x["os_sum"] for x in live)
    npl_live_n = sum(x["n"] for x in live if x["bucket"][0] in "567")
    npl_live_os = sum(x["os_sum"] for x in live if x["bucket"][0] in "567")
    bucket_ladder = {
        "ladder": ladder,
        "book_total": {"n": live_n + legacy["n"], "os_sum": round(live_os + legacy["os_sum"])},
        "live_book": {
            "n": live_n, "os_sum": round(live_os),
            "xdays_n": sum(x["n"] for x in live if x["bucket"].startswith("2.")),
            "roll_n": sum(x["n"] for x in live if x["bucket"][0] in "34"),
            "npl_live_n": npl_live_n, "npl_live_os": round(npl_live_os),
            "npl_live_pct": round(npl_live_n * 100.0 / live_n, 2) if live_n else None,
            "npl_live_os_pct": round(npl_live_os * 100.0 / live_os, 2) if live_os else None},
        "legacy_180plus": {
            "n": legacy["n"], "os_sum": round(legacy["os_sum"]),
            "acct_share_pct": round(legacy["n"] * 100.0 / (live_n + legacy["n"]), 1)
            if (live_n + legacy["n"]) else None},
        "note": "LIVE BOOK = Current..150dpd (the accounts to monitor). The 180+ bucket is legacy "
                "workout stock, reported SEPARATELY — late-stage collections inventory, not fresh "
                "risk. NPL-live = 90-179dpd as a share of the live book.",
    }

    # --- RESTRUCTURING STATUS (owner ask 2026-07-24): separate Normal / Pre-emptive / TDR / Skip.
    #     The CDCO question: did the restructure hold, or are these accounts re-defaulting? ---
    CHG_ORDER = ["Normal", "Skip", "Pre-emptive", "TDR"]
    chgtab = tabs.get("acc_chng", {})
    restructuring = {
        "by_status": [dict(status=s, **chgtab[s]) for s in CHG_ORDER if s in chgtab],
        "stage_mix": {},
        "note": "MEASURED account-change flag. Pre-emptive + TDR are already-restructured books; "
                "their 90+ and 180+ shares reveal whether the restructure held. Skip = payment "
                "holiday. Read against Normal as the baseline.",
    }
    for key, v in tabs.get("chg_x_bucket", {}).items():
        st, stage = key.split("|", 1)
        restructuring["stage_mix"].setdefault(st, {})[stage] = v["n"]
    restructuring["by_occupation"] = _rows(tabs, "chg_x_occ", ("status", "occupation"), top=24)
    restructuring["by_region"] = _rows(tabs, "chg_x_region", ("status", "region"))

    # --- COLLATERAL BOOK deep-dive (owner ask 2026-07-24): TYPE (segment) / AGE / BRAND crossed
    #     by location / occupation / income; branch concentration for the ACQUISITION lens
    #     ("where and what branches have what concentrations") ---
    collateral = {
        "by_type": tabs.get("coll_segment", {}),
        "by_age": tabs.get("coll_age", {}),
        "by_brand": {k: tabs["brand"][k] for k in sorted(
            tabs.get("brand", {}), key=lambda b: -tabs["brand"][b]["n"])[:20]},
        "brand_age_eval": {b: coll[b] for b in top_brands},
        "type_x_region": _rows(tabs, "coll_seg_x_region", ("type", "region")),
        "type_x_occ": _rows(tabs, "coll_seg_x_occ", ("type", "occupation"), top=30),
        "type_x_income": _rows(tabs, "coll_seg_x_income", ("type", "income_tier"), top=30),
        "age_x_occ": _rows(tabs, "collage_x_occ", ("age", "occupation"), top=30),
        "brand_x_area": _rows(tabs, "brand_x_area", ("brand", "area"), top=50, minn=50),
        "branch_type_concentration": _rows(tabs, "branch_x_seg", ("branch", "type"),
                                           top=40, minn=100),
        "branch_brand_concentration": _rows(tabs, "branch_x_brand", ("branch", "brand"),
                                            top=40, minn=100),
        "note": "MEASURED collateral book. TYPE = coll segment (MAJOR car / MINOR motorcycle / "
                "Mortgage / Land / TRACTOR). AGE = collateral age at origination. Branch "
                "concentration = the largest single type/brand books at a branch (acquisition-mix "
                "lens): where the network is over-indexed on one collateral kind.",
    }

    # --- UNIT ECONOMICS by collateral type (owner cost structure 2026-07-24): gross spread =
    #     yield - opex - CoF, then the 90+/NPL risk layered on. Land yields 15% (vs 23.99%) so its
    #     gross spread is thin — but it carries the lowest delinquency: a risk/return trade-off. ---
    economics = []
    for seg, v in tabs.get("coll_segment", {}).items():
        y = COST["yield_land"] if seg == "Land" else COST["yield_standard"]
        spread = round(y - COST["opex"] - COST["cof"], 2)
        economics.append({
            "type": seg, "n": v["n"], "os_sum": v["os_sum"], "yield_pct": y,
            "gross_spread_pct": spread, "dpd90p_pct": v["dpd90p_pct"],
            "npl_live_pct": v["npl_live_pct"], "late180_pct": v["late180_pct"],
            "eval_avg": v.get("eval_avg")})
    economics.sort(key=lambda r: -r["os_sum"])
    collateral["economics_by_type"] = economics
    collateral["cost_structure"] = COST
    collateral["economics_note"] = (
        "MEASURED yields/costs (owner mgmt figures). gross_spread = yield − opex(8%) − CoF(2.5%), "
        "BEFORE credit loss. Land yields 15% (gross spread 4.5%) vs 23.99% elsewhere (13.49%). "
        "The 90+ / 180+ columns are the RISK side, shown separately — they are point-in-time stock "
        "shares, not annualised loss rates, so do not subtract them from the spread. The trade-off "
        "to read: Land is thin-margin but lowest-risk (5.9% 90+); cars are wide-margin, higher-risk "
        "(15.5% 90+).")

    lb = bucket_ladder["live_book"]
    lg = bucket_ladder["legacy_180plus"]
    headline = (
        "REAL tape: %s accounts, ฿%.1fbn OS. LIVE BOOK %s accounts / ฿%.1fbn — "
        "NPL-live (90-179dpd) %.2f%% of accounts, %.2f%% OS-weighted; %s in the X-days "
        "pre-emptive window. Held SEPARATELY: a %s-account / ฿%.2fbn 180+ legacy workout "
        "stock (%.0f%% of accounts)."
        % ("{:,}".format(tmeta["n_accounts"]),
           bucket_ladder["book_total"]["os_sum"] / 1e9,
           "{:,}".format(lb["n"]), lb["os_sum"] / 1e9,
           lb["npl_live_pct"], lb["npl_live_os_pct"], "{:,}".format(lb["xdays_n"]),
           "{:,}".format(lg["n"]), lg["os_sum"] / 1e9, lg["acct_share_pct"]))

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
            "lens_note": tmeta.get("lens_note"),
            "cost_structure": COST,
            "triggers": {"drought": "FIRING — OAE SPEI severe/extreme districts",
                         "crop_margin": "armed, not firing (all joined crops clear cost)",
                         "fuel": "armed — wire to fuel_prices trend"},
        },
        "headline": headline,
        "bucket_ladder": bucket_ladder,
        "restructuring": restructuring,
        "collateral": collateral,
        "ltv_ladder": tabs.get("ltv_range", {}),
        "vintage_curve": tabs.get("vintage_curve", {}),
        "occupations": tabs.get("occupation", {}),
        "occ_x_income": tabs.get("occ_x_income", {}),
        "provinces": tabs.get("province", {}),
        # geographic tape rollups for the data-book drill-down (region cards / province / branch).
        # regions keyed East/Isan/North/South/Central&BKK (matches regions.json); branches keyed by
        # booking-branch name (top-N by size, cells n>=30 — larger branches only).
        "geo": {"regions": tabs.get("geo_region", {}),
                "provinces": tabs.get("province", {}),
                "branches": tabs.get("branch", {})},
        "income_tiers": tabs.get("income_tier", {}),
        "vehicle_types": tabs.get("vehicle_type", {}),
        "product_groups": tabs.get("product_group", {}),
        "collateral_brands": {b: coll[b] for b in top_brands},
        "segments_hit": segments_hit,
        "agri_impact": agri_impact,
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
