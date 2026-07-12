#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_napprang.py — project the measured OAE dry-season rice pull into the app (objective #1).

Reads source-data/oae_napprang.json (pull_oae_napprang.py) → platform/data/napprang.json, the
per-province dry-season (SECOND) rice-crop exposure the drought-watch strip cites: planted /
harvested area + this-season abandonment, with a national-rank so "how exposed is this province
to a second-crop cut" reads at a glance.

Deterministic + network-free; --check byte-exact; exits 3 (SKIP) when the pull is absent.

  python3 build_napprang.py
  python3 build_napprang.py --check
"""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data", "oae_napprang.json")
OUT = os.path.join(ROOT, "platform", "data", "napprang.json")


def build():
    src = json.load(open(SRC, encoding="utf-8"))
    provs = src.get("provinces", [])
    # already sorted by -planted_rai in the pull; stamp a 1-based national rank by planted area.
    out = []
    for i, p in enumerate(provs):
        out.append({
            "th": p["th"], "region": p.get("region"),
            "planted_rai": int(p.get("planted_rai") or 0),
            "harvested_rai": int(p.get("harvested_rai") or 0),
            "production_tons": int(p.get("production_tons") or 0),
            "abandon_pct": p.get("abandon_pct"),
            "rank_planted": i + 1,
        })
    m = src.get("meta", {})
    return {
        "meta": {
            "title": "Dry-season (second) rice exposure per province — measured (OAE)",
            "generated_by": "pipeline/build_napprang.py",
            "label": m.get("label"),
            "source": m.get("source"),
            "vintage": m.get("vintage"),
            "pulled": m.get("pulled"),
            "n_provinces": len(out),
            "national": m.get("national"),
            "why": m.get("why"),
        },
        # province → measured second-crop exposure, keyed by Thai name for a direct join on the strip.
        "by_province": {p["th"]: p for p in out},
        "provinces": out,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(SRC):
        print("build_napprang.py: source-data/oae_napprang.json absent — run pull_oae_napprang.py (SKIP).")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            print("build_napprang.py --check: SKIP (napprang.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_napprang.py --check: drifted — re-run the builder.")
        print("build_napprang.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    d = json.loads(payload)
    print("wrote %s — %s, %d provinces" % (OUT, d["meta"]["vintage"], d["meta"]["n_provinces"]))


if __name__ == "__main__":
    main()
