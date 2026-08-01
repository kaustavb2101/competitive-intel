#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_assist_radar_price.py — which crop, if its price turned, would put the most CURRENTLY-HEALTHY
farm accounts at risk (objective #1, proactive assistance).

  out: platform/data/assist_price_radar.json

  python3 build_assist_radar_price.py            # rebuild
  python3 build_assist_radar_price.py --check    # byte-exact reproduce (gate)

THE QUESTION THIS ANSWERS, AND THE ONE IT DOES NOT.
The existing assistance radar (tape_real.json -> assistance_radar) is DROUGHT-driven: it finds farm
borrowers already slipping in provinces with a rainfall deficit. That is a "who is hurting now" list.

This file is the other half — the PRICE side, and it is deliberately forward-looking. The honest
finding today is that no crop MAPPED HERE is falling: the five mapped farm-gate series are all up
year-on-year (cassava +57%, rubber +38%, palm +32%, rice +12%, maize +11%). So a naive "who is in a
falling sector" screen returns an empty list, and returning an empty list dressed up as insight
would be a lie by omission.

TWO CORRECTIONS TO WHAT THAT USED TO SAY (2026-08-01):
  · It read "every measured Thai farm-gate series is up", which was never true of the whole feed,
    only of the five crops this file maps. NABC publishes thirteen categories and SIX are DOWN —
    coconut -70.9%, pineapple -20.0%, pork -6.7%, white shrimp -4.3%, chicken -2.4%, eggs -1.7%.
    They are absent here because this file's exposure join needs crop_stress.json crop shares, which
    still carry only the original five crops. Wiring them is the next wave, not a silent omission.
  · It quoted "sugarcane +26%" as a current move. That number is the OAE crop_prices.json snapshot
    stamped BE 2562 = 2019 CE — seven years old. There is no current Thai cane price anywhere in
    this repo; cane registers with the OCSB, not DOAE or NABC.

What IS answerable, and is answered here, is the exposure question underneath it:

    For each crop — how many farm accounts that are CURRENT or only in the X bucket (pre-30-day)
    sit in provinces that depend on that crop for a meaningful share of their planted area?

That number is real today and does not depend on the price direction. It is the size of the book that
would need proactive contact IF that crop turned, and it ranks the crops by how much of the healthy
farm book rides on each. `tripped` — provinces where a depended-on crop is actually in price decline
— is the alarm on top of it, and it is EMPTY at this vintage. That is stated plainly in meta, not
hidden, so that when it stops being empty the change is visible rather than invented.

MEASURED vs ESTIMATED.
  * MEASURED: the account counts and outstanding balances (real loan tape, no-PII aggregates);
    the planted-area crop shares (OAE + DOAE registry); the farm-gate price YoY (NABC daily series).
  * ESTIMATED: nothing is modelled here. The only JUDGEMENT is the 15% dominance threshold below —
    how much of a province's planted area a crop must occupy before that province is called
    "dependent" on it. It is published in meta.trigger so any row can be re-derived by hand.
  * NOT A FORECAST. No price path is predicted. "If X turns" is a conditional, not a probability.

BUCKET ARITHMETIC. tape_real.json's agri_impact.by_province carries early_pct (X, pre-30), roll_pct
(30-89) and dpd90p_pct (90+). Current% is the remainder: 100 - early - roll - dpd90p. The
Current+X population is therefore n * (100 - roll - dpd90p) / 100. The bucket split is by ACCOUNT
COUNT; os_thb is the province's whole farm book, because the tape aggregate does not expose
outstanding split by bucket and inventing that split would be fabrication.

DETERMINISM. No wall clock. The vintage stamp is taken from the input files. Sorting is total
(value, then name) so ties cannot reorder between runs. Written with an explicit LF newline: this is
multi-line JSON, and build_provenance.py records os.path.getsize(), so a CRLF write from a Windows
laptop would silently inflate the recorded byte size and fail the gate on CI.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "platform", "data")
SRC = os.path.join(ROOT, "source-data")
OUT = os.path.join(DATA, "assist_price_radar.json")

TAPE = os.path.join(DATA, "tape_real.json")
CROPS = os.path.join(DATA, "crop_stress.json")
PRICES = os.path.join(SRC, "farmgate_prices.json")

# JUDGEMENT (the only one in this file). A crop has to cover this much of a province's planted area
# before the province is called dependent on it. 15% is low enough to catch a real secondary crop and
# high enough to exclude the long tail of trace plantings.
DOMINANT_SHARE = 0.15

# A price move inside this band is noise, not direction. Farm-gate series are daily national averages
# across a handful of quoting markets, so a couple of points either way is not a trend.
FLAT_BAND_PCT = 2.0

# crop_stress.json labels its crop mix in English; farmgate_prices.json keys its YoY in lowercase
# slugs. One map, so a rename on either side fails loudly instead of silently dropping a crop.
CROP_KEY = {
    "Rice": "rice",
    "Rubber": "rubber",
    "Cassava": "cassava",
    "Maize": "maize",
    "Oil palm": "oilpalm",
}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def direction(yoy):
    if yoy is None:
        return "unknown"
    if yoy < -FLAT_BAND_PCT:
        return "down"
    if yoy > FLAT_BAND_PCT:
        return "up"
    return "flat"


def build():
    for p in (TAPE, CROPS, PRICES):
        if not os.path.exists(p):
            return None, os.path.relpath(p, ROOT)

    tape = load(TAPE)
    crop_stress = load(CROPS)
    prices = load(PRICES)

    yoy = prices.get("crop_yoy") or {}
    price_vintage = (prices.get("meta") or {}).get("vintage")

    by_prov = (tape.get("agri_impact") or {}).get("by_province") or []
    if not by_prov:
        return None, "platform/data/tape_real.json:agri_impact.by_province"

    cs = crop_stress.get("provinces") or {}
    cs = cs if isinstance(cs, dict) else {r.get("th"): r for r in cs}

    # Provinces the drought radar already flags — carried through so the UI can say "this province is
    # ALSO in the drought list" rather than presenting two unrelated tables of the same names.
    drought = {r.get("province") for r in (tape.get("assistance_radar") or [])}

    rows = []
    unmapped_crops = set()
    for rec in by_prov:
        th = rec.get("province")
        n = rec.get("n") or 0
        if not th or not n:
            continue
        early = rec.get("early_pct") or 0.0
        roll = rec.get("roll_pct") or 0.0
        d90 = rec.get("dpd90p_pct") or 0.0
        current_pct = round(max(0.0, 100.0 - early - roll - d90), 2)
        n_current = int(round(n * current_pct / 100.0))
        n_early = int(round(n * early / 100.0))

        mix = []
        prov_crop = (cs.get(th) or {}).get("crop_mix") or []
        for c in prov_crop:
            label = c.get("crop")
            share = c.get("share")
            if label is None or share is None:
                continue
            key = CROP_KEY.get(label)
            if key is None:
                unmapped_crops.add(label)
                continue
            v = yoy.get(key)
            mix.append({"crop": label, "key": key, "share": round(share, 4),
                        "yoy": v, "direction": direction(v),
                        "depended_on": bool(share >= DOMINANT_SHARE)})
        mix.sort(key=lambda c: (-c["share"], c["crop"]))

        dep = [c for c in mix if c["depended_on"]]
        falling = [c for c in dep if c["direction"] == "down"]
        # "Weakest" = the depended-on crop with the least price support. It is the one that would
        # cross zero first; it is NOT a claim that it is going to.
        priced = [c for c in dep if c["yoy"] is not None]
        weakest = min(priced, key=lambda c: (c["yoy"], c["crop"])) if priced else None

        rows.append({
            "th": th,
            "region": (cs.get(th) or {}).get("region"),
            "n_farm_accounts": n,
            "current_pct": current_pct,
            "early_pct": round(early, 2),
            "n_current": n_current,
            "n_early": n_early,
            "n_current_x": n_current + n_early,
            "os_thb": rec.get("os_sum"),
            "dpd90p_pct": rec.get("dpd90p_pct"),
            "crops": mix,
            "n_depended_on": len(dep),
            "weakest_crop": weakest["crop"] if weakest else None,
            "weakest_yoy": weakest["yoy"] if weakest else None,
            "also_in_drought_radar": th in drought,
            "tripped": bool(falling),
            "falling_crops": [c["crop"] for c in falling],
        })

    rows.sort(key=lambda r: (-r["n_current_x"], r["th"]))

    # Per-crop rollup — the headline table. "If this one turned, this much of the healthy farm book
    # would need contacting." Only provinces that DEPEND on the crop (>= DOMINANT_SHARE) are counted,
    # so the numbers do not double-count trace plantings.
    crops_out = []
    for label, key in sorted(CROP_KEY.items()):
        hit = [r for r in rows if any(c["key"] == key and c["depended_on"] for c in r["crops"])]
        crops_out.append({
            "crop": label,
            "key": key,
            "yoy": yoy.get(key),
            "direction": direction(yoy.get(key)),
            "n_provinces": len(hit),
            "n_current_x": sum(r["n_current_x"] for r in hit),
            "n_farm_accounts": sum(r["n_farm_accounts"] for r in hit),
            "os_thb": round(sum(r["os_thb"] or 0 for r in hit), 2),
            "top_provinces": [r["th"] for r in hit[:5]],
        })
    crops_out.sort(key=lambda c: (-c["n_current_x"], c["crop"]))

    tripped = [r["th"] for r in rows if r["tripped"]]
    n_cx = sum(r["n_current_x"] for r in rows)

    data = {
        "meta": {
            "title": "Proactive assistance — the healthy farm book, by the crop price it rides on",
            "generated_by": "pipeline/build_assist_radar_price.py",
            "deterministic": True,
            "network_free": True,
            "label": ("MEASURED — real-tape account counts and balances crossed with MEASURED planted-area "
                      "crop shares and MEASURED Thai farm-gate price YoY. The only judgement is the "
                      "dominance threshold in meta.trigger. Nothing is modelled and nothing is forecast."),
            "source": ("accounts + balances: platform/data/tape_real.json (agri_impact.by_province, real "
                       "no-PII tape aggregates); crop shares: platform/data/crop_stress.json (OAE "
                       "crop_prov_area + DOAE 2568 registry); prices: source-data/farmgate_prices.json "
                       "(NABC daily national-average farm-gate series)."),
            "price_vintage": price_vintage,
            "tape_vintage": (tape.get("meta") or {}).get("vintage") or (tape.get("meta") or {}).get("as_of"),
            "n_provinces": len(rows),
            "n_current_x_total": n_cx,
            "sort": "provinces: most Current+X farm accounts first; crops: most exposed Current+X first",
            "trigger": {
                "rule": ("a province is DEPENDED-ON by a crop when that crop is at least "
                         "%d%% of its planted area; the province TRIPS when any such crop's farm-gate "
                         "YoY is below -%.0f%%." % (round(DOMINANT_SHARE * 100), FLAT_BAND_PCT)),
                "dominant_share": DOMINANT_SHARE,
                "flat_band_pct": FLAT_BAND_PCT,
                "n_tripped": len(tripped),
            },
            "reading": ("n_current_x is the count of farm accounts that are CURRENT or only in the X "
                        "(pre-30-day) bucket — the healthy population you would contact BEFORE it "
                        "deteriorates. os_thb is the province's WHOLE farm book, not the Current+X "
                        "slice: the tape aggregate does not expose outstanding split by bucket, and "
                        "splitting it here would be fabrication."),
            "caveats": [
                ("Not a forecast. Ranking crops by exposed accounts says how much of the healthy book "
                 "rides on each price, not which price is going to move."),
                ("Sugarcane cannot be placed on this map, and its only price here is STALE: the OAE "
                 "snapshot is stamped BE 2562 = 2019 CE. Cane registers with the OCSB, so it has "
                 "neither a current Thai price nor a DOAE planted area; it appears in the per-branch "
                 "agri layer carrying that 2019 figure, labelled with its vintage."),
                ("Only " + str(len(CROP_KEY)) + " crops are mapped here (" + ", ".join(sorted(CROP_KEY))
                 + "), so 'nothing is falling' means nothing MAPPED is falling. Six measured Thai "
                 "prices ARE down — coconut, pineapple, pork, white shrimp, chicken, eggs — and are "
                 "shown on the Macro commodities board. They are missing from this radar because the "
                 "exposure join reads crop_stress.json crop shares, which still carry only these five."),
                ("Province crop shares are planted AREA, not the borrower's actual crop. A farm "
                 "borrower in a rice-dominant province is assumed exposed to rice; the tape does not "
                 "record what any individual grows."),
                ("Drought and price are separate hazards. also_in_drought_radar marks the provinces "
                 "the rainfall-driven assistance_radar already flags, so the two lists can be read "
                 "together instead of double-counting."),
            ],
        },
        "crops": crops_out,
        "provinces": rows,
        "tripped": tripped,
    }
    if unmapped_crops:
        data["meta"]["unmapped_crops"] = sorted(unmapped_crops)
    return data, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the committed file reproduces byte-for-byte")
    args = ap.parse_args()

    data, missing = build()

    if args.check:
        if data is None:
            print("CHECK SKIP: %s absent — assist_price_radar not byte-checkable" % missing,
                  file=sys.stderr)
            sys.exit(3)
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == dumps(data):
            print("CHECK OK: %s reproduces byte-for-byte (%d provinces, %d tripped)" %
                  (OUT, len(data["provinces"]), len(data["tripped"])))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    if data is None:
        print("SKIP: %s absent — nothing to build" % missing, file=sys.stderr)
        sys.exit(3)

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(data))
    top = data["crops"][0] if data["crops"] else None
    print("wrote %s (%d provinces, %d Current+X farm accounts, %d tripped)%s" %
          (OUT, len(data["provinces"]), data["meta"]["n_current_x_total"], len(data["tripped"]),
           ("; most-exposed crop: %s (%s, %+.1f%% YoY, %d accounts)" %
            (top["crop"], top["direction"], top["yoy"], top["n_current_x"])) if top else ""))


if __name__ == "__main__":
    main()
