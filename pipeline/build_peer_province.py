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
PICO = os.path.join(DATA, "pico_census.json")
VEHICLES = os.path.join(ROOT, "source-data", "vehicles_by_province.json")
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

    # ── optional: fold in the licensed-PICO-finance operator field per province ──────
    # pico_census.json is a MEASURED per-province count of licensed พิโกไฟแนนซ์ operators
    # (FPO registry) — a DISTINCT small-ticket non-bank competitor class from the big-4 title
    # lenders, keyed on province with no coordinates. It is carried as its own column, NOT
    # summed into the coordinate-geometry big-4 `rivals`/`ratio`/`leader` (that would mix a
    # province-count layer into a haversine census). Absent input degrades to pico=None.
    pico_by_prov, pico_zero, pico_meta = {}, set(), {}
    if os.path.exists(PICO):
        pc = _load(PICO)
        pico_meta = pc.get("meta", {})
        pico_by_prov = pc.get("by_province", {}) or {}
        pico_zero = set(pc.get("zero_provinces", []) or [])

    # ── optional: fold in the MEASURED registered-vehicle stock per province ──────────
    # vehicles_by_province.json is the DLT national vehicle census (source-data/, keyed on the
    # same Thai province name). Vehicles are the collateral a title loan is secured against, so
    # the number of title-loan storefronts PER 100k registered vehicles is a market-SATURATION
    # read — how crowded the industry is relative to the addressable collateral base, i.e. a
    # margin-erosion signal (objective #2). Counts stay MEASURED; the ratio is COMPUTED. Absent
    # input degrades to vehicles=None / sat_per_100k=None (an honest gap, not a 0).
    veh_by_prov, veh_src, veh_total = {}, "", 0
    if os.path.exists(VEHICLES):
        vj = _load(VEHICLES)
        veh_by_prov = vj.get("provinces", {}) or {}
        veh_src = vj.get("source", "")
        veh_total = vj.get("n_vehicles", 0) or 0

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
        # AutoX's OWN competitive standing among the operators PRESENT in the province
        # ({AutoX} + every big-4 brand with >0 branches): a 1-based rank by branch count with
        # the SAME deterministic tie-break as `leader` (AutoX ahead on an equal count). This is
        # the read the `leader` column hides: two provinces both "led by Muangthai" can have
        # AutoX sitting 2nd (a defensible runner-up) or dead-last of 4 (a fragmented also-ran)
        # — a sharper margin-pressure signal than the merged ratio alone. MEASURED counts,
        # COMPUTED position; null where autox == 0 (no AutoX branches assigned in the census).
        if autox > 0:
            n_ranked = 1 + len(by_brand)
            autox_rank = 1 + sum(1 for c in by_brand.values() if c > autox)
        else:
            n_ranked = len(by_brand)
            autox_rank = None
        # licensed-PICO operator count for this province: an int when the FPO registry lists
        # the province (or a MEASURED zero when the registry explicitly has none), else null
        # (registry absent in this sandbox, or province unmatched — an honest gap, not a 0).
        pico_row = pico_by_prov.get(e["province_th"])
        if pico_row is not None:
            pico = pico_row.get("total")
        elif e["province_th"] in pico_zero:
            pico = 0
        else:
            pico = None
        # market saturation: title-loan operators (AutoX + big-4 rivals, coordinate census) per
        # 100k MEASURED registered vehicles in the province — how crowded the industry is against
        # the collateral base it lends on. operators_total is a LOWER BOUND (the rival census is),
        # so sat_per_100k is a lower bound too. null where the vehicle stock is absent/zero.
        veh_row = veh_by_prov.get(e["province_th"])
        vehicles = veh_row.get("total") if isinstance(veh_row, dict) else None
        operators_total = autox + rivals
        if vehicles:
            sat_per_100k = round(operators_total / vehicles * 100000, 1)
        else:
            sat_per_100k = None
        provinces.append({
            "province_th": e["province_th"],
            "region": e["region"],
            "autox": autox,
            "rivals": rivals,
            "by_brand": by_brand,
            "ratio": ratio,
            "leader": leader,
            "autox_rank": autox_rank,
            "n_ranked": n_ranked,
            "pico": pico,
            "vehicles": vehicles,
            "operators_total": operators_total,
            "sat_per_100k": sat_per_100k,
            "n_districts": e["n_districts"],
            "n_outnumbered_districts": e["n_outnumbered_districts"],
        })

    # saturation rank (1 = most crowded per 100k vehicles) over the provinces that carry a value;
    # deterministic tie-break by province_th. Written back onto each record; null where no value.
    _sat = sorted([p for p in provinces if p["sat_per_100k"] is not None],
                  key=lambda p: (-p["sat_per_100k"], p["province_th"]))
    for i, p in enumerate(_sat):
        p["sat_rank"] = i + 1
    for p in provinces:
        p.setdefault("sat_rank", None)

    # rank most-contested first: raw branch deficit (rivals − autox) desc, then province_th
    # asc for a stable tiebreak. This mirrors the district board's "most outnumbered first".
    provinces.sort(key=lambda p: (-(p["rivals"] - p["autox"]), p["province_th"]))

    n_autox_leads = sum(1 for p in provinces if p["leader"] == "AutoX")
    n_outnumbered_prov = sum(1 for p in provinces if p["autox"] > 0 and p["rivals"] > p["autox"])
    # AutoX competitive-standing rollup (only provinces where AutoX is present / rankable).
    ranked = [p for p in provinces if p["autox_rank"] is not None]
    n_autox_last = sum(1 for p in ranked if p["n_ranked"] > 1 and p["autox_rank"] == p["n_ranked"])
    n_autox_top2 = sum(1 for p in ranked if p["autox_rank"] <= 2)
    best_autox_rank = min((p["autox_rank"] for p in ranked), default=None)
    # distribution keyed by rank (string keys, sorted asc) — deterministic, JSON-stable.
    rank_counter = collections.Counter(p["autox_rank"] for p in ranked)
    autox_rank_distribution = {str(k): rank_counter[k] for k in sorted(rank_counter)}
    total_autox = sum(p["autox"] for p in provinces)
    total_rivals = sum(p["rivals"] for p in provinces)
    per_brand_total = {b: sum(p["by_brand"].get(b, 0) for p in provinces) for b in brands}
    pico_present = [p for p in provinces if isinstance(p["pico"], int)]
    total_pico = sum(p["pico"] for p in pico_present)
    n_pico_present = sum(1 for p in pico_present if p["pico"] > 0)

    # saturation rollups (only provinces carrying a MEASURED vehicle stock)
    sat_present = [p for p in provinces if p["sat_per_100k"] is not None]
    saturation_available = bool(sat_present)
    total_vehicles = sum(p["vehicles"] for p in sat_present)
    _most = sorted(sat_present, key=lambda p: (-p["sat_per_100k"], p["province_th"]))
    most_saturated = ({
        "province_th": _most[0]["province_th"],
        "sat_per_100k": _most[0]["sat_per_100k"],
        "operators_total": _most[0]["operators_total"],
        "vehicles": _most[0]["vehicles"],
    } if _most else None)
    least_saturated = ({
        "province_th": _most[-1]["province_th"],
        "sat_per_100k": _most[-1]["sat_per_100k"],
        "operators_total": _most[-1]["operators_total"],
        "vehicles": _most[-1]["vehicles"],
    } if _most else None)
    # national baseline: all censused operators (AutoX + big-4) per 100k vehicles nationwide.
    total_operators = sum(p["operators_total"] for p in sat_present)
    national_sat_per_100k = (round(total_operators / total_vehicles * 100000, 1)
                             if total_vehicles else None)

    meta = {
        "generated_by": "pipeline/build_peer_province.py",
        "label": "PEER COMPARISON per province — MEASURED AutoX branch count next to each big-4 "
                 "rival brand (Muangthai / Srisawad / Tidlor / Heng) separately, for all 77 "
                 "provinces, with the province rival:AutoX ratio, the leading operator, how many "
                 "districts AutoX is outnumbered in, plus a MEASURED count of LICENSED PICO-finance "
                 "operators (a distinct small-ticket rival class) carried as its own column.",
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
            "autox_rank": "COMPUTED — AutoX's 1-based rank by branch count among the operators "
                          "PRESENT in the province ({AutoX} + every big-4 brand with >0 branches), "
                          "same deterministic tie-break as `leader` (AutoX ahead on an equal "
                          "count). null where autox == 0. Underlying counts are MEASURED; the "
                          "position is arithmetic. Ranks AutoX only against the 4 big censused "
                          "brands — NOT against sub-scale local operators (not censused).",
            "n_ranked": "COMPUTED — how many operators are present in the province and thus in the "
                        "ranking pool (AutoX + present big-4 brands), so autox_rank reads as "
                        "'k of n_ranked'.",
            "n_outnumbered_districts": "COMPUTED — count of the province's districts flagged "
                                       "'outnumbered' in rival_density.json.",
            "pico": "MEASURED — count of LICENSED พิโกไฟแนนซ์ (PICO-finance) operator service "
                    "points registered to the province in the FPO open-data registry "
                    "(pico_census.json, catalog.fpo.go.th, vintage %s). A DISTINCT small-ticket "
                    "non-bank competitor class from the big-4 title lenders. Kept as its own "
                    "column and deliberately NOT summed into 'rivals'/'ratio'/'leader' — the "
                    "big-4 census is coordinate geometry (haversine), while the PICO registry is "
                    "province-count only (no coordinates), so mixing them would be dishonest. "
                    "int (or a MEASURED 0 where the registry lists none); null when the registry "
                    "is absent from the sandbox or the province is unmatched."
                    % (pico_meta.get("vintage") or "n/a"),
            "vehicles": "MEASURED — total registered-vehicle stock in the province from the DLT "
                        "national vehicle census (source-data/vehicles_by_province.json: %s). The "
                        "collateral base a title loan is secured against. null when absent."
                        % (veh_src or "n/a"),
            "operators_total": "COMPUTED — autox + rivals (the coordinate census: AutoX + the big-4 "
                               "brands). A LOWER BOUND because the rival census is one. Excludes the "
                               "PICO class (a province-count, not a coordinate census).",
            "sat_per_100k": "COMPUTED — operators_total per 100,000 registered vehicles "
                            "(operators_total / vehicles * 1e5, 1 dp). A market-SATURATION read: how "
                            "crowded the title-loan industry is relative to the addressable collateral "
                            "base — a margin-erosion signal on the footprint we already run (objective "
                            "#2). LOWER BOUND (inherits the rival-census undercount). null where the "
                            "vehicle stock is absent. NOT a share and NOT an expansion cue.",
            "sat_rank": "COMPUTED — 1-based rank by sat_per_100k (1 = most crowded per 100k vehicles) "
                        "over the provinces carrying a vehicle stock; deterministic tie-break by "
                        "province name. null where sat_per_100k is null.",
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
            "autox_rank ranks AutoX ONLY against the 4 big censused brands present in the "
            "province — sub-scale local operators and the distinct PICO class are not in the "
            "pool, so a strong rank (e.g. 2nd) means 'ahead of some big-4 brands here', not "
            "'the 2nd-largest lender overall'. It sharpens the leader column (which names only "
            "the top operator) by showing where AutoX itself sits.",
            "The 'pico' column is a DISTINCT competitor class (licensed small-ticket PICO-finance "
            "operators), counted per province from the FPO registry's own province field — NOT a "
            "coordinate census, so it is not comparable district-by-district and is never summed "
            "into the big-4 'rivals' total. A province's pico=0 (สิงห์บุรี, อ่างทอง) is a MEASURED "
            "zero from the registry, while pico=null would mean the layer was unavailable.",
            "sat_per_100k (operators per 100k vehicles) is a market-saturation / margin-pressure "
            "signal, NOT market share and NOT an expansion cue. The denominator is TOTAL registered "
            "vehicles (the full addressable collateral base), not filtered to title-loan-likely "
            "vehicles, so a vehicle-rich province (e.g. Bangkok, 12.4M vehicles) reads low even where "
            "rival branches are many. It inherits the rival census's LOWER-BOUND undercount, so it "
            "under-states true saturation.",
        ],
        "brands": brands,
        "record_format": "{province_th, region, autox, rivals, by_brand{brand:count}, ratio, "
                         "leader, autox_rank, n_ranked, pico, vehicles, operators_total, "
                         "sat_per_100k, sat_rank, n_districts, n_outnumbered_districts}. by_brand "
                         "omits zero-count brands; autox_rank is AutoX's 1-based position of "
                         "n_ranked present operators (int/null); pico is a distinct-class int/null "
                         "(not in rivals); vehicles is MEASURED DLT stock (int/null); sat_per_100k "
                         "= operators_total per 100k vehicles (float/null); sat_rank is 1=most "
                         "saturated (int/null); provinces[] sorted by (rivals-autox) desc.",
        "n_provinces": len(provinces),
        "n_provinces_autox_leads": n_autox_leads,
        "n_provinces_outnumbered": n_outnumbered_prov,
        "n_provinces_autox_last": n_autox_last,
        "n_provinces_autox_top2": n_autox_top2,
        "best_autox_rank": best_autox_rank,
        "autox_rank_distribution": autox_rank_distribution,
        "total_autox": total_autox,
        "total_rivals": total_rivals,
        "per_brand_total": per_brand_total,
        "total_pico": total_pico,
        "n_provinces_pico_present": n_pico_present,
        "pico_available": bool(pico_by_prov),
        "saturation_available": saturation_available,
        "total_vehicles": total_vehicles,
        "national_sat_per_100k": national_sat_per_100k,
        "most_saturated": most_saturated,
        "least_saturated": least_saturated,
        "vehicles_source": {
            "layer": "source-data/vehicles_by_province.json",
            "source": veh_src,
            "n_vehicles": veh_total,
        } if saturation_available else None,
        "rival_density_source": {
            "n_districts": rd_meta.get("n_districts"),
            "total_autox": rd_meta.get("total_autox"),
            "total_rivals": rd_meta.get("total_rivals"),
        },
        "pico_source": {
            "layer": "platform/data/pico_census.json",
            "vintage": pico_meta.get("vintage"),
            "source_url": pico_meta.get("source_url"),
            "n_operators": pico_meta.get("n_operators"),
        } if pico_by_prov else None,
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
    if m["pico_available"]:
        print("  licensed-PICO rivals: %d operators across %d provinces (distinct class, vintage %s)"
              % (m["total_pico"], m["n_provinces_pico_present"],
                 (m.get("pico_source") or {}).get("vintage")))
    if m["saturation_available"]:
        ms = m.get("most_saturated") or {}
        print("  market saturation: national %.1f operators / 100k vehicles; most crowded %s (%.1f)"
              % (m["national_sat_per_100k"], ms.get("province_th"), ms.get("sat_per_100k")))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="per-province per-brand peer comparison (AutoX vs each big-4 rival)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
