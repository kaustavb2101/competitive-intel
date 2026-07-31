#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_call_lists.py — assistance-pilot call lists (OWNER-SIDE output; never committed)

Turns the assistance radar into the thing regional ops actually dials: per priority province,
branch-level lists of farmer accounts with a built-in TREAT/HOLDOUT split so the pilot's
cure-rate is MEASURABLE (owner directive: strategy without action is a thought piece).

  in : the raw tape xlsx (owner's disk)         — --src / REAL_TAPE_XLSX
       platform/data/tape_real.json             — the radar's priority provinces
  out: %USERPROFILE%\\Documents\\autox-assistance-pilot\\
         tier1_<province>.csv   X-days farmer accounts (slipping, <30dpd) — call this week
         tier2_<province>.csv   current farmer accounts in the same stressed cells — outreach
         README.txt             how to run the pilot + how the holdout works

PRIVACY: these CSVs contain internal account numbers, so they are written OUTSIDE the repo and
must never be committed or shared beyond ops. The holdout split is DETERMINISTIC (md5 of the
account number, ~20% held out) so re-runs produce the same groups and the experiment stays honest:
call the TREAT rows, do NOT call HOLDOUT, and after 60-90 days compare roll-rates between groups.

  python3 make_call_lists.py                # top 6 radar provinces
  python3 make_call_lists.py --top 10
"""
import argparse
import collections
import csv
import hashlib
import json
import os
import sys

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAPE_JSON = os.path.join(ROOT, "platform", "data", "tape_real.json")
DEFAULT_SRC = r"C:\Users\Kaustav Bagchi\Downloads\alibaba receipts\Car_Brand_Group data V2.xlsx"
OUT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "autox-assistance-pilot")

import re


from branchkey import norm_branch, master_index  # ONE definition — see pipeline/branchkey.py


def holdout(acct):
    # deterministic ~20% holdout by account-number hash — same split on every re-run
    return int(hashlib.md5(str(acct).encode()).hexdigest(), 16) % 5 == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.environ.get("REAL_TAPE_XLSX", DEFAULT_SRC))
    ap.add_argument("--top", type=int, default=6, help="how many radar provinces")
    a = ap.parse_args()
    if not os.path.exists(a.src):
        sys.exit("make_call_lists.py: tape not found at %s" % a.src)
    if not os.path.exists(TAPE_JSON):
        sys.exit("make_call_lists.py: run build_tape_layers.py first (needs the radar)")

    radar = json.load(open(TAPE_JSON, encoding="utf-8"))["assistance_radar"][:a.top]
    targets = {r["province"] for r in radar}

    # branch -> province via the master
    master = json.load(open(os.path.join(ROOT, "source-data", "branches_final.json"),
                            encoding="utf-8"))
    mrows = master if isinstance(master, list) else master.get("branches", [])
    b2prov, bcoll = master_index(mrows, lambda m: m.get("prov"))
    if bcoll:
        print("NOTE: %d master branch name(s) share a join key%s" %
              (len(bcoll), " — CONFLICTING provinces, check these"
               if any(c["conflicting"] for c in bcoll) else " (same province, harmless)"),
              file=sys.stderr)
    # Farmers booked at a branch we cannot place are DROPPED from the call list below. That is a
    # person who does not get phoned, so it is counted and printed at the end rather than swallowed.
    unjoined_branches, n_unjoined_acc = set(), 0

    wb = openpyxl.load_workbook(a.src, read_only=True)
    ws = wb["default_1"]
    rows = ws.iter_rows(values_only=True)
    hdr = list(next(rows))
    ix = {h: i for i, h in enumerate(hdr)}

    def g(r, c):
        v = r[ix[c]]
        return v if v not in ("", None) else None

    COLS = ["province", "branch", "region", "account", "tier", "group", "dpd_bucket",
            "product", "brand", "model", "os_outstanding", "installment", "income_tier",
            "occupation_detail", "tenor_months"]
    lists = collections.defaultdict(list)   # (prov, tier) -> rows
    n = 0
    for r in rows:
        n += 1
        occ = str(g(r, "account_disb_ocp_grp") or "")
        if occ != "เกษตร":
            continue
        br = str(g(r, "account_disb_Booking_Branch_Name") or "")
        prov = b2prov.get(norm_branch(br))
        if prov is None:
            unjoined_branches.add(br)
            n_unjoined_acc += 1
        if prov not in targets:
            continue
        dpd = str(g(r, "account_disb_dpd_bucket") or "")
        if dpd.startswith("2."):
            tier = "tier1"
        elif dpd.startswith("1."):
            tier = "tier2"
        else:
            continue          # 30+dpd is collections' lane, not pre-emptive assistance
        acct = g(r, "account_disb_Account_Number")
        lists[(prov, tier)].append({
            "province": prov, "branch": br,
            "region": g(r, "account_disb_Region"), "account": acct, "tier": tier,
            "group": "HOLDOUT" if holdout(acct) else "TREAT", "dpd_bucket": dpd,
            "product": g(r, "account_disb_Product_Group"),
            "brand": g(r, "account_disb_car_brand"), "model": g(r, "account_disb_car_model"),
            "os_outstanding": g(r, "OS"), "installment": g(r, "Sum_account_disb_Installment_Amount"),
            "income_tier": g(r, "account_disb_income_tier"),
            "occupation_detail": g(r, "customer_occp_desc"),
            "tenor_months": g(r, "Tenor"),
        })

    os.makedirs(OUT_DIR, exist_ok=True)
    summary = []
    for (prov, tier), items in sorted(lists.items()):
        items.sort(key=lambda x: (str(x["branch"]), str(x["account"])))
        path = os.path.join(OUT_DIR, "%s_%s.csv" % (tier, prov))
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            w.writerows(items)
        nt = sum(1 for x in items if x["group"] == "TREAT")
        summary.append("%s %s: %d accounts (%d TREAT / %d HOLDOUT)"
                       % (prov, tier, len(items), nt, len(items) - nt))

    with open(os.path.join(OUT_DIR, "README.txt"), "w", encoding="utf-8") as f:
        f.write("AutoX assistance pilot — call lists (INTERNAL; contains account numbers)\n"
                "==========================================================================\n"
                "tier1_*.csv  = farmers currently X-days late (<30dpd). Call THIS WEEK.\n"
                "tier2_*.csv  = farmers current-but-exposed (severe-drought districts). Outreach.\n\n"
                "THE EXPERIMENT: call only group=TREAT. Do NOT call group=HOLDOUT (~20%,\n"
                "deterministic by account hash - identical on every re-run). After 60-90 days,\n"
                "compare the share of each group that rolled into 30+dpd. The difference is the\n"
                "pilot's measured cure-rate - the number that decides if the program scales.\n\n"
                + "\n".join(summary) + "\n")
    print("wrote %s — %d lists" % (OUT_DIR, len(lists)))
    if unjoined_branches:
        # These are farm accounts we could not place on the master, so they were never even
        # considered for the list. Real people, so the number is printed, not swallowed.
        print("WARNING: %d farm account(s) at %d unplaceable branch(es) were excluded before "
              "province targeting — they can never appear on a call list:"
              % (n_unjoined_acc, len(unjoined_branches)), file=sys.stderr)
        for b in sorted(unjoined_branches):
            print("   %s" % b, file=sys.stderr)
    for s in summary:
        print(" ", s)


if __name__ == "__main__":
    main()
