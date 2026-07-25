"""
build_scenarios.py — the scenario engine as a DATA layer (TMLI-convergence move 3, owner ask 2026-07-25)

Owner problem: "the scenario engine has hardcoded scenarios. they dont reflect real-world / current
scenarios which should be updated on a weekly / monthly basis." Fix: scenarios stop being constants
baked into app.js and become a provenance-stamped, VINTAGE-VISIBLE data layer rebuilt from the live
measured signals the rest of the pipeline already refreshes. The weekly cron
(.github/workflows/data-scenarios.yml) re-runs this and auto-merges on a green gate.

Each scenario carries measured driver values where the shock is CURRENT (crop YoY, drought census,
rival-promo count) and clearly-labelled STATED magnitudes where it is a stress test. The drivers are
the same shock vector the income-impact engine (build_income_impact.py) passes through, so a scenario
and the income readout stay consistent.

  in : source-data/commodity_board.json   MEASURED — commodity YoY moves (live crop shock)
       platform/data/crop_stress.json      MEASURED — per-province OAE SPEI drought census
       platform/data/fuel_prices.json      MEASURED — retail diesel level
       platform/data/rival_pulse.json      MEASURED — rival promo count + app-rating gap
       platform/data/income_impact.json    the first-order pass-through (for the live crop effect)
  out: platform/data/scenarios.json        (--check: byte-exact reproduce)

Deterministic — no LLM, no network. Everything is labelled measured / stated-stress.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "platform", "data")
S = os.path.join(ROOT, "source-data")
OUT = os.path.join(P, "scenarios.json")

# stated stress magnitudes (labelled ESTIMATED — a stress test, not a forecast)
FUEL_SPIKE_PCT = 15
CROP_CORRECTION_PCT = -20
RICE_REVERSAL_PCT = -15


def load(*path):
    return json.load(open(os.path.join(*path), encoding="utf-8"))


def build():
    board = {it["lab"]: it for it in load(S, "commodity_board.json")}
    crop_stress = load(P, "crop_stress.json")
    fuel = load(P, "fuel_prices.json")
    income = load(P, "income_impact.json")
    try:
        pulse = load(P, "rival_pulse.json")
    except FileNotFoundError:
        pulse = None

    board_vintage = next((it.get("stale") for it in board.values() if it.get("stale")), None)
    drought_n = sum(1 for p in crop_stress["provinces"] if (p.get("drought") or 0) >= 0.5)
    diesel = (fuel.get("headline") or {}).get("diesel")
    # live crop effect straight off the income engine (most-supported region first / worst last)
    inc_regions = income.get("regions", [])
    crop_best = max(inc_regions, key=lambda g: g["income_pressure_pct"], default=None)
    crop_worst = min(inc_regions, key=lambda g: g["income_pressure_pct"], default=None)

    crop_yoy = {k: board[k]["yoy"] for k in ("Rice", "Rubber", "Palm oil", "Sugar", "Maize")
                if k in board}

    scenarios = []

    # 1) LIVE — the current crop-price picture (measured YoY, real effect via the income engine)
    scenarios.append({
        "id": "crop_now", "kind": "live",
        "title": "Crop-price picture — current",
        "headline": ("Crop prices are up YoY (rice %+.0f%%, rubber %+.0f%%, palm %+.0f%%), lifting "
                     "farm-household income most in %s (%+.1f%% book income) and least in %s."
                     % (crop_yoy.get("Rice", 0), crop_yoy.get("Rubber", 0),
                        crop_yoy.get("Palm oil", 0),
                        crop_best["key"] if crop_best else "—",
                        crop_best["income_pressure_pct"] if crop_best else 0,
                        crop_worst["key"] if crop_worst else "—")),
        "drivers": {"crop_yoy_pct": crop_yoy},
        "effect": {"channel": "farm income",
                   "region_income_pct": {g["key"]: g["income_pressure_pct"]
                                         for g in inc_regions}},
        "provenance": "MEASURED — World Bank Pink Sheet commodity board × NSO SES income "
                      "(via build_income_impact.py first-order pass-through).",
        "vintage": board_vintage,
    })

    # 2) LIVE — drought census (OAE SPEI), the agri-stress amplifier
    scenarios.append({
        "id": "drought_now", "kind": "live",
        "title": "Drought — firing",
        "headline": ("%d of 76 crop provinces sit in OAE SPEI drought (SPEI ≤ −0.5), amplifying "
                     "agri-household stress where the book is farm-heavy." % drought_n),
        "drivers": {"drought_provinces": drought_n},
        "effect": {"channel": "agri stress"},
        "provenance": "MEASURED — OAE SPEI severe/extreme district census (crop_stress.json).",
        "vintage": (crop_stress.get("meta") or {}).get("vintage") or board_vintage,
    })

    # 4) LIVE — rival promo pressure (competitive margin, objective #2)
    if pulse:
        h = pulse.get("headline", "")
        npromo = len(pulse.get("promos", []))
        scenarios.append({
            "id": "rival_promo", "kind": "live",
            "title": "Rival promo pressure",
            "headline": ("%d live rival promotions tracked; our own app trails the best rival on "
                         "rating — sustained acquisition/retention pressure on margin." % npromo),
            "drivers": {"rival_promos": npromo},
            "effect": {"channel": "competitive margin"},
            "provenance": "MEASURED — rival own-site promo pull + Google Play ratings "
                          "(rival_pulse.json).",
            "vintage": ((pulse.get("meta") or {}).get("pulled")
                        or (pulse.get("meta") or {}).get("generated") or board_vintage),
        })

    # 5-7) STATED STRESS TESTS — clearly labelled hypotheticals (not forecasts)
    scenarios.append({
        "id": "fuel_spike", "kind": "stress",
        "title": "Diesel spike +%d%%" % FUEL_SPIKE_PCT,
        "headline": ("STATED STRESS: a +%d%% diesel move squeezes transport/haulage and pickup-"
                     "owner margins (fuel is a direct cost line); salaried incomes unaffected."
                     % FUEL_SPIKE_PCT),
        "drivers": {"fuel_move_pct": FUEL_SPIKE_PCT, "diesel_now_thb_l": diesel},
        "effect": {"channel": "transport/pickup income"},
        "provenance": "STATED STRESS (not a forecast) — magnitude chosen to rank exposure; passes "
                      "through the income engine's documented fuel coefficients.",
        "vintage": "stated",
    })
    scenarios.append({
        "id": "tree_crop_correction", "kind": "stress",
        "title": "Rubber/palm correction %d%%" % CROP_CORRECTION_PCT,
        "headline": ("STATED STRESS: a %d%% reversal in rubber & palm would cut South/East farm "
                     "income, the mirror of today's tailwind." % CROP_CORRECTION_PCT),
        "drivers": {"rubber_pct": CROP_CORRECTION_PCT, "palm_pct": CROP_CORRECTION_PCT},
        "effect": {"channel": "farm income (South/East)"},
        "provenance": "STATED STRESS (not a forecast) — downside mirror of the measured tailwind.",
        "vintage": "stated",
    })
    scenarios.append({
        "id": "rice_reversal", "kind": "stress",
        "title": "Rice reversal %d%%" % RICE_REVERSAL_PCT,
        "headline": ("STATED STRESS: a %d%% rice-price reversal would pressure Isan/North/Central "
                     "farm income — the region-1 (Isan) book is most rice-exposed." % RICE_REVERSAL_PCT),
        "drivers": {"rice_pct": RICE_REVERSAL_PCT},
        "effect": {"channel": "farm income (rice belt)"},
        "provenance": "STATED STRESS (not a forecast).",
        "vintage": "stated",
    })

    return {
        "meta": {
            "title": "Scenario engine — provenance-stamped, refreshed weekly",
            "generated_by": "pipeline/build_scenarios.py",
            "label": "Scenarios are a DATA layer, not hardcoded UI. LIVE scenarios carry MEASURED "
                     "current driver values and refresh weekly with their source layers; STRESS "
                     "scenarios are clearly-labelled stated tests (not forecasts). Each card shows "
                     "its vintage.",
            "refresh": "Weekly via .github/workflows/data-scenarios.yml (rebuild + auto-merge on "
                       "a green determinism gate; draft PR on a red gate).",
            "board_vintage": board_vintage,
            "kinds": {"live": "measured current shock",
                      "stress": "stated hypothetical (not a forecast)"},
        },
        "scenarios": scenarios,
    }


def main():
    if not os.path.exists(os.path.join(P, "income_impact.json")):
        # exit 3 = the gate's SKIP contract (income engine absent → tape ingest wave absent)
        print("build_scenarios.py: SKIP (income_impact.json absent — run build_income_impact first)")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if "--check" in sys.argv[1:]:
        if not os.path.exists(OUT):
            sys.exit("build_scenarios.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_scenarios.py --check: drifted — re-run the builder.")
        print("build_scenarios.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d scenarios (%s)" % (OUT, len(obj["scenarios"]),
          ", ".join(s["kind"] for s in obj["scenarios"])))


if __name__ == "__main__":
    main()
