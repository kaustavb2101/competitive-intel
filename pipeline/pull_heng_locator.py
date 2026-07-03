#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_heng_locator.py — walk Heng Leasing's official branch-finder province-by-province and
harvest every branch's coordinates. RUN FROM A THAI IP (the site is Cloudflare/geo-blocked from
the cloud sandbox; Kaustav's laptop passes — the province <option> list already renders for him).

⛔ NO FABRICATION: only real published branch locations are written. Provinces that yield nothing
are reported as 0, not filled in.

The finder is a PHP cascade:
  branch/selectprovince.php            -> <option value="กระบี่">กระบี่</option> ... (province NAMES)
  <a province-result endpoint>?province=<name>  -> branches for that province (HTML or JSON)

We already KNOW selectprovince.php works (it returned the option list). We don't yet know the exact
result endpoint, so this script AUTO-DISCOVERS it: it scans the finder pages for candidate *.php
endpoints, tests each against the first province, and locks onto whichever returns Thai coordinates.
Then it walks all provinces and writes source-data/heng_branches.json — upload that file.

USAGE (from the pipeline/ folder, on the Thai laptop):
  python pull_heng_locator.py            # discover + walk all provinces + write the file
  python pull_heng_locator.py --verbose  # also print each candidate endpoint it tries

stdlib only. Polite: browser UA + a short delay between requests.
"""
import os, sys, re, json, time, ssl, urllib.request, urllib.parse, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "source-data", "heng_branches.json")

BASE = "https://www.hengleasing.com"
PROVINCE_LIST_URL = BASE + "/branch/selectprovince.php"
# pages likely to reference the province-result endpoint (form action / ajax url / onchange)
FINDER_PAGES = [BASE + "/branch/", BASE + "/branch/index.php", BASE + "/en/branch", BASE + "/en/branch/"]
# fallback candidate result-endpoint templates (used if page-scan finds none). {p}=url-encoded province.
FALLBACK_TEMPLATES = [
    BASE + "/branch/selectbranch.php?province={p}",
    BASE + "/branch/showbranch.php?province={p}",
    BASE + "/branch/branch.php?province={p}",
    BASE + "/branch/list.php?province={p}",
    BASE + "/branch/map.php?province={p}",
    BASE + "/branch/searchbranch.php?province={p}",
    BASE + "/branch/selectamphoe.php?province={p}",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "th,en;q=0.8", "Accept-Encoding": "identity",
           "Referer": BASE + "/branch/"}
try:
    import certifi
    CTX_OK = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX_OK = ssl.create_default_context()
CTX_NO = ssl._create_unverified_context()
TH = (5.4, 97.2, 20.7, 105.8)  # minlat,minlng,maxlat,maxlng — reject strays outside Thailand
VERBOSE = "--verbose" in sys.argv

def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers=HEADERS)
    for ctx in (CTX_OK, CTX_NO):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLError) and ctx is CTX_OK:
                continue
            raise
    return ""

def in_th(lat, lng):
    return TH[0] <= lat <= TH[2] and TH[1] <= lng <= TH[3]

# coordinate patterns: labelled JSON keys + Google-Maps URL forms + LatLng(...) — all LABELLED,
# never blind number-pairing (which would fabricate points).
_COORD = [
    (re.compile(r'"lat(?:itude)?"\s*:\s*"?(-?\d{1,2}\.\d{3,})"?\s*,\s*"l(?:ng|on|ongitude)"\s*:\s*"?(-?\d{2,3}\.\d{3,})'), 0),
    (re.compile(r'"l(?:ng|on|ongitude)"\s*:\s*"?(-?\d{2,3}\.\d{3,})"?\s*,\s*"lat(?:itude)?"\s*:\s*"?(-?\d{1,2}\.\d{3,})'), 1),
    (re.compile(r'[@]\s*(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{2,3}\.\d{3,})'), 0),
    (re.compile(r'[?&](?:q|ll|sll|daddr|destination|center|coord)=(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{2,3}\.\d{3,})'), 0),
    (re.compile(r'LatLng\(\s*(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{2,3}\.\d{3,})'), 0),
]
def coords_from(text):
    out = []
    for pat, order in _COORD:
        for m in pat.finditer(text):
            a, b = float(m.group(1)), float(m.group(2))
            lat, lng = (a, b) if order == 0 else (b, a)
            if in_th(lat, lng):
                out.append((round(lat, 6), round(lng, 6)))
    return out

def branches_from(text, prov):
    """Prefer structured JSON (keeps names); fall back to coord-only regex."""
    items = []
    try:
        data = json.loads(text)
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                lat = x.get("lat") or x.get("latitude") or x.get("Latitude")
                lng = x.get("lng") or x.get("lon") or x.get("longitude") or x.get("Longitude")
                nm  = (x.get("name") or x.get("branch_name") or x.get("title")
                       or x.get("name_th") or x.get("BranchName") or "")
                try:
                    if lat is not None and lng is not None:
                        la, lo = float(lat), float(lng)
                        if in_th(la, lo):
                            items.append({"name": str(nm).strip(), "lat": round(la, 6),
                                          "lng": round(lo, 6), "prov": prov})
                except (TypeError, ValueError):
                    pass
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
    except (ValueError, json.JSONDecodeError):
        pass
    if not items:
        for la, lo in coords_from(text):
            items.append({"name": "", "lat": la, "lng": lo, "prov": prov})
    return items

def get_provinces():
    html = fetch(PROVINCE_LIST_URL)
    vals = re.findall(r'<option[^>]*value="([^"]+)"', html)
    provs = [v.strip() for v in vals if v.strip() and "จังหวัด" not in v]  # drop the "- จังหวัด -" placeholder
    # de-dupe, keep order
    seen, out = set(), []
    for p in provs:
        if p not in seen:
            seen.add(p); out.append(p)
    return out

def discover_templates():
    """Scan the finder pages for *.php endpoints that take a province param; return url templates."""
    tmpl = []
    for pg in FINDER_PAGES:
        try:
            html = fetch(pg)
        except Exception:
            continue
        for m in re.findall(r'([\w./-]+\.php)\?[\w=&]*province=', html):
            u = urllib.parse.urljoin(pg, m)
            tmpl.append(u + ("&" if "?" in u else "?") + "province={p}")
        for m in re.findall(r'([\w./-]+\.php)', html):
            if re.search(r'branch|amphoe|province|search|show|list|map', m, re.I):
                tmpl.append(urllib.parse.urljoin(pg, m) + "?province={p}")
    # de-dupe, keep order, then append the known fallbacks
    seen, out = set(), []
    for t in tmpl + FALLBACK_TEMPLATES:
        if t not in seen:
            seen.add(t); out.append(t)
    return out

def main():
    print("Heng branch-finder walk — run from a Thai IP.\n")
    provs = get_provinces()
    if not provs:
        print("!! got 0 provinces from selectprovince.php — is the IP still passing? Aborting (nothing written).")
        sys.exit(1)
    print(f"provinces found: {len(provs)}  (e.g. {', '.join(provs[:5])} ...)\n")

    templates = discover_templates()
    # lock onto the first template that returns Thai coordinates for province #1
    chosen, probe = None, provs[0]
    for t in templates:
        url = t.format(p=urllib.parse.quote(probe))
        try:
            txt = fetch(url)
        except Exception as e:
            if VERBOSE: print(f"  try {url} -> {type(e).__name__}")
            continue
        n = len(branches_from(txt, probe))
        if VERBOSE: print(f"  try {url} -> {n} coords")
        if n:
            chosen = t
            print(f"locked endpoint: {t}\n")
            break
        time.sleep(0.4)
    if not chosen:
        print("!! no result endpoint returned coordinates. Re-run with --verbose and paste the output;\n"
              "   also paste:  curl -s -A \"Mozilla/5.0\" \"" + FINDER_PAGES[0] + "\" | grep -o '[a-zA-Z0-9_/.-]*\\.php'\n"
              "   so the exact endpoint can be wired in. (nothing written; no fabrication)")
        sys.exit(1)

    all_items, per_prov = [], {}
    for i, p in enumerate(provs, 1):
        url = chosen.format(p=urllib.parse.quote(p))
        try:
            items = branches_from(fetch(url), p)
        except Exception as e:
            items = []
            if VERBOSE: print(f"  {p}: {type(e).__name__}")
        per_prov[p] = len(items)
        all_items.extend(items)
        print(f"  [{i:>2}/{len(provs)}] {p}: {len(items)}")
        time.sleep(0.5)

    # de-dupe by rounded coord
    seen, dedup = set(), []
    for it in all_items:
        k = (round(it["lat"], 5), round(it["lng"], 5))
        if k not in seen:
            seen.add(k); dedup.append(it)

    payload = {
        "meta": {
            "brand": "Heng",
            "label": "MEASURED (official Heng locator)",
            "source": "https://www.hengleasing.com/branch/ (province-walk, run from a Thai IP)",
            "provenance": "Real published branch locations from Heng's own branch-finder. "
                          "No fabricated branches; provinces yielding 0 are recorded as 0.",
            "endpoint": chosen,
            "provinces": len(provs),
            "per_province": per_prov,
            "count": len(dedup),
        },
        "items": [dict(brand="Heng", source="official-locator", **it) for it in dedup],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"\nwrote {OUT}  ({len(dedup)} unique Heng branches across {sum(1 for v in per_prov.values() if v)} provinces)")
    print("Upload that file (source-data/heng_branches.json) and tell Claude — it merges into the census.")

if __name__ == "__main__":
    main()
