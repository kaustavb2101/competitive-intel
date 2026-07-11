#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_ilostat_labour.py — MEASURED Thai labour-market battery via ILOSTAT (the NSO-block workaround).

NSO's own API hosts are geoblocked from datacenter IPs (api/ittdashboard 403, statbank/gdcatalog 502),
but the ILO mirrors Thailand's official LFS submissions on ilostat — reachable, keyless, fresh to 2025:
  rplumber.ilo.org/data/indicator/?id=<ID>&ref_area=THA

Why (objective #1): sector employment (agri 11.2M of 39.6M employed), the INFORMALITY rate (informal
workers are the non-bank borrower base), and unemployment — the official Thai labour numbers, without
the Thai IP. Complements (does not replace) the finer vendored per-province NSO layers.

Writes source-data/ilostat_labour.json — per series: label, unit, latest rows (SEX_T only, compact).
Network puller — NOT in the determinism gate.

  python3 pull_ilostat_labour.py
  python3 pull_ilostat_labour.py --stamp 2026-07-10
"""
import argparse, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "ilostat_labour.json")
BASE = "https://rplumber.ilo.org/data/indicator/?id=%s&ref_area=THA&timefrom=%s&format=.json"
UA = {"User-Agent": "autox-credit-intel/1.0"}

# (id, since, label, unit) — each skipped gracefully on error; ids are ILOSTAT indicator codes.
SERIES = [
    ("EMP_TEMP_SEX_ECO_NB", "2022", "Employment by economic sector", "thousands"),
    ("EMP_TEMP_SEX_AGE_NB", "2022", "Employment by age", "thousands"),
    ("UNE_DEAP_SEX_AGE_RT", "2022", "Unemployment rate", "%"),
    ("EMP_NIFL_SEX_RT", "2019", "Informal employment rate", "% of employment"),
    ("EMP_TEMP_SEX_STE_NB", "2022", "Employment by status (own-account / employees / employers / family)", "thousands"),
    ("EAR_4MTH_SEX_ECO_CUR_NB", "2020", "Mean monthly earnings by sector", "local currency"),
    ("EAR_XEES_SEX_ECO_NB", "2020", "Mean monthly earnings of employees by sector", "local currency"),
    ("HOW_TEMP_SEX_ECO_NB", "2022", "Mean weekly hours by sector", "hours"),
]


def _get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(4 * (i + 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default="")
    args = ap.parse_args()
    out, skipped = {}, []
    for sid, since, label, unit in SERIES:
        try:
            rows = _get(BASE % (sid, since))
        except Exception as e:
            skipped.append({"id": sid, "why": str(e)[:80]})
            continue
        keep = []
        for r in rows:
            if r.get("sex") not in (None, "SEX_T"):
                continue
            keep.append({k: r.get(k) for k in ("time", "classif1", "classif2", "obs_value") if r.get(k) is not None})
        if not keep:
            skipped.append({"id": sid, "why": "no SEX_T rows"})
            continue
        out[sid] = {"label": label, "unit": unit,
                    "times": sorted({r["time"] for r in keep}),
                    "rows": sorted(keep, key=lambda r: (r["time"], r.get("classif1") or ""))}
    if not out:
        sys.exit("pull_ilostat_labour.py: every series failed — API changed?")
    doc = {
        "meta": {
            "source": "ILOSTAT (rplumber.ilo.org) — the ILO's mirror of Thailand's official NSO LFS "
                      "submissions. Keyless, cloud-reachable (NSO's own hosts are geoblocked).",
            "label": "MEASURED — Thai labour battery (sector employment · informality · unemployment · "
                     "earnings/hours where published). National level; the per-province NSO layers "
                     "(vendored SES/LFS) stay the fine-grained source.",
            "generated_by": "pipeline/pull_ilostat_labour.py",
            "pulled": args.stamp,
            "series_ok": sorted(out),
            "series_skipped": skipped,
        },
        "series": out,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print("wrote %s — %d series ok, %d skipped" % (OUT, len(out), len(skipped)))
    for s in skipped:
        print("   skip %s: %s" % (s["id"], s["why"]))


if __name__ == "__main__":
    main()
