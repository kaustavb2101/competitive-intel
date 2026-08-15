#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pull_collateral_census.py — multi-venue used-collateral price census.

WHY
---
AutoX lends against vehicles, but nothing in the platform says what any specific vehicle is worth.
The only anchor is the BoT UVPI (EC_EI_040) — monthly, national, aggregate, and carrying just three
series: car, truck, overall. There is NO motorcycle series in it, and motorcycles are the single
largest collateral type in the book at 127,628 accounts. A third of the book is carried on an
appraised value with nothing measured to check it against.

This pulls the venues that publish the missing prices, and pools them: several venues per make/model/
year gives a DISTRIBUTION rather than one number, and the retail-vs-auction gap is the recovery
corridor that should be setting LTV.

VENUES (reachability measured 2026-08-09, from a Thai IP and from a US Azure runner)
  one2car    RETAIL ask, cars/pickups/vans. Thai IP ONLY — a US datacenter gets 403 Cloudflare on
             every path but robots.txt. Enumerated from the sitemap the site advertises in its own
             robots.txt; price read from the schema.org offers block, which is published for search
             engines in cleartext. The on-page data-price attribute is font-ciphered and is NOT used.
  auct       AUCTION reserve + realised, cars AND motorcycles, ~2 years of archive. ANY IP incl. CI.
  kaidee     RETAIL ask, ~11 fully structured ads per category page (brand/model/submodel/year/
             mileage/fuel/transmission). ANY IP.
  truck2hand RETAIL ask AND SOLD, ~100 items per category page. The only venue that prices trucks,
             buses, heavy plant and AGRICULTURAL MACHINERY — the 4,600 tractor accounts in the book
             have no anchor anywhere else. ANY IP.
  taladrod   RETAIL ask plus the field nothing else publishes: a PREVIOUS asking price, i.e. which
             listings have been marked down. ANY IP. NOT the ราคากลาง price board — that renders from
             /api/, which their robots.txt disallows; the classifieds search renders server-side.

PDPA. Three of these venues attach a private seller to every vehicle, so two defences run on every
record and both are load-bearing. (1) A per-venue strict ALLOWLIST, never a denylist, keeps
structured identity off disk — names, phones, emails, LINE ids, avatars, member ids, and on the
auction feed the chassis/engine/plate numbers and rival lenders' contract numbers. (2) _scrub()
handles what an allowlist structurally cannot: identifiers that sellers TYPE INTO free text. Both
were written against measured leaks, not hypothetical ones — 23 of 1,112 truck2hand ad titles
carried a mobile number, and a kaidee title carried a full licence plate.

POLITENESS IS LOAD-BEARING, NOT DECORATION. The fetchers are capped, spaced, and resumable on
purpose: one2car rate-limited a bare second request during development, and a puller that is impolite
simply stops returning data. Everything is fetched with --compressed (1.22 MB -> 244 KB per page,
measured), which is a 5x cut in transfer for both sides.

Writes JSONL incrementally so a run can be killed and resumed without refetching, and so a partial
harvest is still usable. Network-bound and NOT part of the determinism gate — like every other
pull_*.py, its output is an input.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTDIR = os.path.join(ROOT, "source-data", "census")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

# urllib gets 403 where curl gets 200 — the TLS fingerprint differs. Measured, not assumed, so the
# fetcher shells out rather than using a Python HTTP client.
def fetch(url, timeout=40, retries=2):
    for attempt in range(retries + 1):
        try:
            p = subprocess.run(
                ["curl", "-sL", "--compressed", "--max-time", str(timeout),
                 "-A", UA, "-H", "Accept-Language: th,en;q=0.9", url],
                capture_output=True, timeout=timeout + 15)
            body = p.stdout.decode("utf-8", "replace")
            if body and "Just a moment" not in body and len(body) > 2000:
                return body
            if "Just a moment" in body:
                time.sleep(5 * (attempt + 1))     # challenged -> back off hard, do not hammer
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def enc(url):
    """Percent-encode the Thai path segments; these URLs are full of them."""
    q = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((q.scheme, q.netloc, urllib.parse.quote(q.path), q.query, ""))


# ---------------------------------------------------------------- one2car
SITEMAPS = ["https://www.one2car.com/sitemap/listing_details_%d.xml.gz" % i for i in (1, 2, 3, 4)]


def one2car_urls(limit):
    """Listing URLs from the sitemap index the site advertises in robots.txt."""
    urls = []
    for sm in SITEMAPS:
        if len(urls) >= limit:
            break
        try:
            p = subprocess.run(["curl", "-sL", "--max-time", "90", "-A", UA, sm],
                               capture_output=True, timeout=120)
            raw = gzip.decompress(p.stdout).decode("utf-8", "replace")
        except Exception as exc:
            print("  ! sitemap %s failed: %s" % (sm.rsplit("/", 1)[-1], exc), file=sys.stderr)
            continue
        got = re.findall(r"<loc>([^<]+)</loc>", raw)
        print("  sitemap %-26s %6d urls" % (sm.rsplit("/", 1)[-1], len(got)))
        urls.extend(got)
    return urls[:limit]


LD = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def one2car_parse(html, url):
    m = LD.search(html)
    if not m:
        return None
    try:
        d = json.loads(m.group(1))
    except Exception:
        return None
    r = d[0] if isinstance(d, list) else d
    o = r.get("offers") or {}
    price = o.get("price")
    if not price:
        return None
    def nm(x):
        return x.get("name") if isinstance(x, dict) else x
    km = r.get("mileageFromOdometer")
    km = km.get("value") if isinstance(km, dict) else km
    loc = (((o.get("seller") or {}).get("homeLocation") or {}).get("address") or {}).get("addressLocality")
    return dict(venue="one2car", kind="retail_ask", url=url,
                title=r.get("name"), brand=nm(r.get("brand")), model=nm(r.get("model")),
                year=r.get("vehicleModelDate"), body=r.get("bodyType"), fuel=r.get("fuelType"),
                seats=r.get("seatingCapacity"), color=r.get("color"),
                km=km, price=price, currency=o.get("priceCurrency"), locality=loc)


# ---------------------------------------------------------------- Union Auction (auct.co.th)
# Not scraped. The site's own listing page calls a bulk JSON endpoint, and an EMPTY Brand_Name
# returns the entire upcoming inventory for an asset type — so the whole venue is two HTTP requests,
# not 40,000. Reachable from ANY IP including CI (measured from an Azure US runner).
AUCT_API = "https://service.auct.co.th:2368/webauction/products_new"
AUCT_TYPES = {"car": "รถยนต์", "moto": "รถจักรยานยนต์"}

# service.auct.co.th sends ONLY its leaf certificate and omits the Sectigo intermediate that chains
# it to a trusted root. Browsers hide this by fetching the missing intermediate from the leaf's AIA
# extension; OpenSSL/curl on Linux do not, so every Linux CI runner fails the handshake with
# "unable to get local issuer certificate" while the same URL works fine in a browser and from the
# owner's Windows laptop. That asymmetry is why this was misread as a datacenter geoblock for days.
# We supply the omitted intermediate instead — see pipeline/certs/README.md for why this is a chain
# repair and NOT `curl -k`: verification stays on, and the anchor is a root the system already had.
AUCT_CA_EXTRA = os.path.join(HERE, "certs", "sectigo_public_server_auth_ca_dv_r36.pem")
_CA_BUNDLE_CACHE = []          # one temp bundle per process, built lazily


def _ca_bundle_args():
    """curl args that trust the system roots PLUS the intermediate auct.co.th forgets to send.

    Returns [] when the extra certificate is missing, so the call still runs (and fails loudly with
    a real TLS error) rather than the puller dying on a missing repo file.
    """
    if _CA_BUNDLE_CACHE:
        return _CA_BUNDLE_CACHE[0]
    if not os.path.exists(AUCT_CA_EXTRA):
        print("  ! %s missing — proceeding with system roots only; expect a TLS chain failure."
              % os.path.relpath(AUCT_CA_EXTRA, ROOT), file=sys.stderr)
        _CA_BUNDLE_CACHE.append([])
        return []

    import ssl
    import tempfile

    # --cacert REPLACES the trust store rather than adding to it, so concatenate: system roots first,
    # then the intermediate. Anchoring on the real root (not on the intermediate) keeps the full
    # signature chain under test.
    system = ssl.get_default_verify_paths().cafile
    if not system or not os.path.exists(system):
        try:
            import certifi
            system = certifi.where()
        except Exception:
            system = None

    fd, path = tempfile.mkstemp(prefix="auct_ca_", suffix=".pem")
    with os.fdopen(fd, "wb") as out:
        if system:
            with open(system, "rb") as fh:
                out.write(fh.read())
                out.write(b"\n")
        else:
            # No discoverable system bundle (some Windows setups). Anchoring at the intermediate is
            # narrower than ideal but is still a genuine signature check, unlike --insecure.
            print("  ! no system CA bundle found — anchoring on the Sectigo intermediate alone.",
                  file=sys.stderr)
        with open(AUCT_CA_EXTRA, "rb") as fh:
            out.write(fh.read())

    import atexit
    atexit.register(lambda: os.path.exists(path) and os.unlink(path))

    _CA_BUNDLE_CACHE.append(["--cacert", path])
    return _CA_BUNDLE_CACHE[0]

# STRICT ALLOWLIST — an allowlist, deliberately, not a denylist. Every record carries
# Chassis_No, Engine_No, License_Plate_No, Contract_No, Seller_Contract_No (populated 1147/1147 when
# checked) plus created_user, which is a named branch employee. Chassis/engine/plate identify a
# specific vehicle and through DLT a specific owner; the two contract numbers are RIVAL LENDERS'
# account numbers. None of it may reach disk. A denylist would leak the first new field the API adds;
# this cannot. Customer_* fields were empty in every record checked and are still not listed.
#
# Seller_Name is kept ONLY WHEN IT IS A JURISTIC PERSON — see _seller() below. The original reasoning
# ("the consignor is a finance company, so it's business intelligence, not personal data") was right
# about the typical row and wrong about the tail: a 210,303-row archive turned up 383 distinct
# consignors, and two of the top twenty are plainly individuals' given names with several thousand
# lots each. A private citizen consigning repossessed vehicles is a natural person under PDPA no
# matter how many lots they move, so the name is replaced with a category rather than kept.
AUCT_ALLOW = {
    "Asset_Type", "Asset_Group_Name", "Asset_Type_Code", "Car_Type", "Regist_Type_Name",
    "Brand_Name", "Model_Name", "Sub_Model_Name",
    "Manufacturing_Year", "Year_of_Manufacture", "Register_Year",
    "Mile", "Engine_Size", "Fuel_Type", "Asset_Gear", "Car_Paint",
    "Asset_Grade", "Condition_Grade", "Point_1", "Point_2", "Point_3",
    "Point_Grade_1", "Point_Grade_2", "Point_Grade_3",
    "Sales_Price", "Sales_Type", "Sold_Price", "Highest_Selling_Price", "Price_including_VAT",
    "Auction_Date", "Formatted_Auction_Date", "Auction_Floor", "Auction_No",
    "Branch_Name", "Branch_Code", "Location_Name", "License_Plate_City",
    "Seller_Name", "Seller_Group",
}


# A juristic person carries one of these in its registered name; a natural person does not. Matching
# on the legal-form marker rather than on a curated list of known lenders is what makes this hold as
# new consignors appear — an unknown company still says จำกัด, and an unknown individual still does not.
_JURISTIC = ("จำกัด", "มหาชน", "บริษัท", "บมจ", "หจก", "ห้างหุ้นส่วน", "ธนาคาร", "สหกรณ์",
             "ลีสซิ่ง", "แคปปิตอล", "Co.", "Ltd", "PCL", "Public")


def _seller(name):
    """Juristic consignor -> its name (competitive intelligence). Natural person -> a category."""
    s = (name or "").strip()
    if not s:
        return None
    return s if any(m in s for m in _JURISTIC) else "(individual consignor)"


def auct_history(outpath, brands=None, sleep_s=20):
    """Two years of PAST auctions, brand by brand, streamed.

    Passed=1 returns the archive rather than the forward window: Toyota alone came back with 73,685
    lots spanning 2024-09-12 to 2026-08-24 (692 auction days), and history is far denser in price
    than the upcoming-auction snapshot — Sales_Price on 81% of lots against 33%, plus realised
    Sold_Price hammer figures, which is the actual recovery number rather than a reserve.

    STREAMED, deliberately. That Toyota response is 660 MB; all 57 brands would be ~38 MB short of
    38 GB against 37 GB of free disk, so the raw JSON is never written and never held whole in
    memory. curl writes to a pipe, ijson walks it item by item, each record is reduced to the
    allowlisted fields and appended, and the raw bytes are discarded as they go.

    Paced at one brand per `sleep_s` seconds. Asking a public server for 660 MB is a real cost to
    them; there is no reason to ask for the next one immediately.
    """
    import ijson

    brands = brands or auct_known_brands()
    print("  %d brands, streaming, %ds between calls" % (len(brands), sleep_s))
    seen_ids = set()
    total = 0
    fh = open(outpath, "w", encoding="utf-8")
    for i, (thai_type, brand) in enumerate(brands, 1):
        body = "Asset_Type=%s&Brand_Name=%s&Passed=1" % (urllib.parse.quote(thai_type),
                                                         urllib.parse.quote(brand))
        proc = subprocess.Popen(
            ["curl", "-s", "--compressed", "--max-time", "900", "-A", UA]
            + _ca_bundle_args()
            + ["-H", "Referer: https://www.auct.co.th/", "--data", body, AUCT_API],
            stdout=subprocess.PIPE)
        n = 0
        try:
            for r in ijson.items(proc.stdout, "product.item"):
                rec = {k: r[k] for k in AUCT_ALLOW if k in r}
                if "Seller_Name" in rec:
                    rec["Seller_Name"] = _seller(rec["Seller_Name"])
                if not rec.get("Brand_Name"):
                    continue
                # The archive overlaps between calls; a lot is identified for dedup purposes by its
                # auction slot + vehicle shape, never by chassis/plate/contract (those are dropped
                # before this point and must not be reintroduced as a key).
                key = (rec.get("Formatted_Auction_Date"), rec.get("Auction_No"),
                       rec.get("Auction_Floor"), rec.get("Brand_Name"), rec.get("Model_Name"),
                       rec.get("Sub_Model_Name"), rec.get("Mile"), rec.get("Sales_Price"),
                       rec.get("Branch_Code"))
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                rec["venue"] = "auct"
                rec["kind"] = "auction_history"
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
        except Exception as exc:
            print("    ! %s: stream ended early (%s)" % (brand, type(exc).__name__), file=sys.stderr)
        finally:
            try:
                proc.stdout.close()
                proc.wait(timeout=30)
            except Exception:
                proc.kill()
        total += n
        fh.flush()
        print("  [%2d/%d] %-14s %7d lots   (running total %d)" % (i, len(brands), brand, n, total),
              flush=True)
        if i < len(brands):
            time.sleep(sleep_s)
    fh.close()
    print("\n  %d historical lots -> %s" % (total, outpath))
    return 0 if total else 1


def auct_known_brands():
    """(asset_type, brand) pairs seen in the forward-window harvest.

    Read from what the venue actually listed rather than hardcoded, so a brand that appears or
    disappears is picked up without an edit here."""
    path = os.path.join(OUTDIR, "auct.jsonl")
    pairs = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("Asset_Type") and r.get("Brand_Name"):
                    pairs.add((r["Asset_Type"], r["Brand_Name"]))
    if not pairs:                      # first run, before any forward harvest exists
        pairs = {("รถยนต์", b) for b in ("Toyota", "Isuzu", "Honda", "Mitsubishi", "Nissan", "Mazda")}
        pairs |= {("รถจักรยานยนต์", b) for b in ("Honda", "Yamaha", "Suzuki")}
    # biggest-volume types first so a killed run still has the important brands
    return sorted(pairs, key=lambda p: (p[0], p[1]))


def auct_harvest(outpath, _limit=None, _workers=None):
    """Two calls — cars and motorcycles — then filter every record through the allowlist."""
    kept, dropped_fields = [], set()
    for kind, thai in AUCT_TYPES.items():
        body = "Asset_Type=%s&Brand_Name=&Passed=0" % urllib.parse.quote(thai)
        p = subprocess.run(
            ["curl", "-s", "--compressed", "--max-time", "180", "-A", UA]
            + _ca_bundle_args()
            + ["-H", "Referer: https://www.auct.co.th/", "--data", body, AUCT_API],
            capture_output=True, timeout=240)
        # Check curl's OWN exit status before trying to parse. Without this, a handshake that never
        # completed produced an empty stdout and surfaced as "Expecting value: line 1 column 1",
        # which reads like a malformed response body and sent a diagnosis down the wrong path for
        # days. curl 60 = certificate problem, 6 = DNS, 7 = connection refused, 28 = timeout.
        if p.returncode != 0:
            err = p.stderr.decode("utf-8", "replace").strip().splitlines()
            print("  ! %s: curl failed (exit %d)%s" % (kind, p.returncode,
                  " — " + err[-1] if err else " — no stderr (curl ran with -s)"), file=sys.stderr)
            if p.returncode == 60:
                print("    exit 60 is a TLS chain failure. The venue omits its intermediate CA; "
                      "pipeline/certs/ supplies it. Check that PEM exists and has not expired.",
                      file=sys.stderr)
            continue
        try:
            doc = json.loads(p.stdout.decode("utf-8", "replace"))
        except Exception as exc:
            print("  ! %s: response did not parse (%s); %d bytes received"
                  % (kind, exc, len(p.stdout)), file=sys.stderr)
            continue
        prods = doc.get("product") or []
        print("  %-5s %-16s %5d lots" % (kind, thai, len(prods)))
        for r in prods:
            dropped_fields |= (set(r) - AUCT_ALLOW)
            rec = {k: r[k] for k in AUCT_ALLOW if k in r}
            if "Seller_Name" in rec:
                rec["Seller_Name"] = _seller(rec["Seller_Name"])
            rec["venue"] = "auct"
            rec["kind"] = "auction_reserve"
            kept.append(rec)
    with open(outpath, "w", encoding="utf-8") as fh:
        for rec in kept:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("\n  kept %d lots, %d fields each" % (len(kept), len(AUCT_ALLOW)))
    print("  dropped %d source fields, incl. every identifier: %s"
          % (len(dropped_fields),
             ", ".join(sorted(f for f in dropped_fields
                              if any(t in f for t in ("Chassis", "Engine_No", "License_Plate_No",
                                                      "Contract", "user", "Customer"))))))
    print("  -> %s" % outpath)
    return 0 if kept else 1


# ---------------------------------------------------------------- Kaidee
# Kaidee's LISTING pages are the unit, not the individual ad: one category page carries ~11 fully
# structured ads in its __NEXT_DATA__, so a page fetch yields eleven vehicles instead of one. The
# per-province auto roots come out of the site's own categories_provinces sitemap (/c1p<N>-auto/...).
#
# robots.txt for user-agent * disallows /dfp.js, /member/*, /browse*, /history*, /messages*,
# /cdn-cgi/rum*, *mid=*, *dealership=* and *_escaped_fragment_*. The Disallow: / lines apply only to
# six NAMED bots (PetalBot, grapeshot, Baiduspider, Sogou, Yandex, coccocbot), not to *. Category
# pages carry none of the disallowed markers, and KAIDEE_FORBIDDEN below re-checks every URL at
# fetch time rather than trusting that the sitemap stays clean.
KAIDEE_SITEMAP = "https://www.kaidee.com/sitemap/categories_provinces.xml.gz"
KAIDEE_FORBIDDEN = ("mid=", "dealership=", "_escaped_fragment_", "/member/", "/browse", "/history",
                    "/messages")

# STRICT ALLOWLIST — an allowlist, deliberately, not a denylist. Every kaidee ad ships a `member`
# block (the seller's real name + avatar), a `contactInfo` block (phone, email, LINE id), a
# `memberId`, and an `autoInfo.dealership.name` that is frequently a private individual's given
# name. Those are natural persons' contact details under PDPA and must never reach disk — not in a
# harvest file, not in a log line. A denylist would leak the first field kaidee adds; this cannot.
# `id` is kept and it is NOT an exception to the rule above: it identifies the LISTING, not the
# person who placed it. It is load-bearing rather than incidental — without a stable per-item id the
# only way to tell two records apart is their text, and the same vehicle appears on many overlapping
# category pages. See DEDUP_KEY.
KAIDEE_KEEP_AD = {"id", "price", "title", "location", "categoryName", "conditionName", "purposeName",
                  "firstApprovedTime"}
KAIDEE_KEEP_AUTO = {"brand", "model", "submodel", "year", "mileage", "fuelType", "transmission",
                    "carType"}


# The category roots, MEASURED rather than taken from the categories_provinces sitemap. That sitemap
# is a trap and the reason the first harvest was 81% duplicate rows: its 382 /c1p<N>-auto/<province>
# URLs all 302 onto the SAME nationwide car listing (the served h1 is "ขายรถยนต์มือสอง ทั่วประเทศ"
# — nationwide — and the canonical is rod.kaidee.com/c11-auto-car), so every province root returned
# the identical 30 ads. `?page=N` was ignored there too: pageProps.page came back 1 on every request.
#
# The auto vertical actually lives on rod.kaidee.com, where ?page=N IS honoured (measured:
# pageProps.page tracks the request and page 1 vs page 50 share only the 4 pinned ads). Motorcycles
# are not on that host at all — they are c149 on www. Both are paginated off the page's OWN
# total/pagesCount, so the walk stops when the category does instead of guessing a depth.
KAIDEE_ROOTS = (
    ("https://rod.kaidee.com/c11-auto-car", "car"),        # measured 10,361 listings / 400 pages
    ("https://www.kaidee.com/c149-motorcycle", "moto"),    # measured 2,742 listings
)
KAIDEE_PER_PAGE = 26          # 30 slots/page of which ~4 are pinned repeats, dropped by dedup
KAIDEE_MAX_PAGE = 400


def _next_props(url):
    """pageProps out of a Next.js page, or None. Used to read a category's own size before walking."""
    html = fetch(url)
    if not html:
        return None
    m = NEXT_DATA.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))["props"]["pageProps"]
    except Exception:
        return None


def kaidee_urls(limit):
    """Category roots paginated to their OWN declared depth, not a fixed guess."""
    urls = []
    for root, kind in KAIDEE_ROOTS:
        pp = _next_props(root)
        if not pp:
            print("  ! kaidee %s unreadable — skipped" % root, file=sys.stderr)
            continue
        total = pp.get("total") or 0
        pages = pp.get("pagesCount") or (total + KAIDEE_PER_PAGE - 1) // KAIDEE_PER_PAGE
        pages = min(pages, KAIDEE_MAX_PAGE)
        print("  kaidee %-5s %-44s %6d listings, %d pages" % (kind, root.split("//")[1], total, pages))
        urls.append(root)
        urls += ["%s?page=%d" % (root, p) for p in range(2, pages + 1)]
    return [u for u in urls if not any(bad in u for bad in KAIDEE_FORBIDDEN)][:limit]


NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
# Motorcycle ads carry an EMPTY autoInfo — the structured brand/model/year/mileage block exists only
# on the car vertical. Their titles are consistently "<BRAND> <MODEL> ปี <YYYY> ...", so brand and
# year are recovered from the title rather than dropped. Model is deliberately NOT guessed: the
# token after the brand is reliable for "HONDA CB650F" and wrong for "Yamaha YZF-R7 รถสวยกริ๊บ",
# and a wrong model silently corrupts a census cell. Better absent than fabricated.
_KD_YEAR = re.compile(r"ปี\s*((?:19|20)\d\d)")


def kaidee_parse(html, url):
    """One page -> a LIST of records (the generic harvester accepts either shape)."""
    m = NEXT_DATA.search(html)
    if not m:
        return None
    try:
        pp = json.loads(m.group(1))["props"]["pageProps"]
    except Exception:
        return None
    out = []
    for ad in pp.get("ads") or []:
        if not ad.get("price"):
            continue
        rec = {k: ad[k] for k in KAIDEE_KEEP_AD if ad.get(k) not in (None, "")}
        auto = ad.get("autoInfo") or {}
        rec.update({k: auto[k] for k in KAIDEE_KEEP_AUTO if auto.get(k) not in (None, "")})
        if not rec.get("year"):
            y = _KD_YEAR.search(ad.get("title") or "")
            if y:
                rec["year"] = y.group(1)
        rec.update(venue="kaidee", kind="retail_ask", url=url, currency="THB")
        out.append(_scrubbed(rec, ("title", "location")))
    return out or None


# ---------------------------------------------------------------- Truck2Hand
# The venue that covers the collateral nobody else prices: trucks, buses, and — the one that closes
# a real gap in the book — agricultural machinery (4,600 tractor accounts with no anchor anywhere).
# Its sitemap is category pages only, no individual listings, so the category page IS the unit: 100+
# items each, ?page=N to walk (measured: cat_pickup = 3,953 items over 40 pages).
#
# robots.txt declares no Disallow for user-agent * at all.
T2H_SITEMAP = "https://www.truck2hand.com/sitemap.xml"
# Members of the sitemap index worth walking. Deliberately not every category — wheels, batteries,
# lubricants and accessories are parts, not collateral, and pulling them would be pure noise.
T2H_CATEGORIES = ("truck", "truck-body-trailer", "pickup", "passenger-car", "van", "bus",
                  "heavy-machinery", "agricultural-machinery", "motorbike")
T2H_MAX_PAGE = 40

# STRICT ALLOWLIST, same reasoning as kaidee. Each truck2hand item embeds a `user` block carrying
# displayName, profileImageFullUrl, mobilePhone and a shopOtherTelephoneNumbers list of {tel, name}
# — live mobile numbers belonging to named private individuals. None of it is kept.
# `hashId` identifies the LISTING, not the person — same reasoning as kaidee's `id`, and equally
# load-bearing: it is what lets the same lorry appearing under several categories collapse to one row.
T2H_KEEP = {"hashId", "title", "displayPrice", "shortDetails", "subCategory1Slug", "itemSoldWorkflow"}


T2H_CAT = "https://www.truck2hand.com/category/cat_%s/"
T2H_PAGE_CAP = 100            # the venue stops paginating here: 100 pages x ~100 items = 10,000


def _t2h_size(url):
    """(itemCount, totalPages) for a category page, from the page's own pageProps."""
    pp = _next_props(url)
    if not pp:
        return None, None
    return pp.get("itemCount"), pp.get("totalPages")


def t2h_urls(limit):
    """Top-level categories walked to their own declared depth, sharded when the venue truncates.

    The sitemap is NOT used to pick roots any more, and that is the fix for an 82% duplicate rate.
    It lists 380 category URLs that are a HIERARCHY crossed with attribute facets — cat_truck
    contains cat_truck_6wheel-truck contains cat_truck_6wheel-truck_truck-body-dump, and each of
    those is sliced again by +attr_medium. The same lorry therefore appears on a dozen of those
    pages, and harvesting all 380 counted it a dozen times: a vehicle listed in many categories got
    a dozen votes in a median that is supposed to be one-vehicle-one-vote.

    Every listing sits under exactly ONE top-level category, so the top-level set is complete and
    disjoint. The exception is handled rather than ignored: the venue caps a category at 10,000
    items / 100 pages, so a root at the cap is NOT complete, and those get sharded into their
    children (whose individual counts are under the cap) instead of being silently truncated.

    ?status=sold is kept as a separate walk. A sold listing is a REALISED retail price, which is
    worth more to a recovery census than any number of asks.
    """
    urls, capped = [], []
    for cat in T2H_CATEGORIES:
        for sold in (False, True):
            root = T2H_CAT % cat + ("?status=sold" if sold else "")
            n, pages = _t2h_size(root)
            if not pages:
                print("  ! t2h %s unreadable — skipped" % root, file=sys.stderr)
                continue
            tag = "SOLD" if sold else "ask"
            if pages >= T2H_PAGE_CAP:
                capped.append((cat, sold, n))
            print("  t2h %-24s %-4s %7s items, %3d pages%s"
                  % (cat, tag, n, pages, "  <-- AT CAP, sharding" if pages >= T2H_PAGE_CAP else ""))
            urls.append(root)
            urls += ["%s%spage=%d" % (root, "&" if "?" in root else "?", p)
                     for p in range(2, pages + 1)]
    if capped:
        urls += _t2h_shards(capped)
    return urls[:limit]


def _t2h_shards(capped):
    """Child categories of the roots the venue truncated at 10,000, so their tail is not lost."""
    idx = _sitemap(T2H_SITEMAP)
    if not idx:
        print("  ! t2h sitemap unreadable — capped categories stay TRUNCATED", file=sys.stderr)
        return []
    members = [u for u in re.findall(r"<loc>([^<]+)</loc>", idx)
               if any("categories-%s-" % c in u for c in T2H_CATEGORIES)]
    allcats = []
    for m in members:
        raw = _sitemap(m)
        if raw:
            allcats.extend(re.findall(r"<loc>([^<]+)</loc>", raw))
    out = []
    for cat, sold, _n in capped:
        # Direct children only (cat_truck_6wheel-truck), never grandchildren and never the
        # +attr_ facets — those re-slice the same items and would reintroduce the duplication.
        pref = "/category/cat_%s_" % cat
        kids = sorted({u.split("?")[0] for u in allcats
                       if pref in u and "attr_" not in u
                       and u.split(pref)[1].strip("/").count("_") == 0})
        for k in kids:
            root = k + ("?status=sold" if sold else "")
            n, pages = _t2h_size(root)
            if not pages:
                continue
            out.append(root)
            out += ["%s%spage=%d" % (root, "&" if "?" in root else "?", p)
                    for p in range(2, min(pages, T2H_PAGE_CAP) + 1)]
        print("  t2h shard %-24s %-4s -> %d child categories"
              % (cat, "SOLD" if sold else "ask", len(kids)))
    return out


def t2h_parse(html, url):
    m = NEXT_DATA.search(html)
    if not m:
        return None
    try:
        pp = json.loads(m.group(1))["props"]["pageProps"]
    except Exception:
        return None
    out = []
    sections = (pp.get("listingSections") or []) + (pp.get("listingSoldSections") or [])
    sold_ids = {id(s) for s in (pp.get("listingSoldSections") or [])}
    # A ?status=sold page returns its items in the ORDINARY listingSections, not in
    # listingSoldSections — that second block only appears as a "recently sold" strip appended to an
    # ordinary listing page. Trusting the section alone therefore labelled all 89,794 rows of a sold
    # sweep as asks and silently threw away the realised retail price, which is the whole reason the
    # sold pages are walked. The requested URL is the authority on what was asked for.
    url_sold = "status=sold" in url
    for sec in sections:
        is_sold = url_sold or id(sec) in sold_ids
        for row in sec.get("rows") or []:
            for it in row.get("items") or []:
                price = _thb(it.get("displayPrice"))
                if not price:
                    continue
                rec = {k: it[k] for k in T2H_KEEP if it.get(k) not in (None, "", [])}
                rec.pop("displayPrice", None)
                # shortDetails is the site's own [BRAND, MODEL, "ปี YYYY"] triple.
                sd = it.get("shortDetails") or []
                rec["brand"] = sd[0] if len(sd) > 0 else None
                rec["model"] = sd[1] if len(sd) > 1 else None
                yr = re.search(r"(19|20)\d\d", " ".join(str(s) for s in sd))
                rec["year"] = yr.group(0) if yr else None
                rec.update(venue="truck2hand", url=url, currency="THB", price=price,
                           kind="retail_sold" if is_sold else "retail_ask")
                out.append(_scrubbed({k: v for k, v in rec.items() if v is not None},
                                     ("title", "shortDetails")))
    return out or None


# ---------------------------------------------------------------- free-text scrubbing
# The per-venue allowlists keep STRUCTURED identifiers off disk. They cannot touch the other half of
# the problem: sellers type identifiers into free text. Measured on a 1,112-row truck2hand smoke
# harvest, 23 ad TITLES contained a Thai mobile number, and a kaidee title carried a full licence
# plate ("... 2020 1นข-6076"). Both fields passed every allowlist, because the field itself is
# legitimate — it is the content that is not.
#
# So every free-text field is scrubbed on the way to disk, not on the way out of it. A plate is a
# vehicle identifier that links to a registered keeper, and a mobile number is a natural person's
# contact detail; neither is worth anything to a price census, so there is no trade-off to weigh.
_PHONE_TH = re.compile(r"(?<!\d)0[\d\-\s]{7,12}\d(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_LINE_ID = re.compile(r"(?:line|ไลน์|ไอดี)\s*[:：]?\s*@?[\w.\-]{3,}", re.I)
# Thai plate: an optional leading digit, 1-3 Thai consonants, then up to 4 digits. The province
# suffix is not matched — it is not identifying on its own and is useful geography.
_PLATE_TH = re.compile(r"(?<![฀-๿])\d?[ก-ฮ]{1,3}[\s\-]?\d{1,4}(?![\d฀-๿])")


def _scrub(v):
    """Strip contact details and vehicle plates out of any free-text value (str, or list of str)."""
    if isinstance(v, list):
        return [_scrub(x) for x in v]
    if not isinstance(v, str):
        return v
    s = _EMAIL.sub(" ", v)
    s = _LINE_ID.sub(" ", s)
    s = _PHONE_TH.sub(" ", s)
    s = _PLATE_TH.sub(" ", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def _scrubbed(rec, fields):
    for f in fields:
        if f in rec:
            rec[f] = _scrub(rec[f])
    return rec


def _thb(s):
    """'฿ 60,000' -> 60000. Returns None for 'สอบถามราคา' and friends, which must not become 0."""
    if not isinstance(s, str):
        return s if isinstance(s, (int, float)) else None
    d = re.sub(r"[^\d]", "", s)
    return int(d) if d else None


# ---------------------------------------------------------------- Taladrod (ตลาดรถ)
# The ราคากลาง ("standard price") pages are NOT the way in, and it is worth writing down why so
# nobody spends the afternoon again: schmktprc.aspx / schlowprc.aspx render a make-model PICKER
# server-side and fetch their price table from m.taladrod.com/api/v1.0, and taladrod's robots.txt
# disallows /api/ (and /data/) for user-agent *. Measured, not assumed — a headless render of
# schlowprc.aspx?mk=5&md=21&open=1227 produced 4,290 characters of picker and zero prices.
#
# The classifieds search DOES render server-side, and it is the better source anyway: schc.aspx
# embeds a plain JSON array of car objects straight in the HTML, each with an asking price, a
# 4-digit year, make/model/trim, a sold flag, and a PREVIOUS price. That last field is the one no
# other venue gives us — a populated prvprc is a listing whose asking price was cut, which is a
# direct read on softening demand for that model rather than an inference from levels.
#
# Sharding: a response caps at 600 cars. mk:<id> shards cleanly and disjointly (measured: mk:5 BENZ
# 600, mk:6 BMW 600, mk:14 LANDROVER 33, mk:65 MG 292, zero overlap between any pair). Make ids are
# populated by JS and never appear in the server HTML, so they are swept numerically and their names
# are learned from the returned data — the same discipline as auct_known_brands().
TALADROD_SEARCH = "https://www.taladrod.com/w40/isch/schc.aspx?%s"
TALADROD_MAX_MK = 120
TALADROD_CAP = 600

# Allowlist. These objects carry no seller name or phone — verified field-by-field on a live
# response — but the allowlist stays, because "there was no PII in it the day I looked" is not a
# property a puller can rely on across a site redesign.
TALADROD_KEEP = {"yr4": "year", "amake": "brand", "amodel": "model", "atrim": "trim",
                 "abody": "body", "namemmt": "spec", "prc": "price", "prvprc": "price_previous",
                 "sbaht": "price_start", "issold": "sold", "cid": "listing_id"}


def taladrod_urls(limit):
    """One query per make id. Makes that come back at the 600 cap are reported.

    The fno:all seed page that used to lead this list is gone on purpose: it returns the newest
    cars across EVERY make, so all 600 of its rows are also returned by one of the mk: shards. It
    contributed nothing but a duplicate of work already done, and duplicates are not free — each one
    is an extra vote for its own price in the median.
    """
    return [TALADROD_SEARCH % ("mk:%d" % i) for i in range(1, TALADROD_MAX_MK + 1)][:limit]


CAR_OBJ = re.compile(r'\{"type":"car",.*?"ncar":"\d+"\}')


def taladrod_parse(html, url):
    """One search page -> a list of car records, read out of the embedded JSON array."""
    out, capped = [], 0
    for m in CAR_OBJ.finditer(html):
        try:
            c = json.loads(m.group(0))
        except Exception:
            continue
        price = _thb(c.get("prc"))
        if not price:
            continue
        rec = {}
        for src, dst in TALADROD_KEEP.items():
            v = c.get(src)
            if v in (None, "", "0"):
                continue
            rec[dst] = _thb(v) if dst.startswith("price") else v
        rec["sold"] = (c.get("issold") == "Y")
        rec.update(venue="taladrod", kind="retail_ask", url=url, currency="THB", price=price)
        out.append(rec)
        capped += 1
    if capped >= TALADROD_CAP:
        # No silent truncation: a make at the cap has more inventory than we took, and the log is
        # the only place that fact can survive to whoever reads the harvest.
        print("  ! %s hit the %d-row cap — that make is TRUNCATED, not complete"
              % (url.rsplit("?", 1)[-1], TALADROD_CAP), file=sys.stderr)
    return out or None


def _sitemap(url):
    """Fetch a sitemap that may or may not arrive gzipped. --compressed makes curl transparently
    decode Content-Encoding: gzip, so a .xml.gz served that way lands already-plain; a .gz served as
    an opaque body does not. Sniff the magic rather than trusting the extension."""
    try:
        p = subprocess.run(["curl", "-sL", "--compressed", "--max-time", "90", "-A", UA, url],
                           capture_output=True, timeout=120)
        body = p.stdout
        if body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return body.decode("utf-8", "replace")
    except Exception as exc:
        print("  ! sitemap %s failed: %s" % (url.rsplit("/", 1)[-1], exc), file=sys.stderr)
        return None


VENUES = {
    "one2car": dict(urls=one2car_urls, parse=one2car_parse, harvest=None,
                    note="RETAIL ask — Thai IP only (US datacenter gets 403 Cloudflare)"),
    "auct": dict(urls=None, parse=None, harvest=auct_harvest,
                 note="AUCTION reserve, cars + motorcycles — reachable from ANY IP incl. CI"),
    "kaidee": dict(urls=kaidee_urls, parse=kaidee_parse, harvest=None,
                   note="RETAIL ask, ~11 structured ads per page — reachable from ANY IP incl. CI"),
    "truck2hand": dict(urls=t2h_urls, parse=t2h_parse, harvest=None,
                       note="RETAIL ask + SOLD, trucks/tractors/buses — ANY IP; the only tractor anchor"),
    "taladrod": dict(urls=taladrod_urls, parse=taladrod_parse, harvest=None,
                     note="RETAIL ask + PRICE CUTS (prvprc) — ANY IP; classifieds, not the /api/ price board"),
}


# The IDENTITY of a vehicle row, per venue — what makes two rows the same listing.
#
# This exists because the first full harvest was 66-82% duplicates on every listing-page venue, and
# duplicates are not merely wasted bytes: the census takes MEDIANS, so a vehicle that appears on ten
# category pages casts ten votes and drags the cell toward its own price. Deduping at write time
# makes that structurally impossible rather than something a later stage has to remember to undo.
#
# one2car is absent deliberately — one URL is one listing there, so the url-level resume below is
# already an exact dedup and a second mechanism would be redundant.
DEDUP_KEY = {
    "kaidee":     lambda r: "kaidee:%s" % r.get("id"),
    "truck2hand": lambda r: "t2h:%s:%s" % (r.get("hashId"), r.get("kind")),
    "taladrod":   lambda r: "tld:%s" % r.get("listing_id"),
}


def harvest(venue, limit, workers, outpath):
    spec = VENUES[venue]
    print("venue: %s — %s" % (venue, spec["note"]))
    if spec.get("harvest"):                 # bulk-API venues need no crawl at all
        return spec["harvest"](outpath, limit, workers)
    urls = [enc(u) for u in spec["urls"](limit)]
    print("  %d urls to harvest, %d workers" % (len(urls), workers))

    keyfn = DEDUP_KEY.get(venue)
    done, seen = set(), set()
    if os.path.exists(outpath):                    # resumable: never refetch what we already have
        with open(outpath, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                done.add(r.get("url"))
                if keyfn:
                    seen.add(keyfn(r))
        print("  resuming — %d urls already harvested, %d distinct listings on disk"
              % (len(done), len(seen)))
    # A listing-page venue must NOT skip a page just because that page was fetched before: the page
    # is the unit of fetching, but the listing is the unit of data, and re-walking a page is how new
    # listings get picked up. Only one2car, where url == listing, resumes by url.
    todo = urls if keyfn else [u for u in urls if u not in done]

    lock = threading.Lock()
    stats = dict(ok=0, nodata=0, fail=0, n=0, rows=0, dup=0)
    t0 = time.time()
    fh = open(outpath, "a", encoding="utf-8")

    parse = spec["parse"]

    def work(u):
        html = fetch(u)
        rec = parse(html, u) if html else None
        # one2car returns one record per URL; the listing-page venues return a list of them. Both
        # shapes are normal — a page that yields 100 vehicles is the point of those venues.
        recs = rec if isinstance(rec, list) else ([rec] if rec else [])
        with lock:
            stats["n"] += 1
            fresh = []
            for r in recs:
                if keyfn:
                    k = keyfn(r)
                    if k in seen:
                        stats["dup"] += 1
                        continue
                    seen.add(k)
                fresh.append(r)
            if fresh:
                for r in fresh:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                stats["ok"] += 1
                stats["rows"] += len(fresh)
                if stats["ok"] % 25 == 0:
                    fh.flush()
            elif html:
                stats["nodata"] += 1
            else:
                stats["fail"] += 1
            if stats["n"] % 50 == 0:
                el = time.time() - t0
                print("  %5d/%d  ok=%d rows=%d dup=%d nodata=%d fail=%d  %.2f req/s  eta %.0f min"
                      % (stats["n"], len(todo), stats["ok"], stats["rows"], stats["dup"],
                         stats["nodata"], stats["fail"], stats["n"] / max(el, 1),
                         (len(todo) - stats["n"]) / max(stats["n"] / max(el, 1), .01) / 60),
                      flush=True)

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    fh.close()
    el = time.time() - t0
    print("\ndone: %d pages ok (%d NEW vehicle rows, %d duplicates dropped), %d no-data, %d failed "
          "in %.1f min (%.2f req/s) -> %s"
          % (stats["ok"], stats["rows"], stats["dup"], stats["nodata"], stats["fail"], el / 60,
             stats["n"] / max(el, 1), outpath))
    return 0 if stats["ok"] else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venue", default="one2car", choices=sorted(VENUES))
    ap.add_argument("--limit", type=int, default=500, help="max listings this run")
    ap.add_argument("--workers", type=int, default=4,
                    help="concurrent fetchers. 4 measured clean (12/12 HTTP 200, no challenge); "
                         "going much higher is what gets a puller blocked")
    ap.add_argument("--out", default=None)
    ap.add_argument("--history", action="store_true",
                    help="auct only — stream ~2 years of PAST auctions instead of the forward window")
    ap.add_argument("--sleep", type=int, default=20,
                    help="seconds between brand calls in --history mode (each is up to 660 MB)")
    a = ap.parse_args(argv)
    os.makedirs(OUTDIR, exist_ok=True)
    if a.history:
        if a.venue != "auct":
            print("--history is only meaningful for the auct venue", file=sys.stderr)
            return 1
        out = a.out or os.path.join(OUTDIR, "auct_history.jsonl")
        print("venue: auct — HISTORICAL archive (Passed=1), streamed so raw JSON never lands")
        return auct_history(out, sleep_s=a.sleep)
    out = a.out or os.path.join(OUTDIR, "%s.jsonl" % a.venue)
    return harvest(a.venue, a.limit, a.workers, out)


if __name__ == "__main__":
    sys.exit(main())
