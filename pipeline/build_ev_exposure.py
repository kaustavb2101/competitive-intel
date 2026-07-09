#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_ev_exposure.py — per-province EV-transition exposure (MEASURED, DIW automotive factories).

Projects source-data/scurve_by_province.json (pull_diw_scurve.py — DIW fac-10scurve) into the
app: for each province, the AUTOMOTIVE-industry factory count / workers / registered capital —
the ICE-parts workforce most exposed to the EV wave the brand-trends board measures (pure-EV
marques 0.2%→3.8% of first registrations). Objective #1: these workers are borrowers.

Deterministic + network-free over the committed aggregate; --check byte-exact; exits 3 (SKIP)
when the pull is absent.

  python3 build_ev_exposure.py
  python3 build_ev_exposure.py --check
"""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data", "scurve_by_province.json")
OUT = os.path.join(ROOT, "platform", "data", "ev_exposure.json")
AUTO = "อุตสาหกรรมยานยนต์"


def build():
    src = json.load(open(SRC, encoding="utf-8"))
    rows = []
    for prov, e in src["provinces"].items():
        g = (e.get("groups") or {}).get(AUTO)
        if not g:
            continue
        rows.append({"th": prov, "n": g["n"], "workers": g["workers"],
                     "capital_mbaht": round(g.get("capital_mbaht", 0.0), 1)})
    rows.sort(key=lambda r: (-r["workers"], r["th"]))
    tot_n = sum(r["n"] for r in rows); tot_w = sum(r["workers"] for r in rows)
    return {
        "meta": {
            "title": "EV-transition exposure — automotive-industry factories per province (DIW, measured)",
            "generated_by": "pipeline/build_ev_exposure.py",
            "label": "MEASURED — DIW fac-10scurve automotive-group factories (n / workers / registered "
                     "capital) per province. The ICE-parts workforce exposed to the EV transition; the "
                     "exposure READ (that EV pressures these jobs) is context, not a default forecast.",
            "source": "source-data/scurve_by_province.json (pull_diw_scurve.py — diw-dataset.diw.go.th, "
                      "pulled %s)" % (src["meta"].get("pulled") or "n/a"),
            "national": {"factories": tot_n, "workers": tot_w},
            "n_provinces": len(rows),
        },
        "provinces": rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(SRC):
        print("build_ev_exposure.py: source-data/scurve_by_province.json absent — run pull_diw_scurve.py (SKIP).")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_ev_exposure.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_ev_exposure.py --check: drifted — re-run the builder.")
        print("build_ev_exposure.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    d = json.loads(payload)
    print("wrote %s — %d provinces, national %s workers" % (
        OUT, d["meta"]["n_provinces"], format(d["meta"]["national"]["workers"], ",")))


if __name__ == "__main__":
    main()
