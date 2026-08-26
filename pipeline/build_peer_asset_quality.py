#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_peer_asset_quality.py — COMPETITIVE + PORTFOLIO-RISK lens on rivals (objective #2 × #1):
the six SET-listed title-loan peers' OWN audited/reviewed asset quality, read straight from the
IFRS-9 credit-quality (Stage 1/2/3) staging tables in their financial-statement NOTES.

  in : source-data/set_filings/text/<SYM>_fs_<date>__NOTES.txt   (newest fs per symbol)
       source-data/set_filings/index.json                        (filing date + headline)
       MEASURED — Stock Exchange of Thailand company filings (set.or.th), pulled by
       pull_set_filings.py. The DOCX NOTES were text-extracted to pipe-delimited tables.
  out: platform/data/peer_asset_quality.json

Why this is NOT a duplicate of peer_scoreboard.json / set_peers.json: the SET market-data API
(set_peers.json) carries totalAsset / equity / ROE / deRatio, but NOT the borrowers' credit
quality. The Stage-3 ("Non-performing" / "credit-impaired") share of gross receivables and the
expected-credit-loss (ECL) coverage of it are the peers' NPL-equivalent asset-quality signal — the
single sharpest external read on how the rival book is performing — and they exist only inside the
NOTES tables this script parses. Not an AutoX figure; the rivals' own disclosures.

WHAT IS EXTRACTED, per peer, from the CONSOLIDATED (see basis note), latest-interim staging table(s):
  - gross receivables by stage (S1 performing / S2 under-performing / S3 non-performing),
  - allowance for expected credit losses on the S3 (credit-impaired) bucket,
  - combined across the loan + hire-purchase books where the peer reports them separately.
From those:
  - npl_pct          = S3 gross / total gross           (the peers' NPL-equivalent)
  - s3_coverage_pct  = |S3 allowance| / S3 gross         (ECL cover of the impaired book)
  - total_coverage_pct = |total allowance| / total gross (ECL cover of the whole book)

CORRECTNESS GUARD (why a silent mis-parse is very unlikely): every staging table prints its own
`Total` row. The parser asserts S1+S2+S3(+POCI) == Total for BOTH gross and allowance columns,
per table, within ฿1k rounding. A wrong column map or a mis-read row breaks that identity and the
build aborts rather than shipping a wrong competitor NPL.

HETEROGENEITY handled explicitly (verified by hand against each filing, 2026-08-26):
  - Units: SAK and TURBO report in ฿ (full baht); the other four in ฿ thousand. Normalised to ฿k.
  - Column layout: HENG lays gross(2 periods) then allowance(2 periods) — allow col = 2; the other
    five lay gross|allowance|net — allow col = 1. Current period is always the first numeric column.
  - Book split: HENG/MTC/SAK/TIDLOR report loan + hire-purchase staging separately (summed here);
    SAWAD reports one combined "financial assets" table; TURBO one loan table.
  - SAWAD carries a 4th bucket, Purchased-Or-originated-Credit-Impaired (POCI) — its bought-distressed-
    debt business. POCI is EXCLUDED from npl_pct (it is not organic delinquency) and reported
    separately as poci_bn with a caveat.
  - Basis: HENG files company-only (unconsolidated); SAK's consolidated == separate; the rest
    consolidated. Flagged per peer, not blended away.

Deterministic + network-free. Money rolled to ฿bn (2dp) and ratios to 1dp so the output is
byte-stable across Python builds. `--check` byte-compares; SKIPs (exit 3) if the corpus is absent.

  python3 build_peer_asset_quality.py
  python3 build_peer_asset_quality.py --check
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT_DIR = os.path.join(ROOT, "source-data", "set_filings", "text")
INDEX = os.path.join(ROOT, "source-data", "set_filings", "index.json")
OUT = os.path.join(ROOT, "platform", "data", "peer_asset_quality.json")

# Per-peer parse spec, hand-verified against the Q2/2026 reviewed filings (as-of 30 June 2026).
# books: (book_label, [TABLE n] id) for the CONSOLIDATED current-period staging table(s).
# unit_div: divide the raw figures by this to reach ฿ thousand (SAK/TURBO report in ฿).
# gross_col / allow_col: index into a row's non-empty numeric cells for the current period.
PEERS = [
    {"sym": "MTC", "name": "Muangthai Capital", "basis": "Consolidated",
     "unit_div": 1, "gross_col": 0, "allow_col": 1,
     "books": [("loan", 5), ("hire-purchase", 9)]},
    {"sym": "TIDLOR", "name": "Ngern Tid Lor (Tidlor Holdings)", "basis": "Consolidated",
     "unit_div": 1, "gross_col": 0, "allow_col": 1,
     "books": [("loan", 10), ("hire-purchase", 11)]},
    {"sym": "SAWAD", "name": "Srisawad", "basis": "Consolidated",
     "unit_div": 1, "gross_col": 0, "allow_col": 1,
     "books": [("combined loans to customers", 14)]},
    {"sym": "SAK", "name": "Saksiam Leasing", "basis": "Consolidated (= separate)",
     "unit_div": 1000, "gross_col": 0, "allow_col": 1,
     "books": [("loan", 7), ("hire-purchase", 5)]},
    {"sym": "HENG", "name": "Heng Leasing & Capital", "basis": "Company (unconsolidated)",
     "unit_div": 1, "gross_col": 0, "allow_col": 2,
     "books": [("loan", 7), ("hire-purchase", 4)]},
    {"sym": "TURBO", "name": "Ngern Turbo (NTL)", "basis": "Consolidated",
     "unit_div": 1, "gross_col": 0, "allow_col": 1,
     "books": [("loan", 17)]},
]
# TURBO's TABLE 17 is already in ฿ thousand? No — TURBO reports in full ฿; handled below.
for _p in PEERS:
    if _p["sym"] in ("SAK", "TURBO"):
        _p["unit_div"] = 1000

# Stage-label classification, applied to the row label (used only to locate the S3/POCI rows;
# stage ORDER within the table is the primary key, this is a cross-check).
RE_NONPERF = re.compile(r"non[- ]?performing|credit[- ]?impaired", re.I)
RE_POCI = re.compile(r"purchased or originated", re.I)


def latest_notes(sym):
    files = sorted(glob.glob(os.path.join(TEXT_DIR, "%s_fs_*__NOTES.txt" % sym)))
    return files[-1] if files else None


def parse_num(cell):
    """A single cell -> (kind, value). kind in {'num','dash','text','empty'}."""
    c = cell.strip()
    if c == "":
        return ("empty", None)
    if c in ("-", "–", "—"):
        return ("dash", 0)
    neg = False
    t = c
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1].strip()
    t = t.replace(",", "").replace(" ", "")
    if re.fullmatch(r"-?\d+(\.\d+)?", t):
        v = float(t) if "." in t else int(t)
        return ("num", -v if neg else v)
    return ("text", None)


def table_block(text, tid):
    """Return the list of raw lines strictly inside [TABLE tid] ... [/TABLE tid]."""
    lines = text.split("\n")
    start = end = None
    for i, ln in enumerate(lines):
        if ln.strip() == "[TABLE %d]" % tid:
            start = i + 1
        elif ln.strip() == "[/TABLE %d]" % tid:
            end = i
            break
    if start is None or end is None:
        raise ValueError("TABLE %d not found" % tid)
    return lines[start:end]


def data_rows(block):
    """Rows that carry the current-period staging numbers, in order, up to and including the
    first `Total` row. A data row = label + only numeric/dash cells (>=1 numeric)."""
    out = []
    for ln in block:
        cells = ln.split("|")
        label = cells[0].strip()
        vals, has_num, has_text = [], False, False
        for c in cells[1:]:
            kind, v = parse_num(c)
            if kind == "num":
                vals.append(v)
                has_num = True
            elif kind == "dash":
                vals.append(0)
            elif kind == "text":
                has_text = True
        if has_text or not has_num:
            continue  # header / unit / period / description line
        out.append((label, vals))
        if re.match(r"^\s*total\b", label, re.I):
            break
    return out


def parse_book(text, tid, gcol, acol):
    """Return dict for one staging table: gross/allow totals and by-stage (current period, ฿ raw)."""
    rows = data_rows(table_block(text, tid))
    if len(rows) < 4:  # >=3 stages + Total
        raise ValueError("TABLE %d: only %d data rows" % (tid, len(rows)))
    total_label, total_vals = rows[-1]
    if not re.match(r"^\s*total\b", total_label, re.I):
        raise ValueError("TABLE %d: last data row is not Total (%r)" % (tid, total_label))
    stages = rows[:-1]
    if len(stages) not in (3, 4):
        raise ValueError("TABLE %d: expected 3 or 4 stage rows, got %d" % (tid, len(stages)))

    def col(vals, idx):
        if idx >= len(vals):
            raise ValueError("TABLE %d: row has %d cols, need col %d" % (tid, len(vals), idx))
        return vals[idx]

    g_stage = [col(v, gcol) for _, v in stages]
    a_stage = [col(v, acol) for _, v in stages]
    g_total = col(total_vals, gcol)
    a_total = col(total_vals, acol)
    # CORRECTNESS GUARD: stages must reconcile to the printed Total (gross and allowance).
    if abs(sum(g_stage) - g_total) > 1:
        raise ValueError("TABLE %d: gross stages %d != Total %d" % (tid, sum(g_stage), g_total))
    if abs(sum(a_stage) - a_total) > 1:
        raise ValueError("TABLE %d: allowance stages %d != Total %d" % (tid, sum(a_stage), a_total))
    # S3 = non-performing/credit-impaired. It is the 3rd stage row by IFRS-9 order; cross-check label.
    s3_label = stages[2][0]
    if not RE_NONPERF.search(s3_label):
        raise ValueError("TABLE %d: 3rd stage %r is not the non-performing row" % (tid, s3_label))
    poci_g = 0
    if len(stages) == 4:
        if not RE_POCI.search(stages[3][0]):
            raise ValueError("TABLE %d: 4th row %r is not POCI" % (tid, stages[3][0]))
        poci_g = g_stage[3]
    return {
        "gross_total": g_total, "allow_total": a_total,
        "s3_gross": g_stage[2], "s3_allow": a_stage[2],
        "poci_gross": poci_g,
    }


def build():
    idx = json.load(open(INDEX, encoding="utf-8"))
    fs_by = {}
    for f in idx.get("filings", []):
        if f.get("kind") == "fs":
            fs_by.setdefault(f["symbol"], []).append(f)
    peers = []
    for spec in PEERS:
        sym = spec["sym"]
        notes = latest_notes(sym)
        if notes is None:
            raise SystemExit("no NOTES.txt for %s" % sym)
        text = open(notes, encoding="utf-8").read()
        div = spec["unit_div"]
        gross_k = s3_gross_k = s3_allow_k = allow_k = poci_k = 0.0
        books_used = []
        book_gross_k = []  # per-book gross (฿k), same order as spec["books"]
        for label, tid in spec["books"]:
            b = parse_book(text, tid, spec["gross_col"], spec["allow_col"])
            gross_k += b["gross_total"] / div
            allow_k += abs(b["allow_total"]) / div
            s3_gross_k += b["s3_gross"] / div
            s3_allow_k += abs(b["s3_allow"]) / div
            poci_k += b["poci_gross"] / div
            books_used.append("%s (TABLE %d)" % (label, tid))
            book_gross_k.append((label, b["gross_total"] / div))
        # organic NPL excludes POCI (a bought-distressed-debt line, SAWAD only)
        denom = gross_k
        npl = 100.0 * s3_gross_k / denom if denom else 0.0
        s3_cov = 100.0 * s3_allow_k / s3_gross_k if s3_gross_k else 0.0
        tot_cov = 100.0 * allow_k / gross_k if gross_k else 0.0
        # filing meta
        fdate = os.path.basename(notes).split("_fs_")[1].split("_")[0]
        headline = ""
        for f in sorted(fs_by.get(sym, []), key=lambda x: x["date"]):
            if f["date"] == fdate:
                headline = f.get("headline", "")
        # Book mix (objective #2 — what the rival lends against): the gross split between the
        # secured "loan" book (title-loan / cash lending) and the "hire-purchase" book (vehicle
        # instalment / asset-finance), each already reconciled to its printed Total above. Peers
        # that file a single combined book (SAWAD, TURBO) carry one entry and single_book=True.
        book_mix = []
        hp_gross_k = 0.0
        for label, gk in book_gross_k:
            share = round(100.0 * gk / gross_k, 1) if gross_k else 0.0
            book_mix.append({"label": label, "gross_bn": round(gk / 1e6, 2), "share_pct": share})
            if re.search(r"hire[- ]?purchase", label, re.I):
                hp_gross_k += gk
        single_book = len(book_mix) < 2
        hp_share_pct = None if single_book else round(100.0 * hp_gross_k / gross_k, 1) if gross_k else 0.0
        rec = {
            "symbol": sym, "name": spec["name"], "basis": spec["basis"],
            "npl_pct": round(npl, 1),
            "s3_coverage_pct": round(s3_cov, 1),
            "total_coverage_pct": round(tot_cov, 1),
            "gross_book_bn": round(gross_k / 1e6, 2),
            "nonperf_bn": round(s3_gross_k / 1e6, 3),
            "book_mix": book_mix,
            "hp_share_pct": hp_share_pct,
            "single_book": single_book,
            "as_of": "2026-06-30",
            "filing_date": fdate,
            "filing": headline,
            "books": books_used,
        }
        if poci_k:
            rec["poci_bn"] = round(poci_k / 1e6, 2)
            rec["poci_note"] = ("Excludes ฿%.1fbn purchased/originated credit-impaired (bought "
                                "distressed-debt book) from the NPL ratio." % (poci_k / 1e6))
        peers.append(rec)
    peers.sort(key=lambda p: (-p["npl_pct"], p["symbol"]))
    meta = {
        "label": ("MEASURED — IFRS-9 credit-quality (Stage 1/2/3) from the six SET-listed Thai "
                  "title-loan peers' own reviewed financial-statement NOTES. Stage-3 "
                  "'non-performing / credit-impaired' gross share of gross receivables (NPL-equivalent) "
                  "and expected-credit-loss coverage. Not an AutoX figure — the rivals' own disclosures."),
        "source": ("Stock Exchange of Thailand · set.or.th company filings — Financial Statement NOTES, "
                   "credit-quality staging tables (Q2/2026 reviewed, as-of 30 June 2026)."),
        "generated_by": "pipeline/build_peer_asset_quality.py",
        "objective": "#2 competitive risk (rival asset quality) + #1 portfolio-risk lens applied to rivals",
        "as_of": "2026-06-30",
        "npl_definition": ("Stage-3 (credit-impaired / 'non-performing') gross receivables divided by "
                           "total gross receivables, per the peer's own IFRS-9 staging table. Denominator "
                           "is gross carrying value incl. accrued interest, net of unearned/deferred income, "
                           "as the peer presents it — combined across the loan + hire-purchase books where "
                           "reported separately."),
        "book_mix_definition": ("book_mix splits each peer's gross receivables between the secured "
                                "'loan' book (title-loan / cash lending — AutoX's direct competitive "
                                "space) and the 'hire-purchase' book (vehicle instalment / asset finance), "
                                "using the same per-table figures already reconciled to each printed Total. "
                                "hp_share_pct is the hire-purchase share of the gross book; peers filing a "
                                "single combined book (SAWAD, TURBO) carry single_book=true and hp_share_pct=null "
                                "rather than a fabricated split."),
        "unit": "฿ thousand internally; published figures in ฿bn (2dp) and % (1dp).",
        "basis_note": ("Consolidated where reported. HENG files company-only (unconsolidated); SAK's "
                       "consolidated equals its separate statements. Each peer's basis is carried on its row."),
        "caveats": [
            "NPL here is the IFRS-9 Stage-3 gross share the peer itself discloses, not a regulator-defined "
            "NPL — comparable across these six because all report on the same IFRS-9 basis, but not "
            "identical to a bank 90-days-past-due ratio.",
            "SAWAD's ratio excludes its purchased/originated-credit-impaired (bought distressed-debt) book, "
            "reported separately as poci_bn; including it would overstate organic delinquency.",
            "Latest interim (Q2/2026 reviewed) statements — reviewed, not year-end audited.",
            "book_mix is the loan vs hire-purchase gross split as the peer classifies it, not a "
            "collateral-type census; SAWAD and TURBO file a single combined book so no split is shown.",
            "Correctness guard: for every staging table parsed, the by-stage figures are asserted to "
            "reconcile to the peer's own printed Total (gross and allowance) before publication.",
        ],
        "autox_note": "AutoX is unlisted and files no SET statements — there is deliberately no AutoX row here.",
        "n_peers": len(peers),
    }
    return {"meta": meta, "peers": peers}


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.isdir(TEXT_DIR) or not os.path.exists(INDEX):
        msg = "build_peer_asset_quality.py: set_filings corpus absent"
        if args.check:
            print(msg + " — SKIP"); sys.exit(3)
        sys.exit(msg)
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_peer_asset_quality.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_peer_asset_quality.py --check: drifted — re-run the builder.")
        print("build_peer_asset_quality.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d peers" % (OUT, len(obj["peers"])))
    for p in obj["peers"]:
        extra = (" · POCI ฿%.1fbn" % p["poci_bn"]) if "poci_bn" in p else ""
        print("  %-10s NPL %-4s%%  S3-cov %-5s%%  book ฿%-7sbn  (%s)%s"
              % (p["symbol"], p["npl_pct"], p["s3_coverage_pct"], p["gross_book_bn"], p["basis"], extra))


if __name__ == "__main__":
    main()
