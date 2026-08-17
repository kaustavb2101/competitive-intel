#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_rival_rates.py — MEASURED rival rate OBSERVATION, pulled live from each operator's own
rate_url (objective #2, the rate board's staleness problem).

WHY THIS EXISTS. source-data/rival_rate_card.json pins a `rate_url` + `rate_fetch` for all 23
operators in rival_universe.json, but until this script existed nothing ever re-read them. The
rate board and build_promo_gap.py's undercut check both measure against that card, so a page
that quietly changed its published rate would sit undetected forever — the card would keep
answering a question the market had already stopped asking. This is the puller that closes that
loop: it re-visits every pinned URL and reports what changed, on a schedule the owner sets
separately (this script is deliberately NOT wired into any workflow — see the docstring's
CONSTRAINTS note below).

WHAT THIS IS NOT — READ THIS BEFORE TOUCHING rival_rate_card.json. That file is hand-curated:
every variant's collateral classification, provenance note and caveat was decided by a human
reading the page in context (the SCB_MCMC "same group, not a rival" framing, the KBANK_RCD
walk-in-vs-existing-customer split, TIDLOR's promo-vs-worked-example distinction — none of that
is recoverable from page text by a scraper). So this script NEVER writes rival_rate_card.json.
It writes a separate file, source-data/rival_rate_observed.json, and prints a DRIFT report
against the curated card so a human decides what (if anything) to fold in. Silently overwriting
curated judgement with scraped text is the one failure mode this script exists to avoid.

REFUSING TO GUESS A BASIS. Thai vehicle lending quotes two incompatible conventions (FLAT vs
REDUCING-BALANCE/"effective") that are ~4x apart on the same money — see pipeline/rate_basis.py
for the full explanation, which this script imports rather than re-deriving. A rate is only
converted to its reducing-balance equivalent when the PAGE ITSELF states which basis it is
quoting, in the text immediately around that number. If it does not, `basis` is recorded null
and NO effective figure is computed — never inferred, never assumed from a "everyone here quotes
X" prior. The basis reader is scoped to a NARROW character window anchored on that exact number,
falling back to its own line and never wider — a rate-card page routinely pairs a flat figure
with its OWN reducing-balance equivalent in the SAME sentence ("อัตราดอกเบี้ยคงที่ 5% ต่อปี
(อัตราดอกเบี้ยที่แท้จริง 8.97% ต่อปี)", ttbbank.com and scb.co.th both do this), and
rate_basis.basis_kind_in() is documented to prefer "effective" whenever a span states both cues —
correct for classifying ONE clause as a whole, but wrong if that whole clause is handed in for
BOTH numbers in it, which would relabel the flat 5% as effective too. Anchoring narrowly on each
number keeps its own cue attached to it instead of borrowing its neighbour's — see the
BASIS_NEAR_BEFORE/AFTER comment below for the exact failure this was tuned against.

A PERCENTAGE IS NOT AUTOMATICALLY A RATE. "วงเงิน 160%" is an LTV, "ลดสูงสุด 50%" is a discount,
"ลดดอก 2% ต่อปี" is a reduction OFF a rate — each would read as a spectacular headline rate if
matched naively. This script carries the exact NOT_A_RATE discipline from build_promo_gap.py
(same guard words, same "unit word required" rule: a bare percentage with no ต่อเดือน/ต่อปี is
never treated as a rate at all) — reimplemented here rather than imported, because a network
PULLER importing a `--check`-gated deterministic BUILDER is the wrong dependency direction, and
build_promo_gap.py must not be modified for this. If that guard ever changes there, this comment
is the pointer to bring the same fix here.

TRANSPORT: rate_fetch DECIDES, THIS SCRIPT DOES NOT GUESS. "http" = plain urllib. "browser" =
Playwright. 403s from a plain fetch are common here — verified directly against this repo's own
registry before writing a line of fetch code:

    $ curl -A "<chrome-ua>" https://kkpauto.com/th/carquickcash                    -> 403
    $ curl -A "<chrome-ua>" https://www.kasikornbank.com/.../top-up.aspx           -> 403
    $ curl -A "<chrome-ua>" https://www.carfinn.com/car-loan                       -> 200, 66KB,
                                                                    ZERO occurrences of "ดอกเบี้ย"

carfinn.com is not bot-mitigated — it is a client-rendered React app that assembles the rate
text into the DOM only after the FAQ section hydrates. A plain fetch there returns a shell that
LOOKS successful (200, real bytes) and contains no rate at all, which is the most dangerous kind
of failure because nothing about the HTTP transaction says so. Every other "browser" site is the
opposite problem — Cloudflare/Akamai answering a non-browser client with 403 outright.

The recipe below is the one verified (2026-08-16, against this exact registry) to clear both
failure modes, and every part of it is load-bearing — dropping any one re-opens a 403:
  * a real Chrome user-agent (a Playwright-default UA reads as automation on its own)
  * `ctx.add_init_script(...)` masking `navigator.webdriver` (the single most common bot-check)
  * `channel="chromium"` (a stock Chromium build renders identically to the Chrome branding the
    UA string claims, without needing a bundled Chrome download)
  * `--disable-blink-features=AutomationControlled` (removes a CDP-visible automation flag some
    fingerprinting scripts read directly)
  * for carfinn.com specifically: `wait_until="networkidle"` PLUS a fixed settle wait — the
    hydration is a network-triggered re-render, not something `domcontentloaded` (or even
    `networkidle` alone, which can fire mid-hydration on a slow page) reliably outlasts.
This project's JS-side scraper (pull_rival_facebook.js) uses the same
`navigator.webdriver`-masking + `--disable-blink-features` combination against Facebook, and its
own docstring notes that stock Chromium is fine there because Facebook's wall is a login wall,
not bot mitigation — the opposite is true for KBank/KKP/carfinn, hence the fuller recipe here.
No `patchright` (the stealth-patched Playwright fork this repo's browser-automation SKILL uses
for its own launches) is installed as a Python dependency in this repo — only plain `playwright`
is. The four explicit measures above are what patchright bakes in for exactly this class of site,
applied by hand instead of pulling in a second automation stack for one script.

FAILURE ISOLATION. One unreachable rate_url must never take the other 22 down with it — every
fetch is wrapped per-operator, and a failure is RECORDED (status/error/fetched_via), not raised.
Exit 3 (this repo's RC_ABSENT convention — see build_*.py --check and pull_swarm.py) only if NOT
ONE of the requested operators could be read at all, which is the signal that something is wrong
with the network/browser itself rather than with one site.

CONSTRAINTS (owner's, 2026-08-16): NOT wired into tests/run.sh (this is a network puller, not a
deterministic builder — its output is not byte-reproducible from committed inputs) and NOT given
a GitHub workflow here; scheduling is the owner's to add separately. Does not modify
rival_rate_card.json, build_rate_board.py, or build_promo_gap.py.

  python3 pull_rival_rates.py                     # pull all 23, write rival_rate_observed.json
  python3 pull_rival_rates.py --only SAWAD,TIDLOR  # a subset, by rival_universe.json key
  python3 pull_rival_rates.py --dry-run            # print the plan (url + transport); no network
  python3 -X utf8 pull_rival_rates.py --help       # Thai text in --help needs utf-8 stdout
"""
import argparse
import datetime
import html
import io
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rate_basis as rb  # noqa: E402
from lib.ca_bundle import ssl_context  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data")
UNIVERSE = os.path.join(SRC, "rival_universe.json")
CARD = os.path.join(SRC, "rival_rate_card.json")
OUT = os.path.join(SRC, "rival_rate_observed.json")

RC_ABSENT = 3  # repo-wide convention: "the input this script needs isn't there", not a bug.

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# carfinn.com renders its rate client-side after the FAQ hydrates — see the module docstring's
# curl evidence. `networkidle` alone can still fire mid-hydration on a slow connection, so a
# fixed settle wait is added on top, not instead of it.
SETTLE_HOSTS = ("carfinn.com",)
SETTLE_MS = 3000
NORMAL_SETTLE_MS = 800   # a small settle even for "quick" browser pages — cheap insurance against
                         # a framework that paints its shell before its data fetch resolves.

# ---------------------------------------------------------------------------
# HTML -> TEXT (http-mode only). Browser-mode reads the already-rendered DOM straight off
# page.inner_text("body"), the same call pull_rival_facebook.js uses against Facebook — no
# regex stripping needed there. This is the http-mode equivalent, same shape as pull_pantip.py's
# TAG_RE stripper, extended to turn block-level tags into line breaks so downstream "which LINE
# is this rate on" logic gets real lines instead of one enormous run-on string.
_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.I | re.S)
_BLOCK_RE = re.compile(r"</?(?:br|p|div|li|tr|td|th|h[1-6]|section|article|table|ul|ol)\b[^>]*>",
                        re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(raw):
    s = _SCRIPT_STYLE_RE.sub(" ", raw)
    s = _BLOCK_RE.sub("\n", s)
    s = _TAG_RE.sub(" ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = "\n".join(ln.strip() for ln in s.split("\n"))
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


# ---------------------------------------------------------------------------
# RATE-SHAPED NUMBERS. Same discipline as build_promo_gap.py's NOT_A_RATE guard (see that file's
# module docstring for the ศรีสวัสดิ์ flat-vs-effective trap this pattern also has to survive):
# a percentage only counts as a RATE when it carries the unit word (ต่อเดือน / ต่อปี) — a bare
# "%" is never treated as a rate — AND is not, in its own short context, an LTV/discount/rebate.
# TWO number spellings, each its own alternative (group 1 or group 2 — never both): "X%" is the
# form almost every page on this registry uses, but formal Thai disclosure text (and, as it
# happens, the CURATED CARD's own transcription of car4cash.com — "เริ่มต้นที่ร้อยละ 3.18 ต่อปี")
# writes it word-first as "ร้อยละ X" with no "%" sign at all. Dropping the symbol was the reason
# an earlier version of this script found nothing on that citation even where the number is
# present in the text.
MONTH_RE = re.compile(r"(?:(\d+(?:\.\d+)?)\s*%|ร้อยละ\s*(\d+(?:\.\d+)?))"
                       r"\s*(?:ต่อ\s*เดือน|/\s*เดือน|ต่อเดีอน)")
YEAR_RE = re.compile(r"(?:(\d+(?:\.\d+)?)\s*%|ร้อยละ\s*(\d+(?:\.\d+)?))"
                      r"\s*(?:ต่อ\s*ปี|/\s*ปี|ต่อปี)")
# Identical wordlist to build_promo_gap.py's NOT_A_RATE — kept in lockstep by convention, not by
# import (see the module docstring for why this is reimplemented rather than shared).
NOT_A_RATE = ("วงเงิน", "ของราคาประเมิน", "ส่วนลด", "ลดสูงสุด", "คืนเงิน", "เงินคืน",
              "ลดดอก", "ลดดอกเบี้ย", "ประหยัด", "แคชแบ็ก", "cashback")
CTX_BEFORE, CTX_AFTER = 30, 10   # same clause-sized window build_promo_gap.py uses for the guard

# The basis window. NARROW first (immediately around the number), the single LINE only as a
# fallback — and never wider than that. This was tuned against a real failure this script hit
# on its own first live run: ttbbank.com and scb.co.th both print a FLAT figure immediately
# followed, in the same sentence, by its OWN reducing-balance equivalent in parentheses —
# "อัตราดอกเบี้ยคงที่ 5% ต่อปี (อัตราดอกเบี้ยที่แท้จริง 8.97% ต่อปี)". rate_basis.basis_kind_in()
# is, by design (see its own docstring), "effective wins when a span states both" — correct for
# classifying ONE clause as a whole, but if that whole clause (or a multi-line window around it)
# is handed in for BOTH numbers, the flat 5% gets relabelled effective too, and 5.0 is then
# echoed back as its own "effective_pct_year" — wrong, and exactly the kind of confident-looking
# mistake this script exists to not make. A narrow window anchored on THIS number sees only the
# cue actually attached to it ("คงที่" for the 5%, "ที่แท้จริง" for the 8.97%, each far enough
# from the other's cue not to appear in a ~40/20-char span); the single-line fallback below
# exists only for a number whose own cue isn't that close, and still never reaches into another
# line — a genuinely stacked two-line caption is read as basis=null (safe default) rather than
# guessed, which is the same trade this whole module makes everywhere else.
BASIS_NEAR_BEFORE, BASIS_NEAR_AFTER = 40, 20
MAX_QUOTES_PER_OPERATOR = 25   # a bound against a page that repeats its rate in five banners


def _basis_of(line, start, end):
    near = line[max(0, start - BASIS_NEAR_BEFORE):end + BASIS_NEAR_AFTER]
    return rb.basis_kind_in(near) or rb.basis_kind_in(line)


def quotes_in(text):
    """Every RATE the page states, with basis read from a NARROW window anchored on that exact
    number (falling back to its own line only) and tenor/LTV read from that same line — never
    from another line, and never from the whole page. See BASIS_NEAR_BEFORE/AFTER above for why
    basis in particular must not reach past its own clause. Returns a list of dicts;
    `effective_pct_year` is filled in by the caller (needs the tenor result too)."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    out = []
    for ln in lines:
        for rx, unit in ((MONTH_RE, "pct_per_month"), (YEAR_RE, "pct_per_year")):
            for m in rx.finditer(ln):
                ctx = ln[max(0, m.start() - CTX_BEFORE):m.end() + CTX_AFTER]
                if any(w in ctx for w in NOT_A_RATE):
                    continue
                out.append({
                    "value": float(m.group(1) or m.group(2)),
                    "unit": unit,
                    "quote_th": ln.strip(),
                    "basis": _basis_of(ln, m.start(), m.end()),
                    "tenor_months": rb.tenor_in(ln),
                    "ltv_pct": rb.ltv_in(ln),
                })
    return out


def dedupe_quotes(qs):
    seen, out = set(), []
    for q in qs:
        sig = (q["value"], q["unit"], q["quote_th"])
        if sig in seen:
            continue
        seen.add(sig)
        out.append(q)
    return out


def effective_of(q):
    """The reducing-balance %/yr for one quote, filled in ONLY when the page said enough to
    compute it honestly. `basis` None (not stated) -> None, always. `basis` "flat" with no
    tenor found nearby -> None too: pipeline/rate_basis.flat_to_effective refuses without a
    term, and so does this. Never a guessed tenor, never a guessed basis."""
    if q["basis"] is None:
        return None
    annual = q["value"] * 12.0 if q["unit"] == "pct_per_month" else q["value"]
    if q["basis"] == "effective":
        return round(annual, 2)
    if q["tenor_months"] is None:
        return None
    return rb.flat_to_effective(annual, q["tenor_months"])


# ---------------------------------------------------------------------------
# FETCH
def http_fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "th,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def browser_fetch(ctx, url, timeout_ms):
    settle = any(h in url for h in SETTLE_HOSTS)
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="networkidle" if settle else "domcontentloaded",
                   timeout=timeout_ms)
        page.wait_for_timeout(SETTLE_MS if settle else NORMAL_SETTLE_MS)
        return page.inner_text("body")
    finally:
        page.close()


def launch_browser_context(headful):
    """Isolated so main() can decide, from the PLAN, whether Playwright is even needed —
    an --only run of purely http_fetch operators must work with no browser installed at all."""
    from playwright.sync_api import sync_playwright
    pw_cm = sync_playwright()
    pw = pw_cm.__enter__()
    browser = pw.chromium.launch(
        headless=not headful, channel="chromium",
        args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        user_agent=UA, locale="th-TH", viewport={"width": 1280, "height": 1100},
        ignore_https_errors=True)
    ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return pw_cm, browser, ctx


# ---------------------------------------------------------------------------
# DRIFT vs the curated card. Never writes the card — only compares.
YEAR_TOL = 0.5    # percentage points — the same tolerance rate_basis.py's own PAIRS selftest uses
MONTH_TOL = 0.05  # pct/month; roughly as generous relative to a typical 0.3-1.6%/mo band


def card_reference_ranges(card_entry):
    """Every (lo, hi, unit, label) RANGE the curated card states for one operator — what an
    observed quote gets checked against. Pulls from `quoted`, `quoted_monthly` AND
    `lender_effective` on every variant, since a live page might restate any of the three. A
    field with only one side present (a floor-only "เริ่มต้นที่" or a ceiling-only "ไม่เกิน") is
    carried as a POINT range (lo == hi) — narrower, so a real move away from it still shows.

    RANGE, NOT NEAREST-POINT — this is the fix for the false positives the first live run threw:
    a card that already publishes "20.75% - 24%" and a live page that says 22.32% is not drift,
    it is a value INSIDE the disclosed band. Comparing only to the nearest single endpoint (the
    first version of this function) flagged that as a false "+1.57pp" move. A value is drift
    only when it falls outside EVERY range the card publishes for that unit.
    """
    ranges = []
    for v in card_entry.get("variants") or []:
        label = v.get("variant") or "?"
        q = v.get("quoted") or {}
        q_unit = "pct_per_month" if q.get("unit") == "pct_per_month" else "pct_per_year"
        lo, hi = q.get("lo"), q.get("hi")
        if lo is not None or hi is not None:
            ranges.append((lo if lo is not None else hi, hi if hi is not None else lo,
                           q_unit, "%s.quoted" % label))
        qm = v.get("quoted_monthly") or {}
        lo, hi = qm.get("lo"), qm.get("hi")
        if lo is not None or hi is not None:
            ranges.append((lo if lo is not None else hi, hi if hi is not None else lo,
                           "pct_per_month", "%s.quoted_monthly" % label))
        le = v.get("lender_effective") or {}
        lo, hi = le.get("lo"), le.get("hi")
        if lo is not None or hi is not None:
            ranges.append((lo if lo is not None else hi, hi if hi is not None else lo,
                           "pct_per_year", "%s.lender_effective" % label))
    return ranges


def diff_against_card(quotes, card_entry):
    if card_entry is None:
        return {"in_card": False, "lines": []}
    ranges = card_reference_ranges(card_entry)
    lines = []
    for q in quotes:
        tol = MONTH_TOL if q["unit"] == "pct_per_month" else YEAR_TOL
        same_unit = [r for r in ranges if r[2] == q["unit"]]
        if not same_unit:
            lines.append({"observed": q["value"], "unit": q["unit"], "card_range": None,
                          "card_field": None, "delta": None, "drift": True,
                          "note": "card has no figure in this unit for this operator"})
            continue
        # inside ANY published range (with tolerance padding each side) -> not drift, full stop.
        inside = [r for r in same_unit if r[0] - tol <= q["value"] <= r[1] + tol]
        if inside:
            r = inside[0]
            lines.append({"observed": q["value"], "unit": q["unit"],
                          "card_range": [r[0], r[1]], "card_field": r[3],
                          "delta": 0.0, "drift": False})
            continue
        # outside every range -> report the NEAREST one, by distance to its closer edge.
        def edge_dist(r):
            return r[0] - q["value"] if q["value"] < r[0] else q["value"] - r[1]
        nearest = min(same_unit, key=edge_dist)
        delta = round(edge_dist(nearest), 2)
        lines.append({"observed": q["value"], "unit": q["unit"],
                      "card_range": [nearest[0], nearest[1]], "card_field": nearest[3],
                      "delta": delta, "drift": True})
    return {"in_card": bool(card_entry.get("variants")), "lines": lines}


# ---------------------------------------------------------------------------
def load_json(path, default=None):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def build_plan(operators, only):
    keys = None
    if only:
        keys = set(k.strip().upper() for k in only.split(",") if k.strip())
    plan, missing_url, skipped = [], [], []
    for o in operators:
        key = o.get("key")
        if not key:
            continue
        if keys is not None and key not in keys:
            continue
        url = o.get("rate_url")
        mode = o.get("rate_fetch") or "http"
        if not url:
            missing_url.append(key)
            continue
        plan.append({"key": key, "name_th": o.get("name_th"), "url": url, "mode": mode})
    if keys is not None:
        found = {p["key"] for p in plan} | set(missing_url)
        skipped = sorted(keys - found)
    return plan, missing_url, skipped


def print_plan(plan, missing_url, skipped):
    print("PLAN — %d operator(s), no network touched:" % len(plan))
    w = max([len(p["key"]) for p in plan] + [3])
    for p in plan:
        print("  %-*s  %-8s %s   (%s)" % (w, p["key"], p["mode"], p["url"], p["name_th"] or ""))
    n_http = sum(1 for p in plan if p["mode"] == "http")
    n_browser = len(plan) - n_http
    print("  -> %d via http, %d via browser" % (n_http, n_browser))
    if missing_url:
        print("%d operator(s) have no rate_url in rival_universe.json, skipped: %s"
              % (len(missing_url), ", ".join(missing_url)))
    if skipped:
        print("%d requested key(s) not found in rival_universe.json: %s"
              % (len(skipped), ", ".join(skipped)))


def print_report(results, card_by):
    w = max([len(r["key"]) for r in results] + [3])
    print("\n%-*s  %-13s %-8s %-6s %s" % (w, "KEY", "STATUS", "VIA", "QUOTES", "NOTE"))
    for r in results:
        note = (r.get("error") or "")[:70]
        print("  %-*s  %-13s %-8s %-6d %s"
              % (w, r["key"], r["status"], r["fetched_via"], len(r["quotes"]), note))

    print("\nDRIFT vs source-data/rival_rate_card.json (report only — a human decides, this "
          "script never writes that file):")
    any_drift = False
    quote_by_val = {}
    for r in results:
        for q in r["quotes"]:
            quote_by_val.setdefault((r["key"], q["value"], q["unit"]), q["quote_th"])
    for r in results:
        d = r.get("drift") or {}
        if not d.get("in_card"):
            continue
        name = (card_by.get(r["key"]) or {}).get("name_th") or r["name_th"] or r["key"]
        # One row per DISTINCT finding, not per quote. A page that says "0.27% ต่อเดือน" in three
        # places yields three drift lines that all resolve to the same value, the same band and —
        # because quote_by_val collapses on (key, value, unit) — the same quote, so the report
        # printed the identical row three times. Observed on the first scheduled run (PR #477):
        # TTB_CYC's 0.27% appeared 3×, which pads the list a human is meant to read and makes the
        # feed look noisier than the market actually is. Dedupe on what is actually printed.
        # The JSON payload still carries every line — this is a display-layer collapse only, so
        # nothing about the underlying record is lost.
        seen_rows = set()
        for line in d["lines"]:
            if not line["drift"]:
                continue
            row_id = (line["observed"], line["unit"],
                      tuple(line["card_range"]) if line["card_range"] else None,
                      line.get("note"), line.get("card_field"))
            if row_id in seen_rows:
                continue
            seen_rows.add(row_id)
            any_drift = True
            u = "ต่อเดือน" if line["unit"] == "pct_per_month" else "ต่อปี"
            q_th = quote_by_val.get((r["key"], line["observed"], line["unit"]), "")[:90]
            if line["card_range"] is None:
                print("  DRIFT  %s (%s): page now says %g%% %s — %s\n           quote: %s"
                      % (r["key"], name, line["observed"], u, line["note"], q_th))
            else:
                lo, hi = line["card_range"]
                band = ("%g%%" % lo) if lo == hi else ("%g-%g%%" % (lo, hi))
                print("  DRIFT  %s (%s): page now says %g%% %s, the card says %s (%s) — "
                      "%+.2fpp outside that band\n           quote: %s"
                      % (r["key"], name, line["observed"], u, band, line["card_field"],
                         line["delta"], q_th))
    if not any_drift:
        print("  none — every rate this run could read lands within tolerance of a band "
              "already on the card (or the operator carries no observable quote this run)")


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=None,
                     help="comma-separated rival_universe.json keys, e.g. SAWAD,TIDLOR "
                          "(default: all 23)")
    ap.add_argument("--dry-run", action="store_true",
                     help="print the plan (url + transport per operator) and touch no network")
    ap.add_argument("--timeout", type=int, default=45, help="per-page timeout, seconds (default 45)")
    ap.add_argument("--headful", action="store_true",
                     help="run the browser with a visible window (debugging only)")
    args = ap.parse_args()

    uni = load_json(UNIVERSE)
    if not uni or not uni.get("operators"):
        sys.exit("pull_rival_rates.py: cannot read operators from %s" % UNIVERSE)

    plan, missing_url, skipped = build_plan(uni["operators"], args.only)

    if args.dry_run:
        print_plan(plan, missing_url, skipped)
        return 0

    if not plan:
        print("pull_rival_rates.py: nothing to pull (empty --only selection, or no operator in "
              "rival_universe.json has a rate_url)")
        return RC_ABSENT

    card = load_json(CARD, {}) or {}
    card_by = {o["key"]: o for o in (card.get("operators") or []) if o.get("key")}

    need_browser = any(p["mode"] == "browser" for p in plan)
    pw_cm = browser = ctx = None
    if need_browser:
        try:
            pw_cm, browser, ctx = launch_browser_context(args.headful)
        except ImportError:
            sys.exit("pull_rival_rates.py: this plan needs Playwright (rate_fetch=browser) — "
                      "pip install playwright && python -m playwright install chromium")
        except Exception as e:
            sys.exit("pull_rival_rates.py: could not launch chromium (%s) — "
                      "try: python -m playwright install chromium" % e)

    today = datetime.date.today().isoformat()
    results, n_read, n_error = [], 0, 0
    try:
        for p in plan:
            rec = {"key": p["key"], "name_th": p["name_th"], "rate_url": p["url"],
                   "fetched_via": p["mode"], "fetched_at": today,
                   "status": None, "error": None, "n_chars": None, "quotes": []}
            try:
                if p["mode"] == "browser":
                    text = browser_fetch(ctx, p["url"], args.timeout * 1000)
                else:
                    text = html_to_text(http_fetch(p["url"], args.timeout))
            except Exception as e:
                rec["status"], rec["error"] = "error", str(e)[:200]
                n_error += 1
                results.append(rec)
                print("  [%s] FETCH FAILED (%s): %s" % (p["key"], p["mode"], rec["error"]))
                continue

            n_read += 1
            rec["n_chars"] = len(text)
            qs = dedupe_quotes(quotes_in(text))
            for q in qs:
                q["effective_pct_year"] = effective_of(q)
            qs.sort(key=lambda q: (q["unit"], q["value"]))
            truncated = len(qs) > MAX_QUOTES_PER_OPERATOR
            rec["quotes"] = qs[:MAX_QUOTES_PER_OPERATOR]
            rec["quotes_truncated"] = truncated
            rec["status"] = "ok" if qs else "no_rate_found"
            rec["drift"] = diff_against_card(rec["quotes"], card_by.get(p["key"]))
            results.append(rec)
            print("  [%s] %-13s via=%-8s quotes=%d%s"
                  % (p["key"], rec["status"], p["mode"], len(rec["quotes"]),
                     " (truncated)" if truncated else ""))
    finally:
        if ctx is not None:
            ctx.close()
        if browser is not None:
            browser.close()
        if pw_cm is not None:
            pw_cm.__exit__(None, None, None)

    for r in results:
        r.setdefault("drift", {"in_card": False, "lines": []})

    n_no_rate = sum(1 for r in results if r["status"] == "no_rate_found")
    n_with_drift = sum(1 for r in results
                        if r["drift"]["in_card"] and any(l["drift"] for l in r["drift"]["lines"]))

    payload = {
        "meta": {
            "title": "Rival rate OBSERVATION — live re-read of each operator's pinned rate_url",
            "generated_by": "pipeline/pull_rival_rates.py",
            "label": "MEASURED — the verbatim rate text found on each operator's own rate_url "
                     "this run, PLUS what pipeline/rate_basis.py could read off the page about "
                     "its basis/tenor/LTV. `basis` is null (and `effective_pct_year` is null) "
                     "wherever the page does not itself state which convention it is quoting — "
                     "never inferred. This file is NOT the rate board's input and NEVER "
                     "overwrites source-data/rival_rate_card.json, which stays hand-curated; "
                     "`drift` on each operator is this script's own comparison against that "
                     "card, for a human to act on.",
            "why": "rival_rate_card.json only moved when a human edited it by hand. This script "
                   "is the scheduled eyes that re-visit every rate_url and say what changed, so "
                   "the card (and everything measured against it, incl. build_promo_gap.py's "
                   "undercut check) does not go stale without anyone noticing.",
            "scheduling": "Deliberately absent from tests/run.sh — this is a network puller, not "
                          "a deterministic --check build, so it has nothing byte-exact to gate. "
                          "It IS scheduled: .github/workflows/data-rival-rates.yml runs it weekly "
                          "(cron 10 23 * * 0 — 06:10 Bangkok Monday) and opens a PR carrying the "
                          "drift report below. Registered in pull_swarm.py as `rival_rates` "
                          "(needs_browser), which is why it needs that dedicated workflow: "
                          "data-swarm.yml runs --skip-browser and would never pick it up.",
            "pulled_at": today,
            "n_operators_in_plan": len(plan),
            "n_read": n_read, "n_error": n_error, "n_no_rate_found": n_no_rate,
            "n_with_drift_vs_card": n_with_drift,
            # The one-line headline, written HERE rather than reassembled by the workflow.
            # data-rival-rates.yml used to build this sentence itself from `n_ok`/`n_operators`/
            # `n_with_rate` — three key names this file has never emitted — so the first scheduled
            # run (PR #477) opened with a title reading "? of ? pages read, ? with a parseable
            # rate". Nothing errored: .get(k, '?') did exactly what it was told. A consumer that
            # re-derives a summary from key names it does not own will drift from them silently,
            # so the producer owns the sentence and the workflow prints one field.
            "summary": "%d of %d pages read, %d with a parseable rate, %d showing drift vs the card"
                       % (n_read, len(plan), n_read - n_no_rate, n_with_drift),
            "rate_url_missing": missing_url,
            "requested_keys_not_found": skipped,
            "drift_tolerance": {"pct_per_year_pp": YEAR_TOL, "pct_per_month_pp": MONTH_TOL},
        },
        "operators": results,
    }
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")

    print_report(results, card_by)
    print("\nwrote %s — %d/%d operator(s) read (%d error, %d no rate found), %d drift flag(s) "
          "vs the curated card" % (OUT, n_read, len(plan), n_error, n_no_rate, n_with_drift))

    if n_read == 0:
        print("pull_rival_rates.py: NOTHING could be read this run.")
        return RC_ABSENT
    return 0


if __name__ == "__main__":
    sys.exit(main())
