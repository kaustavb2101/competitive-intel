#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_contested_mindshare.py — COMPETITIVE RISK (objective #2): the ground × screen JOIN.

Two independent per-province reads already exist and nothing crosses them:
  * peer_province.json  — the PHYSICAL branch field: which operator has the most branches
                          (leader), the top rival brand and its share of the local title-lender
                          field, AutoX's rank. MEASURED (real located-branch census).
  * search_demand.json  — the MINDSHARE field: each brand's share-of-search, AutoX's share and
                          search rank, the best rival by share-of-search. ESTIMATED (a Thai
                          search-term demand proxy).

The sharpest obj-#2 question neither answers alone: on the network we ALREADY run, in which
provinces is AutoX BOTH physically outnumbered on the ground AND out-searched on the screen — and,
the double jeopardy, by the SAME rival brand winning both? A rival that leads the branch field and
the search field in the same province is where AutoX's share is hardest to defend: it is neither a
distribution problem alone (that a denser field would answer) nor an attention problem alone (that a
campaign would answer), but both at once, and driven by one named competitor.

  in : platform/data/peer_province.json     ground field per province (MEASURED branch census rollup)
       platform/data/search_demand.json     search field per province (ESTIMATED demand proxy)
  out: platform/data/contested_mindshare.json   per-province double-jeopardy join + plain verdict

TWO AXES, EACH HONESTLY LABELLED:
  ground  — MEASURED. leader / top rival brand / that rival's share of the local title-lender field,
            from the real located-branch census (peer_province.json, itself a gated rollup of
            rival_density.json). "Outnumbered" = the leading operator in the province is a rival, not
            AutoX.
  screen  — ESTIMATED. share-of-search per brand from a Thai search-term demand proxy
            (search_demand.json). "Out-searched" = AutoX's share-of-search is below the best rival's.

The combined layer is therefore MIXED, classified ESTIMATED (its screen axis is estimated). It makes
NO open / close / expand recommendation — a risk lens on the footprint we already run. It invents no
number: every figure is read verbatim from one of the two committed, --check-gated inputs.

Deterministic + network-free; every float rounded so the output is byte-stable. `--check`
byte-compares. Both inputs are always-committed (no SKIP path).

  python3 build_contested_mindshare.py
  python3 build_contested_mindshare.py --check
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "platform", "data")
PEER = os.path.join(DATA, "peer_province.json")
SEARCH = os.path.join(DATA, "search_demand.json")
OUT = os.path.join(DATA, "contested_mindshare.json")


def _classify(outnumbered, out_searched, same_rival):
    """Which of the four competitive postures this province sits in."""
    if outnumbered and out_searched:
        return "double-jeopardy" if same_rival else "split-pressure"
    if outnumbered:
        return "ground-led"        # rival denser, but AutoX holds share-of-search
    if out_searched:
        return "screen-led"        # AutoX holds the branch field, but is out-searched
    return "defended"              # AutoX leads both axes


def _verdict(row):
    """Plain-language, concrete read of the two axes for one province (no abstract index)."""
    cls = row["class"]
    gb, gs = row["ground_top_rival"], row["ground_top_rival_share"]
    sb, ss = row["screen_top_rival"], row["screen_top_rival_share"]
    ax = row["autox_share"]
    if cls == "double-jeopardy":
        return ("Double jeopardy: %s leads BOTH the branch field (%.0f%% of local title-lenders) "
                "and search (%.0f%% share-of-search vs AutoX %.0f%%) — one rival, both fronts."
                % (gb, gs * 100, ss * 100, ax * 100))
    if cls == "split-pressure":
        return ("Split pressure: outnumbered on the ground by %s (%.0f%% of the field) and "
                "out-searched by %s (%.0f%% vs AutoX %.0f%%) — two different rivals."
                % (gb, gs * 100, sb, ss * 100, ax * 100))
    if cls == "ground-led":
        return ("Ground pressure: %s leads the branch field (%.0f%%), but AutoX holds share-of-search "
                "(%.0f%%) — a distribution gap, not an attention one." % (gb, gs * 100, ax * 100))
    if cls == "screen-led":
        return ("Attention pressure: AutoX holds the branch field, but %s is out-searching us "
                "(%.0f%% vs AutoX %.0f%%) — an attention gap, not a distribution one."
                % (sb, ss * 100, ax * 100))
    return "Defended: AutoX leads both the branch field and search demand in this province."


def build():
    peer = json.load(open(PEER, encoding="utf-8"))
    search = json.load(open(SEARCH, encoding="utf-8"))
    search_by = {p.get("th"): p for p in search.get("provinces", []) if p.get("th")}

    rows = []
    unmatched = []
    for p in peer.get("provinces", []):
        name = p.get("province_th")
        s = search_by.get(name)
        if s is None:
            unmatched.append(name)
            continue
        if not p.get("autox"):            # only provinces where AutoX already runs branches
            continue

        leader = p.get("leader")
        ground_top = p.get("rival_top_brand")
        ground_share = p.get("rival_top_share")           # MEASURED — rival share of local field
        best_rival = s.get("best_rival") or {}
        screen_top = best_rival.get("brand")
        screen_share = best_rival.get("share")            # ESTIMATED — rival share-of-search
        autox_share = s.get("autox_share")                # ESTIMATED — AutoX share-of-search

        outnumbered = bool(leader) and leader != "AutoX"
        out_searched = (autox_share is not None and screen_share is not None
                        and autox_share < screen_share)
        same_rival = bool(ground_top) and ground_top == screen_top
        cls = _classify(outnumbered, out_searched, same_rival)

        # Double-jeopardy index — only meaningful when the SAME rival leads both axes; both terms are
        # 0..1 shares so the mean is honestly bounded. MEASURED ground share + ESTIMATED screen share
        # → the index inherits the ESTIMATED label. null for every other posture.
        dj_index = None
        if cls == "double-jeopardy":
            dj_index = round((ground_share + screen_share) / 2.0, 3)

        row = {
            "province_th": name,
            "province_en": s.get("en"),
            "slug": s.get("slug"),
            "region": p.get("region"),
            "autox_branches": p.get("autox"),
            "rival_branches": p.get("rivals"),
            "ratio": p.get("ratio"),
            "autox_rank": p.get("autox_rank"),
            # ground axis (MEASURED)
            "ground_leader": leader,
            "ground_top_rival": ground_top,
            "ground_top_rival_share": round(ground_share, 3) if ground_share is not None else None,
            "outnumbered": outnumbered,
            # screen axis (ESTIMATED)
            "screen_top_rival": screen_top,
            "screen_top_rival_share": round(screen_share, 3) if screen_share is not None else None,
            "autox_share": round(autox_share, 3) if autox_share is not None else None,
            "autox_sos_rank": s.get("autox_sos_rank"),
            "out_searched": out_searched,
            # join
            "same_rival": same_rival,
            "class": cls,
            "dj_index": dj_index,
        }
        row["verdict"] = _verdict(row)
        rows.append(row)

    # Order: double-jeopardy first (by index desc), then split-pressure (by rival:AutoX ratio desc),
    # then the rest, then province name — a fully deterministic sort.
    _class_order = {"double-jeopardy": 0, "split-pressure": 1, "ground-led": 2,
                    "screen-led": 3, "defended": 4}
    rows.sort(key=lambda x: (_class_order.get(x["class"], 9),
                             -(x["dj_index"] or 0),
                             -(x["ratio"] or 0),
                             x["province_th"]))

    dj = [x for x in rows if x["class"] == "double-jeopardy"]
    split = [x for x in rows if x["class"] == "split-pressure"]

    # Which rival brand is the double-jeopardy driver most often, and where it bites hardest.
    dj_by_brand = {}
    for x in dj:
        dj_by_brand[x["ground_top_rival"]] = dj_by_brand.get(x["ground_top_rival"], 0) + 1
    dj_by_brand = dict(sorted(dj_by_brand.items(), key=lambda kv: (-kv[1], kv[0])))

    headline = ""
    if dj:
        top = dj[0]
        driver = next(iter(dj_by_brand)) if dj_by_brand else None
        driver_n = dj_by_brand.get(driver, 0) if driver else 0
        headline = ("%d of %d AutoX provinces are double jeopardy — the same rival leads both the "
                    "branch field and search demand" % (len(dj), len(rows)))
        if driver:
            headline += (" (%s drives %d of them)" % (driver, driver_n))
        headline += (". Hardest to defend: %s, where %s holds %.0f%% of the local field and %.0f%% "
                     "of search vs AutoX's %.0f%%."
                     % (top["province_th"], top["ground_top_rival"],
                        top["ground_top_rival_share"] * 100, top["screen_top_rival_share"] * 100,
                        top["autox_share"] * 100))

    return {
        "meta": {
            "title": "Contested mindshare — where AutoX is outnumbered on the ground AND out-searched "
                     "on the screen by the same rival (obj #2)",
            "generated_by": "pipeline/build_contested_mindshare.py",
            "label": "MIXED, classified ESTIMATED — the GROUND axis (which operator leads the branch "
                     "field and that rival's share of the local title-lender field) is MEASURED (real "
                     "located-branch census, via peer_province.json); the SCREEN axis (share-of-search) "
                     "is ESTIMATED (a Thai search-term demand proxy, via search_demand.json). The "
                     "double-jeopardy index (dj_index) mixes the two and so inherits the ESTIMATED "
                     "label. NOT an AutoX-internal figure. Makes NO open/close/expand recommendation — "
                     "a risk lens on the footprint we already run.",
            "source": "join of platform/data/peer_province.json (ground, MEASURED) + "
                      "platform/data/search_demand.json (screen, ESTIMATED) — both committed, "
                      "deterministic, --check-gated. Join key: Thai province name (77/77 exact match).",
            "ground_axis": "MEASURED — peer_province.json leader / rival_top_brand / rival_top_share "
                           "(share of the located title-lender census in the province).",
            "screen_axis": "ESTIMATED — search_demand.json best_rival share-of-search vs autox_share.",
            "definitions": {
                "outnumbered": "the leading operator in the province (most branches) is a rival, not AutoX",
                "out_searched": "AutoX's share-of-search is below the best rival's",
                "double-jeopardy": "outnumbered AND out-searched by the SAME rival brand",
                "split-pressure": "outnumbered AND out-searched, but by two different rivals",
                "ground-led": "outnumbered on the ground, but AutoX holds share-of-search",
                "screen-led": "AutoX leads the branch field, but is out-searched",
                "defended": "AutoX leads both axes",
                "dj_index": "mean of the rival's ground share and screen share (0..1); double-jeopardy "
                            "provinces only; ESTIMATED",
            },
            "n_provinces": len(rows),
            "n_double_jeopardy": len(dj),
            "n_split_pressure": len(split),
            "dj_by_brand": dj_by_brand,
            "search_vintage": (search.get("meta") or {}).get("pulled_at_utc"),
        },
        "headline": headline,
        "provinces": rows,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    for f, who in ((PEER, "build_peer_province.py"), (SEARCH, "build_search_demand.py")):
        if not os.path.exists(f):
            sys.exit("build_contested_mindshare.py: %s missing — run %s" % (f, who))
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_contested_mindshare.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_contested_mindshare.py --check: drifted — re-run the builder.")
        print("build_contested_mindshare.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    print("wrote %s — %d provinces (%d double-jeopardy, %d split-pressure)"
          % (OUT, m["n_provinces"], m["n_double_jeopardy"], m["n_split_pressure"]))
    print("  dj_by_brand:", m["dj_by_brand"])
    for x in obj["provinces"][:12]:
        if x["class"] != "double-jeopardy":
            break
        print("  %-14s %-10s ground=%.0f%% screen=%.0f%% (AutoX %.0f%%) dj=%.3f"
              % (x["province_th"], x["ground_top_rival"], x["ground_top_rival_share"] * 100,
                 x["screen_top_rival_share"] * 100, x["autox_share"] * 100, x["dj_index"]))
    print("  headline:", obj["headline"])


if __name__ == "__main__":
    main()
