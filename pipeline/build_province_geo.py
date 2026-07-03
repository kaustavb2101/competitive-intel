#!/usr/bin/env python3
"""
build_province_geo.py — province boundary polygons for PROVINCE-resolution map lenses
======================================================================================
Two National-map lenses read a per-PROVINCE value (household DTI `hhdti`, structural
stress `pstress`) but today only paint per-branch dots, so a province with many branches
shows many same-coloured dots instead of one clean shape (tracked in
docs/IMPROVEMENT_BACKLOG.md — "hhdti/pstress lens is province-resolution but only
paints branch dots").

This builder gives those lenses a province polygon layer without a second geometry
simplification pass or a shapely dissolve: it GROUPS the already-simplified amphoe
polygons (platform/data/amphoe_geo.json, built by build_amphoe_geo.py) by their
amphoe.json province_th, and re-emits each province's constituent amphoe rings under
one MultiPolygon feature. Adjacent amphoe share borders, so the grouped shape reads as
the province outline (thin internal amphoe seams are cosmetic, not gaps) — no new
geometry is invented, only regrouped.

    platform/data/province_geo.json

For every one of the 77 provinces:
  - properties.province : Thai name (== amphoe.json province_th == branches.json `v`
    == household_risk_by_province.json / province_stress_index.json `province` key)
  - properties.n_amphoe  : how many amphoe polygons were folded in (context only)
  - geometry             : MultiPolygon, the concatenation of every constituent amphoe's
                           polygon-coordinate arrays (no dissolve, no new vertices)

Deterministic + network-free (reads only committed platform/data/ + amphoe.json).
Carries --check for a byte-exact reproduce, so it belongs in the QA determinism gate.
Degrades gracefully: if amphoe_geo.json is absent, writes nothing and exits 0 (the
frontend already treats a missing province_geo.json as "dots only", same convention as
the amphoe choropleth).

    python3 build_province_geo.py            # write platform/data/province_geo.json
    python3 build_province_geo.py --check     # verify committed output byte-reproduces
"""
import os, json, argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
AMPHOE_GEO = os.path.join(DATA, "amphoe_geo.json")
AMPHOE = os.path.join(DATA, "amphoe.json")
OUT = os.path.join(DATA, "province_geo.json")


def _polys(geom):
    """Return geometry as a list of polygon-coordinate-arrays (each a list of rings),
    uniformly for Polygon or MultiPolygon."""
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return [geom["coordinates"]]


def build():
    if not os.path.exists(AMPHOE_GEO) or not os.path.exists(AMPHOE):
        return None  # optional layer — absent input is not an error

    ageo = json.load(open(AMPHOE_GEO, encoding="utf-8"))
    amphoe = json.load(open(AMPHOE, encoding="utf-8"))
    id_to_prov = {a["id"]: a["province_th"] for a in amphoe.get("amphoe", []) if a.get("id") and a.get("province_th")}

    by_prov = {}  # province_th -> list of polygon-coordinate-arrays
    n_amphoe = {}
    n_unmatched = 0
    for f in ageo.get("features", []):
        aid = (f.get("properties") or {}).get("id")
        prov = id_to_prov.get(aid)
        if not prov:
            n_unmatched += 1
            continue
        by_prov.setdefault(prov, []).extend(_polys(f["geometry"]))
        n_amphoe[prov] = n_amphoe.get(prov, 0) + 1

    out_feats = []
    for prov in sorted(by_prov.keys()):  # deterministic order
        out_feats.append({
            "type": "Feature",
            "properties": {"province": prov, "n_amphoe": n_amphoe[prov]},
            "geometry": {"type": "MultiPolygon", "coordinates": by_prov[prov]},
        })

    obj = {
        "type": "FeatureCollection",
        "meta": {
            "generated_by": "pipeline/build_province_geo.py",
            "source": "platform/data/amphoe_geo.json amphoe polygons, regrouped by amphoe.json province_th",
            "label": "MEASURED boundaries (geometry only), amphoe polygons grouped by province — "
                     "no dissolve, no new vertices; join to hhdti/pstress lens values on "
                     "properties.province (== branches.json `v` Thai province name)",
            "n_features": len(out_feats),
            "n_amphoe_unmatched": n_unmatched,
            "join_key": "properties.province == branches.json branch.v == household_risk_by_province.json "
                        "/ province_stress_index.json `province`",
        },
        "features": out_feats,
    }
    return obj


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: province_geo.json (amphoe_geo.json/amphoe.json not built yet — run build_amphoe_geo.py/build_amphoe.py first)")
            return 0
        print("SKIP: amphoe_geo.json/amphoe.json absent — nothing to build")
        return 0
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, REPO)}")
            return 1
        print(f"OK: province_geo.json reproduces ({obj['meta']['n_features']} provinces)")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print(f"wrote {m['n_features']} province polygons -> platform/data/province_geo.json")
    if m["n_amphoe_unmatched"]:
        print(f"  ({m['n_amphoe_unmatched']} amphoe polygons had no province_th match — skipped, not fabricated)")
    print(f"  size {os.path.getsize(OUT)/1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    raise SystemExit(run(check=a.check))
