#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_heng.py — ONE COMMAND lands the Heng official-locator upload in the app.

THE FLOW
--------
1. On the Thai laptop, `pull_heng_locator.py` walks Heng Leasing's official branch-finder
   (hengleasing.com is Cloudflare-blocked from the cloud sandbox) and writes
   `source-data/heng_branches.json`. Kaustav uploads that file here.
2. `python3 ingest_heng.py` (this script) then does EVERYTHING:
     a. VALIDATE the upload — structure ({meta,items:[{brand:'Heng',name,lat,lng,prov,source}]}),
        every coordinate inside the Thailand bbox, plausible count (WARN outside 300–600 —
        Heng's headline network is ~450 branches; its archived countBranch.php once reported
        852 service points, so a big miss either way means the pull walked the wrong endpoint).
     b. MERGE the official set into `source-data/competitors_official.json` as the Heng brand
        entry (5dp proximity de-dupe, sorted — exactly how the Srisawad/Tidlor/Muangthai
        official sets are stored). This REPLACES the ~340-point Google∪Overture Heng sample:
        `build_competitor_census.py` already prefers official-locator data per brand, so once
        Heng is in the official file the sample is skipped automatically (same rule as the
        other three brands) and the census de-dupe/meta stay intact.
     c. REBUILD `platform/data/competitors_census.json` via build_competitor_census.py, then
        every downstream layer that reads the census (coverage, rival density, opportunity
        score, exit white-space, province deep-dives) so `bash tests/run.sh check` stays green.
     d. PRINT a before/after per-brand count table so the upgrade is visible at a glance.

NO FABRICATION: this script only moves real published branch coordinates from Heng's own
locator into the census. If the upload is malformed it fails loudly and writes nothing.

DETERMINISTIC + NETWORK-FREE. `--check` (the gate runs it) verifies byte-exact reproduce of
the merged competitors_official.json from heng_branches.json; when heng_branches.json is
absent (not uploaded yet) --check SKIP-PASSES, same pattern as the other optional builders.

Usage:
  python3 ingest_heng.py            # validate + merge + rebuild census & downstream + table
  python3 ingest_heng.py --check    # verify the merge reproduces byte-for-byte (offline)
"""
import argparse
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HENG = os.path.join(ROOT, "source-data", "heng_branches.json")
OFFICIAL = os.path.join(ROOT, "source-data", "competitors_official.json")
CENSUS = os.path.join(ROOT, "platform", "data", "competitors_census.json")

# Thailand bbox — minlat, minlng, maxlat, maxlng (same box pull_heng_locator.py enforces).
TH = (5.4, 97.2, 20.7, 105.8)
# Plausibility band around Heng's ~450-branch headline network (WARN only, never fabricate/trim;
# the archived countBranch.php reported 852 service points, so counts are noisy by nature).
PLAUSIBLE_LO, PLAUSIBLE_HI, HEADLINE = 300, 600, 450

# Downstream builders that read competitors_census.json — re-run after a census change so the
# determinism gate (tests/run.sh check) stays green in one command.
DOWNSTREAM = [
    "build_competitor_coverage.py",
    "build_rival_density.py",
    "build_rival_pressure.py",
    "build_contested_pop.py",
    "build_opportunity_score.py",
    "build_exit_whitespace.py",
    "build_province.py",
]


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate(d):
    """Return a list of problems (empty = valid). Structure per pull_heng_locator.py's contract:
    {meta:{...}, items:[{brand:'Heng', name, lat, lng, prov, source}, ...]}."""
    if not isinstance(d, dict):
        return ["top level is not an object (expected {meta,items})"]
    errs = []
    if not isinstance(d.get("meta"), dict):
        errs.append("meta missing or not an object")
    items = d.get("items")
    if not isinstance(items, list) or not items:
        errs.append("items missing or empty — nothing to ingest (refusing: a valid pull always has branches)")
        return errs
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            errs.append("#%d not an object" % i)
        else:
            probs = []
            if it.get("brand") != "Heng":
                probs.append("brand=%r (expected 'Heng')" % it.get("brand"))
            if not isinstance(it.get("name", ""), str):
                probs.append("name not a string")
            if not isinstance(it.get("prov", ""), str):
                probs.append("prov not a string")
            if not it.get("source"):
                probs.append("source missing (expected 'official-locator')")
            la, ln = it.get("lat"), it.get("lng")
            if not (_finite(la) and _finite(ln) and TH[0] <= la <= TH[2] and TH[1] <= ln <= TH[3]):
                probs.append("coords outside Thailand bbox %s: lat=%r lng=%r" % (TH, la, ln))
            if probs:
                errs.append("#%d: %s" % (i, "; ".join(probs)))
        if len(errs) >= 12:
            errs.append("... (stopping after 12 problems — fix the pull and re-upload)")
            break
    return errs


def heng_coords(d):
    """Deterministic official coord set: sort, then keep-first de-dupe at 5dp proximity —
    the same convention the other official-locator brand sets in competitors_official.json use."""
    pts = sorted((round(float(it["lat"]), 6), round(float(it["lng"]), 6)) for it in d["items"])
    seen, out = set(), []
    for la, ln in pts:
        k = (round(la, 5), round(ln, 5))
        if k in seen:
            continue
        seen.add(k)
        out.append([la, ln])
    return out


def merged_official_text(heng):
    """Fold the Heng official set into competitors_official.json (idempotent, byte-stable)."""
    official = _load(OFFICIAL)
    if official is None:
        official = {"meta": {"source": "Official operator store-locators. MEASURED coordinates — "
                                       "no synthesis.", "brands": {}}, "brands": {}}
    coords = heng_coords(heng)
    hmeta = heng.get("meta") or {}
    endpoint = (hmeta.get("endpoint") or hmeta.get("source")
                or "https://www.hengleasing.com/branch/ (province-walk)")
    official.setdefault("brands", {})["Heng"] = {"n": len(coords), "endpoint": endpoint,
                                                 "coords": coords}
    meta = official.setdefault("meta", {})
    meta.setdefault("brands", {})["Heng"] = {"n": len(coords), "endpoint": endpoint}
    meta["pulled_note"] = ("Srisawad/Tidlor/Muangthai pulled from the cloud sandbox (TLS-chain "
                           "completion against each live branch endpoint); Heng ingested from the "
                           "official hengleasing.com branch-finder walked from the Thai laptop "
                           "(pull_heng_locator.py -> source-data/heng_branches.json -> ingest_heng.py).")
    return json.dumps(official, ensure_ascii=False, separators=(",", ":")), len(coords)


def census_by_brand():
    d = _load(CENSUS)
    if not isinstance(d, dict):
        return {}
    return dict(((d.get("meta") or {}).get("counts") or {}).get("by_brand") or {})


def print_table(before, after):
    brands = sorted(set(before) | set(after))
    wb = max([len("brand")] + [len(b) for b in brands])
    print("\nCENSUS PER-BRAND COUNTS — before vs after the Heng official-locator merge")
    print("  %-*s  %10s  %10s  %s" % (wb, "brand", "before", "after", "delta"))
    for b in brands:
        x, y = before.get(b, 0), after.get(b, 0)
        print("  %-*s  %10d  %10d  %+d" % (wb, b, x, y, y - x))
    print("  %-*s  %10d  %10d  %+d" % (wb, "TOTAL", sum(before.values()), sum(after.values()),
                                       sum(after.values()) - sum(before.values())))


def run(check=False):
    heng = _load(HENG)
    if heng is None:
        if check:
            print("SKIP: source-data/heng_branches.json absent — nothing to verify yet "
                  "(produce it with pull_heng_locator.py on the Thai laptop, upload, re-run).")
            return 0
        print("source-data/heng_branches.json is not here yet — nothing to ingest.\n"
              "On the Thai laptop:  cd pipeline && python pull_heng_locator.py\n"
              "then upload source-data/heng_branches.json and re-run this ONE command:\n"
              "  python3 ingest_heng.py")
        return 0

    errs = validate(heng)
    if errs:
        print("INVALID upload — source-data/heng_branches.json does not match the contract "
              "({meta,items:[{brand:'Heng',name,lat,lng,prov,source}]}). Nothing written.")
        for e in errs:
            print("  - %s" % e)
        return 1

    text, n = merged_official_text(heng)
    if not (PLAUSIBLE_LO <= n <= PLAUSIBLE_HI):
        print("WARN: %d unique Heng branches is outside the %d–%d plausibility band around the "
              "~%d-branch headline network (archived countBranch.php once reported 852 service "
              "points). Ingesting anyway — every point is a real locator coordinate — but "
              "double-check the pull walked the right endpoint." % (n, PLAUSIBLE_LO, PLAUSIBLE_HI, HEADLINE))

    if check:
        cur = open(OFFICIAL, encoding="utf-8").read() if os.path.exists(OFFICIAL) else None
        if cur != text:
            print("DRIFT: source-data/competitors_official.json does not contain the merged Heng "
                  "official set — run: python3 ingest_heng.py")
            return 1
        census = _load(CENSUS)
        official_brands = (((census or {}).get("meta") or {}).get("official_locator_brands")) or []
        if "Heng" not in official_brands:
            print("DRIFT: competitors_census.json still treats Heng as a sample brand — "
                  "run: python3 ingest_heng.py")
            return 1
        print("OK: Heng official-locator merge reproduces (%d branches, official in census)" % n)
        return 0

    before = census_by_brand()

    with open(OFFICIAL, "w", encoding="utf-8") as f:
        f.write(text)
    print("merged %d unique Heng official-locator branches -> source-data/competitors_official.json"
          % n)

    # Rebuild the census (this is where the ~340-point sample is replaced by the official set —
    # build_competitor_census.py uses the official file as the sole source for any brand in it).
    sys.path.insert(0, HERE)
    import build_competitor_census as bcc
    rc = bcc.run(check=False)
    if rc:
        print("FAILED: build_competitor_census.py returned %d — census not rebuilt." % rc)
        return rc

    # Downstream layers that read the census — re-run so tests/run.sh check stays green.
    for script in DOWNSTREAM:
        path = os.path.join(HERE, script)
        if not os.path.exists(path):
            print("  skip %s (not present)" % script)
            continue
        r = subprocess.run([sys.executable, path], cwd=HERE,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        tail = (r.stdout or b"").decode("utf-8", "replace").strip().splitlines()
        print("  %s %s — %s" % ("ok" if r.returncode == 0 else "FAIL", script,
                                tail[-1] if tail else "(no output)"))
        if r.returncode:
            print("FAILED: %s returned %d — fix before committing." % (script, r.returncode))
            return r.returncode

    print_table(before, census_by_brand())
    print("\nDone. Heng is now an OFFICIAL-LOCATOR brand in the census (MEASURED, full network). "
          "Run `bash tests/run.sh check` before committing.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="one-command Heng official-locator ingest "
                                             "(heng_branches.json -> competitor census)")
    ap.add_argument("--check", action="store_true",
                    help="verify the merge reproduces byte-for-byte; skip-pass when the upload is absent")
    raise SystemExit(run(check=ap.parse_args().check))
