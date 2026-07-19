#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rival_pulse.py — RIVAL PULSE (objective #2): promotions the competitors are running right now
+ measured customer sentiment for their apps AND our own, projected for the app.

  in : source-data/rival_promos.json   MEASURED promo/campaign items from the rivals' own sites
                                        (pull_rival_promos.py · Thai-IP pull, first_seen tracked)
       source-data/app_reviews.json    MEASURED Google Play ratings + newest reviews, 5 apps incl.
                                        AutoX's own เงินไชโย (pull_app_reviews.py · any IP)
  out: platform/data/rival_pulse.json  sentiment ladder (score, detractor share, 90-day trend,
                                        detractor themes, dev-reply rate, quotes) + promo feed

Provenance: stars/histograms/dates/reply-rates and promo titles/dates are MEASURED (public store
pages + the rivals' own websites). The detractor THEME buckets are ESTIMATED — a transparent Thai
keyword lexicon over the stored 1–2★ reviews (lexicon carried in meta so it can be audited).

Determinism: the 90-day trend window anchors on the NEWEST REVIEW DATE IN THE DATA (never wall
clock), so the output is byte-stable for a given pair of inputs. `--check` byte-compares; SKIPs
(exit 3) if both inputs are absent.

  python3 build_rival_pulse.py
  python3 build_rival_pulse.py --check
"""
import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_PROMOS = os.path.join(ROOT, "source-data", "rival_promos.json")
IN_REVIEWS = os.path.join(ROOT, "source-data", "app_reviews.json")
OUT = os.path.join(ROOT, "platform", "data", "rival_pulse.json")

# ESTIMATED theme lexicon — Thai keywords bucketed over 1–2★ reviews. Transparent + auditable.
THEMES = [
    ("app-reliability", "แอปล่ม / เข้าไม่ได้",
     ["เข้าไม่ได้", "ล่ม", "หน้าจอดำ", "โหลดใหม่", "ปิดปรับปรุง", "อัพเดท", "อัปเดต",
      "ใช้งานไม่ได้", "เด้ง", "ค้าง", "otp", "โอทีพี"]),
    ("approval-speed", "อนุมัติช้า / รอนาน",
     ["อนุมัติช้า", "รอนาน", "ไม่อนุมัติ", "หลายวัน", "ช้า"]),
    ("interest-cost", "ดอกเบี้ย / ค่าธรรมเนียม",
     ["ดอกเบี้ย", "ดอกแพง", "แพง", "ค่าธรรมเนียม", "ค่าปรับ", "ค่างวด"]),
    ("service-staff", "บริการ / พนักงาน / สาขา",
     ["พนักงาน", "บริการ", "สาขา", "call center", "คอลเซ็นเตอร์", "ติดต่อไม่ได้", "ไม่รับสาย"]),
    ("trust-collections", "ทวงถาม / ความเชื่อมั่น",
     ["ทวง", "หลอก", "โกง", "ข่มขู่", "ยึดรถ", "มิจฉาชีพ"]),
]


def _sentiment(doc):
    apps = doc.get("apps", {})
    all_dates = [r["at"] for a in apps.values() for r in a.get("reviews_store", []) if r.get("at")]
    if not all_dates:
        return [], None
    anchor = max(all_dates)                       # newest review date IN THE DATA — never wall clock
    cutoff = (datetime.date.fromisoformat(anchor) - datetime.timedelta(days=90)).isoformat()

    rows = []
    for brand, a in apps.items():
        st, store = a.get("stats", {}), a.get("reviews_store", [])
        hist = st.get("histogram") or [0] * 5
        tot = sum(hist)
        recent = [r for r in store if (r.get("at") or "") >= cutoff]
        rec_scores = [r["score"] for r in recent]
        low = [r for r in store if r["score"] <= 2]
        themes = []
        for key, label, kws in THEMES:
            n = sum(1 for r in low if any(k in (r["content"] or "").lower() for k in kws))
            if n:
                themes.append({"key": key, "label": label, "n": n})
        themes.sort(key=lambda t: -t["n"])
        quotes = sorted((r for r in low if len(r.get("content") or "") >= 20),
                        key=lambda r: (-r.get("thumbs", 0), r.get("at") or ""),)[:2]
        rows.append({
            "brand": brand, "name": a.get("name"), "own": bool(a.get("own")),
            "app_id": a.get("appId"),
            "score": round(st["score"], 2) if st.get("score") is not None else None,
            "ratings": st.get("ratings"), "installs": st.get("installs"),
            "detractor_pct": round(hist[0] * 100.0 / tot, 1) if tot else None,       # lifetime 1★
            "promoter_pct": round(hist[4] * 100.0 / tot, 1) if tot else None,        # lifetime 5★
            "recent90": {
                "n": len(recent),
                "avg": round(sum(rec_scores) / len(rec_scores), 2) if rec_scores else None,
                "low_share_pct": round(sum(1 for s in rec_scores if s <= 2) * 100.0 /
                                       len(rec_scores), 1) if rec_scores else None,
            },
            "reply_rate_pct": round(sum(1 for r in store if r.get("replied")) * 100.0 /
                                    len(store), 1) if store else None,
            "themes": themes[:3],
            "quotes": [{"at": q.get("at"), "score": q["score"],
                        "text": (q["content"] or "")[:140]} for q in quotes],
        })
    rows.sort(key=lambda r: -(r["score"] or 0))
    return rows, anchor


def build():
    promos_doc = json.load(open(IN_PROMOS, encoding="utf-8")) if os.path.exists(IN_PROMOS) else None
    reviews_doc = json.load(open(IN_REVIEWS, encoding="utf-8")) if os.path.exists(IN_REVIEWS) else None

    sent, anchor = _sentiment(reviews_doc) if reviews_doc else ([], None)

    promo_items, promo_meta = [], {}
    if promos_doc:
        promo_meta = promos_doc.get("meta", {})
        pulled = promo_meta.get("pulled_at")
        for it in promos_doc.get("items", []):
            promo_items.append({
                "brand": it["brand"], "kind": it["kind"], "title": it["title"],
                "detail": it.get("detail"), "date": it.get("date"), "url": it["url"],
                "first_seen": it.get("first_seen"),
                "is_new": it.get("first_seen") == pulled,
            })

    headline = ""
    own = next((r for r in sent if r["own"]), None)
    rivals = [r for r in sent if not r["own"] and r["score"] is not None]
    if own and rivals:
        best = rivals[0]
        gap = round((best["score"] or 0) - (own["score"] or 0), 2)
        headline = ("Our own เงินไชโย app rates %.2f★ — %.2f★ behind the best rival (%s %.2f★); "
                    "%s%% of our last-90-day reviews are 1–2★"
                    % (own["score"], gap, best["brand"], best["score"],
                       own["recent90"]["low_share_pct"]))
        if own["themes"]:
            headline += ", led by %s" % own["themes"][0]["label"]
        headline += "."
    if promo_items:
        n_new = sum(1 for p in promo_items if p["is_new"])
        headline += (" %d rival promotions/campaigns tracked from the rivals' own sites"
                     % len(promo_items))
        headline += (" (%d new this pull)." % n_new) if n_new else "."

    return {
        "meta": {
            "title": "Rival pulse — live promotions + measured customer sentiment (obj #2)",
            "generated_by": "pipeline/build_rival_pulse.py",
            "label": "MEASURED — Google Play star histograms/dated reviews (5 apps incl. our own "
                     "เงินไชโย) + promo/campaign items from the rivals' own websites. Detractor "
                     "THEME buckets are ESTIMATED (transparent Thai keyword lexicon over stored "
                     "1–2★ reviews; lexicon in meta.theme_lexicon).",
            "sentiment_anchor": anchor,
            "promos_pulled_at": promo_meta.get("pulled_at"),
            "promos_coverage_note": promo_meta.get("coverage_note"),
            "theme_lexicon": {k: kws for k, _, kws in THEMES},
            "note_installs": "installs is Play's public bracket (e.g. 500,000+), not an exact count.",
        },
        "headline": headline,
        "sentiment": sent,
        "promos": promo_items,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN_PROMOS) and not os.path.exists(IN_REVIEWS):
        if args.check:
            print("build_rival_pulse.py --check: SKIP (no rival_promos/app_reviews source — network pulls)")
            sys.exit(3)
        sys.exit("build_rival_pulse.py: run pull_rival_promos.py / pull_app_reviews.py first")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_rival_pulse.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_rival_pulse.py --check: drifted — re-run the builder.")
        print("build_rival_pulse.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d apps on the sentiment ladder, %d promo items"
          % (OUT, len(obj["sentiment"]), len(obj["promos"])))
    print("headline:", obj["headline"])


if __name__ == "__main__":
    main()
