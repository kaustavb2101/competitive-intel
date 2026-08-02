#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_flood_hazard.py — per-DISTRICT + per-BRANCH repeated-flooding hazard (MEASURED, obj #1).

Projects GISTDA's 12-year repeated-flooding census (source-data/gistda_flood_hazard.json, pulled by
pull_flood_hazard.py) into a clean district + branch layer joined to the app's 928-district master
(amphoe.json). Repeated flooding is a direct PORTFOLIO-RISK signal (objective #1): title-loan
collateral (the pickup/motorcycle) and the borrower's cash flow both sit on ground that, in the worst
districts, went underwater in 10-12 of 12 years — a structural repayment + collateral-recovery hazard
independent of any single season.

WHAT IS MEASURED, AND WHAT IS DELIBERATELY NOT (the overlap trap — docs/NEXT_STEPS.md #0):
  - `max_freq` per district = MAX(flood_freq) over that district's polygons = "this district contains
    ground that flooded in N of the 12 years 2005-2016". This is IMMUNE to the polygon overlap, so it
    is a clean MEASURED hazard flag.
  - NO flooded-AREA figure is produced. The source polygons overlap (per-event, not dissolved), so any
    SUM(area_rai) overstates flooded area 3-9x and is an artifact. Area needs a real spatial dissolve
    (a shapely geometry job), left for a later pass. This layer makes no area claim.

JOIN: GISTDA carries Thai admin names (pv_tn/ap_tn); the geoBoundaries-derived master carries no Thai
admin CODE, so — exactly like build_pico_district.py — districts are resolved by exact Thai-name match
of (canonical province, ap_tn) to the 928-district master. ~91.6% of GISTDA's flood-affected districts
resolve; the rest (mostly recently-split rural amphoe absent from the 928-polygon set) are counted
honestly in n_unresolved, NOT dropped silently. GISTDA's `ap_en` is unreliable (some rows carry the
wrong romanization), so it is NOT used as a fallback — a bad English match would double-count.

SEMANTICS OF 0: a district with no repeated-flood polygon in the 2005-2016 window resolves to max_freq
0 ("no repeatedly-flooded ground recorded", NOT "guaranteed dry in any given year"). Branches whose
district could not be resolved to the GISTDA layer are also set to 0 (understating hazard for at most
the n_unresolved districts, reported in meta) rather than guessed.

OUTPUT platform/data/flood_hazard.json — { meta, by_district{ "prov|amphoe": max_freq },
  district_bands{freq:n_districts}, branches[ max_freq | 0 ] (INDEX-ALIGNED to branches.json),
  branch_bands{freq:n_branches}, top_districts }.

DETERMINISTIC + NETWORK-FREE (pure function of the two committed inputs). Carries --check; SKIP-passes
(exit 3) only if the committed source is absent.

    python3 build_flood_hazard.py
    python3 build_flood_hazard.py --check
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.regionmap import canonical

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data", "gistda_flood_hazard.json")
AMPHOE = os.path.join(ROOT, "platform", "data", "amphoe.json")
OUT = os.path.join(ROOT, "platform", "data", "flood_hazard.json")

VINTAGE = "2005-2016"
SEVERE_MIN = 8   # flooded >= 8 of 12 years — the "severe repeated-flooding" band
CHRONIC_MIN = 5  # flooded >= 5 of 12 years — the "chronic" band


def build():
    src = json.load(open(SRC, encoding="utf-8"))
    amp_doc = json.load(open(AMPHOE, encoding="utf-8"))
    amphoe = amp_doc["amphoe"]
    branch_amphoe = amp_doc["branch_amphoe"]

    # district master: (canonical province, Thai name) -> amphoe index. A handful of polygons share a
    # province|name pair (real district splits); first-wins is deterministic given amphoe.json order.
    idx_by_key = {}
    for i, a in enumerate(amphoe):
        idx_by_key.setdefault((canonical(a["province_th"]), a["name"]), i)

    max_by_idx = {}         # amphoe index -> max_freq (resolved GISTDA districts only)
    by_district = {}        # "prov|amphoe" -> max_freq
    n_rows = n_resolved = n_unmapped_prov = n_off_master = 0
    off_master = {}         # (prov, ap_tn) -> count, honest unresolved sample

    # build province set from the master for the province-mapping check
    master_provs = {canonical(a["province_th"]) for a in amphoe}

    for r in src["districts"]:
        n_rows += 1
        prov = canonical(r["pv_tn"].strip())
        if prov not in master_provs:
            n_unmapped_prov += 1
            continue
        ap = r["ap_tn"].strip()
        idx = idx_by_key.get((prov, ap))
        if idx is None:
            n_off_master += 1
            off_master[(prov, ap)] = off_master.get((prov, ap), 0) + 1
            continue
        f = int(r["max_freq"])
        n_resolved += 1
        # a split-master collision could map two GISTDA rows to one amphoe: keep the higher hazard
        if f > max_by_idx.get(idx, -1):
            max_by_idx[idx] = f
        key = "%s|%s" % (amphoe[idx]["province_th"], amphoe[idx]["name"])
        if f > by_district.get(key, -1):
            by_district[key] = f

    # district-band histogram over RESOLVED districts (max_freq 1..12; 0 = not in GISTDA, excluded)
    district_bands = {}
    for f in by_district.values():
        if f >= 1:
            district_bands[str(f)] = district_bands.get(str(f), 0) + 1

    # per-branch: its district's max_freq, else 0 (see SEMANTICS OF 0 in the docstring)
    branches = []
    branch_bands = {}
    n_branch_severe = n_branch_chronic = n_branch_prone = 0
    for bi in branch_amphoe:
        f = max_by_idx.get(bi, 0)
        branches.append(f)
        branch_bands[str(f)] = branch_bands.get(str(f), 0) + 1
        if f >= 1:
            n_branch_prone += 1
        if f >= CHRONIC_MIN:
            n_branch_chronic += 1
        if f >= SEVERE_MIN:
            n_branch_severe += 1

    top_districts = sorted(by_district.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    unresolved_samples = [{"province": p, "amphoe": a, "n": c}
                          for (p, a), c in sorted(off_master.items(), key=lambda t: (-t[1], t[0]))[:20]]

    n_severe_dist = sum(1 for f in by_district.values() if f >= SEVERE_MIN)
    n_chronic_dist = sum(1 for f in by_district.values() if f >= CHRONIC_MIN)

    meta = {
        "generated_by": "pipeline/build_flood_hazard.py",
        "label": ("MEASURED per-district + per-branch REPEATED-FLOODING hazard. max_freq = how many of "
                  "the 12 years 2005-2016 the worst ground in the district flooded (GISTDA satellite "
                  "flood extents, 1:50,000). A structural portfolio-risk flag (objective #1): "
                  "collateral-recovery + borrower cash-flow exposure on chronically-flooded ground."),
        "source": ("MEASURED — GISTDA (สทอภ.) repeated-flooding layer "
                   "FL_RepeatedFlooding_GISTDA_50k_Y2005_Y2016, via source-data/gistda_flood_hazard.json "
                   "(pull_flood_hazard.py). District read is MAX(flood_freq); the only inference is the "
                   "exact Thai-name match of the district to amphoe.json's 928-district master."),
        "provenance": ("measured (government satellite flood census; district resolved by exact-name "
                       "match of GISTDA's ap_tn to the canonical 928-district master)"),
        "service": src.get("service"),
        "vintage": VINTAGE,
        "vintage_note": ("The 12-year satellite window is 2005-2016 — this is a STRUCTURAL hazard read "
                         "(which ground floods repeatedly), decade-scale and not a current-season "
                         "nowcast. It complements the real-time thaiwater_flood.json / thaiwater_rain.json."),
        "metric": "max_freq: MAX(flood_freq) over the district's polygons, 0..12",
        "no_area_claim": ("This layer makes NO flooded-area claim. The GISTDA polygons overlap "
                          "(per-event, not dissolved), so any SUM(area_rai) overstates area 3-9x and is "
                          "an artifact. MAX(flood_freq) is overlap-immune; area needs a spatial dissolve."),
        "district_master": "platform/data/amphoe.json (928 canonical amphoe, province_th + Thai name)",
        "n_gistda_districts": n_rows,
        "n_district_resolved": n_resolved,
        "n_districts_present": len(by_district),
        "resolution_pct": round(100.0 * n_resolved / n_rows, 1) if n_rows else 0.0,
        "n_unresolved": n_unmapped_prov + n_off_master,
        "unresolved_breakdown": {
            "unmapped_province": n_unmapped_prov,
            "district_not_in_928_master": n_off_master,
        },
        "unresolved_note": ("Unresolved GISTDA districts (mostly recently-split rural amphoe absent from "
                            "the 928-polygon geoBoundaries master) are counted here, NOT dropped. "
                            "GISTDA's ap_en is unreliable, so it is not used as an English fallback."),
        "severe_min": SEVERE_MIN,
        "chronic_min": CHRONIC_MIN,
        "n_districts_severe": n_severe_dist,
        "n_districts_chronic": n_chronic_dist,
        "branch_semantics_of_0": ("A branch in a district with no repeated-flood polygon (or one of the "
                                  "n_unresolved districts) is 0 = 'no repeatedly-flooded ground recorded "
                                  "2005-2016', NOT 'guaranteed dry in a given year'."),
        "n_branches": len(branches),
        "n_branches_flood_prone": n_branch_prone,
        "n_branches_chronic": n_branch_chronic,
        "n_branches_severe": n_branch_severe,
        "index_note": ("branches[] is INDEX-ALIGNED to platform/data/branches.json (entry i <-> branch "
                       "i), identical to branch_population.json / rival_pressure.json / branch_cropland.json."),
        "objective": ("Portfolio risk (#1): a measured structural flood-hazard read on the existing "
                      "footprint — which branches lend against collateral and cash flow on chronically "
                      "flooded ground."),
        "inputs": ["source-data/gistda_flood_hazard.json (GISTDA MAX(flood_freq) per district)",
                   "platform/data/amphoe.json (928-district master + branch_amphoe index)"],
    }
    return {"meta": meta, "by_district": dict(sorted(by_district.items())),
            "district_bands": {k: district_bands[k] for k in sorted(district_bands, key=lambda x: int(x))},
            "branches": branches,
            "branch_bands": {k: branch_bands[k] for k in sorted(branch_bands, key=lambda x: int(x))},
            "top_districts": top_districts, "unresolved_samples": unresolved_samples}


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if not os.path.exists(SRC):
        if args.check:
            print("build_flood_hazard.py --check: SKIP (source-data/gistda_flood_hazard.json absent — "
                  "run pipeline/pull_flood_hazard.py)")
            sys.exit(3)
        sys.exit("gistda_flood_hazard.json missing — run: python3 pull_flood_hazard.py")

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_flood_hazard.py --check: SKIP (flood_hazard.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_flood_hazard.py --check: flood_hazard.json drifted — run "
                     "python3 pipeline/build_flood_hazard.py")
        print("build_flood_hazard.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    print("wrote %s (%d GISTDA districts; %d resolved to %d master districts = %.1f%%; %d unresolved)"
          % (OUT, m["n_gistda_districts"], m["n_district_resolved"], m["n_districts_present"],
             m["resolution_pct"], m["n_unresolved"]))
    print("  districts severe(>=%d): %d · chronic(>=%d): %d" %
          (m["severe_min"], m["n_districts_severe"], m["chronic_min"], m["n_districts_chronic"]))
    print("  branches flood-prone: %d · chronic: %d · severe: %d (of %d)" %
          (m["n_branches_flood_prone"], m["n_branches_chronic"], m["n_branches_severe"], m["n_branches"]))
    print("  top districts: %s" % ", ".join("%s=%d" % (k, v) for k, v in obj["top_districts"][:6]))


if __name__ == "__main__":
    main()
