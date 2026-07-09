#!/usr/bin/env python3
"""
build_search_demand.py — SEARCH-DEMAND layer (objective #2: acquisition / where to expand).

Network-free, deterministic. Projects ONE committed snapshot into an app-ready per-province board:
  - source-data/google_trends.json     REAL Google Trends snapshot (pytrends, geo=TH, REGION res):
        demand{term -> province_th -> 0..100}   two title-loan demand terms
        brands{brand -> province_th -> 0..100}   five lender brands on ONE SHARED payload axis
        brand_terms{brand -> Thai query}, national_ts[[week,val]...], meta{provenance,...}
  - platform/data/provinces/index.json  th <-> slug/en/region (committed; the join key for the map lens)

It computes, PER PROVINCE:
  demand      mean of the two demand terms' relative-interest values (0..100). A RELATIVE index of how
              much people in that province search title-loan intent terms — NOT absolute query volume.
              [ESTIMATED — Google Trends relative index]
  sos         share-of-search per brand = brand value / Σ(all brand values) in that province, a fraction
              in [0,1] that sums to 1 across the 5 brands. GUARD: when Σ = 0 the whole map is null (we
              NEVER fabricate a share out of an all-zero province). Brand values share one Trends payload
              axis, so cross-brand shares within a province are meaningful (Google's own guarantee).
              [ESTIMATED — share of a relative index, noisy in low-volume provinces]
  autox_share the AutoX entry of sos (fraction or null) — the headline number the board leads with.
  best_rival  the single strongest non-AutoX brand {brand, share} (null if sos is null).
  autox_sos_rank  this province's RANK (1 = strongest) by AutoX share-of-search across all provinces
              that have a defined share; provinces with a null share get rank null (ranked last, absent).
  raw         the raw 0..100 per-brand + per-term values behind every derived number, so the UI can show
              reality (the actual index), not just a computed share.

There is NO hidden model here: demand is a mean, sos is a normalize, rank is an argsort. Everything traces
to the committed snapshot. The only editorial choice is labelling — all outputs are ESTIMATED (a relative
search index is a direction/pressure signal, not a volume or a booking).

Run:
  python3 build_search_demand.py            # write platform/data/search_demand.json
  python3 build_search_demand.py --check    # re-run, byte-compare against the committed file
"""
import json
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data")
DATA = os.path.join(ROOT, "platform", "data")
TRENDS = os.path.join(SRC, "google_trends.json")
PROV_INDEX = os.path.join(DATA, "provinces", "index.json")
OUT = os.path.join(DATA, "search_demand.json")

AUTOX = "AutoX"


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build():
    gt = _load(TRENDS)
    idx = _load(PROV_INDEX)

    demand_terms = gt.get("demand_terms") or list((gt.get("demand") or {}).keys())
    demand = gt.get("demand") or {}
    brands_raw = gt.get("brands") or {}
    brand_terms = gt.get("brand_terms") or {}
    # deterministic brand order: AutoX first (the subject), then the rest alphabetically.
    brands = [AUTOX] + sorted(b for b in brands_raw if b != AUTOX)

    # th -> {slug, en, region} from the committed province index (the map-lens join key).
    prov_meta = {r["th"]: r for r in idx if r.get("th") and r.get("slug")}

    records = []
    for th, meta in prov_meta.items():
        # ---- demand: mean of the two demand terms' relative-interest values ----
        vals = [demand[t].get(th) for t in demand_terms if isinstance(demand.get(t), dict)]
        vals = [v for v in vals if isinstance(v, (int, float))]
        dem = round(sum(vals) / len(vals), 1) if vals else None

        # ---- brand raw values on the shared axis ----
        braw = {b: brands_raw.get(b, {}).get(th, 0) for b in brands}
        total = sum(v for v in braw.values() if isinstance(v, (int, float)))

        # ---- share-of-search (GUARD: all-zero province -> null, never fabricated) ----
        if total > 0:
            sos = {b: round(braw[b] / total, 4) for b in brands}
            autox_share = sos.get(AUTOX)
            rivals = [(b, sos[b]) for b in brands if b != AUTOX]
            rivals.sort(key=lambda kv: (-kv[1], kv[0]))
            best_rival = {"brand": rivals[0][0], "share": rivals[0][1]} if rivals else None
        else:
            sos = None
            autox_share = None
            best_rival = None

        records.append({
            "th": th,
            "en": meta.get("en"),
            "slug": meta["slug"],
            "region": meta.get("region"),
            "demand": dem,
            "sos": sos,
            "autox_share": autox_share,
            "best_rival": best_rival,
            "autox_sos_rank": None,   # filled below once all provinces are known
            "raw": {
                "brands": {b: braw[b] for b in brands},
                "demand_terms": {t: demand.get(t, {}).get(th) for t in demand_terms},
                "brand_total": total,
            },
        })

    # ---- autox_sos_rank: rank provinces by AutoX share-of-search (1 = strongest) ----
    # provinces with a null share are unranked (rank stays null) and sorted last for output.
    ranked = sorted((r for r in records if r["autox_share"] is not None),
                    key=lambda r: (-r["autox_share"], r["th"]))
    for i, r in enumerate(ranked, 1):
        r["autox_sos_rank"] = i

    # ---- output order: by demand desc (headline board is "where demand is hottest"), th tiebreak ----
    records.sort(key=lambda r: (-(r["demand"] if r["demand"] is not None else -1), r["th"]))

    n_ranked = len(ranked)
    src_meta = gt.get("meta") or {}
    meta = {
        "generated_by": "pipeline/build_search_demand.py",
        "title": "Per-province title-loan search demand + brand share-of-search (acquisition, objective #2)",
        "label": "ESTIMATED — Google Trends relative search-interest index (0-100), NOT absolute query volume.",
        "n_provinces": len(records),
        "n_ranked": n_ranked,
        "brands": brands,
        "brand_terms": brand_terms,
        "demand_terms": demand_terms,
        "national_ts": gt.get("national_ts") or [],
        "source": src_meta.get("source"),
        "pulled_at_utc": src_meta.get("pulled_at_utc"),
        "provenance": src_meta.get("provenance"),
        "fields": {
            "demand": "ESTIMATED — mean of the two demand terms' Google Trends relative-interest values "
                      "(0-100). A relative direction/pressure signal for title-loan search intent, NOT "
                      "absolute query volume. Low-volume provinces are noisy.",
            "sos": "ESTIMATED — per-brand share-of-search = brand value / Σ(all brand values) in the "
                   "province, a fraction summing to 1 across brands. Brands share one Trends payload axis "
                   "so cross-brand shares within a province are meaningful. null when Σ=0 (never faked).",
            "autox_share": "ESTIMATED — the AutoX entry of sos (fraction) or null.",
            "best_rival": "ESTIMATED — strongest non-AutoX brand {brand, share} (null when sos is null).",
            "autox_sos_rank": "ESTIMATED — province rank by AutoX share-of-search (1 = strongest); null "
                              "when the province has no defined share.",
            "raw": "the raw 0-100 Google Trends values behind every derived number (per brand + per demand term).",
        },
        "caveats": [
            "Google Trends is a RELATIVE index (0-100), not query volume — read direction/pressure, not magnitude.",
            "Share-of-search is a demand/attention proxy, NOT market share or bookings.",
            "Low-search-volume provinces are noisy; treat single-province spikes with caution.",
            "Brand values share ONE payload axis (cross-brand shares valid); demand terms are a separate payload.",
        ],
    }
    return {"meta": meta, "provinces": records}


def dumps(obj):
    # deterministic: keep insertion key order, readable separators, non-ASCII Thai preserved
    # (matches the crop_stress / household_risk convention).
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift")
    args = ap.parse_args()

    data = build()
    text = dumps(data)

    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d provinces, %d ranked)" %
                  (OUT, data["meta"]["n_provinces"], data["meta"]["n_ranked"]))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s (%d provinces, demand-desc)" % (OUT, data["meta"]["n_provinces"]))
    for r in data["provinces"][:6]:
        share = ("%.1f%%" % (100 * r["autox_share"])) if r["autox_share"] is not None else "n/a"
        best = r["best_rival"]
        btxt = ("%s %.1f%%" % (best["brand"], 100 * best["share"])) if best else "n/a"
        print("  %-16s demand=%-5s AutoX SoS=%-6s best rival=%s" % (r["th"], r["demand"], share, btxt))


if __name__ == "__main__":
    main()
