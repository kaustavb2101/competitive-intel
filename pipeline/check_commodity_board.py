#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_commodity_board.py — guard the hand-maintained commodity board against its MEASURED source.

The Overview commodity board (source-data/commodity_board.json) is the canonical 11-item Pink Sheet
readout the app renders (derive.py -> meta.board) and that ~10 downstream builders consume
(build_commodities / build_crop_stress / build_collateral_outlook / build_impact_cards / ...). Its
`yoy` and `stale` (vintage) fields are the MEASURED World Bank Pink Sheet move for each commodity, but
the file is HAND-MAINTAINED: nothing enforced that its numbers still equal the two measured Pink Sheet
source files the board is transcribed from —

  source-data/commodities.json           MEASURED — Pink Sheet YoY for the five crops
                                         (rice / rubber / sugar / palm / maize)
  source-data/commodities_protein.json   MEASURED — Pink Sheet YoY for the protein / gold / timber items
                                         (chicken / beef / fishmeal / logs / sawnwood / gold)

so an editor could refresh one Pink Sheet file and leave the board showing a stale (now-wrong) MEASURED
number with no alarm. commodities_protein.json in particular was a COMMITTED input with zero consumers
until this guard — it is the source of six of the board's eleven numbers, wired in here.

This verifier asserts, for EVERY board item, that its `yoy` and `stale` equal the corresponding source
`yoy` and `date`. A board item whose label is not in the source map fails LOUDLY (rather than being
skipped) so a newly hand-typed board number can never silently escape the measured-source guard.

DETERMINISTIC + NETWORK-FREE — a pure read of three committed files. Exit codes match the gate idiom:
  0  every board number matches its Pink Sheet source
  2  drift — at least one board yoy/vintage no longer equals its measured source (details on stderr)
  3  a source file is absent (not drift — nothing to check)
`--check` is accepted (and is the default) so tests/run.sh can call it like the build_*.py --check guards.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "source-data")

# board label -> (source file key, commodity key in that file). EVERY board item must appear here;
# an unmapped board label is a guard escape and fails (exit 2), not a silent skip.
BOARD_TO_SOURCE = {
    "Rice":     ("crops", "rice"),
    "Rubber":   ("crops", "rubber"),
    "Sugar":    ("crops", "sugar"),
    "Palm oil": ("crops", "palm"),
    "Maize":    ("crops", "maize"),
    "Chicken":  ("protein", "chicken"),
    "Beef":     ("protein", "beef"),
    "Fishmeal": ("protein", "fishmeal"),
    "Logs":     ("protein", "logs"),
    "Sawnwood": ("protein", "sawnwood"),
    "Gold":     ("protein", "gold"),
}


def _load(name):
    with open(os.path.join(S, name), encoding="utf-8") as f:
        return json.load(f)


def main():
    for name in ("commodity_board.json", "commodities.json", "commodities_protein.json"):
        if not os.path.exists(os.path.join(S, name)):
            print("check_commodity_board.py: SKIP (source-data/%s absent)" % name, file=sys.stderr)
            return 3

    board = _load("commodity_board.json")
    src = {"crops": _load("commodities.json"), "protein": _load("commodities_protein.json")}

    problems = []
    for it in board:
        lab = it.get("lab", "?")
        if lab not in BOARD_TO_SOURCE:
            problems.append("board item %r has no Pink Sheet source mapping — add it to "
                            "BOARD_TO_SOURCE so its MEASURED number is guarded" % lab)
            continue
        which, key = BOARD_TO_SOURCE[lab]
        s = src[which].get(key)
        if not isinstance(s, dict):
            problems.append("board item %r maps to %s.%s, absent in the Pink Sheet source"
                            % (lab, which, key))
            continue
        if it.get("yoy") != s.get("yoy"):
            problems.append("board %r yoy=%r != Pink Sheet %s.%s yoy=%r"
                            % (lab, it.get("yoy"), which, key, s.get("yoy")))
        if it.get("stale") != s.get("date"):
            problems.append("board %r stale=%r != Pink Sheet %s.%s date=%r"
                            % (lab, it.get("stale"), which, key, s.get("date")))

    if problems:
        print("check_commodity_board.py: commodity board drifted from its MEASURED Pink Sheet source:",
              file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 2

    print("check_commodity_board.py: OK — all %d board items match commodities.json / "
          "commodities_protein.json (yoy + vintage)" % len(board))
    return 0


if __name__ == "__main__":
    # --check is the default and only mode; accepted so the gate can call it uniformly.
    sys.exit(main())
