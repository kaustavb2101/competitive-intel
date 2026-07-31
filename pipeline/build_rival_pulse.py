#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rival_pulse.py — RIVAL PULSE (objective #2): promotions the competitors are running right now
+ measured customer sentiment for their apps AND our own, projected for the app.

  in : source-data/rival_promos.json   MEASURED promo/campaign items from the rivals' own sites
                                        (pull_rival_promos.py · Thai-IP pull, first_seen tracked)
       source-data/app_reviews.json    MEASURED Google Play ratings + newest reviews, 5 apps incl.
                                        AutoX's own เงินไชโย (pull_app_reviews.py · any IP)
       source-data/promo_taxonomy.json ESTIMATED LLM product/type/audience classification per promo
                                        (classify_promos_llm.py · NVIDIA NIM; optional — the promo
                                        landscape section degrades to absent when this file is)
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
IN_APPLE = os.path.join(ROOT, "source-data", "apple_reviews.json")

# An app mean below this many ratings is noise, not a signal: on the Apple TH storefront the
# nominal "best" title rival is Saksiam at 4.67 stars from NINE ratings. Such rows are still
# shown (their absence would be its own distortion) but are never ranked or compared against.
MIN_RATINGS = 100
IN_TAX = os.path.join(ROOT, "source-data", "promo_taxonomy.json")
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


def _ios(doc):
    """The iOS half of app sentiment — deliberately a SMALLER shape than the Play ladder.

    Apple's public feed carries no review date, no star histogram and no developer replies, so
    the 90-day trend, the lifetime 1★/5★ shares and the reply rate simply do not exist here and
    are not faked. Star shares are computed over the stored REVIEW SAMPLE and labelled as such —
    they are not the lifetime population Play's histogram gives.

    `averageUserRatingForCurrentVersion` is deliberately NOT carried: on the TH storefront Apple
    returns it byte-identical to the lifetime average for all 16 tracked apps (verified
    2026-07-31), so a "current build vs history" delta would read as a measured 0.00 change when
    in truth there is no version-level data at all. Do not re-add it without re-checking.

    Any COMPARATIVE claim is restricted to apps with >= MIN_RATINGS ratings. Without that floor
    the "best rival" is Saksiam at 4.67★ — from nine ratings — which would have told Kaustav he
    trails a competitor on what is statistically noise.
    """
    apps = doc.get("apps", {})
    if not apps:
        return [], {}
    rows = []
    for brand, a in apps.items():
        st, store = a.get("stats", {}), a.get("reviews_store", [])
        scores = [r["score"] for r in store if r.get("score") is not None]
        low = [r for r in store if (r.get("score") or 5) <= 2]
        themes = []
        for key, label, kws in THEMES:
            n = sum(1 for r in low if any(k in ((r.get("content") or "") +
                                                " " + (r.get("title") or "")).lower()
                                          for k in kws))
            if n:
                themes.append({"key": key, "label": label, "n": n})
        themes.sort(key=lambda t: (-t["n"], t["key"]))
        quotes = sorted((r for r in low if len(r.get("content") or "") >= 20),
                        key=lambda r: (-(r.get("votes") or 0), r.get("id") or ""))[:2]
        life, nrat = st.get("score"), st.get("ratings") or 0
        rows.append({
            "brand": brand, "name": a.get("name"), "own": bool(a.get("own")),
            "cohort": a.get("cohort"), "apple_id": a.get("apple_id"),
            "score": round(life, 2) if life is not None else None,
            "ratings": st.get("ratings"),
            # too few ratings for the mean to carry meaning — shown, never ranked or compared
            "thin": nrat < MIN_RATINGS,
            "sample": {
                "n": len(scores),
                "avg": round(sum(scores) / len(scores), 2) if scores else None,
                "low_share_pct": (round(sum(1 for s in scores if s <= 2) * 100.0 / len(scores), 1)
                                  if scores else None),
            },
            "released": st.get("released"),
            "app_updated": st.get("app_updated"),
            "themes": themes[:3],
            "quotes": [{"score": q.get("score"), "title": q.get("title"),
                        "text": (q.get("content") or "")[:140]} for q in quotes],
        })
    # title operators first (comparable to our book), then the digital cohort; score desc within
    rows.sort(key=lambda r: (r["cohort"] != "title", r["thin"], -(r["score"] or 0), r["brand"]))
    return rows, doc.get("meta", {})


def build():
    promos_doc = json.load(open(IN_PROMOS, encoding="utf-8")) if os.path.exists(IN_PROMOS) else None
    reviews_doc = json.load(open(IN_REVIEWS, encoding="utf-8")) if os.path.exists(IN_REVIEWS) else None

    sent, anchor = _sentiment(reviews_doc) if reviews_doc else ([], None)

    apple_doc = json.load(open(IN_APPLE, encoding="utf-8")) if os.path.exists(IN_APPLE) else None
    ios, ios_meta = _ios(apple_doc) if apple_doc else ([], {})

    tax_doc = json.load(open(IN_TAX, encoding="utf-8")) if os.path.exists(IN_TAX) else None
    tax = (tax_doc or {}).get("items", {})

    promo_items, promo_meta = [], {}
    if promos_doc:
        promo_meta = promos_doc.get("meta", {})
        pulled = promo_meta.get("pulled_at")
        for it in promos_doc.get("items", []):
            row = {
                "brand": it["brand"], "kind": it["kind"], "title": it["title"],
                "detail": it.get("detail"), "date": it.get("date"), "url": it["url"],
                "first_seen": it.get("first_seen"),
                "is_new": it.get("first_seen") == pulled,
            }
            c = tax.get(it["url"])
            if c and c.get("title") == it["title"]:      # classification is for THIS title
                row["cls"] = {"product": c["product"], "promo_type": c["promo_type"],
                              "audience": c["audience"], "pricing": c.get("pricing"),
                              "feature": c.get("feature")}
            promo_items.append(row)

    # --- promo landscape: the summarized by-product view (ESTIMATED classification over
    #     MEASURED items); absent when classify_promos_llm.py hasn't run ---
    landscape = None
    classified = [p for p in promo_items if p.get("cls")]
    if classified:
        prods = {}
        for p in classified:
            prods.setdefault(p["cls"]["product"], []).append(p)
        by_product = []
        for prod, items in sorted(prods.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            by_product.append({"product": prod, "n": len(items), "items": [
                {"brand": p["brand"], "title": p["title"], "url": p["url"],
                 "date": p.get("date"), "is_new": p["is_new"],
                 "promo_type": p["cls"]["promo_type"], "pricing": p["cls"]["pricing"],
                 "feature": p["cls"]["feature"], "audience": p["cls"]["audience"]}
                for p in sorted(items, key=lambda x: (x["brand"], x.get("date") or "", x["url"]))]})
        type_counts = {}
        for p in classified:
            type_counts[p["cls"]["promo_type"]] = type_counts.get(p["cls"]["promo_type"], 0) + 1
        landscape = {
            "by_product": by_product,
            "type_counts": dict(sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
            "n_classified": len(classified), "n_total": len(promo_items),
            "model_note": (tax_doc or {}).get("meta", {}).get("label"),
        }

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
        "ios": ios,
        "ios_meta": {
            "store": ios_meta.get("store"),
            "pulled_at": ios_meta.get("pulled_at"),
            "caveat": ios_meta.get("caveat"),
            "cohorts": ios_meta.get("cohorts"),
            "excluded": ios_meta.get("excluded"),
        } if ios else None,
        "promos": promo_items,
        "promo_landscape": landscape,
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
