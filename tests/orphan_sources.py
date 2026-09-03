#!/usr/bin/env python3
"""Orphan-SOURCE gate: every committed source-data/*.json input is actually consumed.

This is the sibling one layer UPSTREAM of `orphan_layers.py`. That check proves every committed
`platform/data/*.json` LEAF is read by a page or a builder. But the branch_density failure it was
written for can happen one step earlier too: a committed `source-data/*.json` INPUT that no pipeline
script, committee member, or guard ever reads — pulled or vendored once, then aging gate-green in
silence because the determinism gate only asks "does this reproduce?", never "does anything USE it?".
`orphan_layers.py` cannot see it, because source inputs are not `platform/data` leaves; until now the
only protection was a handful of bespoke, per-file guards (`vehicle_base_staleness_guard.py`,
`amphoe_crops_zone_guard.py`). This closes the structural gap with one general check in the same idiom.

SCOPE
-----
Top-level `source-data/*.json` only, and only files GIT-TRACKS (a CI runner checks out a fresh tree, so
gitignored inputs — the synthetic loan tape, the legacy `.place_ratings_cache.json`, raw pull caches —
never exist there and are not this check's concern; restricting to tracked files makes the verdict
identical in CI and on a dev laptop that happens to have those files present). Subdirectory families
(`source-data/tmli/`, `staging/`, `snapshots/`, `investor_docs/`, `datagoth/`) are intermediates or
vendored sets guarded elsewhere and are deliberately out of scope, exactly as `orphan_layers.py` scopes
itself to the top-level `platform/data` glob.

WHAT COUNTS AS CONSUMED
-----------------------
A source input is consumed if EITHER:
  - a script OTHER than its producer references its base-name token — any `pipeline/*.py`,
    `committee/*.py`, or `tests/*.py` (a bespoke guard counts as a real consumer). This is a broad
    whole-token match, deliberately fail-open like `orphan_layers.py`'s pipeline side: a script that is
    not the writer and names the file is almost certainly reading it, and erring toward silence means we
    can only miss a real orphan, never cry wolf over a live input; OR
  - its own producer READS IT BACK — a warm cache / accumulate-across-runs store (the file is written
    AND loaded within one script, e.g. `pull_place_ratings.py`'s rating cache, or a
    `--harvest`-then-build script like `build_debt_source.py`). Detected by a real read idiom on the
    file's path literal or the variable it is assigned to (`_load_json(VAR)` / `json.load(...)` /
    `open(VAR, ...)` in any mode that is not write / `.read_text()`), NOT a bare mention. So a producer
    that only ever WRITES the file — computing it fresh each run and reading nothing back, the exact
    branch_density shape — is correctly flagged, while a legitimate self-consuming cache is not.

Pages are NOT scanned: the app fetches from `platform/data/`, never from `source-data/`, so a
source-data reference in HTML/JS would be prose, not a load — including page text would only weaken the
test toward the comment-mention hole `orphan_layers.py` documents.

Producer detection (and thus the "reads it back" refinement) fails OPEN, on purpose: if a writer idiom
is ever missed, the file's own reference reads as consumption and it looks used — a missed orphan (a
false negative), never a false RED gate on a live input.

ALLOW
-----
An explicit, reasoned allowlist for a source input intentionally committed with no consumer (a
dormant-by-design or reversibility-only vendored file). Empty today — the current tree has zero orphan
sources. Add a row only as a deliberate, reviewed act (like `orphan_layers.py`'s ALLOW / LEGACY_ROUTES);
the default fix for a real orphan is to wire it into a builder or retire it, never to silence it here.

`--selftest` runs the classifier over three synthetic scripts (pure orphan / warm cache / harvest+build)
and asserts the verdicts, so the detector is proven to still FIRE, not just to pass on today's tree.

Offline, stdlib only. Exit 0 = pass, 1 = fail.
"""
import glob
import os
import re
import subprocess
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(REPO, "source-data")

# Intentional exceptions: a committed source input with no consumer, retained on purpose. Each MUST
# carry a reason. Do not add a row to silence a genuine orphan; wire it into a builder or retire it.
ALLOW = {}


def _is_writer(text, fname):
    """True if `text` (a python script) WRITES source-data/<fname> — ties the literal filename to a
    write sink, so a script that only READS the file is not mistaken for its producer. Mirrors
    orphan_layers._is_writer, but the literal may be one os.path.join arg among several."""
    lit = re.escape(fname)
    if re.search(r"open\([^)\n]*['\"][^'\"]*" + lit + r"['\"][^)\n]*,\s*['\"]w", text):
        return True
    for m in re.finditer(r"(\w+)\s*=\s*[^\n]*['\"][^'\"]*" + lit + r"['\"]", text):
        v = re.escape(m.group(1))
        if re.search(r"open\(\s*" + v + r"\b[^)\n]*,\s*['\"]w", text):
            return True
        if re.search(v + r"\b[^)\n]*\.write_text\(", text):
            return True
        if re.search(r"json\.dump\([^)\n]*,\s*" + v + r"\b", text):
            return True
    return False


def _reads_back(text, fname):
    """True if a producer of source-data/<fname> ALSO reads it as input (a warm cache / harvest store),
    via a real read idiom on the literal or its assigned path variable — NOT a bare mention/comment."""
    lit = re.escape(fname)
    # literal passed to a load/read helper, or open(literal) not in write mode
    if re.search(r"(?:load|read)\w*\([^)\n]*['\"][^'\"]*" + lit + r"['\"]", text):
        return True
    if re.search(r"open\(\s*['\"][^'\"]*" + lit + r"['\"]\s*[),]", text):
        return True
    for m in re.finditer(r"(\w+)\s*=\s*[^\n]*['\"][^'\"]*" + lit + r"['\"]", text):
        v = re.escape(m.group(1))
        if re.search(r"\b\w*(?:load|read)\w*\([^)\n]*\b" + v + r"\b", text):   # _load_json(VAR / json.load(VAR
            return True
        for om in re.finditer(r"open\(\s*" + v + r"\b([^)\n]*)\)", text):        # open(VAR ...) not write mode
            if not re.search(r",\s*['\"][wax]", om.group(1)):
                return True
        if re.search(v + r"\b[^)\n]*\.read_text\(", text):
            return True
    return False


def _tracked_sources():
    """Top-level source-data/*.json that git tracks. Falls back to a plain glob if git is unavailable
    (CI always has git; the fallback keeps the script runnable in a bare checkout)."""
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(SRC, "*.json")))
    try:
        out = subprocess.check_output(["git", "ls-files", "source-data/*.json"], cwd=REPO,
                                      stderr=subprocess.DEVNULL).decode()
        tracked = {line.strip() for line in out.splitlines() if line.strip()}
        return [n for n in names if ("source-data/" + n) in tracked]
    except Exception:
        return names


def _scripts():
    out = {}
    for d in ("pipeline", "committee", "tests"):
        for p in glob.glob(os.path.join(REPO, d, "**", "*.py"), recursive=True):
            out[os.path.relpath(p, REPO)] = open(p, encoding="utf-8", errors="ignore").read()
    return out


def _find_orphans(leaves, scripts):
    orphans, allowed = [], []
    for f in leaves:
        if f in ALLOW:
            allowed.append(f)
            continue
        base = f[:-5]  # strip .json
        tok = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(base) + r"(?![A-Za-z0-9_])")
        producers = {name for name, txt in scripts.items() if _is_writer(txt, f)}
        consumers = [name for name, txt in scripts.items()
                     if tok.search(txt) and name not in producers]
        self_reads = [name for name in producers if _reads_back(scripts[name], f)]
        if not (consumers or self_reads):
            orphans.append((f, sorted(producers)))
    return orphans, allowed


def _selftest():
    orphan = 'OUT = os.path.join(R, "x_orphan.json")\njson.dump(doc, open(OUT, "w"))'
    cache = 'C = os.path.join(R, "x_cache.json")\ncache = _load_json(C, {})\njson.dump(cache, open(C, "w"))'
    harvest = ('SRC = os.path.join(R, "x_src.json")\n'
               'with open(SRC, "w") as f: f.write(d)\n'
               'with open(SRC, encoding="utf-8") as g: data = g.read()')
    downstream_producer = 'OUT = os.path.join(R, "x_down.json")\njson.dump(doc, open(OUT, "w"))'
    downstream_consumer = 'raw = json.load(open(os.path.join(R, "x_down.json")))'
    cases = [
        # name, scripts-dict, expect_orphan
        ("pure-orphan", {"p.py": orphan}, {"x_orphan.json"}),
        ("warm-cache", {"pull.py": cache}, set()),
        ("harvest+build", {"b.py": harvest}, set()),
        ("downstream-consumed", {"prod.py": downstream_producer, "cons.py": downstream_consumer}, set()),
    ]
    ok = True
    for name, scr, expect in cases:
        leaves = sorted({f for txt in scr.values()
                         for f in re.findall(r"['\"](x_[a-z]+\.json)['\"]", txt)})
        orphans, _ = _find_orphans(leaves, scr)
        got = {f for f, _ in orphans}
        verdict = "OK" if got == expect else "FAIL"
        if got != expect:
            ok = False
        print("  selftest %-20s expect=%s got=%s [%s]" % (name, sorted(expect), sorted(got), verdict))
    if ok:
        print("orphan_sources: self-test OK (fires on the pure-orphan shape, quiet on cache/harvest/downstream).")
        return 0
    print("orphan_sources: SELF-TEST FAILED — the detector no longer classifies the reference shapes correctly.")
    return 1


def main():
    if "--selftest" in sys.argv:
        return _selftest()
    leaves = _tracked_sources()
    scripts = _scripts()
    orphans, allowed = _find_orphans(leaves, scripts)
    if orphans:
        for f, producers in orphans:
            who = ("written by %s but read back by nothing (incl. its own producer)"
                   % ", ".join(producers)) if producers \
                  else "committed but referenced by no pipeline/committee/tests script"
            print("  FAIL source-data/%s — %s. Wire it into a builder (read it as input), or retire "
                  "it, or add it to ALLOW in tests/orphan_sources.py with a reason." % (f, who))
        print("orphan_sources: %d orphan source(s) of %d checked (%d allowed)"
              % (len(orphans), len(leaves), len(allowed)))
        return 1
    print("orphan_sources: %d committed source input(s) checked, all consumed by a builder, a committee "
          "member, or a guard (%d allowed)" % (len(leaves), len(allowed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
