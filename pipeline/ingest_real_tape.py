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
# The bucket ladder, owner-framed (2026-07-24): monitor customers Current -> NPL, and SEPARATE
# the 180+ legacy stock from the live book (it is late-stage workout inventory, not fresh risk —
# leaving it in distorts every ratio).
EARLY = "2."                    # X-days (late <30dpd — the pre-emptive assistance window)
ROLL = ("3.", "4.")             # 30-89dpd — the roll pipeline (recoverable middle)
NPL_LIVE = ("5.", "6.", "7.")   # 90-179dpd — NPL of the LIVE book
LATE = ("8.", "9.")             # 180+dpd — legacy workout stock, reported SEPARATELY
MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}


from branchkey import norm_branch, master_index  # ONE definition — see pipeline/branchkey.py


def fnum(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def new_cell():
    # [n, n_early, n_roll, n_npl_live(90-179), n_late(180+), n_fpd,
    #  os_sum, os_npl_live, os_late, npat_sum, eval_sum, n_eval]
    return [0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0]


def pack(d, floor=MIN_CELL, top=None):
    items = [(k, a) for k, a in d.items() if a[0] >= floor]
    items.sort(key=lambda kv: -kv[1][0])
    if top:
        items = items[:top]
    out = {}
    for k, a in items:
        n, live_n = a[0], a[0] - a[4]          # live book = everything except 180+ legacy
        os_all, live_os = a[6], a[6] - a[8]
        row = {"n": n,
               "early_pct": round(a[1] * 100.0 / n, 2),     # X-days — assistance window
               "roll_pct": round(a[2] * 100.0 / n, 2),      # 30-89 — roll pipeline
               # NPL of the LIVE book: 90-179dpd over accounts excl. the 180+ legacy stock
               "npl_live_pct": round(a[3] * 100.0 / live_n, 2) if live_n else None,
               "npl_live_os_pct": round(a[7] * 100.0 / live_os, 2) if live_os else None,
               # the legacy stock itself, reported separately (share of ALL accounts / OS)
               "late180_pct": round(a[4] * 100.0 / n, 2),
               "late180_os": round(a[8], 0),
               # continuity lenses (whole-book, incl. legacy)
               "dpd90p_pct": round((a[3] + a[4]) * 100.0 / n, 2),
               "dpd30p_pct": round((a[2] + a[3] + a[4]) * 100.0 / n, 2),
               "fpd_pct": round(a[5] * 100.0 / n, 2),
               "os_sum": round(os_all, 0),
               "npat_margin_avg": round(a[9] / n, 0)}
        if a[11]:
            row["eval_avg"] = round(a[10] / a[11], 0)
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
    mname, mcoll = master_index(
        mrows, lambda m: (m.get("prov"), m.get("district"), m.get("region"), m.get("code")))
    if mcoll:
        print("NOTE: %d master branch name(s) share a join key%s"
              % (len(mcoll), " — CONFLICTING geography, resolve these"
                 if any(c["conflicting"] for c in mcoll) else " (same geography, harmless)"),
              file=sys.stderr)

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
        "occ_x_income", "occ_x_region", "branch", "dpd_bucket", "geo_region",
        # geographic-region crosses (impact cards 2026-07-25): occupation mix + vehicle mix per
        # GEO region (East/Isan/North/South/Central&BKK from the master join) — occ_x_region /
        # vehicle_type alone can't give this (tape Region = internal ops NE1/NE2/…)
        "occ_x_georegion", "vehicle_x_georegion",
        # restructuring status (owner ask 2026-07-24): separate Normal / Pre-emptive / TDR / Skip
        "acc_chng", "chg_x_bucket", "chg_x_occ", "chg_x_region",
        # collateral deep-dive (owner ask 2026-07-24): the collateral BOOK crossed by
        # location / occupation / income / area for acquisition-concentration reads
        "coll_segment", "coll_seg_x_region", "coll_seg_x_area",
        "coll_seg_x_occ", "coll_seg_x_income", "coll_seg_x_bucket",
        "collage_x_region", "collage_x_occ", "collage_x_income", "collage_x_area",
        "brand_x_occ", "brand_x_income", "brand_x_area", "brand_x_ltv",
        "coll_age_x_bucket", "branch_x_seg", "branch_x_brand",
        # branch-level occupation mix (assistance drill 2026-07-28): MEASURED cells >=MIN_CELL
        # only; the thin residual of each branch's book is allocated downstream (ESTIMATED,
        # province occupation mix) by build_tape_layers — never published below the floor here.
        "branch_x_occ")}
    n = matched = 0
    anchor = ""            # newest disbursement YYYY-MM in the data (determinism anchor)
    vint_curve = collections.defaultdict(new_cell)   # vintage-year|months-on-book-band

    for r in rows:
        n += 1
        dpd = str(g(r, "account_disb_dpd_bucket") or "?")
        early = dpd.startswith(EARLY)
        roll = dpd.startswith(ROLL)
        npl_live = dpd.startswith(NPL_LIVE)
        late = dpd.startswith(LATE)
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
        # geographic region from the MASTER join (East/Isan/North/South/Central&BKK) — matches
        # regions.json, so the data book can roll the tape up to the region cards. (Distinct from
        # the tape's own account_disb_Region field, which is an internal ops region NE1/NE2/…)
        region_geo = hit[2] if hit and hit[2] else "(unjoined)"
        if hit:
            matched += 1
        occ = str(g(r, "account_disb_ocp_grp") or "(blank)")
        region = str(g(r, "account_disb_Region") or "(blank)")
        area = str(g(r, "account_disb_Area") or "(blank)")
        income = str(g(r, "account_disb_income_tier") or "(blank)")
        ltv = str(g(r, "LTV Range") or "(blank)")
        brand = str(g(r, "account_disb_car_brand") or "(blank)")
        cage = str(g(r, "account_disb_Coll_Age_originate_Group") or "(blank)")
        cseg = str(g(r, "account_disb_coll_segment") or "(blank)")
        chg = str(g(r, "account_disb_acc_chng_flg_groups_") or "(blank)")
        # coarse monitoring stage for the restructuring/collateral crosses (Current->NPL->legacy)
        stage = ("5_late180" if late else "4_npl_live" if npl_live else
                 "3_roll" if roll else "2_xdays" if early else "1_current")
        vals = {
            "province": prov,
            "prov_x_occ": prov + "|" + occ,
            "region": region,
            "area": area,
            "occupation": occ,
            "occ_fine": str(g(r, "customer_occp_desc") or "(blank)"),
            "income_tier": income,
            "ltv_range": ltv,
            "vintage_ym": ym or "(blank)",
            "vehicle_type": str(g(r, "account_disb_Vehicle_Type") or "(blank)"),
            "product_group": str(g(r, "account_disb_Product_Group") or "(blank)"),
            "coll_age": cage,
            "brand": brand,
            "brand_x_collage": brand + "|" + cage,
            "brand_x_region": brand + "|" + region,
            "vehicle_x_ltv": str(g(r, "account_disb_Vehicle_Type") or "(blank)") + "|" + ltv,
            "model": (str(g(r, "account_disb_car_brand") or "") + " " +
                      str(g(r, "account_disb_car_model") or "")).strip() or "(blank)",
            "occ_x_income": occ + "|" + income,
            "occ_x_region": occ + "|" + region,
            "occ_x_georegion": occ + "|" + region_geo,
            "vehicle_x_georegion": (str(g(r, "account_disb_Vehicle_Type") or "(blank)")
                                    + "|" + region_geo),
            "branch": br,
            "dpd_bucket": dpd,
            "geo_region": region_geo,
            # restructuring status split (Normal / Pre-emptive / TDR / Skip)
            "acc_chng": chg,
            "chg_x_bucket": chg + "|" + stage,
            "chg_x_occ": chg + "|" + occ,
            "chg_x_region": chg + "|" + region,
            # collateral book deep-dive (type = coll_segment; age = coll_age; make = brand)
            "coll_segment": cseg,
            "coll_seg_x_region": cseg + "|" + region,
            "coll_seg_x_area": cseg + "|" + area,
            "coll_seg_x_occ": cseg + "|" + occ,
            "coll_seg_x_income": cseg + "|" + income,
            "coll_seg_x_bucket": cseg + "|" + stage,
            "collage_x_region": cage + "|" + region,
            "collage_x_occ": cage + "|" + occ,
            "collage_x_income": cage + "|" + income,
            "collage_x_area": cage + "|" + area,
            "coll_age_x_bucket": cage + "|" + stage,
            "brand_x_occ": brand + "|" + occ,
            "brand_x_income": brand + "|" + income,
            "brand_x_area": brand + "|" + area,
            "brand_x_ltv": brand + "|" + ltv,
            # branch collateral-concentration (acquisition lens: what each branch is built on)
            "branch_x_seg": br + "|" + cseg,
            "branch_x_brand": br + "|" + brand,
            "branch_x_occ": br + "|" + occ,
        }
        for tab, key in vals.items():
            c = tabs[tab][key]
            c[0] += 1
            c[1] += 1 if early else 0
            c[2] += 1 if roll else 0
            c[3] += 1 if npl_live else 0
            c[4] += 1 if late else 0
            c[5] += 1 if fpd else 0
            c[6] += osamt
            c[7] += osamt if npl_live else 0.0
            c[8] += osamt if late else 0.0
            c[9] += npat
            if ev is not None:
                c[10] += ev
                c[11] += 1
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
            for i in range(12):
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
        "lens_note": ("Owner-framed lenses (2026-07-24): LIVE BOOK = Current..179dpd; "
                      "npl_live = 90-179dpd share of the live book; the 180+ legacy stock is "
                      "reported separately (late180) — it is workout inventory, not fresh risk. "
                      "dpd30p/dpd90p keep the whole-book read for continuity."),
        "min_cell": MIN_CELL,
    }, "tabs": {}}
    capped = ("model", "occ_fine", "branch", "branch_x_seg", "branch_x_brand")
    for k, d in tabs.items():
        out["tabs"][k] = pack(d, top=400 if k in capped else None)
    out["tabs"]["vintage_curve"] = pack(vint_curve, floor=100)
    # full branch census (assistance drill 2026-07-28): the "branch" tab stays top-400 for
    # continuity with existing consumers; this UNCAPPED duplicate carries EVERY booking branch
    # clearing the >=MIN_CELL floor, plus a count-free geo join (branch -> province/region from
    # the committed master) so the geography drill can place each branch.
    out["tabs"]["branch_full"] = pack(tabs["branch"])
    out["branch_geo"] = {}
    for b in out["tabs"]["branch_full"]:
        hit = mname.get(norm_branch(b))
        if hit and hit[0]:
            out["branch_geo"][b] = {"prov": hit[0], "region": hit[2]}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("wrote %s — %d accounts, %d tabs, join %.1f%%, anchor %s"
          % (OUT, n, len(out["tabs"]), matched * 100.0 / n, anchor))


if __name__ == "__main__":
    main()
