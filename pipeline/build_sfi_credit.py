#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_sfi_credit.py — Thai Specialized-Financial-Institution system NPL ratio (MEASURED macro, obj #1).

Distils two FPO (Fiscal Policy Office) published quarterly aggregates for Thailand's Specialized
Financial Institutions (SFIs — สถาบันการเงินเฉพาะกิจ: the state-owned banks GSB, BAAC, GHB, SME Bank,
EXIM, Islamic Bank, …) into one clean national credit-quality time-series:

    NPL ratio = gross NPL outstanding / gross credit outstanding   (per quarter, %)

WHY IT MATTERS (objective #1, portfolio risk — a leading-indicator BACKDROP, not a per-branch measure):
The SFI system is the closest PUBLIC read on the household + agricultural repayment stress that AutoX's
own borrowers live inside. GSB is the dominant household lender and BAAC the dominant rural/agri lender;
when their system NPL ratio turns up, broad household/farm repayment stress is rising — and AutoX's
riskier subprime title book tends to move with (often ahead-tracked by) that macro tide. This is a
national aggregate CONTEXT signal, clearly NOT AutoX's book, NOT the non-bank title-lender sector, and
NOT per-province. It makes no open/close/expand call.

INPUT (both committed, MEASURED, tiny — a straight FPO CSV each, one row per quarter × item):
  source-data/fpo_sfi_npl.csv    — FPO msi_d501: gross + net NPL outstanding of SFIs (THB million)
  source-data/fpo_sfi_credit.csv — FPO msi_d301: gross + net credit outstanding of SFIs (THB million)
  Columns (Thai): ชุดข้อมูลเดือน (quarter-end month) / ชุดข้อมูลปี (year, Buddhist Era) /
                  รายการ (item) / ค่าข้อมูล (value, THB million).

OUTPUT platform/data/sfi_credit.json — { meta, series[] }. series is every quarter both files share,
oldest→newest, each { period, npl_gross, npl_net, credit_gross, credit_net, npl_ratio }. Every number
is copied straight from the two government CSVs; the only derived field is npl_ratio = npl_gross /
credit_gross × 100 (a ratio of two measured aggregates — no modelling, no synthesis).

DETERMINISTIC + NETWORK-FREE. Output is a pure function of the two committed CSVs, so --check is
byte-exact (both inputs are git-tracked, unlike the gitignored datagoth pulls — this builder never SKIPs).

Refresh (quarterly; run from anywhere — catalog.fpo.go.th is reachable from CI): re-download the two
pinned resource URLs (see SRC_* below) over source-data/fpo_sfi_*.csv and re-run this builder.

  python3 build_sfi_credit.py
  python3 build_sfi_credit.py --check
"""
import argparse, csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NPL_IN = os.path.join(ROOT, "source-data", "fpo_sfi_npl.csv")
CREDIT_IN = os.path.join(ROOT, "source-data", "fpo_sfi_credit.csv")
OUT = os.path.join(ROOT, "platform", "data", "sfi_credit.json")

# Pinned FPO open-data resources (catalog.fpo.go.th). Constants for honest provenance in meta; the
# committed CSVs are the byte source of truth, so re-pulling the same resource is a no-op.
SRC_NPL = ("https://catalog.fpo.go.th/dataset/cd6c7ed9-62de-4ec7-a964-f42657f54050/resource/"
           "4e755e4c-d6a1-4204-a185-9ab2acaf06b8/download/msi_d501_csv.csv")
SRC_CREDIT = ("https://catalog.fpo.go.th/dataset/6966fc04-8ab5-4427-a27d-a10b324c0c99/resource/"
              "0ba32040-4bc2-47ae-8482-984b36aa41eb/download/msi_d301_csv.csv")

# quarter-end month (Thai) -> (quarter label, sort order). FPO publishes at calendar quarter-ends.
TH_Q = {"มีนาคม": ("Q1", 1), "มิถุนายน": ("Q2", 2), "กันยายน": ("Q3", 3), "ธันวาคม": ("Q4", 4)}

# รายการ (item) strings, verbatim from the FPO files.
NPL_GROSS = "ยอดคงค้าง NPL รวม (Gross)"
NPL_NET = "ยอดคงค้าง NPL สุทธิ (Net)"
CREDIT_GROSS = "ยอดคงค้างสินเชื่อรวม (Gross)"
CREDIT_NET = "ยอดคงค้างสินเชื่อสุทธิ (Net)"

COL_MONTH, COL_YEAR, COL_ITEM, COL_VALUE = ("ชุดข้อมูลเดือน", "ชุดข้อมูลปี", "รายการ", "ค่าข้อมูล")


def _load(path):
    """(year_ce, q_order, q_label) -> {item: value_float}. Skips non-quarter-end months honestly."""
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            mo = (row.get(COL_MONTH) or "").strip()
            if mo not in TH_Q:
                continue
            q, order = TH_Q[mo]
            try:
                year_ce = int((row.get(COL_YEAR) or "").strip()) - 543   # Buddhist Era -> CE
                val = float((row.get(COL_VALUE) or "").strip().replace(",", ""))
            except ValueError:
                continue
            out.setdefault((year_ce, order, q), {})[(row.get(COL_ITEM) or "").strip()] = val
    return out


def build():
    npl = _load(NPL_IN)
    credit = _load(CREDIT_IN)
    keys = sorted(set(npl) & set(credit))   # only quarters present (and complete) in BOTH files

    series = []
    for k in keys:
        ng, nn = npl[k].get(NPL_GROSS), npl[k].get(NPL_NET)
        cg, cn = credit[k].get(CREDIT_GROSS), credit[k].get(CREDIT_NET)
        if ng is None or cg is None or cg <= 0:
            continue                        # a ratio needs both gross legs; skip an incomplete quarter
        year_ce, _order, q = k
        series.append({
            "period": "%d-%s" % (year_ce, q),
            "npl_gross": round(ng, 1),
            "npl_net": round(nn, 1) if nn is not None else None,
            "credit_gross": round(cg, 1),
            "credit_net": round(cn, 1) if cn is not None else None,
            "npl_ratio": round(ng / cg * 100, 2),
        })

    latest = series[-1] if series else None
    prev = series[-2] if len(series) >= 2 else None
    year_ago = series[-5] if len(series) >= 5 else None   # 4 quarters back
    # 5-year (20-quarter) window for a peak/trough that reflects the current cycle, not 2008.
    window = series[-20:] if len(series) >= 1 else []
    peak = max(window, key=lambda r: r["npl_ratio"]) if window else None
    trough = min(window, key=lambda r: r["npl_ratio"]) if window else None

    def _pp(a, b):
        return round(a["npl_ratio"] - b["npl_ratio"], 2) if (a and b) else None

    meta = {
        "generated_by": "pipeline/build_sfi_credit.py",
        "label": ("MEASURED quarterly system NPL ratio of Thailand's Specialized Financial Institutions "
                  "(SFIs — the state-owned banks GSB / BAAC / GHB / SME Bank / EXIM / Islamic Bank). "
                  "NPL ratio = gross NPL outstanding / gross credit outstanding. A national leading-"
                  "indicator BACKDROP for household + agri repayment stress — NOT AutoX's own book, "
                  "NOT the non-bank title-lender sector, and NOT per-province."),
        "source": ("MEASURED — FPO (Fiscal Policy Office) open-data quarterly SFI aggregates, "
                   "catalog.fpo.go.th: msi_d501 (gross + net NPL outstanding) and msi_d301 (gross + net "
                   "credit outstanding), both in THB million. The NPL ratio is those two published "
                   "aggregates divided — no modelling, no synthesis."),
        "provenance": "measured (FPO published SFI system aggregates; NPL ratio = gross NPL / gross credit)",
        "source_urls": {"npl": SRC_NPL, "credit": SRC_CREDIT},
        "unit": "THB million (levels); % (npl_ratio)",
        "vintage": latest["period"] if latest else None,
        "latest": latest,
        "prev": prev,
        "year_ago": year_ago,
        "qoq_ratio_delta_pp": _pp(latest, prev),
        "yoy_ratio_delta_pp": _pp(latest, year_ago),
        "peak_ratio_5y": {"period": peak["period"], "npl_ratio": peak["npl_ratio"]} if peak else None,
        "trough_ratio_5y": {"period": trough["period"], "npl_ratio": trough["npl_ratio"]} if trough else None,
        "n_quarters": len(series),
        "range_from": series[0]["period"] if series else None,
        "range_to": latest["period"] if latest else None,
        "objective": ("Obj #1 macro backdrop: the SFI system NPL ratio is the closest public read on the "
                      "household + agri repayment stress AutoX's borrowers sit inside (GSB = household, "
                      "BAAC = rural/agri). A rising ratio flags broad repayment stress that AutoX's "
                      "riskier subprime title book tends to move with. Context only — no branch action."),
        "gaps": [
            "SYSTEM aggregate for all SFIs combined — NOT AutoX, NOT the non-bank title-lender sector, "
            "and NOT split by institution or province. Read it as a macro tide, not AutoX's own NPL.",
            "SFI books skew to policy/subsidised lending (agri, housing, SME) — their absolute NPL LEVEL "
            "is not comparable to a subprime title book; the useful signal is the DIRECTION / trend, not "
            "the level.",
            "Quarterly, published with a lag — a slow structural backdrop, not an acute pulse (the "
            "ThaiWater flood/rain card is the fast obj-#1 counterpart).",
        ],
    }
    return {"meta": meta, "series": series}


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8")
        except Exception: pass

    for p in (NPL_IN, CREDIT_IN):
        if not os.path.exists(p):
            if args.check:
                print("build_sfi_credit.py --check: SKIP (%s absent)" % os.path.relpath(p, ROOT))
                sys.exit(3)
            sys.exit("%s missing — re-pull the FPO SFI resources (see build_sfi_credit.py header)"
                     % os.path.relpath(p, ROOT))

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_sfi_credit.py --check: SKIP (sfi_credit.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_sfi_credit.py --check: sfi_credit.json drifted — run "
                     "python3 pipeline/build_sfi_credit.py")
        print("build_sfi_credit.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    lt = m["latest"] or {}
    print("wrote %s (%d quarters %s→%s; latest %s NPL ratio %.2f%%, YoY %+.2fpp)"
          % (OUT, m["n_quarters"], m["range_from"], m["range_to"], lt.get("period"),
             lt.get("npl_ratio", 0), m["yoy_ratio_delta_pp"] or 0))


if __name__ == "__main__":
    main()
