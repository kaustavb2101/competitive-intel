#!/usr/bin/env python3
"""
build_branch_density.py — per-branch building density within 10km (MEASURED, Overture)
========================================================================================
Projects the already-committed `source-data/perimeter_counts.json` — a real, sourced
building-density count per branch that has sat UNUSED since it was written (2026-07-02,
commit dda7816, "Perimeter 3D audit") — into `platform/data/branch_density.json`, the
app's usual index-aligned layer shape, so it can be surfaced in the branch popup.

INPUT: source-data/perimeter_counts.json
  {meta: {generated_by, label, method, n_branches, buckets, index_note},
   counts: [int, ...]}  — counts[i] is index-aligned to platform/data/branches.json,
  built by binning Overture building centroids (from the 77 real per-province catchment
  pulls: 3 in-repo + 74 on the operator R2 CDN, capped 180k/province) onto a 0.1-degree
  grid and counting within 10km (equirect) of each branch. A zero means the CAPPED
  catchment file has no buildings there, NOT that the ground truth is empty (Bangkok/
  Rayong still carry pre-province-wide city-core files at the time of that pull).

ALIGNMENT SAFETY: perimeter_counts.json carries no per-record identity field (just a
bare counts[] array) and predates the branches_fingerprint convention, so it cannot be
re-verified byte-for-byte at build time the way a stamped layer can. Before wiring this
in, the branches.json ORDER/IDENTITY was manually confirmed unchanged since the counts
were generated: branches_fingerprint at commit dda7816 (2026-07-02, when
perimeter_counts.json was written) == the fingerprint of the branches.json committed
alongside THIS builder (e25867ab0c76d888...), despite two intervening derive.py runs
that touched branches.json's non-order fields. See docs/DATA_REFRESH_LOG.md for the
verification command. If a FUTURE branches.json reorder ever breaks this, the
branches_fingerprint gate (tests/validate_data.py) will catch it going forward, since
this builder stamps the CURRENT fingerprint into its own output.

OUTPUT per branch (index-aligned to branches.json):
  - buildings_10km : MEASURED building count within 10km (carried verbatim from source)
  - bucket         : density bucket (rich_1000plus / good_200_999 / thin_50_199 /
                     sparse_1_49 / empty_0), same thresholds as the source's own
                     meta.buckets tally (self-checked below — a threshold typo would
                     fail --check, not slip through silently).

Usage:
  python3 build_branch_density.py            # write platform/data/branch_density.json
  python3 build_branch_density.py --check    # re-run, byte-compare (SKIP if source absent)
"""
import argparse
import json
import os
import sys

from fingerprint import branches_fingerprint

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
SOURCE_DATA = os.path.join(REPO, "source-data")
BRANCHES = os.path.join(DATA, "branches.json")
SRC = os.path.join(SOURCE_DATA, "perimeter_counts.json")
OUT = os.path.join(DATA, "branch_density.json")

# same cutpoints as source-data/perimeter_counts.json's own meta.buckets tally
BUCKET_ORDER = ["rich_1000plus", "good_200_999", "thin_50_199", "sparse_1_49", "empty_0"]


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def _bucket(n):
    if n >= 1000:
        return "rich_1000plus"
    if n >= 200:
        return "good_200_999"
    if n >= 50:
        return "thin_50_199"
    if n >= 1:
        return "sparse_1_49"
    return "empty_0"


def build():
    if not os.path.exists(SRC):
        return None  # honest absent — no source, nothing to project (caller handles)

    src = _load(SRC)
    counts = src.get("counts") or []
    smeta = src.get("meta") or {}

    branches = _load(BRANCHES) if os.path.exists(BRANCHES) else []
    n = len(branches)

    if n == 0 or len(counts) != n:
        # length mismatch with the CURRENT master — the source predates today's branches.json
        # and can no longer be trusted as index-aligned. Do not fabricate a projection.
        return {
            "meta": {
                "generated_by": "build_branch_density.py",
                "absent": True,
                "label": "MEASURED building density within 10km (Overture) — UNAVAILABLE this run",
                "note": ("source-data/perimeter_counts.json has %d counts but branches.json has "
                          "%d records — length mismatch, cannot trust index alignment; honest "
                          "ABSENT-state emitted instead of a guessed projection." % (len(counts), n)),
                "n_branches": n,
            },
            "branches": [],
        }

    recs = [{"buildings_10km": int(c or 0), "bucket": _bucket(int(c or 0))} for c in counts]

    # self-check: our bucket tally must match the source's own meta.buckets tally exactly —
    # catches a cutpoint typo instead of silently shipping a wrong bucket label.
    tally = {k: 0 for k in BUCKET_ORDER}
    for r in recs:
        tally[r["bucket"]] += 1
    src_buckets = smeta.get("buckets") or {}
    if src_buckets and tally != src_buckets:
        raise AssertionError(
            "recomputed bucket tally %r does not match source-data/perimeter_counts.json's own "
            "meta.buckets %r — bucket thresholds have drifted from the source's; fix _bucket() "
            "before shipping" % (tally, src_buckets)
        )

    return {
        "meta": {
            "generated_by": "build_branch_density.py",
            "label": "MEASURED — building density within 10km of each branch (Overture footprints)",
            "provenance": (
                "source-data/perimeter_counts.json, %s. Method: %s"
                % (smeta.get("generated_by", "perimeter 3D audit workflow"), smeta.get("method", ""))
            ),
            "caveats": [
                smeta.get("label", ""),
                "perimeter_counts.json predates the branches_fingerprint convention and carries no "
                "per-record identity field; index alignment against the CURRENT branches.json was "
                "manually verified (fingerprint continuity since commit dda7816, 2026-07-02) before "
                "this builder was written — see docs/DATA_REFRESH_LOG.md.",
            ],
            "radius_km": 10.0,
            "n_branches": n,
            "branches_fingerprint": branches_fingerprint(branches),
            "buckets": tally,
            "index_aligned_to": "branches.json (record i == branch i)",
        },
        "branches": recs,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare against the committed JSON; exit 1 on drift "
                         "(exit 3 / SKIP when source-data/perimeter_counts.json is absent)")
    args = ap.parse_args()

    data = build()

    if args.check:
        if data is None:
            print("CHECK SKIP: source-data/perimeter_counts.json absent — branch_density not "
                  "byte-checkable", file=sys.stderr)
            sys.exit(3)
        text = dumps(data)
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as f:
            existing = f.read()
        if existing == text:
            print("CHECK OK: %s reproduces byte-for-byte (%d branches)" %
                  (OUT, data["meta"]["n_branches"]))
            sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    if data is None:
        print("SKIP: source-data/perimeter_counts.json absent — nothing to build", file=sys.stderr)
        sys.exit(3)

    text = dumps(data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    n = data["meta"]["n_branches"]
    print("wrote %s (%d branches, buckets=%s)" % (OUT, n, data["meta"].get("buckets")))


if __name__ == "__main__":
    main()
