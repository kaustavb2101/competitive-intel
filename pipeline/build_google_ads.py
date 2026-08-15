#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_google_ads.py — rival online-ad pressure AND messaging, from Google's Ads Transparency
Center (objective #2).

Turns the accumulating pull (`source-data/google_ads_raw.json`, written by pull_google_ads.py)
into the deterministic platform layer `platform/data/rival_ads.json` for the Competition tab.

WHAT IT MEASURES.
  * PRESSURE — per operator: distinct creatives run, how many are still live, typical run
    length, format mix, monthly launch cadence, and share of tracked creative volume.
  * MESSAGE — what each operator actually SAYS in those ads: the copy itself, the collateral
    and propositions it leans on (ESTIMATED keyword read), and critically the RATES it
    advertises, which is direct evidence of price competition on our own product.
  * THE ADS THEMSELVES — one row per individual creative still running in the last RECENT_DAYS,
    with its dates, its copy, the rate IT quotes and the conditions attached. `pricing` flags the
    ads that compete on COST, which is the slice a pricing decision is actually made from.
  * COVERAGE — every operator in the hand-verified census, bank and non-bank alike, with whether
    it advertises, was searched and found silent, or was excluded on review. Publishing only the
    advertisers would answer "who advertises" while looking like an answer to "the whole field".

WHAT IT CANNOT MEASURE. Google does NOT publish spend or impressions for commercial ads —
only for election ads. So this is share-of-VOLUME, never share-of-spend, and `meta` says so.
A brand running fewer but longer creatives is not necessarily spending less.

RATES ARE NEVER CONVERTED. Thai lenders quote both ต่อเดือน (per month) and ต่อปี (per year),
and 1.5%/month is not 1.5%/year. Each advertised rate keeps its own basis and unconverted
value; a rate whose basis is not stated in the copy is recorded with basis "unstated" rather
than assumed. Comparing across bases is the reader's call, made with the basis in front of them.

Deterministic: every date derives from the pull's own `meta.pulled` stamp, never the wall
clock, so a given input reproduces byte-for-byte. `--check` byte-compares; exits 3 (SKIP)
when the network pull has not been run, matching the other network-fed builders.

  python3 build_google_ads.py
  python3 build_google_ads.py --check
"""
import argparse
import collections
import datetime
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "source-data", "google_ads_raw.json")
# The hand-verified operator census. Read ONLY to name and tier the operators that do NOT
# advertise — the pull knows the keys it found nothing for, but not what they are called or
# whether they are a bank. Without it "all competitors" would silently mean "the five that
# advertise". Optional: absent, the coverage table degrades to keys-only rather than failing.
IN_UNI = os.path.join(ROOT, "source-data", "rival_universe.json")
OUT = os.path.join(ROOT, "platform", "data", "rival_ads.json")

LIVE_DAYS = 2          # last_shown within this many days of the pull = still running
NEW_DAYS = 30          # first_shown inside this window = a fresh push
MONTHS = 24            # cadence history length
TOP_MESSAGES = 12      # distinct copy lines surfaced per operator

# THE PER-AD FEED. The brand rollup above answers "how hard is Tidlor pushing"; it cannot answer
# "show me what they are actually saying, and on what terms", which is the question an exec asks.
# So alongside the aggregates we publish the individual recent creatives: one row per ad, with its
# dates, its copy, the rate IT advertises and the conditions it attaches.
RECENT_DAYS = 90       # a creative last shown within this window of the pull is "recent"
AD_COPY_CHARS = 600    # per-ad copy cap — keeps the layer a few hundred KB, not multi-MB

# PRICING ADS. "Which rivals are advertising on price, and on what terms" is a narrower question
# than "what are they advertising", and it is the one that decides how we price against them. An ad
# counts as pricing-related when it carries a trusted rate, when it plainly quoted a rate we refused
# to transcribe, or when its copy talks about the COST of the loan — instalment size, fees, credit
# limit — even with no percentage in it. "ผ่อนงวดละ 500 บาท" is a price claim with no % sign.
PRICE_CUE = ("ดอกเบี้ย", "อัตรา", "%", "ผ่อน", "งวดละ", "ค่าธรรมเนียม", "วงเงิน",
             "ฟรีค่า", "ไม่มีค่า", "ลดต้นลดดอก", "interest", "rate")
PRICE_THEMES = ("rate_cut", "tenor")
KINDS = ("render", "image", "other")

OWN = "AUTOX"          # our own operator key, so the UI can say "us" not "a rival"

# ESTIMATED keyword read over the ad copy. Thai title-loan advertising is formulaic, so a
# lexicon captures the proposition reliably — but it is still a keyword match, not semantics,
# and the output labels it estimated. Ordered: first match wins per bucket, all buckets scored.
THEMES = [
    ("rate_cut",     "Rate cut / low rate",   ["ลดดอกเบี้ย", "ดอกเบี้ยต่ำ", "ดอกเบี้ยพิเศษ",
                                               "ดอกเบี้ยเริ่มต้น"]),
    ("fast",         "Fast approval",         ["อนุมัติไว", "ทันใจ", "รู้ผลไว", "30 นาที",
                                               "รับเงินเลย", "ด่วน"]),
    ("no_guarantor", "No guarantor",          ["ไม่ต้องใช้คนค้ำ", "ไม่ต้องค้ำ", "ไม่ใช้คนค้ำ"]),
    ("keep_book",    "Keep the vehicle/book", ["ไม่ต้องโอนเล่ม", "ไม่โอนเล่ม", "มีรถ ใช้รถ",
                                               "ใช้รถได้"]),
    ("refinance",    "Refinance",             ["รีไฟแนนซ์", "refinance"]),
    ("car",          "Car (sedan/pickup)",    ["เก๋ง", "กระบะ", "รถยนต์"]),
    ("motorcycle",   "Motorcycle",            ["มอเตอร์ไซค์", "จยย", "บิ๊กไบค์", "รถจักรยานยนต์"]),
    ("truck",        "Truck / commercial",    ["รถบรรทุก", "หกล้อ", "สิบล้อ", "รถพ่วง"]),
    ("agri",         "Tractor / agri",        ["รถไถ", "รถเกี่ยว", "การเกษตร", "เกษตร"]),
    ("property",     "Home / land",           ["บ้าน", "ที่ดิน", "โฉนด"]),
    ("tenor",        "Long tenor / low instal", ["ผ่อนนาน", "ผ่อนสบาย", "ผ่อนน้อย", "งวดละ"]),
    ("digital",      "Online / app",          ["ออนไลน์", "แอป", "สมัครออนไลน์", "แอปพลิเคชัน"]),
    ("insurance",    "Insurance attached",    ["ประกัน"]),
]

# A percentage anywhere in a copy line; the basis is read from the same line.
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
PER_MONTH = ("ต่อเดือน", "/เดือน", "ต่อ เดือน", "per month")
PER_YEAR = ("ต่อปี", "/ปี", "ต่อ ปี", "per year", "ต่อปี*")
RATE_CUE = ("ดอกเบี้ย", "interest", "อัตรา")
# A lender also advertises to INVESTORS. "เมืองไทย แคปปิตอลเปิดจองหุ้นกู้ ดอกเบี้ยสูงสุด 4.15%
# ต่อปี" is MTC's debenture coupon — what it PAYS for funding, not what it charges a borrower.
# Reading it as an advertised lending rate would understate the field by ~4x, so the whole line
# is refused when it prices a funding instrument rather than a loan.
NOT_LENDING = ("หุ้นกู้", "พันธบัตร", "เงินฝาก", "ผลตอบแทน", "เสนอขายหุ้น", "จองซื้อ",
               "debenture", "deposit")


def d(s):
    return datetime.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))


def months_back(anchor, n):
    y, m = int(anchor[0:4]), int(anchor[5:7])
    keys = []
    for _ in range(n):
        keys.append("%04d-%02d" % (y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(keys))


def pct(a, b):
    return round(100.0 * a / b, 1) if b else 0.0


def rates_in(line, nxt=""):
    """[{value, basis}] advertised in one copy line. Never converts between bases.

    A rendered creative often breaks one sentence across lines, stranding the basis on the
    next fragment ("...ดอกเบี้ย เริ่มต้น 10%" / "ต่อปี"). So when the line itself states no
    basis, the following fragment is consulted — but ONLY when that fragment is a bare basis
    cue, never a whole sentence that could belong to a different offer.
    """
    if not any(c in line for c in RATE_CUE):
        return []
    if any(c in line for c in NOT_LENDING):
        return []                       # a bond/deposit coupon, not a borrower price
    basis = ("month" if any(c in line for c in PER_MONTH)
             else "year" if any(c in line for c in PER_YEAR) else "unstated")
    if basis == "unstated" and nxt and len(nxt) <= 12:
        if any(c in nxt for c in PER_MONTH):
            basis = "month"
        elif any(c in nxt for c in PER_YEAR):
            basis = "year"
    out = []
    for m in PCT_RE.finditer(line):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if 0 < v <= 60:                     # a plausible advertised lending rate
            out.append({"value": v, "basis": basis})
    return out


# OCR reads the transparency page's own furniture off the banner frame, and misreads logos and
# URLs into character soup. Both are filtered HERE rather than in the puller, so the raw capture
# keeps exactly what tesseract saw (auditable) while the published layer stays readable.
OCR_CHROME = ("ได้รับการสนับสนุน", "Sponsored", "สถาบันการเงิน")
MIN_LINE = 8
MIN_OCR_ADS = 3          # creatives an OCR-only rate must recur in before it is published
MIN_CHROME_BRANDS = 3    # advertisers sharing a line before it is judged platform furniture

# The rendered creative is served inside Google's own transparency shell, so the DOM text also
# carries that page's furniture — "Advertised by", the report-this-ad prompt, and untranslated
# i18n placeholders. Left in, these outrank real copy (โฆษณาโดย alone appears 231x) and the
# "what rivals are saying" panel would lead with Google's UI instead of the advertiser's message.
PAGE_CHROME = ("โฆษณาโดย", "โฆษณานี้ไม่ดี", "เราจะใช้ความคิดเห็น", "ผลิตภัณฑ์และบริการ",
               "Advertiser", "Ads by", "About this ad", "Why this ad")
# An app-install creative renders the Play Store listing, so the store's OWN interface lands in
# the text. Only one operator here runs those (MoneyDD), so the cross-advertiser rule above
# cannot see it — this surface is named explicitly. Google Play's Thai UI, not anyone's ad copy.
STORE_CHROME = ("ดำเนินการต่อ", "หมวดหมู่", "นักพัฒนาซอฟต์แวร์", "การดาวน์โหลด",
                "แอปใหม่และที่อัปเดต", "เกมที่ดำเนินไปอย่างรวดเร็ว", "การจัดอันดับเนื้อหา",
                "รีวิวจากผู้ใช้", "ติดตั้ง", "ในแอปพลิเคชัน")


def is_chrome(line, brand_names):
    """The transparency page's own UI, or the bare advertiser label — never ad copy."""
    if "%1" in line or "%2" in line:            # untranslated i18n placeholder
        return True
    if any(line.startswith(c) or c in line for c in PAGE_CHROME):
        return True
    if line in STORE_CHROME:                    # exact only — these are whole UI labels
        return True
    # the advertiser's name standing alone is a label, not a message. Tested as a SUBSTRING of
    # the registered name so "ศรีสวัสดิ์" is caught under "ศรีสวัสดิ์ เงินสดทันใจ" — while the
    # longer "เงินให้ใจ รถแลกเงิน" survives, because a name plus a product IS a proposition.
    bare = line.strip(" ·—–-:.")
    return any(bare == n or bare in n for n in brand_names)


def clean_line(line, src, min_len=MIN_LINE):
    """A displayable copy line, or None if it is chrome or OCR garble.

    min_len=1 keeps the short fragments a renderer splits an offer across ("10%" / "ต่อปี"),
    which the display pass drops but the rate reader needs.
    """
    for c in OCR_CHROME:
        if line.startswith(c):
            line = line[len(c):].strip(" -–·—:")
    line = " ".join(line.split())
    if len(line) < min_len:
        return None
    if src != "ocr":
        return line
    # garbled OCR fragments a logo into many stray 1–2 character tokens ("พเพเพ.ปีส อห.๐อทท");
    # real Thai ad copy does not look like that.
    toks = line.split()
    if len(toks) >= 4 and sum(1 for t in toks if len(t) <= 2) / float(len(toks)) > 0.5:
        return None
    # a misread URL comes back as one dotted blob ("เพพพเ.ธสพลฝี่.00.ป่า") — no spaces, ≥2 dots
    if len(toks) <= 2 and line.count(".") >= 2:
        return None
    return line


def clean_text(lines, src, min_len=MIN_LINE, brand_names=(), shared=()):
    out, seen = [], set()
    for l in lines or []:
        c = clean_line(l, src, min_len)
        if c and c not in seen and c not in shared and not is_chrome(c, brand_names):
            seen.add(c)
            out.append(c)
    return out


def cross_advertiser_chrome(creatives):
    """Lines that MIN_CHROME_BRANDS+ different advertisers all "wrote" — i.e. nobody wrote them.

    The rendered creative is served inside Google's transparency shell, whose ad-feedback widget
    ("ส่งความคิดเห็น", "ดูการตั้งค่าโฆษณา") lands in the DOM text of every advertiser alike.
    Blacklisting those strings by hand would rot the moment Google re-words its UI, so they are
    identified structurally: competing lenders do not independently write the same sentence.
    Measured on the 2026-07 pull this separated cleanly — 8 lines shared by 4 advertisers, all 8
    platform furniture, and nothing at all shared by exactly 3, so the threshold sits in a gap.
    """
    owners = collections.defaultdict(set)
    for c in creatives.values():
        for l in clean_text(c.get("text"), c.get("text_src")):
            owners[l].add(c.get("brand"))
    return set(l for l, b in owners.items() if len(b) >= MIN_CHROME_BRANDS)


def themes_in(lines):
    hit = set()
    blob = " ".join(lines)
    for key, _label, words in THEMES:
        if any(w in blob for w in words):
            hit.add(key)
    return hit


def build():
    raw = json.load(io.open(IN, encoding="utf-8"))
    pulled = raw["meta"]["pulled"]
    anchor = d(pulled)
    creatives = raw.get("creatives") or {}
    meta_brands = raw.get("brands") or {}
    shared = cross_advertiser_chrome(creatives)

    by_brand = collections.defaultdict(list)
    for cid, c in creatives.items():
        by_brand[c["brand"]].append(dict(c, _id=cid))

    total = len(creatives)
    cadence_keys = months_back(pulled, MONTHS)
    theme_label = {k: lbl for k, lbl, _ in THEMES}

    brands = []
    ads = []                                   # the per-ad feed, filled per brand below
    for key in sorted(by_brand):
        rows = sorted(by_brand[key], key=lambda r: r["_id"])
        info = meta_brands.get(key) or {}
        # the advertiser's own name is a label on the transparency page, not ad copy
        names = set(n for n in (info.get("name_th"), info.get("name_en")) if n)
        for a in (info.get("accounts") or []):
            names.add((a.get("note") or "").split(" — ")[0].strip())
        names.discard("")
        live = new = 0
        runs, kinds, cad = [], collections.Counter(), collections.Counter()
        firsts, lasts = [], []
        msg = {}                                   # copy line -> {first, last, n}
        theme_n = collections.Counter()
        rate_rows, n_text, n_ocr = [], 0, 0
        ad_rows = []                           # this brand's creatives, pending the rate-trust gate
        for c in rows:
            f, l = c.get("first_shown"), c.get("last_shown")
            kinds[c.get("kind") if c.get("kind") in KINDS else "other"] += 1
            if f:
                firsts.append(f)
                cad[f[0:7]] += 1
                if (anchor - d(f)).days <= NEW_DAYS:
                    new += 1
            if l:
                lasts.append(l)
                if (anchor - d(l)).days <= LIVE_DAYS:
                    live += 1
            if f and l:
                runs.append((d(l) - d(f)).days)
            text = clean_text(c.get("text"), c.get("text_src"), brand_names=names,
                              shared=shared)
            if text:
                n_text += 1
                if c.get("text_src") == "ocr":
                    n_ocr += 1
                for t in themes_in(text):
                    theme_n[t] += 1
                for line in text:
                    e = msg.setdefault(line, {"line": line, "first": f, "last": l, "n": 0,
                                              "src": c.get("text_src")})
                    e["n"] += 1
                    if f and (not e["first"] or f < e["first"]):
                        e["first"] = f
                    if l and (not e["last"] or l > e["last"]):
                        e["last"] = l
            # rates read off a SEPARATE, un-length-filtered pass: a renderer splits one offer
            # across lines ("10%" then "ต่อปี") and both fragments sit under MIN_LINE, so the
            # display filter would silently delete the advertised rate.
            rate_lines = clean_text(c.get("text"), c.get("text_src"), min_len=1,
                                    brand_names=names, shared=shared)
            seen_rate = set()
            this_ad_rates = []
            for i, line in enumerate(rate_lines):
                nxt = rate_lines[i + 1] if i + 1 < len(rate_lines) else ""
                for r in rates_in(line, nxt):
                    # a renderer repeats the same offer as a fragment and again in full;
                    # count each (value, basis) once per creative, not once per fragment
                    sig = (r["value"], r["basis"])
                    if sig in seen_rate:
                        continue
                    seen_rate.add(sig)
                    # quote the adjacent fragment too when the rate line alone is meaningless
                    ev = line if len(line) >= MIN_LINE else (line + " " + nxt).strip()
                    rate_rows.append(dict(r, line=ev, last=l, src=c.get("text_src")))
                    this_ad_rates.append(dict(r, line=ev))

            # Hold the ad aside: its rates cannot be published until the brand-wide OCR-trust gate
            # below has run, because trust is decided by how often a figure RECURS across the
            # brand's creatives — which is not knowable while still inside this loop.
            if l and (anchor - d(l)).days <= RECENT_DAYS:
                copy = " · ".join(text)
                ad_rows.append({
                    "id": c["_id"],
                    "key": key,
                    "first": f,
                    "last": l,
                    "days": (d(l) - d(f)).days if (f and l) else None,
                    "kind": c.get("kind") if c.get("kind") in KINDS else "other",
                    # src decides whether the copy may be quoted verbatim: render is Google's own
                    # text, ocr is a transcription that visibly mangles Thai.
                    "src": c.get("text_src"),
                    "copy": copy[:AD_COPY_CHARS],
                    "copy_truncated": len(copy) > AD_COPY_CHARS,
                    # themes_in returns a set; sort it or the JSON is both unserializable and
                    # non-reproducible run to run, which --check would catch as phantom drift.
                    "themes": sorted(themes_in(text)),
                    "_rates": this_ad_rates,
                })
        runs.sort()

        # OCR drops digits: Tidlor's disclosed "อัตราดอกเบี้ย 12-24% ต่อปี" came back from two
        # banners as "อัตราดอกเบี้ย 1 % ต่อปี", which as a published lending rate would be absurd.
        # Text read straight from the rendered DOM cannot lose a digit, so it is trusted alone;
        # an OCR-only figure has to recur across at least MIN_OCR_ADS separate creatives.
        rendered = set((r["value"], r["basis"]) for r in rate_rows if r.get("src") != "ocr")
        ocr_n = collections.Counter((r["value"], r["basis"])
                                    for r in rate_rows if r.get("src") == "ocr")
        def trusted(r):
            sig = (r["value"], r["basis"])
            return sig in rendered or ocr_n[sig] >= MIN_OCR_ADS
        dropped_rates = sorted(set((r["value"], r["basis"]) for r in rate_rows
                                   if not trusted(r)))
        rate_rows = [r for r in rate_rows if trusted(r)]

        # Release the held-back per-ad rows through the SAME gate. An untrusted figure is dropped
        # from the ad rather than shown with a warning: this table is read by people deciding how
        # to price against a rival, and "12-24%/yr" arriving as "1%/yr" because tesseract ate a
        # digit is worse than showing no rate at all. n_rates_dropped keeps the omission visible.
        for a in ad_rows:
            cand = a.pop("_rates")
            uniq, seen = [], set()
            for r in cand:
                if not trusted(r):
                    continue
                sig = (r["value"], r["basis"])
                if sig in seen:
                    continue
                seen.add(sig)
                uniq.append({"value": r["value"], "basis": r["basis"], "line": r["line"]})
            a["rates"] = sorted(uniq, key=lambda r: (r["basis"], r["value"]))
            # distinct figures this ad advertised that the gate refused — so "no rate shown" can
            # be told apart from "a rate was shown and we did not trust the transcription"
            a["n_rates_dropped"] = len({(r["value"], r["basis"]) for r in cand
                                        if not trusted(r)})
            a["pricing"] = bool(uniq) or a["n_rates_dropped"] > 0 \
                or any(t in PRICE_THEMES for t in a["themes"]) \
                or any(cue in a["copy"] for cue in PRICE_CUE)
            a["brand"] = info.get("name_en") or key
            a["name_th"] = info.get("name_th")
            a["tier"] = info.get("tier")     # bank / nonbank / broker / us — the feed splits on it
            a["is_us"] = key == OWN
            ads.append(a)

        # advertised rates, kept per basis and never converted across bases
        rate_out = {}
        for basis in ("month", "year", "unstated"):
            vals = sorted(r["value"] for r in rate_rows if r["basis"] == basis)
            if vals:
                rate_out[basis] = {"min": vals[0], "max": vals[-1], "n": len(vals)}
        headline = None
        for basis in ("year", "month", "unstated"):        # the number they lead with
            if basis in rate_out:
                headline = {"value": rate_out[basis]["min"], "basis": basis}
                break

        # ranked by how many creatives carry the line — "what they push", not "what ran last";
        # every row still carries its own last-seen date, so recency stays visible
        messages = sorted(msg.values(),
                          key=lambda m: (m["n"], m["last"] or "", m["line"]), reverse=True)
        brands.append({
            "key": key,
            "brand": info.get("name_en") or key,
            "name_th": info.get("name_th"),
            "tier": info.get("tier"),
            "is_us": key == OWN,
            "accounts": [a["id"] for a in (info.get("accounts") or [])],
            "advertiser_names": sorted({c.get("advertiser_name") for c in rows
                                        if c.get("advertiser_name")}),
            "n_creatives": len(rows),
            "n_live": live,
            "live_pct": pct(live, len(rows)),
            "n_new_30d": new,
            "share_of_volume_pct": pct(len(rows), total),
            "median_run_days": runs[len(runs) // 2] if runs else None,
            "longest_run_days": runs[-1] if runs else None,
            "kind_mix": {k: kinds.get(k, 0) for k in KINDS},
            "first_shown": min(firsts) if firsts else None,
            "last_shown": max(lasts) if lasts else None,
            "cadence": [cad.get(k, 0) for k in cadence_keys],
            # --- messaging ---
            "n_with_copy": n_text,
            "copy_coverage_pct": pct(n_text, len(rows)),
            "n_copy_ocr": n_ocr,
            "themes": [{"key": k, "label": theme_label[k], "n": n,
                        "pct": pct(n, n_text)}
                       for k, n in sorted(theme_n.items(), key=lambda kv: (-kv[1], kv[0]))],
            "top_theme": (sorted(theme_n.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
                          if theme_n else None),
            "messages": messages[:TOP_MESSAGES],
            "n_messages": len(messages),
            # what the rate reader refused, so a missing rate is never a silent one
            "rates_dropped": [{"value": v, "basis": b} for v, b in dropped_rates],
            "rates": rate_out,
            "headline_rate": headline,
        })
    brands.sort(key=lambda b: -b["n_creatives"])
    # Newest ad first — the question this feed answers is "what are they running NOW". key and id
    # break ties so the order is total and the layer reproduces byte-for-byte under --check.
    ads.sort(key=lambda a: (a["last"], a["key"], a["id"]), reverse=True)

    # every distinct advertised rate across the field, so price competition is comparable
    market_rates = []
    for b in brands:
        if b["headline_rate"]:
            basis = b["headline_rate"]["basis"]
            band = (b.get("rates") or {}).get(basis) or {}
            # the headline is the FROM rate ("ดอกเบี้ยเริ่มต้น 10%"). Tidlor also discloses an
            # upper bound of 24%/yr in the same basis; carrying only the floor would read as a
            # cheaper offer than the ad actually makes, so the top of the band travels with it.
            market_rates.append({"brand": b["brand"], "key": b["key"],
                                 "value": b["headline_rate"]["value"],
                                 "basis": basis,
                                 "max": band.get("max"),
                                 "n": band.get("n")})
    market_rates.sort(key=lambda r: (r["basis"], r["value"], r["key"]))

    silent = sorted(set((raw.get("meta") or {}).get("no_account", [])))

    # --- coverage, stated per tier -------------------------------------------------------
    # The exec question is "all competitors, bank and non-bank". Five operators advertise on
    # Google; thirteen do not. Publishing only the five would answer a different question than
    # the one asked, so every tracked operator gets a row and its own reason for being here or
    # not. Silent is a MEASURED absence on Google specifically — the account was searched for
    # and does not exist — never a claim that the operator does not advertise anywhere.
    uni = {}
    if os.path.exists(IN_UNI):
        for o in (json.load(io.open(IN_UNI, encoding="utf-8")).get("operators") or []):
            uni[o.get("key")] = o
    advertising = set(b["key"] for b in brands)
    excluded = (raw.get("meta") or {}).get("excluded_accounts") or {}
    coverage = []
    for key in sorted(set(list(advertising) + silent + list(uni))):
        o = uni.get(key) or meta_brands.get(key) or {}
        b = next((x for x in brands if x["key"] == key), None)
        # advertising: pinned account, creatives pulled. silent: searched and NO Thai advertiser
        # account exists — a real competitive finding. excluded: an account exists but review
        # found it is not this lender's title-loan marketing (KKP's is its securities app), so
        # counting it would misattribute another business's spend. untracked: in the census,
        # never searched — the only state that is a gap in OUR work rather than a fact about them.
        state = ("advertising" if b else
                 "silent" if key in silent else
                 "excluded" if key in excluded else "untracked")
        coverage.append({
            "key": key,
            "brand": o.get("name_en") or (b or {}).get("brand") or key,
            "name_th": o.get("name_th"),
            "tier": o.get("tier") or (b or {}).get("tier"),
            "is_us": key == OWN,
            "n_creatives": (b or {}).get("n_creatives", 0),
            "n_ads_recent": sum(1 for a in ads if a["key"] == key),
            "n_ads_pricing": sum(1 for a in ads if a["key"] == key and a["pricing"]),
            "state": state,
            "why": (excluded.get(key) or {}).get("why") if state == "excluded" else None,
        })
    coverage.sort(key=lambda c: (-c["n_ads_pricing"], -c["n_creatives"], c["key"]))
    tier_cov = {}
    for c in coverage:
        t = tier_cov.setdefault(c["tier"] or "unknown",
                                {"n": 0, "advertising": 0, "silent": 0,
                                 "excluded": 0, "untracked": 0})
        t["n"] += 1
        t[c["state"]] += 1

    return {
        "meta": {
            "source": "Google Ads Transparency Center",
            "provenance": "MEASURED — advertiser-level creative listings from Google's public "
                          "transparency product. Advertiser aggregates and ad copy only: no "
                          "users, no targeting, no personal data.",
            "region": "Thailand",
            "pulled": pulled,
            "live_window_days": LIVE_DAYS,
            "new_window_days": NEW_DAYS,
            "cadence_months": cadence_keys,
            "theme_label": theme_label,
            "copy_note": "Ad copy with src=render is MEASURED (Google's own rendered "
                         "creative). src=ocr is ESTIMATED (Thai tesseract over an image "
                         "banner). Theme buckets are an ESTIMATED keyword read over the copy.",
            "rate_note": "Advertised rates keep the basis the ad states — ต่อเดือน (month) and "
                         "ต่อปี (year) are NEVER converted into one another, and copy that "
                         "states no basis is recorded as 'unstated'. These are advertised "
                         "headline rates, not effective yields.",
            "limits": "Google publishes creative dates and formats but NOT spend or "
                      "impressions for commercial ads. These are share-of-VOLUME figures, "
                      "never share-of-spend — a brand running fewer, longer creatives is not "
                      "necessarily spending less. Accounts are pinned by advertiser id "
                      "because Thai brand names collide with personal names.",
            "n_creatives": total,
            "n_brands": len(brands),
            "no_account_found": silent,
            "recent_days": RECENT_DAYS,
            "n_ads": len(ads),
            "n_ads_pricing": sum(1 for a in ads if a["pricing"]),
            "pricing_note": "pricing=true means the ad competes on COST: it carries a trusted "
                            "rate, or it quoted a rate we refused to transcribe, or its copy "
                            "talks about instalment size / fees / credit limit. An instalment "
                            "claim with no percentage ('ผ่อนงวดละ 500 บาท') is still a price "
                            "claim, which is why this is broader than 'has a rate'.",
            "ads_note": "One row per individual creative last shown within %d days of the pull: "
                        "its dates, its copy, the rate IT advertises and the conditions it "
                        "attaches. A per-ad rate passes the same OCR-trust gate as the brand "
                        "aggregates (a figure seen only by OCR must recur across %d creatives), "
                        "so n_rates_dropped > 0 means the ad DID advertise a rate we refused to "
                        "transcribe — not that it quoted none. Conditions are the ESTIMATED "
                        "keyword themes."
                        % (RECENT_DAYS, MIN_OCR_ADS),
            "tier_coverage": tier_cov,
            "coverage_note": "Only operators that actually advertise on Google appear here. "
                             "Silent operators are listed in no_account_found and are NOT "
                             "evidence of no advertising — they may run Facebook or LINE, "
                             "neither of which publishes Thai credit ads (Meta's credit-ad "
                             "slice is invalid for TH: see pipeline/spike_meta_ads.py).",
        },
        "market_rates": market_rates,
        "brands": brands,
        "coverage": coverage,
        "ads": ads,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN):
        if args.check:
            print("build_google_ads.py --check: SKIP (no google_ads_raw source — network pull)")
            sys.exit(3)
        sys.exit("build_google_ads.py: run pull_google_ads.py first")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_google_ads.py --check: output missing — run the builder.")
        if io.open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_google_ads.py --check: drifted — re-run the builder.")
        print("build_google_ads.py --check: OK (byte-exact)")
        return
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d creatives across %d operator(s)"
          % (OUT, obj["meta"]["n_creatives"], obj["meta"]["n_brands"]))
    for b in obj["brands"]:
        hr = b["headline_rate"]
        print("  %-11s %4d creatives %3d live %3d new/30d %5.1f%%  copy %d (%s)  rate %s  %s"
              % (b["key"], b["n_creatives"], b["n_live"], b["n_new_30d"],
                 b["share_of_volume_pct"], b["n_with_copy"],
                 "%.0f%%" % b["copy_coverage_pct"],
                 ("%.2f%%/%s" % (hr["value"], hr["basis"])) if hr else "—",
                 b["top_theme"] or ""))


if __name__ == "__main__":
    main()
