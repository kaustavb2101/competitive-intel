#!/usr/bin/env python3
"""
build_cluster_brief.py — one-line plain-language MACRO read for each branch's customer cluster.

THE QUESTION THIS ANSWERS (objective #1 — what macro factors move each branch's customers)
------------------------------------------------------------------------------------------
When Kaustav opens a branch he wants ONE honest sentence: "who are these customers, and which
macro moves help or hurt their ability to repay?" macro_exposure.json gives the SCORED version
(per-factor 0..100 severity vectors); THIS layer is the PLAIN-LANGUAGE companion — a single
templated sentence per branch, e.g.

    "Rubber-belt farm cluster; rubber prices +32% YoY support incomes,
     gold collateral +26% YoY lifts recovery value"
    "Sugar-exposed / Isan farm cluster; rice prices +17% YoY support incomes,
     gold collateral +26% YoY lifts recovery value; regional cane belt:
     world sugar -13% YoY a repayment headwind; drought elevated (rain 71% of normal)"

Every sentence is ASSEMBLED FROM MEASURED NUMBERS already in the repo — no free-form prose, no
new numbers. The wording is templated; only the numbers and the cluster archetype vary.

WHAT IT COMBINES (all already committed in platform/data / source-data)
-----------------------------------------------------------------------
  branch_occupations.json  MEASURED Overture occupation mix per branch (index-aligned): used to
                           tint the cluster label (factory-worker vs tourism vs merchant).
  branches.json a/m/c/r    a = agri_pd, m = merchant_demand, c = collateral_density (ESTIMATED
                           segment scores), r = region (MEASURED): a drives the farm-vs-town
                           archetype, c gates the gold-collateral clause, r drives the regional
                           board watch.
  meta.json .board         MEASURED World Bank Pink Sheet commodity YoY % (GLOBAL prices — a
                           DIRECTION proxy, NOT Thai farm-gate): rice/rubber/palm/sugar/gold.
  crop_stress.json         MEASURED province crop_mix (dominant crop by planting rai) + MEASURED-
                           proxy drought (rain % of normal): the dominant crop selects which board
                           price is the income clause; drought adds a stress note.

MEASURED vs ESTIMATED (the data-mandate — stated field-by-field in meta)
------------------------------------------------------------------------
  MEASURED    every NUMBER in every sentence — commodity YoY % (board), occupation counts
              (Overture), the dominant crop (OAE planting area), drought (rain anomaly).
  ESTIMATED   the COMPOSITION only — (a) the archetype cutoffs (which agri/occupation score makes
              a "farm" vs "town" cluster), (b) which board price is the income driver for a cluster,
              (c) the plain-language verbs ("support incomes" / "pressures repayment"). No number
              is invented; the editorial layer is only how the measured numbers are phrased.

DETERMINISTIC + NETWORK-FREE: no network, no wall clock (vintage read from meta.json 'updated').
Byte-exact reproducible -> carries --check (the QA gate runs it). Inputs may be absent in a
stripped sandbox: build() returns None, --check skip-passes, a plain run exits non-zero with a
clear message (mirrors build_lead_sites.py / build_catchment_poi.py).

Usage:
  python3 build_cluster_brief.py            # write platform/data/cluster_brief.json
  python3 build_cluster_brief.py --check    # verify byte-for-byte reproduce
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
BRANCHES = os.path.join(DATA, "branches.json")
OCC = os.path.join(DATA, "branch_occupations.json")
META = os.path.join(DATA, "meta.json")
CROP = os.path.join(DATA, "crop_stress.json")
OUT = os.path.join(DATA, "cluster_brief.json")

sys.path.insert(0, HERE)
from lib.fingerprint import branches_fingerprint  # shared index-alignment stamp

# ── EDITORIAL cutoffs (the ESTIMATED composition layer — documented in meta.thresholds) ──
AGRI_HI = 60          # branches.a (agri_pd) at/above -> a genuine farm-belt cluster
AGRI_MID = 35         # a in [MID,HI) -> a mixed farm-&-town cluster (still crop-relevant)
DEP_RELEVANT = 0.30   # province crop_dependence >= this AND a >= AGRI_FLOOR -> crop clause relevant
AGRI_FLOOR = 20       # per-branch agri floor for the dependence path: a city-centre branch with
                      #   near-zero own-catchment agri (a < FLOOR) gets NO farm-income clause even
                      #   in a crop-heavy province — its customers are urban, not farmers.
HOSP_SHARE = 0.15     # Overture hospitality share -> tourism cluster
FAC_SHARE = 0.03      # Overture factory share -> factory-worker cluster
COLL_STRONG = 75      # branches.c (collateral_density) -> "strong gold-collateral book"
COLL_MID = 60         # c in [MID,STRONG) -> ordinary gold clause; below -> "thinner book"
MOVE_SUPPORT = 5.0    # board YoY % at/above -> "support incomes"
MOVE_PRESSURE = -5.0  # board YoY % at/below -> "pressures repayment"
DROUGHT_HI = 0.60     # crop_stress drought (0..1) at/above -> "drought elevated" note
                      #   (mirrors crop_stress double_stress drought_floor)
REGIONAL_STRESS = -10.0  # a board crop this negative, tagged to the branch's region, fires a
                         #   regional risk watch on agri/mixed clusters (objective #1 = risk)

# Occupation-bucket indices (branch_occupations.json buckets order — asserted at build time).
OCC_FACTORY = 0
OCC_HOSPITALITY = 4

# crop_stress crop names -> commodity_board labels (Oil palm is "Palm oil" on the board).
CROP_TO_BOARD = {"Rice": "Rice", "Rubber": "Rubber", "Oil palm": "Palm oil"}
# display name used in the sentence for each board crop
CROP_DISPLAY = {"Rice": "rice", "Rubber": "rubber", "Palm oil": "palm oil", "Sugar": "sugar",
                "Maize": "maize"}
# cluster-label stem for an agri belt, keyed by the dominant crop's board label
BELT_STEM = {"Rice": "Rice", "Rubber": "Rubber", "Palm oil": "Oil-palm"}

# board region-tag tokens -> branches.json region values (for the regional board watch).
REGION_TOKENS = {"isan": "Isan", "ne": "Isan", "n": "North", "north": "North",
                 "c": "Central&BKK", "central": "Central&BKK", "s": "South", "south": "South",
                 "e": "East", "east": "East"}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _pct(y):
    """Signed integer percent, truncated toward zero (matches the board convention:
    32.4 -> '+32', 26.1 -> '+26', -13.5 -> '-13'). The full measured value is kept
    verbatim in the structured crop_yoy / gold_yoy fields for audit."""
    iy = int(y)  # truncation toward zero
    return ("+%d" % iy) if iy >= 0 else ("%d" % iy)


def _board_map(board):
    """label -> full measured YoY % (float)."""
    out = {}
    for row in board:
        lab, yoy = row.get("lab"), row.get("yoy")
        if isinstance(lab, str) and isinstance(yoy, (int, float)):
            out[lab] = float(yoy)
    return out


def _board_regions(board):
    """board label -> set of branch-region values its 'reg' tag maps to (for the regional watch)."""
    out = {}
    for row in board:
        lab, reg = row.get("lab"), row.get("reg")
        regs = set()
        if isinstance(reg, str):
            for tok in reg.replace("·", " ").replace("/", " ").split():
                r = REGION_TOKENS.get(tok.strip().lower())
                if r:
                    regs.add(r)
        out[lab] = regs
    return out


def _province_index(crop):
    """Thai province name -> {dominant board-crop label or None, drought or None, rain_pct or None}."""
    idx = {}
    for p in crop.get("provinces", []):
        th = p.get("th")
        if not th:
            continue
        dom = None
        mix = p.get("crop_mix") or []
        if mix:
            top = max(mix, key=lambda c: c.get("share", 0))
            dom = CROP_TO_BOARD.get(top.get("crop"))
        comp = p.get("components") or {}
        idx[th] = {
            "crop": dom,
            "drought": p.get("drought"),
            "rain_pct": comp.get("rain_pct_of_normal"),
            "dependence": p.get("crop_dependence"),
        }
    return idx


def _income_clause(crop_label, yoy):
    """Templated income read from a dominant crop's MEASURED board YoY."""
    disp = CROP_DISPLAY.get(crop_label, (crop_label or "farm").lower())
    if yoy >= MOVE_SUPPORT:
        return "%s prices %s%% YoY support incomes" % (disp, _pct(yoy))
    if yoy <= MOVE_PRESSURE:
        return "world %s %s%% YoY pressures repayment" % (disp, _pct(yoy))
    return "%s prices flat YoY (neutral for incomes)" % disp


def _gold_clause(c, gold_yoy):
    """Templated collateral-recovery read; strength gated on collateral_density c (the density input)."""
    if gold_yoy >= MOVE_SUPPORT:
        verb = "lifts recovery value"
    elif gold_yoy <= MOVE_PRESSURE:
        verb = "erodes recovery value"
    else:
        verb = "steady for recovery value"
    p = _pct(gold_yoy)
    if c >= COLL_STRONG:
        return "strong gold-collateral book, %s%% YoY %s" % (p, verb)
    if c >= COLL_MID:
        return "gold collateral %s%% YoY %s" % (p, verb)
    return "thinner collateral book; gold %s%% YoY %s" % (p, verb)


def build():
    for pth in (BRANCHES, OCC, META, CROP):
        if not os.path.exists(pth):
            return None
    branches = _load(BRANCHES)
    occ = _load(OCC)
    meta = _load(META)
    crop = _load(CROP)

    occ_recs = occ.get("branches") or []
    if len(occ_recs) != len(branches):
        # index-aligned contract broken — refuse to emit a misaligned layer.
        raise SystemExit("branch_occupations length %d != branches length %d — re-run build_occupations.py"
                         % (len(occ_recs), len(branches)))
    # taxonomy guard: our bucket indices must still point at factory / hospitality.
    bkeys = [b.get("key") for b in occ.get("buckets", [])]
    if not (len(bkeys) > OCC_HOSPITALITY and bkeys[OCC_FACTORY] == "factory"
            and bkeys[OCC_HOSPITALITY] == "hospitality"):
        raise SystemExit("branch_occupations bucket order drifted (factory@0 / hospitality@4) — "
                         "update OCC_* indices")

    board = meta.get("board") or []
    vintage = meta.get("updated")
    bmap = _board_map(board)
    bregs = _board_regions(board)
    prov_idx = _province_index(crop)

    gold_yoy = bmap.get("Gold")
    if gold_yoy is None:
        raise SystemExit("commodity_board has no 'Gold' row — cannot build the collateral clause")

    # regional stress watch candidates: board crops materially negative, with a region tag and a
    # display name (sugar/maize/rice/rubber/palm). Deterministic order = board order.
    regional_candidates = [row.get("lab") for row in board
                           if isinstance(row.get("yoy"), (int, float))
                           and row["yoy"] <= REGIONAL_STRESS
                           and bregs.get(row.get("lab"))
                           and row.get("lab") in CROP_DISPLAY]

    briefs = []
    tally = {}
    for br, orc in zip(branches, occ_recs):
        a = br.get("a", 0)
        c = br.get("c", 0)
        region = br.get("r")
        prov = br.get("v")
        pi = prov_idx.get(prov, {})
        dom_crop = pi.get("crop")           # board label or None
        dependence = pi.get("dependence")
        drought = pi.get("drought")
        rain_pct = pi.get("rain_pct")

        # occupation shares (MEASURED) for the label tint
        t = orc.get("t") or 0
        ovec = orc.get("o") or []
        fac_share = (ovec[OCC_FACTORY] / t) if (t and len(ovec) > OCC_FACTORY) else 0.0
        hosp_share = (ovec[OCC_HOSPITALITY] / t) if (t and len(ovec) > OCC_HOSPITALITY) else 0.0

        crop_relevant = (a >= AGRI_MID) or (
            a >= AGRI_FLOOR and isinstance(dependence, (int, float)) and dependence >= DEP_RELEVANT)
        drivers = ["branch_occupations.o", "branches.a", "branches.c", "board:Gold"]

        # ── cluster label ────────────────────────────────────────────────
        if a >= AGRI_HI:
            if dom_crop and dom_crop in BELT_STEM:
                sign = bmap.get(dom_crop, 0.0)
                stem = BELT_STEM[dom_crop]
                label = "%s-%s farm cluster" % (stem, "exposed" if sign < 0 else "belt")
            else:
                label = "Farm cluster"
        elif hosp_share >= HOSP_SHARE:
            label = "Tourism & hospitality cluster"
        elif fac_share >= FAC_SHARE:
            label = "Factory-worker cluster"
        elif a >= AGRI_MID:
            label = "Mixed farm & town cluster"
        else:
            label = "Town merchant & service cluster"
        tally[label] = tally.get(label, 0) + 1

        # ── primary economics clauses (income + collateral), joined by ", " ──
        primary = []
        crop_yoy = None
        if crop_relevant and dom_crop and dom_crop in bmap:
            crop_yoy = bmap[dom_crop]
            primary.append(_income_clause(dom_crop, crop_yoy))
            drivers += ["crop_stress.crop_mix", "board:%s" % dom_crop]
        include_gold = (c >= COLL_MID) or (not crop_relevant)
        if include_gold:
            primary.append(_gold_clause(c, gold_yoy))
        if not primary:
            # crop-relevant but c<MID and no crop match: still give the collateral lever.
            primary.append(_gold_clause(c, gold_yoy))

        # ── stress / context notes, joined by "; " after the primary clause ──
        extra = []
        flags = {"drought": False, "regional_watch": None}
        # regional board watch (ESTIMATED regional attribution, clearly labelled) — risk only.
        if crop_relevant:
            watch = next((lab for lab in regional_candidates
                          if region in bregs.get(lab, set()) and lab != dom_crop), None)
            if watch:
                extra.append("regional %s belt: world %s %s%% YoY a repayment headwind"
                             % (CROP_DISPLAY.get(watch, watch.lower()),
                                CROP_DISPLAY.get(watch, watch.lower()), _pct(bmap[watch])))
                flags["regional_watch"] = watch
                drivers.append("board:%s(regional)" % watch)
        # drought note — only meaningful for clusters that actually farm.
        if crop_relevant and isinstance(drought, (int, float)) and drought >= DROUGHT_HI:
            if isinstance(rain_pct, (int, float)):
                extra.append("drought elevated (rain %d%% of normal)" % int(round(rain_pct)))
            else:
                extra.append("drought elevated")
            flags["drought"] = True
            drivers.append("crop_stress.drought")
        # honesty tag for pure-urban clusters (no farm income read attached).
        if not crop_relevant:
            extra.append("limited farm exposure")

        line = "%s; %s" % (label, ", ".join(primary))
        if extra:
            line += "; " + "; ".join(extra)

        briefs.append({
            "line": line,
            "cluster": label,
            "crop": dom_crop if (crop_relevant and dom_crop) else None,
            "crop_yoy": crop_yoy,        # full MEASURED board YoY (or null)
            "gold_yoy": gold_yoy,        # full MEASURED board YoY
            "flags": flags,
            "drivers": drivers,
        })

    board_used = {lab: bmap[lab] for lab in ("Gold", "Rice", "Rubber", "Palm oil", "Sugar", "Maize")
                  if lab in bmap}

    metaout = {
        "title": "Per-branch one-line MACRO read of each customer cluster (objective #1)",
        "generated_by": "pipeline/build_cluster_brief.py",
        "deterministic": True,
        "network_free": True,
        "label": "ESTIMATED-EDITORIAL COMPOSITION over MEASURED inputs. Every NUMBER in every "
                 "sentence is MEASURED (commodity YoY %, occupation counts, dominant crop, drought "
                 "rain anomaly); only the COMPOSITION is estimated — the archetype cutoffs, the "
                 "choice of which board price is a cluster's income driver, and the plain-language "
                 "verbs. No number is fabricated; the sentence is templated from the actual values.",
        "provenance": {
            "commodity_yoy": "MEASURED — World Bank Pink Sheet GLOBAL commodity YoY %% via "
                             "meta.json .board (rice/rubber/palm/sugar/gold). A DIRECTION proxy, "
                             "NOT Thai farm-gate.",
            "occupation_mix": "MEASURED — Overture Maps Places occupation shares per branch "
                              "(branch_occupations.json, index-aligned). Used only to tint the "
                              "cluster label (factory-worker / tourism / merchant).",
            "segment_scores": "ESTIMATED — branches.json a (agri_pd), m (merchant_demand), c "
                              "(collateral_density) are the app's own segment scores; a selects the "
                              "farm-vs-town archetype and c gates the gold-collateral clause.",
            "region": "MEASURED — branches.json r; drives the regional board-crop watch.",
            "dominant_crop": "MEASURED — crop_stress.json crop_mix (OAE planting-area share, rai). "
                             "Selects which board price is the income clause.",
            "drought": "MEASURED PROXY — crop_stress.json drought (rain %% of normal, from branch "
                       "rain_3mo_anom). Adds a stress note on farm clusters only.",
            "composition": "ESTIMATED-EDITORIAL — the thresholds, driver selection and wording "
                           "below. See meta.thresholds.",
            "vintage": "board/drought vintage from meta.json 'updated' = %s." % (vintage or "unknown"),
        },
        "inputs_used": [
            "platform/data/branch_occupations.json (.branches[i].o — MEASURED occupation mix)",
            "platform/data/branches.json (a/m/c segment scores + r region + v province)",
            "platform/data/meta.json (.board commodity YoY %% + .updated vintage)",
            "platform/data/crop_stress.json (.provinces crop_mix dominant crop + drought)",
        ],
        "index_note": "briefs[] is INDEX-ALIGNED to platform/data/branches.json (entry i <-> branch i), "
                      "identical to branch_occupations.json / macro_exposure.json / lead_sites.json.",
        "fields": {
            "line": "ESTIMATED-EDITORIAL composition — the one-line brief, templated from measured numbers.",
            "cluster": "ESTIMATED — archetype label from the a-score + occupation-share cutoffs.",
            "crop": "MEASURED — dominant province crop (board label) driving the income clause, or null "
                    "when the cluster is not crop-relevant.",
            "crop_yoy": "MEASURED — full board YoY %% used for the income clause (null when no crop clause).",
            "gold_yoy": "MEASURED — full board Gold YoY %% used for the collateral clause.",
            "flags": "which context notes fired: drought (bool), regional_watch (board crop label or null).",
            "drivers": "audit trail — the exact input fields that composed this branch's line.",
        },
        "thresholds": {
            "agri_hi": AGRI_HI, "agri_mid": AGRI_MID, "dependence_relevant": DEP_RELEVANT,
            "agri_floor": AGRI_FLOOR,
            "hospitality_share": HOSP_SHARE, "factory_share": FAC_SHARE,
            "collateral_strong": COLL_STRONG, "collateral_mid": COLL_MID,
            "move_support": MOVE_SUPPORT, "move_pressure": MOVE_PRESSURE,
            "drought_elevated": DROUGHT_HI, "regional_stress": REGIONAL_STRESS,
            "note": "cutoffs are the ESTIMATED-editorial layer; a>=agri_hi -> farm belt, "
                    "a in [agri_mid,agri_hi) -> mixed, hospitality/factory shares tint the town "
                    "label, c bands set the gold-clause strength, board YoY bands pick the verb.",
        },
        "board_used": board_used,
        "board_note": "commodity YoY %% displayed in the sentence are TRUNCATED to integer toward "
                      "zero (32.4 -> +32); board_used and crop_yoy/gold_yoy keep the full measured value.",
        "gaps": [
            "Sugar & maize have NO per-province planting share in crop_stress.json, so they cannot "
            "be a branch's MEASURED dominant crop — they surface only as an ESTIMATED regional watch "
            "(keyed on the board 'reg' tag) on agri/mixed clusters, clearly labelled 'regional'.",
            "Commodity YoY is a GLOBAL World Bank Pink Sheet direction proxy, NOT Thai farm-gate; "
            "the sentence says 'support/pressure' (direction), never a Thai price level.",
            "The archetype cutoffs are editorial; two branches either side of a cutoff read "
            "differently — the structured crop/crop_yoy/gold_yoy fields expose the underlying numbers.",
        ],
        "n_branches": len(briefs),
        "cluster_tally": dict(sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))),
        "branches_fingerprint": branches_fingerprint(branches),
    }
    return {"meta": metaout, "briefs": briefs}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: branches.json / branch_occupations.json / meta.json / crop_stress.json "
                  "absent — cluster_brief not checkable (optional layer)")
            return 0
        print("missing input: needs platform/data/branches.json + branch_occupations.json + "
              "meta.json + crop_stress.json.")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        print("OK: cluster_brief.json reproduces (%d branches)" % obj["meta"]["n_branches"])
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d briefs -> platform/data/cluster_brief.json (%.0f KB)"
          % (m["n_branches"], len(text.encode("utf-8")) / 1024))
    print("  clusters: %s" % m["cluster_tally"])
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="per-branch one-line plain-language macro cluster brief")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
