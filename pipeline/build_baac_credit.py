#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_baac_credit.py — per-province BAAC personal-credit penetration (portfolio risk, MEASURED).

Distils BAAC's (Bank for Agriculture and Agricultural Co-operatives — ธ.ก.ส.) own MIS report of
personal-credit customers + outstanding balance BY PROVINCE into a clean, canonical-77-province-keyed
layer. BAAC is Thailand's big agri/rural state lender; where its formal-credit reach is DEEP (many
customers, high outstanding) is, all else equal, where rural households already have a formal-credit
relationship — an INVERSE proxy for unmet title-loan demand. Read ALONGSIDE (never merged into) the
household-DTI lens (household_risk_by_province.json): DTI says how stretched households are, this says
how much of that need a state lender already serves, province by province.

INPUT  source-data/datagoth/baac_credit.xlsx — BAAC "สินเชื่อบุคคลรายพื้นที่" (personal credit by area).
       Single sheet, one title row + one header row + exactly 77 province data rows (then ~15 dataset-
       documentation rows that are excluded). Columns (selected BY POSITION — one debt header carries a
       brittle double-space): [0] ลำดับ serial · [1] ชื่อ สนจ. province · [2] general customers ·
       [3] general outstanding THB · [4] farmer customers · [5] farmer outstanding THB. Pulled by
       pull_datagoth.py (--only baac_credit) from data.go.th (dataset baac02_2567). The raw xlsx is
       gitignored + re-pullable; this builder's committed OUTPUT is the repo's source of truth.

OUTPUT platform/data/baac_credit.json — { meta, by_province{prov:{...}}, top_general, top_farmer, national }.
       The four raw fields (2 counts + 2 THB balances per province) are MEASURED straight reads; the
       derived sums/averages are arithmetic on measured numbers (still MEASURED, not modelled). No
       cross-province rank/index is computed here (would be ESTIMATED per repo convention).

PROVENANCE is stable + byte-exact: output is a pure function of the xlsx CONTENT (not the pull
timestamp). The fiscal vintage + download URL are pinned as constants below (BAAC accounting year
2567 = 1 Apr 2024–31 Mar 2025 CE — NOT calendar 2024/2025). Debt floats are rounded to whole THB.

CAVEAT (in meta): this is ONE state lender's own book (BAAC, agri/rural), not a census of all formal
credit — commercial banks and other SFIs are excluded, so "formal-credit penetration" here is a
BAAC-specific proxy, not total formal-credit coverage.

DETERMINISTIC + NETWORK-FREE. Carries --check; SKIP-passes (exit 3) when the gitignored xlsx is
absent (CI has no such pull committed), same convention as build_dbd_formation / build_pico_census.

  python3 build_baac_credit.py
  python3 build_baac_credit.py --check
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.regionmap import canonical, REGION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
XLSX_IN = os.path.join(ROOT, "source-data", "datagoth", "baac_credit.xlsx")
OUT = os.path.join(ROOT, "platform", "data", "baac_credit.json")

# Pinned to the pulled BAAC resource (data.go.th dataset baac02_2567). Constants — NOT read from the
# volatile pull manifest — so the output is byte-stable across re-pulls of the same fiscal year.
SNAPSHOT_URL = ("https://data.go.th/dataset/bd56215c-79d3-4f3b-9601-2e7f491813ab/resource/"
                "55789468-10b2-41ea-aee6-8d1d23e2ea4e/download/2.-67.xlsx")
VINTAGE = "BAAC FY2567 (1 Apr 2024 – 31 Mar 2025 CE)"
VINTAGE_BE = "2567"
DATASET_ID = "baac02_2567"


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def build():
    try:
        import pandas as pd  # noqa: F401  (checked here so a missing dep exits 3, not 1)
    except ImportError as e:
        # An absent optional dependency is an ENVIRONMENT gap, exactly like an absent input — not
        # data drift. Exiting 1 here made tests/run.sh print "baac_credit.json drifted from
        # baac_credit.xlsx" on any machine without pandas, which is a confident claim about data
        # made by a builder that never read any. Exit 3 is what the gate already understands as
        # "cannot check this here", and it keeps the failure honest about which kind it is.
        print("build_baac_credit.py: SKIP (%s — install pandas + openpyxl to check this layer)" % e,
              file=sys.stderr)
        sys.exit(3)
    import pandas as pd
    # header=1 skips the title row; nrows=77 stops before the ~15 documentation rows. Select value
    # columns BY POSITION — the general-debt header has a brittle double space inside it.
    df = pd.read_excel(XLSX_IN, sheet_name=0, header=1, nrows=77, engine="openpyxl")

    by_prov = {}
    unmapped = []
    nat = {"n_general": 0, "debt_general_thb": 0, "n_farmer": 0, "debt_farmer_thb": 0}
    for _, r in df.iterrows():
        raw = str(r.iloc[1]).strip()
        prov = canonical(raw)
        if prov not in REGION:
            unmapped.append(raw)
            continue
        n_gen = _int(r.iloc[2]); d_gen = _int(r.iloc[3])
        n_far = _int(r.iloc[4]); d_far = _int(r.iloc[5])
        n_tot = n_gen + n_far
        d_tot = d_gen + d_far
        by_prov[prov] = {
            "n_general": n_gen,
            "debt_general_thb": d_gen,
            "n_farmer": n_far,
            "debt_farmer_thb": d_far,
            "n_total": n_tot,
            "debt_total_thb": d_tot,
            # arithmetic on measured numbers — still MEASURED, guarded against divide-by-zero
            "avg_debt_general_thb": int(round(d_gen / n_gen)) if n_gen else 0,
            "avg_debt_farmer_thb": int(round(d_far / n_far)) if n_far else 0,
        }
        for k in nat:
            nat[k] += {"n_general": n_gen, "debt_general_thb": d_gen,
                       "n_farmer": n_far, "debt_farmer_thb": d_far}[k]

    by_province = {p: by_prov[p] for p in sorted(by_prov)}
    nat["n_total"] = nat["n_general"] + nat["n_farmer"]
    nat["debt_total_thb"] = nat["debt_general_thb"] + nat["debt_farmer_thb"]
    missing = sorted(set(REGION.keys()) - set(by_prov.keys()))

    top_general = sorted(((p, v["n_general"], v["debt_general_thb"]) for p, v in by_province.items()),
                         key=lambda kv: (-kv[1], kv[0]))[:15]
    top_farmer = sorted(((p, v["n_farmer"], v["debt_farmer_thb"]) for p, v in by_province.items()),
                        key=lambda kv: (-kv[1], kv[0]))[:15]

    meta = {
        "generated_by": "pipeline/build_baac_credit.py",
        "label": ("MEASURED per-province BAAC (ธ.ก.ส.) personal-credit customers + outstanding balance, "
                  "split general vs farmer segment. A rural formal-credit-penetration signal: where BAAC's "
                  "reach is deep, formal credit already serves the household base — read as an INVERSE proxy "
                  "for unmet title-loan demand, ALONGSIDE the household-DTI lens, not merged into it."),
        "source": ("MEASURED — BAAC MIS report 'สินเชื่อบุคคลรายพื้นที่' (personal credit by provincial "
                   "office), via data.go.th dataset %s. Direct read of BAAC's own customer + outstanding-"
                   "balance figures per provincial office; tallied to the canonical 77 provinces." % DATASET_ID),
        "provenance": "measured (state-bank MIS report, read straight; derived sums/averages are arithmetic on measured values)",
        "source_url": SNAPSHOT_URL,
        "dataset_id": DATASET_ID,
        "vintage": VINTAGE,
        "vintage_be": VINTAGE_BE,
        "n_provinces_present": len(by_prov),
        "n_provinces_missing": len(missing),
        "national": nat,
        "objective": ("Objective #1 (portfolio risk): formal-credit penetration is the inverse of unmet "
                      "borrowing need — provinces where BAAC's formal reach is THIN, at a given household-DTI "
                      "level, are where title-loan demand is least already served."),
        "gaps": [
            "BAAC is ONE state lender (agri/rural focus). This is its OWN book, NOT a census of all formal "
            "credit — commercial banks and other SFIs are excluded — so 'formal-credit penetration' here is a "
            "BAAC-specific proxy, not total formal-credit coverage.",
            "Outstanding BALANCE is a stock at the fiscal-year close (%s), not new lending flow." % VINTAGE,
            "'general' (บุคคลทั่วไป) vs 'farmer' (เกษตรกร) is BAAC's own customer classification; the farmer "
            "segment dominates balances in agri provinces and is the more comparable rural-household read.",
            "Keyed by BAAC provincial office (ชื่อ สนจ.), which maps 1:1 to the canonical 77 provinces with "
            "zero renames; %d province(s) unmapped: %s." % (len(unmapped), unmapped or "none"),
        ],
    }
    return {"meta": meta, "by_province": by_province, "missing_provinces": missing,
            "top_general": top_general, "top_farmer": top_farmer}


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8")
        except Exception: pass

    if not os.path.exists(XLSX_IN):
        if args.check:
            print("build_baac_credit.py --check: SKIP (source-data/datagoth/baac_credit.xlsx absent — "
                  "Thai-IP pull_datagoth input, not committed)")
            sys.exit(3)
        sys.exit("baac_credit.xlsx missing — run: python3 pull_datagoth.py --only baac_credit")

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_baac_credit.py --check: SKIP (baac_credit.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_baac_credit.py --check: baac_credit.json drifted — run "
                     "python3 pipeline/build_baac_credit.py")
        print("build_baac_credit.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]; nat = m["national"]
    print("wrote %s (%d provinces; %s)" % (OUT, m["n_provinces_present"], m["vintage"]))
    print("  national: general %s cust / ฿%.1fbn · farmer %s cust / ฿%.1fbn"
          % (f"{nat['n_general']:,}", nat["debt_general_thb"] / 1e9,
             f"{nat['n_farmer']:,}", nat["debt_farmer_thb"] / 1e9))
    print("  top farmer-credit provinces: %s"
          % ", ".join("%s=%d" % (p, n) for p, n, _ in obj["top_farmer"][:6]))
    if obj["missing_provinces"]:
        print("  missing provinces: %s" % ", ".join(obj["missing_provinces"]))


if __name__ == "__main__":
    main()
