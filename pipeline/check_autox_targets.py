#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_autox_targets.py — tripwire: AutoX's own headline targets ⇄ CLAUDE.md.

WHY THIS EXISTS
    Every RIVAL constant on the objective-#2 competitive board is now digest-locked
    (check_peer_constants.py ⇄ RESEARCH_DIGEST.md §B). But the peer ROE ladder also
    renders ONE AutoX self-figure — AutoX's stated 25% ROE TARGET — as the reference
    line the exec reads every peer's ROE against. It is hand-carried as a CITED constant:
        pipeline/build_peer_scoreboard.py  →  AUTOX_ROE_TARGET  (surfaced on #acq / obj #2)
    Its single source of truth is the project brief in CLAUDE.md ("… ฿70bn loans, 25% ROE").
    Unlike every rival figure, nothing gate-checks it. AutoX is a corp-strategy shop, so a
    revised ROE target is a realistic edit — and if CLAUDE.md were updated (or the builder
    were) without the other, the peer ladder would silently compare rivals against a STALE
    AutoX benchmark with a green gate. That is exactly the provenance drift this repo's
    determinism gate exists to catch, applied to the one AutoX self-figure it had missed.

WHAT IT DOES
    DERIVES the expected CLAUDE.md substring FROM the live builder constant (imported, not
    re-typed here) and asserts it is present in CLAUDE.md. So BOTH drift directions are caught:
      - edit AUTOX_ROE_TARGET in the builder  → its derived "<n>% ROE" no longer in CLAUDE.md
      - edit the "25% ROE" line in CLAUDE.md   → the builder's derived substring is no longer there
    Nothing is written — a pure cross-consistency assertion, so no platform/data output and no
    provenance regen. Both the bare and the `--check` invocation run the same verification,
    exiting 1 on any mismatch so it is a clean tripwire for tests/run.sh and rederive_drift.py.

    python3 pipeline/check_autox_targets.py            # report the figure, exit 1 on drift
    python3 pipeline/check_autox_targets.py --check     # identical (gate-convention alias)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLAUDEMD = os.path.join(ROOT, "CLAUDE.md")

# Import the builder's constant live, so a builder edit is what changes the expected
# substring (never a second hand-typed copy here). build_peer_scoreboard imports only stdlib
# at module level and reads no file until build()/main() — importing it just binds the constant.
sys.path.insert(0, HERE)
import build_peer_scoreboard as bps  # noqa: E402


def _pct(value):
    """Render a percent the way CLAUDE.md prints it: no trailing '.0' for a whole number
    (25.0 -> '25'), but a real decimal is kept (25.5 -> '25.5'). `:g` does exactly this."""
    return f"{value:g}"


def _checks():
    """(label, expected-substring) pairs, each DERIVED from a live builder constant."""
    return [
        ("build_peer_scoreboard.AUTOX_ROE_TARGET", f"{_pct(bps.AUTOX_ROE_TARGET)}% ROE"),
    ]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="gate-convention alias; identical behaviour (nothing is written)")
    ap.parse_args()

    with open(CLAUDEMD, encoding="utf-8") as f:
        brief = f.read()

    checks = _checks()
    missing = []
    for label, needle in checks:
        present = needle in brief
        print(f"  [{'OK ' if present else 'MISS'}] {label:44s} → {needle!r}  (CLAUDE.md brief)")
        if not present:
            missing.append((label, needle))

    if missing:
        print("\nFAIL check_autox_targets: %d AutoX target figure(s) not found in CLAUDE.md —"
              % len(missing))
        for label, needle in missing:
            print(f"    {label}: expected {needle!r} in CLAUDE.md")
        print("  The builder constant and the CLAUDE.md brief have diverged. Reconcile "
              "build_peer_scoreboard.py with CLAUDE.md (update whichever is stale after a "
              "strategy/target revision).")
        sys.exit(1)

    print("\nOK check_autox_targets: all %d AutoX target constant(s) match the CLAUDE.md brief."
          % len(checks))


if __name__ == "__main__":
    main()
