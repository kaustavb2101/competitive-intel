"""
build_commodities.py — the commodities board upgrade (TMLI-convergence move 4, owner ask 2026-07-25)

TMLI's commodities page was concise and readable; CI has richer data but scattered. This unifies it
into ONE board layer with a "who's exposed" drill:
  · GLOBAL price move  — World Bank Pink Sheet YoY (commodity_board.json)
  · LOCAL price move    — Thai farm-gate YoY (farmgate_prices.json) — the domestic cross-check
  · DIVERGENCE          — local − global (where the Thai farmer's reality parts from the world price)
  · WHO'S EXPOSED       — provinces growing the crop (planted area) and the AutoX book accounts
                          sitting in them, weighted by crop share → press a commodity, see the book.

  in : source-data/commodity_board.json    MEASURED — Pink Sheet YoY (global)
       source-data/farmgate_prices.json    MEASURED — Thai farm-gate daily price + YoY (local)
       platform/data/fuel_prices.json      MEASURED — retail diesel (the cost line)
       source-data/crop_prov_area.json      MEASURED — rice/rubber/oilpalm planted area per province
       platform/data/impact_cards.json      book accounts per province
       platform/data/income_impact.json     per-province crop mix (area shares)
  out: platform/data/commodities.json       (--check: byte-exact reproduce)

Deterministic + network-free. Exposure is book-FOOTPRINT weighted by crop area (an ESTIMATE of which
accounts sit under each crop — labelled), and resolvable only for the three crops with province-level
area (rice/rubber/oilpalm); other board items carry their global/local price only, with region tags.
"""
import json
import os
import sys

from regionmap import REGION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "platform", "data")
S = os.path.join(ROOT, "source-data")
OUT = os.path.join(P, "commodities.json")

# board label → farm-gate key (local cross-check) and crop_prov_area key (exposure)
BOARD_TO_FARMGATE = {"Rice": "rice", "Rubber": "rubber", "Palm oil": "oilpalm",
                     "Maize": "maize"}
BOARD_TO_AREA = {"Rice": "rice", "Rubber": "rubber", "Palm oil": "oilpalm"}


def load(*path):
    return json.load(open(os.path.join(*path), encoding="utf-8"))


def build():
    board = load(S, "commodity_board.json")
    fg = load(S, "farmgate_prices.json")
    fgc = fg.get("commodities", {})
    fuel = load(P, "fuel_prices.json")
    area = load(S, "crop_prov_area.json")
    cards = load(P, "impact_cards.json")
    income = load(P, "income_impact.json")

    acc = {pv: p["accounts"] for pv, p in cards["provinces"].items()}
    cmix = {pv: p["crop_mix"] for pv, p in income["provinces"].items()}

    items = []
    for it in board:
        lab = it["lab"]
        fgkey = BOARD_TO_FARMGATE.get(lab)
        local = fgc.get(fgkey) if fgkey else None
        local_yoy = local.get("yoy") if local else None
        row = {
            "lab": lab, "seg": it.get("seg"), "reg": it.get("reg"),
            "global_yoy": it["yoy"], "cls": it["cls"], "note": it.get("note"),
            "global_vintage": it.get("stale"),
            "local_yoy": local_yoy,
            "local_price": (("%.2f %s" % (local["price"], local.get("unit", "")))
                            if local else None),
            "local_date": local.get("latest_date") if local else None,
            "divergence": (round(local_yoy - it["yoy"], 1) if local_yoy is not None else None),
        }
        # who's exposed — rank provinces by MEASURED planted area (the real crop belt, not
        # within-province share, which wrongly floats urban high-account provinces to the top),
        # take the core belt (provinces making up ~80% of national area), and report the book
        # accounts sitting in it.
        akey = BOARD_TO_AREA.get(lab)
        # canonical provinces only — crop_prov_area carries an empty-key national-total row that
        # would otherwise dominate the belt and inflate the national area.
        ar = {pv: a for pv, a in (area.get(akey, {}) if akey else {}).items() if pv in REGION}
        if ar:
            ranked = sorted(((pv, a) for pv, a in ar.items() if a > 0), key=lambda x: -x[1])
            national = sum(a for _, a in ranked) or 1
            belt, cum = [], 0
            for pv, a in ranked:
                belt.append((pv, a))
                cum += a
                if cum >= 0.80 * national:
                    break
            book_in_belt = sum(acc.get(pv, 0) for pv, _ in belt)
            row["exposure"] = {
                "book_accounts": book_in_belt,
                "belt_provinces": len(belt),
                "national_area_rai": national,
                "top": [{"prov": pv, "area_rai": a, "accounts": acc.get(pv, 0)}
                        for pv, a in belt[:6]],
                "basis": "book accounts in the crop's core belt (provinces = ~80% of national "
                         "planted area, MEASURED); belt identifies the real growing region.",
            }
        else:
            row["exposure"] = None
        items.append(row)

    # stressed (falling) first, then biggest movers — same ordering the cards use
    items.sort(key=lambda r: (r["cls"] != "stress", -abs(r["global_yoy"])))

    diesel = (fuel.get("headline") or {}).get("diesel")
    return {
        "meta": {
            "title": "Commodities board — global Pink Sheet × Thai farm-gate × book exposure",
            "generated_by": "pipeline/build_commodities.py",
            "label": "MEASURED prices (World Bank Pink Sheet global YoY + Thai farm-gate local YoY). "
                     "Divergence = local − global. WHO'S EXPOSED is an ESTIMATED book-footprint "
                     "read: accounts in a crop's growing provinces weighted by planted-area share; "
                     "resolvable only for rice/rubber/oilpalm (the crops with province area).",
            "farmgate_vintage": (fg.get("meta") or {}).get("pulled")
                                or next((v.get("latest_date") for v in fgc.values()), None),
            "divergence_note": "A large local−global gap flags where the Thai farmer's cash reality "
                               "parts from the world index (FX, export policy, local supply).",
        },
        "fuel": {"diesel_thb_l": diesel,
                 "name": (fuel.get("headline") or {}).get("diesel_name"),
                 "note": "Diesel is a cost line for pickup/haulage borrowers, not a crop revenue."},
        "board": items,
    }


def main():
    if not os.path.exists(os.path.join(P, "income_impact.json")):
        print("build_commodities.py: SKIP (income_impact.json absent — run the tape/income wave)")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if "--check" in sys.argv[1:]:
        if not os.path.exists(OUT):
            sys.exit("build_commodities.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_commodities.py --check: drifted — re-run the builder.")
        print("build_commodities.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d commodities, %d with exposure"
          % (OUT, len(obj["board"]), sum(1 for r in obj["board"] if r["exposure"])))


if __name__ == "__main__":
    main()
