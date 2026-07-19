#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_regional_outlook.py — the Overview's ANALYTICAL NARRATIVE, rolled up from the branch layers.

The Overview page answers, in order: (1) what is the current situation, (2) what factors are
hitting the economy and each segment, (3) what is the regional impact, (4) what is the
recommendation by region, and (5) what is the nationwide recommendation.

Everything here is a DETERMINISTIC aggregation of layers already shown per branch — so the
regional/national recommendations are provably the SAME per-branch recs rolled up, not a fresh
opinion. Sources:
  branch_recommendations.json (per-branch ranked recs · index-aligned) · branches.json (region ·
  province · opportunity) · branch_agri.json (agri pressure) · branch_workforce.json (borrower base)
  · macro_indicators.json (national leverage/rates) · meta.json (commodity board).

  python3 build_regional_outlook.py
  python3 build_regional_outlook.py --check
"""
import argparse, json, os, sys
from collections import Counter, defaultdict
from fingerprint import branches_fingerprint
from regionmap import canonical

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "platform", "data")
OUT = os.path.join(D, "regional_outlook.json")

# region display names (keys come from regionmap.REGION / branches.json 'r')
REGION_NAME = {"Isan": "Northeast · Isan", "North": "North", "South": "South",
               "East": "East · Eastern Seaboard", "Central&BKK": "Central & Bangkok"}
REGION_ORDER = ["Central&BKK", "Isan", "East", "North", "South"]


def _load(f):
    p = os.path.join(D, f)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def _rows(doc):
    if not doc:
        return None
    return doc.get("branches") if isinstance(doc, dict) else doc


def _pct(n, tot):
    return round(100.0 * n / tot) if tot else 0


# rank of rec kinds → (icon, tone, sentence template with (count, pct))
def _region_actions(t, tot):
    """Ranked regional actions from the per-branch rec tallies t (kind→count)."""
    cand = []
    if t.get("acquire"):
        cand.append((t["acquire"], {"i": "📈", "tone": "good", "k": "acquire",
            "t": "Expand — %d branches (%d%%) sit on prime white-space with thin competition; lead the region's acquisition here." % (t["acquire"], _pct(t["acquire"], tot))}))
    if t.get("defend"):
        cand.append((t["defend"], {"i": "⚔️", "tone": "warn", "k": "defend",
            "t": "Defend the book — %d branches (%d%%) face 3+ rival branches within 2 km; hold share on service and turnaround." % (t["defend"], _pct(t["defend"], tot))}))
    if t.get("agri_stress"):
        cand.append((t["agri_stress"], {"i": "🌾", "tone": "warn", "k": "agri_stress",
            "t": "De-risk agri — %d branches (%d%%) sit in stressed crop catchments; tighten agri exposure and watch collections." % (t["agri_stress"], _pct(t["agri_stress"], tot))}))
    if t.get("agri_tail"):
        cand.append((t["agri_tail"], {"i": "🌿", "tone": "good", "k": "agri_tail",
            "t": "Grow farm lending — %d branches (%d%%) enjoy a crop-price tailwind; collections favourable, room to lend." % (t["agri_tail"], _pct(t["agri_tail"], tot))}))
    if t.get("collateral"):
        cand.append((t["collateral"], {"i": "🚙", "tone": "good", "k": "collateral",
            "t": "Push vehicle-title — %d branches (%d%%) have prime collateral density; lead with vehicle-title products." % (t["collateral"], _pct(t["collateral"], tot))}))
    cand.sort(key=lambda x: -x[0])
    return [c[1] for c in cand]


# single dominant action for a province (icon · kind · short label), from its rec tally
def _top_action(t, tot):
    acts = _region_actions(t, tot)
    if not acts:
        return None
    a = acts[0]
    short = {"acquire": "Expand", "defend": "Defend", "agri_stress": "De-risk agri",
             "agri_tail": "Grow farm lending", "collateral": "Push vehicle-title"}
    return {"i": a["i"], "k": a["k"], "tone": a["tone"], "label": short.get(a["k"], a["k"])}


def build():
    branches = _load("branches.json")
    items = branches if isinstance(branches, list) else branches.get("items", branches)
    n = len(items)
    recs = _rows(_load("branch_recommendations.json"))
    agri = _rows(_load("branch_agri.json"))
    wf = _load("branch_workforce.json")
    wf_rows = wf.get("branches") if wf else None
    wf_buckets = wf.get("buckets") if wf else None
    macro = (_load("macro_indicators.json") or {}).get("indicators", {})
    meta = _load("meta.json") or {}
    board = meta.get("board", [])
    veh = _rows(_load("branch_vehicles.json"))          # per-branch collateral score / vehicle-shop density (est/OSM)
    rival = _rows(_load("rival_pressure.json"))          # per-branch rival branches ≤2/5 km (measured)
    agri_crops = (_load("branch_agri.json") or {}).get("meta", {}).get("crops", [])
    # MEASURED DLT registered-vehicle stock per province (justifies "prime collateral density")
    pidx = _load("provinces/index.json") or []
    dlt = {}
    for p in pidx:
        dlt[p.get("th")] = p
        c = canonical(p.get("th") or "")
        if c:
            dlt.setdefault(c, p)

    # per-branch rec-kind flags → region & province tallies
    def kinds_of(i):
        e = recs[i] if recs and i < len(recs) else None
        got = set()
        for r in (e.get("recs") if e else []) or []:
            k = r.get("k")
            if k == "agri":
                got.add("agri_stress" if r.get("tone") == "warn" else "agri_tail")
            elif k in ("acquire", "defend", "collateral"):
                got.add(k)
        return got

    reg_tally = defaultdict(Counter)
    reg_branches = defaultdict(list)
    reg_base = defaultdict(Counter)
    prov_tally = defaultdict(Counter)
    prov_meta = {}     # v -> {r, n}
    prov_stress = defaultdict(list)
    prov_opp = defaultdict(list)
    prov_coll = defaultdict(list)      # branch collateral_score (est composite)
    prov_vshop = defaultdict(list)     # vehicle/moto shops ≤10km (OSM, measured)
    prov_pyoy = defaultdict(list)      # crop price YoY (measured)
    prov_riv2 = defaultdict(list)      # rival branches ≤2km (measured)
    prov_riv5 = defaultdict(list)      # rival branches ≤5km (measured)
    prov_crop = defaultdict(Counter)   # dominant crop label per province
    reg_coll = defaultdict(list)       # region-level collateral score

    def dom_crop_label(i):
        a = agri[i] if agri and i < len(agri) else {}
        if a.get("rubber_share", 0) >= 0.5:
            return "rubber"
        d = a.get("dom", -1)
        return agri_crops[d]["label"] if (isinstance(d, int) and 0 <= d < len(agri_crops)) else None

    for i, b in enumerate(items):
        r = b.get("r"); v = b.get("v")
        ks = kinds_of(i)
        reg_tally[r].update(ks); reg_tally[r]["n"] += 1
        reg_branches[r].append(i)
        prov_tally[(r, v)].update(ks); prov_tally[(r, v)]["n"] += 1
        pm = prov_meta.setdefault(v, {"r": r, "n": 0}); pm["n"] += 1
        # dominant borrower base
        if wf_rows and wf_buckets and i < len(wf_rows):
            dom = wf_rows[i].get("dom", -1)
            if isinstance(dom, int) and 0 <= dom < len(wf_buckets):
                lab = wf_buckets[dom]["label"] if isinstance(wf_buckets[dom], dict) else wf_buckets[dom]
                reg_base[r][lab] += 1
        # stress / opportunity for province drill
        ap = (agri[i].get("agri_pressure") if agri and i < len(agri) else None)
        if isinstance(ap, (int, float)):
            prov_stress[v].append(ap)
        o = b.get("o")
        if isinstance(o, (int, float)):
            prov_opp[v].append(o)
        # collateral / vehicle-shop density (justifies "prime collateral density")
        vv = veh[i] if veh and i < len(veh) else {}
        cs = vv.get("collateral_score")
        if isinstance(cs, (int, float)):
            prov_coll[v].append(cs); reg_coll[r].append(cs)
        ne = vv.get("n_est")
        if isinstance(ne, (int, float)):
            prov_vshop[v].append(ne)
        # rival pressure (measured)
        rv = rival[i] if rival and i < len(rival) else {}
        if isinstance(rv.get("n2"), (int, float)):
            prov_riv2[v].append(rv["n2"])
        if isinstance(rv.get("n5"), (int, float)):
            prov_riv5[v].append(rv["n5"])
        # crop price + dominant crop
        py = (agri[i].get("price_yoy") if agri and i < len(agri) else None)
        if isinstance(py, (int, float)):
            prov_pyoy[v].append(py)
        dc = dom_crop_label(i)
        if dc:
            prov_crop[v][dc] += 1

    # ---- per-region blocks ----
    regions = []
    for r in REGION_ORDER:
        if r not in reg_tally:
            continue
        t = reg_tally[r]; tot = t["n"]
        base = reg_base[r].most_common(1)
        base_lab = base[0][0] if base else None
        base_share = _pct(base[0][1], tot) if base else 0
        # province rollups within region
        provs = [v for v, m in prov_meta.items() if m["r"] == r]
        stressed = sorted(
            ({"v": v, "score": round(sum(prov_stress[v]) / len(prov_stress[v])), "n": prov_meta[v]["n"]}
             for v in provs if prov_stress.get(v)),
            key=lambda x: -x["score"])[:5]
        oppy = sorted(
            ({"v": v, "opp": round(sum(prov_opp[v]) / len(prov_opp[v]), 1), "n": prov_meta[v]["n"]}
             for v in provs if prov_opp.get(v)),
            key=lambda x: -x["opp"])[:5]
        # full per-province drill within the region (every province, biggest book first)
        def _avg(lst, d=0):
            return round(sum(lst) / len(lst), d) if lst else None
        prov_list = []
        for v in provs:
            pt = prov_tally[(r, v)]; ptot = pt["n"]
            d = dlt.get(v) or dlt.get(canonical(v)) or {}
            tot_veh = d.get("vehicles") or 0
            share = lambda k: (round(100 * (d.get(k) or 0) / tot_veh) if tot_veh else None)
            top_crop = prov_crop[v].most_common(1)
            metrics = {
                # collateral (what justifies "prime collateral density")
                "coll_score": _avg(prov_coll[v]),                       # ESTIMATED composite 0-100
                "veh_shops": _avg(prov_vshop[v]),                       # MEASURED — vehicle/moto shops ≤10km (OSM), avg per branch
                "dlt_vehicles": tot_veh or None,                        # MEASURED — DLT registered vehicle stock
                "pickup_pct": share("pickup"), "car_pct": share("car"), # MEASURED — DLT mix
                "moto_pct": share("moto"), "ev_pct": share("ev"),
                # demand / risk
                "rivals2": _avg(prov_riv2[v], 1), "rivals5": _avg(prov_riv5[v], 1),   # MEASURED
                "price_yoy": _avg(prov_pyoy[v]),                        # MEASURED (NABC/OAE)
                "dom_crop": top_crop[0][0] if top_crop else None,
            }
            prov_list.append({
                "v": v, "slug": d.get("slug"), "n": ptot,
                "tallies": {k: pt.get(k, 0) for k in ("acquire", "defend", "agri_stress", "agri_tail", "collateral")},
                "stress": round(sum(prov_stress[v]) / len(prov_stress[v])) if prov_stress.get(v) else None,
                "opp": round(sum(prov_opp[v]) / len(prov_opp[v]), 1) if prov_opp.get(v) else None,
                "action": _top_action(pt, ptot),
                "metrics": metrics,
            })
        prov_list.sort(key=lambda p: -p["n"])
        situation = "%d branches%s. %d in stressed crop catchments, %d flagged prime white-space, %d besieged by rivals." % (
            tot, " · mostly %s borrowers (%d%%)" % (base_lab.lower(), base_share) if base_lab else "",
            t.get("agri_stress", 0), t.get("acquire", 0), t.get("defend", 0))
        regions.append({
            "r": r, "name": REGION_NAME.get(r, r), "n": tot,
            "base": base_lab, "base_share": base_share,
            "tallies": {k: t.get(k, 0) for k in ("acquire", "defend", "agri_stress", "agri_tail", "collateral")},
            "situation": situation,
            "recommendation": _region_actions(t, tot),
            "top_stressed": stressed,
            "top_opportunity": oppy,
            "collateral": {
                "avg_score": round(sum(reg_coll[r]) / len(reg_coll[r])) if reg_coll[r] else None,
                "dlt_vehicles": sum((dlt.get(v, {}).get("vehicles") or 0) for v in provs) or None,
            },
            "n_provinces": len(prov_list),
            "provinces": prov_list,
        })

    # ---- national situation (macro) ----
    def macro_card(key, label, good_when_falling=True):
        m = macro.get(key)
        if not m:
            return None
        yc = m.get("yoy_change")
        d, tone = "", "info"
        if yc is not None:
            falling = yc < 0
            tone = ("good" if falling else "warn") if good_when_falling else ("warn" if falling else "good")
            d = "%s%g pp YoY%s" % ("▼" if falling else "▲", abs(yc),
                                   " · deleveraging" if (falling and good_when_falling) else "")
        return {"k": label, "v": "%s%s" % (m.get("value"), m.get("unit", "").replace("% of GDP", "%").replace("THB/USD", "")),
                "d": d, "tone": tone, "src": ("%s %s" % (m.get("source", ""), m.get("period", ""))).strip()}

    situation = [c for c in [
        macro_card("household_debt_gdp", "Household debt", True),
        macro_card("policy_rate", "Policy rate", True),
        macro_card("cpi_inflation", "Inflation", True),
        macro_card("usd_thb", "USD/THB", True),
    ] if c]

    # ---- factors (commodity board movers + rate) ----
    # AutoX lends against VEHICLE TITLES, not gold — gold/pawn collateral is NOT relevant, so the
    # Collateral segment (gold) is excluded from the borrower-facing factors.
    factors = []
    for b in sorted(board, key=lambda x: -abs(x.get("yoy") or 0)):
        y = b.get("yoy")
        seg = b.get("seg", "")
        if y is None or abs(y) < 8 or seg == "Collateral":
            continue
        up = y > 0
        # crop/livestock/fisheries price up = borrower income tailwind (eases PD)
        factors.append({"lab": b.get("lab"), "yoy": y, "seg": seg, "reg": b.get("reg"),
                        "note": b.get("note"), "tone": "good" if up else "warn",
                        "hits": "%s household income %s" % (seg.lower() or "farm", "↑" if up else "↓")})
    factors = factors[:8]

    # ---- nationwide recommendation (sum of regional tallies) ----
    nat = Counter()
    for r in regions:
        for k, v in r["tallies"].items():
            nat[k] += v
    nat_actions = _region_actions(nat, n)
    hh = macro.get("household_debt_gdp") or {}
    backdrop = ""
    if hh.get("yoy_change") is not None:
        backdrop = ("Deleveraging backdrop (household debt %s%% and falling) eases borrower risk across the existing book. "
                    % hh.get("value")) if hh["yoy_change"] < 0 else \
                   ("Rising household leverage (%s%% of GDP) argues for caution on new exposure. " % hh.get("value"))
    top_reg = lambda kind: max(regions, key=lambda x: x["tallies"].get(kind, 0))["name"] if regions else "—"
    # Risk lens on the network we already run — NO branch open/expand recommendations (see CLAUDE.md).
    # Priority triad: competitive risk (defend the most rival-pressed branches) + portfolio (product
    # lead where collateral is deepest, de-risk the agri-stressed tail).
    headline = backdrop + "Priority: defend the branches under heaviest rival pressure (most in %s), lead with vehicle-title products where collateral density is high (most in %s), and de-risk agri-stressed branches (most in %s)." % (
        top_reg("defend"), top_reg("collateral"), top_reg("agri_stress"))

    return {
        "meta": {
            "title": "Regional & national outlook — situation · factors · regional impact · recommendation",
            "generated_by": "pipeline/build_regional_outlook.py",
            "label": "Deterministic rollup of the per-branch recommendation layer — the SAME recs aggregated by region/nation, not a fresh opinion. Inputs measured/estimated as labelled in their own layers.",
            "branches_fingerprint": branches_fingerprint(items),
            "n_branches": n,
            "updated": meta.get("updated"),
        },
        "national": {
            "situation": situation,
            "factors": factors,
            "recommendation": nat_actions,
            "headline": headline,
            "tallies": dict(nat),
        },
        "regions": regions,
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
            sys.exit("build_regional_outlook.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_regional_outlook.py --check: drifted — re-run the builder.")
        print("build_regional_outlook.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024))
    print("  regions: %d · national actions: %d" % (len(obj["regions"]), len(obj["national"]["recommendation"])))
    for r in obj["regions"]:
        print("  %-22s n=%-4d top: %s" % (r["name"], r["n"], (r["recommendation"][0]["k"] if r["recommendation"] else "—")))


if __name__ == "__main__":
    main()
