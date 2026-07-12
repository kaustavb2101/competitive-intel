#!/usr/bin/env python3
"""
build_peer_province.py — PEER COMPARISON per province (objective #2, brand granularity)
=======================================================================================

THE QUESTION THIS ANSWERS
-------------------------
The competition surface already has two peer reads: a NATIONAL brand-total board
(competitor_coverage.json — one row per brand for the whole country) and a per-DISTRICT
merged-rival board (rival_density.json — 928 amphoe, all rivals summed into one "rivals"
number). Neither answers the question a strategy director actually asks about the existing
footprint province by province: "in THIS province, how does our branch count stack up
against Muangthai, against Srisawad, against Tidlor, against Heng — one brand at a time —
and who leads the ground here?"

This layer rolls the MEASURED per-district rival census up to the 77 provinces and keeps the
per-BRAND split intact, so each province shows AutoX next to every rival brand separately,
the province-level rival:AutoX ratio, the leading operator, and how many of the province's
districts AutoX is outnumbered in. A competitive-pressure read on the network we already run
— it makes NO open / close / expand recommendation.

MEASURED vs ESTIMATED (the data-mandate — stated explicitly, repeated in meta)
------------------------------------------------------------------------------
Everything here is a pure, deterministic ROLLUP of platform/data/rival_density.json (itself
gated, --check-reproducible), so provenance is inherited verbatim:
  MEASURED   autox      per-province AutoX branch count = sum of the district .autox counts
                        (point-in-polygon of branches_final.json into th_amphoe.geojson,
                        build_amphoe.py). NOT recomputed here.
  MEASURED   by_brand   per-province, per-brand rival count = sum of the district .by_brand
                        splits (real pulled competitor branch coordinates from the merged
                        official-locator UNION Google/Overture census). NOT recomputed here.
  COMPUTED   rivals     sum of by_brand for the province.
  COMPUTED   ratio      rivals / autox (null when autox == 0).
  COMPUTED   leader     the operator with the most branches in the province among
                        {AutoX} + rival brands ("AutoX" or a brand name); ties break by the
                        fixed alphabetical brand order with AutoX first.
  COMPUTED   n_outnumbered_districts
                        how many of the province's districts carry rival_density's
                        'outnumbered' flag (AutoX present but outnumbered).

INHERITED CAVEATS (do not restate as if new): the rival census is a LOWER BOUND (Google caps
~60/query/province; Heng is a Google/Overture SAMPLE because its locator is Cloudflare-blocked
— Muangthai/Srisawad/Tidlor are near-complete official-locator networks). AutoX district
counts are point-in-polygon, so a handful of branches that fall off every amphoe polygon are
not assigned (rival_density total_autox = 2000 vs 2015 committed) — the shortfall is disclosed
in rival_density.json .meta and carried forward here, NOT silently reconciled.

DETERMINISTIC + NETWORK-FREE: reads one committed file, no network, no wall clock, no
randomness. Byte-exact reproducible -> carries --check (the QA gate runs it). Input may be
absent in a stripped sandbox: build() returns None, --check skip-passes, a plain run exits
non-zero with a clear message (mirrors build_rival_density.py).

Usage:
  python3 build_peer_province.py            # write platform/data/peer_province.json
  python3 build_peer_province.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, os, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
RIVDEN = os.path.join(DATA, "rival_density.json")
OUT = os.path.join(DATA, "peer_province.json")


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build():
    if not os.path.exists(RIVDEN):
        return None
    rd = _load(RIVDEN)
    recs = rd.get("records", [])
    rd_meta = rd.get("meta", {})
    # fixed brand order carried verbatim from rival_density (alphabetical over the census)
    brands = list(rd_meta.get("brands", []))

    # ── roll the 928 district records up to their province ───────────────────────
    # province_th is the join key; region is carried from the first district seen (all
    # districts in a province share one region in amphoe.json).
    prov = collections.OrderedDict()
    for r in recs:
        p = r.get("province_th") or ""
        if p not in prov:
            prov[p] = {
                "province_th": p,
                "region": r.get("region", ""),
                "autox": 0,
                "by_brand": collections.Counter(),
                "n_districts": 0,
                "n_outnumbered_districts": 0,
            }
        e = prov[p]
        e["autox"] += r.get("autox", 0)
        for b, c in (r.get("by_brand") or {}).items():
            e["by_brand"][b] += c
        e["n_districts"] += 1
        if r.get("flag") == "outnumbered":
            e["n_outnumbered_districts"] += 1

    provinces = []
    for e in prov.values():
        by_brand = {b: e["by_brand"][b] for b in brands if e["by_brand"][b]}
        rivals = sum(by_brand.values())
        autox = e["autox"]
        ratio = round(rivals / autox, 2) if autox > 0 else None
        # leader = the single operator holding the most ground in the province.
        # AutoX competes as one "brand"; ties break by fixed order (AutoX first, then the
        # census's alphabetical brand order) so the result is deterministic.
        order = ["AutoX"] + brands
        counts = {"AutoX": autox, **by_brand}
        leader = max(order, key=lambda k: (counts.get(k, 0), -order.index(k)))
        provinces.append({
            "province_th": e["province_th"],
            "region": e["region"],
            "autox": autox,
            "rivals": rivals,
            "by_brand": by_brand,
            "ratio": ratio,
            "leader": leader,
            "n_districts": e["n_districts"],
            "n_outnumbered_districts": e["n_outnumbered_districts"],
        })

    # rank most-contested first: raw branch deficit (rivals − autox) desc, then province_th
    # asc for a stable tiebreak. This mirrors the district board's "most outnumbered first".
    provinces.sort(key=lambda p: (-(p["rivals"] - p["autox"]), p["province_th"]))

    n_autox_leads = sum(1 for p in provinces if p["leader"] == "AutoX")
    n_outnumbered_prov = sum(1 for p in provinces if p["autox"] > 0 and p["rivals"] > p["autox"])
    total_autox = sum(p["autox"] for p in provinces)
    total_rivals = sum(p["rivals"] for p in provinces)
    per_brand_total = {b: sum(p["by_brand"].get(b, 0) for p in provinces) for b in brands}

    meta = {
        "generated_by": "pipeline/build_peer_province.py",
        "label": "PEER COMPARISON per province — MEASURED AutoX branch count next to each big-4 "
                 "rival brand (Muangthai / Srisawad / Tidlor / Heng) separately, for all 77 "
                 "provinces, with the province rival:AutoX ratio, the leading operator, and how "
                 "many districts AutoX is outnumbered in.",
        "objective": "Competitive risk (objective #2): a per-province, per-brand read on the "
                     "footprint we ALREADY run — where each rival brand is densest around our "
                     "branches. Makes NO open / close / expand recommendation.",
        "provenance": {
            "source_file": "platform/data/rival_density.json (rolled up district -> province; "
                           "gated, --check-reproducible). Nothing is recomputed from raw geometry "
                           "here — this layer is a pure aggregation of that file's records.",
            "autox": "MEASURED — sum of district .autox (point-in-polygon of branches_final.json "
                     "into th_amphoe.geojson, build_amphoe.py). Inherited verbatim.",
            "by_brand": "MEASURED — sum of district .by_brand (real pulled competitor branch "
                        "coordinates from the merged official-locator UNION Google/Overture "
                        "census). Inherited verbatim; per-brand split preserved.",
            "rivals": "COMPUTED — sum of by_brand for the province.",
            "ratio": "COMPUTED — rivals / autox, rounded 2 dp; null where autox == 0.",
            "leader": "COMPUTED — the operator (AutoX or a rival brand) with the most branches "
                      "in the province; deterministic tie-break (AutoX first, then census order).",
            "n_outnumbered_districts": "COMPUTED — count of the province's districts flagged "
                                       "'outnumbered' in rival_density.json.",
        },
        "caveats": [
            "The rival census is a LOWER BOUND: Muangthai / Srisawad / Tidlor are near-complete "
            "official-locator networks, but Heng is a Google/Overture SAMPLE (its locator is "
            "Cloudflare-blocked), so Heng per-province counts under-count more than the others. "
            "Only the 4 big compliant brands are censused — sub-scale local operators are not, so "
            "this is big-4 density, not total competitive density.",
            "AutoX per-province counts are point-in-polygon, so branches that fall off every "
            "amphoe polygon are unassigned: total_autox here = %d vs 2015 committed branches "
            "(the shortfall is disclosed in rival_density.json .meta and carried forward, not "
            "silently reconciled)." % total_autox,
            "A high rival:AutoX ratio is a competitive-pressure signal on the EXISTING network, "
            "not an expansion cue and not a verdict.",
        ],
        "brands": brands,
        "record_format": "{province_th, region, autox, rivals, by_brand{brand:count}, ratio, "
                         "leader, n_districts, n_outnumbered_districts}. by_brand omits "
                         "zero-count brands; provinces[] sorted by (rivals-autox) desc.",
        "n_provinces": len(provinces),
        "n_provinces_autox_leads": n_autox_leads,
        "n_provinces_outnumbered": n_outnumbered_prov,
        "total_autox": total_autox,
        "total_rivals": total_rivals,
        "per_brand_total": per_brand_total,
        "rival_density_source": {
            "n_districts": rd_meta.get("n_districts"),
            "total_autox": rd_meta.get("total_autox"),
            "total_rivals": rd_meta.get("total_rivals"),
        },
    }
    return {"meta": meta, "provinces": provinces}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            print("SKIP: rival_density.json absent — peer_province not checkable (optional layer)")
            return 0
        print("missing input: needs platform/data/rival_density.json "
              "(run: python3 build_rival_density.py).")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, ROOT))
            return 1
        m = obj["meta"]
        print("OK: peer_province.json reproduces (%d provinces, %d outnumbered, AutoX leads %d)"
              % (m["n_provinces"], m["n_provinces_outnumbered"], m["n_provinces_autox_leads"]))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print("wrote %d provinces -> platform/data/peer_province.json (%.0f KB)"
          % (m["n_provinces"], len(text.encode("utf-8")) / 1024))
    print("  AutoX total: %d | rivals total: %d | per-brand: %s"
          % (m["total_autox"], m["total_rivals"],
             ", ".join("%s %d" % (b, n) for b, n in m["per_brand_total"].items())))
    print("  provinces AutoX leads: %d | provinces outnumbered: %d"
          % (m["n_provinces_autox_leads"], m["n_provinces_outnumbered"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="per-province per-brand peer comparison (AutoX vs each big-4 rival)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
