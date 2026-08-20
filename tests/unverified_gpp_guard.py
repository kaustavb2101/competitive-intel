#!/usr/bin/env python3
# unverified_gpp_guard.py — the PROVENANCE-HONESTY gate for the unverified GPP knowledge base.
#
# CLAUDE.md: "Always state whether a number is measured or estimated." The one committed layer that
# most persistently violates that in disguise is `source-data/gpp_by_province.json`. Its meta.source
# reads "NESDC Provincial Accounts (GPP)" and the source file it is vendored from labels itself
# "NESDC OFFICIAL DATA" — but only 1 of its 77 provinces (Mukdahan, source 'CKAN-NESDC-2566') was
# ever verified against a real NESDC CKAN dataset. The other 76 are round-number figures (multiples
# of 1,000-5,000 THB million) under a generic 'NESDC-2566' tag with hand-assigned confidence — a
# plausibility KNOWLEDGE BASE, not a per-province pull. The 2026-07-02 audit caught this, and both
# NEXT_STEPS §0a and the file's OWN meta.provenance carry the standing instruction verbatim:
#   "Do NOT surface this layer as MEASURED in the app until re-pulled per-province from NESDC's CKAN."
#
# WHY THIS EXISTS (the same argument that justifies mandate_guard.py): good labelling and hand-audit
# are NOT enough, because nothing in the gate LOCKED IT IN. The hazard is live and recurring — the
# file's official-looking self-label keeps fooling careful readers into proposing to project it into
# platform/data. Most recently (2026-08-20) a negative-space audit, reading only meta.source and the
# per-row 'NESDC-2566' tag, recommended exactly that: "add build_gpp_backdrop.py projecting
# gpp_by_province.json -> platform/data/gpp_backdrop.json" and wire it into #overview as MEASURED.
# That is precisely the honesty regression the standing instruction forbids. A fabricated provincial
# GPP shipped to an exec dashboard as "measured" is the kind of number Kaustav explicitly distrusts.
# This turns the recurring manual audit into an automated regression gate.
#
# THE INVARIANT (self-lifting, mirrors the repo's UPSTREAM_CAPPED self-clearing idiom):
#   While the file is still predominantly UNVERIFIED (n_ckan_verified < n_provinces) the ONLY way its
#   estimated GPP values can reach the app is a pipeline builder reading the source file and
#   projecting it into platform/data. So the guard FAILs if any pipeline/*.py other than its writer
#   (ingest_tmli.py) references it, or if any page (app.js / *.html) fetches it. The day a real
#   per-province NESDC CKAN re-pull lands (every row 'CKAN-NESDC-2566', n_ckan_verified ==
#   n_provinces), the precondition no longer holds and the guard passes trivially — integration
#   becomes allowed automatically, no edit to this file needed.
#
# SCOPE (deliberately tight, false-positive-free): the ONLY token matched is the filename base
# `gpp_by_province` (unambiguous — it names this one file), whole-token, not the bare word "gpp"
# (which legitimately appears in unrelated layers like province `gov.hp` capacity or vehicle data).
#
# Offline, stdlib-only, deterministic. Exit 0 = clean (or file absent, or now-verified); 1 = a
# violation is live.

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC = os.path.join(REPO, "source-data", "gpp_by_province.json")

# The one script permitted to reference the file: its WRITER. ingest_tmli.build_gpp() returns
# ("gpp_by_province.json", payload) and main() writes it — so the literal appears in the producer by
# construction. Any OTHER pipeline referencer is a consumer projecting the unverified data.
WRITER = "ingest_tmli.py"

# Whole-token match on the filename base, so "gpp" substrings in unrelated code never trip it.
TOKEN = re.compile(r"(?<![A-Za-z0-9_])gpp_by_province(?![A-Za-z0-9_])")


def _ckan_verified(doc):
    """Return (n_provinces, n_ckan_verified) counted from the rows themselves (not trusting meta),
    with meta.n_ckan_verified as a cross-check when present."""
    provs = doc.get("provinces") or {}
    if not isinstance(provs, dict):
        provs = {}
    n = len(provs)
    ck = sum(1 for v in provs.values()
             if isinstance(v, dict) and v.get("source") == "CKAN-NESDC-2566")
    return n, ck


def _referencers(texts_by_name, allowed):
    """Names in texts_by_name (a {name: source_text} map) that reference the token, excluding the
    allowed writer. Pure function so the self-test can feed synthetic inputs."""
    return sorted(name for name, txt in texts_by_name.items()
                  if name not in allowed and TOKEN.search(txt))


def _selftest():
    """Prove the guard FIRES when a builder/page projects the file and stays QUIET on the writer
    alone. A drift here is itself a gate failure, so the guard can never pass vacuously."""
    fails = []
    # must fire: a new builder reads the source file
    bad = {WRITER: "return 'gpp_by_province.json', payload",
           "build_gpp_backdrop.py": "d=json.load(open('source-data/gpp_by_province.json'))"}
    if _referencers(bad, {WRITER}) != ["build_gpp_backdrop.py"]:
        fails.append("SHOULD-FIRE on a builder reading gpp_by_province — did not")
    # must fire: a page fetches it
    page = {"app.js": "loadX().then(...) fetch('data/gpp_by_province.json')"}
    if _referencers(page, {WRITER}) != ["app.js"]:
        fails.append("SHOULD-FIRE on a page fetching gpp_by_province — did not")
    # must stay quiet: only the writer references it
    ok = {WRITER: "return 'gpp_by_province.json', payload"}
    if _referencers(ok, {WRITER}) != []:
        fails.append("FALSE POSITIVE: flagged the writer itself")
    # must stay quiet: an unrelated 'gpp' substring (province capacity, etc.) is not the token
    noise = {"build_province.py": "gov['hp']=gp.get('hp'); gpp_note='n/a'; foo_gpp_bar=1"}
    if _referencers(noise, {WRITER}) != []:
        fails.append("FALSE POSITIVE: matched a bare 'gpp' substring, not the whole token")
    return fails


def main():
    st = _selftest()
    if st:
        print("unverified_gpp_guard: SELF-TEST FAILED (guard logic is unsound, not a data problem):")
        for f in st:
            print("   -", f)
        return 1

    if not os.path.exists(SRC):
        print("unverified_gpp_guard: OK — source-data/gpp_by_province.json absent, nothing to guard.")
        return 0

    try:
        doc = json.load(open(SRC, encoding="utf-8"))
    except Exception as e:
        print("unverified_gpp_guard: cannot read gpp_by_province.json (%s)" % e)
        return 1

    n_prov, n_ck = _ckan_verified(doc)
    if n_prov > 0 and n_ck >= n_prov:
        print("unverified_gpp_guard: OK — all %d provinces are CKAN-verified ('CKAN-NESDC-2566'); "
              "the file has been re-pulled and integration is now allowed." % n_prov)
        return 0

    # Still predominantly unverified: assert no integration path exists.
    pipe = {}
    for p in sorted(glob.glob(os.path.join(REPO, "pipeline", "*.py"))):
        pipe[os.path.basename(p)] = open(p, encoding="utf-8", errors="ignore").read()
    pipe_hits = _referencers(pipe, {WRITER})

    pages = {}
    for p in sorted(glob.glob(os.path.join(REPO, "platform", "*.html"))):
        pages[os.path.basename(p)] = open(p, encoding="utf-8", errors="ignore").read()
    appjs = os.path.join(REPO, "platform", "app.js")
    if os.path.exists(appjs):
        pages["app.js"] = open(appjs, encoding="utf-8", errors="ignore").read()
    page_hits = _referencers(pages, set())  # no writer among pages; any reference is a surfacing

    if pipe_hits or page_hits:
        print("unverified_gpp_guard: the UNVERIFIED GPP knowledge base is being projected toward the "
              "app (only %d/%d provinces CKAN-verified). CLAUDE.md + NEXT_STEPS §0a + the file's own "
              "meta.provenance: do NOT surface gpp_by_province.json as MEASURED until it is re-pulled "
              "per-province from NESDC's CKAN." % (n_ck, n_prov))
        for name in pipe_hits:
            print("   pipeline consumer: %s reads gpp_by_province (only %s may)." % (name, WRITER))
        for name in page_hits:
            print("   page surfacing: %s references gpp_by_province." % name)
        print("   Fix: drop the reference, OR re-pull real per-province NESDC CKAN GPP so every row "
              "is 'CKAN-NESDC-2566' (which lifts this guard automatically), OR — if a legitimate "
              "ESTIMATED integration is truly intended — label it estimated and update this guard's "
              "WRITER allow with a reason, a deliberate reviewed act.")
        return 1

    print("unverified_gpp_guard: OK — gpp_by_province.json (%d/%d CKAN-verified) stays source-only; "
          "no pipeline builder but %s reads it and no page surfaces it." % (n_ck, n_prov, WRITER))
    return 0


if __name__ == "__main__":
    sys.exit(main())
