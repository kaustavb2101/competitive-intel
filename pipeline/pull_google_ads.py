#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_google_ads.py — rival ONLINE ADS + their MESSAGE, from Google's Ads Transparency Center.

WHAT THIS IS (objective #2). Google publishes, for every advertiser, each creative it has run
with the first and last date it was shown. Unlike Meta's Ad Library it DOES cover Thai
commercial advertisers (Meta's credit-ad slice is rejected as "invalid" for TH — see
`spike_meta_ads.py` for that dead end). So this answers both halves of the question:
  * how hard each rival is pushing paid acquisition (volume, live-now, cadence, run length)
  * WHAT THEY ARE SAYING — the actual ad copy, including the rates they advertise

Coverage is the WHOLE field, not the big three: the advertiser list is driven by
`source-data/rival_universe.json` (17 operators — the non-bank title lenders AND the
bank-backed entrants Somwang / Ngern Hai Jai / Car4Cash / KTC พี่เบิ้ม / GSB / ttb / KKP).

HOW THE MESSAGE IS RECOVERED. Google returns the creative payload in one of two shapes:
  * a rendered display ad -> a googleusercontent render URL. Fetching it yields the ad's real
    text. Recorded as text_src="render" — MEASURED, it is Google's own copy of the creative.
  * an image banner -> just an <img> archive URL; the words are pixels. With --ocr we fetch the
    image and run Thai tesseract over it. Recorded as text_src="ocr" — ESTIMATED, because a
    transcription can misread. The two are never blended, so the UI can label them apart.
Creative text hosts (googleusercontent / googlesyndication) are separate from the RPC host and
are not subject to its rate limit, so text fetching is paced independently.

  out: source-data/google_ads_raw.json   (accumulating: per-creative first/last seen + text)

  python3 pull_google_ads.py --discover           # vet advertiser accounts, writes nothing
  python3 pull_google_ads.py                      # pull creatives + render text
  python3 pull_google_ads.py --ocr                # ...also OCR the image banners (slow)
  python3 pull_google_ads.py --brand TIDLOR       # one operator

RATE LIMITS ARE REAL: the RPC host returns HTTP 429 after a burst and the cooldown is applied
per IP — once tripped, even a plain page GET is refused. Every call goes through `rpc()`, which
warms a cookie jar, backs off exponentially, and RAISES rather than returning a silent empty
list. A throttled zero must never be mistaken for "this brand runs no ads"; that mistake was
made once during the spike, and the guard exists so it cannot recur.
"""
import argparse
import datetime
import http.cookiejar
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "google_ads_raw.json")
UNIVERSE = os.path.join(ROOT, "source-data", "rival_universe.json")

BASE = "https://adstransparency.google.com/anji/_/rpc/"
REGION_TH = 2764                      # Google's internal region id for Thailand
PAGE = 40                             # what the UI itself requests

# Seconds between RPC calls. Google rate-limits this endpoint at the IP level and, once
# tripped, the cooldown is long. Pace generously: a full pull is a few hundred calls and there
# is no deadline. Raise --sleep if you have been throttled.
POLITE = 4.0
TEXT_POLITE = 0.6                     # creative-text hosts: different host, much looser limit

# Google files advertisers by LEGAL ENTITY, and Thai brand names double as common personal
# names (a search for ศรีสวัสดิ์ returns private individuals; "AutoX" returns two unrelated
# Italian firms). So accounts are hand-curated and ID-pinned, never name-matched at run time.
# Re-vet with --discover; `note` records why each id is accepted.
ADVERTISERS = {
    "TIDLOR": [
        ("AR00343519610412204033", "บริษัท เงินติดล้อ จำกัด (มหาชน) — Tidlor PCL, acct 1"),
        ("AR12032973375124013057", "บริษัท เงินติดล้อ จำกัด (มหาชน) — Tidlor PCL, acct 2"),
    ],
    "SAWAD": [
        ("AR05287991188266156033", "Srisawad Power 2014 Co.,Ltd — SAWAD group operating co"),
        # Same operator, adjacent product: the group's home/land-title arm. Pinned under SAWAD
        # rather than as a new key because the census counts one Srisawad. The legal name is
        # unambiguously Srisawad's own entity — unlike the private individuals and unrelated
        # firms a ศรีสวัสดิ์ search returns, ศรีสวัสดิ์ being a common Thai surname.
        ("AR18420769142295494657", "บริษัท ศรีสวัสดิ์ โฮม จำกัด — SAWAD group home/land lender"),
    ],
    "MTC": [
        ("AR03790918283557863425", "Muangthai Capital Public Company Limited — MTC"),
    ],
    "NGERNHAIJAI": [
        ("AR02829134420034715649", "บริษัท เงินให้ใจ จำกัด — KBank-backed lender, acct 1"),
        ("AR14376384815463137281", "บริษัท เงินให้ใจ จำกัด — KBank-backed lender, acct 2"),
        # No corporate marker in the name, so --discover files it under "individual, skip".
        # Vetted 2026-08-16 by reading its creatives: 8 of 8 are เงินให้ใจ's own title-loan
        # copy ("สินเชื่อรถจากเงินให้ใจ … สมัครง่ายผ่านธนาคารกสิกรไทย"), naming the KBank
        # parent. A private individual does not advertise a bank's lending product.
        ("AR11022866559675662337", "เงินให้ใจ — same lender, acct 3 (41 ads; brand-name "
                                   "account with no corporate suffix, copy-vetted)"),
    ],
    "GSB_MONEYDD": [
        ("AR16341765122877816833", "บริษัท เงินดีดี จำกัด — GSB's MoneyDD lending entity"),
    ],
    # TURBO advertises through its INSURANCE-BROKER entity, which is why a name search files it
    # as "individual, skip" and why this operator read as having no paid Google presence at all
    # until 2026-08-16. It has 121 creatives. Vetted by reading them: 7 of 7 sampled are
    # จำนำทะเบียน copy ("จำนำเล่มทะเบียนรถยนต์ที่เงินเทอร์โบ ไม่ต้องมีคนค้ำ … ไม่ต้องโอนเล่ม"),
    # i.e. the group's LENDING marketing, merely billed to the broker company. Contrast KKP
    # below, whose only account genuinely sells a different product.
    "TURBO": [
        ("AR13508192232099807233", "NGERNTURBO INSURANCE BROKER COMPANY LIMITED — เงินเทอร์โบ "
                                   "group; copy-vetted 2026-08-16 as title-loan advertising"),
    ],
    "WSOL_CARFINN": [
        ("AR11374489330266406913", "บริษัท คาร์ฟินน์ อินเตอร์ กรุ๊ป จำกัด — CarFinn, the online "
                                   "broker already in the census"),
    ],
}

# Advertiser accounts that a name search surfaces but that we deliberately DO NOT pull, with
# the reason. Counting these as title-loan competition would misattribute someone else's
# marketing to our market.
EXCLUDED = {
    "KKP":         ("AR15900838128093495297", "KKP Dime Securities Company Limited — the "
                                              "group's INVESTMENT app, not KKP รถเรียกเงิน. "
                                              "Its 200-300 ads sell securities, not title loans."),
    "KTC_PBERM":   ("AR12468876374863511553", "KTC Business Consultants Ltd — a consulting "
                                              "entity, not the KTC พี่เบิ้ม title-loan product; "
                                              "2 ads total."),
    "GSB_MONEYDD2": ("AR13594408615325728769", "บริษัท นับดีมีเงิน จำกัด — surfaced next to "
                                               "เงินดีดี but is a separate legal entity we "
                                               "could not tie to the GSB product; left out "
                                               "rather than guessed."),
    # --- Thai brand-name collisions, recorded so nobody re-adds them next quarter ------------
    # These are the accounts a name search surfaces that belong to DIFFERENT COMPANIES. The
    # เมืองไทย one is the dangerous one: 700-800 creatives, more than every title lender we
    # track combined, and folding it in would have made MTC look like the dominant advertiser
    # in the market on the strength of a life insurer's marketing.
    "MTC_LIFE":     ("AR13571366837337194497", "บริษัท เมืองไทยประกันชีวิต จำกัด (มหาชน) — Muang "
                                               "Thai LIFE INSURANCE, an unrelated company. "
                                               "700-800 ads. 'เมืองไทย' is a generic name."),
    "MTC_TRAVEL":   ("AR00610429528388403201", "บริษัท เมืองไทย ทราเวล จำกัด — a travel agency."),
    "MTC_MEDIA":    ("AR05428757573161451521", "MTC Media Ltd — unrelated; the MTC initialism "
                                               "also returns MTCGAME, MTCH AG and a German "
                                               "electronics firm."),
    "MTC_MITR":     ("AR15716447253566586881", "บริษัท มิตรเมืองไทย จำกัด — unrelated."),
    "SOMWANG_LERT": ("AR10449566370726150145", "บริษัท สมหวังเลิศมงคล จำกัด — 93 ads, but TISCO's "
                                               "สมหวัง operates as บริษัท ไฮเวย์ จำกัด. สมหวัง is "
                                               "an ordinary Thai word ('wish fulfilled'); the "
                                               "same search also returns a flower shop."),
    "CAR4CASH_SUMO": ("AR17925099482198835201", "ซูโม่คาร์ จำกัด — a car dealer, not Krungsri's "
                                                "Car4Cash. The คาร์ token matches garages and "
                                                "rental firms across the whole country."),
}

# Operators checked with --discover and found to have NO advertiser account in Thailand. A
# lender with no paid Google presence is a real competitive finding, so it is carried into the
# output and rendered — but ONLY add a key here after a clean, non-throttled --discover run,
# because a 429 also returns zero suggestions. The run behind this list logged ZERO throttle
# errors across all 17 operators (2026-07-30), so these empties are real.
# TURBO left this list on 2026-08-16: it DOES advertise, through its insurance-broker entity,
# and a --discover run cannot see that because the entity name carries no lending token. A
# "no account" finding is only as good as the name we searched under — worth remembering before
# reading the remaining eight as proof that those operators buy no paid search at all.
NO_ACCOUNT = ["AMANAH", "AUTOX", "CAR4CASH", "GSB_MEETEE", "HENG", "MICRO", "SAK",
              "SOMWANG", "TTB_CYC"]

# A suggestion is only a company if the name carries a corporate marker. Filters out the
# private individuals that Thai name collisions surface.
CORP = ("จำกัด", "มหาชน", "Co.", "Co,", "Ltd", "LTD", "Limited", "PCL", "Public", "บริษัท")


class Throttled(RuntimeError):
    """Raised when the endpoint keeps returning 429 — never degrade this to an empty result."""


# A cold, cookie-less client gets throttled hard while a browser sails through, because the
# transparency page sets consent/session cookies on first load and the RPC layer rate-limits
# unrecognised callers much more aggressively. So: one shared opener with a cookie jar, warmed
# by a single GET of the page the RPCs belong to. This is the handshake any browser performs;
# it authenticates us as nobody and involves no credential.
_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_JAR))
_WARM = [False]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")


def warm():
    if _WARM[0]:
        return
    try:
        _OPENER.open(urllib.request.Request(
            "https://adstransparency.google.com/?region=TH",
            headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
                     "Accept-Language": "en-US,en;q=0.9,th;q=0.8"}), timeout=60).read(1)
    except Exception as e:                       # a failed warm-up is noted, not fatal
        sys.stderr.write("  (warm-up failed: %s)\n" % str(e)[:80])
    _WARM[0] = True
    time.sleep(1.0)


def rpc(name, payload, tries=5):
    warm()
    body = "f.req=" + urllib.parse.quote(json.dumps(payload, separators=(",", ":")))
    delay = 15.0
    for attempt in range(tries):
        req = urllib.request.Request(
            BASE + name + "?authuser=", data=body.encode("utf-8"), method="POST",
            headers={"User-Agent": UA, "Accept": "*/*",
                     "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
                     "Content-Type": "application/x-www-form-urlencoded",
                     "X-Same-Domain": "1",
                     "Origin": "https://adstransparency.google.com",
                     "Referer": "https://adstransparency.google.com/?region=TH"})
        try:
            with _OPENER.open(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < tries - 1:
                sys.stderr.write("  ... HTTP %s, backing off %.0fs\n" % (e.code, delay))
                time.sleep(delay)
                delay *= 2
                _WARM[0] = False                 # re-handshake before the next attempt
                warm()
                continue
            if e.code in (429, 503):
                raise Throttled("%s still %s after %d tries" % (name, e.code, tries))
            raise RuntimeError("%s HTTP %s: %s"
                               % (name, e.code, e.read(200).decode("utf-8", "ignore")))
    raise Throttled(name)


# ── creative payload ───────────────────────────────────────────────────────────────────────
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"')
# Thai runs, plus latin/number fragments long enough to be copy rather than markup noise.
COPY_RE = re.compile(r"[฀-๿][฀-๿\s0-9%.,!–\-]{3,}")


def payload_of(creative):
    """(kind, render_url, image_url) read off the creative rather than a guessed enum.

    Google's numeric format code is undocumented, so classify by what the creative carries:
    a googleusercontent render (its text is fetchable) or an <img> archive banner (its words
    are pixels). An unrecognised shape stays "other" — never bucketed into a known kind.
    """
    node = creative.get("3") or {}
    render = ((node.get("1") or {}) if isinstance(node.get("1"), dict) else {}).get("4")
    blob = json.dumps(node, ensure_ascii=False)
    img = IMG_RE.search(blob)
    if render:
        return "render", render, None
    if img:
        return "image", None, img.group(1).replace("\\/", "/")
    return "other", None, None


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://adstransparency.google.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_copy(raw):
    """Distinct ad-copy lines, order preserved, boilerplate dropped."""
    out, seen = [], set()
    for m in COPY_RE.findall(raw):
        t = " ".join(m.split())
        if len(t) < 4 or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def render_text(url):
    """MEASURED: the ad's own copy, from Google's rendered creative."""
    try:
        return clean_copy(fetch(url).decode("utf-8", "ignore"))
    except Exception as e:
        sys.stderr.write("    (render text failed: %s)\n" % str(e)[:70])
        return []


def ocr_text(url):
    """ESTIMATED: Thai tesseract over an image banner. A transcription can misread."""
    try:
        import PIL.Image
        import pytesseract
    except ImportError:
        return []
    try:
        img = PIL.Image.open(io.BytesIO(fetch(url)))
        txt = pytesseract.image_to_string(img, lang="tha+eng")
        return clean_copy(txt)
    except Exception as e:
        sys.stderr.write("    (ocr failed: %s)\n" % str(e)[:70])
        return []


def day(node):
    """{'1': unix_seconds, '2': nanos} -> 'YYYY-MM-DD' (UTC), or None."""
    if not isinstance(node, dict) or not node.get("1"):
        return None
    return datetime.datetime.fromtimestamp(
        int(node["1"]), datetime.timezone.utc).strftime("%Y-%m-%d")


# ── the operator universe ──────────────────────────────────────────────────────────────────
def universe():
    """Every material operator, from the file the Competition tab already uses."""
    if not os.path.exists(UNIVERSE):
        return []
    return (json.load(io.open(UNIVERSE, encoding="utf-8")).get("operators") or [])


def discover_queries():
    """{key: (label, [search terms])} across the whole field, not just the big three."""
    q = {}
    for o in universe():
        key = o.get("key")
        if not key:
            continue
        terms = []
        for t in (o.get("name_th"), o.get("name_en"), o.get("app_brand")):
            if t and t not in terms:
                terms.append(t)
        # the shortest distinctive Thai token often matches where the full legal name will not
        th = o.get("name_th") or ""
        head = th.split()[0] if th.split() else ""
        if head and head not in terms and len(head) >= 3:
            terms.append(head)
        q[key] = (o.get("name_en") or key, terms)
    return q


def suggest(query):
    d = rpc("SearchService/SearchSuggestions",
            {"1": query, "2": 10, "3": 10, "4": [REGION_TH], "5": {"1": 1}})
    out = []
    for row in (d.get("1") or []):
        a = row.get("1") or {}
        band = (a.get("4") or {}).get("2") or {}
        out.append({"name": a.get("1"), "id": a.get("2"), "cc": a.get("3"),
                    "ads_lo": band.get("1"), "ads_hi": band.get("2")})
    return out


def creatives(advertiser_id):
    got, token, page = [], None, 0
    while True:
        payload = {"2": PAGE,
                   "3": {"8": [REGION_TH], "12": {"1": "", "2": True},
                         "13": {"1": [advertiser_id]}},
                   "7": {"1": 1, "2": 0, "3": REGION_TH}}
        if token:
            payload["4"] = token
        d = rpc("SearchService/SearchCreatives", payload)
        rows = d.get("1") or []
        got.extend(rows)
        page += 1
        token = d.get("2")
        sys.stderr.write("    page %d: +%d (total %d)\n" % (page, len(rows), len(got)))
        if not token or not rows:
            break
        time.sleep(POLITE)
    return got


def do_discover():
    qs = discover_queries()
    print("Vetting advertiser accounts in Thailand (region %d) across %d operators.\n"
          % (REGION_TH, len(qs)))
    print("%-12s %-44s %-24s %s" % ("OPERATOR", "ADVERTISER", "ID", "ADS"))
    print("-" * 100)
    empty = []
    for key in sorted(qs):
        label, terms = qs[key]
        seen, any_corp = set(), False
        for t in terms:
            for s in suggest(t):
                if not s["id"] or s["id"] in seen:
                    continue
                seen.add(s["id"])
                is_corp = any(m in (s["name"] or "") for m in CORP)
                any_corp = any_corp or is_corp
                print("%-12s %-44s %-24s %s-%s%s"
                      % (key, (s["name"] or "")[:42], s["id"], s["ads_lo"], s["ads_hi"],
                         "" if is_corp else "   <- individual, skip"))
            time.sleep(POLITE)
        if not any_corp:
            empty.append(key)
            print("%-12s %s" % (key, "no corporate advertiser account (checked %d spelling(s))"
                                % len(terms)))
    print("\nNO_ACCOUNT candidates (clean run, not throttled): %s" % ", ".join(empty))
    print("Pin accepted ids into ADVERTISERS[] and empties into NO_ACCOUNT[] before pulling.")


def from_browser(path, ocr, no_text, names, today, prev):
    """Ingest a creative dump captured in a real browser session on the same page.

    Google's RPC layer rate-limits a scripted client far harder than a browser tab: once
    tripped it refuses even a plain page GET from this IP, while the page itself keeps
    loading. Rather than pretend to be a browser more convincingly, the honest fallback is to
    let the actual browser make the calls and hand the JSON here. From a fresh IP (CI) the
    normal path works and this is unnecessary — the two produce the same records.
    """
    dump = json.load(io.open(path, encoding="utf-8"))
    rows = dump.get("creatives") or []
    store, brands = dict(prev), {}
    for r in rows:
        cid = r.get("cid")
        if not cid:
            continue
        old = prev.get(cid) or {}
        rec = {"brand": r.get("brand"), "advertiser_id": r.get("aid"),
               "advertiser_name": r.get("name"), "format": r.get("fmt"),
               "kind": "render" if r.get("render") else "image" if r.get("img") else "other",
               "image_url": r.get("img"),
               "first_shown": day({"1": r["first"]} if r.get("first") else None),
               "last_shown": day({"1": r["last"]} if r.get("last") else None),
               "first_pull": old.get("first_pull", today), "last_pull": today,
               "text": old.get("text") or [], "text_src": old.get("text_src")}
        if not rec["text"] and not no_text:
            if r.get("render"):
                rec["text"] = render_text(r["render"])
                rec["text_src"] = "render" if rec["text"] else None
            elif r.get("img") and ocr:
                rec["text"] = ocr_text(r["img"])
                rec["text_src"] = "ocr" if rec["text"] else None
            if rec["text"]:
                time.sleep(TEXT_POLITE)
        store[cid] = rec
    for key in sorted({r["brand"] for r in store.values() if r.get("brand")}):
        mine = [r for r in store.values() if r["brand"] == key]
        op = names.get(key) or {}
        brands[key] = {"key": key, "name_en": op.get("name_en") or key,
                       "name_th": op.get("name_th"), "tier": op.get("tier"),
                       "accounts": [{"id": i, "note": n}
                                    for i, n in ADVERTISERS.get(key, [])],
                       "n": len(mine),
                       "n_with_text": sum(1 for r in mine if r.get("text"))}
        print("  %-12s %4d creatives (%d with copy)" % (key, len(mine),
                                                        brands[key]["n_with_text"]))
    return store, brands


def main():
    global POLITE
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-browser", metavar="PATH",
                    help="ingest a creative dump captured in a browser session (see docstring)")
    ap.add_argument("--discover", action="store_true", help="vet accounts; writes nothing")
    ap.add_argument("--brand", help="pull a single operator key (e.g. TIDLOR)")
    ap.add_argument("--sleep", type=float, default=POLITE,
                    help="seconds between RPC calls (default %.1f; raise if throttled)" % POLITE)
    ap.add_argument("--ocr", action="store_true",
                    help="also OCR image banners (slow; text_src=ocr is ESTIMATED)")
    ap.add_argument("--no-text", action="store_true", help="skip creative-text fetching")
    a = ap.parse_args()
    POLITE = a.sleep

    if a.discover:
        do_discover()
        return 0

    prev = {}
    if os.path.exists(OUT):
        prev = (json.load(io.open(OUT, encoding="utf-8")) or {}).get("creatives") or {}

    names = {o.get("key"): o for o in universe()}
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    if a.from_browser:
        store, brands = from_browser(a.from_browser, a.ocr, a.no_text, names, today, prev)
        return write(store, brands, today)

    store, brands = dict(prev), {}
    if a.brand:
        # A single-operator run must not evict the operators it did not visit. The creatives
        # store is merged into `prev` already, but `brands` carries each operator's name, tier
        # and account list — rebuilt from scratch it would leave the layer with ONE brand and
        # every other operator's rows nameless and tierless downstream. Seed from the previous
        # file and let this run overwrite only its own key. A FULL run still rebuilds the map
        # from ADVERTISERS, so removing an operator there still removes it from the output.
        brands = dict((json.load(io.open(OUT, encoding="utf-8")) or {}).get("brands") or {}
                      if os.path.exists(OUT) else {})
    for key, accts in ADVERTISERS.items():
        if a.brand and key.lower() != a.brand.lower():
            continue
        op = names.get(key) or {}
        n_new = 0
        brands[key] = {"key": key,
                       "name_en": op.get("name_en") or key,
                       "name_th": op.get("name_th"),
                       "tier": op.get("tier"),
                       "accounts": [{"id": i, "note": n} for i, n in accts]}
        for aid, note in accts:
            sys.stderr.write("  %s / %s\n" % (key, aid))
            for c in creatives(aid):
                cid = c.get("2")
                if not cid:
                    continue
                old = prev.get(cid) or {}
                kind, render, img = payload_of(c)
                rec = {"brand": key, "advertiser_id": c.get("1"),
                       "advertiser_name": c.get("12"),
                       "format": c.get("4"), "kind": kind,
                       "image_url": img,
                       "first_shown": day(c.get("6")), "last_shown": day(c.get("7")),
                       "first_pull": old.get("first_pull", today), "last_pull": today}
                # copy is immutable once captured — re-fetch only what we do not yet have
                rec["text"] = old.get("text") or []
                rec["text_src"] = old.get("text_src")
                if not rec["text"] and not a.no_text:
                    if render:
                        rec["text"] = render_text(render)
                        rec["text_src"] = "render" if rec["text"] else None
                    elif img and a.ocr:
                        rec["text"] = ocr_text(img)
                        rec["text_src"] = "ocr" if rec["text"] else None
                    if rec["text"]:
                        time.sleep(TEXT_POLITE)
                if not old:
                    n_new += 1
                store[cid] = rec
            time.sleep(POLITE)
        rows = [r for r in store.values() if r["brand"] == key]
        brands[key]["n"] = len(rows)
        brands[key]["n_new_this_run"] = n_new
        brands[key]["n_with_text"] = sum(1 for r in rows if r.get("text"))
        print("  %-10s %4d creatives (%d new, %d with copy)"
              % (key, len(rows), n_new, brands[key]["n_with_text"]))

    return write(store, brands, today)


def write(store, brands, today):
    payload = {
        "meta": {
            "source": "Google Ads Transparency Center (adstransparency.google.com)",
            "provenance": "MEASURED — advertiser-level creative listings from Google's public "
                          "transparency product. Advertiser aggregates and ad copy only: no "
                          "users, no targeting, no personal data.",
            "region": "Thailand (Google region id %d)" % REGION_TH,
            "pulled": today,
            "no_account": sorted(NO_ACCOUNT),
            "excluded_accounts": {k: {"id": i, "why": w} for k, (i, w) in EXCLUDED.items()},
            "text_note": "text_src=render is MEASURED (Google's own rendered copy). "
                         "text_src=ocr is ESTIMATED (Thai tesseract over an image banner; a "
                         "transcription can misread). Image banners without --ocr carry no text.",
            "caveat": "Google publishes creative dates and formats but NOT spend or "
                      "impressions for commercial ads, so treat volume and run-length as the "
                      "metric, never budget. Accounts are hand-curated by advertiser id "
                      "because Thai brand names collide with personal names.",
        },
        "brands": brands,
        "creatives": store,
    }
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, sort_keys=True, indent=1)
    print("\nwrote %s — %d creatives across %d operator(s)"
          % (os.path.relpath(OUT, ROOT), len(store), len(brands)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Throttled as e:
        sys.stderr.write("\nTHROTTLED: %s\nNothing was written. Wait and re-run — a "
                         "rate-limited empty result must not be read as 'no ads'.\n" % e)
        sys.exit(3)
