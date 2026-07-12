#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ingest_pico.py — MEASURED sub-scale competitor census (FPO licensed PICO-finance operators).

WHAT THIS IS
    The Fiscal Policy Office (FPO, Ministry of Finance) publishes the full registry of licensed
    PICO-finance operators (พิโกไฟแนนซ์) — the small, provincially-licensed personal-loan lenders
    (loan ceilings ฿50k PICO / ฿100k PICO-plus, secured incl. vehicle-registration title). These are
    exactly the SUB-SCALE rivals AutoX faces that the big-4 title-lender census (Muangthai / Srisawad /
    Tidlor / Heng) does NOT cover — and exactly the operators exposed to the Q1-2026 BoT responsible-
    lending registration deadline. The FPO CKAN (catalog.fpo.go.th) is reachable from any IP, so this
    census refreshes from CI without the Thai laptop.

    This script normalizes the raw registry CSV into the canonical 77-province layer the pipeline uses:
    per-province counts of licensed operators, split into head offices (สำนักงานใหญ่ = distinct legal
    operators) and branch offices (สำนักสาขา = additional service points).

    python3 ingest_pico.py --pull    # fetch the FPO registry via pull_datagoth (any IP) -> source-data/datagoth/fpo_pico.csv
    python3 ingest_pico.py           # normalize the raw CSV -> source-data/pico_by_province.json (committed)
    python3 ingest_pico.py --check   # verify the normalized layer reproduces byte-exact (SKIP/exit 3 if raw absent)

PROVENANCE
    MEASURED — an official government licence registry, nothing synthesized. Each row is one licensed
    office with its service province + licence number + full address. We aggregate to per-province
    counts only (no coordinates in the source, so no fake geometry). The raw CSV is gitignored (bulk,
    re-pullable); the small normalized per-province layer is committed and byte-exact reproducible.
"""
import argparse, csv, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from regionmap import canonical

RAW = os.path.join(ROOT, "source-data", "datagoth", "fpo_pico.csv")
OUT = os.path.join(ROOT, "source-data", "pico_by_province.json")

# CSV column headers (Thai, from the FPO registry) we read.
COL_PROV   = "จังหวัดที่ให้บริการ"   # province of service
COL_OFFICE = "ประเภทสำนักงาน"        # office type: head office vs branch office
HEAD_OFFICE = "สำนักงานใหญ่"         # = a distinct legal operator
BRANCH_OFFICE = "สำนักสาขา"          # = an additional service point of an operator


def pull():
    """Fetch the FPO PICO registry into the datagoth cache via the shared puller (any IP)."""
    sys.argv = ["pull_datagoth.py", "--only", "fpo_pico"]
    import pull_datagoth
    return pull_datagoth.main()


def normalize():
    """Raw FPO registry CSV -> {canonical province_th: {operators, hq, branch}}. MEASURED counts."""
    with io.open(RAW, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    prov = {}
    n_unmapped = 0
    for r in rows:
        pv = (r.get(COL_PROV) or "").strip()
        if not pv:
            n_unmapped += 1
            continue
        c = canonical(pv)
        if not c or c in ("Other", ""):
            n_unmapped += 1
            continue
        d = prov.setdefault(c, {"operators": 0, "hq": 0, "branch": 0})
        d["operators"] += 1
        office = (r.get(COL_OFFICE) or "").strip()
        if office == HEAD_OFFICE:
            d["hq"] += 1
        elif office == BRANCH_OFFICE:
            d["branch"] += 1
    return rows, prov, n_unmapped


def build():
    rows, prov, n_unmapped = normalize()
    total = sum(d["operators"] for d in prov.values())
    total_hq = sum(d["hq"] for d in prov.values())
    total_branch = sum(d["branch"] for d in prov.values())
    # deterministic ordering: province key sorted, so the committed file is stable.
    provinces = {k: prov[k] for k in sorted(prov.keys())}
    meta = {
        "title": "MEASURED sub-scale competitor census — licensed PICO-finance operators by province",
        "generated_by": "pipeline/ingest_pico.py",
        "source": "FPO (Fiscal Policy Office, Ministry of Finance) PICO-finance licence registry, "
                  "catalog.fpo.go.th (open CKAN, no key). MEASURED — an official licence registry.",
        "what": "PICO-finance (พิโกไฟแนนซ์) = provincially-licensed small personal-loan operators "
                "(ceiling ฿50k PICO / ฿100k PICO-plus, secured incl. vehicle title). The sub-scale rivals "
                "AutoX faces that the big-4 title-lender census does NOT cover, and the operators most "
                "exposed to the Q1-2026 BoT responsible-lending registration deadline.",
        "provenance": "MEASURED — one row per licensed office (service province + licence no. + address). "
                      "Aggregated to per-province counts only; the source carries NO coordinates, so no "
                      "geometry is synthesized (this is a province registry, not a branch-coordinate census).",
        "unit": "count of licensed offices",
        "fields": {
            "operators": "MEASURED — total licensed PICO offices whose SERVICE province is this province.",
            "hq": "MEASURED — head offices (สำนักงานใหญ่) = distinct legal operators.",
            "branch": "MEASURED — branch offices (สำนักสาขา) = additional service points.",
        },
        "n_provinces": len(provinces),
        "n_offices_total": total,
        "n_hq_total": total_hq,
        "n_branch_total": total_branch,
        "n_rows_unmapped": n_unmapped,
        "gaps": [
            "Province-granular only — the FPO registry lists a service province + street address per office "
            "but no coordinates, so this cannot be joined to a district or a branch catchment. It complements "
            "(does not replace) the coordinate-based big-4 census.",
            "Snapshot of currently-LICENSED operators — informal / unlicensed lenders are outside any registry.",
        ],
    }
    return {"meta": meta, "provinces": provinces}


def run(mode):
    if mode == "pull":
        return pull()
    if not os.path.exists(RAW):
        if mode == "check":
            print("SKIP: source-data/datagoth/fpo_pico.csv absent (gitignored raw pull) — "
                  "run `python3 ingest_pico.py --pull` from a network-enabled run")
            return 3
        print("ERROR: raw registry absent — run `python3 ingest_pico.py --pull` first "
              "(source-data/datagoth/fpo_pico.csv)", file=sys.stderr)
        return 1
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if mode == "check":
        if not os.path.exists(OUT) or io.open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, ROOT)} (re-run: python3 pipeline/ingest_pico.py)")
            return 1
        m = obj["meta"]
        print(f"OK: pico_by_province.json reproduces ({m['n_offices_total']} offices, {m['n_provinces']} provinces)")
        return 0
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    m = obj["meta"]
    print(f"wrote {m['n_offices_total']} PICO offices across {m['n_provinces']} provinces "
          f"({m['n_hq_total']} HQ + {m['n_branch_total']} branch) -> source-data/pico_by_province.json")
    return 0


def main():
    ap = argparse.ArgumentParser(description="normalize the FPO PICO-finance licence registry into a per-province layer")
    ap.add_argument("--pull", action="store_true", help="fetch the raw registry via pull_datagoth (any IP)")
    ap.add_argument("--check", action="store_true", help="verify the normalized layer reproduces byte-exact")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try: stream.reconfigure(encoding="utf-8")
        except Exception: pass
    return run("pull" if args.pull else "check" if args.check else "build")


if __name__ == "__main__":
    sys.exit(main())
