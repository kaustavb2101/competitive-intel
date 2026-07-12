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
import argparse, json, math, os, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
SRC = os.path.join(ROOT, "source-data")
OFFICIAL = os.path.join(ROOT, "source-data", "competitors_official.json")  # official-locator pulls
NAT = os.path.join(DATA, "competitors_national.json")   # Google Places sample
OVT = os.path.join(DATA, "competitors_overture.json")   # Overture Places sample
OUT = os.path.join(DATA, "competitors_census.json")
AMPHOE = os.path.join(SRC, "th_amphoe.geojson")         # 928 ADM2 district polygons (shapeName/shapeID)
BRANCHES = os.path.join(SRC, "branches_final.json")     # AutoX master (each branch has a real prov)

DEDUPE_M = 140.0
CELL_DEG = 0.0025
R_EARTH = 6371000.0

# Reverse-geocode machinery (Part A): reuse build_province's pure point-in-polygon helpers so every
# census point gets a real province + district from its coordinates. Everything here is pure
# arithmetic (PIP + planar-degree argmin + string ops) — NO transcendental math — so the enrichment
# is byte-identical across Python versions AND platforms (the committed census is gate-checked on
# Linux/3.11 while it may be regenerated on Windows/3.14). canonical() folds raw prov strings to the
# 77 canonical Thai names.
sys.path.insert(0, HERE)
from regionmap import canonical
from build_province import _rings, _bbox, _pip, _contains, _centroid  # noqa: E402  (pure PIP helpers)


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


# ── reverse-geocode: point -> (canonical province, amphoe/district) ────────────────────────────
def _amphoe_geo():
    """Build the geocoding index from the real data. Returns:
       polys   — [(feature, bbox), ...] for all 928 amphoe polygons (bbox-prefilter order = file order)
       amph_prov — {shapeID: canonical province}, derived like build_province: PIP every AutoX branch
                   into its amphoe, then each amphoe's province = the MAJORITY canonical(prov) of the
                   branches inside it (ties broken lexicographically → deterministic).
       mapped  — [(shapeID, shapeName, prov, cx, cy), ...] centroids of the MAPPED amphoes only, for
                 the nearest-centroid province fallback (points that miss every polygon).
       Returns (None, None, None) if a source is absent (env-broken) → geocoding is skipped."""
    ageo = _load(AMPHOE)
    master = _load(BRANCHES)
    if ageo is None or master is None:
        return None, None, None
    feats = ageo["features"]
    polys = [(f, _bbox(f["geometry"])) for f in feats]
    votes = defaultdict(Counter)
    for b in master:
        x, y = b.get("lng"), b.get("lat")
        if x is None or y is None:
            continue
        for f, (x0, y0, x1, y1) in polys:
            if x0 <= x <= x1 and y0 <= y <= y1 and _contains(f["geometry"], x, y):
                votes[f["properties"]["shapeID"]][canonical(b.get("prov", ""))] += 1
                break
    amph_prov = {}
    for sid, c in votes.items():
        best = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]  # top count, tie→lex-smallest
        if best:                                                        # skip amphoe whose votes are all blank
            amph_prov[sid] = best
    mapped = []
    for f, _bb in polys:
        sid = f["properties"]["shapeID"]
        if sid in amph_prov:
            cx, cy = _centroid(f["geometry"])                          # (lng, lat), rounded 4dp
            mapped.append((sid, f["properties"]["shapeName"], amph_prov[sid], cx, cy))
    return polys, amph_prov, mapped


def _nearest_mapped(la, ln, mapped):
    """Nearest mapped-amphoe centroid by PLANAR squared-degree distance (pure +/-/* → platform-stable;
    Thailand-scale distortion never changes the argmin here). Ties broken by shapeID. Returns prov."""
    best_sid = None; best_prov = ""; best_d2 = None
    for (sid, _name, prov, cx, cy) in mapped:
        dx = cx - ln; dy = cy - la; d2 = dx * dx + dy * dy
        if best_d2 is None or d2 < best_d2 or (d2 == best_d2 and sid < best_sid):
            best_d2 = d2; best_sid = sid; best_prov = prov
    return best_prov


def _geocode(rows, geo):
    """Stamp each census row with a real prov (canonical Thai) + amphoe (district shapeName), derived
    purely from its coordinates. amphoe is set ONLY on an actual PIP hit (honest — no district guessed
    for a point outside every polygon); prov falls back to the nearest mapped centroid. Returns a
    Counter of how points resolved."""
    polys, amph_prov, mapped = geo
    cats = Counter()
    if polys is None:                                     # source absent → leave fields blank, count all
        for r in rows:
            r["prov"] = ""; r["amphoe"] = ""; cats["source_absent"] += 1
        return cats
    for r in rows:
        la, ln = r["lat"], r["lng"]
        found = None
        for f, (x0, y0, x1, y1) in polys:
            if x0 <= ln <= x1 and y0 <= la <= y1 and _contains(f["geometry"], ln, la):
                found = f; break
        if found is not None:
            r["amphoe"] = found["properties"]["shapeName"]
            sid = found["properties"]["shapeID"]
            if sid in amph_prov:
                r["prov"] = amph_prov[sid]; cats["in_polygon"] += 1
            else:                                          # inside a real district with no AutoX branch
                r["prov"] = _nearest_mapped(la, ln, mapped); cats["polygon_prov_fallback"] += 1
        else:                                              # outside every polygon (coastal/boundary)
            r["prov"] = _nearest_mapped(la, ln, mapped); r["amphoe"] = ""
            cats["centroid_fallback"] += 1
        if not r["prov"]:
            cats["unresolved_prov"] += 1
        if not r["amphoe"]:
            cats["no_amphoe"] += 1
    return cats


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
                        "prov": "", "amphoe": "", "src": "official-locator"})

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
                        "prov": "", "amphoe": "", "src": src_name})  # prov/amphoe filled by _geocode (PIP)
            grid.setdefault(_cell(brand, la, ln), []).append((la, ln))
            added_sample += 1

    # Reverse-geocode every point to (canonical province, amphoe/district) from its real coordinates.
    gcats = _geocode(out, _amphoe_geo())

    out.sort(key=lambda r: (r["brand"], r["lat"], r["lng"], r["src"]))

    by_brand = Counter(r["brand"] for r in out)
    by_src = Counter(r["src"] for r in out)
    by_prov = Counter(r["prov"] for r in out if r["prov"])
    heng_official = "Heng" in official_brands
    if heng_official:
        label = ("MERGED measured competitor census — official store-locator networks for all four "
                 "big brands (Srisawad, Tidlor, Muangthai, Heng — the FULL networks; Heng ingested "
                 "from its own branch-finder via ingest_heng.py). Any remaining sample rows are "
                 "minor brands only. This is what the 3D scene / map load.")
        heng_gap = ("Heng is now the OFFICIAL locator set (province-walk of hengleasing.com from a "
                    "Thai IP via pull_heng_locator.py, merged by ingest_heng.py) — the earlier "
                    "Google∪Overture sample was replaced, not unioned.")
    else:
        label = ("MERGED measured competitor census — official store-locator networks where we could "
                 "pull them (Srisawad, Tidlor, Muangthai — the FULL networks), plus a Google∪Overture "
                 "sample for brands we couldn't (Heng). This is what the 3D scene / map load.")
        heng_gap = ("Heng Leasing is a SAMPLE (Google∪Overture), not its full network — its official locator "
                    "sits behind a Cloudflare challenge unsolvable from a headless cloud IP (archived "
                    "countBranch.php reported ~852 branches). Needs a residential/Thai browser session.")
    meta = {
        "generated_by": "pipeline/build_competitor_census.py",
        "label": label,
        "source": "MEASURED. Official-locator brands: each operator's live branch endpoint "
                  "(source-data/competitors_official.json). Sample brands: competitors_national.json "
                  "(Google Places) ∪ competitors_overture.json (Overture Places), deduped by proximity. "
                  "Every point is a real coordinate; no synthesis.",
        "official_locator_brands": sorted(official_brands),
        "official_endpoints": endpoints,
        "dedupe": "official-locator sets are used as-is (deduped upstream at 5dp); sample brands are "
                  "deduped within-brand at %dm." % int(DEDUPE_M),
        "counts": {"total": len(out), "by_brand": dict(sorted(by_brand.items())), "by_source": dict(by_src),
                   "by_province": dict(sorted(by_prov.items()))},
        "geocode": {
            "method": "Each point reverse-geocoded to its province + district by point-in-polygon over "
                      "the 928 th_amphoe.geojson ADM2 polygons. Each amphoe's province = the majority "
                      "canonical province of the AutoX branches (branches_final.json) inside it. A point "
                      "in a district with no AutoX branch, or outside every polygon, takes the province "
                      "of the nearest mapped district centroid (district left blank when no polygon "
                      "contains the point). Pure PIP + string ops — deterministic, network-free.",
            "resolution": dict(sorted(gcats.items())),
        },
        "gaps": [
            heng_gap,
            "Official-locator counts list every service point/sub-branch, so they can slightly exceed "
            "a company's headline branch count (e.g. Muangthai 8,931 vs FY2025 headline 8,673).",
            "prov/amphoe are reverse-geocoded (point-in-polygon of the real coordinate into the national "
            "ADM2 district polygons), not shipped by the locators — so province rollups are exact, not "
            "bbox approximations.",
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
    g = obj["meta"]["geocode"]["resolution"]
    print("wrote %d rivals -> platform/data/competitors_census.json" % c["total"])
    print("  by brand: %s" % c["by_brand"])
    print("  by source: %s" % c["by_source"])
    print("  geocode resolution: %s" % g)
    bp = c["by_province"]
    print("  provinces resolved: %d  (points with a province: %d)" % (len(bp), sum(bp.values())))
    top = sorted(bp.items(), key=lambda kv: -kv[1])[:15]
    for prov, n in top:
        print("    %-14s %5d" % (prov, n))
    print("  Chon Buri (ชลบุรี) in-province big-4: %d" % bp.get("ชลบุรี", 0))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="merge official-locator + sample competitor censuses")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
