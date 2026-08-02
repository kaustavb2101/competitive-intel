#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pull_flood_hazard.py — GISTDA repeated-flooding hazard, MAX(flood_freq) per district (MEASURED).

Pulls the GISTDA "พื้นที่น้ำท่วมซ้ำซาก 2005-2016" (Repeated Flooding 2005-2016) FeatureServer and
aggregates it SERVER-SIDE to one MAX(flood_freq) per amphoe (district). Writes the small, committable
`source-data/gistda_flood_hazard.json` that build_flood_hazard.py projects into platform/data.

WHY MAX(flood_freq), NOT area
-----------------------------
The service also carries `area_rai` per polygon, but the polygons OVERLAP (they are per-event, not
dissolved by frequency): a naive SUM(area_rai) overstates flooded area ~3-9x and yields a national
total (~40% of Thailand) that is an artifact, not a finding — dissolving that geometry is a separate
job (see docs/NEXT_STEPS.md §0). What IS immune to the overlap is the per-district MAX(flood_freq):
"this district contains ground that flooded in N of the 12 years 2005-2016". That is a clean,
defensible branch-hazard flag and it is all this puller claims. NO area is pulled or written.

The `flood_freq` field is the count of the 12 annual layers (year2005..year2016) in which a polygon
flooded, so it ranges 1..12. Grouping by (pv_code, ap_code) with a MAX statistic returns one row per
flood-affected district in a single call (< the 1000 maxRecordCount, verified 2026-08-02).

REACHABILITY: GISTDA's ArcGIS server is open from cloud IPs, no key (verified from CI 2026-08-02).
This puller is NETWORK and therefore NOT in the determinism gate; its committed OUTPUT is the gate's
input. Re-runnable — the output is sorted deterministically by (pv_code, ap_code) so a re-pull of the
same snapshot is byte-stable apart from the recorded `pulled` date.

  python3 pull_flood_hazard.py            # pull + write source-data/gistda_flood_hazard.json
  python3 pull_flood_hazard.py --stdout   # print the aggregate, do not write
"""
import argparse, datetime, json, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "source-data", "gistda_flood_hazard.json")

SERVICE = ("https://gistdaportal.gistda.or.th/data/rest/services/FL_Flood/"
           "FL_RepeatedFlooding_GISTDA_50k_Y2005_Y2016/FeatureServer/0")
QUERY = SERVICE + "/query"
# The dataset's own temporal coverage (from the service/layer name) — a fixed data vintage, NOT a
# pull date, so it never drifts on re-pull.
DATA_VINTAGE = "2005-2016"


def _get(url, params):
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "autox-flood-hazard/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def pull():
    params = {
        "where": "1=1",
        "groupByFieldsForStatistics": "pv_code,pv_tn,ap_code,ap_tn,ap_en",
        "outStatistics": json.dumps([{
            "statisticType": "max",
            "onStatisticField": "flood_freq",
            "outStatisticFieldName": "maxfreq",
        }]),
        "f": "json",
    }
    d = _get(QUERY, params)
    feats = d.get("features", [])
    if d.get("exceededTransferLimit"):
        # groupBy returned more rows than the server would send in one page — bail loudly rather
        # than silently ship a truncated hazard map.
        raise SystemExit("ERROR: exceededTransferLimit — the district groupBy was truncated; "
                         "add pagination before trusting the output.")
    rows = []
    for f in feats:
        a = f.get("attributes", {})
        mf = a.get("maxfreq")
        if mf is None:
            continue
        rows.append({
            "pv_code": (a.get("pv_code") or "").strip(),
            "pv_tn": (a.get("pv_tn") or "").strip(),
            "ap_code": (a.get("ap_code") or "").strip(),
            "ap_tn": (a.get("ap_tn") or "").strip(),
            "ap_en": (a.get("ap_en") or "").strip(),
            "maxfreq": int(mf),
        })
    rows.sort(key=lambda r: (r["pv_code"], r["ap_code"], r["ap_tn"]))
    return {
        "meta": {
            "source": ("GISTDA Repeated Flooding 2005-2016 (FL_RepeatedFlooding_GISTDA_50k_Y2005_Y2016) "
                       "FeatureServer — server-side MAX(flood_freq) grouped by district (amphoe)."),
            "service": SERVICE,
            "label": ("MEASURED — per-district MAX(flood_freq): count of the 12 years 2005-2016 in "
                      "which any ground in the district flooded (1-12). Immune to the per-event "
                      "polygon overlap that makes area totals unreliable; no flooded-AREA is claimed."),
            "data_vintage": DATA_VINTAGE,
            "pulled": datetime.date.today().isoformat(),
            "n_districts_flooded": len(rows),
            "generated_by": "pipeline/pull_flood_hazard.py",
        },
        "districts": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true", help="print, do not write")
    args = ap.parse_args()
    out = pull()
    txt = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=False) + "\n"
    if args.stdout:
        sys.stdout.write(txt)
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(txt)
    print("wrote %s (%d flood-affected districts, vintage %s)"
          % (os.path.relpath(OUT, ROOT), out["meta"]["n_districts_flooded"], DATA_VINTAGE))


if __name__ == "__main__":
    main()
