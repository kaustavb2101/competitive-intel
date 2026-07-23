#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
classify_promos_llm.py — promo taxonomy classifier (pull layer, ANY IP; GEMINI_API_KEY primary,
NVIDIA_API_KEY fallback)

Classifies every scraped rival promo/campaign item into a FIXED product / promo-type / audience
taxonomy so the app can render a summarized "promo landscape" (by product, feature, pricing)
instead of raw line items — owner ask 2026-07-21.

  in : source-data/rival_promos.json     MEASURED promo items (pull_rival_promos.py, Thai-IP)
  out: source-data/promo_taxonomy.json   ESTIMATED classifications, cached by item url —
                                         re-runs classify ONLY items not already in the cache
                                         (or whose title changed), so the daily refresh is cheap.

This is a NETWORK script like the other pull_*: it tries the providers in ENDPOINTS in order
(Gemini Flash, then NVIDIA NIM; keys from env or the repo .env — NEVER committed). The
deterministic builder (build_rival_pulse.py) only READS the cached file; it never networks.

  python3 classify_promos_llm.py            # classify new/changed items, update the cache
  python3 classify_promos_llm.py --force    # re-classify everything (taxonomy change etc.)
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_PROMOS = os.path.join(ROOT, "source-data", "rival_promos.json")
OUT = os.path.join(ROOT, "source-data", "promo_taxonomy.json")

# Provider chain: Gemini Flash first (strong Thai, generous free tier — verified on the items the
# NVIDIA 8B misread), NVIDIA NIM 8B as fallback (its bigger siblings queue indefinitely on the
# free tier — verified 2026-07-21, HTTP timeout at 100s on a 5-token prompt).
ENDPOINTS = [
    ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
     "GEMINI_API_KEY", "gemini-2.5-flash"),
    ("https://integrate.api.nvidia.com/v1/chat/completions",
     "NVIDIA_API_KEY", "meta/llama-3.1-8b-instruct"),
]

PRODUCTS = ["title_loan_motorcycle", "title_loan_car", "title_loan_pickup", "title_loan_truck",
            "title_loan_land", "personal_loan", "nano_finance", "hire_purchase",
            "insurance_broking", "corporate_or_ir", "other"]
PROMO_TYPES = ["rate_discount", "cashback", "free_gift", "lucky_draw", "fee_waiver",
               "fast_approval", "credit_line_boost", "refinance_offer", "payment_relief",
               "partnership", "brand_campaign", "corporate_news", "content_marketing", "other"]
AUDIENCES = ["farmers", "riders", "drivers", "sme", "salaried", "general"]

PROMPT = ("""You classify Thai title-lender website items. Many are CSR/IR/corporate news, NOT
promotions. Rules: ESG awards, forums, blood drives, donations, condolences, analyst/IR events,
regulatory notices -> product=corporate_or_ir, promo_type=corporate_news, pricing=null. Blog
articles, tips, buying guides with no concrete offer -> promo_type=content_marketing (product = the
topic's product, else other). Real customer offers get a loan product + promo type; perks with a
partner (fuel, service centers, retail coupons) -> promo_type=partnership or cashback/free_gift as
stated. pricing = the rate/amount stated IN THE TEXT (short string), else null — NEVER invent
pricing. feature = <=8 English words: the selling point.
Insurance offers (พ.ร.บ., ประกันภัยรถ, ประกันชั้น 1/2/3, ต่อประกัน) -> product=insurance_broking;
special price/bundle on insurance -> promo_type=rate_discount or free_gift as stated; insurer or
service-partner tie-ups (FIT AUTO, PTT, retail chains) -> promo_type=partnership.
Vocab: จำนำทะเบียน = title loan; มอเตอร์ไซค์/รถเครื่อง = motorcycle; กระบะ = pickup; โฉนด/ที่ดิน = land;
พ.ร.บ. = compulsory motor insurance.
Example: title=MTC คว้า ESG Ratings ระดับ AA
 -> {"product":"corporate_or_ir","promo_type":"corporate_news","audience":"general","pricing":null,"feature":null}
Example: title=สินเชื่อทะเบียนรถกระบะ ดอกเบี้ย 0.59%
 -> {"product":"title_loan_pickup","promo_type":"rate_discount","audience":"drivers","pricing":"0.59%","feature":"low fixed rate pickup title loan"}
Example: title=ลูกค้ารับส่วนลดเปลี่ยนน้ำมันเครื่องที่ศูนย์บริการพันธมิตร
 -> {"product":"other","promo_type":"partnership","audience":"general","pricing":null,"feature":"partner service center discount for customers"}
Example: title=ต่อ พ.ร.บ. และประกันรถ ราคาพิเศษ
 -> {"product":"insurance_broking","promo_type":"rate_discount","audience":"drivers","pricing":null,"feature":"discounted compulsory motor insurance renewal"}
Reply with COMPACT JSON only, no prose. Keys: product (one of @P), promo_type (one of @T),
audience (one of @A), pricing, feature.

Item: brand=@BRAND | title=@TITLE | detail=@DETAIL"""
          .replace("@P", json.dumps(PRODUCTS))
          .replace("@T", json.dumps(PROMO_TYPES))
          .replace("@A", json.dumps(AUDIENCES)))


def item_prompt(it):
    return (PROMPT.replace("@BRAND", it["brand"]).replace("@TITLE", it["title"])
                  .replace("@DETAIL", it.get("detail") or "-"))


def api_key(name):
    k = os.environ.get(name)
    if not k and os.path.exists(os.path.join(ROOT, ".env")):
        for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
            if line.strip().startswith(name + "="):
                k = line.strip().split("=", 1)[1].strip()
    return k


def call_llm(prompt):
    last_err = None
    for url, key_name, model in ENDPOINTS:
        key = api_key(key_name)
        if not key:
            continue
        body = {"model": model, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000, "temperature": 0}
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode("utf-8"))
            return d["choices"][0]["message"]["content"], model
        except Exception as e:  # timeout / 4xx / queue-cold — fall through to the next provider
            last_err = e
    raise RuntimeError("all providers failed (need GEMINI_API_KEY or NVIDIA_API_KEY): %s" % last_err)


def parse_cls(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    pricing = d.get("pricing")
    feature = d.get("feature")
    return {
        "product": d.get("product") if d.get("product") in PRODUCTS else "other",
        "promo_type": d.get("promo_type") if d.get("promo_type") in PROMO_TYPES else "other",
        "audience": d.get("audience") if d.get("audience") in AUDIENCES else "general",
        "pricing": (str(pricing)[:60] if pricing not in (None, "", "null") else None),
        "feature": (str(feature)[:80] if feature else None),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-classify every item")
    args = ap.parse_args()

    if not os.path.exists(IN_PROMOS):
        sys.exit("classify_promos_llm.py: run pull_rival_promos.py first")
    items = json.load(open(IN_PROMOS, encoding="utf-8")).get("items", [])

    cache = {}
    if os.path.exists(OUT) and not args.force:
        cache = json.load(open(OUT, encoding="utf-8")).get("items", {})

    done = skipped = failed = 0
    for it in items:
        url = it["url"]
        hit = cache.get(url)
        if hit and hit.get("title") == it["title"]:
            skipped += 1
            continue
        text, model = call_llm(item_prompt(it))
        cls = parse_cls(text)
        if not cls:
            failed += 1
            print("  PARSE-FAIL %s" % url)
            continue
        cache[url] = dict(cls, title=it["title"], brand=it["brand"], model=model,
                          classified_at=datetime.date.today().isoformat())
        done += 1
        print("  %s %-22s %-16s %s" % (it["brand"], cls["product"], cls["promo_type"],
                                       (cls["pricing"] or "")))

    live_urls = {it["url"] for it in items}
    cache = {u: c for u, c in cache.items() if u in live_urls}   # drop items gone from the feed

    obj = {"meta": {
        "generated_by": "pipeline/classify_promos_llm.py",
        "label": "ESTIMATED — LLM-classified taxonomy (NVIDIA NIM, models in items[].model) over "
                 "MEASURED promo titles from the rivals' own sites. Enums fixed in the script.",
        "products": PRODUCTS, "promo_types": PROMO_TYPES, "audiences": AUDIENCES,
        "updated": datetime.date.today().isoformat(),
    }, "items": cache}
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    print("wrote %s — %d classified now, %d cached, %d parse-failures, %d total"
          % (OUT, done, skipped, failed, len(cache)))


if __name__ == "__main__":
    main()
