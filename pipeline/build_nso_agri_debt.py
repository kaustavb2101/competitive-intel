#!/usr/bin/env python3
"""
build_nso_agri_debt.py — PORTFOLIO RISK (obj #1) + COMPETITIVE RISK (obj #2): the per-province
agricultural-holder debt profile from the NSO 2023 Agricultural Census (สำมะโนการเกษตร 2566).

Network-free, deterministic, --check-gated. Reads the committed MEASURED snapshot
source-data/nso/agri_debt_2566.json (pulled by pull_nso_agri_debt.py, a network puller NOT in the
gate) and projects it into platform/data/nso_agri_debt.json.

Three census tables, all full-count "by province" (รายจังหวัด):
  income          AGC_0506_11_1301  holders reporting agri income  → holders (agri-holder base)
  debt_incidence  AGC_0506_11_1303  holders reporting debt status  → reporting_debt / with_debt
  loan_source     AGC_0506_11_1305  debt-holders by LENDER source  → the source mix

Per province it computes (all counts MEASURED; shares are exact ratios of MEASURED counts):
  holders          agricultural holders reporting agri income (scale/denominator context).
  reporting_debt   holders who reported their debt status.
  with_debt        holders who HAVE debt.
  debt_incidence   with_debt / reporting_debt — share of agri holders carrying debt.   [obj #1]
  src_total        debt-holders who reported a loan source (source-share denominator).
  src.<lender>     count of debt-holders using each lender type (a holder may report several,
                   so the lender counts sum ABOVE src_total — shares are share-of-borrowers-
                   using-that-source, they do NOT sum to 100%).
  baac_share       ธกส. (BAAC) reliance — the dominant formal agri lender.
  institutional_share  BAAC + cooperatives + village funds + other banks/FIs + govt agencies.
  informal_share   moneylenders + middlemen + private shops — HIGH-COST INFORMAL credit.       [obj #2]
                   Where agri borrowers lean on informal, high-cost credit is both a distress
                   signal (portfolio) and the competitive space a licensed non-bank lender
                   occupies. A risk lens on the borrower base of the network we already run —
                   it makes NO open / close / expand recommendation.
  (relatives — ญาติ/เพื่อนบ้าน — are kept as their own count and are NOT folded into informal_share,
   since family lending is typically low/no-cost, not the high-cost informal channel.)

Province / region keys are the canonical 77 Thai-name set (lib.regionmap.REGION); the NSO snapshot
uses exactly those names (asserted — a mismatch fails the build rather than silently dropping).

GRACEFUL DEGRADE: a missing snapshot still ships a clear absent-state (empty provinces list,
meta.absent=true) so the frontend lens hides itself without erroring.

Run:
  python3 build_nso_agri_debt.py            # write platform/data/nso_agri_debt.json
  python3 build_nso_agri_debt.py --check    # re-run, byte-compare against the committed file
"""
import argparse
import json
import os
import sys

from lib.regionmap import REGION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data", "nso", "agri_debt_2566.json")
OUT = os.path.join(ROOT, "platform", "data", "nso_agri_debt.json")

# loan-source Thai label -> short key. Exact match; an unmapped label fails the build.
LOAN_SRC = {
    "ธนาคารเพื่อการเกษตรและสหกรณ์การเกษตร (ธกส.)": "baac",
    "สหกรณ์/กลุ่มเกษตรกร": "coop",
    "กองทุนหมู่บ้านและชุมชนเมืองแห่งชาติ": "village_fund",
    "ธนาคารอื่นๆ/สถาบันการเงิน": "other_fi",
    "หน่วยงานราชการอื่นๆ": "govt_other",
    "นายทุนเงินกู้": "moneylender",
    "พ่อค้าคนกลาง": "middleman",
    "ร้านค้าเอกชน": "private_shop",
    "ญาติ/เพื่อนบ้าน/บุคคลอื่น": "relatives",
    "อื่นๆ": "other",
}
LOAN_SRC_TOTAL = "ผู้ถือครองที่มีหนี้สินและรายงานแหล่งเงินกู้"
INCOME_TOTAL = "รายงานรายได้ทางการเกษตร"
DEBT_REPORTING = "รายงานการมีหนี้สิน"
DEBT_HAS = "มีหนี้สิน"

INSTITUTIONAL = ("baac", "coop", "village_fund", "other_fi", "govt_other")
INFORMAL_HIGHCOST = ("moneylender", "middleman", "private_shop")


def _load():
    if not os.path.exists(SRC):
        return None
    with open(SRC, encoding="utf-8") as f:
        return json.load(f)


def _absent(reason):
    meta = {
        "title": "Per-province agri-holder debt & lender-source mix (NSO Ag Census 2566) — "
                 "portfolio risk (obj #1) + competitive risk (obj #2)",
        "generated_by": "pipeline/build_nso_agri_debt.py",
        "deterministic": True,
        "network_free": True,
        "absent": True,
        "absent_reason": reason,
        "provenance": "ABSENT — run pipeline/pull_nso_agri_debt.py to land the MEASURED NSO "
                      "Agricultural Census snapshot, then re-run this builder.",
        "n_provinces": 0,
    }
    return {"meta": meta, "provinces": []}


def _by_prov(rows, dim, cat):
    """Sum VALUE for rows whose category field `dim` == `cat`, keyed by province."""
    out = {}
    for r in rows:
        if r.get(dim) == cat:
            out[r["PROVINCE"]] = out.get(r["PROVINCE"], 0) + int(r.get("VALUE") or 0)
    return out


def build():
    snap = _load()
    if snap is None:
        return _absent("missing source snapshot: source-data/nso/agri_debt_2566.json")

    tabs = snap.get("tables", {})
    try:
        inc_rows = tabs["income"]["rows"]
        debt_rows = tabs["debt_incidence"]["rows"]
        src_rows = tabs["loan_source"]["rows"]
    except (KeyError, TypeError):
        return _absent("snapshot missing one of tables income/debt_incidence/loan_source")

    # assert every loan-source category is known (fail loudly on a new/renamed lender bucket)
    seen = {r.get("SOURCE_LOAN") for r in src_rows}
    unknown = sorted(c for c in seen if c not in LOAN_SRC and c != LOAN_SRC_TOTAL)
    if unknown:
        raise SystemExit("unmapped SOURCE_LOAN category(ies): %s" % unknown)

    holders = _by_prov(inc_rows, "INCOME", INCOME_TOTAL)
    reporting = _by_prov(debt_rows, "DEBT", DEBT_REPORTING)
    with_debt = _by_prov(debt_rows, "DEBT", DEBT_HAS)
    src_total = _by_prov(src_rows, "SOURCE_LOAN", LOAN_SRC_TOTAL)
    src_counts = {key: _by_prov(src_rows, "SOURCE_LOAN", label) for label, key in LOAN_SRC.items()}

    canon = set(REGION)
    present = set(holders) & set(reporting) & set(with_debt) & set(src_total)
    unmatched = sorted(present - canon)
    if unmatched:
        raise SystemExit("NSO provinces not in canonical REGION set: %s" % unmatched)
    missing_canon = sorted(canon - present)  # provinces in canon but absent from the join

    rows = []
    for prov in sorted(present):
        rep = reporting.get(prov, 0)
        wd = with_debt.get(prov, 0)
        st = src_total.get(prov, 0)
        src = {k: src_counts[k].get(prov, 0) for k in LOAN_SRC.values()}
        inst = sum(src[k] for k in INSTITUTIONAL)
        inf = sum(src[k] for k in INFORMAL_HIGHCOST)
        rows.append({
            "province": prov,
            "region": REGION.get(prov),
            "holders": holders.get(prov, 0),
            "reporting_debt": rep,
            "with_debt": wd,
            "debt_incidence": round(wd / rep, 4) if rep > 0 else None,
            "src_total": st,
            "src": src,
            "baac_share": round(src["baac"] / st, 4) if st > 0 else None,
            "institutional_share": round(inst / st, 4) if st > 0 else None,
            "informal_share": round(inf / st, 4) if st > 0 else None,
        })

    # sort worst-first by informal high-cost reliance (obj #2 headline); None last; province tie-break
    rows.sort(key=lambda r: (
        -(r["informal_share"] if r["informal_share"] is not None else -1.0),
        r["province"],
    ))

    meta = {
        "title": "Per-province agri-holder debt & lender-source mix (NSO Ag Census 2566) — "
                 "portfolio risk (obj #1) + competitive risk (obj #2)",
        "generated_by": "pipeline/build_nso_agri_debt.py",
        "deterministic": True,
        "network_free": True,
        "absent": False,
        "n_provinces": len(rows),
        "n_canonical": len(canon),
        "missing_canonical": missing_canon,
        "sort": "worst-first by informal_share (high-cost informal reliance, desc)",
        "source": "NSO Agricultural Census 2566 (2023) — สำนักงานสถิติแห่งชาติ, dataset income-debt "
                  "(catalog.nso.go.th), via pipeline/pull_nso_agri_debt.py.",
        "provenance": "MEASURED — full-count agricultural census, by province. Counts are census "
                      "totals; every share is an exact ratio of two MEASURED counts.",
        "unit": "ราย (agricultural holders)",
        "fields": {
            "holders": "MEASURED — agri holders reporting agricultural income (scale/context).",
            "reporting_debt": "MEASURED — holders who reported their debt status.",
            "with_debt": "MEASURED — holders who HAVE debt.",
            "debt_incidence": "MEASURED ratio — with_debt / reporting_debt (obj #1).",
            "src_total": "MEASURED — debt-holders who reported a loan source (share denominator).",
            "src": "MEASURED counts of debt-holders by lender type. A holder may report several "
                   "sources, so these sum ABOVE src_total — shares do NOT sum to 100%.",
            "baac_share": "MEASURED — BAAC (ธกส.) reliance = src.baac / src_total.",
            "institutional_share": "MEASURED — (baac+coop+village_fund+other_fi+govt_other)/src_total.",
            "informal_share": "MEASURED — high-cost informal reliance = "
                              "(moneylender+middleman+private_shop)/src_total (obj #2).",
        },
        "src_legend": {
            "baac": "ธนาคารเพื่อการเกษตรและสหกรณ์การเกษตร (BAAC)",
            "coop": "สหกรณ์/กลุ่มเกษตรกร (cooperatives / farmer groups)",
            "village_fund": "กองทุนหมู่บ้านและชุมชนเมือง (village & urban community funds)",
            "other_fi": "ธนาคารอื่นๆ/สถาบันการเงิน (other banks / financial institutions)",
            "govt_other": "หน่วยงานราชการอื่นๆ (other government agencies)",
            "moneylender": "นายทุนเงินกู้ (informal moneylenders)",
            "middleman": "พ่อค้าคนกลาง (crop middlemen / traders)",
            "private_shop": "ร้านค้าเอกชน (private shops / stores)",
            "relatives": "ญาติ/เพื่อนบ้าน/บุคคลอื่น (relatives / neighbours — not in informal_share)",
            "other": "อื่นๆ (other)",
        },
        "measured_vs_estimated": "All counts and shares are MEASURED (full-count census). The "
                                 "institutional/informal groupings are a labelling of census "
                                 "categories, not an estimate.",
        "caveats": [
            "Census holders are the farm-holder population, not the AutoX borrower book — this reads "
            "the agri borrower LANDSCAPE, not the realized portfolio.",
            "Lender counts double-count holders who use multiple sources; shares are share-of-"
            "borrowers-using-a-source, and do not sum to 100%.",
            "informal_share deliberately excludes relatives/neighbours (typically low/no-cost).",
        ],
    }
    return {"meta": meta, "provinces": rows}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift")
    args = ap.parse_args()

    data = build()
    text = dumps(data)

    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d provinces%s)" % (
                OUT, data["meta"]["n_provinces"],
                ", ABSENT-state" if data["meta"].get("absent") else ""))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    if data["meta"].get("absent"):
        print("wrote %s (ABSENT-state: %s)" % (OUT, data["meta"]["absent_reason"]))
        return
    print("wrote %s (%d provinces, worst-first by informal reliance)" % (OUT, data["meta"]["n_provinces"]))
    for r in data["provinces"][:6]:
        print("  %-16s informal=%-6s baac=%-6s debt_inc=%-6s (n=%s)" % (
            r["province"], r["informal_share"], r["baac_share"], r["debt_incidence"], r["src_total"]))


if __name__ == "__main__":
    main()
