#!/usr/bin/env python3
"""Dangling-reference gate: every data layer the FRONTEND fetches actually exists on disk.

This is the reverse of orphan_layers.py, and it closes the other half of the
"data-reference integrity" hole:

  - orphan_layers.py asks  "is every committed platform/data/*.json CONSUMED?"  (file -> ref)
  - THIS check asks        "does every data/*.json the app FETCHES still EXIST?" (ref -> file)

The failure it catches is a silent production 404. A builder is renamed or retired, or a layer is
`git rm`'d (e.g. moved to R2), but a `fetch('data/X.json')` / `tmliFetch('X')` literal is left behind
in the frontend. The determinism gate stays green (it only reproduces the files that DO exist),
validate_data.py stays green (it only validates files that DO exist), and orphan_layers.py stays green
(it only looks at committed files) — so nothing in the repo notices. The break shows up only when a
real browser hits the live Vercel deploy and the fetch returns 404, and until now the only thing that
caught it was a human re-deriving "0 broken references" by hand in every SERVICE_AUDIT.md pass. This
turns that hand-audited invariant into a deterministic, offline gate check.

WHAT COUNTS AS A REFERENCE
--------------------------
Three literal forms the frontend uses to load a top-level layer `data/X.json`:
  1. a path literal   `'data/X.json'` / "data/X.json" / `data/X.json`   (any wrapper: fetch/opt/gopt)
  2. a direct helper  `tmliFetch('X')` — resolves to fetch('data/'+ 'X' +'.json') (see app.js)
  3. the array idiom  `['a','b',...].map(n => tmliFetch(n))` — each quoted name in the array literal
Only LITERAL names are read. Dynamically-built URLs (the R2/slug catchment scenes fetch
`P + '_catchment.json'` where P is a variable) never appear as a literal here, so they are not — and
must not be — flagged: they are covered by the province index / nav and probed live nightly by
check_site_health.py::run_r2_catchment_checks. A name containing a template/interpolation marker can
never match the literal character class, so it is excluded structurally, not by guesswork.

The check errs toward silence: it flags a name ONLY when it is an unambiguous static literal AND the
file is absent. An unrecognized fetch idiom is a false NEGATIVE (a missed dangling ref), never a false
RED gate — exactly the posture orphan_layers.py takes.

ALLOW is for a literal that is fetched but intentionally NOT committed (served from R2 / an operator
CDN with a documented local-first fallback). Empty today — every literal the frontend fetches resolves
to a committed file. Adding a row is a deliberate, reviewed act, with a reason.

Offline, stdlib only. Exit 0 = pass, 1 = fail.
"""
import glob
import os
import re
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(REPO, "platform", "data")

# A layer name: a top-level base like "peer_province" or a subdir leaf like "provinces/index".
NAME = r"[A-Za-z0-9_][A-Za-z0-9_\-/]*"

# Fetched-but-intentionally-uncommitted literals (served from R2 / a CDN with a local-first fallback).
# Each MUST carry a reason. Empty today — do not add a row to silence a genuine break; restore the file
# or fix the reference instead.
ALLOW = {
    # "some_layer": "fetched by the app but served only from R2, with a documented local-first fallback",
}


def collect_refs(text):
    """All literal layer names the given frontend source fetches (the three forms above)."""
    names = set()
    # form 1: any '…data/X.json…' string literal (fetch/opt/gopt/Promise.all — wrapper-agnostic)
    for m in re.finditer(r"""['"`]data/(%s)\.json['"`]""" % NAME, text):
        names.add(m.group(1))
    # form 2: direct tmliFetch('X')
    for m in re.finditer(r"""tmliFetch\(\s*['"](%s)['"]""" % NAME, text):
        names.add(m.group(1))
    # form 3: [ 'a','b',… ].map( n => tmliFetch( n ) )
    for m in re.finditer(r"""\[([^\]]*?)\]\s*\.map\(\s*\w+\s*=>\s*tmliFetch\(\s*\w+\s*\)""", text):
        for s in re.findall(r"""['"](%s)['"]""" % NAME, m.group(1)):
            names.add(s)
    return names


def main():
    refs = {}  # name -> sorted list of frontend files that reference it
    sources = sorted(glob.glob(os.path.join(REPO, "platform", "*.html")))
    app_js = os.path.join(REPO, "platform", "app.js")
    if os.path.exists(app_js):
        sources.append(app_js)
    for p in sources:
        text = open(p, encoding="utf-8", errors="ignore").read()
        for n in collect_refs(text):
            refs.setdefault(n, set()).add(os.path.basename(p))

    dangling, allowed = [], []
    for n in sorted(refs):
        if n in ALLOW:
            allowed.append(n)
            continue
        if not os.path.exists(os.path.join(DATA, n + ".json")):
            dangling.append((n, sorted(refs[n])))

    if dangling:
        for n, where in dangling:
            print("  FAIL data/%s.json — fetched by %s but no such file on disk. Restore the layer, "
                  "fix the reference, or (if it is served from R2 with a local-first fallback) add "
                  "'%s' to ALLOW in tests/dangling_refs.py with a reason."
                  % (n, ", ".join(where), n))
        print("dangling_refs: %d dangling reference(s) of %d literal refs checked (%d allowed)"
              % (len(dangling), len(refs), len(allowed)))
        return 1
    print("dangling_refs: %d literal data references checked, all resolve to a committed file "
          "(%d allowed)" % (len(refs), len(allowed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
