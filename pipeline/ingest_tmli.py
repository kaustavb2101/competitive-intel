#!/usr/bin/env python3
"""
ingest_tmli.py — bridge MEASURED data.go.th province datasets into competitive-intel.

The competitive-intel sandbox is blocked from data.go.th / NSO / NESDC from its
foreign IP. The user's separate Thailand Macro Labor Intelligence (TMLI) platform
(`kaustavb2101/watcher`) already pulled these MEASURED datasets from a Thai network.
We vendored the needed raw files into source-data/tmli/ (see source-data/tmli/PROVENANCE.md).

This script is deterministic + network-free. It reads the vendored files, normalizes
province names to competitive-intel's canonical 77 Thai-name keys (the keys in
regionmap.REGION), and emits clean province-keyed MEASURED layers into source-data/:

  household_debt_by_province.json    debtToIncome, stressIndex, debtPerHousehold
  household_income_by_province.json  monthly income by occupation + avg (THB/month)
  unemployment_by_province.json      employed/unemployed/laborForce + unemployment rate
  gpp_by_province.json               GPP (million THB) + sector shares + hubType

Each output: {"meta": {...}, "provinces": {"<th-name>": {...measured fields...}}}.
A layer is skipped gracefully (with a warning) if its source file is missing.

NOT bridged (intentionally — existing layers are richer):
  - DLT vehicles: existing vehicles_by_province.json is vehicle STOCK (44.3M, with
    car/pickup/moto/ev breakdown); TMLI dlt-vehicles.json is vehicles PROCESSED (3.48M flow).
  - NSO employment: existing employment_by_province.json has formal/informal split;
    TMLI nso-unemployment.js is National-only. (TMLI LFS summary IS used, for unemployment rate.)

Run:
  python3 ingest_tmli.py            # write the clean layers into source-data/
  python3 ingest_tmli.py --check    # re-build, byte-compare against committed files; exit 1 on drift
"""
import argparse
import json
import os
import re
import sys

from regionmap import REGION

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(ROOT), "source-data")
TMLI = os.path.join(SRC, "tmli")

# ── province-name normalization ────────────────────────────────────────────────
# Canonical keys are the Thai province names in regionmap.REGION (the 77-province set
# the rest of the pipeline uses). TMLI debt/income/GPP are keyed by ENGLISH name;
# TMLI LFS is keyed by Thai name. We build an English->Thai map from the vendored
# provinces.js (THAI_PROVINCE_MAP) — it matches REGION exactly — then add a couple of
# spelling aliases for variants seen in the source files.
def _load_en2th():
    txt = open(os.path.join(TMLI, "provinces.js"), encoding="utf-8").read()
    m = re.search(r"THAI_PROVINCE_MAP\s*=\s*\{(.*?)\};", txt, re.S)
    if not m:
        raise SystemExit("ingest_tmli: cannot parse THAI_PROVINCE_MAP from provinces.js")
    pairs = re.findall(r"'([^']+)'\s*:\s*'([^']+)'", m.group(1))
    en2th = {en: th for th, en in pairs}
    # spelling / alias variants found in the TMLI English-keyed sources:
    en2th.setdefault("Phangnga", en2th["Phang Nga"])    # nso-ses income/debt spelling
    en2th["Bangkok Metropolis"] = en2th["Bangkok"]      # GPP alias row (identical values)
    en2th["Buriram"] = en2th["Buri Ram"]                # GPP alias row
    en2th["Sisaket"] = en2th["Si Sa Ket"]               # GPP alias row
    en2th["Phetchuri"] = en2th["Phetchaburi"]           # GPP alias row (typo in source)
    # sanity: every mapped Thai value must be a canonical key
    bad = sorted(v for v in en2th.values() if v not in REGION)
    if bad:
        raise SystemExit("ingest_tmli: en2th maps to non-canonical province(s): %s" % bad)
    return en2th


# Thai-name spelling variants seen in TMLI Thai-keyed sources (NSO LFS) -> canonical.
TH_ALIAS = {
    "สุราษฏร์ธานี": "สุราษฎร์ธานี",   # ฏ -> ฎ spelling variant in NSO data
}


def _canon_th(th):
    th = (th or "").strip()
    return TH_ALIAS.get(th, th)


def _dumps(obj):
    # deterministic: insertion key order, ensure_ascii=False, indent=2, trailing newline
    # (matches the convention of meta.json / crop_stress.json across the pipeline).
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def _round(x, n):
    return round(float(x), n)


# ── builders (each returns (filename, payload) or None if its source is missing) ──
def build_household_debt(en2th):
    """household_debt_by_province.json — from household-debt.js (the curated debt KB:
    NSO SES 2566 debtPerHousehold + BOT Q4/2024 debtToIncome & stressIndex)."""
    path = os.path.join(TMLI, "household-debt.js")
    if not os.path.exists(path):
        print("  SKIP household_debt: source household-debt.js missing")
        return None
    txt = open(path, encoding="utf-8").read()
    body = re.search(r"HOUSEHOLD_DEBT_RECORDS\s*=\s*\{(.*?)\n\};", txt, re.S).group(1)
    rows = re.findall(
        r'"([^"]+)":\s*\{\s*debtToIncome:\s*([0-9.]+),\s*stressIndex:\s*([0-9.]+),'
        r'\s*mobility:\s*([0-9.]+),\s*debtPerHousehold:\s*_NSO_DEBT\["[^"]+"\]\s*\|\|\s*([0-9]+)',
        body,
    )
    # debtPerHousehold uses `_NSO_DEBT[name] || <fallback>`; resolve the actual value
    # from the inline _NSO_DEBT object (it is the corrected SES table).
    nso_body = re.search(r"_NSO_DEBT\s*=\s*\{(.*?)\};", txt, re.S).group(1)
    nso = {k: int(v) for k, v in re.findall(r'"([^"]+)":\s*([0-9]+)', nso_body)}

    provinces = {}
    for en, dti, stress, mobility, fallback in rows:
        th = en2th.get(en)
        if not th:
            raise SystemExit("ingest_tmli household_debt: unmapped province %r" % en)
        debt = nso.get(en, int(fallback))
        provinces[_canon_th(th)] = {
            "debt_to_income": _round(dti, 2),       # BOT: debt as multiple of annual income
            "stress_index": _round(stress, 3),      # BOT: 0..1 financial-stress index
            "debt_per_household": debt,             # NSO SES: THB, measured
        }
    provinces = _sort(provinces)
    meta = {
        "source": "NSO SES 2566 (debt/household) + BOT Household Debt Regional Q4/2024 "
                  "(debt_to_income, stress_index), via data.go.th / TMLI",
        "provenance": "MEASURED. Vendored from kaustavb2101/watcher source-data/tmli/household-debt.js. "
                      "NSO SES 2566 (2023 CE); BOT Q4/2024.",
        "fields": {
            "debt_to_income": "household debt as a multiple of annual income (BOT regional)",
            "stress_index": "0..1 financial-stress index (BOT regional)",
            "debt_per_household": "average household debt, THB (NSO SES 2566, measured)",
        },
        "n_provinces": len(provinces),
    }
    return "household_debt_by_province.json", {"meta": meta, "provinces": provinces}


def build_household_income(en2th):
    """household_income_by_province.json — from nso-ses-income-2566.json (monthly income
    by occupation; THB/month). Adds a simple unweighted occupation average for convenience."""
    path = os.path.join(TMLI, "nso-ses-income-2566.json")
    if not os.path.exists(path):
        print("  SKIP household_income: source nso-ses-income-2566.json missing")
        return None
    raw = json.load(open(path, encoding="utf-8"))
    provinces = {}
    for en, occ in raw.items():
        th = en2th.get(en)
        if not th:
            raise SystemExit("ingest_tmli household_income: unmapped province %r" % en)
        vals = {k: int(v) for k, v in occ.items()}
        avg = round(sum(vals.values()) / len(vals)) if vals else 0
        rec = dict(sorted(vals.items()))
        rec["avg_monthly_income"] = avg
        provinces[_canon_th(th)] = rec
    provinces = _sort(provinces)
    meta = {
        "source": "NSO SES 2566 — monthly income by occupation (THB/month), via data.go.th / TMLI",
        "provenance": "MEASURED. Vendored from kaustavb2101/watcher source-data/tmli/"
                      "nso-ses-income-2566.json. NSO SES 2566 (2023 CE).",
        "fields": {
            "OfficeStaff/FactoryWorkers/Transport/SMEOwners/Agriculture":
                "average monthly income for that occupation, THB (NSO SES 2566)",
            "avg_monthly_income": "unweighted mean across the five occupations, THB (derived)",
        },
        "n_provinces": len(provinces),
    }
    return "household_income_by_province.json", {"meta": meta, "provinces": provinces}


def build_unemployment():
    """unemployment_by_province.json — from nso-lfs-provincial-summary.json (NSO Labour
    Force Survey; thousands of persons). Thai-keyed already."""
    path = os.path.join(TMLI, "nso-lfs-provincial-summary.json")
    if not os.path.exists(path):
        print("  SKIP unemployment: source nso-lfs-provincial-summary.json missing")
        return None
    raw = json.load(open(path, encoding="utf-8"))
    src_meta = raw.get("meta", {})
    provinces = {}
    for th, r in raw["provinces"].items():
        cth = _canon_th(th)
        if cth not in REGION:
            raise SystemExit("ingest_tmli unemployment: non-canonical province %r" % th)
        provinces[cth] = {
            "employed_k": _round(r.get("employed", 0), 1),
            "unemployed_k": _round(r.get("unemployed", 0), 1),
            "labor_force_k": _round(r.get("laborForce", 0), 1),
            "unemployment_rate": _round(r.get("unemploymentRate", 0), 2),
        }
    provinces = _sort(provinces)
    meta = {
        "source": "NSO Labour Force Survey — provincial summary, via data.go.th / TMLI",
        "provenance": "MEASURED. Vendored from kaustavb2101/watcher source-data/tmli/"
                      "nso-lfs-provincial-summary.json. NSO LFS %s (table %s)." % (
                          src_meta.get("reference_period", "latest quarter"),
                          src_meta.get("table", "?")),
        "unit": "*_k fields are thousands of persons (พันคน); unemployment_rate is percent",
        "n_provinces": len(provinces),
    }
    return "unemployment_by_province.json", {"meta": meta, "provinces": provinces}


def build_gpp(en2th):
    """gpp_by_province.json — from provincial-gpp.js (NESDC Provincial Accounts; GPP in
    million THB + sector shares + hubType). Dedups the alias rows by canonical key."""
    path = os.path.join(TMLI, "provincial-gpp.js")
    if not os.path.exists(path):
        print("  SKIP gpp: source provincial-gpp.js missing")
        return None
    txt = open(path, encoding="utf-8").read()
    rows = re.findall(
        r'"([^"]+)":\s*\{\s*gpp:\s*([0-9]+),\s*manufacturing:\s*([0-9.]+),'
        r'\s*agri:\s*([0-9.]+),\s*services:\s*([0-9.]+),\s*hubType:\s*\'([^\']+)\','
        r'\s*confidence:\s*([0-9.]+),\s*source:\s*\'([^\']+)\'',
        txt,
    )
    provinces = {}
    for en, gpp, manu, agri, svc, hub, conf, src in rows:
        th = en2th.get(en)
        if not th:
            raise SystemExit("ingest_tmli gpp: unmapped province %r" % en)
        cth = _canon_th(th)
        rec = {
            "gpp_million_thb": int(gpp),
            "manufacturing_share": _round(manu, 3),
            "agri_share": _round(agri, 3),
            "services_share": _round(svc, 3),
            "hub_type": hub,
            "confidence": _round(conf, 3),
            "source": src,
        }
        # alias rows (Bangkok Metropolis, Buriram, Sisaket, Phetchuri) carry identical
        # values; keep the first and assert any later row agrees.
        if cth in provinces and provinces[cth] != rec:
            raise SystemExit("ingest_tmli gpp: conflicting alias rows for %r" % cth)
        provinces[cth] = rec
    provinces = _sort(provinces)
    meta = {
        "source": "NESDC Provincial Accounts (GPP) — via data.go.th / TMLI",
        "provenance": "MIXED — NOT predominantly measured, despite the source file's own "
                      "'NESDC OFFICIAL DATA' framing. Vendored from kaustavb2101/watcher "
                      "source-data/tmli/provincial-gpp.js, whose own header/GPP_META confirms "
                      "only ONE row (Mukdahan, confidence 0.95, source 'CKAN-NESDC-2566', CKAN "
                      "resource ffabdf4f-b326-4d2d-8ede-a4514bf20339) was independently verified "
                      "against a real NESDC CKAN dataset. The other 76 provinces carry generic "
                      "source 'NESDC-2566', round-number GPP figures (multiples of 1,000-5,000 "
                      "THB million), and hand-assigned confidence 0.75-0.97 — i.e. a plausibility "
                      "knowledge base, NOT a per-province CKAN pull. Treat every row with "
                      "confidence < 0.95 / source != 'CKAN-NESDC-2566' as ESTIMATED, not measured. "
                      "Flagged during the 2026-07-02 audit cycle; see docs/DATA_REFRESH_LOG.md. Do "
                      "NOT surface this layer as MEASURED in the app until re-pulled per-province "
                      "from NESDC's CKAN resource on data.go.th.",
        "fields": {
            "gpp_million_thb": "total Gross Provincial Product, million THB (NESDC 2566)",
            "manufacturing_share/agri_share/services_share": "sector share of GPP, 0..1",
            "hub_type": "IND | AGRI | SVC | TOUR | MIX",
            "confidence": "0..1 data confidence per TMLI source (1.0 = CKAN-verified; only "
                          "Mukdahan actually reaches CKAN-verified status here)",
            "source": "per-row provenance tag from provincial-gpp.js — 'CKAN-NESDC-2566' "
                      "(verified) vs generic 'NESDC-2566' (unverified estimate)",
        },
        "n_provinces": len(provinces),
        "n_ckan_verified": sum(1 for r in provinces.values() if r.get("source") == "CKAN-NESDC-2566"),
    }
    return "gpp_by_province.json", {"meta": meta, "provinces": provinces}


def _sort(provinces):
    """Stable, deterministic ordering: by Thai province key."""
    return {k: provinces[k] for k in sorted(provinces)}


def build_all():
    en2th = _load_en2th()
    outputs = []
    for item in (
        build_household_debt(en2th),
        build_household_income(en2th),
        build_unemployment(),
        build_gpp(en2th),
    ):
        if item is not None:
            outputs.append(item)
    return outputs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-build and byte-compare against committed files; exit 1 on drift")
    args = ap.parse_args()

    if not os.path.isdir(TMLI):
        print("ingest_tmli: source-data/tmli/ not found — nothing to bridge")
        sys.exit(1)

    outputs = build_all()
    if not outputs:
        print("ingest_tmli: no source files present — nothing built")
        sys.exit(1)

    failed = False
    for fname, payload in outputs:
        out = os.path.join(SRC, fname)
        text = _dumps(payload)
        n = payload["meta"]["n_provinces"]
        if args.check:
            if not os.path.exists(out):
                print("CHECK FAIL: %s does not exist" % fname)
                failed = True
                continue
            existing = open(out, encoding="utf-8").read()
            if existing == text:
                print("CHECK OK: %s reproduces byte-for-byte (%d provinces)" % (fname, n))
            else:
                print("CHECK FAIL: %s differs from a fresh build" % fname)
                failed = True
        else:
            open(out, "w", encoding="utf-8").write(text)
            print("wrote %s (%d provinces)" % (fname, n))

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
