#!/usr/bin/env python3
"""
build_collateral_outlook.py — PORTFOLIO RISK (objective #1): per-province COLLATERAL-VALUE OUTLOOK.

Title-loan recovery value hinges on what the collateral is worth at the moment of default:
  - GOLD / pawn collateral firming  -> recovery value holds up (good for the book).
  - USED-MOTORCYCLE title collateral -> the highest-loss title collateral; a province whose
    pledged stock skews to motorcycles is more exposed to falling used-vehicle resale value.

This builder is a DIRECTIONAL, ESTIMATED read — NOT a measured recovery rate. It combines ONLY
signals already committed to the repo (no new external numbers, no invented prices):
  - commodity_board.json  Gold YoY %% (the MEASURED/GLOBAL board move; PROXY for Thai gold-pawn
                          collateral direction). Applied NATIONALLY — gold is a global price.
  - vehicles_by_province.json  DLT registered-vehicle stock per province -> motorcycle share of
                          the fleet (moto / total). MEASURED DLT. Used as the proxy for how
                          moto-title-heavy a province's pledgeable collateral base is.
  - branches.json         per-branch collateral segment score 'c', aggregated to a province mean.
                          ESTIMATED (derive.py segment scoring). Tells us how collateral-reliant
                          AutoX's book is in that province.

PER PROVINCE we emit the three raw signals + a transparent directional note. We do NOT fabricate
a recovery rate; if a signal is absent for a province we omit it and say so in the note.

OUTLOOK direction (documented, plain — see meta.formula):
  gold_term = clamp(gold_yoy / GOLD_SCALE, -1, 1)        national gold tailwind, +1 = strong firming
  moto_term = clamp((moto_title_share - MOTO_MID) / MOTO_SPAN, -1, 1)
                                                          +1 = moto-title-heavy (more depreciation risk)
  outlook   = round(W_GOLD*gold_term - W_MOTO*moto_term, 4)   in roughly [-1, +1]
              POSITIVE = recovery value firming (gold tailwind dominates),
              NEGATIVE = recovery value softening (moto-title depreciation dominates).
  The outlook is scaled in the NOTE by the province collateral_score so the reader knows whether
  AutoX is actually collateral-exposed there — but the numeric outlook stays comparable across
  provinces (score shown alongside, not multiplied in, to keep the direction honest).

Run:
  python3 build_collateral_outlook.py          # write platform/data/collateral_outlook.json
  python3 build_collateral_outlook.py --check   # re-run, byte-compare against the committed file
"""
import json
import os
import sys
import argparse
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data")
OUT = os.path.join(ROOT, "platform", "data", "collateral_outlook.json")

# --- direction-scaling constants (see FORMULA in module docstring) ---
GOLD_SCALE = 60.0    # gold YoY %% that maps gold_term to +1.0 (board shows +62.7 -> ~1.0 firming)
MOTO_MID = 0.50      # fleet moto-share considered "neutral"
MOTO_SPAN = 0.30     # +/- span around MOTO_MID that maps moto_term to +/-1 (0.20..0.80 fleet share)
W_GOLD = 0.6         # gold tailwind weight
W_MOTO = 0.4         # moto-title depreciation weight


def load(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return json.load(f)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def build():
    # --- inputs (graceful: each may be absent; we note what we actually had) ---
    board = None
    vehicles = None
    branches = None
    try:
        board = load("commodity_board.json")
    except Exception:
        board = None
    try:
        vehicles = load("vehicles_by_province.json")
    except Exception:
        vehicles = None
    # branches.json is the DERIVED app projection (province th in 'v', region in 'r', collateral 'c')
    bpath = os.path.join(ROOT, "platform", "data", "branches.json")
    if os.path.exists(bpath):
        with open(bpath, encoding="utf-8") as f:
            branches = json.load(f)

    # --- gold YoY: national MEASURED/GLOBAL proxy from the commodity board ---
    gold_yoy = None
    if isinstance(board, list):
        for row in board:
            if row.get("lab") == "Gold":
                try:
                    gold_yoy = float(row["yoy"])
                except (KeyError, TypeError, ValueError):
                    gold_yoy = None
                break

    # --- per-province moto-title share (MEASURED DLT) ---
    veh_prov = {}
    if isinstance(vehicles, dict):
        veh_prov = vehicles.get("provinces", {}) or {}

    # --- per-province collateral score (ESTIMATED) + region, from branches ---
    prov_c = defaultdict(list)
    prov_region = {}
    if isinstance(branches, list):
        for r in branches:
            p = r.get("v")
            if not p:
                continue
            prov_region.setdefault(p, r.get("r"))
            c = r.get("c")
            if c is not None:
                try:
                    prov_c[p].append(float(c))
                except (TypeError, ValueError):
                    pass

    # If we have no branch network at all there is nothing to key provinces on -> honest absent-state.
    if not prov_region:
        meta = {
            "title": "Per-province collateral-value outlook (portfolio risk, objective #1)",
            "generated_by": "pipeline/build_collateral_outlook.py",
            "deterministic": True,
            "network_free": True,
            "absent": True,
            "label": "ESTIMATED directional outlook (no recovery rate)",
            "note": "branches.json absent — no province network to key the outlook on. "
                    "Run derive.py first, then re-run this builder.",
            "n_provinces": 0,
        }
        return {"meta": meta, "national": None, "provinces": []}

    # --- national gold direction term (applied to every province; gold is a global price) ---
    if gold_yoy is not None:
        gold_term = clamp(gold_yoy / GOLD_SCALE, -1.0, 1.0)
    else:
        gold_term = 0.0

    records = []
    n_with_moto = 0
    n_with_score = 0
    for prov in sorted(prov_region.keys()):
        region = prov_region.get(prov)

        # moto-title share (MEASURED DLT) — omit when absent
        moto_share = None
        v = veh_prov.get(prov)
        if isinstance(v, dict):
            total = v.get("total")
            moto = v.get("moto")
            if isinstance(total, (int, float)) and total and isinstance(moto, (int, float)):
                moto_share = round(float(moto) / float(total), 4)

        # collateral score (ESTIMATED) — province mean of branch 'c'
        cs = prov_c.get(prov, [])
        collateral_score = round(sum(cs) / len(cs), 1) if cs else None

        # --- direction terms ---
        if moto_share is not None:
            moto_term = clamp((moto_share - MOTO_MID) / MOTO_SPAN, -1.0, 1.0)
            n_with_moto += 1
        else:
            moto_term = 0.0
        if collateral_score is not None:
            n_with_score += 1

        # outlook: gold tailwind minus moto-title depreciation drag. POSITIVE = firming.
        outlook = round(W_GOLD * gold_term - W_MOTO * moto_term, 4)

        # human note: lead with the direction, name which legs were present, flag missing signals.
        note = _note(gold_yoy, moto_share, collateral_score, outlook)

        records.append({
            "province": prov,
            "region": region,
            "gold_yoy": gold_yoy,            # MEASURED/GLOBAL proxy (national, same for all)
            "moto_title_share": moto_share,  # MEASURED DLT (or null if absent)
            "collateral_score": collateral_score,  # ESTIMATED (or null if absent)
            "outlook": outlook,              # ESTIMATED directional read in ~[-1,+1]
            "outlook_note": note,
            "components": {
                "gold_term": round(gold_term, 4),
                "moto_term": round(moto_term, 4),
                "n_branches": len(cs),
            },
        })

    # sort most-AT-RISK first: lowest (most negative) outlook, then highest collateral exposure,
    # then province name for determinism.
    def _score_key(r):
        sc = r["collateral_score"] if r["collateral_score"] is not None else -1.0
        return (r["outlook"], -sc, r["province"])
    records.sort(key=_score_key)

    # --- national summary ---
    softening = [r for r in records if r["outlook"] < 0]
    firming = [r for r in records if r["outlook"] > 0]
    # exposure-weighted national outlook (weight by collateral_score where present; honest if none)
    wsum = 0.0
    wnum = 0.0
    for r in records:
        sc = r["collateral_score"]
        if sc is not None:
            wsum += sc
            wnum += sc * r["outlook"]
    nat_outlook = round(wnum / wsum, 4) if wsum > 0 else None
    most_at_risk = records[0]["province"] if records else None

    national = {
        "gold_yoy": gold_yoy,
        "n_provinces": len(records),
        "n_with_moto_share": n_with_moto,
        "n_with_collateral_score": n_with_score,
        "n_softening": len(softening),
        "n_firming": len(firming),
        "exposure_weighted_outlook": nat_outlook,
        "most_at_risk_province": most_at_risk,
        "headline": _headline(gold_yoy, nat_outlook, len(softening), len(records)),
    }

    meta = {
        "title": "Per-province collateral-value outlook (portfolio risk, objective #1)",
        "generated_by": "pipeline/build_collateral_outlook.py",
        "deterministic": True,
        "network_free": True,
        "label": "ESTIMATED directional outlook — NOT a measured recovery rate",
        "n_provinces": len(records),
        "sort": "most-at-risk-first by outlook (asc), then collateral exposure (desc)",
        "what_this_is": "A DIRECTIONAL, comparative read on whether title-loan collateral RECOVERY "
                        "value is firming or softening per province. It is an ESTIMATE built from the "
                        "signals below — it is NOT a measured loss-given-default or recovery rate, and "
                        "no price is invented. Use it to triage which provinces' collateral base is "
                        "trending the wrong way, not as a settlement value.",
        "fields": {
            "gold_yoy": "MEASURED / GLOBAL PROXY — Gold YoY %% from the commodity board (World Bank "
                        "Pink Sheet GLOBAL gold). Applied NATIONALLY (one global price). A DIRECTION "
                        "proxy for Thai gold-pawn collateral value, not a Thai gold-shop quote.",
            "moto_title_share": "MEASURED — motorcycle share of the province DLT registered-vehicle "
                                "fleet (moto / total), from vehicles_by_province.json. Proxy for how "
                                "moto-title-heavy the pledgeable collateral base is. null when absent.",
            "collateral_score": "ESTIMATED — province mean of the per-branch collateral segment score "
                                "'c' (derive.py segment scoring). Tells you how collateral-reliant the "
                                "AutoX book is in that province. null when no branch carries it.",
            "outlook": "ESTIMATED — directional index in ~[-1,+1]. POSITIVE = recovery value firming "
                       "(gold tailwind dominates), NEGATIVE = softening (moto-title depreciation drag "
                       "dominates). See meta.formula. NOT a recovery rate.",
        },
        "formula": {
            "gold_term": "clamp(gold_yoy / %g, -1, 1)" % GOLD_SCALE,
            "moto_term": "clamp((moto_title_share - %g) / %g, -1, 1)" % (MOTO_MID, MOTO_SPAN),
            "outlook": "round(%g*gold_term - %g*moto_term, 4)" % (W_GOLD, W_MOTO),
            "rationale": "Gold firming lifts pawn/gold-collateral recovery (tailwind, +). A province "
                         "skewed to motorcycle titles carries more used-vehicle depreciation risk, the "
                         "highest-loss title collateral (drag, -). collateral_score is shown alongside "
                         "(not multiplied in) so the outlook stays comparable across provinces while "
                         "the reader can see actual collateral exposure.",
        },
        "provenance": {
            "commodity_board.json": "World Bank Pink Sheet GLOBAL Gold price, YoY %% — MEASURED/GLOBAL, "
                                    "a DIRECTION proxy for Thai gold-pawn collateral, not farm/shop-gate.",
            "vehicles_by_province.json": "DLT registered-vehicle stock by province (data.go.th) — "
                                         "MEASURED. moto/total = motorcycle share of the fleet.",
            "branches.json": "per-branch collateral segment score 'c' (DERIVED by derive.py) — "
                             "ESTIMATED segment scoring, aggregated to a province mean.",
        },
        "caveats": [
            "outlook is an ESTIMATED direction, not a recovery rate or loss-given-default. Do not "
            "read it as a settlement value.",
            "gold_yoy is a GLOBAL board move applied to every province — it is not a province-level "
            "gold-shop price and it shifts every province's outlook by the same national constant.",
            "moto_title_share is the share of the ALL-VEHICLE fleet that is motorcycles, a proxy for "
            "the pledgeable collateral mix; it is not AutoX's actual pledged-collateral composition.",
            "collateral_score is an ESTIMATED segment score, shown for exposure context only; it is "
            "not multiplied into outlook, so a high-score province with a soft outlook is the worst "
            "combination to triage.",
            "Provinces missing a signal carry null for that field and say so in outlook_note; the "
            "outlook still computes from the signals that were present.",
        ],
    }

    return {"meta": meta, "national": national, "provinces": records}


def _dir_word(outlook):
    if outlook > 0.05:
        return "firming"
    if outlook < -0.05:
        return "softening"
    return "broadly flat"


def _note(gold_yoy, moto_share, collateral_score, outlook):
    direction = _dir_word(outlook)
    parts = ["Collateral recovery value %s." % direction]
    if gold_yoy is not None:
        if gold_yoy > 0:
            parts.append("Gold +%.1f%% YoY firms pawn/gold-collateral value (global proxy)." % gold_yoy)
        else:
            parts.append("Gold %.1f%% YoY (global proxy) does not support pawn-collateral value." % gold_yoy)
    else:
        parts.append("Gold board signal absent.")
    if moto_share is not None:
        parts.append("Motorcycles are %.0f%% of the DLT fleet (measured) — "
                     "%s used-bike depreciation exposure on title collateral."
                     % (100 * moto_share, "high" if moto_share >= 0.55 else
                        ("low" if moto_share <= 0.45 else "moderate")))
    else:
        parts.append("DLT moto-share absent for this province.")
    if collateral_score is not None:
        parts.append("Collateral segment score %.0f (estimated) sets the book's exposure here." % collateral_score)
    else:
        parts.append("No branch collateral score for this province.")
    return " ".join(parts)


def _headline(gold_yoy, nat_outlook, n_soft, n_total):
    g = ("Gold +%.1f%% YoY (global proxy) is the dominant collateral tailwind"
         % gold_yoy) if gold_yoy is not None else "Gold board signal absent"
    if nat_outlook is None:
        return "%s; no collateral-weighted national outlook (no province scores)." % g
    dirn = _dir_word(nat_outlook)
    return ("%s. Exposure-weighted national collateral outlook is %s (%.3f); "
            "%d of %d provinces are softening on used-motorcycle-title depreciation."
            % (g, dirn, nat_outlook, n_soft, n_total))


def dumps(obj):
    # deterministic: insertion key order, readable separators, ensure_ascii=False, trailing newline
    # — matching the other builders / meta.json convention.
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift")
    args = ap.parse_args()

    data = build()
    text = dumps(data)

    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d provinces)" %
                  (OUT, data["meta"]["n_provinces"]))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s (%d provinces, most-at-risk-first)" % (OUT, data["meta"]["n_provinces"]))
    nat = data.get("national") or {}
    print("  national: %s" % nat.get("headline"))
    for r in data["provinces"][:5]:
        print("  %-16s outlook=%+.4f moto=%s gold=%s c=%s" % (
            r["province"], r["outlook"], r["moto_title_share"], r["gold_yoy"], r["collateral_score"]))


if __name__ == "__main__":
    main()
