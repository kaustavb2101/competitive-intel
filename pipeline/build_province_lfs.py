#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_province_lfs.py — FRESH provincial labour market (objective #1): NSO Labour Force Survey
2026 Q1, all 77 provinces, projected for the app.

  in : source-data/staging/nso_lfs.json          NSO LFS via CKAN CSVs (ingest 2026-07-20)
  out: platform/data/province_lfs.json           per-province unemployment / seasonal-waiting / age mix

Provenance: MEASURED — NSO Labour Force Survey (BE 2569 Q1 = CE 2026 Q1). Informal share, wages
and occupation splits are NOT here — NSO publishes those only at region level (checked; logged in
the staging meta), so this layer carries only what is genuinely provincial.

Deterministic + network-free; `--check` byte-compares; SKIPs (exit 3) if staging absent.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "source-data", "staging", "nso_lfs.json")
OUT = os.path.join(ROOT, "platform", "data", "province_lfs.json")


def build():
    doc = json.load(open(IN, encoding="utf-8"))
    rows = []
    for p in doc.get("provinces", []):
        lf = p.get("labor_force_total_k")
        sw = p.get("seasonal_waiting_k")
        rows.append({
            "name_th": p["name_th"],
            "labor_force_k": lf,
            "employed_k": p.get("employed_k"),
            "unemployment_rate_pct": p.get("unemployment_rate_pct"),
            "seasonal_waiting_k": sw,
            "seasonal_share_pct": round(sw * 100.0 / lf, 2) if (sw is not None and lf) else None,
        })
    rows.sort(key=lambda r: -(r["unemployment_rate_pct"] or 0))

    hi = rows[:5]
    headline = ("NSO LFS %s %s: highest provincial unemployment — "
                % (doc.get("meta", {}).get("vintage", "2026 Q1"), "")).strip() + " "
    headline = ("Freshest measured labour read (NSO LFS 2026 Q1, all 77 provinces): highest "
                "unemployment " +
                ", ".join("%s %.1f%%" % (r["name_th"], r["unemployment_rate_pct"]) for r in hi if r["unemployment_rate_pct"] is not None) + ".")

    return {
        "meta": {
            "title": "Provincial labour market — NSO LFS 2026 Q1 (obj #1)",
            "generated_by": "pipeline/build_province_lfs.py",
            "label": "MEASURED — NSO Labour Force Survey, BE 2569 Q1 (Jan–Mar 2026), all 77 "
                     "provinces via NSO's CKAN CSV exports. Informal share / wages / occupation "
                     "exist only at region level at NSO and are deliberately absent here.",
            "source": doc.get("meta", {}).get("label"),
            "vintage": "2026 Q1 (BE 2569)",
            "retrieved": doc.get("meta", {}).get("retrieved"),
        },
        "headline": headline,
        "provinces": rows,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN):
        if args.check:
            print("build_province_lfs.py --check: SKIP (staging/nso_lfs.json absent)")
            sys.exit(3)
        sys.exit("build_province_lfs.py: staging/nso_lfs.json missing")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_province_lfs.py --check: output missing")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_province_lfs.py --check: drifted — re-run the builder.")
        print("build_province_lfs.py --check: OK (byte-exact)")
        return
    open(OUT, "w", encoding="utf-8").write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d provinces" % (OUT, len(obj["provinces"])))
    print("headline:", obj["headline"])


if __name__ == "__main__":
    main()
