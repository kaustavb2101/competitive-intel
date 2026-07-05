#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_fuel_prices.py — LIVE Thai retail fuel prices (diesel / gasohol) from Bangchak.

SOURCE: Bangchak official retail-price API (www.bangchak.co.th/api/oilprice) — daily Bangkok
reference prices, JSON, NO key, and REACHABLE from the cloud (verified HTTP 200), unlike EPPO /
data.go.th / PTT which are geoblocked. Fuel cost is a macro pressure on AutoX's borrower base
(pickup-owning farmers pay diesel; motorcycle owners pay gasohol), so a live fuel line belongs on
the macro/commodity board alongside crop prices.

OUTPUT: source-data/fuel_prices.json — every fuel's today/tomorrow price + day delta (฿/litre), plus
headline diesel & gasohol-95 figures. The API pre-announces tomorrow's price, so the delta is a real
forward signal. No history in the API → YoY isn't available here; the daily workflow snapshots build
the series over time.

  python3 pull_fuel_prices.py            # pull + write source-data/fuel_prices.json
  python3 pull_fuel_prices.py --stamp 2026-07-05
  python3 pull_fuel_prices.py --selftest # offline parse check
"""
import argparse, json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "fuel_prices.json")
URL = "https://www.bangchak.co.th/api/oilprice"
UA = {"User-Agent": "Mozilla/5.0 (compatible; autox-credit-intel/1.0)"}


def _fetch():
    req = urllib.request.Request(URL, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _num(x):
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return None


def parse(raw):
    items = (raw.get("data") or {}).get("items") or raw.get("items") or []
    fuels = {}
    for it in items:
        name = (it.get("OilNameEng") or it.get("OilName") or "").strip()
        if not name:
            continue
        fuels[name] = {
            "today": _num(it.get("PriceToday")),
            "tomorrow": _num(it.get("PriceTomorrow")),
            "delta_tomorrow": _num(it.get("PriceDifTomorrow")),
        }
    # headline fuels most relevant to AutoX borrowers
    def pick(*subs):
        # try each substring in PRIORITY order (so "Hi Diesel S" beats "Diesel B20")
        for s in subs:
            for n, v in fuels.items():
                if s.lower() in n.lower() and v["today"] is not None:
                    return n, v
        return None, None
    dn, dv = pick("Hi Diesel S", "Diesel S", "Diesel")
    gn, gv = pick("Gasohol 95", "95")
    headline = {
        "diesel": (dv or {}).get("today"), "diesel_name": dn,
        "diesel_delta_tomorrow": (dv or {}).get("delta_tomorrow"),
        "gasohol95": (gv or {}).get("today"), "gasohol95_name": gn,
        "gasohol95_delta_tomorrow": (gv or {}).get("delta_tomorrow"),
    }
    return fuels, headline


def build(raw, stamp):
    fuels, headline = parse(raw)
    return {
        "meta": {
            "source": "Bangchak retail oil-price API (www.bangchak.co.th/api/oilprice) — daily Bangkok "
                      "reference prices; free, no key, cloud-reachable (EPPO/PTT/data.go.th are geoblocked).",
            "label": "MEASURED — live Thai retail fuel prices (฿/litre, Bangkok reference)",
            "generated_by": "pipeline/pull_fuel_prices.py",
            "pulled": stamp,
            "unit": "THB/litre",
            "note": "The API pre-announces tomorrow's price; delta_tomorrow is a forward signal. No "
                    "in-API history (YoY unavailable); daily snapshots build the series over time. "
                    "Diesel = pickup/farm borrowers; gasohol = motorcycle borrowers. No LPG/NGV (Bangchak "
                    "doesn't retail them; those need the geoblocked EPPO pull).",
            "n_fuels": len(fuels),
        },
        "headline": headline,
        "fuels": {k: fuels[k] for k in sorted(fuels)},
    }


SELFTEST = {"data": {"items": [
    {"OilNameEng": "Hi Diesel S", "PriceToday": "37.5", "PriceTomorrow": "37.8", "PriceDifTomorrow": "0.3"},
    {"OilNameEng": "Gasohol 95 S EVO", "PriceToday": "37.45", "PriceTomorrow": "37.45", "PriceDifTomorrow": "0"},
]}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default="")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        doc = build(SELFTEST, "test")
        assert doc["headline"]["diesel"] == 37.5 and doc["headline"]["gasohol95"] == 37.45, doc["headline"]
        print("selftest OK:", doc["headline"])
        return
    doc = build(_fetch(), a.stamp)
    if not doc["fuels"]:
        sys.exit("pull_fuel_prices.py: no fuels parsed — API shape may have changed.")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    h = doc["headline"]
    print("wrote %s" % OUT)
    print("  diesel (%s): ฿%s/L (Δtmrw %s) | gasohol95: ฿%s/L (Δtmrw %s) | %d fuels"
          % (h["diesel_name"], h["diesel"], h["diesel_delta_tomorrow"],
             h["gasohol95"], h["gasohol95_delta_tomorrow"], doc["meta"]["n_fuels"]))


if __name__ == "__main__":
    main()
