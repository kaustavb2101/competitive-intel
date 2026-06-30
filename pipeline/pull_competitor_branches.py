#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_competitor_branches.py — COMPLETE competitor branch census from the operators' own
store-locators (the authoritative source) + merge into platform/data/competitors_national.json.

WHY: the Google-Places census (~2.5k) and the Overture harvest (~2.5k) both badly undercount —
MTC alone runs 6,000+ branches, Srisawad 5,000+. The only complete, authoritative source is each
company's official branch-finder. Those corporate sites are GEO-BLOCKED from the cloud sandbox, so
this script is built to run from Kaustav's THAI laptop (where the sites resolve).

⛔ NO FABRICATION: this script only PULLS real published branch locations. It never invents a branch.
If a brand yields 0, it says so loudly and writes nothing for that brand — it does not fill the gap.

TWO MODES
  python pull_competitor_branches.py --discover
      Visits each brand's branch-finder and REPORTS where the branch data lives: candidate API/XHR
      URLs, embedded JSON blobs (Next.js __NEXT_DATA__, WP store-locator, etc.), and how many
      lat/lng pairs it can already see in the page. Paste the output back so the exact endpoints can
      be locked in. (No files written.)

  python pull_competitor_branches.py --pull [--merge]
      Harvests every branch from the configured endpoints, dedupes, and writes
      platform/data/competitors_locator.json. With --merge it also unions locator + Overture +
      Google into platform/data/competitors_national.json (deduped), with honest provenance.

  python pull_competitor_branches.py --check
      Network-free sanity check (for the QA gate): asserts the config is well-formed and, if
      competitors_locator.json exists, that it is structurally valid. Always offline. Exit 0.

CONFIG: edit BRANDS below. Each brand lists candidate `data_urls` (the XHR/API the finder calls) and
a `page_url` (the human finder page, used by --discover and as a regex fallback). Once --discover
reveals the real endpoint, drop it into `data_urls` and re-run --pull.

stdlib only (urllib). Polite: a browser UA + a short delay between requests.
"""
import os, sys, json, re, time, argparse, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_LOCATOR = os.path.join(ROOT, "platform", "data", "competitors_locator.json")
OUT_NATIONAL = os.path.join(ROOT, "platform", "data", "competitors_national.json")
OVERTURE = os.path.join(ROOT, "platform", "data", "competitors_overture.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Thailand bounding box — sanity filter so a stray coordinate never enters the census.
TH_BBOX = (5.4, 97.2, 20.7, 105.8)  # minlat, minlng, maxlat, maxlng

# Per-brand config. brand key MUST match the app's known set (Heng/Muangthai/Srisawad/Tidlor).
# data_urls: the XHR/API endpoints the finder calls (fill these from --discover output).
# page_url:  the human branch-finder page (probed by --discover; regex-scraped as a fallback).
BRANDS = {
    "Muangthai": {
        "label": "Muang Thai Capital (MTC)",
        "page_url": "https://www.muangthaicap.com/en/branch/",
        "data_urls": [
            # candidates to try; --discover will confirm the real one
            "https://www.muangthaicap.com/wp-admin/admin-ajax.php?action=get_branch",
            "https://www.muangthaicap.com/api/branch",
        ],
    },
    "Srisawad": {
        "label": "Srisawad (SAWAD)",
        "page_url": "https://www.srisawad.com/branch",
        "data_urls": [
            "https://www.srisawad.com/api/branch",
            "https://www.sawad.co.th/api/branch",
        ],
    },
    "Tidlor": {
        "label": "Ngern Tid Lor (TIDLOR)",
        "page_url": "https://www.tidlor.com/en/find-branch",
        "data_urls": [
            "https://www.tidlor.com/api/branches",
        ],
    },
    "Heng": {
        "label": "Heng Leasing (HENGX)",
        "page_url": "https://www.hengleasing.com/en/branch",
        "data_urls": [
            "https://www.hengleasing.com/api/branch",
        ],
    },
}

# ---------------------------------------------------------------------------
def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", "replace")

def in_th(lat, lng):
    return TH_BBOX[0] <= lat <= TH_BBOX[2] and TH_BBOX[1] <= lng <= TH_BBOX[3]

# pull every plausible lat/lng pair out of a JSON/HTML blob. Handles "lat":x,"lng":y ,
# "latitude":x,"longitude":y , and bare [lng,lat]-ish via labelled keys only (no blind pairing,
# which would fabricate locations). Returns list of (lat,lng).
_PAT = [
    re.compile(r'"lat(?:itude)?"\s*:\s*(-?\d{1,2}\.\d{3,})\s*,\s*"l(?:ng|on|ongitude)"\s*:\s*(-?\d{2,3}\.\d{3,})'),
    re.compile(r'"l(?:ng|on|ongitude)"\s*:\s*(-?\d{2,3}\.\d{3,})\s*,\s*"lat(?:itude)?"\s*:\s*(-?\d{1,2}\.\d{3,})'),
]
def extract_coords(text):
    out = []
    for i, pat in enumerate(_PAT):
        for m in pat.finditer(text):
            a, b = float(m.group(1)), float(m.group(2))
            lat, lng = (a, b) if i == 0 else (b, a)
            if in_th(lat, lng):
                out.append((round(lat, 6), round(lng, 6)))
    return out

# try to parse a structured branch list (name+coords) out of JSON; fall back to coords-only.
def parse_branches(text, brand):
    items = []
    try:
        data = json.loads(text)
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                lat = x.get("lat") or x.get("latitude") or x.get("Latitude")
                lng = x.get("lng") or x.get("lon") or x.get("longitude") or x.get("Longitude")
                name = (x.get("name") or x.get("branch_name") or x.get("title")
                        or x.get("BranchName") or x.get("name_th") or "")
                prov = (x.get("province") or x.get("prov") or x.get("Province") or "")
                try:
                    if lat is not None and lng is not None:
                        lat, lng = float(lat), float(lng)
                        if in_th(lat, lng):
                            items.append({"brand": brand, "name": str(name).strip(),
                                          "lat": round(lat, 6), "lng": round(lng, 6),
                                          "prov": str(prov).strip(), "source": "official-locator"})
                except (TypeError, ValueError):
                    pass
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
    except (ValueError, json.JSONDecodeError):
        pass
    if not items:  # regex fallback (coords only — honest, names unknown)
        for lat, lng in extract_coords(text):
            items.append({"brand": brand, "name": "", "lat": lat, "lng": lng,
                          "prov": "", "source": "official-locator"})
    return items

def dedupe(items):
    seen, out = set(), []
    for it in items:
        k = (it["brand"], round(it["lat"], 5), round(it["lng"], 5))
        if k in seen:
            continue
        seen.add(k); out.append(it)
    return out

# ---------------------------------------------------------------------------
def cmd_discover():
    print("DISCOVERY — paste this whole block back so the exact endpoints can be locked in.\n")
    for brand, cfg in BRANDS.items():
        print("=" * 64)
        print(f"{brand}  ({cfg['label']})")
        # probe the finder page
        for url in [cfg["page_url"]] + cfg["data_urls"]:
            try:
                txt = fetch(url)
                coords = extract_coords(txt)
                # surface candidate data URLs embedded in the page
                apis = sorted(set(re.findall(r'https?://[^\s"\'<>]+?(?:api|branch|store|locat|\.json)[^\s"\'<>]*', txt, re.I)))[:12]
                has_next = "__NEXT_DATA__" in txt
                has_wp = "admin-ajax.php" in txt or "/wp-json/" in txt
                print(f"  [{len(txt):>7} B] {url}")
                print(f"      lat/lng pairs visible: {len(coords)}"
                      f"{'  · Next.js __NEXT_DATA__' if has_next else ''}"
                      f"{'  · WordPress store-locator' if has_wp else ''}")
                for a in apis:
                    print(f"      candidate data URL: {a}")
            except urllib.error.HTTPError as e:
                print(f"  [HTTP {e.code}] {url}")
            except Exception as e:
                print(f"  [ERR {type(e).__name__}: {e}] {url}")
            time.sleep(1.0)
    print("\nNext: send the output above. The real branch endpoint is the URL with the most lat/lng "
          "pairs (or the __NEXT_DATA__ / admin-ajax line). I'll wire it into data_urls.")

def cmd_pull(merge):
    all_items, per_brand = [], {}
    for brand, cfg in BRANDS.items():
        got = []
        for url in cfg["data_urls"] + [cfg["page_url"]]:
            try:
                txt = fetch(url)
                got = parse_branches(txt, brand)
                if got:
                    print(f"{brand}: {len(got)} branches from {url}")
                    break
            except Exception as e:
                print(f"{brand}: {type(e).__name__} on {url}")
            time.sleep(1.0)
        if not got:
            print(f"!! {brand}: 0 branches — endpoint not yet configured. Run --discover. "
                  f"(writing nothing for {brand}; no fabrication)")
        got = dedupe(got)
        per_brand[brand] = len(got)
        all_items.extend(got)

    all_items = dedupe(all_items)
    payload = {
        "meta": {
            "source": "official operator store-locators (authoritative, run from a Thai IP)",
            "provenance": "Real published branch locations harvested from each brand's own "
                          "branch-finder. No fabricated branches; brands yielding 0 are omitted.",
            "generated_by": "pipeline/pull_competitor_branches.py --pull",
            "label": "MEASURED (official locator)",
            "brands": per_brand,
        },
        "brands": sorted(per_brand),
        "items": all_items,
    }
    with open(OUT_LOCATOR, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"\nwrote {OUT_LOCATOR}  ({len(all_items)} branches)  {per_brand}")

    if merge:
        merge_censuses()

def _load_items(path):
    if not os.path.exists(path):
        return []
    try:
        d = json.load(open(path, encoding="utf-8"))
        return d.get("items", d) if isinstance(d, dict) else d
    except Exception:
        return []

def merge_censuses():
    # union of official-locator + Overture + existing national (Google), deduped by brand+coords.
    locator = _load_items(OUT_LOCATOR)
    overture = _load_items(OVERTURE)
    google = _load_items(OUT_NATIONAL)
    # locator first so its names/source win on dedupe
    merged = dedupe(locator + overture + google)
    from collections import Counter
    per_brand = dict(Counter(i.get("brand") for i in merged))
    payload = {
        "meta": {
            "source": "UNION of official locators + Overture + Google Places (deduped)",
            "provenance": "Deduplicated union of three real censuses; richest available coverage. "
                          "Still a lower bound where a source is incomplete. No fabricated branches.",
            "generated_by": "pipeline/pull_competitor_branches.py --merge",
            "label": "MEASURED (multi-source union)",
            "components": {"official_locator": len(locator), "overture": len(overture),
                           "google": len(google), "merged_unique": len(merged)},
        },
        "brands": sorted(per_brand),
        "items": merged,
    }
    with open(OUT_NATIONAL, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"merged -> {OUT_NATIONAL}  ({len(merged)} unique)  {per_brand}")

def cmd_check():
    # offline: config sane + (if present) locator file structurally valid.
    assert isinstance(BRANDS, dict) and BRANDS, "BRANDS config empty"
    for b, c in BRANDS.items():
        assert c.get("page_url") and isinstance(c.get("data_urls"), list), f"bad config for {b}"
    if os.path.exists(OUT_LOCATOR):
        d = json.load(open(OUT_LOCATOR, encoding="utf-8"))
        assert "items" in d and isinstance(d["items"], list), "locator file malformed"
        for it in d["items"]:
            assert in_th(it["lat"], it["lng"]), "locator coord outside Thailand"
    print("pull_competitor_branches.py --check: OK (config valid; offline)")

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--discover", action="store_true", help="report where each brand's branch data lives")
    ap.add_argument("--pull", action="store_true", help="harvest branches -> competitors_locator.json")
    ap.add_argument("--merge", action="store_true", help="with --pull: union into competitors_national.json")
    ap.add_argument("--check", action="store_true", help="offline config/file sanity (QA gate)")
    a = ap.parse_args()
    if a.check:
        cmd_check()
    elif a.discover:
        cmd_discover()
    elif a.pull:
        cmd_pull(a.merge)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
