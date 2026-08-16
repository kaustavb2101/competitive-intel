#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vet the unpinned advertiser accounts in pull_google_ads.CANDIDATES. READ-ONLY.

WHY THIS EXISTS. `--discover` found a real Google advertiser account for every bank operator
once the search finally used the bank's LEGAL ENTITY name instead of its product name (SCB My
Car My Cash is marketed by บริษัท ธนาคารไทยพาณิชย์ จำกัด (มหาชน), not by an account called
"My Car My Cash"). But finding an account is not the same as knowing what it advertises: a
bank's ad account carries credit cards, deposits, mortgages and car loans together, and
KKP's only account belongs to KKP Dime SECURITIES — probably an investing account, not
รถเรียกเงิน. Pinning an id that markets something else would pour unrelated creatives into the
rate board and the daily digest. So the ids sit in CANDIDATES, unpinned, until a run reads
their copy and says which product they actually push.

WHY IT IS A JOB AND NOT A LAPTOP SCRIPT. Two attempts from Kaustav's laptop read 0 of 13
accounts — every call answered HTTP 429 after five backoffs. That is a limit on us, not a
verdict: a throttled caller and an advertiser with no ads both return an empty list. The
swarm pulls hundreds of creatives from GitHub's runners on the same endpoint, so the clean
IP is the fix.

THE FAILURE MODE THIS GUARDS. Reading "0 creatives" as "runs no ads" writes a false negative
into the competitive picture that nothing downstream can detect. So the run reports its own
CAPTURE RATE first, and refuses to recommend a NO_ACCOUNT verdict for any account when the
probe itself was throttled. An unreadable account stays unreadable in the output.

Writes nothing to source-data/ or platform/data/. Emits a report to stdout and, with --json,
a machine-readable artifact for the workflow to upload.
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pull_google_ads as P  # noqa: E402  (single source of truth for CANDIDATES + the RPC)

# The question is never "does this bank advertise" — it is "does THIS ACCOUNT advertise the
# vehicle-refinance product". A bank account pushing credit cards is a wrong pin, not a hit.
VEHICLE = ("รถ", "ทะเบียนรถ", "จำนำทะเบียน", "รถแลกเงิน", "รถคือเงิน", "รถปลดล็อก", "รถช่วยได้",
           "รถเรียกเงิน", "โอนเล่ม", "เล่มทะเบียน", "รีไฟแนนซ์", "ออโต้",
           "car2cash", "car for cash", "my car my cash", "cash your car", "auto cash", "refinance")
LEND = ("สินเชื่อ", "กู้", "ดอกเบี้ย", "ผ่อน", "วงเงิน", "อนุมัติ", "เงินสด", "เงินก้อน",
        "loan", "interest", "credit")
# Products that share the vehicle vocabulary but are NOT lending — a motor-insurance creative
# says รถ and ผ่อน too, and would otherwise read as a hit.
NOT_LENDING = ("ประกันภัยรถ", "ประกันชั้น", "พ.ร.บ.", "ประกันชีวิต", "ประกันสุขภาพ",
               "motor insurance", "travel insurance")

PROBE_N = 25          # creatives to read per account — enough to characterise, cheap enough to be polite
MIN_HITS = 2          # one vehicle-lending creative could be a stray; two is a product line


def copy_of(c):
    """Ad copy for one creative row, via the same readers the real pull uses (no OCR: image-only
    banners are left unread here rather than spending OCR budget on a vetting probe)."""
    try:
        _kind, render, _img = P.payload_of(c)
    except Exception:
        return ""
    if not render:
        return ""
    try:
        return " ".join(P.render_text(render) or [])
    except Exception:
        return ""


def probe(aid):
    """Return a dict describing what this account advertises, or why we could not tell."""
    try:
        rows = P.creatives(aid)
    except Exception as e:
        return {"status": "unreadable", "error": str(e)[:160],
                "n_listed": None, "n_read": 0, "n_vehicle_lending": 0, "samples": []}

    out = {"status": None, "error": None, "n_listed": len(rows),
           "n_read": 0, "n_vehicle_lending": 0, "samples": []}
    if not rows:
        out["status"] = "listed_zero"      # deliberately NOT "no ads" — see module docstring
        return out

    for c in rows[:PROBE_N]:
        txt = copy_of(c)
        if not txt:
            continue
        out["n_read"] += 1
        low = txt.lower()
        if any(t in low for t in NOT_LENDING):
            continue
        if any(t in low for t in VEHICLE) and any(t in low for t in LEND):
            out["n_vehicle_lending"] += 1
            if len(out["samples"]) < 3:
                out["samples"].append(" ".join(txt.split())[:180])

    if out["n_read"] == 0:
        out["status"] = "unreadable"       # listed, but no copy came back — still not a verdict
    elif out["n_vehicle_lending"] >= MIN_HITS:
        out["status"] = "vehicle_refinance"
    else:
        out["status"] = "other_product"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", metavar="PATH", help="also write the machine-readable report here")
    ap.add_argument("--sleep", type=float, default=None,
                    help="seconds between RPC calls (default: pull_google_ads.POLITE)")
    ap.add_argument("--list", action="store_true",
                    help="print the candidate table and exit — no network. Exercises the "
                         "CANDIDATES unpacking offline, which is the one thing py_compile and "
                         "an import check cannot do (a shape change there shipped a "
                         "ValueError straight to CI).")
    a = ap.parse_args()
    if a.sleep is not None:
        P.POLITE = a.sleep

    # CANDIDATES values are (advertiser_id, advertiser_name, ads_note) — the NAME matters here:
    # it is the evidence that --discover matched the bank's legal entity rather than a personal
    # name collision, so it is carried into the report instead of being dropped.
    cands = [(k, aid, name, note)
             for k, accts in sorted(P.CANDIDATES.items()) for aid, name, note in accts]
    print("Vetting %d unpinned advertiser accounts across %d operators.\n"
          % (len(cands), len(P.CANDIDATES)))
    if a.list:
        for key, aid, name, note in cands:
            print("%-10s %-24s %-46s %s" % (key, aid, name[:46], note))
        return 0
    P.warm()

    report = []
    for key, aid, name, note in cands:
        r = probe(aid)
        r.update({"operator": key, "advertiser_id": aid,
                  "advertiser_name": name, "discovery_note": note})
        report.append(r)
        print("%-10s %s" % (key, aid))
        print("   %s — %s" % (name, note))
        if r["status"] == "unreadable":
            print("   UNREADABLE — %s" % (r["error"] or "listed creatives but no copy returned"))
        else:
            print("   listed %s | copy read %d | vehicle-lending %d -> %s"
                  % (r["n_listed"], r["n_read"], r["n_vehicle_lending"], r["status"].upper()))
        for s in r["samples"]:
            print("     · %s" % s)
        print()

    unreadable = sum(1 for r in report if r["status"] == "unreadable")
    capture = len(report) - unreadable
    print("=" * 78)
    print("CAPTURE: %d of %d accounts readable." % (capture, len(report)))

    # The whole point. A throttled run must not be allowed to look like a set of findings.
    if capture == 0:
        print("THROTTLED — every account failed. This run establishes NOTHING. Do not pin, and")
        print("do not add any operator to NO_ACCOUNT on the strength of it.")
        verdict = "throttled"
    else:
        verdict = "usable"
        pin = [r for r in report if r["status"] == "vehicle_refinance"]
        drop = [r for r in report if r["status"] == "other_product"]
        print("\nPIN to ADVERTISERS (markets vehicle refinance):")
        for r in pin or []:
            print("   %-10s %s  (%d/%d creatives on-product)"
                  % (r["operator"], r["advertiser_id"], r["n_vehicle_lending"], r["n_read"]))
        if not pin:
            print("   (none)")
        print("\nLEAVE OUT (account advertises something else):")
        for r in drop or []:
            print("   %-10s %s" % (r["operator"], r["advertiser_id"]))
        if not drop:
            print("   (none)")
        if unreadable:
            print("\nSTILL UNREADABLE (%d) — carry forward, do not conclude:" % unreadable)
            for r in report:
                if r["status"] == "unreadable":
                    print("   %-10s %s" % (r["operator"], r["advertiser_id"]))

    if a.json:
        io.open(a.json, "w", encoding="utf-8").write(json.dumps(
            {"verdict": verdict, "n_accounts": len(report), "n_readable": capture,
             "probe_n": PROBE_N, "min_hits": MIN_HITS, "accounts": report},
            ensure_ascii=False, indent=1, sort_keys=True))
        print("\nwrote %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
