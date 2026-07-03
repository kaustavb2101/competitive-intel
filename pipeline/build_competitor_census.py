#!/usr/bin/env python3
"""
build_competitor_census.py — MERGE the two measured competitor censuses into one deduped layer.

THE PROBLEM THIS FIXES
----------------------
The repo carries TWO measured rival-branch censuses:
  - competitors_national.json  (Google Places, 2,556 pts) — the one the 3D scene / map actually load
  - competitors_overture.json  (Overture Places, 2,458 pts) — NOT loaded anywhere in the UI
Each source misses branches the other found (Google caps ~60 hits/query/province; Overture has a
different, complementary sample). Loading only Google understates rival density by ~1,900 real
branches. This builder UNIONS both, de-duplicates by brand + coordinate proximity, and writes one
census the UI loads instead — so the map shows every measured rival we have, not one source's slice.

MEASURED vs ESTIMATED
---------------------
  MEASURED   every point: a real Google Places or Overture Places branch coordinate. No synthesis.
  ESTIMATED  nothing. The only operation is a UNION + a proximity DEDUPE (two same-brand points
             within DEDUPE_M metres are treated as the same physical branch; the richer record —
             the one carrying a province/name — is kept). Documented in meta.

STILL A LOWER BOUND
-------------------
Even merged this is a sample, not a registry — e.g. MTC's public FY2025 total is 8,673 vs the few
thousand mapped (see competitor_coverage.json). The true 100% needs each operator's official
store-locator (pull_competitor_branches.py, run from a Thai IP). meta.gaps says so.

DETERMINISTIC + NETWORK-FREE: no network, no wall clock. Byte-exact reproducible → carries --check
(the QA gate runs it). Inputs absent in a stripped sandbox: build() returns None, --check skip-passes.

Usage:
  python3 build_competitor_census.py            # write platform/data/competitors_census.json
  python3 build_competitor_census.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
NAT = os.path.join(DATA, "competitors_national.json")   # Google Places
OVT = os.path.join(DATA, "competitors_overture.json")   # Overture Places
OUT = os.path.join(DATA, "competitors_census.json")

DEDUPE_M = 140.0       # two same-brand points within this many metres = the same branch
CELL_DEG = 0.0025      # ~275m grid cell for the dedupe spatial index
R_EARTH = 6371000.0


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("items") if isinstance(d, dict) else d


def _hav(la1, ln1, la2, ln2):
    p = math.pi / 180.0
    a = (math.sin((la2 - la1) * p / 2) ** 2
         + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((ln2 - ln1) * p / 2) ** 2)
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def _norm(it, src):
    la, ln = it.get("lat"), it.get("lng")
    try:
        la, ln = float(la), float(ln)
    except (TypeError, ValueError):
        return None
    return {"brand": it.get("brand") or "?", "name": (it.get("name") or "").strip(),
            "lat": round(la, 6), "lng": round(ln, 6), "prov": (it.get("prov") or "").strip(),
            "src": src}


def build():
    nat, ovt = _load(NAT), _load(OVT)
    if nat is None or ovt is None:
        return None

    # base = the Google census (richer names + province); index it by brand+cell for dedupe.
    grid = {}
    out = []
    for it in nat:
        rec = _norm(it, "google")
        if rec is None:
            continue
        out.append(rec)
        cell = (rec["brand"], int(math.floor(rec["lat"] / CELL_DEG)), int(math.floor(rec["lng"] / CELL_DEG)))
        grid.setdefault(cell, []).append((rec["lat"], rec["lng"]))

    def is_dup(brand, la, ln):
        gx, gy = int(math.floor(la / CELL_DEG)), int(math.floor(ln / CELL_DEG))
        for dgx in (-1, 0, 1):
            for dgy in (-1, 0, 1):
                for (pla, pln) in grid.get((brand, gx + dgx, gy + dgy), ()):
                    if _hav(la, ln, pla, pln) <= DEDUPE_M:
                        return True
        return False

    # add Overture points that are NOT already represented (same brand within DEDUPE_M).
    added = 0
    for it in ovt:
        rec = _norm(it, "overture")
        if rec is None:
            continue
        if is_dup(rec["brand"], rec["lat"], rec["lng"]):
            continue
        out.append(rec)
        cell = (rec["brand"], int(math.floor(rec["lat"] / CELL_DEG)), int(math.floor(rec["lng"] / CELL_DEG)))
        grid.setdefault(cell, []).append((rec["lat"], rec["lng"]))
        added += 1

    # deterministic order: brand, then lat, then lng, then source (stable regardless of input order)
    out.sort(key=lambda r: (r["brand"], r["lat"], r["lng"], r["src"]))

    from collections import Counter
    by_brand = Counter(r["brand"] for r in out)
    by_src = Counter(r["src"] for r in out)
    meta = {
        "generated_by": "pipeline/build_competitor_census.py",
        "label": "MERGED measured competitor census — the UNION of the Google Places and Overture "
                 "Places rival-branch censuses, de-duplicated by brand + %dm proximity. This is what "
                 "the 3D scene / map load, so every measured rival we have is shown, not one source's "
                 "slice." % int(DEDUPE_M),
        "source": "MEASURED — competitors_national.json (Google Places) UNION competitors_overture.json "
                  "(Overture Places); each point is a real pulled branch coordinate, no synthesis.",
        "dedupe": "two same-brand points within %dm are the same physical branch; the Google record "
                  "(richer name/province) is kept, the Overture duplicate dropped." % int(DEDUPE_M),
        "counts": {"total": len(out), "by_brand": dict(sorted(by_brand.items())),
                   "by_source": dict(by_src), "overture_added": added,
                   "national_in": len(nat), "overture_in": len(ovt)},
        "gaps": [
            "STILL A LOWER BOUND, not a registry: Google caps ~60 hits/query/province and Overture is "
            "a sample. Public reports put the real totals far higher (e.g. MTC FY2025 = 8,673) — see "
            "competitor_coverage.json. The true 100% per brand needs each operator's official "
            "store-locator: pipeline/pull_competitor_branches.py, run from a Thai IP (MTC & Sawad are "
            "geo-blocked from the cloud sandbox).",
        ],
    }
    return {"meta": meta, "items": out}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: competitors_national.json / competitors_overture.json absent — census not checkable")
            return 0
        print("missing input: needs platform/data/competitors_national.json + competitors_overture.json.")
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
    print("wrote %d rivals -> platform/data/competitors_census.json "
          "(national %d + %d new overture)" % (c["total"], c["national_in"], c["overture_added"]))
    print("  by brand: %s" % c["by_brand"])
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="merge the two measured competitor censuses (deduped)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
