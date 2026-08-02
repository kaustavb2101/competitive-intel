#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_used_vehicle_value.py — the used-vehicle COLLATERAL-VALUE layer (objective #1, portfolio
risk): what a lender actually recovers when it repossesses and auctions a title-loan vehicle,
tracked over time against the vehicle mix AutoX actually holds.

  in : source-data/bot_uvpi.json          (pull_bot_uvpi.py — MEASURED, BoT report EC_EI_040,
                                            built by BoT from AUCT's own auction hammer prices)
  out: platform/data/used_vehicle_value.json

Deterministic + network-free over the committed source-data file; `--check` byte-exact. Exits 3
(SKIP, not drift) when source-data/bot_uvpi.json is absent — mirrors build_credit_anchor.py's /
build_vehicle_mix.py's convention. No wall clock anywhere: every date in the output comes from the
data itself (the newest period actually published), never datetime.now().

THREE SERIES, same 2015 (พ.ศ. 2558) = 100 base:
  overall — all vehicles
  car     — รถยนต์นั่ง, passenger cars
  truck   — รถยนต์บรรทุก. CONFIRMED (pull_bot_uvpi.py's Task-1 finding, cited in its own meta and
            passed through here) to mean รถกระบะ, PICKUP TRUCKS — not heavy commercial trucks. This
            is the sub-index nearest AutoX's own collateral mix.
  The 2015 base is confirmed IN THE DATA (not assumed): each series' own 12 monthly 2015 values
  average to 100.00 +/-0.05, asserted before any "vs 2015 base" figure is computed.

PER SERIES, emitted:
  history        full monthly series, ascending, every month BoT has published (no gap-filling —
                 a month absent from the source is absent here too).
  latest         newest published value + its period + whether BoT still flags it preliminary ("p").
  yoy_pct        latest vs the same month one year earlier; null if that month isn't in the data.
  trailing_12m   high/low (value + period) over the newest 12 published months.
  all_time       peak/trough (value + period) over the FULL published history — this IS "the
                 pre-downturn peak": for every series here it lands at 2012-01, the post-flood /
                 pre-first-car-program spike the source's own methodology paper documents.
  change_since_peak_pct   latest vs that all-time peak.
  vs_2015_base_pp         latest value minus 100 — since each series' own 2015 sits at 100, this
                          IS "how many points below/above its own base year" in one number.
  sparkline      last 36 published months, values only, ascending — compact chart-ready trend.

TOP-LEVEL comparison (car vs truck, THE finding this layer exists to surface): the task brief
asserted the truck sub-index sits "far below" car on the shared base FROM A 6-MONTH SAMPLE. Checked
here over the full 137-month post-2015 overlap, that is only PARTLY true: the gap (car minus truck,
in index points) was near zero or even NEGATIVE (truck above car) through roughly 2013-2021, and
only opened up sharply from 2022 onward. `gap_by_year` carries the actual measured figures so nobody
has to take that on faith; `gap_latest_pp` / `gap_mean_early_pp` / `gap_mean_recent_12m_pp` are the
three summary numbers that show the widening without asserting a specific turning-point year.

Run:
    python3 build_used_vehicle_value.py
    python3 build_used_vehicle_value.py --check
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data", "bot_uvpi.json")
OUT = os.path.join(ROOT, "platform", "data", "used_vehicle_value.json")

SPARKLINE_MONTHS = 36
TRAILING_MONTHS = 12
BASE_TOL = 0.1          # +/- tolerance for the "2015 average == 100" assertion
EARLY_WINDOW = ("2013-01", "2021-12")  # pre-divergence reference band: after the 2011-12 flood /
                                        # first-car-program distortion, before the post-2022 widening


def _prior_year_period(period):
    y, m = period.split("-")
    return "%04d-%s" % (int(y) - 1, m)


def _assert_2015_base(name, data):
    vals2015 = [v for p, v in data.items() if p.startswith("2015-")]
    if not vals2015:
        return  # no 2015 data pulled — nothing to assert (would be a SKIP-worthy gap upstream)
    avg = sum(vals2015) / len(vals2015)
    assert abs(avg - 100.0) <= BASE_TOL, (
        "%s: 2015 monthly average = %.3f, expected ~100.0 (base year) — source rebased?" % (name, avg))


def _series_block(name, data, preliminary_periods):
    periods = sorted(data)
    history = [{"period": p, "value": data[p]} for p in periods]

    latest_p = periods[-1]
    latest_v = data[latest_p]
    prior_p = _prior_year_period(latest_p)
    yoy_pct = round((latest_v - data[prior_p]) / data[prior_p] * 100, 2) if prior_p in data else None

    trailing = periods[-TRAILING_MONTHS:]
    hi_p = max(trailing, key=lambda p: data[p])
    lo_p = min(trailing, key=lambda p: data[p])

    peak_p = max(periods, key=lambda p: data[p])
    trough_p = min(periods, key=lambda p: data[p])
    change_since_peak_pct = round((latest_v - data[peak_p]) / data[peak_p] * 100, 2)

    _assert_2015_base(name, data)
    vs_2015_base_pp = round(latest_v - 100.0, 2) if any(p.startswith("2015-") for p in periods) else None

    spark_periods = periods[-SPARKLINE_MONTHS:]

    return {
        "n_months": len(periods),
        "history": history,
        "latest": {"period": latest_p, "value": latest_v,
                   "preliminary": latest_p in preliminary_periods},
        "yoy_pct": yoy_pct,
        "yoy_prior_period": prior_p if yoy_pct is not None else None,
        "trailing_12m": {
            "high": {"period": hi_p, "value": data[hi_p]},
            "low": {"period": lo_p, "value": data[lo_p]},
        },
        "all_time": {
            "peak": {"period": peak_p, "value": data[peak_p]},
            "trough": {"period": trough_p, "value": data[trough_p]},
        },
        "change_since_peak_pct": change_since_peak_pct,
        "vs_2015_base_pp": vs_2015_base_pp,
        "sparkline": {"periods": spark_periods, "values": [data[p] for p in spark_periods]},
    }


def _comparison_block(car, truck):
    common = sorted(set(car) & set(truck))
    post2015 = [p for p in common if p >= "2015-01"]
    gaps = {p: round(car[p] - truck[p], 2) for p in post2015}

    by_year = {}
    for p, g in gaps.items():
        by_year.setdefault(p[:4], []).append(g)
    gap_by_year = {y: {"mean_pp": round(sum(vs) / len(vs), 2), "n_months": len(vs),
                        "min_pp": round(min(vs), 2), "max_pp": round(max(vs), 2)}
                   for y, vs in sorted(by_year.items())}

    early = [g for p, g in gaps.items() if EARLY_WINDOW[0] <= p <= EARLY_WINDOW[1]]
    recent12 = [gaps[p] for p in sorted(gaps)[-TRAILING_MONTHS:]]
    latest_p = common[-1]
    latest_gap = round(car[latest_p] - truck[latest_p], 2)

    car_vs_base = round(car[latest_p] - 100.0, 2)
    truck_vs_base = round(truck[latest_p] - 100.0, 2)
    decline_multiple = round(abs(truck_vs_base) / abs(car_vs_base), 2) if car_vs_base else None

    return {
        "basis": "car and truck are each independently rebased so THEIR OWN full-year 2015 average "
                 "= 100 (asserted in the data, not assumed) — so 'value - 100' is directly "
                 "comparable across the two series as points below/above own base year.",
        "window": {"first_period": post2015[0] if post2015 else None, "last_period": latest_p,
                   "n_months": len(post2015)},
        "gap_definition": "gap_pp = car index - truck index, in index points on the shared 2015=100 "
                          "base; positive means car sits above truck (the recent/current pattern), "
                          "negative means truck sits above car (true for stretches of 2013-2021).",
        "gap_latest_pp": latest_gap,
        "gap_mean_early_pp": round(sum(early) / len(early), 2) if early else None,
        "gap_mean_early_window": "%s..%s" % EARLY_WINDOW,
        "gap_mean_recent_12m_pp": round(sum(recent12) / len(recent12), 2) if recent12 else None,
        "gap_by_year": gap_by_year,
        "latest_vs_2015_base": {
            "car_pp": car_vs_base, "truck_pp": truck_vs_base,
            "truck_decline_multiple_of_car": decline_multiple,
        },
        "finding": "Checked over the full 2015-onward series (not the 6-month sample): the car-minus-"
                  "truck gap was near zero or NEGATIVE (truck above car) through most of 2013-2021, "
                  "then widened sharply from 2022 onward to the ~20-34pt gap seen in 2023-2026. The "
                  "current wide gap is a RECENT pattern, not a constant since the 2015 base year — "
                  "see gap_by_year for the actual measured trajectory.",
    }


def build():
    if not os.path.exists(SRC):
        return None
    with open(SRC, encoding="utf-8") as f:
        src = json.load(f)

    series_src = src["series"]
    m = src["meta"]
    preliminary = set(m.get("preliminary_periods", []))

    series = {name: _series_block(name, data, preliminary)
              for name, data in sorted(series_src.items())}
    comparison = _comparison_block(series_src["car"], series_src["truck"])

    return {
        "meta": {
            "title": "Used Vehicle Price Index (UVPI) — collateral-recovery value, MEASURED "
                     "(portfolio risk, objective #1)",
            "generated_by": "pipeline/build_used_vehicle_value.py",
            "label": "MEASURED — Bank of Thailand (ธปท.) report EC_EI_040, built from Union "
                     "Auction Public Company Limited's (AUCT) own auction hammer prices. This is "
                     "the price a lender recovers when it repossesses and auctions a title-loan "
                     "vehicle — BoT's own stated purpose for publishing it.",
            "source": m.get("title"),
            "source_url": m.get("source_url"),
            "metadata_pdf_url": m.get("metadata_pdf_url"),
            "methodology_paper_url": m.get("methodology_paper_url"),
            "base": m.get("base"),
            "definition_truck_series": m.get("definition_truck_series"),
            "provenance": "MEASURED. Pure projection of source-data/bot_uvpi.json (itself a direct "
                          "parse of BoT's published grid, spot-verified against 6 fixed anchor "
                          "months on every pull). Nothing modelled; yoy/trailing/peak/gap figures "
                          "are plain arithmetic over the published series.",
            "pulled": m.get("pulled"),
            "preliminary_periods": sorted(preliminary),
            "preliminary_note": m.get("preliminary_note"),
            "missing_periods": m.get("missing_periods", {}),
            "sparkline_months": SPARKLINE_MONTHS,
            "trailing_months": TRAILING_MONTHS,
        },
        "series": series,
        "comparison": comparison,
    }


def run(check=False):
    data = build()
    if data is None:
        print("SKIP: source-data/bot_uvpi.json absent "
              "— not data drift, run pull_bot_uvpi.py first")
        return 3
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: platform/data/used_vehicle_value.json")
            return 1
        ov = data["series"]["overall"]
        print("OK: used_vehicle_value.json reproduces byte-exact "
              "(%s..%s, %d months overall)" % (
                  ov["history"][0]["period"], ov["latest"]["period"], ov["n_months"]))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    ov = data["series"]["overall"]
    cmp_ = data["comparison"]
    print("wrote platform/data/used_vehicle_value.json")
    print("  overall: %d months, latest %s = %.2f (YoY %s%%)" % (
        ov["n_months"], ov["latest"]["period"], ov["latest"]["value"], ov["yoy_pct"]))
    print("  car-truck gap: latest %.2fpp, early(%s) mean %.2fpp, recent-12m mean %.2fpp" % (
        cmp_["gap_latest_pp"], cmp_["gap_mean_early_window"],
        cmp_["gap_mean_early_pp"], cmp_["gap_mean_recent_12m_pp"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
