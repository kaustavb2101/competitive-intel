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

PROBE_N = 80          # creatives to probe per account (was 25 — too thin once most are images)
MIN_HITS = 2          # one vehicle-lending creative could be a stray; two is a product line
MIN_READ = 12         # below this, "no hits" means we barely looked — report it as such


def copy_of(c, use_ocr=False):
    """Ad copy for one creative row, via the same readers the real pull uses.

    Text-rendered creatives are read directly. IMAGE banners need OCR, and skipping them is
    not a neutral economy here: bank creatives are overwhelmingly image banners, so the
    text-only path read 1 of 1,278 KBank creatives and 1 of 66 ttb ones. A classifier fed
    that thin a slice cannot distinguish "advertises something else" from "we barely looked".
    """
    try:
        _kind, render, img = P.payload_of(c)
    except Exception:
        return ""
    if render:
        try:
            return " ".join(P.render_text(render) or [])
        except Exception:
            return ""
    if img and use_ocr:
        try:
            return " ".join(P.ocr_text(img) or [])      # ESTIMATED: a transcription can misread
        except Exception:
            return ""
    return ""


def probe(aid, use_ocr=False):
    """Return a dict describing what this account advertises, or why we could not tell."""
    try:
        rows = P.creatives(aid)
    except Exception as e:
        return {"status": "unreadable", "error": str(e)[:160], "n_listed": None,
                "n_probed": 0, "n_read": 0, "n_vehicle_lending": 0, "samples": [], "seen": []}

    out = {"status": None, "error": None, "n_listed": len(rows),
           "n_probed": 0, "n_read": 0, "n_vehicle_lending": 0, "samples": [], "seen": []}
    if not rows:
        out["status"] = "listed_zero"      # deliberately NOT "no ads" — see module docstring
        return out

    for c in rows[:PROBE_N]:
        out["n_probed"] += 1
        txt = copy_of(c, use_ocr)
        if not txt:
            continue
        out["n_read"] += 1
        flat = " ".join(txt.split())
        low = flat.lower()
        # A few reads kept REGARDLESS of verdict. Without them a "no hits" line is unfalsifiable
        # — you cannot tell a genuinely off-product account from a broken token list.
        if len(out["seen"]) < 4:
            out["seen"].append(flat[:160])
        if any(t in low for t in NOT_LENDING):
            continue
        if any(t in low for t in VEHICLE) and any(t in low for t in LEND):
            out["n_vehicle_lending"] += 1
            if len(out["samples"]) < 3:
                out["samples"].append(flat[:180])

    if out["n_read"] == 0:
        out["status"] = "unreadable"       # listed, but no copy came back — still not a verdict
    elif out["n_vehicle_lending"] >= MIN_HITS:
        out["status"] = "vehicle_refinance"
    elif out["n_read"] < MIN_READ:
        # THE FIX. The first CI run called this "other_product" off 1 read of 1,278 listed
        # creatives. Absence of evidence in a sample that small is not evidence of absence,
        # and it is the same false negative the account-level capture guard exists to stop —
        # one layer down, at the creative level.
        out["status"] = "insufficient_sample"
    else:
        out["status"] = "no_hit_in_sample"  # NOT "this account has no car-loan ads"
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
    ap.add_argument("--ocr", action="store_true",
                    help="OCR image banners too (needs tesseract + Thai traineddata). Without "
                         "it only text-rendered creatives are read, which for bank accounts is "
                         "a few per thousand — not enough to conclude anything.")
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
        r = probe(aid, a.ocr)
        r.update({"operator": key, "advertiser_id": aid,
                  "advertiser_name": name, "discovery_note": note})
        report.append(r)
        print("%-10s %s" % (key, aid))
        print("   %s — %s" % (name, note))
        if r["status"] == "unreadable":
            print("   UNREADABLE — %s" % (r["error"] or "listed creatives but no copy returned"))
        else:
            # Coverage is printed as read/probed/listed, never as a bare verdict: "0 hits" off
            # 1 read of 1,278 and "0 hits" off 60 reads of 66 are not the same claim.
            print("   read %d of %d probed (%s listed) | vehicle-lending %d -> %s"
                  % (r["n_read"], r["n_probed"], r["n_listed"],
                     r["n_vehicle_lending"], r["status"].upper()))
        for s in r["samples"]:
            print("     HIT · %s" % s)
        for s in r["seen"]:
            print("     saw · %s" % s)
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
        drop = [r for r in report if r["status"] == "no_hit_in_sample"]
        thin = [r for r in report if r["status"] == "insufficient_sample"]
        print("\nPIN to ADVERTISERS (markets vehicle refinance):")
        for r in pin or []:
            print("   %-10s %s  (%d/%d creatives on-product)"
                  % (r["operator"], r["advertiser_id"], r["n_vehicle_lending"], r["n_read"]))
        if not pin:
            print("   (none)")
        print("\nNO VEHICLE-REFINANCE COPY IN THE SAMPLE READ — a defensible leave-out, but say")
        print("it as what it is: this is the sample, not a census of the account.")
        for r in drop or []:
            print("   %-10s %s  (read %d of %d probed, %s listed)"
                  % (r["operator"], r["advertiser_id"], r["n_read"], r["n_probed"], r["n_listed"]))
        if not drop:
            print("   (none)")
        if thin:
            print("\nINCONCLUSIVE — too few creatives readable to call it either way (<%d):"
                  % MIN_READ)
            for r in thin:
                print("   %-10s %s  (read %d of %d probed, %s listed)"
                      % (r["operator"], r["advertiser_id"], r["n_read"], r["n_probed"],
                         r["n_listed"]))
            print("   Re-run with --ocr: these accounts are mostly image banners, whose words")
            print("   are only reachable by transcription.")
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
