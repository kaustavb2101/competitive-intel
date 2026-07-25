"""
build_product_segments.py — product → segment → driver map (TMLI-convergence move 5, 2026-07-25)

The connective layer TMLI had and CI lacked: a single map from each LOAN PRODUCT (what the collateral
is) to the borrower SEGMENTS behind it, the income DRIVERS that move those segments, and the SCENARIOS
(scenarios.json) that hit them. It turns "rice fell / diesel spiked / the rate cap bit" into "…so THIS
share of the book, in THESE products, feels it."

Measured spine, curated transmission:
  · book economics per product (share, NPL-live, outstanding, avg eval) are MEASURED — tape vehicle_types
  · the product→segment→driver→scenario wiring is a CURATED editorial map (labelled), linking each
    product to the income drivers (build_income_impact) and scenario ids (build_scenarios) that move it

  in : platform/data/tape_real.json    MEASURED — vehicle_types (book share + NPL per collateral)
       platform/data/scenarios.json    scenario ids to link (validated against this file)
  out: platform/data/product_segments.json   (--check: byte-exact reproduce)

Deterministic + network-free. No macro feed is pulled here — IMF WEO is 403-blocked even from the
Thai IP; the CPI-by-category / MOTS-tourism feeds are reachable but each needs its own scheduled
puller (a cron like data-fuel-prices.yml), tracked separately. This move ships the one piece that is
fully in-hand and ties moves 1-4 together.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "platform", "data")
OUT = os.path.join(P, "product_segments.json")

# CURATED transmission map keyed by the tape's vehicle_type code. segments = plain-language borrower
# groups; drivers = the income channels that move them; scenarios = ids in scenarios.json.
PRODUCT_MAP = {
    "MC": {"product": "Motorcycle title", "th": "ทะเบียนมอเตอร์ไซค์",
           "segments": ["Rural / agri households", "Gig & daily-wage earners"],
           "drivers": ["crop price", "fuel"], "scenarios": ["crop_now", "rice_reversal", "fuel_spike"],
           "note": "Smallest-ticket, most rural book — moves with the farm cycle and pump price."},
    "PU": {"product": "Pickup title", "th": "ทะเบียนรถกระบะ",
           "segments": ["Farmers", "Transporters / haulage", "Rural SME"],
           "drivers": ["fuel", "crop price"], "scenarios": ["fuel_spike", "crop_now", "tree_crop_correction"],
           "note": "The working-vehicle book — diesel is a direct cost line; doubles as farm income."},
    "PA": {"product": "Passenger-car title", "th": "ทะเบียนรถเก๋ง",
           "segments": ["Salaried / urban", "Small business owners"],
           "drivers": ["rate cap"], "scenarios": ["rate_cap_28"],
           "note": "More urban / salaried — least crop-sensitive; the rate cap is the main lever."},
    "PA_ALT": None,   # placeholder guard (no such code); ignored
    "Mortgage": {"product": "Mortgage / house title", "th": "จำนอง/ทะเบียนบ้าน",
                 "segments": ["SME owners", "Landholding farmers"],
                 "drivers": ["rate cap", "crop price"], "scenarios": ["rate_cap_28", "crop_now"],
                 "note": "Larger-ticket, land-backed — rate-sensitive; rural landholders also crop-exposed."},
    "Land": {"product": "Land title", "th": "โฉนดที่ดิน",
             "segments": ["Landholding farmers", "SME owners"],
             "drivers": ["crop price", "rate cap"], "scenarios": ["crop_now", "drought_now", "rate_cap_28"],
             "note": "Lowest-NPL, land-secured — farm cash-flow and drought move the underlying holder."},
    "TRUCK": {"product": "Truck title", "th": "ทะเบียนรถบรรทุก",
              "segments": ["Haulage / logistics operators"],
              "drivers": ["fuel"], "scenarios": ["fuel_spike"],
              "note": "Commercial haulage — most fuel-geared segment in the book."},
    "TRACTOR": {"product": "Tractor / agri-vehicle title", "th": "ทะเบียนรถแทรกเตอร์",
                "segments": ["Farmers (mechanised)"],
                "drivers": ["crop price", "fuel", "drought"],
                "scenarios": ["crop_now", "drought_now", "fuel_spike", "rice_reversal"],
                "note": "Pure farm collateral — the most crop-and-drought-exposed product."},
    "VAN": {"product": "Van title", "th": "ทะเบียนรถตู้",
            "segments": ["Passenger transport", "Tourism operators"],
            "drivers": ["fuel", "tourism"], "scenarios": ["fuel_spike"],
            "note": "Passenger/tourism transport — fuel-geared; a tourism feed would sharpen this."},
}


def load(*path):
    return json.load(open(os.path.join(*path), encoding="utf-8"))


def build():
    tape = load(P, "tape_real.json")
    vt = tape.get("vehicle_types", {})
    valid_scen = {s["id"] for s in load(P, "scenarios.json").get("scenarios", [])}
    total = sum(v["n"] for v in vt.values()) or 1

    products = []
    mapped = 0
    for code, cell in sorted(vt.items(), key=lambda kv: -kv[1]["n"]):
        m = PRODUCT_MAP.get(code)
        if not m:
            # unmapped collateral code — carry the measured economics, flag the gap honestly
            products.append({
                "code": code, "product": code, "mapped": False,
                "book_share_pct": round(cell["n"] * 100.0 / total, 1),
                "accounts": cell["n"], "npl_live_pct": cell["npl_live_pct"],
                "os_bn": round(cell["os_sum"] / 1e9, 2),
                "segments": [], "drivers": [], "scenarios": [],
                "note": "No curated segment map for this collateral code yet.",
            })
            continue
        mapped += 1
        # keep only scenario ids that exist in scenarios.json (guards drift)
        scen = [s for s in m["scenarios"] if s in valid_scen]
        products.append({
            "code": code, "product": m["product"], "th": m["th"], "mapped": True,
            "book_share_pct": round(cell["n"] * 100.0 / total, 1),
            "accounts": cell["n"], "npl_live_pct": cell["npl_live_pct"],
            "os_bn": round(cell["os_sum"] / 1e9, 2),
            "eval_avg": cell.get("eval_avg"),
            "segments": m["segments"], "drivers": m["drivers"], "scenarios": scen,
            "note": m["note"],
        })

    # driver → products index (which books move when a given channel moves)
    driver_index = {}
    for p in products:
        for d in p.get("drivers", []):
            driver_index.setdefault(d, []).append(p["code"])

    return {
        "meta": {
            "title": "Product → segment → driver map",
            "generated_by": "pipeline/build_product_segments.py",
            "label": "MEASURED book economics per product (share/NPL/outstanding/eval — tape "
                     "vehicle_types) with a CURATED transmission map (product → borrower segments "
                     "→ income drivers → scenario ids). The wiring is editorial and labelled; the "
                     "numbers are measured.",
            "feeds_note": "Macro feeds not yet wired: IMF WEO is 403-blocked even from the Thai IP; "
                          "CPI-by-category and MOTS tourism are reachable but each needs its own "
                          "scheduled puller (a cron like data-fuel-prices.yml) — tracked separately, "
                          "not faked here. The 'tourism' driver on van/transport is a placeholder "
                          "the MOTS feed would populate.",
            "n_products": len(products), "n_mapped": mapped,
        },
        "products": products,
        "driver_index": driver_index,
    }


def main():
    if not os.path.exists(os.path.join(P, "scenarios.json")):
        print("build_product_segments.py: SKIP (scenarios.json absent — run the scenario/tape wave)")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if "--check" in sys.argv[1:]:
        if not os.path.exists(OUT):
            sys.exit("build_product_segments.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_product_segments.py --check: drifted — re-run the builder.")
        print("build_product_segments.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d products (%d mapped)" % (OUT, len(obj["products"]),
                                                  obj["meta"]["n_mapped"]))


if __name__ == "__main__":
    main()
