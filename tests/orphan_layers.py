#!/usr/bin/env python3
"""Orphan-layer gate: every committed platform/data/*.json is actually consumed.

The failure this catches had already happened, silently, and for months:
`build_branch_density.py` produced `platform/data/branch_density.json` and NOTHING read it —
no page fetched it, no other builder consumed it. It sat committed and gate-green from
2026-07-02, aging in silence, because the determinism gate only asks "does this file reproduce
byte-for-byte?", never "does anything USE this file?". A layer can be perfectly deterministic and
completely dead.

There is already an orphan-*route* check (`nav_consistency.py`: a route index.html renders that
the nav never links) and an orphan-*amphoe* check (`validate_data.py`: a district polygon with no
join). This is the missing sibling: an orphan-*data-layer* check. Together they close the
"built but never surfaced" hole from all three angles.

WHAT COUNTS AS CONSUMED
-----------------------
A top-level `platform/data/X.json` is consumed if EITHER:
  - a page reads it — via a real LOADER idiom in platform/app.js or any platform/*.html: the base
    name quoted (`tmliFetch('X')`, or `'X'` in a `Promise.all([...])` batch) or the fetch path
    `data/X.json`. A bare, unquoted MENTION does NOT count — a name that appears only inside a
    comment (`// X removed`, `<!-- X.json remains on disk -->`) is prose, not a fetch, and used to
    fool a naive whole-token grep into reporting a dead layer as "consumed" (the exact hole that
    hid opportunity_score / expansion_plan below — see ALLOW). Requiring the quoted/path form is a
    STRICTER test (every real page consumer uses one of these forms; comments do not), so it can
    only surface a real orphan, never cry wolf over a genuinely-loaded layer; OR
  - a pipeline script reads it as INPUT — the base name appears in a pipeline/*.py that is NOT the
    script which WRITES X.json. The producer is identified structurally (it ties the "X.json"
    literal to an `open(..,'w')` / `.write_text` / json.dump sink), so a layer referenced ONLY by
    its own producer — the exact branch_density shape — is flagged, while a hand-authored INPUT
    read by a single builder (e.g. provenance_sidecar.json, read by build_provenance.py) is
    correctly seen as consumed. (The pipeline side still matches a whole token, so a layer named
    only in a builder's docstring/comment still reads as consumed there — a narrower, rarer hole
    than the page-comment one; ALLOW is the sanctioned escape hatch when it bites.)

Producer detection failing OPEN is deliberate: if a writer idiom is ever missed, the producer's own
reference reads as consumption and the layer looks used — a false NEGATIVE (a missed orphan), never
a false RED gate on a real layer. The check errs toward silence, not toward crying wolf.

EXCLUSIONS
----------
- The network-pulled geometry FAMILIES (`*_catchment/_places/_roads/_water/_landuse.json`) are
  loaded by dynamically-constructed slug URLs (`rayong-catchment.html?city=<slug>`), never by a
  literal per-file reference, so a per-file consumption test cannot see them. Their coverage is
  guarded elsewhere (province index / nav). Excluded by suffix.
- `provinces/*.json` live in a subdir (not matched by the top-level glob) and are slug-loaded too.
- ALLOW: an explicit, reasoned allowlist for any layer intentionally committed without a consumer
  (a dormant-by-design output retained for reversibility). Carries the two strategy-pivot expansion
  leaderboards (opportunity_score / expansion_plan) — generated, `--check`-gated for reproducibility,
  but surfaced by no page since the network went consolidation-only (see CLAUDE.md, and each
  builder's DORMANT docstring). Adding an entry is a deliberate, reviewed act, exactly like
  LEGACY_ROUTES.

Offline, stdlib only. Exit 0 = pass, 1 = fail.
"""
import glob
import os
import re
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(REPO, "platform", "data")

# Geometry families loaded by dynamic slug URL, not by a literal per-file reference — see docstring.
FAMILY_SUFFIX = ("_catchment.json", "_places.json", "_roads.json", "_water.json", "_landuse.json")

# Intentional exceptions: a committed layer with no consumer, retained on purpose. Each MUST carry a
# reason. Do not add a row to silence a genuine orphan; wire the layer up instead.
ALLOW = {
    "opportunity_score.json": "DORMANT by design — the per-amphoe demand×gap growth leaderboard was "
        "dropped in the consolidation strategy pivot (no where-to-open recommendation). Still built + "
        "--check-gated for reproducibility/reversibility; surfaced by no page (all app refs are "
        "comments). See build_opportunity_score.py docstring + CLAUDE.md.",
    "expansion_plan.json": "DORMANT by design — the sequenced D'Hondt branch-placement plan, retained "
        "but unrendered since the network is consolidating not growing. Still built + --check-gated; "
        "no page consumes it. See build_expansion_plan.py docstring + CLAUDE.md.",
}


def _is_writer(text, fname):
    """True if `text` (a pipeline script) WRITES platform/data/<fname> — ties the literal filename
    to a write sink, so a script that merely READS the file is not mistaken for its producer."""
    lit = re.escape(fname)
    # direct literal inside an open(..,'w') call
    if re.search(r"open\([^)\n]*['\"]" + lit + r"['\"][^)\n]*,\s*['\"]w", text):
        return True
    # variable assigned an expression containing the "<fname>" literal, then used as a write sink
    for m in re.finditer(r"(\w+)\s*=\s*[^\n]*['\"]" + lit + r"['\"]", text):
        v = re.escape(m.group(1))
        if re.search(r"open\(\s*" + v + r"\b[^)\n]*,\s*['\"]w", text):
            return True
        if re.search(v + r"\b[^)\n]*\.write_text\(", text):
            return True
        if re.search(r"json\.dump\([^)\n]*,\s*" + v + r"\b", text):
            return True
    return False


def _page_consumes(app_text, base):
    """True if a page LOADS platform/data/<base>.json via a real fetch idiom — the base name
    quoted (tmliFetch('base') / 'base' in a Promise.all batch) or the fetch path data/base.json.
    A bare, unquoted mention (a comment or prose) is NOT a load and does not count. Every real
    page consumer uses one of these forms; comments do not — so this is strictly tighter than a
    whole-token grep and cannot mis-flag a genuinely-loaded layer. See module docstring."""
    b = re.escape(base)
    if re.search(r"""['"`]""" + b + r"""['"`]""", app_text):   # quoted bare token
        return True
    if re.search(r"data/" + b + r"\.json", app_text):          # fetch path form
        return True
    return False


def main():
    leaves = sorted(os.path.basename(p) for p in glob.glob(os.path.join(DATA, "*.json")))
    candidates = [f for f in leaves if not f.endswith(FAMILY_SUFFIX)]

    app_text = ""
    for p in sorted(glob.glob(os.path.join(REPO, "platform", "*.html"))):
        app_text += open(p, encoding="utf-8", errors="ignore").read()
    app_js = os.path.join(REPO, "platform", "app.js")
    if os.path.exists(app_js):
        app_text += open(app_js, encoding="utf-8", errors="ignore").read()

    pipe = {}
    for p in sorted(glob.glob(os.path.join(REPO, "pipeline", "*.py"))):
        pipe[os.path.basename(p)] = open(p, encoding="utf-8", errors="ignore").read()

    orphans, allowed = [], []
    for f in candidates:
        if f in ALLOW:
            allowed.append(f)
            continue
        base = f[:-5]  # strip .json
        tok = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(base) + r"(?![A-Za-z0-9_])")
        producers = {name for name, txt in pipe.items() if _is_writer(txt, f)}
        pipe_consumers = [name for name, txt in pipe.items()
                          if tok.search(txt) and name not in producers]
        app_consumed = _page_consumes(app_text, base)
        if not (app_consumed or pipe_consumers):
            orphans.append((f, sorted(producers)))

    if orphans:
        for f, producers in orphans:
            who = ("written by %s but read by nothing" % ", ".join(producers)) if producers \
                  else "committed but referenced by no page and no pipeline script"
            print("  FAIL %s — %s. Wire it into a page (tmliFetch) or a downstream builder, "
                  "or add it to ALLOW in tests/orphan_layers.py with a reason." % (f, who))
        print("orphan_layers: %d orphan layer(s) of %d checked (%d allowed)"
              % (len(orphans), len(candidates), len(allowed)))
        return 1
    print("orphan_layers: %d data layers checked, all consumed by a page or a builder "
          "(%d family-excluded, %d allowed)"
          % (len(candidates), len(leaves) - len(candidates), len(allowed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
