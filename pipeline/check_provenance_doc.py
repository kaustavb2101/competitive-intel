#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_provenance_doc.py — tripwire: the provenance census ⇄ CLAUDE.md's stated count.

WHY THIS EXISTS
    `build_provenance.py` → `platform/data/provenance.json` censuses every committed
    `platform/data` layer and stamps each MEASURED / ESTIMATED / UNLABELLED. That JSON is
    already `--check`-gated, so its counts cannot silently drift from the actual layer set.
    But CLAUDE.md's "Provenance + guards" bullet ALSO prints those counts in prose:
        "… censuses every layer's MEASURED/ESTIMATED label (N layers · M MEASURED / E ESTIMATED
         / U unlabelled at this revision)."
    Nothing tied that sentence to the live census. Every autonomous run that adds a layer and
    re-runs `build_provenance.py` moves the JSON counts but leaves the prose behind — exactly
    what happened here (the doc read 146 · 85 / 61 while the census had grown to 149 · 86 / 63).
    A session that trusts CLAUDE.md then quotes a stale provenance headline with a green gate.
    That is the same provenance drift the determinism gate exists to catch, applied to the one
    census figure the doc carries by hand.

WHAT IT DOES
    DERIVES the expected CLAUDE.md substrings FROM the live census counts in provenance.json
    (read, never re-typed here) and asserts each is present in CLAUDE.md. So BOTH drift
    directions are caught:
      - add/remove a layer + re-run build_provenance.py  → the new counts no longer match the prose
      - edit the count sentence in CLAUDE.md              → the derived counts no longer appear there
    Nothing is written — a pure cross-consistency assertion, so no platform/data output and no
    provenance regen. Both the bare and the `--check` invocation run the same verification,
    exiting 1 on any mismatch so it is a clean tripwire for tests/run.sh and rederive_drift.py.

    python3 pipeline/check_provenance_doc.py            # report the figures, exit 1 on drift
    python3 pipeline/check_provenance_doc.py --check     # identical (gate-convention alias)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLAUDEMD = os.path.join(ROOT, "CLAUDE.md")
PROVENANCE = os.path.join(ROOT, "platform", "data", "provenance.json")


def _checks(counts):
    """(label, expected-substring) pairs, each DERIVED from the live census counts.
    The substrings mirror CLAUDE.md's exact wording so each is specific enough not to
    match an unrelated number elsewhere in the brief."""
    return [
        ("provenance.counts.layers", f"{counts['layers']} layers"),
        ("provenance.counts.measured", f"{counts['measured']} MEASURED"),
        ("provenance.counts.estimated", f"{counts['estimated']} ESTIMATED"),
        ("provenance.counts.unlabelled", f"{counts['unlabelled']} unlabelled"),
    ]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="gate-convention alias; identical behaviour (nothing is written)")
    ap.parse_args()

    with open(PROVENANCE, encoding="utf-8") as f:
        counts = json.load(f)["counts"]
    with open(CLAUDEMD, encoding="utf-8") as f:
        brief = f.read()

    checks = _checks(counts)
    missing = []
    for label, needle in checks:
        present = needle in brief
        print(f"  [{'OK ' if present else 'MISS'}] {label:32s} → {needle!r}  (CLAUDE.md brief)")
        if not present:
            missing.append((label, needle))

    if missing:
        print("\nFAIL check_provenance_doc: %d census figure(s) not found in CLAUDE.md —"
              % len(missing))
        for label, needle in missing:
            print(f"    {label}: expected {needle!r} in CLAUDE.md")
        print("  The live provenance census and the CLAUDE.md 'Provenance + guards' bullet have "
              "diverged. build_provenance.py is the source of truth — update the count sentence in "
              "CLAUDE.md (~ 'censuses every layer's MEASURED/ESTIMATED label (N layers · …)') to "
              "match platform/data/provenance.json's counts.")
        sys.exit(1)

    print("\nOK check_provenance_doc: all %d census figure(s) match the CLAUDE.md brief "
          "(%d layers · %d MEASURED / %d ESTIMATED / %d unlabelled)."
          % (len(checks), counts["layers"], counts["measured"],
             counts["estimated"], counts["unlabelled"]))


if __name__ == "__main__":
    main()
