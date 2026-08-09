#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
pull_investor_docs.py — MEASURED investor-facing disclosure for the six SET-listed Thai title
lenders, from the two channels that carry what the STATUTORY filings do not. Writes
source-data/investor_docs/.

Read pull_set_filings.py first — this is its sibling. That script pulls what companies file WITH
the exchange (MD&A narrative + audited financial statements and notes). This one pulls what they
publish FOR INVESTORS:

  annual  The 56-1 One Report — Thailand's combined annual registration statement and annual
          report. This is where the book split by PRODUCT AND COLLATERAL, branch counts by
          region, customer segments, market share and distribution economics live. All six peers'
          audited notes were checked and NOT ONE discloses a collateral split — it stops at "loan
          receivables" and "hire-purchase receivables". The 56-1 is the only public document that
          goes further, which is the entire reason this script exists.
  oppday  SET's Opportunity Day quarterly earnings-call decks — the current-quarter numbers with
          management's own framing, filed to SET's investor portal rather than as an announcement.

WHY NO BROWSER (unlike pull_set_filings.py): set.or.th's news API 403s external requests, so that
script needs a headless Chromium. Neither channel here does — verified live, every URL below
returns HTTP 200/206 with a `%PDF` magic over plain urllib with a browser User-Agent. That makes
this script CI-runnable with no chromium install.

--------------------------------------------------------------------------------------------
THE 56-1 IS NOT FILED TO SET. Do not go looking for it there — it cost a full pass to learn.
SET carries only a NOTICE ("Publication of the Annual Report (Form 56-1 One Report) on the
Company's website") with the notice itself as the sole attachment. The document lives on each
company's IR site, and there is no single index of those.

SEC Thailand is ALSO a dead end, checked directly: market.sec.or.th's iDisc is a securities-
OFFERING registry (its filing search returns MTC's 2014 IPO prospectus and nothing else — one row
per fundraising event, and none of its 11 filter categories is "56-1"/"Annual Report"), and
www.sec.or.th is blanket WAF-blocked, every path returning HTTP 403.

So the URLs below were each followed from a real link on a real page. NONE was constructed by
pattern. That distinction matters: an earlier attempt guessed six `investor.<brand>.com` addresses
and five did not resolve at all, which is the same failure mode as guessing a Thai search string —
it fails silently and teaches you nothing. Five of the six run on `listedcompany.com` (the IR Plus
platform); MTC alone uses Optiwise; and TIDLOR's IR domain is `tidlorinvestor.com`, reachable only
via a "For Shareholders" link in tidlor.com's own footer — no amount of pattern-guessing finds it.

Because these are hand-verified per edition, `--kind annual` VERIFIES each URL still serves a PDF
and fails loudly with the rediscovery recipe rather than silently writing a 404 page to disk. When
the FY2026 editions publish (~March 2027) this registry needs one manual refresh; the docstring
above is the recipe.
--------------------------------------------------------------------------------------------

  python3 pull_investor_docs.py                       # both kinds, EN, all 6
  python3 pull_investor_docs.py --kind annual --lang both
  python3 pull_investor_docs.py --kind oppday --per-symbol 12
  python3 pull_investor_docs.py --symbols MTC,SAWAD --no-text   # download only, skip extraction
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "source-data", "investor_docs")
PDF_DIR = os.path.join(OUT_DIR, "pdf")
TEXT_DIR = os.path.join(OUT_DIR, "text")
INDEX_PATH = os.path.join(OUT_DIR, "index.json")

DEFAULT_SYMS = ["MTC", "TIDLOR", "SAWAD", "TURBO", "HENG", "SAK"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 56-1 One Report FY2025. Every URL verified live 2026-08-09: HTTP 200/206, body starts %PDF.
# `ir` is the IR site the link was followed FROM — kept so the next edition can be rediscovered
# without repeating the search, and so a dead link is diagnosable rather than mysterious.
ANNUAL = {
    "MTC": {"ir": "https://investor.muangthaicap.com/th", "platform": "Optiwise",
            "en": "https://hub.optiwise.io/storage/118/annual-report/2025/mtc-or2025-en.pdf",
            "th": "https://hub.optiwise.io/storage/118/annual-report/2025/mtc-or2025-th.pdf"},
    "SAWAD": {"ir": "https://investor.sawad.co.th", "platform": "listedcompany.com",
              "en": "https://sawad.listedcompany.com/misc/ar/20260327-sawad-ar-2025-en.pdf",
              "th": "https://sawad.listedcompany.com/misc/ar/20260327-sawad-ar-2025-th.pdf"},
    "TURBO": {"ir": "https://investor.turbo.co.th", "platform": "listedcompany.com",
              "en": "https://turbo.listedcompany.com/misc/one-reports/20260331-turbo-or2025-en.pdf",
              "th": "https://turbo.listedcompany.com/misc/one-reports/20260331-turbo-or2025-th.pdf"},
    "HENG": {"ir": "https://investor.hengleasing.com", "platform": "listedcompany.com",
             "en": "https://heng.listedcompany.com/misc/form561/20260317-heng-one-report-2025-en.pdf",
             "th": "https://heng.listedcompany.com/misc/form561/20260317-heng-one-report-2025-th.pdf"},
    "SAK": {"ir": "https://investor.saksiam.com", "platform": "listedcompany.com",
            "en": "https://sak.listedcompany.com/misc/one-report/20260323-sak-one-report-2025-en.pdf",
            "th": "https://sak.listedcompany.com/misc/one-report/20260323-sak-one-report-2025-th.pdf"},
    # TIDLOR's "-en" file is a live PDF but its CONTENT is Thai — byte-identical to the -th file.
    # The English edition simply has not been uploaded; the EN button serves the Thai document.
    # Recorded as an honest caveat rather than silently pulling the same file twice.
    "TIDLOR": {"ir": "https://www.tidlorinvestor.com", "platform": "listedcompany.com",
               "th": "https://ntl.listedcompany.com/misc/one-report/tidlor-one-report-2025-th-ntl.pdf",
               "en_is_thai": True,
               "en": "https://ntl.listedcompany.com/misc/one-report/tidlor-one-report-2025-en-ntl.pdf"},
}
ANNUAL_YEAR = 2025

# SET Opportunity Day. TWO-STEP API, captured from the site driving its own search drawer.
# The sibling /api/v1/investor/archive endpoint looks right and is a trap: it accepts POST but
# SILENTLY IGNORES every filter body, always returning the same latest-10 rows regardless of
# symbol. Use /search — its `keyword` field takes a plain ticker and really filters.
OPPDAY_HOST = "https://api.lcp.setgroup.or.th"
OPPDAY_SEARCH = OPPDAY_HOST + "/api/v1/investor/search"
OPPDAY_VDO = OPPDAY_HOST + "/api/v1/investor/vdo/%s"


def log(msg):
    # console is cp1252 on the owner's box; a Thai company name in a title must not crash the run.
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "cp1252"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


def http(url, referer=None, data=None, timeout=180):
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, headers=headers, data=body)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download_pdf(url, dest, referer=None):
    """Filings/decks are immutable once published, so an existing file is authoritative."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        with open(dest, "rb") as f:
            return f.read(), True
    raw = http(url, referer=referer)
    if raw[:4] != b"%PDF":
        raise ValueError("not a PDF (first bytes %r) — the URL may have moved; rediscover it from "
                         "the IR site named in the registry" % raw[:16])
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(raw)
    return raw, False


def extract_text(raw):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        n = len(pdf.pages)
        parts = []
        for p in pdf.pages:
            try:
                parts.append(p.extract_text() or "")
            except Exception as e:  # one malformed page must not lose the other 300
                parts.append("")
                log("      [warn] page extract failed: %s" % e)
    return "\n".join(parts), n


def oppday_events(sym, per_symbol):
    """Newest N Opportunity Day events for one symbol, each resolved to its slide-deck URL."""
    search = json.loads(http(OPPDAY_SEARCH, referer="https://opportunity-day.setgroup.or.th/",
                             data={"start": 1, "page_size": max(per_symbol, 12), "keyword": sym,
                                   "year": None, "theme_id": None, "type_id": None, "market": None,
                                   "stage_id": None, "industry_id": None, "trust_id": None}))
    # `keyword` is a free-text match, so a ticker can pull in another company's row — filter on the
    # returned symbol rather than trusting the search to have matched only what we asked for.
    vdos = [v for v in (search.get("vdos") or []) if (v.get("symbol") or "").upper() == sym]
    vdos.sort(key=lambda v: v.get("meeting_date") or "", reverse=True)
    out = []
    for v in vdos[:per_symbol]:
        try:
            d = json.loads(http(OPPDAY_VDO % v["id"], referer="https://opportunity-day.setgroup.or.th/"))
        except Exception as e:
            log("    [%s] vdo %s detail FAILED: %s" % (sym, v.get("id"), e))
            continue
        link = d.get("document_link")
        out.append({
            "symbol": sym, "event_id": d.get("id"), "year": d.get("year"),
            "round": d.get("round"), "round_name": d.get("round_name"), "type": d.get("type"),
            "meeting_date": (d.get("meeting_date") or "")[:10],
            # document_link is RELATIVE and must be prefixed with the API host — the frontend
            # host (opportunity-day.setgroup.or.th) 404s on the same path.
            "pdf_url": (OPPDAY_HOST + link) if link else None,
            "video_link": d.get("video_link"), "snapshot_link": d.get("snapshot_link"),
            "has_transcription": d.get("has_transcription"), "has_summary": d.get("has_summary"),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMS))
    ap.add_argument("--kind", default="both", choices=["annual", "oppday", "both"])
    ap.add_argument("--lang", default="en", choices=["en", "th", "both"],
                    help="56-1 edition(s) to pull (default en)")
    ap.add_argument("--per-symbol", type=int, default=8,
                    help="newest N Opportunity Day decks per symbol (default 8)")
    ap.add_argument("--no-text", action="store_true", help="download only, skip text extraction")
    args = ap.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    kinds = ["annual", "oppday"] if args.kind == "both" else [args.kind]
    langs = ["en", "th"] if args.lang == "both" else [args.lang]

    if not args.no_text:
        try:
            import pdfplumber  # noqa: F401  (import check only — used lazily in extract_text)
        except ImportError:
            sys.exit("pull_investor_docs.py: needs pdfplumber — pip install pdfplumber "
                     "(or pass --no-text)")

    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(TEXT_DIR, exist_ok=True)
    entries = []
    n_ok = n_fail = 0

    def handle(kind, sym, label, url, referer, meta):
        nonlocal n_ok, n_fail
        base = "%s_%s_%s" % (sym, kind, label)
        pdf_path = os.path.join(PDF_DIR, base + ".pdf")
        e = dict(meta, symbol=sym, kind=kind, label=label, url=url,
                 pdf_path=os.path.relpath(pdf_path, ROOT).replace("\\", "/"))
        try:
            raw, cached = download_pdf(url, pdf_path, referer=referer)
        except Exception as ex:
            log("  [%-6s] %-26s DOWNLOAD FAILED: %s" % (sym, label, str(ex)[:100]))
            e.update(status="download_failed", error=str(ex))
            entries.append(e)
            n_fail += 1
            return
        e.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), cached=cached)
        if args.no_text:
            e["status"] = "downloaded"
            entries.append(e)
            n_ok += 1
            log("  [%-6s] %-26s OK %.1fMB%s (no text)"
                % (sym, label, len(raw) / 1e6, ", cached" if cached else ""))
            return
        try:
            text, n_pages = extract_text(raw)
        except Exception as ex:
            log("  [%-6s] %-26s EXTRACT FAILED: %s" % (sym, label, str(ex)[:100]))
            e.update(status="extract_failed", error=str(ex))
            entries.append(e)
            n_fail += 1
            return
        tp = os.path.join(TEXT_DIR, base + ".txt")
        with open(tp, "w", encoding="utf-8") as f:
            f.write(text)
        e.update(status="ok", n_pages=n_pages, n_chars=len(text),
                 text_path=os.path.relpath(tp, ROOT).replace("\\", "/"))
        entries.append(e)
        n_ok += 1
        log("  [%-6s] %-26s OK %.1fMB, %d pages, %d chars%s"
            % (sym, label, len(raw) / 1e6, n_pages, len(text), ", cached" if cached else ""))

    if "annual" in kinds:
        log("== 56-1 One Report FY%d ==" % ANNUAL_YEAR)
        for sym in syms:
            reg = ANNUAL.get(sym)
            if not reg:
                log("  [%-6s] no registry entry — rediscover from its IR site (see docstring)" % sym)
                continue
            for lang in langs:
                url = reg.get(lang)
                if not url:
                    log("  [%-6s] no %s edition registered" % (sym, lang))
                    continue
                meta = {"year": ANNUAL_YEAR, "lang": lang, "ir_site": reg["ir"],
                        "platform": reg["platform"]}
                if lang == "en" and reg.get("en_is_thai"):
                    # Not a bug to fix silently: the file really is served, it is just the Thai
                    # edition wearing an -en filename. Recorded so nobody reads it as English.
                    meta["caveat"] = ("the -en file is byte-identical to the -th file; the English "
                                      "edition has not been published, the EN link serves Thai")
                handle("annual", sym, "%d_%s" % (ANNUAL_YEAR, lang), url, reg["ir"], meta)

    if "oppday" in kinds:
        log("== Opportunity Day decks (newest %d per symbol) ==" % args.per_symbol)
        for sym in syms:
            try:
                evs = oppday_events(sym, args.per_symbol)
            except Exception as ex:
                log("  [%-6s] search FAILED: %s" % (sym, str(ex)[:100]))
                n_fail += 1
                continue
            log("  [%-6s] %d event(s)" % (sym, len(evs)))
            for ev in evs:
                if not ev["pdf_url"]:
                    entries.append(dict(ev, kind="oppday", status="no_document",
                                        label=str(ev["event_id"])))
                    continue
                label = "%s_%s" % (ev.get("round_name") or ev.get("meeting_date"), ev["event_id"])
                label = label.replace("/", "-").replace(" ", "")
                handle("oppday", sym, label, ev["pdf_url"],
                       "https://opportunity-day.setgroup.or.th/", ev)

    # Merge, not clobber: a subset run (--symbols MTC, or --kind oppday) must not discard the
    # other symbols'/kinds' already-pulled rows.
    ran = {(s, k) for s in syms for k in kinds}
    carried = []
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, encoding="utf-8") as f:
                old = json.load(f)
            carried = [e for e in old.get("documents", [])
                       if (e.get("symbol"), e.get("kind")) not in ran]
        except (OSError, ValueError) as ex:
            log("  [warn] could not merge existing index.json, starting fresh: %s" % ex)

    merged = carried + entries
    merged.sort(key=lambda e: (e.get("symbol") or "", e.get("kind") or "", e.get("label") or ""))
    payload = {
        "meta": {
            "title": "Investor-facing disclosure — 56-1 One Report + SET Opportunity Day decks "
                     "for the six SET-listed Thai title-loan peers",
            "generated_by": "pipeline/pull_investor_docs.py",
            "generated_date": datetime.date.today().isoformat(),
            "label": "MEASURED — companies' own published investor documents. kind=annual: the "
                     "56-1 One Report (Thailand's annual registration statement), the only public "
                     "document carrying a product/collateral split — the audited notes of all six "
                     "peers stop at 'loan receivables' + 'hire-purchase receivables'. kind=oppday: "
                     "SET Opportunity Day quarterly earnings-call slide decks.",
            "source": "Company IR sites (Optiwise / listedcompany.com) + SET Opportunity Day "
                      "(api.lcp.setgroup.or.th). The 56-1 is NOT filed to SET and NOT available "
                      "from SEC Thailand — see this script's docstring.",
            "annual_year": ANNUAL_YEAR,
            "symbols": sorted(set(syms) | {e.get("symbol") for e in carried if e.get("symbol")}),
            "kinds": kinds,
            "langs": langs,
            "per_symbol_oppday": args.per_symbol,
        },
        "documents": merged,
    }
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    log("\nwrote %s -- %d ok, %d failed" % (INDEX_PATH, n_ok, n_fail))
    return 0 if n_ok else 1


if __name__ == "__main__":
    sys.exit(main())
