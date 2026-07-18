#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_pico_competitors.py — per-province sub-scale rivals vs AutoX footprint (MEASURED).

Objective #2 (competitive risk on the EXISTING network). The "sub-scale rivals per province vs our
footprint" read: for every canonical province, the MEASURED count of licensed PICO-finance
(พิโกไฟแนนซ์) operators — a distinct small-ticket non-bank competitor class to AutoX — set against
the MEASURED count of AutoX (เงินไชโย) branches. Answers, without any inference:

  "Where do sub-scale rivals most outnumber our own branches?"

WHY A SEPARATE LAYER (not folded into build_exit_whitespace.py)
--------------------------------------------------------------
The obvious ask was to swap the PICO census into exit_whitespace's ESTIMATED sub-scale leg. We do
NOT, on purpose. exit_whitespace scores at the AMPHOE (district, 928) grain; the FPO PICO registry
carries only a PROVINCE of service (จังหวัดที่ให้บริการ), no coordinate and no district. Spreading a
province total across its districts would manufacture spatial precision the registry does not have —
turning a clean measurement into a fabricated one. So exit_whitespace stays as the honest
district-grain ESTIMATED regulatory-tailwind cue (big-4 scarcity × demand), and the measured PICO
census gets its OWN province-grain layer where BOTH sides are a straight count. Two honest reads beat
one dishonest blend.

INPUTS  (both committed, deterministic, network-free)
  platform/data/pico_census.json  — MEASURED per-province PICO operator counts (build_pico_census.py,
                                     from the FPO licence registry). {by_province:{prov:{total,head,branch}}}
  platform/data/branches.json     — the 2,015 AutoX branches; province in field "v" (Thai). Counted
                                     per canonical province via regionmap.canonical — a direct tally.
  platform/data/provinces/index.json — province EN name + slug + region (for display / deep-dive link).

OUTPUT  platform/data/pico_competitors.json
  { meta, provinces:[{th,en,slug,region, pico_total,pico_head,pico_branch, autox_branches,
                      outnumber (=pico_total-autox_branches), ratio (=pico_total/autox_branches)}],
    top, totals }  sorted by outnumber desc (then province th).

Every number is MEASURED — two government/own-footprint tallies divided; no scoring, no synthesis.

DETERMINISTIC + NETWORK-FREE. Carries --check (byte-exact reproduce). SKIP-passes (exit 3) only if the
upstream pico_census.json is absent, so the determinism gate never breaks on a missing input.

  python3 build_pico_competitors.py
  python3 build_pico_competitors.py --check
"""
import argparse, json, os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from regionmap import canonical, REGION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
PICO_IN = os.path.join(DATA, "pico_census.json")
BRANCHES_IN = os.path.join(DATA, "branches.json")
INDEX_IN = os.path.join(DATA, "provinces", "index.json")
OUT = os.path.join(DATA, "pico_competitors.json")


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build():
    pico = _load(PICO_IN)
    by_prov = pico.get("by_province", {})

    # MEASURED AutoX branch count per canonical province (field "v" = Thai province name).
    branches = _load(BRANCHES_IN)
    autox = Counter()
    n_unmapped = 0
    for b in branches:
        c = canonical((b.get("v") or "").strip())
        if c:
            autox[c] += 1
        else:
            n_unmapped += 1

    # province EN name / slug / region for display + deep-dive linking (canonical th key).
    disp = {}
    if os.path.exists(INDEX_IN):
        for r in _load(INDEX_IN):
            th = canonical((r.get("th") or "").strip())
            if th:
                disp[th] = {"en": r.get("en"), "slug": r.get("slug"), "region": r.get("region")}

    all_prov = sorted(set(by_prov) | set(autox) | set(REGION))
    rows = []
    for p in all_prov:
        rec = by_prov.get(p, {})
        pico_total = rec.get("total", 0)
        pico_head = rec.get("head", 0)
        pico_branch = rec.get("branch", 0)
        ax = autox.get(p, 0)
        d = disp.get(p, {})
        rows.append({
            "th": p,
            "en": d.get("en"),
            "slug": d.get("slug"),
            "region": d.get("region") or REGION.get(p),
            "pico_total": pico_total,
            "pico_head": pico_head,
            "pico_branch": pico_branch,
            "autox_branches": ax,
            "outnumber": pico_total - ax,                         # >0 = sub-scale rivals exceed our branches
            "ratio": round(pico_total / ax, 2) if ax else None,   # None where AutoX is absent (no denominator)
        })

    # headline sort: where sub-scale rivals most OUTNUMBER our footprint (absolute gap), then province.
    rows.sort(key=lambda r: (-r["outnumber"], r["th"]))
    top = rows[:15]

    n_outnumbered = sum(1 for r in rows if r["outnumber"] > 0)
    n_autox_absent = sum(1 for r in rows if r["autox_branches"] == 0)
    pico_total_all = sum(r["pico_total"] for r in rows)
    autox_total_all = sum(r["autox_branches"] for r in rows)

    meta = {
        "generated_by": "pipeline/build_pico_competitors.py",
        "label": ("MEASURED per-province read of sub-scale rival density vs the AutoX footprint: "
                  "licensed PICO-finance (พิโกไฟแนนซ์) operators (a distinct small-ticket non-bank "
                  "competitor class) set against AutoX branch count, province by province. Answers "
                  "\"where do sub-scale rivals most outnumber our own branches?\""),
        "source": ("MEASURED — two direct tallies: (1) PICO operators per province from the FPO "
                   "licence registry (platform/data/pico_census.json, built by build_pico_census.py); "
                   "(2) AutoX branches per canonical province counted from platform/data/branches.json. "
                   "outnumber and ratio are those two counts differenced / divided — no modelling."),
        "provenance": ("measured — government PICO licence registry (per-province tally) vs own branch "
                       "footprint (per-province tally). Both counts are direct; no inference."),
        "objective": ("Competitive risk (#2): measured sub-scale-rival pressure on the existing network, "
                      "province by province. Complements the coordinate-based big-4 census and the "
                      "district-grain ESTIMATED exit_whitespace cue — this leg is fully MEASURED."),
        "pico_vintage": (pico.get("meta") or {}).get("vintage"),
        "pico_source_url": (pico.get("meta") or {}).get("source_url"),
        "n_provinces": len(rows),
        "n_provinces_pico_outnumbers_autox": n_outnumbered,
        "n_provinces_autox_absent": n_autox_absent,
        "n_autox_branches_unmapped": n_unmapped,
        "pico_total": pico_total_all,
        "autox_total": autox_total_all,
        "definitions": {
            "pico_total": "MEASURED count of licensed PICO-finance operator service points in the province (FPO registry).",
            "autox_branches": "MEASURED count of AutoX (เงินไชโย) branches in the province (branches.json, field v).",
            "outnumber": "pico_total - autox_branches. Positive = sub-scale rivals outnumber our branches.",
            "ratio": "pico_total / autox_branches (null where AutoX has no branch in the province).",
        },
        "gaps": [
            "PICO counts are per PROVINCE (the FPO registry carries province of service, not a coordinate "
            "or district), so this is a province-grain read — it does NOT localise pressure within a "
            "province the way the coordinate-based big-4 census does.",
            "A PICO licence does not guarantee an active storefront; treat the count as licensed capacity.",
            "PICO overlaps but is not identical to AutoX's product (a licence-capped small-ticket class); "
            "outnumbering is competitive-density pressure, not a like-for-like branch race.",
        ],
        "sorted_by": "outnumber desc, then province th asc (stable)",
    }
    return {"meta": meta, "provinces": rows, "top": top,
            "totals": {"pico_total": pico_total_all, "autox_total": autox_total_all,
                       "n_provinces": len(rows), "n_provinces_pico_outnumbers_autox": n_outnumbered}}


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8")
        except Exception: pass

    if not os.path.exists(PICO_IN):
        msg = ("build_pico_competitors.py: pico_census.json absent — run "
               "python3 pipeline/build_pico_census.py first (needs the FPO pull).")
        if args.check:
            print("build_pico_competitors.py --check: SKIP (pico_census.json absent)")
            sys.exit(3)
        sys.exit(msg)

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_pico_competitors.py --check: SKIP (pico_competitors.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_pico_competitors.py --check: pico_competitors.json drifted — run "
                     "python3 pipeline/build_pico_competitors.py")
        print("build_pico_competitors.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    print("wrote %s (%d provinces; PICO %d vs AutoX %d; sub-scale rivals outnumber us in %d provinces)"
          % (OUT, m["n_provinces"], m["pico_total"], m["autox_total"],
             m["n_provinces_pico_outnumbers_autox"]))
    for r in obj["top"][:6]:
        print("  %-16s PICO=%3d  AutoX=%3d  outnumber=%+d  ratio=%s"
              % (r["th"], r["pico_total"], r["autox_branches"], r["outnumber"],
                 ("%.2f" % r["ratio"]) if r["ratio"] is not None else "n/a"))


if __name__ == "__main__":
    main()
