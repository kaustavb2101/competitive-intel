#!/usr/bin/env python3
"""
build_competitor_census.py — the merged measured competitor census the UI loads.

SOURCES (per brand, best-available wins)
----------------------------------------
1. OFFICIAL STORE-LOCATOR (authoritative + ~complete) — source-data/competitors_official.json.
   Srisawad, Tidlor and Muangthai were pulled directly from each operator's live branch endpoint
   (from the cloud sandbox, by completing each site's incomplete TLS chain — no laptop). These are
   the FULL networks: Srisawad 5,203 · Tidlor 1,919 · Muangthai 8,931. When a brand is present here,
   it is the sole source for that brand (the sample below is NOT unioned in — the locator already
   has everything, and unioning would add noise/near-dupes).
2. SAMPLE fallback (Google Places ∪ Overture Places, deduped) — for brands NOT in the official file
   (today: Heng, whose locator sits behind a Cloudflare challenge that blocks headless pulls; its
   archived countBranch.php reported 852 branches but no coordinates are retrievable without a
   residential IP). competitors_national.json ∪ competitors_overture.json, deduped by brand+proximity.

MEASURED vs ESTIMATED: every point is a real coordinate (an official-locator branch, or a Google/
Overture place). No synthesis. The only operations are a union + a proximity de-dupe. meta says so.

DETERMINISTIC + NETWORK-FREE, byte-exact reproducible → carries --check (the gate runs it). Inputs
absent → build() returns None, --check skip-passes.

Usage:
  python3 build_competitor_census.py            # write platform/data/competitors_census.json
  python3 build_competitor_census.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, math, os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
OFFICIAL = os.path.join(ROOT, "source-data", "competitors_official.json")  # official-locator pulls
NAT = os.path.join(DATA, "competitors_national.json")   # Google Places sample
OVT = os.path.join(DATA, "competitors_overture.json")   # Overture Places sample
OUT = os.path.join(DATA, "competitors_census.json")

DEDUPE_M = 140.0
CELL_DEG = 0.0025
R_EARTH = 6371000.0


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _items(d):
    if d is None:
        return None
    return d.get("items") if isinstance(d, dict) else d


def _hav(la1, ln1, la2, ln2):
    p = math.pi / 180.0
    a = (math.sin((la2 - la1) * p / 2) ** 2
         + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((ln2 - ln1) * p / 2) ** 2)
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def build():
    official = _load(OFFICIAL)
    nat, ovt = _items(_load(NAT)), _items(_load(OVT))
    if official is None and (nat is None or ovt is None):
        return None

    official_brands = set((official or {}).get("brands", {}).keys()) if official else set()
    out = []

    # 1) OFFICIAL-LOCATOR brands — the full network, used as-is (already deduped upstream).
    endpoints = {}
    for brand in sorted(official_brands):
        entry = official["brands"][brand]
        endpoints[brand] = entry.get("endpoint", "")
        for c in entry.get("coords", []):
            try:
                la, ln = float(c[0]), float(c[1])
            except (TypeError, ValueError, IndexError):
                continue
            out.append({"brand": brand, "name": "", "lat": round(la, 6), "lng": round(ln, 6),
                        "prov": "", "src": "official-locator"})

    # 2) SAMPLE fallback — only for brands NOT covered by an official pull.
    #    Union Google ∪ Overture, deduped within-brand by proximity; skip official brands entirely.
    grid = {}
    added_sample = 0

    def _cell(brand, la, ln):
        return (brand, int(math.floor(la / CELL_DEG)), int(math.floor(ln / CELL_DEG)))

    def _is_dup(brand, la, ln):
        gx, gy = int(math.floor(la / CELL_DEG)), int(math.floor(ln / CELL_DEG))
        for dgx in (-1, 0, 1):
            for dgy in (-1, 0, 1):
                for (pla, pln) in grid.get((brand, gx + dgx, gy + dgy), ()):
                    if _hav(la, ln, pla, pln) <= DEDUPE_M:
                        return True
        return False

    for src_name, items in (("google", nat or []), ("overture", ovt or [])):
        for it in items:
            brand = it.get("brand") or "?"
            if brand in official_brands:
                continue  # official pull already has this brand's full network
            try:
                la, ln = float(it.get("lat")), float(it.get("lng"))
            except (TypeError, ValueError):
                continue
            if _is_dup(brand, la, ln):
                continue
            out.append({"brand": brand, "name": (it.get("name") or "").strip(),
                        "lat": round(la, 6), "lng": round(ln, 6),
                        "prov": (it.get("prov") or "").strip(), "src": src_name})
            grid.setdefault(_cell(brand, la, ln), []).append((la, ln))
            added_sample += 1

    out.sort(key=lambda r: (r["brand"], r["lat"], r["lng"], r["src"]))

    by_brand = Counter(r["brand"] for r in out)
    by_src = Counter(r["src"] for r in out)
    meta = {
        "generated_by": "pipeline/build_competitor_census.py",
        "label": "MERGED measured competitor census — official store-locator networks where we could "
                 "pull them (Srisawad, Tidlor, Muangthai — the FULL networks), plus a Google∪Overture "
                 "sample for brands we couldn't (Heng). This is what the 3D scene / map load.",
        "source": "MEASURED. Official-locator brands: each operator's live branch endpoint "
                  "(source-data/competitors_official.json). Sample brands: competitors_national.json "
                  "(Google Places) ∪ competitors_overture.json (Overture Places), deduped by proximity. "
                  "Every point is a real coordinate; no synthesis.",
        "official_locator_brands": sorted(official_brands),
        "official_endpoints": endpoints,
        "dedupe": "official-locator sets are used as-is (deduped upstream at 5dp); sample brands are "
                  "deduped within-brand at %dm." % int(DEDUPE_M),
        "counts": {"total": len(out), "by_brand": dict(sorted(by_brand.items())), "by_source": dict(by_src)},
        "gaps": [
            "Heng Leasing is a SAMPLE (Google∪Overture), not its full network — its official locator "
            "sits behind a Cloudflare challenge unsolvable from a headless cloud IP (archived "
            "countBranch.php reported ~852 branches). Needs a residential/Thai browser session.",
            "Official-locator counts list every service point/sub-branch, so they can slightly exceed "
            "a company's headline branch count (e.g. Muangthai 8,931 vs FY2025 headline 8,673).",
        ],
    }
    return {"meta": meta, "items": out}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: competitor source files absent — census not checkable")
            return 0
        print("missing input: needs source-data/competitors_official.json OR the Google+Overture samples.")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        print("OK: competitors_census.json reproduces (%d rivals)" % obj["meta"]["counts"]["total"])
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    c = obj["meta"]["counts"]
    print("wrote %d rivals -> platform/data/competitors_census.json" % c["total"])
    print("  by brand: %s" % c["by_brand"])
    print("  by source: %s" % c["by_source"])
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="merge official-locator + sample competitor censuses")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
