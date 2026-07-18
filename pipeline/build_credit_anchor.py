#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_credit_anchor.py — project the BoT credit-quality anchor into the app (objective #1).

Reads the MEASURED source-data/bot_credit.json (pulled by pull_bot_credit.py) and emits the small
app-facing layer platform/data/credit_anchor.json that the risk-trend readout consumes: the national
NPL-by-loan-type scale + household-debt context, in a slim display-ready shape.

WHY A SEPARATE LAYER: the app should read a tiny, stable file — not the full puller output. This is a
pure, deterministic projection (no network); --check byte-compares, and SKIPs (exit 3) if the source
source-data/bot_credit.json is absent (a network-pulled input, not drift).

The anchor is CONTEXT for the ESTIMATED 0-100 branch-risk composite (build_branch_risk.py): it shows
the real measured NPL scale the triage score sits against. It does NOT feed the composite.

Run:
  python3 build_credit_anchor.py           # rebuild platform/data/credit_anchor.json
  python3 build_credit_anchor.py --check   # verify byte-exact (SKIP if source absent)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data", "bot_credit.json")
OUT = os.path.join(ROOT, "platform", "data", "credit_anchor.json")


def build(src):
    fg = src["figures"]
    m = src["meta"]
    npl = fg["system_npl_pct"]
    gdp = fg["household_debt_to_gdp_pct"]
    hh = fg["household_debt_thb"]
    auto = fg["auto_hp_household_debt_thb"]
    ahp = fg["auto_hp_npl_pct"]
    return {
        "meta": {
            "title": "BoT credit-quality anchor — measured NPL scale for the risk readout",
            "generated_by": "pipeline/build_credit_anchor.py",
            "label": "MEASURED — Bank of Thailand. The real-world NPL scale + household-debt "
                     "backdrop the modelled 0-100 branch-risk triage score is read against. "
                     "Context only; it does not feed the composite.",
            "source": m.get("source", ""),
            "provenance": "MEASURED. Pure projection of source-data/bot_credit.json (BoT FSR 2024 "
                          "text layer + BoT statistics report 984). Nothing modelled.",
            "pulled": m.get("pulled"),
        },
        # Headline metrics, display-ready. Each carries its own vintage + source page/table.
        "metrics": [
            {"key": "system_npl", "label": "System NPL",
             "value": npl["value"], "display": "%.1f%%" % npl["value"], "unit": "%",
             "scope": npl["scope"], "vintage": npl["vintage"], "source": npl["source"],
             "source_url": npl["source_url"]},
            {"key": "household_debt_to_gdp", "label": "Household debt / GDP",
             "value": gdp["value"], "display": "%.1f%%" % gdp["value"], "unit": "% of GDP",
             "scope": gdp["scope"], "vintage": gdp["vintage"], "source": gdp["source"],
             "source_url": gdp["source_url"]},
            {"key": "household_debt", "label": "Household debt",
             "value": hh["value_tn_thb"], "display": "฿%.1ftn" % hh["value_tn_thb"], "unit": "THB",
             "scope": hh["scope"], "vintage": hh["vintage"], "source": hh["source"],
             "source_url": hh["source_url"]},
            {"key": "auto_hp_debt", "label": "Vehicle hire-purchase debt",
             "value": auto["value_tn_thb"], "display": "฿%.2ftn" % auto["value_tn_thb"], "unit": "THB",
             "share_of_hh_debt_pct": auto["share_of_hh_debt_pct"],
             "scope": auto["scope"], "vintage": auto["vintage"], "source": auto["source"],
             "source_url": auto["source_url"]},
        ],
        # The auto hire-purchase NPL split is honestly absent (behind BoT's geoblocked data API).
        "auto_hp_npl": {"value": ahp["value"], "reason_absent": ahp["reason_absent"]},
        "context": (
            "The estimated 0-100 branch-risk score is a TRIAGE RANK, not a predicted NPL. "
            "System NPL %.1f%% and household debt ฿%.1ftn (%.0f%% of GDP), of which vehicle "
            "hire-purchase ฿%.2ftn, are the measured real-world scale it is read against."
        ) % (npl["value"], hh["value_tn_thb"], gdp["value"], auto["value_tn_thb"]),
    }


def _dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify platform/data/credit_anchor.json reproduces byte-exact from "
                         "source-data/bot_credit.json; exit 3 SKIP if the source is absent")
    args = ap.parse_args()

    if args.check:
        if not os.path.exists(SRC):
            print("build_credit_anchor.py --check: SKIP (source-data/bot_credit.json absent — "
                  "network-pulled input, not drift)")
            sys.exit(3)
        if not os.path.exists(OUT):
            sys.exit("build_credit_anchor.py --check: platform/data/credit_anchor.json missing — "
                     "run python3 pipeline/build_credit_anchor.py")
        src = json.load(open(SRC, encoding="utf-8"))
        if _dumps(build(src)) != open(OUT, encoding="utf-8").read():
            sys.exit("build_credit_anchor.py --check: credit_anchor.json drifted — re-run "
                     "python3 pipeline/build_credit_anchor.py")
        print("build_credit_anchor.py --check: OK (byte-exact)")
        return

    if not os.path.exists(SRC):
        sys.exit("build_credit_anchor.py: source-data/bot_credit.json absent — run "
                 "python3 pipeline/pull_bot_credit.py first")
    src = json.load(open(SRC, encoding="utf-8"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(_dumps(build(src)))
    print("wrote %s" % OUT)
    for mt in build(src)["metrics"]:
        print("  %-26s %s  (%s · %s)" % (mt["label"], mt["display"], mt["vintage"], mt["source"]))


if __name__ == "__main__":
    main()
