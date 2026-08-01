#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_branch_recommendations.py — per-branch ACTION recommendations (the "what to do here" read).

The platform shows rich STATS per branch; this turns them into a ranked list of concrete
RECOMMENDATIONS per branch — acquisition, defend, agri, collateral, borrower-base — so the right-
hand panel answers "what should we do at this branch?" not just "what is this branch?".

Synthesised (deterministically, network-free) from the committed per-branch layers:
  branch_agri (agri pressure · crop price YoY · rubber) · branch_vehicles (collateral score · pickup
  share) · branch_workforce (dominant occupation) · rival_pressure (rivals ≤2/5km) · branches.json
  (opportunity · population) · macro_indicators (national leverage/rate backdrop).

Each branch gets up to REC_MAX ranked recommendations: {k:kind, i:icon, t:text, p:priority, tone}.
INDEX-ALIGNED + fingerprinted; --check gated. Provenance: the inputs are measured/estimated as
labelled in their own layers; the recommendation is an ESTIMATED synthesis (a triage prompt, not a
credit decision).

  python3 build_branch_recommendations.py
  python3 build_branch_recommendations.py --check
"""
import argparse, json, os, sys
from lib.fingerprint import branches_fingerprint

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "platform", "data")
OUT = os.path.join(D, "branch_recommendations.json")
REC_MAX = 4


def _load(f):
    p = os.path.join(D, f)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def _rows(doc):
    if not doc:
        return None
    return doc.get("branches") if isinstance(doc, dict) else doc


def _pct(vals, q):
    v = sorted(x for x in vals if isinstance(x, (int, float)))
    return v[int(q * (len(v) - 1))] if v else 0.0


def build():
    branches = _load("branches.json")
    items = branches if isinstance(branches, list) else branches.get("items", branches)
    n = len(items)
    agri = _rows(_load("branch_agri.json"))
    veh = _rows(_load("branch_vehicles.json"))
    wf = _load("branch_workforce.json")
    wf_rows, wf_buckets = (wf.get("branches"), wf.get("buckets")) if wf else (None, None)
    rival = _rows(_load("rival_pressure.json"))
    agri_crops = (_load("branch_agri.json") or {}).get("meta", {}).get("crops", [])
    macro = (_load("macro_indicators.json") or {}).get("indicators", {})

    # thresholds from the data (deterministic percentiles)
    opp_hi = _pct([b.get("o") for b in items], 0.70)
    col_hi = _pct([r.get("collateral_score") for r in veh], 0.70) if veh else 60.0

    # national macro backdrop (same for all; one supportive/caution line)
    hh = macro.get("household_debt_gdp") or {}
    macro_rec = None
    if hh.get("yoy_change") is not None:
        macro_why = [{"s": "Household debt-to-GDP · BIS", "v": "%s%%" % hh.get("value"), "m": "measured"},
                     {"s": "YoY change · BIS", "v": "%+g pp" % hh["yoy_change"], "m": "measured"}]
        if hh["yoy_change"] < 0:
            macro_rec = {"k": "macro", "i": "🏦", "tone": "good", "p": 20,
                         "t": "Supportive backdrop: national household debt %s%% and falling (deleveraging)."
                              % hh.get("value"), "w": macro_why}
        elif hh["yoy_change"] > 0:
            macro_rec = {"k": "macro", "i": "🏦", "tone": "warn", "p": 30,
                         "t": "Caution: national household leverage rising (%s%% of GDP)." % hh.get("value"),
                         "w": macro_why}

    out = []
    for i, b in enumerate(items):
        recs = []
        a = agri[i] if agri and i < len(agri) else {}
        v = veh[i] if veh and i < len(veh) else {}
        rv = rival[i] if rival and i < len(rival) else {}
        n2 = rv.get("n2") or 0
        n5 = rv.get("n5") or 0
        opp = b.get("o")

        # 1) LOW COMPETITIVE PRESSURE — thin rival presence around this existing branch (a competitive-risk
        #    read for objective #2, NOT an expand/acquire call — the product makes no where-to-open recs).
        if isinstance(opp, (int, float)) and opp >= opp_hi and n5 <= 8:
            recs.append({"k": "acquire", "i": "🟢", "tone": "good", "p": 90,
                         "t": "Low competitive pressure: only %d rival branch(es) ≤5 km around this branch." % n5,
                         "w": [{"s": "Under-contested score · branches.json", "v": "%d (≥ p70 = %d)" % (round(opp), round(opp_hi)), "m": "est"},
                               {"s": "Rival branches ≤5 km · rival_pressure.json", "v": "%d (≤8)" % n5, "m": "measured"}]})
        # 2) DEFEND — besieged by rivals
        if n2 >= 3:
            recs.append({"k": "defend", "i": "⚔️", "tone": "warn", "p": 85,
                         "t": "Defend the book: %d competitor branch(es) ≤2 km — differentiate on service/turnaround, watch churn." % n2,
                         "w": [{"s": "Competitor branches ≤2 km · rival_pressure.json", "v": "%d (≥3)" % n2, "m": "measured"}]})
        # 3) AGRI — pressure vs tailwind
        ap = a.get("agri_pressure"); pyoy = a.get("price_yoy")
        pstress = a.get("price_stress") or 0.0
        dstress = a.get("drought_stress") or 0.0
        inten = a.get("intensity") or 0.0
        pyoy_src = a.get("price_src") or "NABC/OAE"
        dom_crop = agri_crops[a["dom"]]["label"] if (a.get("dom", -1) >= 0 and a["dom"] < len(agri_crops)) else None
        if a.get("rubber_share", 0) >= 0.5:
            dom_crop = "rubber"
        if isinstance(ap, (int, float)) and ap >= 25:
            # agri_pressure = (0.6·price_stress + 0.4·drought)·intensity, and price_stress is
            # max(0, −price_yoy·3) — so a crop price that is UP contributes exactly ZERO to the score.
            # This line used to print that positive YoY inside "under pressure (…, price 10.8% + dry)",
            # which states the opposite of what the number means: it read as if a rising price were
            # causing the stress. Every branch over the threshold today is drought-only, so the
            # sentence now names the term that actually produced the index and says plainly when the
            # price is not part of it. Fixed 2026-08-02 during the Macro audit.
            p_part = 0.6 * pstress * inten
            d_part = 0.4 * dstress * inten
            agri_why = [{"s": "Agri-pressure index · branch_agri.json", "v": "%s (≥25)" % ap, "m": "est"}]
            if pyoy is not None:
                agri_why.append({"s": "%s price YoY · %s" % (dom_crop or "crop", pyoy_src),
                                 "v": "%+.1f%% (%s)" % (pyoy, "drag" if pstress > 0 else "not a drag"),
                                 "m": "measured"})
            if dstress > 40:
                agri_why.append({"s": "Drought stress · branch_agri.json", "v": "%s (>40)" % dstress, "m": "est"})
            if p_part >= d_part:
                cause = "falling crop prices (%s mix %+.1f%% YoY)%s" % (
                    dom_crop or "crop", pyoy if pyoy is not None else 0.0,
                    " on top of dry weather" if dstress > 40 else "")
            else:
                ra = a.get("rain_anom")
                cause = "dry weather%s" % ("" if ra is None else " (3-month rainfall %s%% of normal)" % ra)
                if pyoy is not None and pstress == 0:
                    cause += "; the %s price is %+.1f%% YoY and is NOT contributing" % (dom_crop or "crop", pyoy)
            recs.append({"k": "agri", "i": "🌾", "tone": "warn", "p": 80,
                         "t": "Agri stress: %s catchment, pressure index %s — driven by %s. Tighten agri exposure, monitor collections."
                              % (dom_crop or "farming", ap, cause), "w": agri_why})
        elif isinstance(pyoy, (int, float)) and pyoy >= 20 and (a.get("intensity") or 0) >= 0.3:
            recs.append({"k": "agri", "i": "🌾", "tone": "good", "p": 60,
                         "t": "Agri tailwind: %s prices %+d%% and rising — farm cash improving, expect agri arrears here to hold." % (dom_crop or "crop", round(pyoy)),
                         "w": [{"s": "%s price YoY · %s" % (dom_crop or "crop", pyoy_src), "v": "%+d%% (≥20)" % round(pyoy), "m": "measured"},
                               {"s": "Agri intensity · branch_agri.json", "v": "%.2f (≥0.30)" % (a.get("intensity") or 0), "m": "est"}]})
        # 4) COLLATERAL — pickup/vehicle base
        cs = v.get("collateral_score"); ps = v.get("pickup_share")
        if isinstance(cs, (int, float)) and cs >= col_hi:
            col_why = [{"s": "Collateral score · branch_vehicles.json", "v": "%s (≥ p70 = %s)" % (cs, round(col_hi)), "m": "est"}]
            if ps is not None:
                col_why.append({"s": "Pickup share · branch_vehicles.json", "v": "%s%%" % ps, "m": "est"})
            recs.append({"k": "collateral", "i": "🚙", "tone": "good", "p": 70,
                         # Risk read, not a product push (see CLAUDE.md — the product makes no
                         # grow/expand/product-lead calls): a deep local vehicle market is what a
                         # repossession is sold into, so it is a recovery-value statement.
                         "t": "Prime collateral: high vehicle density (score %s, pickups %s%%) — deep local resale market, stronger recovery if a title is enforced." % (cs, ps),
                         "w": col_why})
        # 5) BORROWER BASE — dominant occupation
        if wf_rows and wf_buckets and i < len(wf_rows):
            dom = wf_rows[i].get("dom", -1)
            if dom is not None and 0 <= dom < len(wf_buckets):
                lab = wf_buckets[dom]["label"] if isinstance(wf_buckets[dom], dict) else wf_buckets[dom]
                mix = wf_rows[i].get("mix") or []
                share = mix[dom] if dom < len(mix) else None
                base_val = ("%s (%.0f%% of local workforce)" % (lab, share)) if isinstance(share, (int, float)) else lab
                recs.append({"k": "base", "i": "👥", "tone": "info", "p": 40,
                             "t": "Borrower base: mostly %s — size affordability and collections around that income pattern." % lab.lower(),
                             "w": [{"s": "Dominant occupation · branch_workforce.json", "v": base_val, "m": "est"}]})
        if macro_rec:
            recs.append(dict(macro_rec))

        recs.sort(key=lambda r: -r["p"])
        out.append({"recs": recs[:REC_MAX]})

    return {
        "meta": {
            "title": "Per-branch action recommendations (acquire · defend · agri · collateral · base)",
            "generated_by": "pipeline/build_branch_recommendations.py",
            "label": "ESTIMATED synthesis over the per-branch layers — a triage prompt, not a credit decision.",
            "evidence": "Every rec carries a 'w' array — the exact source layer · field · value (and measured/est provenance) that triggered its rule. Deterministic (network-free); no model in the loop, so the numbers are auditable, not generated.",
            "kinds": ["acquire", "defend", "agri", "collateral", "base", "macro"],
            "rec_max": REC_MAX,
            "branches_fingerprint": branches_fingerprint(items),
            "n_branches": n,
            "n_with_recs": sum(1 for x in out if x["recs"]),
        },
        "branches": out,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_branch_recommendations.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_branch_recommendations.py --check: drifted — re-run the builder.")
        print("build_branch_recommendations.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    from collections import Counter
    kinds = Counter(r["k"] for x in obj["branches"] for r in x["recs"])
    print("wrote %s (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024))
    print("  %d/%d branches have recommendations" % (obj["meta"]["n_with_recs"], obj["meta"]["n_branches"]))
    print("  by kind:", dict(kinds))


if __name__ == "__main__":
    main()
