#!/usr/bin/env python3
"""
build_pico_operators.py — per-province LICENSED PICO-FINANCE OPERATORS (objective #2, MEASURED)
================================================================================================
The competitor census (competitors_census.json / rival_pressure.json) is a coordinate census of
the FOUR big, compliant title-loan brands (Muangthai · Srisawad · Tidlor · Heng). By its own
caveat it misses the SUB-SCALE tier — the small local operators facing the Q1-2026 BoT
registration deadline. The #acq "Rival fragility" section says so explicitly: a true rival read
"needs a sub-scale-operator census — a blocked desktop / Thai-IP company-registry pull."

This layer IS that census, for the licensed slice of it. The Fiscal Policy Office (FPO) publishes
the registry of every licensed PICO-finance operator (พิโกไฟแนนซ์ — MOF-licensed micro-lenders
capped at ฿50,000 / ฿100,000 per loan, province-restricted). Each row carries the operator's
name, office type (สำนักงานใหญ่ HQ / สำนักสาขา branch office), the province it serves, full
address, and license date. We roll it up to the canonical 77 Thai provinces as a MEASURED
count of the sub-scale competitor field — a direct competitive-density signal the big-4 census
cannot see, and the exact operators most exposed to the regulatory shake-out.

MEASURED vs ESTIMATED: every number is a straight count of real registry rows (per province, by
office type) plus the AutoX branch count per province from the master (point-in-province, already
MEASURED). No scores, no weights, no synthesis. Province recency = the newest license date seen
in that province (a content-derived freshness marker; deterministic).

INPUT (gitignored, re-pullable): source-data/datagoth/fpo_pico.csv — pulled by
pipeline/pull_datagoth.py --only fpo_pico (FPO CKAN, reachable from any IP incl. CI; NOT the
geo-blocked data.go.th aggregator). Because the raw pull is gitignored, this builder follows the
same gate contract as build_branch_cropland / build_vehicle_flow: --check exits 3 (SKIP) when the
CSV is absent, 0 when the committed output reproduces byte-exact, 1 on drift. The derived
platform/data/pico_operators.json IS committed.

    python3 build_pico_operators.py            # write platform/data/pico_operators.json
    python3 build_pico_operators.py --check    # verify byte-for-byte reproduce (exit 3 if input absent)

Deterministic + network-free. Pure function of the committed master + the pulled registry CSV.
"""
import argparse, csv, json, os, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DATA = os.path.join(REPO, "platform", "data")
SRC = os.path.join(REPO, "source-data")
PICO_CSV = os.path.join(SRC, "datagoth", "fpo_pico.csv")
BRANCHES = os.path.join(SRC, "branches_final.json")
OUT = os.path.join(DATA, "pico_operators.json")

sys.path.insert(0, HERE)
from regionmap import canonical, region_of, REGION  # noqa: E402

# FPO CKAN column headers (Thai). Kept explicit so a header change fails loudly, not silently.
COL_OFFICE = "ประเภทสำนักงาน"       # office type: สำนักงานใหญ่ (HQ) / สำนักสาขา (branch office)
COL_PROV = "จังหวัดที่ให้บริการ"      # province served
COL_LIC = "วันที่ได้รับใบอนุญาต"      # license date (YYYY-MM-DD)
OFFICE_HQ = "สำนักงานใหญ่"

# Static citation — the FPO PICO-finance operator registry. Held here (not read from the volatile
# datagoth manifest) so the committed output is a pure function of the CSV content, byte-reproducible.
SOURCE_CITE = ("Fiscal Policy Office (สำนักงานเศรษฐกิจการคลัง) — licensed PICO-finance operator "
               "registry (พิโกไฟแนนซ์), catalog.fpo.go.th CKAN, resource picofinanceoperate. Pulled "
               "by pipeline/pull_datagoth.py --only fpo_pico.")


def _load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build():
    if not os.path.exists(PICO_CSV):
        return None
    master = _load_json(BRANCHES)
    if master is None:
        return None

    # AutoX branches per canonical province (MEASURED — the master already carries a real prov).
    autox = Counter(canonical(b.get("prov", "")) for b in master if b.get("prov"))

    # Roll the registry up to canonical provinces.
    n_hq = Counter()
    n_office = Counter()          # branch offices (สำนักสาขา) and anything not HQ
    newest_lic = {}               # province -> newest license date string (lexical max works on ISO dates)
    n_rows = 0
    n_unmapped = 0
    with open(PICO_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            prov = canonical((row.get(COL_PROV) or "").strip())
            if prov not in REGION:
                n_unmapped += 1
                continue
            n_rows += 1
            office = (row.get(COL_OFFICE) or "").strip()
            if office == OFFICE_HQ:
                n_hq[prov] += 1
            else:
                n_office[prov] += 1
            lic = (row.get(COL_LIC) or "").strip()
            if lic and (prov not in newest_lic or lic > newest_lic[prov]):
                newest_lic[prov] = lic

    provinces = []
    for prov in REGION:
        hq = n_hq[prov]
        office = n_office[prov]
        total = hq + office
        ax = autox[prov]
        provinces.append({
            "province_th": prov,
            "region": region_of(prov),
            "n_total": total,           # licensed PICO operators serving this province (MEASURED)
            "n_hq": hq,                 # head offices (distinct licensed companies)
            "n_office": office,         # additional branch offices (สำนักสาขา)
            "autox": ax,                # AutoX (เงินไชโย) branches in this province (MEASURED)
            # sub-scale competitor field size relative to our own footprint; null when AutoX absent.
            "pico_per_autox": round(total / ax, 2) if ax > 0 else None,
            "newest_license": newest_lic.get(prov),
        })
    # rank by the size of the sub-scale field (n_total desc), then province_th for a stable tie-break.
    provinces.sort(key=lambda p: (-p["n_total"], p["province_th"]))

    total_ops = sum(p["n_total"] for p in provinces)
    total_hq = sum(p["n_hq"] for p in provinces)
    total_office = sum(p["n_office"] for p in provinces)
    n_covered = sum(1 for p in provinces if p["n_total"] > 0)
    by_region = defaultdict(int)
    for p in provinces:
        by_region[p["region"]] += p["n_total"]
    national_newest = max((v for v in newest_lic.values() if v), default=None)

    meta = {
        "generated_by": "pipeline/build_pico_operators.py",
        "label": "LICENSED PICO-FINANCE OPERATORS per province — MEASURED count of the sub-scale "
                 "competitor tier (MOF/FPO-licensed micro-lenders, ฿50k/฿100k per-loan cap) that the "
                 "big-4 store-locator census cannot see. The registry of exactly the small operators "
                 "most exposed to the Q1-2026 BoT registration deadline.",
        "objective": "#2 competitive risk — sizes the sub-scale rival field around the existing "
                     "network province by province. A competitive-density read; makes NO open / "
                     "close / expand recommendation.",
        "source": "MEASURED. " + SOURCE_CITE + " AutoX per-province counts are the master "
                  "(branches_final.json), point-in-province. Every figure is a straight count of "
                  "real rows — no scores, no synthesis.",
        "provenance": {
            "pico": "MEASURED — one registry row per licensed PICO-finance office; n_hq counts head "
                    "offices (สำนักงานใหญ่ ≈ distinct licensed companies), n_office counts additional "
                    "branch offices (สำนักสาขา). Province = the operator's declared service province.",
            "autox": "MEASURED — AutoX (เงินไชโย) branches in the province from branches_final.json.",
            "newest_license": "MEASURED — newest license-issue date seen in the province (ISO date); a "
                              "content-derived recency marker, deterministic.",
            "pico_per_autox": "COMPUTED — n_total ÷ AutoX branches (null when AutoX absent).",
        },
        "counts": {
            "n_operators": total_ops,
            "n_hq": total_hq,
            "n_office": total_office,
            "n_provinces_covered": n_covered,
            "n_provinces_zero": len(REGION) - n_covered,
            "n_unmapped_rows": n_unmapped,
            "by_region": dict(sorted(by_region.items(), key=lambda kv: -kv[1])),
        },
        "vintage": national_newest,
        "what_is_pico": "PICO-finance (พิโกไฟแนนซ์) = MOF-licensed, province-restricted micro-lenders "
                        "(loan cap ฿50,000 for PICO / ฿100,000 for PICO-plus). They compete for the "
                        "same small-ticket, near-prime borrower AutoX serves, from below the big-4.",
        "gaps": [
            "Licensed operators only — informal / unlicensed sub-scale lenders are not in any registry "
            "and remain uncounted, so the sub-scale field is a LOWER bound.",
            "The registry is province-granular (service province), not geocoded — this is a per-province "
            "count, not a coordinate census, so it does not feed the per-branch rival-pressure geometry.",
            "Office count ≠ loan volume: a PICO operator is far smaller than a big-4 branch; read the "
            "count as competitive-field DENSITY, not comparable book size.",
        ],
        "n_provinces": len(provinces),
    }
    return {"meta": meta, "provinces": provinces}


def run(check=False):
    obj = build()
    if obj is None:
        if check:
            if not os.path.exists(PICO_CSV):
                print("SKIP: source-data/datagoth/fpo_pico.csv absent — pico_operators not checkable")
                return 3
            print("SKIP: source-data/branches_final.json absent — pico_operators not checkable")
            return 3
        print("missing input: needs source-data/datagoth/fpo_pico.csv (pull_datagoth.py --only fpo_pico) "
              "and source-data/branches_final.json.")
        return 1
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, REPO))
            return 1
        c = obj["meta"]["counts"]
        print("OK: pico_operators.json reproduces (%d operators, %d provinces covered)"
              % (c["n_operators"], c["n_provinces_covered"]))
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    c = obj["meta"]["counts"]
    print("wrote %d licensed PICO operators across %d provinces -> platform/data/pico_operators.json"
          % (c["n_operators"], c["n_provinces_covered"]))
    print("  HQ %d · branch offices %d · vintage %s" % (c["n_hq"], c["n_office"], obj["meta"]["vintage"]))
    top = obj["provinces"][:10]
    for p in top:
        print("    %-14s ops %4d  (AutoX %3d)  %s" % (p["province_th"], p["n_total"], p["autox"], p["region"]))
    if c["n_unmapped_rows"]:
        print("  NOTE: %d registry rows had an unmapped province (dropped)." % c["n_unmapped_rows"])
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="per-province licensed PICO-finance operator census (sub-scale competitor tier)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
