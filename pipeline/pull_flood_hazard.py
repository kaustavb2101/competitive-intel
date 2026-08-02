#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pull_flood_hazard.py — pull GISTDA's REPEATED-FLOODING district census (MEASURED, no key).

GISTDA (Geo-Informatics and Space Technology Development Agency) publishes a national
repeated-flooding layer built from 12 years of satellite flood extents, 2005-2016, at 1:50,000:

    FL_Flood/FL_RepeatedFlooding_GISTDA_50k_Y2005_Y2016/FeatureServer/0

Each polygon carries `flood_freq` — how many of the 12 years that ground flooded — plus the full
admin key (pv_tn/ap_tn Thai names + pv_code/ap_code). The FeatureServer supports server-side
statistics, so this pulls a group-by aggregation and never downloads geometry.

THE OVERLAP TRAP (see docs/NEXT_STEPS.md #0): the polygons OVERLAP (per-event, not dissolved), so a
SUM of `area_rai` overstates flooded area 3-9x and is an artifact, not a finding. This puller therefore
takes ONLY `MAX(flood_freq)` per district — a value that is immune to overlap ("this district contains
ground that flooded in N of 12 years"). It deliberately does NOT emit any flooded-AREA figure; that
would need a real spatial dissolve (a shapely geometry job), not a query parameter.

Reachable from any IP, no key (verified 2026-08-02, HTTP 200 from CI). Writes the small aggregation
to source-data/gistda_flood_hazard.json (committed — no PII, ~840 rows), which is the deterministic
input to build_flood_hazard.py. This puller is NETWORK-ONLY and NOT in the determinism gate; its
committed output is the repo's source of truth (same convention as the other network pullers).

    python3 pull_flood_hazard.py
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "source-data", "gistda_flood_hazard.json")

SERVICE = ("FL_Flood/FL_RepeatedFlooding_GISTDA_50k_Y2005_Y2016/FeatureServer/0")
BASE = ("https://gistdaportal.gistda.or.th/data/rest/services/%s/query" % SERVICE)
VINTAGE = "2005-2016"  # the 12-year satellite window the layer is built from (fixed in the source name)


def _query(params, timeout=120):
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "autox-intel/flood-hazard"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def pull():
    # per-district MAX(flood_freq) + polygon count — the overlap-immune hazard read
    stats = json.dumps([
        {"statisticType": "max", "onStatisticField": "flood_freq", "outStatisticFieldName": "max_freq"},
        {"statisticType": "count", "onStatisticField": "objectid", "outStatisticFieldName": "n_poly"},
    ])
    d = _query({
        "where": "1=1",
        "outStatistics": stats,
        "groupByFieldsForStatistics": "pv_code,pv_tn,pv_en,ap_code,ap_tn,ap_en",
        "f": "json",
    })
    rows = []
    for f in d.get("features", []):
        a = f["attributes"]
        rows.append({
            "pv_code": (a.get("pv_code") or "").strip(),
            "pv_tn": (a.get("pv_tn") or "").strip(),
            "pv_en": (a.get("pv_en") or "").strip(),
            "ap_code": (a.get("ap_code") or "").strip(),
            "ap_tn": (a.get("ap_tn") or "").strip(),
            "ap_en": (a.get("ap_en") or "").strip(),
            "max_freq": int(a.get("max_freq") or 0),
            "n_poly": int(a.get("n_poly") or 0),
        })
    # deterministic order so the committed source file is byte-stable across re-pulls
    rows.sort(key=lambda r: (r["pv_code"], r["ap_code"], r["ap_tn"]))

    # national frequency histogram (group-by flood_freq) — also overlap-immune (a count of districts per
    # band is derived downstream; here we keep the raw polygon-band tally for a cross-check in the meta)
    hstats = json.dumps([{"statisticType": "count", "onStatisticField": "objectid",
                          "outStatisticFieldName": "n"}])
    h = _query({"where": "1=1", "outStatistics": hstats,
                "groupByFieldsForStatistics": "flood_freq", "f": "json"})
    freq_polys = {}
    for f in h.get("features", []):
        a = f["attributes"]
        freq_polys[str(int(a.get("flood_freq") or 0))] = int(a.get("n") or 0)

    return {
        "generated_by": "pipeline/pull_flood_hazard.py",
        "source": ("GISTDA repeated-flooding, 1:50,000, satellite flood extents 2005-2016 "
                   "(FL_RepeatedFlooding_GISTDA_50k_Y2005_Y2016 FeatureServer). MEASURED."),
        "service": SERVICE,
        "vintage": VINTAGE,
        "field": "flood_freq (count of the 12 years 2005-2016 that this ground flooded)",
        "aggregation": ("MAX(flood_freq) per district — overlap-immune. NO area figure is pulled: the "
                        "polygons overlap (per-event), so any SUM(area_rai) is an artifact (see "
                        "docs/NEXT_STEPS.md #0)."),
        "pulled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_districts": len(rows),
        "freq_poly_histogram": {k: freq_polys[k] for k in sorted(freq_polys, key=lambda x: int(x))},
        "districts": rows,
    }


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    obj = pull()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("wrote %s (%d districts; freq histogram %s)"
          % (OUT, obj["n_districts"], obj["freq_poly_histogram"]))


if __name__ == "__main__":
    main()
