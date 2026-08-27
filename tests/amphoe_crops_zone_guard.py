#!/usr/bin/env python3
# amphoe_crops_zone_guard.py — the REDUNDANT-STAGING gate for the OAE per-zone crop files.
#
# CLAUDE.md: "Always state whether a number is measured or estimated" and prefer something honest
# over something that merely looks like progress. The committed staging files
# `source-data/staging/amphoe_crops_zone{1..12}.json` persistently violate that in disguise: seven
# are EMPTY probe artifacts (rows: 0) and the four populated ones (zone8/9/10/12, 427 rows total)
# are a STRICT DUPLICATE SUBSET of `source-data/staging/amphoe_crops_national.json` — every single
# row matches a national row on the full key (province_th, amphoe_th, crop, crop_year, source_file)
# AND on planted_rai, because the zone files were extracted FROM the same OAE HQ Geo-Informatics
# Center nationwide per-crop PDFs the national file already carries (their own meta.route says so).
#
# WHY THIS EXISTS (the same argument that justifies unverified_gpp_guard.py / mandate_guard.py): good
# labelling and hand-audit are NOT enough, because nothing in the gate LOCKED IT IN. The hazard is
# live and recurring — the files LOOK like unwired MEASURED coverage waiting to be folded into the
# already-wired `build_amphoe_crops.py`, so careful readers keep proposing exactly that:
#   - the 2026-08-19 PROGRESS_LOG entry recorded them as "Next recommended integration (a)" claiming
#     they would "extend per-crop grain from 9 provinces to 26";
#   - a 2026-08-27 negative-space audit re-ranked "fold the 4 populated zone files into
#     build_amphoe_crops.py" as the #1 improvement of the run.
# Both are FALSE: the national file already covers all 77 provinces (rice 74/67, cassava 50, rubber
# 42), the zone files add ZERO provinces (all 26 are a subset) and ZERO unique rows (all 427 are
# exact duplicates). Folding them in would only DOUBLE-COUNT 427 district-crop rows in a live app
# surface (`platform/data/amphoe_crops.json`, consumed by app.js + index.html) — a data-integrity
# regression dressed up as a coverage win. This turns the recurring manual re-audit into a gate.
#
# THE INVARIANT (self-lifting, mirrors the repo's UPSTREAM_CAPPED / gpp self-clearing idiom):
#   While every populated zone row is an exact duplicate of a national row (n_unique == 0), the zone
#   files carry no information the wired board lacks, so folding them in can only duplicate. The guard
#   therefore FAILs if ANY pipeline/*.py references the `amphoe_crops_zone` token (there is no
#   producer or consumer of it in-tree today — any reference is a fold-in attempt). The day a zone
#   file is re-pulled with a row the national file does NOT already carry (genuinely new district /
#   crop / vintage coverage), n_unique > 0, the precondition no longer holds, and the guard passes
#   trivially — a real integration becomes allowed automatically, no edit to this file needed.
#
# SCOPE (deliberately tight, false-positive-free): the ONLY token matched is `amphoe_crops_zone`
# (whole-token start) — it names ONLY these files and never collides with `amphoe_crops_national`
# or the output `amphoe_crops.json`, which build_amphoe_crops.py legitimately reads/writes.
#
# Offline, stdlib-only, deterministic. Exit 0 = clean (redundant + unwired, OR national absent, OR a
# zone file now carries genuinely new rows); 1 = a fold-in path is live while the files are duplicates.

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
STAGING = os.path.join(REPO, "source-data", "staging")
NATIONAL = os.path.join(STAGING, "amphoe_crops_national.json")

# Whole-token start match: "amphoe_crops_zone" names only the zone files (zone8, zone*, ...) and is a
# strict prefix that never matches "amphoe_crops_national" or "amphoe_crops.json".
TOKEN = re.compile(r"(?<![A-Za-z0-9_])amphoe_crops_zone")


def _fullkey(r):
    return (r.get("province_th"), r.get("amphoe_th"), r.get("crop"),
            r.get("crop_year") or r.get("year"), r.get("source_file"))


def n_unique_rows(national_rows, zone_rows):
    """Count zone rows that are NOT an exact duplicate of a national row — absent full key, OR present
    but with a divergent planted_rai (genuinely new/updated data the national file lacks). Pure
    function so the self-test can feed synthetic inputs. n_unique == 0 => the zone rows are pure
    duplicates and carry nothing the national file does not already have."""
    nat = {}
    for r in national_rows:
        nat[_fullkey(r)] = r.get("planted_rai")
    n_unique = 0
    for r in zone_rows:
        k = _fullkey(r)
        if k not in nat or nat[k] != r.get("planted_rai"):
            n_unique += 1
    return n_unique


def _referencers(texts_by_name):
    """Names in texts_by_name (a {name: source_text} map) that reference the token. There is no
    legitimate producer or consumer of the zone token in-tree, so ANY reference is a fold-in path.
    Pure function so the self-test can feed synthetic inputs."""
    return sorted(name for name, txt in texts_by_name.items() if TOKEN.search(txt))


def _selftest():
    """Prove the guard FIRES on a fold-in path while the files are duplicates, and stays QUIET both
    when a zone row is genuinely new AND on unrelated tokens. A drift here is itself a gate failure,
    so the guard can never pass vacuously."""
    fails = []
    nat = [{"province_th": "กระบี่", "amphoe_th": "เกาะลันตา", "crop": "rubber",
            "crop_year": "2567", "source_file": "rubber_2567.pdf", "planted_rai": 34574.0}]
    dup = [dict(nat[0])]                       # exact duplicate
    new = [dict(nat[0], amphoe_th="อ่าวลึก")]  # a district the national file lacks

    # duplicate detection
    if n_unique_rows(nat, dup) != 0:
        fails.append("n_unique_rows should be 0 for an exact duplicate row")
    if n_unique_rows(nat, new) != 1:
        fails.append("n_unique_rows should be 1 for a genuinely new district row")
    if n_unique_rows(nat, [dict(nat[0], planted_rai=99.0)]) != 1:
        fails.append("n_unique_rows should be 1 when planted_rai diverges (updated data)")

    # referencer detection: must fire on any zone reference...
    if _referencers({"build_amphoe_crops.py": "glob('amphoe_crops_zone*.json')"}) != ["build_amphoe_crops.py"]:
        fails.append("SHOULD-FIRE: a builder globbing amphoe_crops_zone was not flagged")
    if _referencers({"foo.py": "open('source-data/staging/amphoe_crops_zone8.json')"}) != ["foo.py"]:
        fails.append("SHOULD-FIRE: a script reading amphoe_crops_zone8 was not flagged")
    # ...but never on the national file or the output board (false-positive guard)
    if _referencers({"build_amphoe_crops.py": "IN_NAT='amphoe_crops_national.json'; OUT='amphoe_crops.json'"}) != []:
        fails.append("FALSE POSITIVE: matched amphoe_crops_national / amphoe_crops.json")
    return fails


def _load_rows(path):
    try:
        return json.load(open(path, encoding="utf-8")).get("rows", []) or []
    except Exception:
        return []


def main():
    st = _selftest()
    if st:
        print("amphoe_crops_zone_guard: SELF-TEST FAILED (guard logic is unsound, not a data problem):")
        for f in st:
            print("   -", f)
        return 1

    if not os.path.exists(NATIONAL):
        print("amphoe_crops_zone_guard: OK — amphoe_crops_national.json absent, nothing to compare against.")
        return 0

    zone_files = sorted(glob.glob(os.path.join(STAGING, "amphoe_crops_zone*.json")))
    if not zone_files:
        print("amphoe_crops_zone_guard: OK — no amphoe_crops_zone*.json staging files present.")
        return 0

    national_rows = _load_rows(NATIONAL)
    all_zone_rows, populated, empty = [], [], []
    for zf in zone_files:
        rows = _load_rows(zf)
        (populated if rows else empty).append(os.path.basename(zf))
        all_zone_rows.extend(rows)

    n_unique = n_unique_rows(national_rows, all_zone_rows)

    if n_unique > 0:
        # A zone file now carries rows the national file does not — genuine coverage, integration is
        # potentially valuable. The redundancy precondition no longer holds; pass and stop guarding.
        print("amphoe_crops_zone_guard: OK — zone staging now carries %d row(s) absent from "
              "amphoe_crops_national.json; the files are no longer pure duplicates and folding the "
              "NEW rows into build_amphoe_crops.py is now allowed." % n_unique)
        return 0

    # Still pure duplicates: assert no fold-in path exists anywhere in the pipeline.
    pipe = {}
    for p in sorted(glob.glob(os.path.join(REPO, "pipeline", "*.py"))):
        pipe[os.path.basename(p)] = open(p, encoding="utf-8", errors="ignore").read()
    hits = _referencers(pipe)

    if hits:
        print("amphoe_crops_zone_guard: a pipeline script references the REDUNDANT amphoe_crops_zone "
              "staging files (%d populated, all %d rows are exact duplicates of amphoe_crops_national — "
              "0 new provinces, 0 new rows). Folding them into build_amphoe_crops.py would DOUBLE-COUNT "
              "district-crop rows in the live #map board." % (len(populated), len(all_zone_rows)))
        for name in hits:
            print("   fold-in path: %s references amphoe_crops_zone*." % name)
        print("   Fix: drop the reference (the national file already carries every zone row), OR "
              "re-pull the zone files with genuinely NEW district/crop/vintage rows the national file "
              "lacks (which lifts this guard automatically and makes folding the new rows worthwhile).")
        return 1

    print("amphoe_crops_zone_guard: OK — %d populated zone file(s), all %d rows are exact duplicates "
          "of amphoe_crops_national.json (0 new provinces / rows); %d empty probe file(s). No pipeline "
          "script folds them in. Do NOT wire them into build_amphoe_crops.py — it would only "
          "double-count." % (len(populated), len(all_zone_rows), len(empty)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
