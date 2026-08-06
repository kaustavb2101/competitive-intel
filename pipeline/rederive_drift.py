#!/usr/bin/env python3
"""
rederive_drift.py — re-derive whatever an upstream pull left stale, with no hand-kept list
==========================================================================================

THE PROBLEM THIS EXISTS FOR
---------------------------
A data-pull workflow refreshes ONE file (nabc_prices.json, thaiwater_rain.json, …) and the layers
computed downstream of it go stale in the same commit. The determinism gate then goes red on merge
and somebody re-derives the fan-out by hand. Every such workflow tried to fix this by carrying its
own hand-written list of downstream builders — and every one of those lists went stale, repeatedly:
the NABC job's rebuild step grew three separate "we also forgot X" paragraphs and STILL missed eight
layers on 2026-08-04 (crop_mix, farm_book, occupation_risk, farm_income_impact, branch_risk,
assist_price_radar, branch_peers, province_risk).

A hand-kept list is the wrong shape. It is a fourth copy of the dependency graph — after the scripts
themselves, the gate, and each workflow's `git add` line — and nothing keeps the copies honest.

THE APPROACH: FIXED-POINT ITERATION OVER THE GATE'S OWN SET
-----------------------------------------------------------
The set of layers that can turn the gate red IS, by definition, the set the gate `--check`s. So:

    1. discover every `--check`ed script by PARSING tests/run.sh (the single source of truth),
    2. run them all; whatever reports drift, run for real,
    3. repeat until nothing reports drift.

That needs no dependency graph and no ordering — iteration converges regardless, because a builder
whose input is still stale simply drifts again next pass and gets rebuilt again. It cannot go stale
as a list, because it is not a list: add a builder to the gate and this covers it automatically.
Its completeness is exactly the gate's completeness, which is the property we actually want.

Cost is one extra `--check` sweep per pass. Real fan-outs converge in 2-3 passes.

WHAT IT WILL NOT RUN BY ITSELF (see DENY below)
-----------------------------------------------
`pull_*.py` reaches the network or re-parses an owner-side raw cache, and `timeseries.py` WRITES A
NEW SNAPSHOT rather than regenerating an existing file. Auto-running either inside an unattended
cron would take an action nobody asked for, so drift in one is REPORTED (and exits non-zero) rather
than silently "fixed". Everything else is deterministic and network-free by construction.

`build_provenance.py` censuses the bytes of every other layer, so it is held out of the loop and run
ONCE at the end — the house rule everywhere else in this repo.

    python3 rederive_drift.py                   # re-derive the fan-out, then provenance
    python3 rederive_drift.py --dry-run         # report drift, change nothing
    python3 rederive_drift.py --report-md p.md  # also write a markdown summary for a PR body
    python3 rederive_drift.py --selftest        # prove the tests/run.sh parse still works

Exit 0 = converged (clean, or rebuilt to clean). Exit 1 = drift this cannot resolve by itself.
"""
import os
import re
import sys
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GATE = os.path.join(ROOT, "tests", "run.sh")

# The gate is the source of truth for "what can go red". Two syntaxes appear in it: explicit
# `python3 <name>.py --check` invocations, and a `name|source` table fed to a while-read loop.
RE_EXPLICIT = re.compile(r"python3\s+([A-Za-z0-9_]+)\.py\s+--check")
RE_HEREDOC = re.compile(r"<<'INGESTS'\n(.*?)\n\s*INGESTS", re.S)

# A parse that silently finds nothing would make this script a no-op — the exact failure mode it
# exists to remove. Refuse to run below a floor well under today's count (115) but far above zero.
MIN_BUILDERS = 80

# Held out of the loop and run last: it records every other layer's byte size.
PROVENANCE = "build_provenance"

# Never auto-run. Drift here is reported and fails the run instead.
DENY = {
    # writes a NEW per-vintage snapshot rather than regenerating a committed file
    "timeseries": "captures a new snapshot — a side effect, not a re-derivation",
}
DENY_PREFIX = ("pull_",)          # network, or a re-parse of an owner-side raw cache

MAX_PASSES = 6                     # a real fan-out converges in 2-3; more means oscillation

RC_CLEAN, RC_ABSENT = 0, 3         # the gate's own convention: 3 = an input is absent, not drift


def _run(script, check):
    """Run one pipeline script from pipeline/, returning (rc, combined output)."""
    argv = [sys.executable, f"{script}.py"] + (["--check"] if check else [])
    p = subprocess.run(argv, cwd=HERE, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def discover():
    """Every script the gate --checks, in gate order, deduped. Raises if the parse looks broken."""
    try:
        with open(GATE, encoding="utf-8") as fh:
            src = fh.read()
    except OSError as e:
        sys.exit(f"FATAL: cannot read the gate at {GATE} ({e}) — refusing to run a no-op.")

    names, seen = [], set()
    for m in RE_EXPLICIT.finditer(src):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            names.append(m.group(1))
    for block in RE_HEREDOC.finditer(src):
        for line in block.group(1).splitlines():
            name = line.split("|", 1)[0].strip()
            if name and not name.startswith("#") and name not in seen:
                seen.add(name)
                names.append(name)

    if len(names) < MIN_BUILDERS:
        sys.exit(f"FATAL: parsed only {len(names)} --check'ed scripts from tests/run.sh (floor is "
                 f"{MIN_BUILDERS}). The gate's syntax changed and this parser no longer sees it — "
                 f"fix RE_EXPLICIT/RE_HEREDOC rather than shipping a silent no-op.")
    return [n for n in names if n != PROVENANCE]


def blocked(name):
    """Why this script must not be auto-run, or None if it may be."""
    if name in DENY:
        return DENY[name]
    if name.startswith(DENY_PREFIX):
        return "a pull — reaches the network or an owner-side raw cache"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dry-run", action="store_true", help="report drift, rebuild nothing")
    ap.add_argument("--report-md", metavar="PATH", help="write a markdown summary (for a PR body)")
    ap.add_argument("--selftest", action="store_true", help="prove the gate parse works, then exit")
    args = ap.parse_args()

    builders = discover()
    if args.selftest:
        print(f"OK — parsed {len(builders)} gated scripts from tests/run.sh (+ {PROVENANCE}, "
              f"run last). Deny-listed: {sorted(DENY)} and {DENY_PREFIX}*")
        return 0

    rebuilt, unresolved, absent = [], [], []
    for p in range(1, MAX_PASSES + 1):
        drifted = []
        for name in builders:
            rc, _ = _run(name, check=True)
            if rc == RC_CLEAN:
                continue
            if rc == RC_ABSENT:
                if p == 1:
                    absent.append(name)          # an optional input is missing — honest, not drift
                continue
            drifted.append(name)

        if not drifted:
            print(f"pass {p}: no drift — converged.")
            break

        # Anything we are not allowed to touch stops being retried; it is reported instead.
        stuck = [(n, blocked(n)) for n in drifted if blocked(n)]
        for name, why in stuck:
            if name not in [u[0] for u in unresolved]:
                unresolved.append((name, why))
        runnable = [n for n in drifted if not blocked(n)]

        print(f"pass {p}: {len(drifted)} drifted -> rebuilding {len(runnable)} "
              f"({', '.join(runnable) if runnable else 'none'})")
        if not runnable:
            break

        for name in runnable:
            rc, out = _run(name, check=False)
            if rc != 0:
                print(f"  !! {name}.py failed (rc {rc}):\n{out.strip()[:2000]}")
                if name not in [u[0] for u in unresolved]:
                    unresolved.append((name, f"the builder itself failed (rc {rc})"))
            elif name not in rebuilt:
                rebuilt.append(name)
        # anything that just failed to run is not worth retrying next pass
        builders = [b for b in builders if b not in [u[0] for u in unresolved]]
    else:
        unresolved.append(("(convergence)", f"still drifting after {MAX_PASSES} passes"))

    # Provenance censuses every other layer's bytes, so it goes last and only if something moved.
    if rebuilt and not args.dry_run:
        rc, out = _run(PROVENANCE, check=False)
        if rc != 0:
            print(f"  !! {PROVENANCE}.py failed (rc {rc}):\n{out.strip()[:2000]}")
            unresolved.append((PROVENANCE, f"failed to regenerate (rc {rc})"))
        else:
            rebuilt.append(PROVENANCE)

    print(f"\nrebuilt {len(rebuilt)}: {', '.join(rebuilt) if rebuilt else '(nothing — already clean)'}")
    if absent:
        print(f"skipped {len(absent)} (an input is absent, not drift): {', '.join(absent)}")
    for name, why in unresolved:
        print(f"UNRESOLVED {name}: {why}")

    if args.report_md:
        lines = []
        if rebuilt:
            lines.append(f"**Re-derived downstream ({len(rebuilt)}):** "
                         + ", ".join(f"`{n}`" for n in rebuilt))
            lines.append("")
            lines.append("Computed by `pipeline/rederive_drift.py`, which iterates the determinism "
                         "gate's own `--check` set to a fixed point — so it covers whatever the gate "
                         "covers, with no hand-kept list to go stale.")
        else:
            lines.append("**Re-derived downstream:** nothing — no gated layer drifted.")
        if unresolved:
            lines.append("")
            lines.append("**Needs a human:**")
            lines += [f"- `{n}` — {w}" for n, w in unresolved]
        with open(args.report_md, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    return 1 if unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
