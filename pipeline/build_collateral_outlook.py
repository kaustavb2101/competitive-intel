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
  - used_vehicle_value.json  BoT UVPI used-vehicle price index (2015=100), separate car and
                          truck(=รถกระบะ pickup) series. MEASURED / NATIONAL. Its trailing YoY is
                          the ACTUAL resale-price direction of the car/pickup title collateral —
                          the resale value AutoX recovers on a repossessed vehicle. Added
                          2026-08-03: previously the vehicle leg ASSUMED a direction from fleet
                          composition alone with no price evidence; this grounds it in the measured
                          index that was already committed to the repo.
  - vehicles_by_province.json  DLT registered-vehicle stock per province -> motorcycle share of
                          the fleet (moto / total). MEASURED DLT. Used as the proxy for how
                          moto-title-heavy a province's pledgeable collateral base is (UVPI does
                          NOT cover motorcycles, so this stays a structural exposure proxy for the
                          motorcycle-title slice specifically).
  - branches.json         per-branch collateral segment score 'c', aggregated to a province mean.
                          ESTIMATED (derive.py segment scoring). Tells us how collateral-reliant
                          AutoX's book is in that province.

PER PROVINCE we emit the raw signals + a transparent directional note. We do NOT fabricate
a recovery rate; if a signal is absent for a province we omit it and say so in the note.

OUTLOOK direction (documented, plain — see meta.formula):
  gold_term      = clamp(gold_yoy / GOLD_SCALE, -1, 1)   national gold tailwind, +1 = strong firming
  veh_price_term = clamp(used_veh_yoy / VEH_SCALE, -1, 1)  MEASURED national used-car/pickup price
                                                          direction, +1 = resale value rising (firming)
  moto_term      = clamp((moto_title_share - MOTO_MID) / MOTO_SPAN, -1, 1)
                                                          +1 = moto-title-heavy (structural depreciation
                                                          exposure — the slice UVPI cannot price)
  outlook   = round(W_GOLD*gold_term + W_VEH*veh_price_term - W_MOTO*moto_term, 4)  in roughly [-1, +1]
              POSITIVE = recovery value firming, NEGATIVE = softening.
  The gold:vehicle weight balance is held at the prior 60:40; within the 40, the MEASURED car/pickup
  price direction now leads (W_VEH) and the unmeasured motorcycle structural proxy is demoted (W_MOTO).
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
# MEASURED BoT UVPI used-vehicle price index (2015=100), committed under platform/data (a projected
# TMLI layer). Read from there like branches.json below — graceful/absent-safe.
UVPI = os.path.join(ROOT, "platform", "data", "used_vehicle_value.json")

# --- direction-scaling constants (see FORMULA in module docstring) ---
GOLD_SCALE = 60.0    # gold YoY %% that maps gold_term to +1.0 (board shows +62.7 -> ~1.0 firming)
VEH_SCALE = 15.0     # used-vehicle YoY %% that maps veh_price_term to +/-1.0. Used-vehicle indices
                     # move far less than gold, so a ~15% annual swing is already a full-scale move.
MOTO_MID = 0.50      # fleet moto-share considered "neutral"
MOTO_SPAN = 0.30     # +/- span around MOTO_MID that maps moto_term to +/-1 (0.20..0.80 fleet share)
# gold:vehicle balance held at the prior 60:40. Within the vehicle 0.40, the MEASURED car/pickup
# price direction now leads (0.25) and the unmeasured motorcycle structural proxy is demoted (0.15).
W_GOLD = 0.6         # gold tailwind weight (unchanged)
W_VEH = 0.25         # MEASURED used-car/pickup resale-price direction weight (BoT UVPI)
W_MOTO = 0.15        # motorcycle-title structural depreciation-exposure weight (demoted from 0.4)


def load(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return json.load(f)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _series_yoy(history):
    """Trailing YoY %% for a UVPI series: newest month vs the SAME month a year earlier.
    Deterministic (anchors on the newest period IN the data, never wall clock). Returns
    (yoy_pct, latest_period) or (None, latest_period/None) when the year-ago month is absent."""
    if not isinstance(history, list) or not history:
        return None, None
    by_period = {}
    for pt in history:
        p = pt.get("period")
        v = pt.get("value")
        if isinstance(p, str) and isinstance(v, (int, float)):
            by_period[p] = float(v)
    if not by_period:
        return None, None
    latest = history[-1].get("period")
    if not isinstance(latest, str) or "-" not in latest or latest not in by_period:
        return None, latest
    y, m = latest.split("-", 1)
    prior = "%d-%s" % (int(y) - 1, m)
    base = by_period.get(prior)
    if base is None or base == 0:
        return None, latest
    return round((by_period[latest] / base - 1.0) * 100.0, 2), latest


def used_vehicle_price():
    """MEASURED used-car/pickup resale-price direction from the BoT UVPI index (national).
    Returns a dict of car/pickup/blended trailing YoY %% + the period, or an absent marker.
    Blended = simple mean of the available car & pickup YoYs (UVPI's own two constituent series,
    equal-weighted — documented, no invented mix). None-safe: absent file -> absent marker."""
    try:
        with open(UVPI, encoding="utf-8") as f:
            d = json.load(f)
        series = d.get("series", {}) if isinstance(d, dict) else {}
    except Exception:
        return {"car_yoy": None, "pickup_yoy": None, "blended_yoy": None, "period": None}
    car_yoy, car_p = _series_yoy((series.get("car") or {}).get("history"))
    pk_yoy, pk_p = _series_yoy((series.get("truck") or {}).get("history"))  # UVPI 'truck' == รถกระบะ pickup
    avail = [x for x in (car_yoy, pk_yoy) if x is not None]
    blended = round(sum(avail) / len(avail), 2) if avail else None
    return {
        "car_yoy": car_yoy,
        "pickup_yoy": pk_yoy,
        "blended_yoy": blended,
        "period": car_p or pk_p,
    }


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

    # --- national used-vehicle price direction (MEASURED BoT UVPI; car/pickup resale value) ---
    # National, like gold: UVPI is a single national index, not a province series. + = resale
    # value rising (recovery firming); - = falling (softening). Absent file -> 0.0 (honest neutral).
    uvpi = used_vehicle_price()
    veh_yoy = uvpi["blended_yoy"]
    veh_price_term = clamp(veh_yoy / VEH_SCALE, -1.0, 1.0) if veh_yoy is not None else 0.0

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

        # outlook: gold tailwind + MEASURED used-vehicle price direction - moto structural drag.
        # POSITIVE = firming.
        outlook = round(W_GOLD * gold_term + W_VEH * veh_price_term - W_MOTO * moto_term, 4)

        # human note: lead with the direction, name which legs were present, flag missing signals.
        note = _note(gold_yoy, veh_yoy, moto_share, collateral_score, outlook)

        records.append({
            "province": prov,
            "region": region,
            "gold_yoy": gold_yoy,            # MEASURED/GLOBAL proxy (national, same for all)
            "used_veh_yoy": veh_yoy,         # MEASURED BoT UVPI car/pickup blended YoY (national)
            "moto_title_share": moto_share,  # MEASURED DLT (or null if absent)
            "collateral_score": collateral_score,  # ESTIMATED (or null if absent)
            "outlook": outlook,              # ESTIMATED directional read in ~[-1,+1]
            "outlook_note": note,
            "components": {
                "gold_term": round(gold_term, 4),
                "veh_price_term": round(veh_price_term, 4),
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
        "used_veh_yoy_car": uvpi["car_yoy"],        # MEASURED BoT UVPI (national)
        "used_veh_yoy_pickup": uvpi["pickup_yoy"],  # MEASURED BoT UVPI (national)
        "used_veh_yoy_blended": veh_yoy,            # MEASURED — car/pickup equal-weight mean
        "used_veh_price_period": uvpi["period"],    # newest period IN the UVPI data (not wall clock)
        "veh_price_term": round(veh_price_term, 4),
        "n_provinces": len(records),
        "n_with_moto_share": n_with_moto,
        "n_with_collateral_score": n_with_score,
        "n_softening": len(softening),
        "n_firming": len(firming),
        "exposure_weighted_outlook": nat_outlook,
        "most_at_risk_province": most_at_risk,
        "headline": _headline(gold_yoy, veh_yoy, uvpi["period"], nat_outlook, len(softening), len(records)),
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
            "used_veh_yoy": "MEASURED — BoT UVPI used-vehicle price index (2015=100), trailing YoY of "
                            "the car and truck(=รถกระบะ pickup) series, equal-weight mean. NATIONAL "
                            "(one national index, same for all provinces). The ACTUAL resale-price "
                            "direction of the car/pickup title collateral — negative = falling resale "
                            "value = softening vehicle-title recovery. Does NOT cover motorcycles.",
            "moto_title_share": "MEASURED — motorcycle share of the province DLT registered-vehicle "
                                "fleet (moto / total), from vehicles_by_province.json. Proxy for how "
                                "moto-title-heavy the pledgeable collateral base is. null when absent.",
            "collateral_score": "ESTIMATED — province mean of the per-branch collateral segment score "
                                "'c' (derive.py segment scoring). Tells you how collateral-reliant the "
                                "AutoX book is in that province. null when no branch carries it.",
            "outlook": "ESTIMATED — directional index in ~[-1,+1]. POSITIVE = recovery value firming, "
                       "NEGATIVE = softening. A composite of a MEASURED gold direction, a MEASURED "
                       "used-car/pickup resale-price direction (BoT UVPI), and a structural "
                       "motorcycle-exposure proxy, combined with the documented weights below. The "
                       "composite is ESTIMATED; its price legs are measured. NOT a recovery rate.",
        },
        "formula": {
            "gold_term": "clamp(gold_yoy / %g, -1, 1)" % GOLD_SCALE,
            "veh_price_term": "clamp(used_veh_yoy / %g, -1, 1)" % VEH_SCALE,
            "moto_term": "clamp((moto_title_share - %g) / %g, -1, 1)" % (MOTO_MID, MOTO_SPAN),
            "outlook": "round(%g*gold_term + %g*veh_price_term - %g*moto_term, 4)" % (W_GOLD, W_VEH, W_MOTO),
            "rationale": "Gold firming lifts pawn/gold-collateral recovery (tailwind, +). Used "
                         "car/pickup resale prices set the MEASURED direction of vehicle-title "
                         "recovery value (BoT UVPI; falling prices = drag, -). A province skewed to "
                         "motorcycle titles carries extra depreciation risk on the slice UVPI cannot "
                         "price (structural drag, -). The gold:vehicle weight balance is held at the "
                         "prior 60:40; within the 40, the measured price direction (W_VEH=%g) leads "
                         "and the unmeasured moto proxy (W_MOTO=%g) is demoted from 0.4. "
                         "collateral_score is shown alongside (not multiplied in) so the outlook "
                         "stays comparable across provinces while the reader can see actual exposure."
                         % (W_VEH, W_MOTO),
        },
        "provenance": {
            "commodity_board.json": "World Bank Pink Sheet GLOBAL Gold price, YoY %% — MEASURED/GLOBAL, "
                                    "a DIRECTION proxy for Thai gold-pawn collateral, not farm/shop-gate.",
            "used_vehicle_value.json": "BoT UVPI used-vehicle price index (2015=100), car + "
                                       "truck(=รถกระบะ pickup) series — MEASURED / NATIONAL. Trailing "
                                       "YoY = the actual resale-price direction of car/pickup title "
                                       "collateral. Anchored on the newest period in the data.",
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
            "used_veh_yoy is the BoT UVPI NATIONAL used-vehicle price index — one national number "
            "applied to every province (like gold), not a province-level resale quote. It prices "
            "cars and pickups (its two constituent series) but NOT motorcycles, so the motorcycle "
            "slice keeps its structural moto_title_share proxy instead of a measured price.",
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


def _note(gold_yoy, veh_yoy, moto_share, collateral_score, outlook):
    direction = _dir_word(outlook)
    parts = ["Collateral recovery value %s." % direction]
    if gold_yoy is not None:
        if gold_yoy > 0:
            parts.append("Gold +%.1f%% YoY firms pawn/gold-collateral value (global proxy)." % gold_yoy)
        else:
            parts.append("Gold %.1f%% YoY (global proxy) does not support pawn-collateral value." % gold_yoy)
    else:
        parts.append("Gold board signal absent.")
    if veh_yoy is not None:
        if veh_yoy < 0:
            parts.append("Used car/pickup resale prices %.1f%% YoY (BoT UVPI, measured) — "
                         "a real drag on vehicle-title recovery value." % veh_yoy)
        else:
            parts.append("Used car/pickup resale prices +%.1f%% YoY (BoT UVPI, measured) — "
                         "vehicle-title recovery value holding." % veh_yoy)
    else:
        parts.append("BoT UVPI used-vehicle price signal absent.")
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


def _headline(gold_yoy, veh_yoy, veh_period, nat_outlook, n_soft, n_total):
    g = ("Gold +%.1f%% YoY (global proxy) is the dominant collateral tailwind"
         % gold_yoy) if gold_yoy is not None else "Gold board signal absent"
    if veh_yoy is not None:
        per = (" to %s" % veh_period) if veh_period else ""
        v = ("; used car/pickup resale prices %+.1f%% YoY%s (BoT UVPI, measured) pull the vehicle "
             "side the other way" % (veh_yoy, per))
    else:
        v = ""
    if nat_outlook is None:
        return "%s%s; no collateral-weighted national outlook (no province scores)." % (g, v)
    dirn = _dir_word(nat_outlook)
    return ("%s%s. Exposure-weighted national collateral outlook is %s (%.3f); "
            "%d of %d provinces are softening."
            % (g, v, dirn, nat_outlook, n_soft, n_total))


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
