#!/usr/bin/env python3
# feed_freshness.py — the "no puller left to age in silence" tripwire.
#
# CLAUDE.md, "Where to go next" §3: the standing service worry is that a puller quietly stops
# running and its feed "ages in silence" while everyone assumes the data is live. The determinism
# gate already proves platform/data/feed_history.json reproduces byte-for-byte from the accumulator
# (build_feed_history.py --check) — but that only proves the PROJECTION is faithful, NOT that any
# series is still being fed. If one puller dies, its series simply stops gaining points; the
# accumulator and its projection stay perfectly self-consistent, --check still passes, and the dead
# feed rots undetected until a human happens to eyeball the chart. Every series already carries its
# observation `dates`, so the staleness signal is right there — it was just never checked.
#
# WHAT THIS CATCHES (deliberately scoped to the real failure mode): DIVERGENT staleness — one feed
# falling far behind while its siblings keep updating. That is exactly the "a single puller died"
# case §3 worries about. It does NOT try to catch a TOTAL pipeline freeze (every puller stops at
# once) — that is the nightly live site-health job's beat (it files a GitHub issue), and this check
# cannot see it anyway because it measures each series against its siblings, not against a clock.
#
# HOW (deterministic, NEVER wall-clock — CLAUDE.md's iron rule for this data): the reference "now"
# is the NEWEST observation date across ALL series (the data's own leading edge), never the machine
# clock. A series is DEAD only when it lags that leading edge by more than a generous, cadence-aware
# bound — far beyond any plausible normal cadence gap, so ordinary weekly/holiday lag never trips it.
# The bounds are intentionally loud-only-when-truly-abandoned so this never freezes the other data
# loops' green-gate auto-merges on a merely-late feed; it fires only when a feed is genuinely rotting.
#
# Offline, stdlib-only, deterministic. Exit 0 = every feed fresh (or clean-absent); exit 1 = a feed
# has aged past its dead-bound while its siblings moved on. Exit 3 = the history file is absent
# (same "not-a-failure, just not built here" convention build_feed_history.py --check uses).

import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FEED = os.path.join(REPO, "platform", "data", "feed_history.json")

# Dead-bounds in days behind the newest observation across all series. Generous by design: a weekly
# feed can legitimately lag ~7-10d (and more across a Thai public-holiday cluster), a daily feed a
# few days over a long weekend / source outage — none of that is a dead puller. These bounds sit far
# above that so the tripwire fires only on genuine abandonment, never on normal cadence.
DEAD_BOUND_DAYS = {"daily": 45, "weekly": 60}
DEFAULT_BOUND_DAYS = 120  # unknown/irregular cadence: only a very long silence counts as dead


def _parse(d):
    """Lenient ISO-ish date parse. Returns a date or None (a malformed stamp is not this check's
    job to police — validate_data.py owns shape; here it just doesn't count as an observation)."""
    try:
        return datetime.date.fromisoformat(d[:10])
    except (ValueError, TypeError):
        return None


def evaluate(series):
    """Pure core (unit-testable): given {name: {cadence, dates:[...]}} return (leading_edge, dead)
    where dead = [(name, last_date, lag_days, bound)] for series past their cadence dead-bound."""
    last_by = {}
    for name, s in series.items():
        dates = [d for d in (_parse(x) for x in s.get("dates", [])) if d]
        if dates:
            last_by[name] = max(dates)
    if not last_by:
        return None, []
    lead = max(last_by.values())
    dead = []
    for name, last in sorted(last_by.items()):
        lag = (lead - last).days
        bound = DEAD_BOUND_DAYS.get(series[name].get("cadence"), DEFAULT_BOUND_DAYS)
        if lag > bound:
            dead.append((name, last.isoformat(), lag, bound))
    return lead, dead


def _selftest():
    """Prove both directions: a fresh sibling set is clean; one long-dead daily feed fires; and a
    merely-late weekly feed (inside its bound) stays quiet. Guards against a bound/logic regression
    silently disarming the tripwire."""
    fails = []
    fresh = {
        "a": {"cadence": "daily", "dates": ["2026-09-08", "2026-09-09"]},
        "b": {"cadence": "weekly", "dates": ["2026-09-02", "2026-09-06"]},
    }
    lead, dead = evaluate(fresh)
    if lead != datetime.date(2026, 9, 9) or dead:
        fails.append("fresh sibling set should be clean, got dead=%r" % (dead,))

    one_dead = {
        "live": {"cadence": "daily", "dates": ["2026-09-08", "2026-09-09"]},
        "rotting": {"cadence": "daily", "dates": ["2026-06-01"]},  # ~100d behind
    }
    _, dead = evaluate(one_dead)
    if [d[0] for d in dead] != ["rotting"]:
        fails.append("a ~100d-stale daily feed beside a live one should fire, got %r" % (dead,))

    late_ok = {
        "live": {"cadence": "daily", "dates": ["2026-09-09"]},
        "weekly_late": {"cadence": "weekly", "dates": ["2026-08-20"]},  # 20d — late but not dead (<60)
    }
    _, dead = evaluate(late_ok)
    if dead:
        fails.append("a 20d-late weekly feed (inside its 60d bound) should stay quiet, got %r" % (dead,))
    return fails


def main():
    st = _selftest()
    if st:
        print("feed_freshness: SELF-TEST FAILED (bound/logic is unsound, not a data problem):")
        for f in st:
            print("   -", f)
        return 1

    if not os.path.exists(FEED):
        print("feed_freshness: SKIP — platform/data/feed_history.json absent "
              "(run: python3 pipeline/build_feed_history.py)")
        return 3

    with open(FEED, encoding="utf-8") as fh:
        doc = json.load(fh)
    series = doc.get("series", {})
    if not isinstance(series, dict) or not series:
        print("feed_freshness: SKIP — feed_history.json carries no 'series' block")
        return 3

    lead, dead = evaluate(series)
    if dead:
        print("feed_freshness: a feed has AGED IN SILENCE — its puller looks dead while its siblings "
              "kept updating (newest observation across all series: %s):" % lead.isoformat())
        for name, last, lag, bound in dead:
            print("   %-26s last=%s  %dd behind the leading edge (dead-bound %dd for its cadence)"
                  % (name, last, lag, bound))
        print("\n   Re-run that feed's puller (see .github/workflows/data-*.yml) or, if the source "
              "genuinely retired, document it in the layer's provenance. Byte-exact --check does NOT "
              "catch this — a dead puller's accumulator stays self-consistent.")
        return 1

    print("feed_freshness: OK — all %d feed-history series current (max lag behind the %s leading "
          "edge is within cadence bounds; self-test: 3 cases pass)." % (len(series), lead.isoformat()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
