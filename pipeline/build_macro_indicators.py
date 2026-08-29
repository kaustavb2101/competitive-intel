#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_macro_indicators.py — folds the fresher, primary-source MEASURED pulls landed 2026-08-02
(owner review: "inflation shows -0.13% / World Bank 2025 — shouldn't be using 2025"; escalation:
"why are figures still 2025? isn't there more current data?") into the SAME platform/data/
macro_indicators.json the chip strip already reads via compactMacro() — no app.js change needed.

WHY A SEPARATE DETERMINISTIC BUILDER (not folded into pull_macro.py directly): pull_macro.py is a
live network puller (BIS + World Bank + ECB) and is not gated by --check. The four inputs this
builder folds in are themselves separate network pullers' OUTPUTS (already-committed source-data/
JSON, not re-fetched here) — so this step can and must be a deterministic, network-free, --check
-gated builder: given the same platform/data/macro_indicators.json base and the same source-data/
inputs, it reproduces byte-for-byte.

INPUTS (all optional independently — an absent input leaves that indicator/key untouched):
  - platform/data/macro_indicators.json  (BASE — the file itself; household_debt_gdp, lending_rate
    and usd_thb are carried through UNCHANGED, since those are already fresh/correct per the owner's
    own review and this builder does not touch them)
  - source-data/bot_policy_rate.json → OVERRIDES policy_rate with the BOT-DIRECT primary reading
    (MPC decision history, `pull_bot_policy_rate.py`) instead of pull_macro.py's BIS republication:
    same headline rate to the decimal, but labelled BOT (not the quarterly BIS proxy) and carrying
    a meeting-level trend. Previously orphaned — pulled every meeting but consumed by nothing.
  - source-data/tpso_cpi.json      → OVERRIDES cpi_inflation with the MONTHLY headline CPI YoY from
    the Ministry of Commerce / TPSO (the actual compiler of Thai CPI — not BOT, not World Bank's
    annual average), period becomes "YYYY-MM" instead of a bare year.
  - source-data/nesdc_gdp.json     → ADDS gdp_growth, the ACTUAL latest-quarter real GDP YoY from
    NESDC (the actual compiler of Thai GDP), explicitly kind:"actual" — never to be confused with
    the IMF WEO 2026 projection shown elsewhere on the page.
  - source-data/bot_current_account.json → ADDS current_account, BOT's own monthly Balance-of-
    Payments current-account balance (the MEASURED series behind the IMF WEO current-account row).
  - source-data/bot_tourist_arrivals.json → ADDS tourist_arrivals, BOT's own monthly foreign-
    arrivals count, both the latest single month and a trailing-12-month sum (directly comparable
    in scale to the old annual "32.9M / 2025" editorial figure it supersedes).

ORDER OF OPERATIONS (important — read before re-running pull_macro.py): pull_macro.py OVERWRITES
platform/data/macro_indicators.json from scratch on every run and knows nothing about the three ADDED
keys here (gdp_growth, current_account, tourist_arrivals) or the CPI override. Always re-run THIS
builder immediately after any pull_macro.py run, or those three additions and the CPI override will
silently disappear until the next build_macro_indicators.py pass. (A future refactor could have
pull_macro.py call this builder as its last step; not done here to keep this change confined to a
new file, per the no-app.js/no-unrelated-refactor constraint for this pass.)

  python3 build_macro_indicators.py            # fold sources into platform/data/macro_indicators.json
  python3 build_macro_indicators.py --check     # byte-exact reproduction check
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "platform", "data", "macro_indicators.json")
SRC_CPI = os.path.join(ROOT, "source-data", "tpso_cpi.json")
SRC_GDP = os.path.join(ROOT, "source-data", "nesdc_gdp.json")
SRC_CA = os.path.join(ROOT, "source-data", "bot_current_account.json")
SRC_TOUR = os.path.join(ROOT, "source-data", "bot_tourist_arrivals.json")
SRC_POLICY = os.path.join(ROOT, "source-data", "bot_policy_rate.json")

TH_MON_ORDER = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _be_quarter_to_iso(q_be):
    """'2569' -> 2026, kept as the year; quarter number stays as-is (already ASCII digit)."""
    return int(q_be) - 543


def _load(path):
    if not os.path.exists(path):
        return None
    return json.load(open(path, encoding="utf-8"))


def _fold_cpi(indicators):
    d = _load(SRC_CPI)
    if not d:
        return
    latest = d["meta"]["latest_yoy"]
    y_ad = int(latest["year_be"]) - 543
    mon_i = TH_MON_ORDER.index(latest["month"]) + 1
    period = "%04d-%02d" % (y_ad, mon_i)
    indicators["cpi_inflation"] = {
        "value": latest["value"], "period": period, "unit": "% YoY",
        "source": "TPSO (Ministry of Commerce) — headline CPI, monthly",
    }


def _fold_gdp(indicators):
    d = _load(SRC_GDP)
    if not d:
        return
    latest = d["latest"]
    y_ad = _be_quarter_to_iso(latest["quarter"].split("/")[1])
    q_num = latest["quarter"].split("/")[0].replace("Q", "")
    period = "%04d-Q%s" % (y_ad, q_num)
    indicators["gdp_growth"] = {
        "value": latest["yoy_pct"], "period": period, "unit": "% YoY", "kind": "actual",
        "source": "NESDC (สภาพัฒน์) — Quarterly GDP, latest ACTUAL quarter (not a projection)",
        "qoq_sa_pct": latest.get("qoq_sa_pct"),
        "prior_quarter": latest.get("prior_quarter"),
    }


def _fold_current_account(indicators):
    d = _load(SRC_CA)
    if not d:
        return
    latest = d["meta"]["latest"]
    if not latest or latest.get("current_account") is None:
        return
    period = latest["period"]
    prelim = d["meta"].get("preliminary_periods") or []
    entry = {
        "latest_month": {"value": latest["current_account"], "period": period,
                         "preliminary": period in prelim},
        "source": "Bank of Thailand — Balance of Payments (summary), monthly",
    }
    # A single month of the current account swings hard (April 2026 alone printed -7,591 USD
    # million); the honest exec headline is the rolling twelve-month NET, so the chip carries a
    # trailing sum, not a season. Computed here, deterministically, from the MEASURED monthly
    # series already committed in source-data/bot_current_account.json — no new pull.
    series = (d.get("series") or {}).get("current_account") or {}
    periods = sorted(series.keys())
    if len(periods) >= 12:
        window = periods[-12:]
        total = sum(series[p] for p in window)
        entry["trailing_12m"] = {
            "value": round(total, 2), "period_end": window[-1], "period_start": window[0],
        }
        entry["value"] = entry["trailing_12m"]["value"]
        entry["period"] = window[-1]
        entry["unit"] = "USD million (trailing 12mo)"
    else:
        entry["value"] = latest["current_account"]
        entry["period"] = period
        entry["unit"] = "USD million (single month)"
    indicators["current_account"] = entry


def _fold_tourist_arrivals(indicators):
    d = _load(SRC_TOUR)
    if not d:
        return
    latest = d["meta"]["latest"]
    ttm = d["meta"].get("trailing_12m")
    if not latest or latest.get("foreign_arrivals_thousand") is None:
        return
    period = latest["period"]
    entry = {
        "latest_month": {"value_thousand": latest["foreign_arrivals_thousand"], "period": period,
                         "preliminary": period in (d["meta"].get("preliminary_periods") or [])},
        "source": "Bank of Thailand — foreign tourist arrivals (Immigration Bureau feed), monthly",
    }
    if ttm and ttm.get("sum_thousand") is not None:
        entry["trailing_12m"] = {
            "value_million": round(ttm["sum_thousand"] / 1000.0, 2),
            "period_end": ttm["periods"][-1], "period_start": ttm["periods"][0],
        }
        entry["value"] = entry["trailing_12m"]["value_million"]
        entry["period"] = ttm["periods"][-1]
        entry["unit"] = "million persons (trailing 12mo)"
        # MOMENTUM (was dropped): the card showed a directionless "32.16M". Tourism is the income
        # backdrop for borrowers in tourist provinces (Phuket/Krabi/Chon Buri/Chiang Mai), so its
        # DIRECTION is a portfolio-risk read (obj #1). The MEASURED monthly series already committed
        # here carries 100+ months — enough for a real YoY and a trend line, which the sibling
        # indicators (household_debt_gdp, policy_rate) both ship. Computed from the series only (never
        # from the base's own previous value) so a --check re-run reproduces byte-for-byte.
        # A rolling trailing-12m sum is used for BOTH, not raw monthly arrivals, because a single
        # month is a season — the TTM line is the non-seasonal momentum that matches the headline.
        srs = (d.get("series") or {}).get("foreign_arrivals_thousand") or {}
        months = sorted(srs.keys())
        roll = []  # (period_end, TTM sum in million persons), one per month with >=12 months behind it
        for i in range(11, len(months)):
            w = months[i - 11:i + 1]
            roll.append((months[i], round(sum(srs[p] for p in w) / 1000.0, 2)))
        # YoY: current TTM vs the TTM ending 12 months earlier (a clean like-for-like annual move).
        if len(roll) >= 13:
            cur, prior = roll[-1][1], roll[-13][1]
            if prior:
                entry["yoy_change"] = round((cur - prior) / prior * 100.0, 1)
        # Trend: the last 12 rolling-TTM points — a full year of the TTM's own trajectory.
        if len(roll) >= 2:
            entry["trend"] = [v for _p, v in roll[-12:]]
    else:
        entry["value"] = round(latest["foreign_arrivals_thousand"] / 1000.0, 3)
        entry["period"] = period
        entry["unit"] = "million persons (single month)"
    indicators["tourist_arrivals"] = entry


def _fold_policy_rate(indicators):
    """OVERRIDE policy_rate with the BOT-direct MEASURED reading.

    pull_macro.py sets policy_rate from BIS — a monthly-but-derivative republication of BOT's own
    number, attributed to BIS. We already pull the primary source (BOT/MPC's own decision-history
    XLSX, `pipeline/pull_bot_policy_rate.py` → `source-data/bot_policy_rate.json`, 200+ meetings
    since 2000, anchor-verified on every pull) but it was orphaned — no builder consumed it. This
    folds it in so the headline policy-rate chip reads the authoritative primary at MEETING
    granularity (not a quarterly proxy) and is labelled BOT, not BIS. The headline value/period/YoY
    match BIS to the decimal (BIS just republishes the same rate); what changes is the provenance
    label and a correct meeting-level trend. Fully recomputed from bot_policy_rate.json only (never
    from the base's own policy_rate), so a --check re-run reproduces byte-for-byte. Absent input →
    leave pull_macro.py's BIS reading in place (graceful degrade, same as every other fold)."""
    d = _load(SRC_POLICY)
    if not d:
        return
    latest = d.get("latest") or {}
    hist = sorted((d.get("history") or []), key=lambda m: m["date"])
    if latest.get("rate") is None or not latest.get("date") or not hist:
        return
    y, mm, _dd = latest["date"].split("-")
    period = "%s-%s" % (y, mm)
    # YoY: the rate set by the most recent meeting on/before the same calendar day one year earlier
    # (ISO date strings compare lexicographically). round to kill float noise.
    target = "%04d-%s-%s" % (int(y) - 1, mm, _dd)
    prior = [m for m in hist if m["date"] <= target]
    ref = prior[-1] if prior else hist[0]
    yoy = round(latest["rate"] - ref["rate"], 2)
    # Meeting-level trend: the last six decisions' rates, chronological — the same length the
    # sparkline drew for the BIS quarterly trend, but at the cadence the rate actually moves.
    trend = [m["rate"] for m in hist[-6:]]
    indicators["policy_rate"] = {
        "value": latest["rate"], "period": period, "yoy_change": yoy, "unit": "%",
        "source": "BOT (ธปท./กนง.) — 1-day repo, MPC decision history",
        "trend": trend,
        "as_of": latest["date"], "meeting": latest.get("meeting"),
        "decision": latest.get("decision_en"), "n_meetings": len(hist),
    }


# The base file's OWN "indicators" dict is the starting point for every field this builder does
# NOT touch (household_debt_gdp, lending_rate, usd_thb — carried through unchanged;
# and cpi_inflation itself IF source-data/tpso_cpi.json happens to be absent on a given run, so a
# missing input degrades to "leave pull_macro.py's own reading alone" rather than dropping the
# card). Every field this builder DOES fold (cpi_inflation, gdp_growth, current_account,
# tourist_arrivals) is fully recomputed from its OWN source-data/ input when that input is present —
# never derived from whatever value is already sitting in the base — which is what makes re-running
# the builder idempotent (a --check run reads the just-written file as its own base and must
# reproduce it byte-for-byte; if any folded field depended on its OWN previous value, a second run
# would drift).
def build():
    if not os.path.exists(OUT):
        sys.exit(3)
    base = json.load(open(OUT, encoding="utf-8"))
    indicators = dict(base.get("indicators") or {})
    _fold_cpi(indicators)
    _fold_gdp(indicators)
    _fold_current_account(indicators)
    _fold_tourist_arrivals(indicators)
    _fold_policy_rate(indicators)
    meta = dict(base.get("meta") or {})
    meta["folded_by"] = "pipeline/build_macro_indicators.py"
    meta["folded_sources"] = {
        "cpi_inflation": "source-data/tpso_cpi.json" if os.path.exists(SRC_CPI) else None,
        "gdp_growth": "source-data/nesdc_gdp.json" if os.path.exists(SRC_GDP) else None,
        "current_account": "source-data/bot_current_account.json" if os.path.exists(SRC_CA) else None,
        "tourist_arrivals": "source-data/bot_tourist_arrivals.json" if os.path.exists(SRC_TOUR) else None,
        "policy_rate": "source-data/bot_policy_rate.json" if os.path.exists(SRC_POLICY) else None,
    }
    return {"meta": meta, "indicators": indicators}


def _dumps(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="byte-exact reproduction check against the committed "
                         "platform/data/macro_indicators.json; exit 3 SKIP if the base file is "
                         "absent, exit 1 on drift")
    args = ap.parse_args()
    if not os.path.exists(OUT):
        print("build_macro_indicators.py: platform/data/macro_indicators.json absent — run "
              "pull_macro.py first (SKIP).")
        sys.exit(3)
    before = json.load(open(OUT, encoding="utf-8")).get("indicators") or {}
    payload = _dumps(build())
    if args.check:
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_macro_indicators.py --check: drifted — re-run the builder.")
        print("build_macro_indicators.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    after = json.loads(payload)["indicators"]
    print("wrote %s" % OUT)
    for k in ("cpi_inflation", "gdp_growth", "current_account", "tourist_arrivals", "policy_rate"):
        b, a = before.get(k), after.get(k)
        if b == a:
            print("  %-16s unchanged: %s" % (k, a))
        else:
            print("  %-16s %s  ->  %s" % (k, b, a))


if __name__ == "__main__":
    main()
