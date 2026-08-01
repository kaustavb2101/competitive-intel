#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_feed_history.py — project the accumulated daily-feed series into the app.

  in : source-data/feed_history.json    the accumulator written by append_history.py
  out: platform/data/feed_history.json  publishable series + direction, for the live board

This is the deterministic, --check-gated half of the append-history mechanism. append_history.py
reaches out to the feed files and to git and is therefore a pull-side action; everything downstream
of its output is reproducible byte-for-byte and lives inside the gate.

WHAT GETS PUBLISHED. A series needs at least MIN_PUBLISH points to appear at all — one observation
is a reading, not a series, and drawing an axis through it would imply a trend that was never
measured. Below CHART_MIN it is published but marked `chartable: false`, so the board can show the
numbers and the direction without pretending a three-point line is a trend.

DIRECTION IS OVER THE WHOLE RECORD, and `change_recent` covers the last step, because those answer
different questions: "is diesel dearer than when we started watching" vs "did it move last night".
Both are stated rather than one being silently chosen. Percentage change is suppressed when the
base is zero — a flood-station count going 0 → 4 is a real move but "+∞%" is not a number.

  python3 build_feed_history.py
  python3 build_feed_history.py --check
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "source-data", "feed_history.json")
OUT = os.path.join(ROOT, "platform", "data", "feed_history.json")

MIN_PUBLISH = 2     # below this it is an observation, not a series
CHART_MIN = 4       # below this, publish the numbers but do not draw a line
FLAT_EPS = 1e-9     # exact-equality guard for "no change"


def direction(delta):
    if delta > FLAT_EPS:
        return "up"
    if delta < -FLAT_EPS:
        return "down"
    return "flat"


def build():
    src = json.load(open(IN, encoding="utf-8"))
    out, order = {}, []
    for key in sorted(src.get("series", {})):
        s = src["series"][key]
        dates, values = s.get("dates") or [], s.get("values") or []
        if len(dates) != len(values) or len(dates) < MIN_PUBLISH:
            continue
        first, last = values[0], values[-1]
        change = round(last - first, 4)
        step = round(last - values[-2], 4)
        rec = {
            "label": s.get("label"), "unit": s.get("unit"), "cadence": s.get("cadence"),
            "source": s.get("source"),
            "dates": dates, "values": values, "n": len(dates),
            "first_seen": dates[0], "last_seen": dates[-1],
            "latest": last,
            "change": change, "direction": direction(change),
            "change_recent": step, "direction_recent": direction(step),
            "chartable": len(dates) >= CHART_MIN,
        }
        # A percentage of zero is not a percentage. Say the absolute move instead of inventing one.
        rec["change_pct"] = round((last - first) / abs(first) * 100, 1) if abs(first) > FLAT_EPS else None
        out[key] = rec
        order.append(key)

    charted = [k for k in order if out[k]["chartable"]]
    return {
        "meta": {
            "title": "Accumulated history for feeds whose source only publishes 'now'",
            "generated_by": "pipeline/build_feed_history.py",
            "source": "source-data/feed_history.json (pipeline/append_history.py)",
            "label": "MEASURED — every point is a value the source itself published, dated by the "
                     "source's own stamp, never by the clock on the machine that pulled it.",
            "note": "Nothing is interpolated. A missed pull leaves a gap, so a line here joins the "
                    "observations that exist and invents none. Each series states when its record "
                    "begins: a short series is a short record, not a short trend.",
            "backfill": src.get("meta", {}).get("backfill"),
            "min_publish": MIN_PUBLISH,
            "chart_min": CHART_MIN,
            "n_series": len(order),
            "n_chartable": len(charted),
            "n_points": sum(out[k]["n"] for k in order),
        },
        "order": order,
        "series": out,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN):
        if args.check:
            print("build_feed_history.py --check: SKIP (source-data/feed_history.json absent)")
            sys.exit(3)
        sys.exit("build_feed_history.py: source-data/feed_history.json missing — "
                 "run: python3 pipeline/append_history.py --from-git")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_feed_history.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_feed_history.py --check: drifted — re-run the builder.")
        print("build_feed_history.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    m = json.loads(payload)["meta"]
    print("wrote %s — %d series (%d chartable), %d points"
          % (OUT, m["n_series"], m["n_chartable"], m["n_points"]))


if __name__ == "__main__":
    main()
