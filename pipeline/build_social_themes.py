#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_social_themes.py — what the market SAYS vs what the lenders ADVERTISE (objective #2).

THE IDEA. We already hold two piles of Thai text that nobody has ever read against each other:

  DEMAND  — what customers actually write, unprompted:
              source-data/youtube_comments.json  (public comments under rival brand videos)
              source-data/app_reviews.json       (Google Play)
              source-data/apple_reviews.json     (Apple App Store)
  SUPPLY  — what the lenders choose to say, in paid and owned channels:
              source-data/google_ads_raw.json    (Google Ads Transparency creatives)
              source-data/rival_promos.json      (the rivals' own promo pages)

Counting themes on either side alone is mildly interesting. Counting them on BOTH and subtracting is
the marketing read: a theme that is loud in DEMAND and silent in SUPPLY is an unanswered objection —
the thing customers keep raising that nobody is addressing in market. A theme loud in SUPPLY and
absent from DEMAND is spend that is not landing. That difference is what this file computes.

  out: platform/data/social_themes.json

  python3 build_social_themes.py            # rebuild
  python3 build_social_themes.py --check    # byte-exact reproduce (gate)

MEASURED vs ESTIMATED — the line, stated plainly because the whole output depends on it.
  * The COUNTS are MEASURED. Every number is "how many documents contain this phrase", and the
    phrase list is published in meta.lexicon so any number here can be re-derived by hand.
  * The THEME BUCKETS are ESTIMATED. Deciding that "ดอกแพง" belongs to "interest & fees" is an
    editorial judgement, and so is the choice of which phrases to look for at all. A theme that is
    not in the lexicon reads as zero — absence of evidence here is not evidence of absence.
  * Nothing is sentiment-scored by a model. "Complaint" vs "praise" is itself a lexicon bucket.

Thai has no word boundaries, so matching is by SUBSTRING, which is correct for Thai but means short
keywords over-match (e.g. "ช้า" = slow is a substring of several unrelated words). Keywords are kept
long enough to be specific; the ones that cannot be (rate digits, single words) are flagged
`loose: true` in the lexicon so a reader knows which counts to treat as soft.

PRIVACY. Reads comment/review TEXT only. `pull_youtube_comments.py` never writes author identity to
disk, and the review stores carry no author name either. Quotes published here are short, capped in
number, and unattributed — the same contract the app-review ladders already ship under.

DETERMINISM. No wall clock anywhere: the "as of" stamp is the newest document date IN THE DATA.
Sorting is total (score, then key) so ties cannot reorder between runs.
"""
import argparse
import collections
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data")
OUT = os.path.join(ROOT, "platform", "data", "social_themes.json")

MAX_QUOTES = 3           # per theme per side — evidence, not a reading list
QUOTE_CHARS = 160
MIN_DOCS_FOR_GAP = 12    # a theme needs this many demand hits before a "gap" claim is made

# ---------------------------------------------------------------------------------------------
# THE LEXICON (ESTIMATED). Two families, because the two sides of the corpus speak differently.
#
#   DEMAND themes  — what a customer raises: an objection, a question, or praise.
#   SUPPLY themes  — what a lender claims: the offer, the hook, the reassurance.
#
# Several themes deliberately exist on BOTH sides (rate, speed, limit, channel) — those are the ones
# where the gap arithmetic is meaningful, because both sides are talking about the same thing.
# `loose` marks a keyword short enough to over-match; its count is a soft upper bound.
# ---------------------------------------------------------------------------------------------
DEMAND = [
    ("interest-cost", "Interest & fees", "objection", [
        "ดอกเบี้ย", "ดอกแพง", "ดอกโหด", "ค่าธรรมเนียม", "ค่าปรับ", "ค่างวด", "เบี้ยปรับ",
        "ดอกเยอะ", "แพงมาก", "ค่าทวงถาม", "interest"]),
    ("approval-speed", "Approval speed & waiting", "objection", [
        "อนุมัติช้า", "รอนาน", "ไม่อนุมัติ", "หลายวัน", "ยังไม่ได้เงิน", "รอเป็นอาทิตย์",
        "ติดต่อกลับ", "เงียบ"]),
    ("app-reliability", "App broken / can't log in", "objection", [
        "เข้าไม่ได้", "แอปล่ม", "หน้าจอดำ", "ปิดปรับปรุง", "ใช้งานไม่ได้", "เด้งออก",
        "ค้าง", "otp", "โอทีพี", "รหัสผ่าน", "ล็อกอิน", "อัปเดตแล้วใช้ไม่ได้"]),
    ("service-staff", "Staff & branch service", "objection", [
        "พนักงาน", "บริการแย่", "สาขา", "คอลเซ็นเตอร์", "call center", "ติดต่อไม่ได้",
        "ไม่รับสาย", "พูดจา", "หยาบคาย", "มารยาท"]),
    ("trust-collections", "Collections & trust", "objection", [
        "ทวงหนี้", "ทวงถาม", "หลอกลวง", "โกง", "ข่มขู่", "ยึดรถ", "มิจฉาชีพ", "หลอก",
        "ประจาน", "โทรหาคนอื่น", "โทรหาญาติ"]),
    ("eligibility-docs", "Eligibility & documents", "objection", [
        "เอกสาร", "เล่มทะเบียน", "คนค้ำ", "ผู้ค้ำ", "สลิปเงินเดือน", "ไม่มีสลิป",
        "ติดแบล็คลิสต์", "แบล็คลิสต์", "เครดิตบูโร", "ไม่มีงานประจำ", "อาชีพอิสระ"]),
    ("repayment-hardship", "Can't keep up / restructuring", "objection", [
        "ผ่อนไม่ไหว", "จ่ายไม่ไหว", "ปิดยอด", "พักชำระ", "ปรับโครงสร้าง", "ประนอมหนี้",
        "ผ่อนต่อไม่ไหว", "ขอลดค่างวด", "ไม่มีเงินจ่าย"]),
    ("amount-limit", "How much can I get", "question", [
        "วงเงิน", "ได้กี่บาท", "ได้เท่าไหร่", "ได้น้อย", "กู้ได้เท่าไร", "ประเมินราคา",
        "ตีราคา", "ราคารถ"]),
    ("how-to-apply", "How do I apply / who do I contact", "question", [
        "สมัครยังไง", "ทำยังไง", "ต้องทำไง", "สนใจ", "ติดต่อ", "เบอร์โทร", "อยากกู้",
        "อยากได้เงิน", "สมัครที่ไหน", "ต้องใช้อะไรบ้าง", "รับไหม"]),
    ("praise", "Praise & thanks", "praise", [
        "ดีมาก", "ประทับใจ", "ขอบคุณ", "เร็วมาก", "สะดวก", "บริการดี", "ชอบ",
        "ช่วยได้จริง", "แนะนำเลย"]),
]

SUPPLY = [
    ("interest-cost", "Interest & fees", "claim", [
        "ดอกเบี้ย", "ดอกเบี้ยต่ำ", "ดอกถูก", "ดอกเริ่มต้น", "ลดดอก", "ดอกเบี้ยพิเศษ",
        "ต่อเดือน", "ต่อปี"]),
    ("approval-speed", "Fast approval", "claim", [
        "อนุมัติไว", "อนุมัติเร็ว", "รู้ผลไว", "ทันใจ", "ได้เงินไว", "รับเงินทันที",
        "30 นาที", "ภายในวันเดียว", "วันเดียวจบ"]),
    ("amount-limit", "High limit", "claim", [
        "วงเงินสูง", "วงเงินใหญ่", "สูงสุด", "ล้าน", "วงเงิน"]),
    ("no-guarantor", "No guarantor needed", "claim", [
        "ไม่ต้องมีคนค้ำ", "ไม่ใช้คนค้ำ", "ไม่ต้องค้ำ", "ไม่มีคนค้ำ", "ไม่ต้องมีผู้ค้ำ"]),
    ("keep-vehicle", "Keep driving your vehicle", "claim", [
        "ไม่ต้องโอนเล่ม", "รถยังใช้ได้", "ไม่ต้องจอด", "ยังได้ใช้รถ", "รับเล่มไม่รับรถ",
        "จอดรถไว้ใช้"]),
    ("easy-docs", "Minimal documents / anyone qualifies", "claim", [
        "ไม่ต้องใช้เอกสาร", "เอกสารน้อย", "ใช้แค่", "ไม่เช็คเครดิตบูโร", "ไม่เช็คบูโร",
        "อาชีพอิสระก็กู้ได้", "ไม่มีสลิปก็ได้"]),
    ("branch-reach", "Branches everywhere", "claim", [
        "สาขาทั่วประเทศ", "ใกล้บ้าน", "ทุกสาขา", "สาขาใกล้", "กว่า", "สาขา"]),
    ("digital-channel", "App / online / LINE", "claim", [
        "ผ่านแอป", "ออนไลน์", "แอปพลิเคชัน", "โหลดแอป", "ไลน์", "line", "app"]),
    ("promo-giveaway", "Prize draw / giveaway / free", "claim", [
        "ลุ้นรับ", "แจก", "ฟรี", "ของแถม", "รับเลย", "โปรโมชั่น", "แคมเปญ", "ส่วนลด"]),
    ("trust-licensed", "Licensed / regulated / safe", "claim", [
        "ถูกกฎหมาย", "ได้รับอนุญาต", "ธปท", "กำกับ", "ปลอดภัย", "มั่นใจ", "ไม่ใช่มิจฉาชีพ"]),
]

# Calls to action — the imperative half of SUPPLY text. Counted separately from themes because a
# CTA is a mechanic ("what they want you to do next"), not a message ("what they want you to believe").
CTAS = [
    ("apply-now", "สมัครเลย / สมัครตอนนี้", ["สมัครเลย", "สมัครตอนนี้", "สมัครวันนี้", "สมัครง่าย"]),
    ("click", "คลิก / กดที่นี่", ["คลิก", "กดที่นี่", "กดเลย", "คลิกเลย", "ดูเพิ่มเติม"]),
    ("chat", "ทักแชท / LINE", ["ทักแชท", "แอดไลน์", "แอดLine", "inbox", "ทักมา", "add line"]),
    ("call", "โทร", ["โทรเลย", "โทร.", "โทรหา", "call center", "สายด่วน"]),
    ("visit-branch", "เข้าสาขา", ["เข้าสาขา", "ไปที่สาขา", "สาขาใกล้บ้าน", "มาที่สาขา"]),
    ("download-app", "โหลดแอป", ["โหลดแอป", "ดาวน์โหลด", "download"]),
    ("check-limit", "เช็ควงเงิน", ["เช็ควงเงิน", "ตรวจสอบวงเงิน", "ประเมินวงเงิน", "เช็คเลย"]),
]

# ---------------------------------------------------------------------------------------------
# ANSWERED / UNANSWERED (ESTIMATED PAIRING). Only three theme KEYS appear in both lexicons, because
# the two sides name the same thing differently: a customer writes "แอปล่ม" (the app crashed), a
# lender advertises "ผ่านแอป" (apply in the app). Comparing only the three literal key matches would
# miss the most important rows. So each demand theme is paired, editorially, with the supply theme(s)
# that would ANSWER it — published here so the pairing can be argued with.
#
# A demand theme with no counterpart at all is listed with an empty pairing: nothing in the field's
# messaging speaks to it. That is a finding, not a gap in the data.
PAIRS = [
    ("app-reliability",    ["digital-channel"],
     "The app failing is the #2 thing customers write about; digital is barely marketed."),
    ("trust-collections",  ["trust-licensed"],
     "Collections conduct and scam fear vs how much the field reassures on being licensed."),
    ("eligibility-docs",   ["easy-docs", "no-guarantor"],
     "Who qualifies and what paperwork — the field's 'easy docs / no guarantor' claims answer this."),
    ("interest-cost",      ["interest-cost"], "Rate and fees, both sides."),
    ("amount-limit",       ["amount-limit"], "How much can I get, both sides."),
    ("approval-speed",     ["approval-speed"], "Speed of decision, both sides."),
    ("service-staff",      ["branch-reach"],
     "Staff conduct vs a branch-count claim — reach is not the same as service, so a large "
     "positive here means the field answers a service complaint with a coverage boast."),
    ("repayment-hardship", [],
     "Nobody in the field advertises hardship, restructuring or payment relief."),
    ("how-to-apply",       [],
     "Unconverted intent sitting in public comment threads — see the CTA table for what the field "
     "asks people to do instead."),
    ("praise",             [], "Positive sentiment; no supply counterpart by design."),
]

# keywords too short to be safe on their own — their counts are soft upper bounds
LOOSE = {"แพงมาก", "เงียบ", "ค้าง", "otp", "สาขา", "ชอบ", "สนใจ", "ติดต่อ", "แจก", "ฟรี",
         "กว่า", "ล้าน", "วงเงิน", "app", "line", "ต่อเดือน", "ต่อปี", "หลอก", "ใช้แค่",
         "ดูเพิ่มเติม", "คลิก", "มั่นใจ", "ปลอดภัย", "กำกับ", "download", "โทร."}


def norm(s):
    """Lowercase for Latin, collapse whitespace. Thai is untouched — it has no case."""
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def hits(text, keywords):
    """Which of `keywords` occur in `text`. Substring is correct for unsegmented Thai."""
    return [k for k in keywords if k.lower() in text]


def quote(text):
    t = re.sub(r"\s+", " ", text).strip()
    return (t[:QUOTE_CHARS].rstrip() + "…") if len(t) > QUOTE_CHARS else t


def load(name):
    p = os.path.join(SRC, name)
    if not os.path.exists(p):
        return None
    return json.load(io.open(p, encoding="utf-8"))


def demand_docs():
    """[(brand, source, date, text)] — everything a customer wrote."""
    out = []
    yt = load("youtube_comments.json")
    if yt:
        for bkey, rec in (yt.get("brands") or {}).items():
            for c in rec.get("comments") or []:
                out.append((bkey, "youtube", (c.get("published") or "")[:10], c.get("text") or ""))
    for fn, src in (("app_reviews.json", "play"), ("apple_reviews.json", "apple")):
        d = load(fn)
        if not d:
            continue
        for bkey, a in (d.get("apps") or {}).items():
            for r in a.get("reviews_store") or []:
                txt = " ".join(x for x in (r.get("title"), r.get("content")) if x)
                out.append((bkey, src, (r.get("at") or "")[:10], txt))
    pt = load("pantip_threads.json")
    if pt:
        for bkey, rec in (pt.get("brands") or {}).items():
            for t in rec.get("threads") or []:
                # The opening post is one document: the question the customer actually came to ask.
                op = " ".join(x for x in (t.get("title"), t.get("post") or t.get("snippet")) if x)
                if op:
                    out.append((bkey, "pantip", (t.get("created") or "")[:10], op))
                for c in t.get("comments") or []:
                    # org-badged replies are a LENDER speaking, not a customer. They are counted as
                    # supply instead (see supply_docs) so a brand answering its own thread can never
                    # inflate the demand side.
                    if c.get("org"):
                        continue
                    out.append((bkey, "pantip", (c.get("created") or "")[:10], c.get("text") or ""))
    return out


def supply_docs():
    """[(brand, source, date, text)] — everything a lender published."""
    out = []
    ga = load("google_ads_raw.json")
    if ga:
        for cid, c in (ga.get("creatives") or {}).items():
            t = c.get("text")
            if isinstance(t, list):
                t = " ".join(str(x) for x in t)
            out.append((c.get("brand") or "?", "google-ads",
                        (c.get("last_shown") or c.get("first_shown") or "")[:10], t or ""))
    pr = load("rival_promos.json")
    if pr:
        for it in pr.get("items") or []:
            out.append((it.get("brand") or "?", "promo", (it.get("date") or "")[:10],
                        " ".join(x for x in (it.get("title"), it.get("detail")) if x)))
    pt = load("pantip_threads.json")
    if pt:
        # A lender's own verified account replying in a public thread IS the lender publishing a
        # message — unpaid, but a message. It belongs on the supply side, not the customer side.
        for bkey, rec in (pt.get("brands") or {}).items():
            for t in rec.get("threads") or []:
                for c in t.get("comments") or []:
                    if c.get("org"):
                        out.append((bkey, "pantip-official", (c.get("created") or "")[:10],
                                    c.get("text") or ""))
    return out


def _by_source(docs):
    """source -> {n, brands{brand: n}}. The denominators a reader needs to compare brands
    like-for-like instead of across a blend — see meta.cohort_warning."""
    out = {}
    for brand, src, _date, _text in docs:
        rec = out.setdefault(src, {"n": 0, "brands": {}})
        rec["n"] += 1
        rec["brands"][brand] = rec["brands"].get(brand, 0) + 1
    return out


def tally(docs, themes):
    """theme key -> counts, per-brand counts, matched keywords, quotes. Counts are DOCUMENTS."""
    res = {}
    for key, label, kind, kws in themes:
        n, brands, kwc, quotes = 0, collections.Counter(), collections.Counter(), []
        for brand, src, date, raw in docs:
            t = norm(raw)
            if not t:
                continue
            h = hits(t, kws)
            if not h:
                continue
            n += 1
            brands[brand] += 1
            for k in h:
                kwc[k] += 1
            if len(quotes) < MAX_QUOTES * 4:
                quotes.append((len(raw), src, quote(raw)))
        # medium-length quotes read best: long enough to carry meaning, short enough to scan
        quotes.sort(key=lambda q: (abs(q[0] - 110), q[2]))
        res[key] = {
            "key": key, "label": label, "kind": kind, "docs": n,
            "brands": dict(sorted(brands.items())),
            "keywords": [{"k": k, "n": c, "loose": k in LOOSE}
                         for k, c in sorted(kwc.items(), key=lambda x: (-x[1], x[0]))],
            "quotes": [{"src": s, "text": q} for _, s, q in quotes[:MAX_QUOTES]],
        }
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    dem, sup = demand_docs(), supply_docs()
    if not dem and not sup:
        print("no social sources on disk — run the pullers first. Nothing written.", file=sys.stderr)
        return 3

    dt, st = tally(dem, DEMAND), tally(sup, SUPPLY)
    nd, ns = len(dem) or 1, len(sup) or 1

    # THE GAP. Share of demand documents raising a theme minus share of supply documents claiming it.
    # Only computed for themes present on BOTH lexicons — otherwise we would be subtracting a number
    # that was never measured, which is worse than not answering.
    shared = sorted(set(dt) & set(st))
    gap = []
    for k in shared:
        d, s = dt[k], st[k]
        d_share, s_share = 100.0 * d["docs"] / nd, 100.0 * s["docs"] / ns
        gap.append({
            "key": k, "label": d["label"],
            "demand_docs": d["docs"], "demand_share_pct": round(d_share, 2),
            "supply_docs": s["docs"], "supply_share_pct": round(s_share, 2),
            "gap_pts": round(d_share - s_share, 2),
            "thin": d["docs"] < MIN_DOCS_FOR_GAP,
        })
    gap.sort(key=lambda g: (-g["gap_pts"], g["key"]))

    # ANSWERED / UNANSWERED — every demand theme against the message(s) that would answer it.
    # This is the marketing read: sort descending and the top rows are what customers raise that
    # nobody is saying anything about.
    answered = []
    for dkey, skeys, note in PAIRS:
        d = dt.get(dkey)
        if not d:
            continue
        s_docs = sum(st[k]["docs"] for k in skeys if k in st)
        d_share = 100.0 * d["docs"] / nd
        s_share = 100.0 * s_docs / ns
        answered.append({
            "demand_key": dkey, "label": d["label"], "kind": d["kind"],
            "answered_by": skeys,
            "answered_by_labels": [st[k]["label"] for k in skeys if k in st],
            "demand_docs": d["docs"], "demand_share_pct": round(d_share, 2),
            "supply_docs": s_docs, "supply_share_pct": round(s_share, 2),
            "unanswered_pts": round(d_share - s_share, 2),
            "no_counterpart": not skeys,
            "thin": d["docs"] < MIN_DOCS_FOR_GAP,
            "note": note,
        })
    answered.sort(key=lambda r: (-r["unanswered_pts"], r["demand_key"]))

    # CTAs — what the supply side asks you to DO.
    # Counted over PAID supply only (ad creatives + promo pages). A lender's organic forum reply
    # saying "call us" is customer SERVICE, not a campaign mechanic, and mixing the two would make
    # a brand that answers its own threads look like it runs a call-to-action strategy. The organic
    # ones are counted separately in ctas_organic so nothing is hidden — that split is the whole
    # point: it is how we can say "nobody in the field runs a chat CTA in paid, and the single
    # conversational invitation anywhere is one of ours, done by hand".
    PAID_SRC = ("google-ads", "promo")
    paid = [d for d in sup if d[1] in PAID_SRC]
    organic = [d for d in sup if d[1] not in PAID_SRC]
    n_paid = len(paid) or 1

    def _cta_rows(docs, denom):
        rows = []
        for key, label, kws in CTAS:
            n, brands = 0, collections.Counter()
            for brand, src, date, raw in docs:
                if hits(norm(raw), kws):
                    n += 1
                    brands[brand] += 1
            rows.append({"key": key, "label": label, "docs": n,
                         "share_pct": round(100.0 * n / denom, 2),
                         "brands": dict(sorted(brands.items()))})
        rows.sort(key=lambda c: (-c["docs"], c["key"]))
        return rows

    ctas = _cta_rows(paid, n_paid)
    ctas_organic = _cta_rows(organic, len(organic) or 1)

    # per-brand demand profile — which objection dominates each lender's own audience
    brands = {}
    for brand, src, date, raw in dem:
        brands.setdefault(brand, {"key": brand, "docs": 0, "themes": collections.Counter()})
        brands[brand]["docs"] += 1
    for k, rec in dt.items():
        for b, c in rec["brands"].items():
            if b in brands:
                brands[b]["themes"][k] += c
    label_of = {k: label for k, label, _, _ in DEMAND}
    profile = []
    for b in sorted(brands):
        r = brands[b]
        top = sorted(r["themes"].items(), key=lambda x: (-x[1], x[0]))[:4]
        profile.append({"brand": b, "docs": r["docs"],
                        "top_themes": [{"key": k, "label": label_of[k], "docs": c,
                                        "share_pct": round(100.0 * c / r["docs"], 1)}
                                       for k, c in top]})
    profile.sort(key=lambda p: (-p["docs"], p["brand"]))

    dates = [d for _, _, d, _ in dem + sup if d]
    doc = {
        "demand": [dt[k] for k in sorted(dt, key=lambda k: (-dt[k]["docs"], k))],
        "supply": [st[k] for k in sorted(st, key=lambda k: (-st[k]["docs"], k))],
        "gap": gap,
        "answered": answered,
        "ctas": ctas,
        "ctas_organic": ctas_organic,
        "brand_profile": profile,
        "meta": {
            "as_of": max(dates) if dates else None,   # newest doc IN THE DATA — never wall clock
            # build_provenance.py scans these four keys (label/source/provenance/generated_by) to
            # classify a layer; without at least one the layer lands in the ledger as UNLABELLED,
            # which is the gap the ledger exists to catch. "ESTIMATED" in the label is deliberate
            # and correct: the counts are measured but the theme buckets are editorial.
            "label": ("Say/hear gap — MEASURED document counts against an ESTIMATED editorial Thai "
                      "phrase list; theme buckets are judgement, not model sentiment."),
            "generated_by": "pipeline/build_social_themes.py",
            "source": ("demand: pantip_threads.json + app_reviews.json + apple_reviews.json + "
                       "youtube_comments.json; supply: google_ads_raw.json + rival_promos.json + "
                       "verified-organisation replies in pantip_threads.json"),
            "demand_docs": len(dem),
            "supply_docs": len(sup),
            "supply_paid_docs": len(paid),
            "supply_organic_docs": len(organic),
            "cta_basis": ("`ctas` counts PAID supply only (ad creatives + promo pages, n=%d) "
                          "because a call to action is a campaign mechanic. `ctas_organic` counts "
                          "the unpaid verified-organisation forum replies (n=%d) separately: a "
                          "support account saying 'call us' is service, not a campaign, and "
                          "blending the two would make a lender that answers its own threads look "
                          "like it runs a CTA strategy." % (len(paid), len(organic))),
            "demand_sources": ["youtube_comments.json (public comments, no author identity stored)",
                               "app_reviews.json (Google Play)", "apple_reviews.json (Apple)",
                               "pantip_threads.json (forum posts + non-org comments; the opening "
                               "post and each reply count as separate documents. Replies badged as "
                               "a verified ORGANISATION are excluded here and counted as supply, so "
                               "a lender answering its own thread cannot inflate customer voice.)"],
            "supply_sources": ["google_ads_raw.json (Google Ads Transparency creatives)",
                               "rival_promos.json (rivals' own promo pages)",
                               "pantip_threads.json (verified-organisation replies only — a lender "
                               "publishing an unpaid message in a public thread)"],
            "cohort_warning": ("Demand documents are NOT interchangeable across sources and brand "
                               "shares must not be compared across a mixed blend. App complaints "
                               "concentrate in app-store reviews and barely appear in YouTube "
                               "comments, so a brand whose corpus is mostly app reviews will always "
                               "look worse on that theme than one whose corpus is mostly comments. "
                               "Compare brands WITHIN a single source (meta.demand_by_source gives "
                               "the denominators). Apple reviews additionally carry no date, so "
                               "their time window is unbounded and unknown."),
            "demand_by_source": _by_source(dem),
            "measured": ("Document COUNTS are MEASURED — each is 'how many documents contain one of "
                         "these published phrases', re-derivable by hand from meta.lexicon."),
            "estimated": ("THEME BUCKETS and the phrase list itself are ESTIMATED editorial "
                          "judgement. A theme absent from the lexicon reads as zero, so absence "
                          "here is not evidence of absence. Nothing is model-sentiment-scored."),
            "matching": ("Substring matching — correct for Thai, which has no word boundaries, but "
                         "short keywords over-match. Those are flagged loose:true and their counts "
                         "are soft upper bounds."),
            "gap_note": ("gap_pts = share of DEMAND documents raising a theme minus share of SUPPLY "
                         "documents claiming it. Positive = customers raise it more than the field "
                         "advertises it. Computed only for themes in BOTH lexicons; thin:true means "
                         "fewer than %d demand documents, so read it as directional only."
                         % MIN_DOCS_FOR_GAP),
            "privacy": ("Text only. No author name, id or handle is read or stored at any stage; "
                        "quotes are short, capped at %d per theme per side, and unattributed."
                        % MAX_QUOTES),
            "lexicon": {
                "demand": {k: kws for k, _, _, kws in DEMAND},
                "supply": {k: kws for k, _, _, kws in SUPPLY},
                "ctas": {k: kws for k, _, kws in CTAS},
                "loose": sorted(LOOSE),
                "pairing": {d: s for d, s, _ in PAIRS},
            },
        },
    }

    blob = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if a.check:
        if not os.path.exists(OUT):
            print("build_social_themes.py --check: %s missing" % OUT, file=sys.stderr)
            return 1
        cur = io.open(OUT, encoding="utf-8").read()
        if cur != blob:
            print("build_social_themes.py --check: social_themes.json drifted", file=sys.stderr)
            return 1
        print("build_social_themes.py --check: OK (byte-exact)")
        return 0

    io.open(OUT, "w", encoding="utf-8", newline="\n").write(blob)
    print("wrote %s" % os.path.relpath(OUT, ROOT))
    print("  demand %d docs / %d themes · supply %d docs / %d themes · %d shared themes"
          % (len(dem), len(dt), len(sup), len(st), len(gap)))
    print("\n  what customers raise that the field does NOT answer (top 5):")
    for r in answered[:5]:
        print("    %-20s demand %5.2f%%  answered %5.2f%%  unanswered %+6.2f pts%s%s"
              % (r["demand_key"], r["demand_share_pct"], r["supply_share_pct"],
                 r["unanswered_pts"], "  NO COUNTERPART" if r["no_counterpart"] else "",
                 "  (thin)" if r["thin"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
