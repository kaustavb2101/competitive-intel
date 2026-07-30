#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
spike_meta_ads.py — PROBE: is Meta's Ad Library a usable rival-ad source for THAILAND?

  ####################################################################################
  #  ANSWERED 2026-07-30: NO. Meta's Ad Library does NOT cover Thai commercial ads.  #
  #  Kept as the evidence trail + a re-test if Meta ever extends coverage to TH.     #
  ####################################################################################

  Measured with a live `ads_read` token:
   * `ad_type=CREDIT_ADS` and `FINANCIAL_PRODUCTS_AND_SERVICES_ADS` return
     HTTP 400 "invalid for your selected ad_reached_countries: TH" — yet BOTH return
     50 ads for US / DE / GB. Meta's financial-ad transparency slice is jurisdictional
     and Thailand is outside it. That is the whole finding; no query can route around it.
   * `ad_type=ALL` for TH answers, and `search_terms` genuinely works (a nonsense term
     returns 0; "pizza" returns 50 ads actually about pizza; two terms share 0 rows).
   * But EVERY title-loan probe returns 0 RELEVANT ads: `จำนำทะเบียนรถ` (vehicle-title
     pawn) returns 0 rows outright; `ทะเบียนรถ`, `สินเชื่อทะเบียนรถ`, `กู้เงิน`,
     `ดอกเบี้ยต่อเดือน`, `ติดล้อ`, `เงินด่วน` each return 50 rows with 0 relevant.
     All four rivals + our own `เงินไชโย`: 0 relevant.
   * The apparent brand "hits" are Thai NAME COLLISIONS — `ศรีสวัสดิ์` is a common Thai
     personal name, so it matches politicians' pages (e.g. an MP from Saraburi), not the
     lender. This is why the first version of this spike wrongly printed "USABLE": it
     counted rows, not rows that mention the brand. Verdict logic below now counts
     relevance, so a future re-run cannot repeat that mistake.
   * `GET /search?type=page` returns `{"data":[]}` on a standard token, so the
     `search_page_ids` fallback is not reachable either without App Review.

  Do NOT answer this with scraping. An empty official source is a finding. See the
  reachable alternatives noted at the bottom of this file.

This is a spike, not a pipeline stage. It answers one question and writes nothing into
platform/data: does the official Ad Library API return title-lender ads for Thailand, with
which ad_type, and are spend/impressions populated? If the answer is yes this becomes
pull_rival_ads.py (+ a deterministic build_rival_ads.py with --check, per house style).

WHY OFFICIAL, NOT SCRAPING: the Ad Library is a superset of what a page-scraper could see
(every ad a rival runs, with delivery dates and often reach/spend bands), it is public by
regulation, and it works from ANY IP — so unlike pull_rival_promos.py it runs in CI instead
of depending on the owner's Thai laptop. No login, no ToS breach, no PDPA exposure: the API
returns advertiser-level marketing copy, not personal data.

  in : META_ADS_TOKEN in the environment or in .env (NEVER committed; .env is gitignored)
  out: stdout verdict + raw JSON under source-data/raw/meta_ads/ (gitignored, for eyeballing)

  python3 spike_meta_ads.py                 # probe ad_types, then each rival brand
  python3 spike_meta_ads.py --brand Tidlor  # one brand only
  python3 spike_meta_ads.py --country TH,SG # widen the country filter

Get a token: developers.facebook.com -> create an app -> Graph API Explorer -> permission
`ads_read`. Non-political ad access may additionally require Identity Verification; if so the
API says exactly that and this spike prints Meta's own message verbatim — that message IS the
finding, so do not paper over it.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "source-data", "raw", "meta_ads")
API = "https://graph.facebook.com/v21.0/ads_archive"

# The Thai title-loan field: our four tracked rivals plus our own brand as a control. Thai and
# roman spellings both, because advertisers register pages under either.
BRANDS = [
    ("Srisawad",  ["ศรีสวัสดิ์", "Srisawad"]),
    ("Muangthai", ["เมืองไทยแคปปิตอล", "Muangthai Capital", "MTC"]),
    ("Tidlor",    ["เงินติดล้อ", "Tidlor"]),
    ("Heng",      ["เฮงลิสซิ่ง", "Heng Leasing"]),
    ("AutoX",     ["เงินไชโย", "Ngern Chaiyo", "AutoX"]),      # our own — the control
]

# Which archive slice actually contains commercial ads varies by jurisdiction; that is the
# single biggest unknown this spike exists to settle. Probe in order and report each verdict.
AD_TYPES = ["ALL", "FINANCIAL_PRODUCTS_AND_SERVICES_ADS", "CREDIT_ADS",
            "POLITICAL_AND_ISSUE_ADS"]

FIELDS = ",".join([
    "id", "page_id", "page_name", "ad_creation_time",
    "ad_delivery_start_time", "ad_delivery_stop_time",
    "ad_creative_bodies", "ad_creative_link_titles",
    "publisher_platforms", "languages", "impressions", "spend", "currency",
    "ad_snapshot_url",
])


def load_token(explicit=None):
    if explicit:
        return explicit
    for k in ("META_ADS_TOKEN", "META_ADS_ACCESS_TOKEN", "FB_ADS_TOKEN"):
        if os.environ.get(k):
            return os.environ[k]
    for env in (os.path.join(ROOT, ".env"), os.path.join(os.path.dirname(ROOT), ".env")):
        if not os.path.exists(env):
            continue
        try:
            for line in open(env, encoding="utf-8", errors="ignore"):
                line = line.strip()
                if line.startswith(("META_ADS_TOKEN=", "META_ADS_ACCESS_TOKEN=", "FB_ADS_TOKEN=")):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
    return None


def call(token, **params):
    """-> (payload, error_string). Meta's own error text is the finding; never swallow it."""
    q = {"access_token": token, "fields": FIELDS, "limit": "50"}
    q.update({k: v for k, v in params.items() if v is not None})
    url = API + "?" + urllib.parse.urlencode(q, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": "autox-adlib-spike/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            err = (json.loads(body).get("error") or {})
            msg = err.get("message") or body[:300]
            code = err.get("code")
            sub = err.get("error_user_msg")
            return None, "HTTP %s code=%s: %s%s" % (e.code, code, msg,
                                                    " | " + sub if sub else "")
        except ValueError:
            return None, "HTTP %s: %s" % (e.code, body[:300])
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, "network/parse: %s" % e


def relevant(ad, terms):
    """Does this row actually MENTION the brand, or is it a name collision?

    Thai brand names double as common personal names (ศรีสวัสดิ์, ไชโย), so a raw row
    count says nothing. Only rows whose page name or creative copy contain a search
    term are evidence that the advertiser is in the archive.
    """
    blob = ((ad.get("page_name") or "") + " " +
            " ".join(ad.get("ad_creative_bodies") or []) + " " +
            " ".join(ad.get("ad_creative_link_titles") or [])).lower()
    return any(t.lower() in blob for t in terms)


def summarize(ads, terms=()):
    """Aggregate shape only — what a builder could actually render."""
    pages, plats, starts, langs = {}, {}, [], {}
    n_spend = n_impr = 0
    n_rel = sum(1 for a in ads if relevant(a, terms)) if terms else 0
    for a in ads:
        pn = a.get("page_name") or "(unnamed)"
        pages[pn] = pages.get(pn, 0) + 1
        for p in (a.get("publisher_platforms") or []):
            plats[p] = plats.get(p, 0) + 1
        for l in (a.get("languages") or []):
            langs[l] = langs.get(l, 0) + 1
        if a.get("ad_delivery_start_time"):
            starts.append(a["ad_delivery_start_time"][:10])
        if a.get("spend"):
            n_spend += 1
        if a.get("impressions"):
            n_impr += 1
    return {"n": len(ads), "n_relevant": n_rel,
            "pages": pages, "platforms": plats, "languages": langs,
            "first_seen": min(starts) if starts else None,
            "last_seen": max(starts) if starts else None,
            "with_spend": n_spend, "with_impressions": n_impr}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--token")
    ap.add_argument("--country", default="TH", help="comma-separated ISO codes (default TH)")
    ap.add_argument("--brand", help="probe a single brand key from BRANDS")
    ap.add_argument("--status", default="ALL", choices=["ALL", "ACTIVE", "INACTIVE"])
    a = ap.parse_args()

    token = load_token(a.token)
    if not token:
        print("NO TOKEN — nothing was called.\n")
        print("  set it (never commit it; .env is gitignored):")
        print("     echo 'META_ADS_TOKEN=<token>' >> .env")
        print("  get one: developers.facebook.com -> app -> Graph API Explorer -> `ads_read`.")
        print("  Commercial (non-political) ad access may also need Identity Verification.")
        return 2

    countries = [c.strip().upper() for c in a.country.split(",") if c.strip()]
    os.makedirs(RAW, exist_ok=True)
    print("Meta Ad Library spike — countries=%s status=%s\n" % (",".join(countries), a.status))

    # ── phase 1: which ad_type slice responds at all for this country? ──────────
    print("PHASE 1 — which ad_type returns data for %s?" % ",".join(countries))
    usable = []
    for t in AD_TYPES:
        payload, err = call(token, search_terms="loan", ad_type=t,
                            ad_reached_countries=json.dumps(countries),
                            ad_active_status=a.status)
        if err:
            print("  %-38s ERROR  %s" % (t, err))
        else:
            n = len(payload.get("data") or [])
            print("  %-38s ok, %d ad(s) on a generic 'loan' probe" % (t, n))
            usable.append((t, n))
        time.sleep(1)
    if not usable:
        print("\nVERDICT: no ad_type is queryable with this token. The errors above are Meta's")
        print("own words — usually a missing `ads_read` scope or pending Identity Verification.")
        print("Fix the token/verification and re-run; do NOT fall back to scraping.")
        return 1

    best = max(usable, key=lambda kv: kv[1])[0]
    print("\n  -> using ad_type=%s for the brand sweep" % best)

    # ── phase 2: per-brand sweep ────────────────────────────────────────────────
    todo = [b for b in BRANDS if (not a.brand or b[0].lower() == a.brand.lower())]
    if not todo:
        print("unknown --brand; known: %s" % ", ".join(b[0] for b in BRANDS))
        return 2
    print("\nPHASE 2 — per-brand sweep (ad_type=%s)" % best)
    results, grand = {}, 0
    for key, terms in todo:
        got, seen = [], set()
        for term in terms:
            payload, err = call(token, search_terms=term, ad_type=best,
                                ad_reached_countries=json.dumps(countries),
                                ad_active_status=a.status)
            if err:
                print("  %-10s %-22s ERROR %s" % (key, term, err))
                continue
            for ad in (payload.get("data") or []):
                if ad.get("id") not in seen:
                    seen.add(ad.get("id"))
                    got.append(ad)
            time.sleep(1)
        s = summarize(got, terms)
        results[key] = s
        # count only rows that MENTION the brand — raw rows are name-collision noise
        grand += s["n_relevant"]
        top = sorted(s["pages"].items(), key=lambda kv: -kv[1])[:3]
        print("  %-10s %3d rows / %3d RELEVANT | pages: %s | %s..%s | spend:%d impr:%d"
              % (key, s["n"], s["n_relevant"],
                 ", ".join("%s(%d)" % p for p in top) or "-",
                 s["first_seen"] or "?", s["last_seen"] or "?",
                 s["with_spend"], s["with_impressions"]))
        if got:
            with open(os.path.join(RAW, "%s.json" % key), "w", encoding="utf-8") as f:
                json.dump(got, f, ensure_ascii=False, indent=1)

    # ── verdict ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 68)
    rows = sum(r["n"] for r in results.values())
    if grand == 0:
        print("VERDICT: NOT USABLE for %s. The API answered and returned %d row(s), but"
              % (",".join(countries), rows))
        print("ZERO of them actually mention any tracked brand — they are name-collision")
        print("noise (Thai brand names double as common personal names).")
        print("Confirmed structural cause: CREDIT_ADS / FINANCIAL_PRODUCTS_AND_SERVICES_ADS")
        print("are rejected as 'invalid' for TH while returning data for US/DE/GB — Meta's")
        print("financial-ad transparency slice is jurisdictional and excludes Thailand.")
        print("Do NOT substitute scraping: an empty official source is a finding, not a")
        print("reason to take on ToS and PDPA risk. Reachable alternatives instead:")
        print("  - build_rival_pulse.py (SHIPPING) — Google Play ratings/reviews, any IP")
        print("  - pull_rival_promos.py (SHIPPING) — rivals' own promo pages, Thai IP")
        print("  - YouTube Data API v3 — official free quota, marketing cadence, any IP")
        print("  - SET quarterly filings (TIDLOR/MTC/SAWAD/HENG are all listed) — rival")
        print("    branch counts, loan yields and NPL: far better objective-#2 evidence")
        print("    than ad copy, and it is official public disclosure")
    else:
        anyspend = sum(r["with_spend"] for r in results.values())
        print("VERDICT: USABLE — %d ads that actually name a tracked brand (of %d rows)."
              % (grand, rows))
        print("Spend/impression bands present on %d ads%s."
              % (anyspend, "" if anyspend else " (so treat volume+cadence as the metric,"
                                               " not budget)"))
        print("Next: promote to pull_rival_ads.py + build_rival_ads.py (--check, aggregate-")
        print("only: per-brand ad counts, cadence, product mix, first/last seen) -> #acq.")
    print("raw JSON (gitignored): %s" % RAW)
    return 0 if grand else 1


if __name__ == "__main__":
    sys.exit(main())
