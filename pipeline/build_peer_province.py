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
VEH = os.path.join(ROOT, "source-data", "vehicles_by_province.json")
EMP = os.path.join(ROOT, "source-data", "employment_by_province.json")
OUT = os.path.join(DATA, "peer_province.json")

# A province's registered-vehicle stock is flagged UNRELIABLE-AS-A-DENOMINATOR when it holds
# fewer than this many vehicles per person in its labour force. The DLT registers a large share
# of Greater-Bangkok vehicles centrally at the Bangkok office, so the inner-ring provinces
# (Nonthaburi / Pathum Thani / Samut Prakan) report ~0.07–0.10 vehicles/worker — physically
# implausible (< 1 vehicle per 7 workers) and a clean 3x below the next province (0.285) and
# ~5–7x below the national median (0.499). The 0.15 cut isolates exactly those three; every
# other province clears it. MEASURED cross-check (NSO labour force), deterministic, cited.
VEH_PER_WORKER_FLOOR = 0.15


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

    # ── optional: MEASURED denominator for a saturation read — DLT registered-vehicle stock ──
    # Raw branch counts say who has the most doors; they do NOT say how CROWDED a province is
    # relative to the pool we can actually lend against. For a vehicle-title lender the addressable
    # collateral base IS the registered-vehicle stock, so title-lender branches PER 100k REGISTERED
    # VEHICLES is the honest saturation metric: a province with 300 rivals over 3M vehicles is far
    # less contested per unit of collateral than one with 120 rivals over 250k vehicles. vehicles is
    # MEASURED (DLT รถจดทะเบียน stock by province); the per-100k figures are COMPUTED. Absent input
    # (or an unmatched province) degrades every derived field to null — an honest gap, never a 0.
    veh_by_prov, veh_meta, veh_total = {}, {}, None
    if os.path.exists(VEH):
        vh = _load(VEH)
        veh_by_prov = vh.get("provinces", {}) or {}
        veh_total = vh.get("n_vehicles")
        veh_meta = {"source": vh.get("source"), "n_vehicles": veh_total}

    # MEASURED labour-force cross-check (NSO): flags provinces whose registered-vehicle stock is
    # physically implausible as a denominator (the Greater-Bangkok central-registration artifact).
    emp_by_prov = {}
    if os.path.exists(EMP):
        emp_by_prov = (_load(EMP).get("provinces", {}) or {})

    def _veh_flag(prov, vehicles):
        # returns "low-vs-labour" when vehicles/labour-force < VEH_PER_WORKER_FLOOR, else None
        # (also None when either input is missing — never guess a flag).
        if not isinstance(vehicles, int):
            return None
        e = emp_by_prov.get(prov) or {}
        labour = (e.get("formal") or 0) + (e.get("informal") or 0)
        if labour <= 0:
            return None
        return "low-vs-labour" if (vehicles / labour) < VEH_PER_WORKER_FLOOR else None

    def _per100k(n, veh):
        # branches per 100,000 registered vehicles, 2 dp; null when the denominator is absent/0.
        if not veh:
            return None
        return round(n / veh * 100000, 2)

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
        # MEASURED registered-vehicle stock for this province (the collateral base), and the
        # COMPUTED saturation reads over it. vehicles is None (not 0) when the DLT layer is absent
        # or the province is unmatched, which cascades every per-100k field to null.
        veh_row = veh_by_prov.get(e["province_th"])
        vehicles = veh_row.get("total") if isinstance(veh_row, dict) else None
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
            "vehicle_stock_flag": _veh_flag(e["province_th"], vehicles),
            "autox_per_100k_veh": _per100k(autox, vehicles),
            "rivals_per_100k_veh": _per100k(rivals, vehicles),
            "titlelender_per_100k_veh": _per100k(autox + rivals, vehicles),
            "n_districts": e["n_districts"],
            "n_outnumbered_districts": e["n_outnumbered_districts"],
        })

    # rank most-contested first: raw branch deficit (rivals − autox) desc, then province_th
    # asc for a stable tiebreak. This mirrors the district board's "most outnumbered first".
    provinces.sort(key=lambda p: (-(p["rivals"] - p["autox"]), p["province_th"]))

    n_autox_leads = sum(1 for p in provinces if p["leader"] == "AutoX")
    # provinces_led_by: how many of the 77 provinces each operator is the single largest network in
    # (the same `leader` field, tallied). n_provinces_autox_leads already gives AutoX's own count;
    # this extends it to every rival brand so the board can name WHICH rival dominates the most
    # ground — and by how many provinces — from MEASURED data, instead of a hardcoded "Muangthai
    # leads most" assertion. Ordered AutoX-first then census-brand order; zeros kept (a brand that
    # leads nowhere is itself a signal), so the dict is deterministic and JSON-stable.
    lead_counter = collections.Counter(p["leader"] for p in provinces)
    provinces_led_by = {op: lead_counter.get(op, 0) for op in (["AutoX"] + brands)}
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

    # ── vehicle-saturation rollup (MEASURED denominator, COMPUTED reads) ─────────────
    # National saturation uses the layer's OWN matched vehicle total (sum of the provinces we
    # joined), not the raw file's n_vehicles — so it stays consistent with the counts on the board
    # even if a province ever fails to match. The single most-saturated province (highest
    # title-lender branches per 100k vehicles, among provinces where AutoX is present) is the
    # lead-with-the-answer headline the raw counts can't give.
    veh_present = [p for p in provinces if isinstance(p.get("vehicles"), int)]
    matched_vehicles = sum(p["vehicles"] for p in veh_present) or None
    nat_autox_per_100k = _per100k(sum(p["autox"] for p in veh_present), matched_vehicles)
    nat_rivals_per_100k = _per100k(sum(p["rivals"] for p in veh_present), matched_vehicles)
    nat_titlelender_per_100k = _per100k(
        sum(p["autox"] + p["rivals"] for p in veh_present), matched_vehicles)
    # most-saturated province = highest title-lender density where AutoX actually operates
    # (autox > 0) AND the vehicle denominator is reliable (NOT flagged low-vs-labour), so the
    # headline is a real crowded market, never the Greater-Bangkok central-registration artifact.
    n_veh_flagged = sum(1 for p in veh_present if p["vehicle_stock_flag"])
    sat_pool = [p for p in veh_present
                if p["autox"] > 0 and p["titlelender_per_100k_veh"] is not None
                and not p["vehicle_stock_flag"]]
    sat_pool.sort(key=lambda p: (-p["titlelender_per_100k_veh"], p["province_th"]))
    most_saturated = ({
        "province_th": sat_pool[0]["province_th"],
        "titlelender_per_100k_veh": sat_pool[0]["titlelender_per_100k_veh"],
        "rivals_per_100k_veh": sat_pool[0]["rivals_per_100k_veh"],
        "autox_per_100k_veh": sat_pool[0]["autox_per_100k_veh"],
        "vehicles": sat_pool[0]["vehicles"],
    } if sat_pool else None)

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
            "provinces_led_by (meta)": "COMPUTED — a national tally of the `leader` field: how many "
                                       "of the 77 provinces each operator is the single largest "
                                       "network in. Pure aggregation of MEASURED counts; inherits "
                                       "leader's Heng-under-count caveat.",
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
            "vehicles": "MEASURED — DLT registered-vehicle stock for the province (รถจดทะเบียน, "
                        "vehicles_by_province.json .total). The addressable collateral base for a "
                        "vehicle-title lender. null when the DLT layer is absent or the province "
                        "is unmatched (an honest gap, never a 0).",
            "vehicle_stock_flag": "MEASURED cross-check — 'low-vs-labour' when the province's "
                                  "registered-vehicle stock is under %.2f vehicles per person in "
                                  "its NSO labour force (formal+informal), i.e. physically "
                                  "implausible as a denominator. This isolates the Greater-Bangkok "
                                  "central-registration artifact (Nonthaburi / Pathum Thani / "
                                  "Samut Prakan register most vehicles at the Bangkok DLT office). "
                                  "Flagged provinces keep their saturation numbers but are EXCLUDED "
                                  "from the most-saturated headline. null = reliable (or labour "
                                  "figure absent)." % VEH_PER_WORKER_FLOOR,
            "autox_per_100k_veh / rivals_per_100k_veh / titlelender_per_100k_veh":
                "COMPUTED — branches per 100,000 registered vehicles (AutoX / big-4 rivals / both), "
                "2 dp. A SATURATION read: how crowded the province is relative to the vehicle pool "
                "we can lend against, which raw counts cannot show. Numerator inherits the MEASURED "
                "census's lower-bound caveat; denominator is MEASURED DLT stock. null where vehicles "
                "is null.",
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
            "The *_per_100k_veh saturation reads divide the (lower-bound) big-4 census by MEASURED "
            "DLT registered-vehicle stock. The vehicle stock counts ALL registered vehicles, while "
            "the rivals also lend against gold and cashflow — so this is a relative crowding proxy "
            "over the vehicle collateral base, not a literal branches-per-titleable-vehicle. It "
            "sharpens the raw count (crowded-per-collateral vs merely populous), it does not replace "
            "it, and it makes NO open / close / expand call.",
            "Greater-Bangkok central-registration artifact: the DLT registers a large share of "
            "metro vehicles at the Bangkok office, so the inner-ring provinces (Nonthaburi, Pathum "
            "Thani, Samut Prakan) report only ~0.07–0.10 vehicles per worker and their per-100k "
            "saturation is INFLATED. Those provinces carry vehicle_stock_flag='low-vs-labour' (a "
            "MEASURED NSO-labour cross-check) and are EXCLUDED from the most-saturated headline. "
            "Their raw branch counts and ratios are unaffected — only the vehicle-normalised reads "
            "are unreliable. The NATIONAL saturation is sound: vehicle stock is sum-conserved "
            "(the ring's shortfall is Bangkok's surplus), so the distortion is per-province only.",
        ],
        "brands": brands,
        "record_format": "{province_th, region, autox, rivals, by_brand{brand:count}, ratio, "
                         "leader, autox_rank, n_ranked, pico, vehicles, vehicle_stock_flag, "
                         "autox_per_100k_veh, rivals_per_100k_veh, titlelender_per_100k_veh, "
                         "n_districts, n_outnumbered_districts}. by_brand omits zero-count brands; autox_rank "
                         "is AutoX's 1-based position of n_ranked present operators (int/null); "
                         "pico is a distinct-class int/null (not in rivals); provinces[] sorted "
                         "by (rivals-autox) desc.",
        "n_provinces": len(provinces),
        "n_provinces_autox_leads": n_autox_leads,
        "provinces_led_by": provinces_led_by,
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
        "vehicle_saturation_available": bool(veh_present),
        "n_provinces_vehicle_matched": len(veh_present),
        "n_provinces_vehicle_flagged": n_veh_flagged,
        "matched_vehicles": matched_vehicles,
        "national_autox_per_100k_veh": nat_autox_per_100k,
        "national_rivals_per_100k_veh": nat_rivals_per_100k,
        "national_titlelender_per_100k_veh": nat_titlelender_per_100k,
        "most_saturated_province": most_saturated,
        "vehicle_source": {
            "layer": "source-data/vehicles_by_province.json",
            "source": veh_meta.get("source"),
            "n_vehicles": veh_meta.get("n_vehicles"),
        } if veh_present else None,
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
    print("  provinces led by: %s"
          % ", ".join("%s %d" % (op, n) for op, n in m["provinces_led_by"].items() if n))
    if m["pico_available"]:
        print("  licensed-PICO rivals: %d operators across %d provinces (distinct class, vintage %s)"
              % (m["total_pico"], m["n_provinces_pico_present"],
                 (m.get("pico_source") or {}).get("vintage")))
    if m["vehicle_saturation_available"]:
        ms = m.get("most_saturated_province") or {}
        print("  saturation (per 100k registered vehicles): AutoX %.2f | rivals %.2f | title-lenders %.2f"
              % (m["national_autox_per_100k_veh"], m["national_rivals_per_100k_veh"],
                 m["national_titlelender_per_100k_veh"]))
        if ms:
            print("  most-saturated market: %s (%.2f title-lender branches / 100k vehicles)"
                  % (ms["province_th"], ms["titlelender_per_100k_veh"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="per-province per-brand peer comparison (AutoX vs each big-4 rival)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
