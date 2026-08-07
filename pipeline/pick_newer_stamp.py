#!/usr/bin/env python3
"""pick_newer_stamp.py — for a conflicted data file, which side is the newer OBSERVATION?

WHY THIS EXISTS
---------------
resolve_derived_conflicts.sh resolves anything under platform/data/ by taking the base's side,
on the reasoning that a generated layer is about to be recomputed from committed sources anyway,
so which side you keep cannot matter. That reasoning is sound — for generated layers.

Three files under platform/data/ are NOT generated. They are PULLED snapshots with no builder
behind them:

    platform/data/thaiwater_flood.json    live river / reservoir levels
    platform/data/thaiwater_rain.json     live 24h rainfall

and source-data/ has the same shape in nabc_prices.json / farmgate_prices.json. For those, "take
the base's side and re-derive" silently reverts to the OLDER reading, because no re-derive will
ever put the newer one back. It is the quietest possible failure: the gate stays green (the tree
is perfectly self-consistent), the live card just shows yesterday. Worse, feed_history accumulates
independently, so the card and its own history end up disagreeing about the same day.

This bit for real on 2026-08-07 while landing two ThaiWater PRs: four files (both thaiwater
layers, nabc_prices, farmgate_prices) would have reverted to the 08-06 pull while feed_history
kept 08-07. The 4x/day cadence makes it likelier still — a data job whose base moved between
checkout and push would discard the reading it had just pulled.

THE RULE
--------
Compare the two sides' own declared observation date (meta.observed_to, else meta.pulled, else
meta.updated) and print which side to keep. NEVER this machine's clock — the file's own stamp,
which is the same discipline append_history.py follows.

  - both sides carry a stamp and they differ  -> keep the newer, exit 0
  - no stamp on either side, or equal stamps  -> "theirs", exit 0 (a generated layer; the
                                                 caller's re-derive settles it, as before)
  - a side does not parse as JSON             -> "theirs", exit 0 (same fallback; never guess)

Prints exactly one of `ours` / `theirs` on stdout so the shell can act on it, and a one-line
reason on stderr so the run log says WHY a side was kept rather than leaving it silent.

Usage:
  python3 pick_newer_stamp.py --ours <file> --theirs <file>
  python3 pick_newer_stamp.py --selftest
"""
import argparse
import json
import sys

STAMP_KEYS = ("observed_to", "pulled", "updated")


def stamp(text):
    """The observation date this document claims, or None if it claims none."""
    try:
        meta = json.loads(text).get("meta")
    except Exception:
        return None
    if not isinstance(meta, dict):
        return None
    for k in STAMP_KEYS:
        v = meta.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def pick(ours_text, theirs_text):
    """(side, reason). Side is 'ours' or 'theirs'."""
    so, st = stamp(ours_text), stamp(theirs_text)
    if so is None or st is None:
        return "theirs", "no observation stamp on both sides — treating as generated"
    if so == st:
        return "theirs", "same observation stamp (%s) — treating as generated" % so
    # ISO-8601 prefixes sort lexicographically, which is why the pullers write them that way.
    if so > st:
        return "ours", "ours observed %s, theirs %s — keeping the newer reading" % (so, st)
    return "theirs", "theirs observed %s, ours %s — keeping the newer reading" % (st, so)


def selftest():
    J = json.dumps
    cases = [
        # (ours, theirs, expected side, label)
        (J({"meta": {"observed_to": "2026-08-07 07:50"}}),
         J({"meta": {"observed_to": "2026-08-06 05:20"}}), "ours", "ours is newer"),
        (J({"meta": {"observed_to": "2026-08-06"}}),
         J({"meta": {"observed_to": "2026-08-07"}}), "theirs", "theirs is newer"),
        (J({"meta": {"observed_to": "2026-08-07"}}),
         J({"meta": {"observed_to": "2026-08-07"}}), "theirs", "equal stamps -> generated path"),
        (J({"meta": {"pulled": "2026-08-07"}}),
         J({"meta": {"pulled": "2026-08-05"}}), "ours", "falls back to meta.pulled"),
        # observed_to WINS over pulled on the same document: the ThaiWater job runs at 21:20 UTC,
        # already the next morning in Bangkok, so pulled is a day ahead of what the gauges say.
        (J({"meta": {"observed_to": "2026-08-05", "pulled": "2026-08-09"}}),
         J({"meta": {"observed_to": "2026-08-06", "pulled": "2026-08-06"}}), "theirs",
         "observed_to outranks pulled"),
        (J({"meta": {}}), J({"meta": {"pulled": "2026-08-07"}}), "theirs", "one side unstamped"),
        (J({"provinces": []}), J({"provinces": [1]}), "theirs", "no meta at all"),
        ("not json {{{", J({"meta": {"pulled": "2026-08-07"}}), "theirs", "unparseable side"),
        ("", "", "theirs", "both empty"),
        (J({"meta": {"updated": "2026M07"}}),
         J({"meta": {"updated": "2026M06"}}), "ours", "vintage strings sort too"),
        (J({"meta": {"observed_to": ""}}),
         J({"meta": {"observed_to": "2026-08-07"}}), "theirs", "blank stamp is no stamp"),
        (J({"meta": {"observed_to": None}}),
         J({"meta": {"observed_to": "2026-08-07"}}), "theirs", "null stamp is no stamp"),
        (J({"meta": ["not", "a", "dict"]}),
         J({"meta": {"pulled": "2026-08-07"}}), "theirs", "meta is not an object"),
    ]
    bad = 0
    for ours, theirs, want, label in cases:
        got, why = pick(ours, theirs)
        ok = got == want
        bad += not ok
        print("  %s %-32s -> %-6s (%s)" % ("ok  " if ok else "FAIL", label, got, why))
    print("%d/%d passed" % (len(cases) - bad, len(cases)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ours")
    ap.add_argument("--theirs")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if not a.ours or not a.theirs:
        ap.error("--ours and --theirs are both required")

    def read(p):
        try:
            with open(p, encoding="utf-8") as fh:
                return fh.read()
        except Exception:
            return ""

    side, why = pick(read(a.ours), read(a.theirs))
    print(why, file=sys.stderr)
    print(side)


if __name__ == "__main__":
    main()
