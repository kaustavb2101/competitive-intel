#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_macro.py — MEASURED Thai macro-risk indicators (BIS + World Bank), cloud-reachable, no key.

For a title-loan lender, borrower LEVERAGE and rates are core PD drivers. Two keyless, cloud-reachable
sources (BOT's own API is geoblocked — laptop-only):
  * BIS Statistics (stats.bis.org, SDMX-JSON) — HOUSEHOLD DEBT-to-GDP (quarterly, authoritative) and
    the central-bank POLICY RATE (monthly).
  * World Bank (api.worldbank.org) — CPI inflation, bank lending rate, USD/THB (annual).

OUTPUT: source-data/macro_indicators.json — each indicator's latest value + period + a short trend +
YoY where computable. Surfaces on the macro/Home card as a "household leverage / rates" readout.

  python3 pull_macro.py             # pull + write source-data/macro_indicators.json
  python3 pull_macro.py --stamp 2026-07-05
  python3 pull_macro.py --selftest  # offline parse check
"""
import argparse, json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "platform", "data", "macro_indicators.json")   # served directly to the frontend
UA = {"User-Agent": "Mozilla/5.0 (compatible; autox-credit-intel/1.0)"}
BIS = "https://stats.bis.org/api/v2/data/dataflow/BIS"
WB = "https://api.worldbank.org/v2/country/THA/indicator"


def _get(url, headers=None, tries=4):
    import time
    h = dict(UA); h.update(headers or {})
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e; time.sleep(1.5 * (i + 1))
    raise RuntimeError("GET failed after %d tries: %s\n  %s" % (tries, last, url))


def bis_series(flow, key, n=8):
    """{period_label: float} for a single BIS SDMX series, oldest→newest."""
    url = "%s/%s/%s?lastNObservations=%d" % (BIS, flow, key, n)
    d = _get(url, {"Accept": "application/vnd.sdmx.data+json"})["data"]
    labels = [v.get("name") or v.get("id")
              for v in d["structure"]["dimensions"]["observation"][0]["values"]]
    obs = list(d["dataSets"][0]["series"].values())[0]["observations"]
    out = {}
    for idx, arr in obs.items():
        try:
            out[labels[int(idx)]] = round(float(arr[0]), 3)
        except (ValueError, TypeError, IndexError):
            pass
    return out


def wb_latest(code):
    """(period, value) latest non-null World Bank annual observation."""
    d = _get("%s/%s?format=json&mrv=6" % (WB, code))
    for row in (d[1] if isinstance(d, list) and len(d) > 1 else []):
        if row.get("value") is not None:
            return row["date"], round(float(row["value"]), 2)
    return None, None


def _series_out(series, unit, source, yoy_lag):
    if not series:
        return None
    periods = list(series)          # already oldest→newest from BIS lastNObservations
    latest_p = periods[-1]
    latest_v = series[latest_p]
    yoy = None
    if len(periods) > yoy_lag:
        prior = series[periods[-1 - yoy_lag]]
        yoy = round(latest_v - prior, 2)      # change in pp/level (already a rate/ratio)
    return {"value": latest_v, "period": latest_p, "yoy_change": yoy, "unit": unit,
            "source": source, "trend": [series[p] for p in periods[-6:]]}


def build(hh, pr, cpi, lend, fx, stamp):
    ind = {}
    ind["household_debt_gdp"] = _series_out(hh, "% of GDP", "BIS", 4)   # quarterly → 4-qtr YoY
    ind["policy_rate"] = _series_out(pr, "%", "BIS", 12)               # monthly → 12-mo YoY
    cp, cv = cpi; lp, lv = lend; fp, fv = fx
    ind["cpi_inflation"] = {"value": cv, "period": cp, "unit": "% YoY", "source": "World Bank"} if cv is not None else None
    ind["lending_rate"] = {"value": lv, "period": lp, "unit": "%", "source": "World Bank"} if lv is not None else None
    ind["usd_thb"] = {"value": fv, "period": fp, "unit": "THB/USD", "source": "World Bank"} if fv is not None else None
    return {
        "meta": {
            "source": "BIS Statistics (stats.bis.org, household debt + policy rate) + World Bank "
                      "(api.worldbank.org, CPI/lending rate/FX). Keyless, cloud-reachable; BOT's own "
                      "API is geoblocked (laptop-only).",
            "label": "MEASURED — Thai macro-risk indicators (leverage · rates · inflation · FX)",
            "generated_by": "pipeline/pull_macro.py",
            "pulled": stamp,
            "note": "Household debt-to-GDP is the core borrower-leverage signal (falling = deleveraging "
                    "= easing risk). yoy_change is the pp/level change over ~1 year.",
        },
        "indicators": {k: v for k, v in ind.items() if v is not None},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default="")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        hh = {"2024-Q4": 88.8, "2025-Q1": 88.0, "2025-Q2": 87.8, "2025-Q3": 87.6, "2025-Q4": 87.5}
        doc = build(hh, {}, ("2025", -0.13), ("2025", 3.94), ("2025", 32.88), "test")
        i = doc["indicators"]["household_debt_gdp"]
        assert i["value"] == 87.5 and i["yoy_change"] == -1.3, i
        print("selftest OK:", i)
        return
    hh = bis_series("WS_TC/2.0", "Q.TH.H.A.M.770.A", 8)
    try:
        pr = bis_series("WS_CBPOL/1.0", "M.TH", 14)
    except Exception:
        pr = {}
    doc = build(hh, pr, wb_latest("FP.CPI.TOTL.ZG"), wb_latest("FR.INR.LEND"), wb_latest("PA.NUS.FCRF"), a.stamp)
    if "household_debt_gdp" not in doc["indicators"]:
        sys.exit("pull_macro.py: BIS household-debt series empty — API may have changed.")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print("wrote %s" % OUT)
    for k, v in doc["indicators"].items():
        print("  %-20s %8s %-10s (%s%s)" % (k, v["value"], v["unit"], v["period"],
              ", YoY %+g" % v["yoy_change"] if v.get("yoy_change") is not None else ""))


if __name__ == "__main__":
    main()
