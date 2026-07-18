#!/usr/bin/env python3
"""ingest_pdf.py — general-purpose PDF -> text/tables extraction (backend data capability).

So the platform is NOT limited to CSV/Excel sources: many Thai gov datasets (e.g. OAE crop
PRODUCTION-COST surveys) are published only as PDF, and some of those are SCANNED images with no
text layer. This module gives every puller a common way to pull data out of a PDF.

Two tiers, chosen PER PAGE automatically:
  - TEXT tier  — pdfplumber / PyMuPDF. Exact extraction of a real text layer (digital PDFs).
                 Deterministic, high-confidence. Also pulls ruled tables (pdfplumber.extract_tables).
  - OCR  tier  — PyMuPDF rasterises the page, Tesseract (Thai+English) reads it. For SCANNED PDFs.
                 Error-prone on Thai numerals — every OCR'd figure MUST be spot-verified against the
                 source page before it is trusted, and is tagged method="ocr" so downstream code and
                 provenance never present it as clean as a text/CSV pull.

A page is OCR'd only when its text layer is effectively empty (< `ocr_threshold` chars).

Determinism note: OCR output can vary across Tesseract versions, so this is an EXTRACTION (pull)
step — its distilled output is committed once (after verification) and the deterministic --check
gate runs against that committed JSON, exactly like the network pulls. Raw PDFs stay gitignored.

Deps: pdfplumber, pymupdf (text tier, pip); pytesseract + the `tesseract-ocr` binary with the `tha`
+ `eng` language packs (OCR tier). If OCR deps are missing, text-tier pages still work and OCR pages
are returned with method="ocr-unavailable" (never fabricated).

CLI:
  python3 ingest_pdf.py report.pdf                     # extract all pages -> stdout JSON summary
  python3 ingest_pdf.py report.pdf --pages 5-8         # just those pages (1-indexed, inclusive)
  python3 ingest_pdf.py report.pdf --grep ต้นทุน       # only lines matching a pattern
  python3 ingest_pdf.py report.pdf --json out.json     # full structured extract to a file
  python3 ingest_pdf.py https://host/report.pdf ...    # a URL is downloaded to a temp file first

As a library:
  from ingest_pdf import extract_pdf
  doc = extract_pdf("report.pdf", pages=(5, 8))
  for pg in doc["pages"]:
      print(pg["page"], pg["method"], pg["text"][:200])
"""
import argparse
import json
import os
import re
import sys
import tempfile
import urllib.request

OCR_THRESHOLD = 20          # a page with fewer extractable text chars is treated as scanned -> OCR
OCR_DPI = 200               # rasterisation DPI for the OCR tier
OCR_LANG = "tha+eng"


def _fetch(src):
    """Return a local path for a PDF given a path or an http(s) URL (temp file for URLs)."""
    if re.match(r"^https?://", src):
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
        fd, path = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path, True
    return src, False


def _ocr_page(fitz_page):
    """Rasterise a page and OCR it. Returns (text, method)."""
    try:
        import pytesseract          # noqa
        from PIL import Image       # noqa
        import io
    except Exception:
        return "", "ocr-unavailable"
    try:
        import fitz  # noqa
        pix = fitz_page.get_pixmap(dpi=OCR_DPI)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img, lang=OCR_LANG), "ocr"
    except Exception as e:
        return "", "ocr-error:%s" % type(e).__name__


def extract_pdf(src, pages=None, ocr_threshold=OCR_THRESHOLD, want_tables=True):
    """Extract text (+ ruled tables on text pages) from a PDF.

    src           path or http(s) URL
    pages         (first, last) 1-indexed inclusive, or None for all
    Returns {"meta": {...}, "pages": [{"page", "method", "text", "tables"}]}
    """
    import pdfplumber
    import fitz

    path, is_tmp = _fetch(src)
    try:
        out_pages = []
        counts = {"text": 0, "ocr": 0, "other": 0}
        with pdfplumber.open(path) as pl, fitz.open(path) as fz:
            n = len(pl.pages)
            lo = 1 if not pages else max(1, pages[0])
            hi = n if not pages else min(n, pages[1])
            for i in range(lo - 1, hi):
                pg = pl.pages[i]
                text = pg.extract_text() or ""
                tables = []
                if len(text.strip()) >= ocr_threshold:
                    method = "text"
                    if want_tables:
                        try:
                            tables = [t for t in (pg.extract_tables() or []) if t]
                        except Exception:
                            tables = []
                else:
                    text, method = _ocr_page(fz[i])
                counts["text" if method == "text" else ("ocr" if method == "ocr" else "other")] += 1
                out_pages.append({"page": i + 1, "method": method,
                                  "text": text, "tables": tables})
        return {"meta": {"source": src, "n_pages": n,
                         "pages_extracted": [lo, hi], "method_counts": counts,
                         "ocr_threshold": ocr_threshold, "ocr_lang": OCR_LANG,
                         "note": "method='text' = exact text layer (trust like CSV); "
                                 "method='ocr' = Tesseract on a scanned page — SPOT-VERIFY every "
                                 "figure before use; 'ocr-unavailable' = tesseract/pytesseract not "
                                 "installed (no data fabricated)."},
                "pages": out_pages}
    finally:
        if is_tmp:
            try:
                os.remove(path)
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", help="PDF path or http(s) URL")
    ap.add_argument("--pages", help="1-indexed inclusive range, e.g. 5-8 or a single page 5")
    ap.add_argument("--grep", help="only print lines matching this regex")
    ap.add_argument("--json", help="write the full structured extract to this file")
    ap.add_argument("--no-tables", action="store_true", help="skip table extraction")
    args = ap.parse_args()

    pages = None
    if args.pages:
        parts = args.pages.split("-")
        pages = (int(parts[0]), int(parts[-1]))

    doc = extract_pdf(args.pdf, pages=pages, want_tables=not args.no_tables)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print("wrote %s (%d pages; methods %s)" % (
            args.json, len(doc["pages"]), doc["meta"]["method_counts"]))
        return

    print("== %s ==" % args.pdf)
    print("pages %s of %d · methods %s" % (
        doc["meta"]["pages_extracted"], doc["meta"]["n_pages"], doc["meta"]["method_counts"]))
    pat = re.compile(args.grep) if args.grep else None
    for pg in doc["pages"]:
        lines = [ln for ln in pg["text"].splitlines() if ln.strip()]
        if pat:
            lines = [ln for ln in lines if pat.search(ln)]
        if lines:
            print("\n--- page %d [%s] ---" % (pg["page"], pg["method"]))
            for ln in lines[:40]:
                print(" ", ln[:110])
        if pg["tables"]:
            print("  (%d table(s) on page %d)" % (len(pg["tables"]), pg["page"]))


if __name__ == "__main__":
    main()
