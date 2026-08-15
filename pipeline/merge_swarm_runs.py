#!/usr/bin/env python3
"""merge_swarm_runs.py — union-merge the swarm's run log during a conflicted git merge.

THE PROBLEM
-----------
source-data/swarm_runs.json is the swarm's own audit trail: one row per pull_swarm.py run, saying
which feeds were pulled concurrently and whether each succeeded / changed / failed / timed out.
pull_swarm.py APPENDS a row and keeps the last `max_runs` (60). Nothing has ever been evicted — the
file holds 6 rows — so every row in it is the only copy of that run's outcome.

That makes it exactly the same shape of collision as feed_history.json: two swarm branches each
append a run the other never saw, git tries to text-merge parallel array entries, and it conflicts.
Until now there was no merger for it at all, so resolve_derived_conflicts.sh classified it as a
REAL CONFLICT and stopped — which is how PR #414 came to need a human for a file where the two
sides did not disagree about anything. Taking either side whole DELETES run records permanently;
the runs are not re-playable.

THE KEY
-------
`started` (the run's own UTC start stamp) identifies a run. Two runs cannot start at the same
instant, so a union keyed on it is exactly what pull_swarm.py would have written had both runs
happened in sequence on one machine.

WHAT IT REFUSES
---------------
Per run, a real 3-way merge. Both sides holding an identical row is a no-op; a row only one side
has is taken; the same `started` carrying DIFFERENT content on the two sides means something
rewrote history, which is not an append and not something to guess about — exit 3 for a human.

    python3 pipeline/merge_swarm_runs.py --base B --ours O --theirs T --out FILE
    python3 pipeline/merge_swarm_runs.py --selftest

Exit 0 = wrote the union. 3 = contested; the caller must abort. 1 = usage or unreadable input.
"""
import argparse
import json
import os
import sys

RC_OK, RC_ERR, RC_CONTESTED = 0, 1, 3
KEY = "started"


def _by_key(doc):
    """Runs as {started: row}. A row with no stamp cannot be identified, so it is kept aside."""
    rows, anon = {}, []
    for row in (doc or {}).get("runs") or []:
        k = row.get(KEY) if isinstance(row, dict) else None
        if k is None:
            anon.append(row)
        else:
            rows[k] = row
    return rows, anon


def union(base, ours, theirs):
    """-> (merged_doc, reason_or_None). `theirs` is the base branch (master)."""
    b, _ = _by_key(base)
    o, o_anon = _by_key(ours)
    t, t_anon = _by_key(theirs)

    merged = {}
    for k in sorted(set(o) | set(t)):
        ro, rt, rb = o.get(k), t.get(k), b.get(k)
        if ro is None:
            merged[k] = rt
        elif rt is None:
            merged[k] = ro
        elif ro == rt:
            merged[k] = ro
        elif ro == rb:                    # only master changed it
            merged[k] = rt
        elif rt == rb:                    # only we changed it
            merged[k] = ro
        else:
            return None, ("run %s has different content on the two sides — that is a rewrite, "
                          "not an append" % k)

    # A row with no `started` cannot be deduplicated, so keep every distinct one rather than
    # dropping any: this file is the only record of the run it describes.
    anon = []
    for row in o_anon + t_anon:
        if row not in anon:
            anon.append(row)

    rows = [merged[k] for k in sorted(merged)] + anon

    meta = dict((theirs or {}).get("meta") or (ours or {}).get("meta") or {})
    cap = meta.get("max_runs")
    if isinstance(cap, int) and cap > 0 and len(rows) > cap:
        rows = rows[-cap:]                # same trim pull_swarm.py applies: keep the newest
    meta["n_runs"] = len(rows)

    doc = dict(theirs or ours or {})
    doc["meta"] = meta
    doc["runs"] = rows
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

    def run(stamp, ok=10, **kw):
        r = {"started": stamp, "finished": stamp, "n_ok": ok, "jobs": 6}
        r.update(kw)
        return r

    def doc(rows, max_runs=60):
        return {"meta": {"generated_by": "pipeline/pull_swarm.py", "max_runs": max_runs,
                         "n_runs": len(rows)}, "runs": list(rows)}

    a, b_, c = run("2026-08-09T02:57:25Z"), run("2026-08-11T10:28:47Z"), run("2026-08-14T10:36:23Z")

    # 1. THE REAL CASE — each side appended a run the other never saw. Nothing may be lost.
    out, err = union(doc([a]), doc([a, b_]), doc([a, c]))
    check("no error on disjoint runs", err, None)
    check("kept every run from both sides", [r["started"] for r in out["runs"]],
          [a["started"], b_["started"], c["started"]])
    check("restated meta.n_runs", out["meta"]["n_runs"], 3)

    # 2. ordering is by the run's own start stamp, not by which side supplied it
    out2, _ = union(doc([]), doc([c]), doc([a]))
    check("orders by start stamp", [r["started"] for r in out2["runs"]],
          [a["started"], c["started"]])

    # 3. a row only one side has is carried through
    out3, err = union(doc([a]), doc([a]), doc([a, c]))
    check("carries a run the other side lacks", (err, len(out3["runs"])), (None, 2))

    # 4. identical rows on both sides do not duplicate
    out4, _ = union(doc([]), doc([a]), doc([a]))
    check("identical rows collapse", len(out4["runs"]), 1)

    # 5. the same run with DIFFERENT content is a rewrite, not an append
    _, err = union(doc([a]), doc([run(a["started"], ok=1)]), doc([run(a["started"], ok=2)]))
    check("refuses a rewritten run record", err is not None, True)

    # 6. one-sided edit of an existing row is taken rather than refused
    out6, err = union(doc([a]), doc([run(a["started"], ok=99)]), doc([a]))
    check("takes a one-sided edit", (err, out6["runs"][0]["n_ok"]), (None, 99))

    # 7. the cap is honoured, and it drops the OLDEST — never the newest
    out7, _ = union(doc([]), doc([a, b_]), doc([c]), )
    check("no trim below the cap", len(out7["runs"]), 3)
    out8, _ = union(doc([], 2), doc([a, b_], 2), doc([c], 2))
    check("trims to max_runs", len(out8["runs"]), 2)
    check("trim keeps the NEWEST runs", [r["started"] for r in out8["runs"]],
          [b_["started"], c["started"]])

    # 8. an empty base (the file was created on both sides) still unions
    out9, err = union({}, doc([a]), doc([c]))
    check("handles an empty base", (err, len(out9["runs"])), (None, 2))

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
        print("contested run log — %s" % reason, file=sys.stderr)
        return RC_CONTESTED

    # Byte-for-byte the shape pull_swarm.py writes, so the next append is a clean diff and nothing
    # downstream sees a spurious reformat. newline="" keeps LF on Windows.
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(merged, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return RC_OK


if __name__ == "__main__":
    sys.exit(main())
