#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_real_tape.py — REAL loan-tape ingest (objective #1's biggest unlock, landed 2026-07-21)

Streams the owner-side loan-level xlsx export (382,735 accounts, 60 columns) into committed
NO-PII AGGREGATES. The raw file NEVER enters the repo; no account/application numbers are read
into any output; every published cell is suppressed below MIN_CELL accounts.

  in : the xlsx export (owner's disk) — path via --src or REAL_TAPE_XLSX env; NOT in git
  out: source-data/staging/real_tape_aggregates.json   committed no-PII aggregates, which the
       deterministic gated builder (build_tape_layers.py) projects into platform layers.

Like the pull_* scripts this ingest is NOT in the determinism gate (its input is off-repo);
everything downstream of the staging file is. Determinism inside the output: the months-on-book
anchor is the NEWEST disbursement year-month IN THE DATA — never wall clock.

Provenance: MEASURED — AutoX loan tape export "Car_Brand_Group data V2" (owner-side, no-PII
aggregation at ingest). First-payment-default: the F_FPD column is CATEGORICAL text; any value
other than "Regular"/blank counts as FPD-flagged (v1 read it numerically and got 0 — fixed).

  python3 ingest_real_tape.py            # default src, writes staging
  python3 ingest_real_tape.py --src "C:\\path\\to\\tape.xlsx"
"""
import argparse
import collections
import json
import os
import re
import sys

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "staging", "real_tape_aggregates.json")
DEFAULT_SRC = r"C:\Users\Kaustav Bagchi\Downloads\alibaba receipts\Car_Brand_Group data V2.xlsx"

MIN_CELL = 30           # publication floor: cells with fewer accounts are dropped
EARLY = "2."            # dpd bucket prefix: X-days (late but <30dpd — the pre-emptive window)
BAD = ("3.", "4.", "5.", "6.", "7.", "8.", "9.")   # 30+dpd buckets
MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}


def norm_branch(s):
    return re.sub(r"เงินไชโย|สาขา|\s+", "", str(s or ""))


def fnum(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def new_cell():
    # [n, n_early, n_dpd30p, n_fpd, os_sum, npat_margin_sum, eval_sum, n_eval]
    return [0, 0, 0, 0, 0.0, 0.0, 0.0, 0]


def pack(d, floor=MIN_CELL, top=None):
    items = [(k, a) for k, a in d.items() if a[0] >= floor]
    items.sort(key=lambda kv: -kv[1][0])
    if top:
        items = items[:top]
    out = {}
    for k, a in items:
        row = {"n": a[0],
               "early_pct": round(a[1] * 100.0 / a[0], 2),
               "dpd30p_pct": round(a[2] * 100.0 / a[0], 2),
               "fpd_pct": round(a[3] * 100.0 / a[0], 2),
               "os_sum": round(a[4], 0),
               "npat_margin_avg": round(a[5] / a[0], 0)}
        if a[7]:
            row["eval_avg"] = round(a[6] / a[7], 0)
        out[k] = row
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.environ.get("REAL_TAPE_XLSX", DEFAULT_SRC))
    a = ap.parse_args()
    if not os.path.exists(a.src):
        sys.exit("ingest_real_tape.py: tape not found at %s (set --src or REAL_TAPE_XLSX)" % a.src)

    # branch master join: normalized branch name -> (prov, district, region, code)
    master = json.load(open(os.path.join(ROOT, "source-data", "branches_final.json"),
                            encoding="utf-8"))
    mrows = master if isinstance(master, list) else master.get("branches", [])
    mname = {}
    for m in mrows:
        mname.setdefault(norm_branch(m.get("name")),
                         (m.get("prov"), m.get("district"), m.get("region"), m.get("code")))

    wb = openpyxl.load_workbook(a.src, read_only=True)
    ws = wb["default_1"]
    rows = ws.iter_rows(values_only=True)
    hdr = list(next(rows))
    ix = {h: i for i, h in enumerate(hdr)}

    def g(r, c):
        v = r[ix[c]]
        return v if v not in ("", None) else None

    tabs = {k: collections.defaultdict(new_cell) for k in (
        "province", "prov_x_occ", "region", "area", "occupation", "occ_fine", "income_tier",
        "ltv_range", "vintage_ym", "vehicle_type", "product_group", "coll_age",
        "brand", "brand_x_collage", "brand_x_region", "vehicle_x_ltv", "model",
        "occ_x_income", "occ_x_region", "branch")}
    n = matched = 0
    anchor = ""            # newest disbursement YYYY-MM in the data (determinism anchor)
    vint_curve = collections.defaultdict(new_cell)   # vintage-year|months-on-book-band

    for r in rows:
        n += 1
        dpd = str(g(r, "account_disb_dpd_bucket") or "?")
        early = dpd.startswith(EARLY)
        bad = dpd.startswith(BAD)
        fpd_raw = str(g(r, "F_FPD") or "").strip()
        fpd = bool(fpd_raw) and fpd_raw.lower() not in ("regular", "0", "n", "none")
        osamt = fnum(g(r, "OS")) or 0.0
        npat = fnum(g(r, "NPAT - Margin")) or 0.0
        ev = fnum(g(r, "account_disb_eval_amt_adj"))
        yr = str(g(r, "account_disb_first_disb_dt_Year") or "?")
        mo = MONTHS.get(str(g(r, "account_disb_first_disb_dt_Month") or ""), 0)
        ym = "%s-%02d" % (yr, mo) if (yr.isdigit() and mo) else None
        if ym and ym > anchor:
            anchor = ym
        br = str(g(r, "account_disb_Booking_Branch_Name") or "(blank)")
        hit = mname.get(norm_branch(br))
        prov = hit[0] if hit and hit[0] else "(unjoined)"
        if hit:
            matched += 1
        occ = str(g(r, "account_disb_ocp_grp") or "(blank)")
        vals = {
            "province": prov,
            "prov_x_occ": prov + "|" + occ,
            "region": str(g(r, "account_disb_Region") or "(blank)"),
            "area": str(g(r, "account_disb_Area") or "(blank)"),
            "occupation": occ,
            "occ_fine": str(g(r, "customer_occp_desc") or "(blank)"),
            "income_tier": str(g(r, "account_disb_income_tier") or "(blank)"),
            "ltv_range": str(g(r, "LTV Range") or "(blank)"),
            "vintage_ym": ym or "(blank)",
            "vehicle_type": str(g(r, "account_disb_Vehicle_Type") or "(blank)"),
            "product_group": str(g(r, "account_disb_Product_Group") or "(blank)"),
            "coll_age": str(g(r, "account_disb_Coll_Age_originate_Group") or "(blank)"),
            "brand": str(g(r, "account_disb_car_brand") or "(blank)"),
            "brand_x_collage": str(g(r, "account_disb_car_brand") or "(blank)") + "|" +
                               str(g(r, "account_disb_Coll_Age_originate_Group") or "(blank)"),
            "brand_x_region": str(g(r, "account_disb_car_brand") or "(blank)") + "|" +
                              str(g(r, "account_disb_Region") or "(blank)"),
            "vehicle_x_ltv": str(g(r, "account_disb_Vehicle_Type") or "(blank)") + "|" +
                             str(g(r, "LTV Range") or "(blank)"),
            "model": (str(g(r, "account_disb_car_brand") or "") + " " +
                      str(g(r, "account_disb_car_model") or "")).strip() or "(blank)",
            "occ_x_income": occ + "|" + str(g(r, "account_disb_income_tier") or "(blank)"),
            "occ_x_region": occ + "|" + str(g(r, "account_disb_Region") or "(blank)"),
            "branch": br,
        }
        for tab, key in vals.items():
            c = tabs[tab][key]
            c[0] += 1
            c[1] += 1 if early else 0
            c[2] += 1 if bad else 0
            c[3] += 1 if fpd else 0
            c[4] += osamt
            c[5] += npat
            if ev is not None:
                c[6] += ev
                c[7] += 1
        if n % 100000 == 0:
            print("  rows", n, flush=True)

    # vintage curves need the anchor — second pass over the per-ym tab (no re-read of the tape):
    # months-on-book for a vintage-month = anchor - ym; band by 6-month steps.
    ay, am = int(anchor[:4]), int(anchor[5:7])
    for ym, c in tabs["vintage_ym"].items():
        if len(ym) == 7 and ym[:4].isdigit():
            mob = (ay - int(ym[:4])) * 12 + (am - int(ym[5:7]))
            band = "%02d-%02dm" % (mob // 6 * 6, mob // 6 * 6 + 5)
            key = ym[:4] + "|" + band
            vc = vint_curve[key]
            for i in range(8):
                vc[i] += c[i]

    out = {"meta": {
        "generated_by": "pipeline/ingest_real_tape.py",
        "label": "MEASURED — AutoX real loan tape (owner-side no-PII aggregation; account-level "
                 "raw never leaves the owner's disk; cells under %d accounts suppressed)." % MIN_CELL,
        "source": "Car_Brand_Group data V2.xlsx (loan-level export, 60 columns)",
        "n_accounts": n,
        "branch_join": {"matched": matched, "pct": round(matched * 100.0 / n, 2)},
        "mob_anchor": anchor,
        "fpd_note": "F_FPD categorical: any non-Regular value counts as FPD-flagged",
        "min_cell": MIN_CELL,
    }, "tabs": {}}
    for k, d in tabs.items():
        out["tabs"][k] = pack(d, top=400 if k in ("model", "occ_fine", "branch") else None)
    out["tabs"]["vintage_curve"] = pack(vint_curve, floor=100)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("wrote %s — %d accounts, %d tabs, join %.1f%%, anchor %s"
          % (OUT, n, len(out["tabs"]), matched * 100.0 / n, anchor))


if __name__ == "__main__":
    main()
