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
    factors = []
    for b in sorted(board, key=lambda x: -abs(x.get("yoy") or 0)):
        y = b.get("yoy")
        if y is None or abs(y) < 8:
            continue
        up = y > 0
        # crop/livestock/fisheries price up = income tailwind (supports borrowers); gold up = collateral value up
        seg = b.get("seg", "")
        if seg == "Collateral":
            tone = "good" if up else "warn"
            hits = "pawn / gold-collateral value %s" % ("↑" if up else "↓")
        else:
            tone = "good" if up else "warn"
            hits = "%s household income %s" % (seg.lower() or "farm", "↑" if up else "↓")
        factors.append({"lab": b.get("lab"), "yoy": y, "seg": seg, "reg": b.get("reg"),
                        "note": b.get("note"), "tone": tone, "hits": hits})
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
        backdrop = ("Deleveraging backdrop (household debt %s%% and falling) eases borrower risk — a window to grow selectively. "
                    % hh.get("value")) if hh["yoy_change"] < 0 else \
                   ("Rising household leverage (%s%% of GDP) argues for caution on new exposure. " % hh.get("value"))
    top_reg = lambda kind: max(regions, key=lambda x: x["tallies"].get(kind, 0))["name"] if regions else "—"
    headline = backdrop + "Priority: expand where white-space is thin-competition (most in %s), de-risk agri-stressed branches (most in %s), and push gold-collateral products while gold is bid." % (
        top_reg("acquire"), top_reg("agri_stress"))

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
