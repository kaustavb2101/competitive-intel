#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
pull_set_filings.py — MEASURED company disclosures for the six SET-listed Thai title-loan lenders,
pulled AUTONOMOUSLY. Writes source-data/set_filings/. Two KINDS of filing, because they answer
different questions and arrive in different containers:

  mda  "Management Discussion and Analysis" — management's own NARRATIVE (branch counts, growth,
       credit-cost commentary). Delivered as a single PDF. URL carries `NWS`.
  fs   "Financial Statement" — the AUDITED/REVIEWED statements and, crucially, the NOTES TO THE
       FINANCIAL STATEMENTS: IFRS-9 Stage 1/2/3 ECL tables, allowance movement, receivables by
       collateral type, maturity analysis. Delivered as a ZIP. URL carries `FIN`.

The MD&A is what management CHOSE to say; the notes are what the auditor made them disclose. When
the two disagree, the notes win. Most of what the MD&A layer records as "not disclosed" (portfolio
mix by collateral, ECL staging) is in the notes — that is why this script pulls both.

WHY A BROWSER (same pattern as pull_set_peers.py, read that script first): set.or.th's JSON API
403s external requests (Akamai bot protection). The reliable path is a real browser: load a SET
page, then call the news-search API SAME-ORIGIN with fetch() from inside the page, which carries
whatever the 403 was missing and returns 200.

Three steps per symbol (all exactly as verified manually before this script was written):
  1. GET /api/set/news/search?symbol=<SYM>&lang=en&fromDate=01/01/2026&toDate=<today D/M/Y>&limit=60
     (same-origin fetch from inside a loaded page) -> {totalCount, newsInfoList:[{id, datetime,
     symbol, headline, url, ...}]}. fromDate/toDate are REQUIRED — omit them and the endpoint
     silently returns totalCount 0 for almost every symbol (no error, just an empty result).
  2. For each filing selected, GET (same-origin, as TEXT, not JSON — the JSON detail endpoint
     /api/set/news/<id> 404s, do not use it) /en/market/news-and-alert/newsdetails?id=<id>&symbol=<SYM>
     and regex the attachment URL out of the HTML:
       https://weblink\.set\.or\.th/dat/news/[^"'\s\\]+\.(pdf|zip)
     There is normally exactly one match.
  3. Download that attachment over plain urllib (weblink.set.or.th does NOT need the browser —
     verified HTTP 200 — just a browser User-Agent + Referer: https://www.set.or.th/), then:
       .pdf -> pdfplumber text
       .zip -> for each member: .docx via the zip/XML reader below, .xlsx via openpyxl

DOCX WITHOUT python-docx: a .docx is itself a zip whose word/document.xml holds w:p paragraphs and
w:tbl tables. The ECL staging numbers live in the TABLES, so a naive paragraph-only reader silently
returns prose and no numbers. Both are walked, in document order, and tables are emitted as
pipe-delimited rows so the structure survives into the flat .txt.

NETWORK + BROWSER. Not in the offline determinism gate (this pulls new filings as SET publishes
them; the committed index.json + text/ are the artifact). Requires:
  pip install playwright pdfplumber openpyxl && python -m playwright install chromium

  python3 pull_set_filings.py                       # both kinds, all 6 symbols
  python3 pull_set_filings.py --kind fs             # only the financial statements + notes
  python3 pull_set_filings.py --symbols MTC,TIDLOR  # subset
  python3 pull_set_filings.py --per-symbol 4        # how many newest filings of EACH kind to keep
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "source-data", "set_filings")
PDF_DIR = os.path.join(OUT_DIR, "pdf")
ZIP_DIR = os.path.join(OUT_DIR, "zip")
TEXT_DIR = os.path.join(OUT_DIR, "text")
INDEX_PATH = os.path.join(OUT_DIR, "index.json")

# The SIX SET-listed Thai title/vehicle-title lenders — same roster as pull_set_peers.py.
DEFAULT_SYMS = ["MTC", "TIDLOR", "SAWAD", "TURBO", "HENG", "SAK"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

ATTACH_URL_RE = re.compile(r"https://weblink\.set\.or\.th/dat/news/[^\"'\s\\]+\.(?:pdf|zip)",
                           re.IGNORECASE)

# Headline discriminators. SET files the statements under headlines like "Financial Statement
# Quarter 1 (Reviewed)" / "Financial Statement Yearly 2025 (Audited)"; the MD&A under
# "Management Discussion and Analysis Quarter 1 Ending 31 Mar 2026".
KIND_RE = {
    "mda": re.compile(r"management discussion", re.IGNORECASE),
    "fs": re.compile(r"financial statement", re.IGNORECASE),
}

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# The async fetch run INSIDE the loaded SET page — same-origin, so it bypasses the external 403.
# Kept as ONE script-side round trip per symbol (search, then each selected filing's detail page)
# so the browser only needs to be launched once for the whole run.
SEARCH_JS = r"""
async (params) => {
  const url = `/api/set/news/search?symbol=${params.sym}&lang=en&fromDate=${params.fromDate}` +
              `&toDate=${params.toDate}&limit=60`;
  const r = await fetch(url);
  if (!r.ok) { return { error: `HTTP ${r.status}`, totalCount: 0, newsInfoList: [] }; }
  return await r.json();
}
"""

DETAIL_JS = r"""
async (params) => {
  const r = await fetch(`/en/market/news-and-alert/newsdetails?id=${params.id}&symbol=${params.sym}`);
  if (!r.ok) { return { error: `HTTP ${r.status}`, text: "" }; }
  const t = await r.text();
  return { text: t };
}
"""


def log(msg):
    # console is cp1252 on this box; a stray non-ASCII char (e.g. a Thai company name leaking into
    # a headline) must never crash the run — degrade to '?' rather than raise.
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "cp1252"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


def search_symbol(page, sym, from_date, to_date):
    """Returns the raw newsInfoList for one symbol (same-origin, from inside the loaded page)."""
    data = page.evaluate(SEARCH_JS, {"sym": sym, "fromDate": from_date, "toDate": to_date})
    if data.get("error"):
        log("  [%s] search error: %s" % (sym, data["error"]))
        return []
    return data.get("newsInfoList") or []


def fetch_detail_text(page, sym, filing_id):
    data = page.evaluate(DETAIL_JS, {"sym": sym, "id": filing_id})
    if data.get("error"):
        return None, data["error"]
    return data.get("text") or "", None


def select_filings(items, kind, per_symbol):
    """Filter to headlines matching the kind, newest first, top N."""
    rx = KIND_RE[kind]
    hits = [it for it in items if rx.search(it.get("headline") or "")]
    hits.sort(key=lambda it: it.get("datetime") or "", reverse=True)
    return hits[:per_symbol]


def download_attachment(url, dest_path):
    """Skip re-download if the file already exists (filings are immutable once filed)."""
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        with open(dest_path, "rb") as f:
            return f.read(), True
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://www.set.or.th/",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    magic = raw[:4]
    if url.lower().endswith(".pdf") and magic != b"%PDF":
        raise ValueError("response is not a PDF (first bytes: %r)" % raw[:16])
    if url.lower().endswith(".zip") and magic != b"PK\x03\x04":
        raise ValueError("response is not a ZIP (first bytes: %r)" % raw[:16])
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(raw)
    return raw, False


def extract_pdf_text(raw):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        n_pages = len(pdf.pages)
        parts = []
        for p in pdf.pages:
            try:
                parts.append(p.extract_text() or "")
            except Exception as e:  # a single malformed page must not kill the whole extraction
                parts.append("")
                log("    [warn] page extract failed: %s" % e)
    return "\n".join(parts), n_pages


def docx_text(raw):
    """Flatten a .docx to text, PARAGRAPHS AND TABLES, in document order.

    No python-docx dependency: a .docx is a zip whose word/document.xml holds w:p paragraphs and
    w:tbl tables. Tables matter more than the prose here — the Stage 1/2/3 ECL split, the allowance
    roll-forward and the receivables-by-collateral breakdown are ALL tables, so a paragraph-only
    reader would return a document full of accounting boilerplate and none of the numbers.
    Cells are joined with ' | ' and never truncated; a truncated cell is a lost number.
    """
    z = zipfile.ZipFile(io.BytesIO(raw))
    if "word/document.xml" not in z.namelist():
        raise ValueError("docx has no word/document.xml")
    body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
    if body is None:
        raise ValueError("docx has no w:body")
    out, n_tables = [], 0
    for el in body:
        if el.tag == W + "p":
            t = "".join(n.text or "" for n in el.iter(W + "t")).strip()
            if t:
                out.append(t)
        elif el.tag == W + "tbl":
            rows = []
            for tr in el.findall(W + "tr"):
                cells = [" ".join("".join(n.text or "" for n in p.iter(W + "t")).strip()
                                 for p in tc.findall(W + "p")).strip()
                         for tc in tr.findall(W + "tc")]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                n_tables += 1
                out.append("\n[TABLE %d]" % n_tables)
                out.extend(rows)
                out.append("[/TABLE %d]\n" % n_tables)
    return "\n".join(out), n_tables


def xlsx_text(raw):
    """Flatten an .xlsx to tab-separated text, one block per sheet. SET ships the statements as a
    standardised workbook, so this is the balance sheet / P&L in machine-readable form."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    out, n_sheets = [], 0
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            if row is None or all(c is None or str(c).strip() == "" for c in row):
                continue
            rows.append("\t".join("" if c is None else str(c).strip() for c in row))
        if rows:
            n_sheets += 1
            out.append("\n[SHEET: %s]" % ws.title)
            out.extend(rows)
    wb.close()
    return "\n".join(out), n_sheets


def extract_zip_members(raw):
    """Extract every readable member of a Financial-Statement zip.

    Returns (parts, members) where parts is {member_name: text}. Member names are NOT hardcoded:
    SET's own naming (NOTES.DOCX / FINANCIAL_STATEMENTS.XLSX / AUDITOR_REPORT.DOCX) is consistent
    today, but a filer who ships NOTES.PDF or a Thai-named member must still be read, not skipped.
    Dispatch is by EXTENSION, and an unreadable member is recorded, never silently dropped.
    """
    z = zipfile.ZipFile(io.BytesIO(raw))
    parts, members = {}, []
    for info in sorted(z.infolist(), key=lambda i: i.filename):
        name = info.filename
        if info.is_dir():
            continue
        ext = os.path.splitext(name)[1].lower()
        rec = {"name": name, "bytes": info.file_size, "ext": ext}
        try:
            data = z.read(info)
            if ext == ".docx":
                txt, n = docx_text(data)
                rec["n_tables"] = n
            elif ext == ".xlsx":
                txt, n = xlsx_text(data)
                rec["n_sheets"] = n
            elif ext == ".pdf":
                txt, n = extract_pdf_text(data)
                rec["n_pages"] = n
            elif ext in (".txt", ".csv", ".htm", ".html", ".xml"):
                txt = data.decode("utf-8", errors="replace")
            else:
                rec["status"] = "skipped_unsupported_ext"
                members.append(rec)
                continue
            parts[name] = txt
            rec["status"] = "ok"
            rec["n_chars"] = len(txt)
        except Exception as e:
            rec["status"] = "extract_failed"
            rec["error"] = str(e)
        members.append(rec)
    return parts, members


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMS))
    ap.add_argument("--kind", default="both", choices=["mda", "fs", "both"],
                    help="mda = Management Discussion & Analysis (PDF narrative); "
                         "fs = Financial Statements + NOTES (ZIP); both = default")
    ap.add_argument("--per-symbol", type=int, default=4,
                    help="newest N filings of EACH kind to keep per symbol (default 4)")
    ap.add_argument("--from-date", default="01/01/2026", help="search window start, DD/MM/YYYY")
    args = ap.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    kinds = ["mda", "fs"] if args.kind == "both" else [args.kind]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pull_set_filings.py: needs Playwright — pip install playwright && python -m "
                 "playwright install chromium")
    try:
        import pdfplumber  # noqa: F401  (import check only — used lazily in extract_pdf_text)
    except ImportError:
        sys.exit("pull_set_filings.py: needs pdfplumber — pip install pdfplumber")
    if "fs" in kinds:
        try:
            import openpyxl  # noqa: F401  (import check only — used lazily in xlsx_text)
        except ImportError:
            sys.exit("pull_set_filings.py: --kind fs needs openpyxl — pip install openpyxl")

    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(ZIP_DIR, exist_ok=True)
    os.makedirs(TEXT_DIR, exist_ok=True)

    to_date = datetime.date.today().strftime("%d/%m/%Y")

    # --- Phase 1: browser session — search + resolve attachment URLs for every symbol -----------
    resolved = []  # list of dict: symbol, kind, id, date, headline, url
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(user_agent=UA)
        pg.goto("https://www.set.or.th/en/market/product/stock/quote/%s/price" % syms[0],
                wait_until="domcontentloaded", timeout=45000)

        for sym in syms:
            try:
                items = search_symbol(pg, sym, args.from_date, to_date)
            except Exception as e:
                log("  [%s] search FAILED: %s" % (sym, e))
                continue
            for kind in kinds:
                chosen = select_filings(items, kind, args.per_symbol)
                log("  [%s/%s] %d news items in window, %d matches, keeping newest %d"
                    % (sym, kind, len(items),
                       sum(1 for it in items if KIND_RE[kind].search(it.get("headline") or "")),
                       len(chosen)))
                for it in chosen:
                    fid = str(it.get("id"))
                    headline = it.get("headline") or ""
                    dt_raw = it.get("datetime") or ""
                    date_iso = dt_raw[:10] if dt_raw else "unknown-date"
                    base = {"symbol": sym, "kind": kind, "id": fid, "date": date_iso,
                            "headline": headline}
                    try:
                        text, err = fetch_detail_text(pg, sym, fid)
                    except Exception as e:
                        text, err = None, str(e)
                    if err or text is None:
                        log("    [%s] id=%s detail FAILED: %s" % (sym, fid, err))
                        resolved.append(dict(base, status="detail_fetch_failed", error=err))
                        continue
                    m = ATTACH_URL_RE.findall(text)
                    if not m:
                        log("    [%s] id=%s (%s): no attachment url in detail page"
                            % (sym, fid, date_iso))
                        resolved.append(dict(base, status="no_attachment_url"))
                        continue
                    if len(set(m)) > 1:
                        log("    [%s] id=%s: %d distinct attachment urls, using the first"
                            % (sym, fid, len(set(m))))
                    resolved.append(dict(base, url=m[0], status="resolved"))
        br.close()

    # --- Phase 2: plain urllib — download + extract each resolved attachment (no browser) -------
    index = []
    n_ok, n_fail = 0, 0
    for rec in resolved:
        sym, kind, fid, date_iso = rec["symbol"], rec["kind"], rec["id"], rec["date"]
        entry = {"symbol": sym, "kind": kind, "id": fid, "date": date_iso,
                 "headline": rec.get("headline"), "url": rec.get("url")}
        if rec["status"] != "resolved":
            entry["status"] = rec["status"]
            entry["error"] = rec.get("error")
            index.append(entry)
            n_fail += 1
            continue

        url = rec["url"]
        is_zip = url.lower().endswith(".zip")
        base = "%s_%s_%s_%s" % (sym, kind, date_iso, fid)
        raw_dir = ZIP_DIR if is_zip else PDF_DIR
        raw_path = os.path.join(raw_dir, base + (".zip" if is_zip else ".pdf"))
        try:
            raw, cached = download_attachment(url, raw_path)
        except Exception as e:
            log("  [%s] %s: DOWNLOAD FAILED: %s" % (sym, base, e))
            entry.update(status="download_failed", error=str(e))
            index.append(entry)
            n_fail += 1
            continue
        entry["raw_path"] = os.path.relpath(raw_path, ROOT).replace("\\", "/")
        entry["sha256"] = hashlib.sha256(raw).hexdigest()
        entry["cached"] = cached

        try:
            if is_zip:
                parts, members = extract_zip_members(raw)
                entry["members"] = members
            else:
                txt, n_pages = extract_pdf_text(raw)
                parts = {base + ".pdf": txt}
                entry["n_pages"] = n_pages
        except Exception as e:
            log("  [%s] %s: EXTRACT FAILED: %s" % (sym, base, e))
            entry.update(status="extract_failed", error=str(e))
            index.append(entry)
            n_fail += 1
            continue

        if not parts:
            log("  [%s] %s: attachment yielded NO readable text" % (sym, base))
            entry["status"] = "no_text"
            index.append(entry)
            n_fail += 1
            continue

        # One .txt per readable member so the notes stay addressable on their own — an agent asked
        # for "the ECL note" should not have to scan the auditor's report to find it.
        written = []
        for member, txt in sorted(parts.items()):
            # A zip member names itself (NOTES / AUDITOR_REPORT / ...); a bare PDF does not, so it
            # is stamped with its KIND. Don't hardcode "MDA" here — an `fs` filing occasionally
            # arrives as a plain PDF announcement, and calling that file MDA would misname it.
            stem = os.path.splitext(os.path.basename(member))[0].upper() if is_zip else kind.upper()
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", stem)
            tp = os.path.join(TEXT_DIR, "%s__%s.txt" % (base, safe))
            with open(tp, "w", encoding="utf-8") as f:
                f.write(txt)
            written.append({"member": member,
                            "text_path": os.path.relpath(tp, ROOT).replace("\\", "/"),
                            "n_chars": len(txt)})
        entry["status"] = "ok"
        entry["text_files"] = written
        entry["n_chars"] = sum(w["n_chars"] for w in written)
        index.append(entry)
        n_ok += 1
        log("  [%s] %s: OK (%d file(s), %d chars%s)"
            % (sym, base, len(written), entry["n_chars"], ", cached" if cached else ""))

    # Merge into any existing index rather than clobber it — a subset run (--symbols MTC, or
    # --kind fs) must not discard the other symbols'/kind's already-resolved filings. For the
    # (symbol, kind) pairs IN this run the fresh entries fully replace the old rows (deterministic
    # re-derivation); everything else is carried forward untouched.
    ran = {(s, k) for s in syms for k in kinds}
    carried_forward = []
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, encoding="utf-8") as f:
                old = json.load(f)
            for e in old.get("filings", []):
                # Rows written before `kind` existed are all MD&A — label them rather than drop them.
                k = e.get("kind") or "mda"
                e.setdefault("kind", k)
                if (e.get("symbol"), k) not in ran:
                    carried_forward.append(e)
        except (OSError, ValueError) as e:
            log("  [warn] could not read existing index.json to merge, starting fresh: %s" % e)

    merged = carried_forward + index
    merged.sort(key=lambda e: (e["symbol"], e.get("kind", ""), e["date"]))
    all_symbols = sorted(set(syms) | {e["symbol"] for e in carried_forward})
    payload = {
        "meta": {
            "title": "SET filings — MD&A narrative + Financial Statements/NOTES for the six "
                     "SET-listed Thai title-loan peers (measured, autonomous pull)",
            "generated_by": "pipeline/pull_set_filings.py",
            "generated_date": datetime.date.today().isoformat(),
            "label": "MEASURED — Stock Exchange of Thailand (set.or.th) company disclosures. "
                     "kind=mda: the Management Discussion & Analysis PDF (management's narrative). "
                     "kind=fs: the Financial Statement ZIP, whose NOTES.DOCX carries the IFRS-9 "
                     "Stage 1/2/3 ECL tables, allowance movement and receivables-by-collateral "
                     "breakdowns, and whose FINANCIAL_STATEMENTS.XLSX carries the primary "
                     "statements. Text extracted with pdfplumber / openpyxl / a zip+XML docx "
                     "reader. Newest %d of each kind per symbol." % args.per_symbol,
            "source": "Stock Exchange of Thailand · set.or.th news search + weblink.set.or.th attachments",
            "symbols": all_symbols,
            "kinds": kinds,
            "last_run_symbols": syms,
            "search_window": {"from": args.from_date, "to": to_date},
            "per_symbol": args.per_symbol,
        },
        "filings": merged,
    }
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    log("wrote %s -- %d filings ok, %d failed" % (INDEX_PATH, n_ok, n_fail))


if __name__ == "__main__":
    main()
