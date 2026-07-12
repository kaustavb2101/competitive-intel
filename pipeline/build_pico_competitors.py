#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_pico_competitors.py — per-province SUB-SCALE competitor exposure (MEASURED, objective #2).

Projects the FPO PICO-finance licence registry (source-data/pico_by_province.json, via ingest_pico.py)
into the app layer platform/data/pico_competitors.json, joined against AutoX's own per-province branch
count (MEASURED, from branches.json). One row per province:

    operators (licensed PICO offices) · hq · branch · autox (AutoX branches) · ratio (operators / autox)

WHY THIS MATTERS (two honest reads on the SAME measured count):
  - Competitive density: these are real sub-scale rivals AutoX competes with for the same small-ticket
    secured borrower — invisible in the big-4 title-lender census, so this is the first MEASURED read on
    that long tail (province granularity).
  - Regulatory shake-out (Q1-2026 BoT registration deadline): PICO operators are exactly the sub-scale
    licensees under pressure. A province thick with them is a province where the competitive field could
    thin the most — the MEASURED complement to the ESTIMATED rival-fragility proxy (exit_whitespace.json).

This is a competitive-pressure read on the network we already run — it makes NO open / close / expand call.

MEASURED vs COMPUTED (stated in meta, repeated in the UI):
  MEASURED   operators/hq/branch  FPO licence registry, per-province office counts (ingest_pico.py).
  MEASURED   autox                AutoX branches in the province (canonical province of branches.json).
  COMPUTED   ratio                operators / autox (null when autox == 0).

DETERMINISTIC + NETWORK-FREE. Pure function of two committed inputs -> carries --check (byte-exact).
SKIP-passes (exit 3) when source-data/pico_by_province.json is absent, mirroring the other optional
distilled layers, so the gate never breaks on a missing pull.

    python3 build_pico_competitors.py           # write platform/data/pico_competitors.json
    python3 build_pico_competitors.py --check    # verify byte-for-byte reproduce
"""
import argparse, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from regionmap import canonical

SRC      = os.path.join(ROOT, "source-data", "pico_by_province.json")
BRANCHES = os.path.join(ROOT, "platform", "data", "branches.json")
OUT      = os.path.join(ROOT, "platform", "data", "pico_competitors.json")


def _load(p):
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def _autox_by_province():
    br = _load(BRANCHES)
    br = br if isinstance(br, list) else br.get("items", br)
    counts = {}
    for b in br:
        c = canonical(b.get("v"))
        if c and c not in ("Other", ""):
            counts[c] = counts.get(c, 0) + 1
    return counts, len(br)


def build():
    src = _load(SRC)
    prov = src.get("provinces", {})
    autox, n_branches = _autox_by_province()

    rows = []
    for pv, d in prov.items():
        a = autox.get(pv, 0)
        ops = d.get("operators", 0)
        rows.append({
            "province_th": pv,
            "operators": ops,
            "hq": d.get("hq", 0),
            "branch": d.get("branch", 0),
            "autox": a,
            "ratio": round(ops / a, 2) if a > 0 else None,
        })
    # rank by raw operator count desc, then ratio desc, then name — deterministic tie-break.
    rows.sort(key=lambda r: (-r["operators"], -(r["ratio"] or 0), r["province_th"]))

    total_ops = sum(r["operators"] for r in rows)
    n_outnumbered = sum(1 for r in rows if r["autox"] > 0 and r["operators"] > r["autox"])
    top = rows[0] if rows else None

    meta = {
        "generated_by": "pipeline/build_pico_competitors.py",
        "label": "SUB-SCALE competitor exposure per province — MEASURED count of licensed PICO-finance "
                 "operators (FPO registry) next to AutoX's own branch count. The first measured read on "
                 "the small-lender long tail the big-4 title-lender census misses.",
        "objective": "#2 competitive risk: where AutoX faces the thickest sub-scale-rival field, and — the "
                     "same operators being the Q1-2026 BoT registration-deadline cohort — where the "
                     "competitive field could thin most in the regulatory shake-out. No open/expand call.",
        "provenance": {
            "operators": "MEASURED — FPO PICO-finance licence registry (catalog.fpo.go.th), per-province "
                         "office counts via ingest_pico.py. HQ = distinct operators; branch = extra offices.",
            "autox": "MEASURED — AutoX branches whose canonical province matches, counted from branches.json.",
            "ratio": "COMPUTED — operators / autox (null where AutoX has no branch in the province).",
        },
        "relation_to_big4_census": "COMPLEMENT, not overlap. competitors_census.json / rival_density.json "
                                   "census the four big COMPLIANT title lenders (Muangthai/Srisawad/Tidlor/"
                                   "Heng) by coordinate. This layer censuses the SUB-SCALE PICO licensees — "
                                   "province-only (no coordinates). Do NOT sum the two; they are different "
                                   "operator universes measured at different granularities.",
        "n_provinces": len(rows),
        "n_operators_total": total_ops,
        "n_provinces_outnumbered": n_outnumbered,
        "n_autox_branches": n_branches,
        "top_province": {"province_th": top["province_th"], "operators": top["operators"]} if top else None,
        "gaps": [
            "Province-granular only (no coordinates in the FPO source) — cannot be joined to a district or "
            "branch catchment; it complements, not replaces, the coordinate-based big-4 census.",
            "Licensed operators only — informal / unlicensed lenders are outside any registry.",
        ],
        "inputs": ["source-data/pico_by_province.json (FPO registry, ingest_pico.py)",
                   "platform/data/branches.json (AutoX branch coordinates + province)"],
    }
    return {"meta": meta, "provinces": rows}


def run(check=False):
    if not os.path.exists(SRC):
        if check:
            print("SKIP: source-data/pico_by_province.json absent — run `python3 ingest_pico.py` "
                  "(needs the FPO pull) first")
            return 3
        print("ERROR: source-data/pico_by_province.json absent — run `python3 ingest_pico.py` first",
              file=sys.stderr)
        return 1
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or io.open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, ROOT)} (re-run: python3 pipeline/build_pico_competitors.py)")
            return 1
        m = obj["meta"]
        print(f"OK: pico_competitors.json reproduces ({m['n_operators_total']} operators, {m['n_provinces']} provinces)")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print(f"wrote {m['n_provinces']} provinces -> platform/data/pico_competitors.json "
          f"({len(text)/1024:.0f} KB; {m['n_operators_total']} PICO operators, "
          f"{m['n_provinces_outnumbered']} provinces where they outnumber AutoX)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="per-province sub-scale PICO competitor exposure (measured, vs AutoX)")
    ap.add_argument("--check", action="store_true")
    for stream in (sys.stdout, sys.stderr):
        try: stream.reconfigure(encoding="utf-8")
        except Exception: pass
    raise SystemExit(run(check=ap.parse_args().check))
