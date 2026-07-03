#!/usr/bin/env python3
"""
build_rival_density.py — WHERE COMPETITORS OWN GROUND (objective #2, district granularity)
==========================================================================================

THE QUESTION THIS ANSWERS
-------------------------
Objective #2 is "where to expand". White-space (amphoe.json) says where demand is
under-served by AutoX. This layer answers the sharper question: in which districts do
our RIVALS already own the ground? For every one of the 928 amphoe (districts) it puts
our AutoX branch count next to the MEASURED count of competitor branches, computes the
rival:AutoX ratio, and flags the two shapes of ceded ground:
  - OUTNUMBERED         AutoX is present (>=1 branch) but rivals outnumber us.
  - ABSENT_RIVAL_DENSE  AutoX has zero branches yet rivals cluster there (>= DENSE_THRESH)
                        — white-space with incumbents already dug in.

MEASURED vs ESTIMATED (the data-mandate — stated explicitly, repeated in meta)
------------------------------------------------------------------------------
  MEASURED   autox    per-district AutoX branch count, carried verbatim from
                      amphoe.json .branches (point-in-polygon of branches_final.json into
                      th_amphoe.geojson — build_amphoe.py). NOT recomputed here.
  MEASURED   rivals   per-district competitor branch count. Every rival is a real pulled
             by_brand branch coordinate from platform/data/competitors_census.json .items
                      (the MERGED Google Places UNION Overture census, ~4,384 points, no
                      synthesis). Assigned to a district by the SAME ray-casting point-in-
                      polygon join build_amphoe.py uses for AutoX branches (so a rival and a
                      branch at the same spot land in the same district — a fair ratio),
                      with a nearest-centroid fallback for the handful of points that sit
                      off every polygon (coast/border geometry).
  COMPUTED   ratio    rivals / autox (null when autox == 0 — read rivals + flag instead).
  COMPUTED   flag     the OUTNUMBERED / ABSENT_RIVAL_DENSE threshold below. The inputs are
             /EDITORIAL measured; only the DENSE_THRESH cut is a documented judgement.

HONEST LOWER BOUND: the census is a lower bound, not a registry (Google caps ~60 hits/
query/province; Overture is a sample — public reports put true rival totals far higher, e.g.
MTC FY2025 = 8,673). So rival counts here UNDER-count: a district flagged outnumbered is
conservatively outnumbered, and some un-flagged districts are outnumbered in reality. The
direction of the bias only ever makes AutoX look LESS outnumbered than it is. See meta.gaps.

DETERMINISTIC + NETWORK-FREE: no network, no wall clock, no randomness. Byte-exact
reproducible -> carries --check (the QA gate runs it). Inputs may be absent in a stripped
sandbox: build() returns None, --check skip-passes, a plain run exits non-zero with a clear
message (mirrors build_lead_sites.py / build_catchment_poi.py).

Usage:
  python3 build_rival_density.py            # write platform/data/rival_density.json
  python3 build_rival_density.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, math, os, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
AMPHOE = os.path.join(DATA, "amphoe.json")
CENSUS = os.path.join(DATA, "competitors_census.json")
GEO = os.path.join(ROOT, "source-data", "th_amphoe.geojson")
OUT = os.path.join(DATA, "rival_density.json")

# A district with ZERO AutoX branches is flagged ABSENT_RIVAL_DENSE when rivals >= this.
# 3 = the national median rival count per district at build time (rivals are a lower bound,
# so this is a conservative "the competition is genuinely dug in here" cut, not noise). It is
# surfaced in meta so it is transparent and tunable.
DENSE_THRESH = 3


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _rings(geom):
    return geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]


def _bbox(geom):
    xs, ys = [], []
    for poly in _rings(geom):
        for x, y in poly[0]:
            xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _pip(x, y, ring):
    inside = False; n = len(ring); j = n - 1
    for i in range(n):
        xi, yi = ring[i]; xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _contains(geom, x, y):
    for poly in _rings(geom):
        if _pip(x, y, poly[0]) and not any(_pip(x, y, h) for h in poly[1:]):
            return True
    return False


def _centroid(geom):
    xs, ys = [], []
    for poly in _rings(geom):
        for x, y in poly[0]:
            xs.append(x); ys.append(y)
    return round(sum(xs) / len(xs), 4), round(sum(ys) / len(ys), 4)


def _hav(la1, lo1, la2, lo2):
    R = 6371.0; p = math.pi / 180
    a = (0.5 - math.cos((la2 - la1) * p) / 2
         + math.cos(la1 * p) * math.cos(la2 * p) * (1 - math.cos((lo2 - lo1) * p)) / 2)
    return 2 * R * math.asin(math.sqrt(a))


def build():
    for p in (AMPHOE, CENSUS, GEO):
        if not os.path.exists(p):
            return None
    amp = _load(AMPHOE)["amphoe"]
    census = _load(CENSUS)
    items = census.get("items", [])
    features = _load(GEO)["features"]

    # fixed, deterministic brand order (alphabetical over the brands actually in the census)
    brands = sorted({it["brand"] for it in items})

    # ── assign each rival to a district (shapeID) ────────────────────────────────
    # SAME ray-casting PIP + bbox prefilter build_amphoe.py used for AutoX branches, so
    # rival and branch district assignment share one geometry definition. Points off every
    # polygon (coast/border) fall back to the nearest polygon centroid (geometric).
    polys = [(f, _bbox(f["geometry"])) for f in features]
    centroids = [(_centroid(f["geometry"]), f["properties"]["shapeID"]) for f in features]
    rivct = collections.Counter()                                   # shapeID -> rival count
    rivbrand = collections.defaultdict(lambda: collections.Counter())  # shapeID -> brand -> count
    n_fallback = 0
    for it in items:
        x, y = float(it["lng"]), float(it["lat"])
        sid = None
        for f, (x0, y0, x1, y1) in polys:
            if x0 <= x <= x1 and y0 <= y <= y1 and _contains(f["geometry"], x, y):
                sid = f["properties"]["shapeID"]
                break
        if sid is None:
            (_cx, _cy), sid = min(centroids, key=lambda c: _hav(y, x, c[0][1], c[0][0]))
            n_fallback += 1
        rivct[sid] += 1
        rivbrand[sid][it["brand"]] += 1

    # ── per-district records, INDEX-ALIGNED to amphoe.json .amphoe order ─────────
    recs = []
    n_outnumbered = n_absent_dense = n_covered = 0
    for r in amp:
        sid = r["id"]
        autox = r["branches"]
        rivals = rivct.get(sid, 0)
        by_brand = {b: rivbrand[sid][b] for b in brands if rivbrand[sid][b]}
        ratio = round(rivals / autox, 2) if autox > 0 else None
        if autox > 0 and rivals > autox:
            flag = "outnumbered"; n_outnumbered += 1
        elif autox == 0 and rivals >= DENSE_THRESH:
            flag = "absent_rival_dense"; n_absent_dense += 1
        else:
            flag = ""
            if autox > 0 and rivals <= autox:
                n_covered += 1
        recs.append({
            "id": sid,
            "name": r["name"],
            "province_th": r["province_th"],
            "region": r["region"],
            "autox": autox,
            "rivals": rivals,
            "by_brand": by_brand,
            "ratio": ratio,
            "flag": flag,
        })

    n_rivals_assigned = sum(rivct.values())
    meta = {
        "generated_by": "pipeline/build_rival_density.py",
        "label": "RIVAL DENSITY per district — MEASURED AutoX vs MEASURED competitor branch "
                 "counts for all 928 amphoe, with the rival:AutoX ratio and the districts where "
                 "competitors own the ground (outnumbered, or absent-but-rival-dense).",
        "objective": "Acquisition (objective #2): find where rivals already hold the district so "
                     "expansion can contest ceded ground, not just empty white-space.",
        "provenance": {
            "autox": "MEASURED — per-district AutoX branch count carried verbatim from "
                     "amphoe.json .branches (point-in-polygon of branches_final.json into "
                     "th_amphoe.geojson, build_amphoe.py). Not recomputed here.",
            "rivals": "MEASURED — real pulled competitor branch coordinates from "
                      "platform/data/competitors_census.json .items (the merged Google Places "
                      "UNION Overture census, %d points, no synthesis), assigned to districts by "
                      "the same ray-casting point-in-polygon join build_amphoe.py uses for AutoX "
                      "branches; %d point(s) off every polygon fell back to the nearest polygon "
                      "centroid (geometric)." % (len(items), n_fallback),
            "by_brand": "MEASURED — per-brand split of the same rival census points.",
            "ratio": "COMPUTED — rivals / autox, rounded 2 dp; null where autox == 0 (AutoX absent; "
                     "read rivals + flag instead of dividing by zero).",
            "flag": "COMPUTED / EDITORIAL — 'outnumbered' when autox>=1 and rivals>autox; "
                    "'absent_rival_dense' when autox==0 and rivals>=DENSE_THRESH (%d); else ''. "
                    "The counts are measured; only the DENSE_THRESH cut is judgement." % DENSE_THRESH,
        },
        "join_method": "ray-casting point-in-polygon (th_amphoe.geojson) with a bbox prefilter — "
                       "identical to build_amphoe.py's branch join so AutoX and rival counts share "
                       "one geometry; nearest-centroid fallback for off-polygon points. shapely is "
                       "available but deliberately NOT used, to keep rival/branch assignment "
                       "byte-identical to the committed AutoX join.",
        "index_note": "records[] is INDEX-ALIGNED to platform/data/amphoe.json .amphoe "
                      "(record i <-> amphoe i, same .id) — join by position or by id.",
        "dense_thresh": DENSE_THRESH,
        "brands": brands,
        "record_format": "{id, name, province_th, region, autox, rivals, by_brand{brand:count}, "
                         "ratio, flag}. by_brand omits zero-count brands; brand order fixed "
                         "(alphabetical).",
        "gaps": [
            "The rival census is a LOWER BOUND, not a registry (Google caps ~60 hits/query/"
            "province; Overture is a sample — public reports put true totals far higher, e.g. "
            "MTC FY2025 = 8,673). Rival counts here UNDER-count, so 'outnumbered' is conservative "
            "and some un-flagged districts are outnumbered in reality; the bias only ever makes "
            "AutoX look LESS outnumbered than it is. A true 100% census needs each operator's "
            "official store-locator (pull_competitor_branches.py, from a Thai IP).",
            "Only the 4 big compliant brands (%s) are censused; sub-scale local operators are not, "
            "so this is big-4 density, not total competitive density." % ", ".join(brands),
        ],
        "n_districts": len(recs),
        "n_rivals_assigned": n_rivals_assigned,
        "n_offpolygon_fallback": n_fallback,
        "n_outnumbered": n_outnumbered,
        "n_absent_rival_dense": n_absent_dense,
        "n_districts_with_rivals": sum(1 for r in recs if r["rivals"] > 0),
        "n_autox_covered_or_parity": n_covered,
        "total_autox": sum(r["autox"] for r in recs),
        "total_rivals": n_rivals_assigned,
    }
    return {"meta": meta, "records": recs}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: amphoe.json / competitors_census.json / th_amphoe.geojson absent — "
                  "rival_density not checkable (optional layer)")
            return 0
        print("missing input: needs platform/data/amphoe.json + "
              "platform/data/competitors_census.json + source-data/th_amphoe.geojson.")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        m = obj["meta"]
        print("OK: rival_density.json reproduces (%d districts, %d rivals, %d outnumbered, "
              "%d absent-rival-dense)" % (m["n_districts"], m["n_rivals_assigned"],
                                          m["n_outnumbered"], m["n_absent_rival_dense"]))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d districts -> platform/data/rival_density.json (%.0f KB)"
          % (m["n_districts"], len(text.encode("utf-8")) / 1024))
    print("  rivals assigned: %d (%d off-polygon fallback) | AutoX total: %d"
          % (m["n_rivals_assigned"], m["n_offpolygon_fallback"], m["total_autox"]))
    print("  outnumbered: %d | absent-rival-dense: %d | with rivals: %d"
          % (m["n_outnumbered"], m["n_absent_rival_dense"], m["n_districts_with_rivals"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="district rival-density layer (AutoX vs measured competitor branches)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
