#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_drought_district.py — DISTRICT drought index (objective #1): OAE's SPEI ดัชนีภัยแล้ง per
amphoe, projected for the app. Upgrades the drought read from province rainfall to an official
district-level index.

  in : source-data/staging/drought_district.json  OAE SPEI by amphoe (Power BI capture, 2026-06)
  out: platform/data/drought_district.json        928 districts: spei + severity class

Provenance: MODELLED — published by OAE (official), computed from ERA5-Land reanalysis; a model
product, not station rainfall and not a disaster declaration. Single-month snapshot (2026-06);
5 districts carry a suspect exact 0.0 (grid-coverage gap — flagged, not corrected).

Deterministic + network-free; `--check` byte-compares; SKIPs (exit 3) if staging absent.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "source-data", "staging", "drought_district.json")
OUT = os.path.join(ROOT, "platform", "data", "drought_district.json")

SUSPECT_ZERO = 0.0


def cls_of(s):
    if s is None:
        return None
    if s <= -2.0:
        return "extreme"
    if s <= -1.5:
        return "severe"
    if s <= -1.0:
        return "moderate"
    if s < 1.0:
        return "normal"
    return "wet"


def build():
    doc = json.load(open(IN, encoding="utf-8"))
    spei_key = None
    rows = []
    for d in doc.get("districts", []):
        if spei_key is None:
            spei_key = next((k for k in d if k.startswith("spei_")), None)
        s = d.get(spei_key)
        suspect = (s == SUSPECT_ZERO)
        rows.append({
            "code": d.get("amphoe_code"),
            "name_th": d.get("name_th"), "name_en": d.get("name_en"),
            "province_th": d.get("province_th"),
            "spei": round(s, 3) if s is not None else None,
            "cls": None if suspect else cls_of(s),
            "suspect_zero": suspect or None,
            "join_ambiguous": (d.get("join_to_th_amphoe_geojson") or {}).get("ambiguous") or None,
        })
    rows.sort(key=lambda r: (r["spei"] if r["spei"] is not None else 99))

    n = {}
    for r in rows:
        if r["cls"]:
            n[r["cls"]] = n.get(r["cls"], 0) + 1
    dry = (n.get("extreme", 0) + n.get("severe", 0) + n.get("moderate", 0))
    worst = [r for r in rows if r["cls"] in ("extreme", "severe")][:5]
    headline = ("%d of 928 districts sit at moderate-or-worse drought on OAE's SPEI (2026-06): "
                "%d extreme, %d severe, %d moderate."
                % (dry, n.get("extreme", 0), n.get("severe", 0), n.get("moderate", 0)))
    if worst:
        headline += " Driest: " + ", ".join("%s (%s)" % (w["name_th"], w["province_th"]) for w in worst) + "."

    return {
        "meta": {
            "title": "District drought — OAE SPEI ดัชนีภัยแล้ง รายอำเภอ (obj #1)",
            "generated_by": "pipeline/build_drought_district.py",
            "label": "MODELLED — OAE-published SPEI per amphoe (ERA5-Land reanalysis). An official "
                     "model product: not station rainfall, not a disaster declaration. Snapshot "
                     "%s only; 5 districts carry a suspect 0.0 (grid gap) and are unclassified."
                     % (spei_key or "").replace("spei_", "").replace("_", "-"),
            "source": doc.get("meta", {}).get("label"),
            "snapshot": (spei_key or "").replace("spei_", "").replace("_", "-"),
            "retrieved": doc.get("meta", {}).get("retrieved"),
            "counts": n,
        },
        "headline": headline,
        "districts": rows,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN):
        if args.check:
            print("build_drought_district.py --check: SKIP (staging/drought_district.json absent)")
            sys.exit(3)
        sys.exit("build_drought_district.py: staging/drought_district.json missing")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_drought_district.py --check: output missing")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_drought_district.py --check: drifted — re-run the builder.")
        print("build_drought_district.py --check: OK (byte-exact)")
        return
    open(OUT, "w", encoding="utf-8").write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d districts" % (OUT, len(obj["districts"])))
    print("headline:", obj["headline"])


if __name__ == "__main__":
    main()
