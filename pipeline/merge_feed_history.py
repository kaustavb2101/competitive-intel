#!/usr/bin/env python3
"""merge_feed_history.py — union-merge the daily-feed accumulator during a conflicted git merge.

THE PROBLEM
-----------
source-data/feed_history.json is an ACCUMULATOR. ThaiWater gauges and the Bangchak pump price
publish only "now" — there is no archive to re-pull — so the only copy of yesterday's reading is the
one this file already holds. Every daily pull appends a row, which means every daily-pull branch
collides with every other one, and the collision is on parallel `dates`/`values` arrays that git
merges by line. That is why resolve_derived_conflicts.sh has always refused this file outright:
taking either side WHOLE silently deletes a day of telemetry that cannot be recovered.

Refusing was right, but it is not the smallest correct answer. The two sides do not disagree — each
holds days the other never saw. A union keyed on the observation date loses nothing, and is exactly
what append_history.py would have produced had both pulls run in sequence on one machine.

WHAT IT REFUSES
---------------
Per (series, date), a real 3-way merge. Both sides agreeing is a no-op; one side adding or
correcting a reading is taken; BOTH sides recording a DIFFERENT value for the same series on the
same date is contested measurement, and it exits 3 for a human rather than picking a number. That
last case is not hypothetical — it is what raising the pull cadence above once a day would create.

Dates are the source's own observation stamps (append_history.py prefers `observed_to` over
`pulled`, since the nightly job runs 22:40 UTC = next morning in Bangkok). This script never invents
or re-dates a point; it only takes the union of points that already exist.

    python3 pipeline/merge_feed_history.py --base B --ours O --theirs T --out FILE
    python3 pipeline/merge_feed_history.py --selftest

Exit 0 = wrote the union. 3 = contested; the caller must abort. 1 = usage or unreadable input.
"""
import argparse
import json
import os
import sys

RC_OK, RC_ERR, RC_CONTESTED = 0, 1, 3
DESCRIPTIVE = ("label", "unit", "cadence", "source", "path")


def _pairs(series):
    """A series' points as {date: value}. Tolerates a missing/short values array."""
    dates = series.get("dates") or []
    values = series.get("values") or []
    return {d: v for d, v in zip(dates, values)}


def _merge3(base, ours, theirs, what):
    """Standard 3-way on one scalar. Returns (value, None) or (None, reason)."""
    if ours == theirs:
        return ours, None
    if ours == base:
        return theirs, None
    if theirs == base:
        return ours, None
    return None, what


def union(base, ours, theirs):
    """-> (merged_doc, None) or (None, reason). `theirs` is the base branch (master)."""
    b_ser = (base or {}).get("series") or {}
    o_ser = (ours or {}).get("series") or {}
    t_ser = (theirs or {}).get("series") or {}

    out_series = {}
    for key in sorted(set(o_ser) | set(t_ser)):
        b, o, t = b_ser.get(key, {}), o_ser.get(key), t_ser.get(key)
        if o is None:
            out_series[key] = t
            continue
        if t is None:
            out_series[key] = o
            continue

        pb, po, pt = _pairs(b), _pairs(o), _pairs(t)
        merged = {}
        for date in set(po) | set(pt):
            v, err = _merge3(pb.get(date), po.get(date), pt.get(date),
                             "series %r has a different value on %s (%r vs %r) on the two sides"
                             % (key, date, po.get(date), pt.get(date)))
            if err:
                return None, err
            if v is not None:            # None = a deletion both sides accept (max_points trim)
                merged[date] = v

        row = dict(t)                    # start from master's descriptive fields
        for field in DESCRIPTIVE:
            v, err = _merge3(b.get(field), o.get(field), t.get(field),
                             "series %r has conflicting %s" % (key, field))
            if err:
                return None, err
            if v is not None:
                row[field] = v
            elif field in row:
                del row[field]

        dates = sorted(merged)
        row["dates"] = dates
        row["values"] = [merged[d] for d in dates]
        row["first_seen"] = dates[0] if dates else None
        row["n"] = len(dates)
        out_series[key] = row

    # meta: take master's, then restate the two counts it derives from the series it now holds.
    meta = dict((theirs or {}).get("meta") or (ours or {}).get("meta") or {})
    meta["n_series"] = len(out_series)
    meta["n_points"] = sum(len(s.get("dates") or []) for s in out_series.values())

    doc = dict(theirs or ours or {})
    doc["meta"] = meta
    doc["series"] = out_series
    return doc, None


# --------------------------------------------------------------------------------------- selftest
def _selftest():
    passed = failed = 0

    def check(name, got, want):
        nonlocal passed, failed
        if got == want:
            passed += 1
            print("  [PASS] %s" % name)
        else:
            failed += 1
            print("  [FAIL] %s\n         got:  %r\n         want: %r" % (name, got, want))

    def doc(points, **metakw):
        m = {"n_points": sum(len(v) for v in points.values()), "n_series": len(points)}
        m.update(metakw)
        return {"meta": m, "series": {
            k: {"label": "L", "unit": "u", "cadence": "daily", "source": "s", "path": "p",
                "dates": sorted(v), "values": [v[d] for d in sorted(v)],
                "first_seen": min(v) if v else None, "n": len(v)}
            for k, v in points.items()}}

    base = doc({"flood": {"2026-08-04": 132.0}})
    mine = doc({"flood": {"2026-08-04": 132.0, "2026-08-06": 140.0}})
    master = doc({"flood": {"2026-08-04": 132.0, "2026-08-05": 136.0}})

    # 1. the real case: each side holds a day the other never saw. Nothing may be dropped.
    out, err = union(base, mine, master)
    check("no error on disjoint days", err, None)
    check("kept every day from both sides", out["series"]["flood"]["dates"],
          ["2026-08-04", "2026-08-05", "2026-08-06"])
    check("values stay aligned to their dates", out["series"]["flood"]["values"],
          [132.0, 136.0, 140.0])
    check("restated n", out["series"]["flood"]["n"], 3)
    check("restated meta.n_points", out["meta"]["n_points"], 3)

    # 2. one side correcting a reading the other left alone is taken, not refused
    corrected = doc({"flood": {"2026-08-04": 999.0}})
    out2, err = union(base, corrected, doc({"flood": {"2026-08-04": 132.0}}))
    check("takes a one-sided correction", (err, out2["series"]["flood"]["values"]), (None, [999.0]))

    # 3. both sides recording a DIFFERENT number for the same day is contested measurement
    _, err = union(base, doc({"flood": {"2026-08-04": 1.0}}), doc({"flood": {"2026-08-04": 2.0}}))
    check("refuses two different readings for one date", err is not None, True)

    # 4. a series only one side has is carried through whole
    out4, err = union(base, doc({"flood": {"2026-08-04": 132.0}, "rain": {"2026-08-06": 7.0}}),
                      master)
    check("carries a series the other side lacks", (err, sorted(out4["series"])), (None, ["flood", "rain"]))
    check("restated meta.n_series", out4["meta"]["n_series"], 2)

    # 5. an empty base (the file was created on both sides) still unions
    out5, err = union({}, mine, master)
    check("handles an empty base", (err, out5["series"]["flood"]["n"]), (None, 3))

    # 6. a day dropped by BOTH sides (max_points trim) stays dropped, not resurrected
    out6, err = union(doc({"flood": {"2026-08-01": 1.0, "2026-08-04": 132.0}}),
                      doc({"flood": {"2026-08-04": 132.0}}),
                      doc({"flood": {"2026-08-04": 132.0}}))
    check("honours a trim both sides made", (err, out6["series"]["flood"]["dates"]),
          (None, ["2026-08-04"]))

    print("  %d passed, %d failed" % (passed, failed))
    return RC_OK if failed == 0 else RC_ERR


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base")
    ap.add_argument("--ours")
    ap.add_argument("--theirs")
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()
    if not all([a.base, a.ours, a.theirs, a.out]):
        ap.error("--base, --ours, --theirs and --out are all required")

    docs = []
    for p in (a.base, a.ours, a.theirs):
        try:
            # A stage can be legitimately absent (added-on-one-side); treat that as empty.
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                docs.append({})
                continue
            with open(p, "r", encoding="utf-8") as fh:
                docs.append(json.load(fh))
        except (OSError, ValueError) as e:
            print("cannot read merge stage %s: %s" % (p, e), file=sys.stderr)
            return RC_ERR

    merged, reason = union(*docs)
    if merged is None:
        print("contested accumulator — %s" % reason, file=sys.stderr)
        return RC_CONTESTED

    # Byte-for-byte the shape append_history.py writes, so the next append is a clean diff and
    # nothing downstream sees a spurious reformat. newline="" keeps LF on Windows.
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(merged, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return RC_OK


if __name__ == "__main__":
    sys.exit(main())
