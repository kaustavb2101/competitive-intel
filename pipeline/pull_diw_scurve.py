#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_diw_scurve.py — MEASURED S-curve (target-industry) factory footprint per province (DIW).

Source: diw-dataset.diw.go.th CKAN, dataset `fac-10scurve` — 18k factories in Thailand's target
industries (แปรรูปอาหาร, อิเล็กทรอนิกส์, ยานยนต์, หุ่นยนต์, เกษตรเทคโนชีวภาพ, …), each with
province, workers and registered capital. Reachable from any cloud IP (the data.go.th bypass).

Why (objective #1): the AUTOMOTIVE group (~1.6k factories) is the measured footprint of the
ICE-parts industry — the workforce most exposed to the EV transition that the brand-trends board
shows arriving (pure-EV marques 0.2%→3.8% of first registrations). Which provinces carry that
exposure is a portfolio-risk read for factory-worker borrowers.

Writes the compact per-province aggregate (NOT the 11MB raw) → source-data/scurve_by_province.json:
{meta, provinces: {<th-name>: {groups: {<group>: {n, workers, capital_mbaht}}, total…}}}.
Network puller — NOT in the determinism gate.

  python3 pull_diw_scurve.py            # pull + aggregate + write
  python3 pull_diw_scurve.py --stamp 2026-07-09
"""
import argparse, csv, io, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "scurve_by_province.json")
PKG = "https://diw-dataset.diw.go.th/api/3/action/package_show?id=fac-10scurve"
UA = {"User-Agent": "autox-credit-intel/1.0"}
COL_PROV, COL_CAP, COL_WORK, COL_GROUP = 14, 16, 17, 20


def _get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default="")
    args = ap.parse_args()
    pkg = json.loads(_get(PKG))["result"]
    url = [r for r in pkg["resources"] if (r.get("format") or "").upper() == "CSV"][0]["url"]
    rows = list(csv.reader(io.StringIO(_get(url).decode("utf-8-sig", errors="replace"))))[1:]
    if len(rows) < 5000:
        sys.exit("pull_diw_scurve.py: only %d rows — likely truncated; not writing." % len(rows))
    prov = {}
    for r in rows:
        if len(r) <= COL_GROUP:
            continue
        p, g = r[COL_PROV].strip(), r[COL_GROUP].strip()
        if not p or not g:
            continue
        try:
            w = int(float(r[COL_WORK] or 0))
        except ValueError:
            w = 0
        try:
            c = float(r[COL_CAP] or 0)
        except ValueError:
            c = 0.0
        e = prov.setdefault(p, {"n": 0, "workers": 0, "capital_mbaht": 0.0, "groups": {}})
        e["n"] += 1; e["workers"] += w; e["capital_mbaht"] += c
        ge = e["groups"].setdefault(g, {"n": 0, "workers": 0, "capital_mbaht": 0.0})
        ge["n"] += 1; ge["workers"] += w; ge["capital_mbaht"] += c
    for e in prov.values():
        e["capital_mbaht"] = round(e["capital_mbaht"], 1)
        for ge in e["groups"].values():
            ge["capital_mbaht"] = round(ge["capital_mbaht"], 1)
    doc = {
        "meta": {
            "source": "DIW fac-10scurve via diw-dataset.diw.go.th CKAN (department catalog — bypasses the "
                      "data.go.th geoblock; reachable from any cloud IP).",
            "label": "MEASURED — S-curve/target-industry factories per province (n, workers, registered "
                     "capital) incl. the AUTOMOTIVE group = the ICE-parts workforce exposed to the EV transition.",
            "generated_by": "pipeline/pull_diw_scurve.py",
            "pulled": args.stamp,
            "n_factories": sum(e["n"] for e in prov.values()),
            "n_provinces": len(prov),
            "groups_national": {},
        },
        "provinces": {k: prov[k] for k in sorted(prov)},
    }
    nat = {}
    for e in prov.values():
        for g, ge in e["groups"].items():
            ne = nat.setdefault(g, {"n": 0, "workers": 0})
            ne["n"] += ge["n"]; ne["workers"] += ge["workers"]
    doc["meta"]["groups_national"] = {g: nat[g] for g in sorted(nat, key=lambda x: -nat[x]["n"])}
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    auto = nat.get("อุตสาหกรรมยานยนต์", {})
    print("wrote %s — %d factories, %d provinces; automotive: %s factories / %s workers" % (
        OUT, doc["meta"]["n_factories"], len(prov),
        format(auto.get("n", 0), ","), format(auto.get("workers", 0), ",")))


if __name__ == "__main__":
    main()
