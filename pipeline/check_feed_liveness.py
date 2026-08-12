#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_feed_liveness.py — fail loudly when a live feed has stopped being live.

WHY THIS EXISTS
---------------
Every existing guard in this repo tests PRESENCE. build_provenance.py --check asserts that each
platform/data file still reproduces byte-for-byte; validate_data.py asserts the numbers inside are
internally consistent; the live board renders a stamp. All of them pass with flying colours while a
feed is quietly dead, because a dead feed is not an ABSENT file — it is a present file that has
stopped changing. Three real failures in this repo were invisible to every gate we had:

  * youtube_comments.json sat at 2,416 comments for 9 days behind an expired API key. The puller
    ran on schedule, exited 0, and rewrote the file with an identical payload every single day.
  * set_filings had no cron entry in any workflow. Nothing pulled it, so nothing could notice.
  * investor_docs sys.exit'd in 0.1s on every run for want of pdfplumber — a 100% failure rate that
    never once turned a check red.

So this checker asks the two questions those failures needed, and they are NOT the same question:

  TEST A — STALE STAMP.  Is the feed's own vintage older than its cadence allows?
      Catches: puller unscheduled, puller crashing, source withdrawn.
      Blind to: a puller that runs fine and republishes the same payload forever.

  TEST B — FROZEN VALUE.  Has the number actually MOVED inside its cadence window?
      Catches: the expired-key class, where the stamp is refreshed daily and the value never is.
      This is the test nothing in the repo had, and it is the one the YouTube key needed.

A feed can pass A and fail B (youtube_comments), or pass B and fail A (a source that publishes a
real new value, late). Reporting them separately is deliberate: the remedy differs. A stale stamp
is a scheduling or plumbing problem; a frozen value is almost always an auth or upstream problem.

DETERMINISTIC + NETWORK-FREE — a pure read of two committed files. `--asof` pins the clock so the
output is reproducible in a test; without it the clock is today, which is what CI wants.

Exit codes match the gate idiom used by check_commodity_board.py:
  0  every feed is live (aging feeds are reported, not fatal — 'aging' is the usable-but-old band)
  2  at least one feed is STALE or FROZEN (details on stderr)
  3  an input file is absent — nothing to check, which is not the same as a pass
"""
import argparse
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOARD = os.path.join(ROOT, "platform", "data", "live_board.json")
HISTORY = os.path.join(ROOT, "source-data", "feed_history.json")

# ---------------------------------------------------------------- TEST B calibration
# How far back "has this moved recently?" looks, and how many observations must sit inside that
# window before a flat run is evidence of anything. Two points that agree prove nothing; a daily
# feed that has reported the identical number on five separate days is not reporting.
FROZEN_WINDOW = {"daily": 7, "weekly": 35, "monthly": 120, "quarterly": 400, "annual": 1200}
FROZEN_MIN_POINTS = {"daily": 5, "weekly": 4, "monthly": 3, "quarterly": 3, "annual": 3}

# Per-SERIES overrides for the frozen window, for feeds PULLED on one cadence whose VALUE legitimately
# MOVES on a slower one. Keyed by the pull cadence, FROZEN_WINDOW would cry wolf on these; keyed by the
# series' real movement cadence, it stays a live canary. A checker that cries wolf gets muted, and a
# muted checker is worth less than no checker — so this RE-CALIBRATES the test rather than exempting it
# (contrast FROZEN_EXEMPT): a flat run past the override window still fails, because past that horizon a
# flat value really is evidence of a dead upstream.
FROZEN_WINDOW_OVERRIDE = {
    # Retail Thai fuel is polled DAILY by the Bangchak API, but the pump price is a step function that
    # legitimately holds flat for one to two weeks between adjustments. Observed directly, not assumed:
    # fuel_gasohol95 held ฿36.69 for 11 straight daily readings (2026-07-22 .. 2026-08-04, a 13-day
    # span) while the puller ran on schedule, then stepped to 35.99 — the series carries 4 distinct
    # values over its life (37.45 / 34.94 / 36.69 / 35.99), so the value clearly moves; it just does
    # not move every 7 days. On the 7-day 'daily' window the checker fired FROZEN on 2026-08-11 during
    # a perfectly normal 6-day hold — a false alarm. TEST A (stale stamp) still watches the puller on
    # the daily cadence, so a puller that STOPS is caught within 7 days regardless; only TEST B's
    # value-movement horizon is widened here, to ~2.7x the longest observed legitimate hold.
    "fuel_gasohol95": 35,
}
FROZEN_MIN_POINTS_OVERRIDE = {
    "fuel_gasohol95": 15,   # ~a month of daily pulls must accumulate before a flat run is judged
}

# Series that are legitimately allowed to sit flat, with the reason. A checker that cries wolf gets
# muted, and a muted checker is worth less than no checker — so anything parked here needs a reason
# that would still read as true to someone who did not write it.
FROZEN_EXEMPT = {
    # Thai retail diesel is administered by the Oil Fuel Fund (กองทุนน้ำมันเชื้อเพลิง), so a flat run
    # of weeks is the NORMAL state, not a dead puller. Verified rather than assumed: on the day this
    # exemption was written fuel_prices.json carried diesel 36.69 "Hi Diesel S" and gasohol95 35.99
    # "Gasohol 95 S EVO" as separate fields with separate product names, and the source published its
    # own diesel_delta_tomorrow of 0.0 — the price is pinned upstream, not stuck downstream.
    #
    # Note what is NOT exempt: fuel_gasohol95, from the same pull and the same file, DOES step and
    # stays the live canary for this puller — but on a slower horizon than diesel's flat weeks, so it
    # is re-calibrated via FROZEN_WINDOW_OVERRIDE above rather than exempted. If the Bangchak API
    # dies, gasohol freezes past that horizon and TEST B fires — so coverage of the puller is kept.
    "fuel_diesel": "administered price (Oil Fuel Fund); fuel_gasohol95 is the live canary for this pull",
}


def _load(path, what):
    if not os.path.exists(path):
        print("check_feed_liveness.py: %s is absent (%s) — nothing to check."
              % (what, path), file=sys.stderr)
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _date(s):
    """Parse the leading YYYY-MM-DD of a stamp. Stamps carry times and zones; the day is enough."""
    if not isinstance(s, str) or len(s) < 10:
        return None
    try:
        return dt.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
    except (ValueError, TypeError):
        return None


def test_a_stale_stamps(board, asof):
    """Is each feed's own vintage inside the age its cadence allows?

    Thresholds are NOT restated here — they are read off the board rows, which build_live_board.py
    already stamped from its CADENCE table. One definition of "how old is too old for a weekly
    feed", owned by the builder that renders it.
    """
    stale, aging, undated = [], [], []
    for f in board.get("feeds") or []:
        aging_days = f.get("aging_days")
        fresh_days = f.get("fresh_days")
        if aging_days is None:            # 'reference' cadence — a registry that only moves when
            continue                      # reissued. Ageing it would cry wolf, by design.
        stamp = _date(f.get("stamp_iso") or f.get("stamp"))
        if stamp is None:
            undated.append(f)
            continue
        age = (asof - stamp).days
        row = (age, f)
        if age > aging_days:
            stale.append(row)
        elif fresh_days is not None and age > fresh_days:
            aging.append(row)
    stale.sort(reverse=True, key=lambda r: r[0])
    aging.sort(reverse=True, key=lambda r: r[0])
    return stale, aging, undated


def test_b_frozen_values(history, asof):
    """Has each accumulated series actually MOVED inside its cadence window?

    Only the accumulator can answer this. A feed's own file shows one value — 'now' — so it cannot
    reveal that 'now' has been the same number for nine days. source-data/feed_history.json keeps
    one dated row per pull, which is precisely the record needed.
    """
    frozen, thin = [], []
    for key, s in sorted((history.get("series") or {}).items()):
        if key in FROZEN_EXEMPT:
            continue
        cadence = s.get("cadence") or "daily"
        # A per-series override wins over the cadence default (see FROZEN_WINDOW_OVERRIDE): it lets a
        # feed pulled daily but moving on a slower step cadence be judged on its real movement horizon.
        window = FROZEN_WINDOW_OVERRIDE.get(key, FROZEN_WINDOW.get(cadence))
        min_pts = FROZEN_MIN_POINTS_OVERRIDE.get(key, FROZEN_MIN_POINTS.get(cadence))
        if window is None or min_pts is None:
            continue
        dates, values = s.get("dates") or [], s.get("values") or []
        if len(dates) != len(values):
            # Parallel arrays that disagree are a corrupt series, not a frozen one. Say so plainly
            # rather than silently reading past the shorter of the two.
            thin.append((key, "dates/values length mismatch (%d vs %d)" % (len(dates), len(values))))
            continue
        cutoff = asof - dt.timedelta(days=window)
        pts = [(d, v) for d, v in zip(dates, values) if (_date(d) or dt.date(1900, 1, 1)) >= cutoff]
        if len(pts) < min_pts:
            thin.append((key, "only %d point(s) in the last %dd — too few to judge"
                         % (len(pts), window)))
            continue
        distinct = {json.dumps(v, sort_keys=True) for _, v in pts}
        if len(distinct) == 1:
            frozen.append((key, s, len(pts), window, pts[0][1], pts[0][0], pts[-1][0]))
    return frozen, thin


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--asof", metavar="YYYY-MM-DD",
                    help="pin the clock, so the result is reproducible in a test "
                         "(default: today)")
    ap.add_argument("--check", action="store_true",
                    help="accepted for symmetry with the build_*.py guards; this is the only mode")
    args = ap.parse_args(argv)

    asof = _date(args.asof) if args.asof else dt.date.today()
    if asof is None:
        print("check_feed_liveness.py: --asof %r is not YYYY-MM-DD" % args.asof, file=sys.stderr)
        return 1

    board = _load(BOARD, "the live board")
    history = _load(HISTORY, "the feed-history accumulator")
    if board is None or history is None:
        return 3

    stale, aging, undated = test_a_stale_stamps(board, asof)
    frozen, thin = test_b_frozen_values(history, asof)

    n_feeds = len(board.get("feeds") or [])
    n_series = len((history.get("series") or {}))
    print("check_feed_liveness.py: %d board feeds, %d accumulated series, as of %s"
          % (n_feeds, n_series, asof.isoformat()))

    # ---- fatal: TEST A ---------------------------------------------------------------
    if stale:
        print("\nSTALE — the feed's own vintage is past the age its cadence allows:", file=sys.stderr)
        for age, f in stale:
            print("  - %-20s %s  stamp %s, %dd old (%s cadence allows %dd)"
                  % (f.get("key"), f.get("file"), f.get("stamp_iso") or f.get("stamp"),
                     age, f.get("cadence"), f.get("aging_days")), file=sys.stderr)

    # ---- fatal: TEST B ---------------------------------------------------------------
    if frozen:
        print("\nFROZEN — the stamp keeps moving but the VALUE has not. This is the expired-key\n"
              "shape: the puller runs, exits 0, and republishes an identical payload.", file=sys.stderr)
        for key, s, npts, window, val, first, last in frozen:
            print("  - %-20s %s: %d identical readings %s .. %s (last %dd), stuck at %r"
                  % (key, s.get("label") or s.get("source") or "", npts, first, last, window, val),
                  file=sys.stderr)

    # ---- informational ---------------------------------------------------------------
    if aging:
        print("\naging (past fresh, still inside the usable band — not a failure):")
        for age, f in aging:
            print("  - %-20s %dd old (%s: fresh %dd, usable to %dd)"
                  % (f.get("key"), age, f.get("cadence"), f.get("fresh_days"), f.get("aging_days")))
    if undated:
        print("\nno readable stamp (cannot be aged — worth a look, not a failure):")
        for f in undated:
            print("  - %-20s %s" % (f.get("key"), f.get("file")))
    if thin:
        print("\nnot yet judgeable on movement (too few accumulated points):")
        for key, why in thin:
            print("  - %-20s %s" % (key, why))
    if FROZEN_EXEMPT:
        # Printed every run, never silently applied: an exemption that stops being true should be
        # visible to whoever reads the log, not buried in the source of the checker.
        print("\nexempt from the movement test (flat is the expected state):")
        for key, why in sorted(FROZEN_EXEMPT.items()):
            print("  - %-20s %s" % (key, why))

    if stale or frozen:
        print("\ncheck_feed_liveness.py: FAIL — %d stale, %d frozen." % (len(stale), len(frozen)),
              file=sys.stderr)
        return 2

    print("\ncheck_feed_liveness.py: OK — every feed with a cadence is inside it, and every "
          "accumulated series has moved inside its window.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
