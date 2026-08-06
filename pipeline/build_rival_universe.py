#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rival_universe.py — the FULL จำนำทะเบียน operator census (objective #2), projected for the app.

  in : source-data/rival_universe.json   hand-verified editorial census (owner/backing, model,
                                          footprint claims — ESTIMATED-from-public-reports, cited)
       source-data/app_reviews.json      measured Play ladder (optional) — joins live app scores
                                          onto operators via app_brand
  out: platform/data/rival_universe.json operators grouped us / nonbank / bank, app score joined

Why this exists: the big-4 census (branch coordinates) covers the branch-led non-banks we compete
with street-by-street, but the competitive field is wider — TISCO's Somwang (800+ branches), KBank's
เงินให้ใจ riding ~800 K-branches, Krungsri's Car4Cash, KTC พี่เบิ้ม, GSB's เงินดีดี/มีที่มีเงิน rate
pressure, plus listed regionals (SAK, TURBO, MICRO, AMANAH). This layer names them all with owner,
model, footprint claim and (where an app exists) the measured Play score.

Deterministic + network-free. `--check` byte-compares. Exits 3 (SKIP) only if the census itself is
absent; the app-score join degrades to null per-operator when app_reviews.json is missing.

  python3 build_rival_universe.py
  python3 build_rival_universe.py --check
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_UNI = os.path.join(ROOT, "source-data", "rival_universe.json")
IN_REV = os.path.join(ROOT, "source-data", "app_reviews.json")
OUT = os.path.join(ROOT, "platform", "data", "rival_universe.json")

# 'broker' sorts last and is COUNTED SEPARATELY on purpose: an online origination platform with no
# branches is not local competitive pressure, so folding it into the tracked-operator count would
# overstate the field around our footprint. It is listed rather than omitted because an absent
# operator invites the same "is X a rival?" question again (this tier exists because of exactly one:
# WSOL/CarFinn, née SABUY). Any tier not named here sorts to 9 — keep new tiers explicit.
TIER_ORDER = {"us": 0, "nonbank": 1, "bank": 2, "broker": 3}


def build():
    doc = json.load(open(IN_UNI, encoding="utf-8"))
    scores = {}
    if os.path.exists(IN_REV):
        for brand, a in json.load(open(IN_REV, encoding="utf-8")).get("apps", {}).items():
            st = a.get("stats", {})
            if st.get("score") is not None:
                scores[brand] = {"score": round(st["score"], 2), "ratings": st.get("ratings")}

    ops = []
    for o in doc.get("operators", []):
        rec = dict(o)
        rec["app"] = scores.get(o.get("app_brand")) if o.get("app_brand") else None
        ops.append(rec)
    ops.sort(key=lambda o: (TIER_ORDER.get(o["tier"], 9), o["key"]))

    n_nonbank = sum(1 for o in ops if o["tier"] == "nonbank")
    n_bank = sum(1 for o in ops if o["tier"] == "bank")
    n_broker = sum(1 for o in ops if o["tier"] == "broker")
    return {
        "meta": {
            "title": doc["meta"]["title"],
            "generated_by": "pipeline/build_rival_universe.py",
            "label": doc["meta"]["label"],
            "verified": doc["meta"]["verified"],
            "market_note": doc["meta"].get("market_note"),
            "citations": doc["meta"].get("citations", []),
            "source": "source-data/rival_universe.json (hand-verified editorial) + app_reviews.json (measured Play scores)",
        },
        "headline": ("%d operators tracked beyond our own network: %d branch-led non-banks and %d "
                     "bank-backed entrants — the bank tier competes through ~2,000 bank branches "
                     "and apps, not storefronts, so it pressures margins before it shows up on a map."
                     % (n_nonbank + n_bank, n_nonbank, n_bank)
                     + ("" if not n_broker else
                        " A further %d online broker%s is listed but NOT counted here: it originates "
                        "through a website and runs no branches, so it is not local pressure on the "
                        "footprint." % (n_broker, "" if n_broker == 1 else "s"))),
        "operators": ops,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN_UNI):
        if args.check:
            print("build_rival_universe.py --check: SKIP (source-data/rival_universe.json absent)")
            sys.exit(3)
        sys.exit("build_rival_universe.py: source-data/rival_universe.json missing")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_rival_universe.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_rival_universe.py --check: drifted — re-run the builder.")
        print("build_rival_universe.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d operators" % (OUT, len(obj["operators"])))
    print("headline:", obj["headline"])


if __name__ == "__main__":
    main()
