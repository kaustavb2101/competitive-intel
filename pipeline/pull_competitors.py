#!/usr/bin/env python3
"""
pull_competitors.py — national competitor-branch census via Google Places
=========================================================================
Pulls the major Thai title-loan / vehicle-finance competitors nationwide so the
platform can compute competitor-aware white-space (objective #2). Run from a
NON-blocked network (Kaustav's Thai laptop). Needs a Google Places key in the
git-ignored .env as GOOGLE_PLACES_KEY (envload reads it).

    cd pipeline && python pull_competitors.py            # all 77 provinces, all brands
    python pull_competitors.py --provinces 10            # cheaper: 10 biggest only (smoke test)
    python pull_competitors.py --brands Srisawad,Tidlor  # subset of brands

COST NOTE: Google Places Text Search is billable (~$32 / 1,000 calls). A full run
is ~4 brands x 77 provinces x up to 3 pages ≈ 300-900 calls (~$10-30 or your free
quota). Use --provinces N to cap it. The script prints an estimate and the running
call count, and stops cleanly on OVER_QUERY_LIMIT / REQUEST_DENIED.

Output: platform/data/competitors_national.json   (served dir — the frontend fetches it here)
  { "meta": {...}, "brands": {...counts...},
    "items": [ {"brand","name","lat","lng","prov","place_id"} ] }
Deduped by place_id. Folds into the acquisition white-space + a map lens later.
"""
import json, os, sys, time, argparse, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
SRC = os.path.join(REPO, "source-data")
# Write straight into the served app dir so a fresh pull lands where the frontend fetches it
# (platform/data/competitors_national.json — read by the National-map competitor lens + Acquisition).
OUT_DIR = os.path.join(REPO, "platform", "data")
sys.path.insert(0, ROOT)
try:
    from envload import load_env; load_env()
except Exception:
    pass

KEY = (os.environ.get("GOOGLE_PLACES_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
       or os.environ.get("GMAPS_KEY") or os.environ.get("GOOGLE_MAPS_KEY"))

# brand -> Thai query term(s). Title-loan / vehicle-finance lenders AutoX competes with.
BRANDS = {
    "Srisawad":  "ศรีสวัสดิ์ เงินติดล้อ สาขา",
    "Muangthai": "เมืองไทย แคปปิตอล สาขา",
    "Tidlor":    "เงินติดล้อ สาขา",
    "Heng":      "เฮงลิสซิ่ง สาขา",
}
TEXTSEARCH = "https://maps.googleapis.com/maps/api/place/textsearch/json"


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def provinces(limit=None):
    """Thai province names, biggest-branch-first (from the province index)."""
    idx = json.load(open(os.path.join(SRC, "..", "platform", "data", "provinces", "index.json"), encoding="utf-8"))
    names = [p["th"] for p in idx]                       # already sorted by branches desc
    return names[:limit] if limit else names


def search(query):
    """Text Search with pagination (up to 3 pages / 60 results)."""
    out, token, calls = [], None, 0
    for _ in range(3):
        params = {"query": query, "region": "th", "language": "th", "key": KEY}
        if token:
            params["pagetoken"] = token
        d = _get(TEXTSEARCH + "?" + urllib.parse.urlencode(params))
        calls += 1
        st = d.get("status")
        if st in ("REQUEST_DENIED", "OVER_QUERY_LIMIT", "INVALID_REQUEST") and not token:
            # Surface Google's exact reason (it sits in error_message) instead of just the status.
            em = d.get("error_message")
            return out, calls, (f"{st}: {em}" if em else st)
        for r in d.get("results", []):
            loc = r.get("geometry", {}).get("location", {})
            if loc.get("lat") and loc.get("lng"):
                out.append((r.get("place_id"), r.get("name", ""), loc["lat"], loc["lng"]))
        token = d.get("next_page_token")
        if not token:
            break
        time.sleep(2.2)   # Places requires a short delay before a page token is valid
    return out, calls, "OK"


def run(brands, prov_limit, check=False):
    if not KEY:
        sys.exit("Set GOOGLE_PLACES_KEY in the repo-root .env (git-ignored).")
    provs = provinces(prov_limit)
    est = len(brands) * len(provs)
    print(f"~{est}-{est*3} Places calls across {len(brands)} brands x {len(provs)} provinces "
          f"(billable; Ctrl-C to stop). Output -> platform/data/competitors_national.json")
    seen, items, calls = set(), [], 0
    for brand in brands:
        q = BRANDS[brand]
        for prov in provs:
            try:
                res, c, st = search(f"{q} {prov}")
            except Exception as e:
                print(f"  ! {brand}/{prov}: {e}"); continue
            calls += c
            if st != "OK":
                print(f"  ! {brand}: {st} (stopping this brand)"); break
            for pid, name, lat, lng in res:
                if pid in seen:
                    continue
                seen.add(pid)
                items.append({"brand": brand, "name": name, "lat": round(lat, 6),
                              "lng": round(lng, 6), "prov": prov, "place_id": pid})
            print(f"  {brand} · {prov}: +{len(res)} (total {len(items)}, calls {calls})")
            time.sleep(0.2)
    by_brand = {}
    for it in items:
        by_brand[it["brand"]] = by_brand.get(it["brand"], 0) + 1
    out = {"meta": {"source": "Google Places Text Search — measured competitor locations",
                    "brands_queried": brands, "provinces": len(provs), "places_calls": calls,
                    "note": "Coverage is best-effort (Places caps ~60/query/province); a lower bound, not a registry."},
           "brands": by_brand, "items": sorted(items, key=lambda x: (x["brand"], x["prov"]))}
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "competitors_national.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"\nwrote {path}: {len(items)} competitor branches  {by_brand}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="national competitor census via Google Places")
    ap.add_argument("--brands", default=",".join(BRANDS), help="comma list (default all)")
    ap.add_argument("--provinces", type=int, default=None, help="cap to N biggest provinces (cost control)")
    a = ap.parse_args()
    bl = [b.strip() for b in a.brands.split(",") if b.strip() in BRANDS]
    raise SystemExit(run(bl, a.provinces))
