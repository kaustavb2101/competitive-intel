#!/usr/bin/env python3
# investor_docs_guard.py — the PROVENANCE-HONESTY gate for the rival investor-disclosure TEXT corpus.
#
# CLAUDE.md: "Always state whether a number is measured or estimated." — and Kaustav explicitly
# distrusts a number dressed up as measured when it is not. `source-data/investor_docs/` is the 56-1
# One Report + SET Opportunity Day corpus for the six SET-listed title-loan peers
# (HENG/MTC/SAK/SAWAD/TIDLOR/TURBO), pulled by pull_investor_docs.py. Two of its signals are ALREADY
# distilled SAFELY and stay allowed by this guard:
#   - build_peer_oppday.py projects the STRUCTURED index.json (the earnings-call calendar/recency);
#     it invents no figure.
#   - build_competitor_coverage.py carries a hand-curated BRANCH_TRAJECTORY where every rival branch
#     count is a per-figure CITED public number (each with its verbatim source quote); it only NAMES
#     the text files as a `src` provenance string, it never opens them.
#
# WHAT THIS GUARD PROTECTS — the ONE remaining honesty hazard: the deeper financials (product /
# collateral split, NPL %, yield) live only in the free `investor_docs/text/*.txt` files, and reading
# those is a fabrication trap (audited 2026-08-30):
#   - The annual 56-1 text is a MULTI-COLUMN PDF dump with columns interleaved line-by-line — e.g.
#     MTC_annual_2025_en.txt line 900 is "Mil. Baht % Mil. Baht % Mil. Baht %" with product rows and
#     values scattered across adjacent columns. There is no reliable within-line label<->value
#     pairing; a regex that scrapes a "%" onto a product label mis-attributes.
#   - 5 of 6 annual PDFs are status "download_failed" in index.json; the large .txt files persist from
#     an OLDER pull, so scraping them also publishes a stale vintage as current.
#   - The oppday transcripts state figures inconsistently across the six (bilingual Thai prior-vs-
#     current pairs, partner-branch mixing), so one regex mis-picks.
#   The determinism gate cannot catch a semantically-WRONG-but-syntactically-valid number, so ONLY a
#   semantic guard protects the honesty mandate here. The obvious safe signals are now taken, so the
#   next temptation is precisely a naive open()-and-scrape of these text files.
#
# WHY THIS EXISTS (same argument as mandate_guard.py / unverified_gpp_guard.py): good labelling and a
# one-time audit are not enough because nothing in the gate LOCKS IT IN, and the corpus is literally
# the top-named integration backlog item, so the next autonomous run WILL be pointed at it. This turns
# "skip it, don't fake it, and log why" into an automated regression gate.
#
# THE INVARIANT (precise, false-positive-free): the guard FAILs if any pipeline/*.py APPLIES A READ
# PRIMITIVE (open / io.open / read_text / read_bytes / glob / iglob / listdir / scandir) to a path
# under `investor_docs/.../text` — i.e. actually parses the raw disclosure text. It does NOT fire on
# reading index.json, nor on merely NAMING a text file in a citation string (the existing legitimate
# consumers), because neither wraps the text path in a read call.
#
# SELF-LIFTING escape hatch (a deliberate reviewed act): land a per-figure verification manifest at
# `source-data/investor_docs/verified_figures.json` (each figure hand-verified against its verbatim
# source line) and the guard passes trivially — a real verified extraction is never blocked, only a
# naive scrape. (Or add the reading builder to ALLOWED with a reason.)
#
# Offline, stdlib-only, deterministic. Exit 0 = clean (no text-scrape, or a verification manifest
# exists); 1 = a raw-text-scrape path is live without verification.

import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CORPUS = os.path.join(REPO, "source-data", "investor_docs")
MANIFEST = os.path.join(CORPUS, "verified_figures.json")

# Scripts explicitly permitted to read the raw text (none today; add here with a reason only after a
# per-figure verification discipline is in place — a deliberate reviewed act).
ALLOWED = set()

# A read primitive whose argument path reaches into investor_docs/.../text. `[^)]` keeps the match
# inside a single call's parentheses, so it fires on open("…/investor_docs/text/…") and
# open(os.path.join(…,"investor_docs","text",…)) but NOT on a bare citation string (no read verb
# wraps it) nor on reading index.json (no "text" segment).
READ_TEXT = re.compile(
    r"(?:open|io\.open|read_text|read_bytes|glob|iglob|listdir|scandir)\s*"
    r"\([^)]{0,240}investor_docs[^)]{0,120}text",
    re.IGNORECASE,
)


def _scrapers(texts_by_name, allowed):
    """Names in texts_by_name (a {name: source_text} map) that apply a read primitive to the text
    corpus, excluding the allowed set. Pure function so the self-test can feed synthetic inputs."""
    return sorted(name for name, txt in texts_by_name.items()
                  if name not in allowed and READ_TEXT.search(txt))


def _selftest():
    """Prove the guard FIRES on a raw-text read and stays QUIET on the two legitimate patterns (an
    index.json read; a text filename used only as a citation string). A drift here is itself a gate
    failure, so the guard can never pass vacuously."""
    fails = []
    # must fire: a plain-string open of the annual text
    a = {"build_x.py": "open('source-data/investor_docs/text/MTC_annual_2025_en.txt').read()"}
    if _scrapers(a, ALLOWED) != ["build_x.py"]:
        fails.append("SHOULD-FIRE on open() of a text file — did not")
    # must fire: os.path.join-style glob of the text dir
    b = {"build_y.py": 'glob.glob(os.path.join(ROOT,"source-data","investor_docs","text","*.txt"))'}
    if _scrapers(b, ALLOWED) != ["build_y.py"]:
        fails.append("SHOULD-FIRE on glob() of the text dir — did not")
    # must stay quiet: reading the STRUCTURED index.json (build_peer_oppday.py's real pattern)
    idx = {"build_peer_oppday.py": 'IN=os.path.join(R,"source-data","investor_docs","index.json")\n'
                                   "with io.open(IN) as f: d=json.load(f)"}
    if _scrapers(idx, ALLOWED) != []:
        fails.append("FALSE POSITIVE: flagged an index.json read")
    # must stay quiet: a text filename used ONLY as a citation string (build_competitor_coverage.py)
    cite = {"build_competitor_coverage.py":
            '{"branches":743,"src":"Heng annual report 2025 — 743 branch offices. '
            'source-data/investor_docs/text/HENG_annual_2025_en.txt"}'}
    if _scrapers(cite, ALLOWED) != []:
        fails.append("FALSE POSITIVE: flagged a bare citation string, not a read")
    return fails


def main():
    st = _selftest()
    if st:
        print("investor_docs_guard: SELF-TEST FAILED (guard logic is unsound, not a data problem):")
        for f in st:
            print("   -", f)
        return 1

    if not os.path.isdir(CORPUS):
        print("investor_docs_guard: OK — source-data/investor_docs/ absent, nothing to guard.")
        return 0

    if os.path.exists(MANIFEST):
        print("investor_docs_guard: OK — source-data/investor_docs/verified_figures.json is present; "
              "a per-figure verification manifest exists, so parsing the raw text is now allowed.")
        return 0

    pipe = {}
    for p in sorted(glob.glob(os.path.join(REPO, "pipeline", "*.py"))):
        pipe[os.path.basename(p)] = open(p, encoding="utf-8", errors="ignore").read()
    hits = _scrapers(pipe, ALLOWED)

    if hits:
        print("investor_docs_guard: a pipeline script is PARSING the raw investor-disclosure text "
              "(source-data/investor_docs/text/*.txt) without a verification manifest. That text is "
              "multi-column-garbled, 5/6 annual PDFs are stale download_failures, and its figures are "
              "stated inconsistently across the six peers — a naive scrape mis-attributes numbers and "
              "would ship a WRONG figure labelled MEASURED, which the determinism gate cannot catch.")
        for name in hits:
            print("   raw-text scraper: %s reads investor_docs/.../text (index.json + cited figures "
                  "are the only sanctioned uses)." % name)
        print("   Fix: land source-data/investor_docs/verified_figures.json — each extracted figure "
              "hand-verified against its verbatim source line (which lifts this guard automatically) "
              "— OR, if a legitimate ESTIMATED integration is truly intended, label it estimated and "
              "add the builder to this guard's ALLOWED set with a reason, a deliberate reviewed act.")
        return 1

    print("investor_docs_guard: OK — no pipeline script parses the raw investor_docs text "
          "(index.json projection + hand-cited figures are the only sanctioned uses; no verified-"
          "figure manifest yet, so a naive text scrape stays blocked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
