#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_farm_household.py — the MEASURED Thai farm-household cash P&L (objective #1).

  in : source-data/oae_household/*.csv   MEASURED — OAE socio-economic survey, 5 crop years
  out: platform/data/farm_household.json  (--check: byte-exact reproduce)

  python3 build_farm_household.py --pull    # refresh the CSVs from catalog.oae.go.th
  python3 build_farm_household.py           # CSVs -> platform/data/farm_household.json
  python3 build_farm_household.py --check   # byte-exact reproduce (gate)

WHY THIS MATTERS MORE THAN IT LOOKS. This product tells a crop-price story: a price falls, farm
income falls, the farm book deteriorates. Every link in that chain was modelled from planted area
and price moves, with no measured anchor for the household underneath it. OAE surveys that household
directly, and the survey says something the model could not:

    NON-FARM cash income is roughly HALF of a Thai farm household's cash income.

So a crop-price shock does not hit a farm borrower's whole income — it hits the farm half, against a
non-farm half (wages, remittances, off-season work) that a crop price does not touch. That is a
material correction to how hard any price move should be read, and it is measured, not assumed.

The survey is NATIONAL, not per-province — it is a sample survey, and OAE publishes it as one set of
national means. It is therefore a BACKDROP and a sanity check on the per-province modelled income
numbers, never a per-province input. Stated in meta so nothing downstream mistakes it for geography.

Deterministic + network-free by default; --pull is the only network path. Crop years are the
survey's own labels (2562/63 .. 2566/67) folded to CE for display, never a wall clock.
"""
import argparse, csv, io, json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data", "oae_household")
OUT = os.path.join(ROOT, "platform", "data", "farm_household.json")
BE_OFFSET = 543
UA = {"User-Agent": "Mozilla/5.0 (compatible; autox-credit-intel/1.0)"}
D = "https://catalog.oae.go.th/dataset/eb9e456c-875a-44ab-ad03-0ef5804d0d80/resource"
FILES = {
    "oae_basic.csv":   D + "/14613393-94a5-4ae7-b341-f88d11aa71d8/download/untitled.csv",
    "oae_income.csv":  D + "/e15d0d06-0cff-4168-888e-bc280720827f/download/untitled.csv",
    "oae_expense.csv": D + "/3a1f92e8-b357-4e82-9e12-531bdd04db08/download/expenses.csv",
    "oae_netcash.csv": D + "/41750602-f923-416b-9565-5d3447be993f/download/untitled.csv",
}

# Thai survey line -> (english key, group). Matched on the `subcatagory` + `list` pair, because the
# same word ("สาขาพืช" = crop branch) appears on BOTH the income and expense sides and keying on it
# alone would silently collapse revenue into cost.
INCOME = {
    ("รายได้เงินสดจากการเกษตร", "สาขาพืช"): ("farm_crops", "farm"),
    ("รายได้เงินสดจากการเกษตร", "สาขาสัตว์"): ("farm_livestock", "farm"),
    ("รายได้เงินสดจากการเกษตร", "อื่น ๆ"): ("farm_other", "farm"),
    ("รายได้เงินสดนอกภาคเกษตร", ""): ("nonfarm", "nonfarm"),
}
EXPENSE = {
    ("รายจ่ายเงินสดทางการเกษตร", "สาขาพืช"): ("farm_crops", "farm"),
    ("รายจ่ายเงินสดทางการเกษตร", "สาขาสัตว์"): ("farm_livestock", "farm"),
    ("รายจ่ายเงินสดทางการเกษตร", "อื่นๆ"): ("farm_other", "farm"),
    ("รายจ่ายเงินสดนอกการเกษตร", "การบริโภค"): ("living_food", "household"),
    ("รายจ่ายเงินสดนอกการเกษตร", "การอุปโภค และอื่นๆ"): ("living_other", "household"),
}
BASIC = {
    "อายุเฉลี่ยของหัวหน้าครัวเรือน": ("head_age_years", "years"),
    "ขนาดครัวเรือน": ("household_size", "people"),
    "จำนวนแรงงานอายุ 15–64 ปี": ("workers_15_64", "people"),
    "เนื้อที่ถือครอง": ("landholding_rai", "rai"),
}


def pull():
    os.makedirs(SRC, exist_ok=True)
    for name, url in sorted(FILES.items()):
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
            b = r.read()
        with open(os.path.join(SRC, name), "wb") as f:
            f.write(b)
        print("pulled %-18s %6d B" % (name, len(b)))


def rows(name):
    p = os.path.join(SRC, name)
    if not os.path.exists(p):
        return []
    raw = io.open(p, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "cp874"):
        try:
            return list(csv.DictReader(io.StringIO(raw.decode(enc))))
        except UnicodeDecodeError:
            continue
    return []


def _f(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def build():
    inc, exp, bas, net = (rows(n) for n in
                          ("oae_income.csv", "oae_expense.csv", "oae_basic.csv", "oae_netcash.csv"))
    if not inc or not exp:
        return None
    years = sorted({r["year"] for r in inc if r.get("year")})

    out = []
    for y in years:
        def collect(src, table):
            got = {}
            for r in src:
                if r.get("year") != y:
                    continue
                k = table.get(((r.get("subcatagory") or "").strip(), (r.get("list") or "").strip()))
                v = _f(r.get("value"))
                if k and v is not None:
                    got[k[0]] = v
            return got

        i, e = collect(inc, INCOME), collect(exp, EXPENSE)
        b = {}
        for r in bas:
            if r.get("year") != y:
                continue
            k = BASIC.get((r.get("list") or "").strip())
            v = _f(r.get("value"))
            if k and v is not None:
                b[k[0]] = v
        nc = next((_f(r.get("value")) for r in net if r.get("year") == y), None)

        farm_in = sum(i.get(k, 0) for k in ("farm_crops", "farm_livestock", "farm_other"))
        nonfarm_in = i.get("nonfarm", 0)
        farm_ex = sum(e.get(k, 0) for k in ("farm_crops", "farm_livestock", "farm_other"))
        living = sum(e.get(k, 0) for k in ("living_food", "living_other"))
        total_in, total_ex = farm_in + nonfarm_in, farm_ex + living
        out.append({
            "crop_year": y,
            "year_ce": int(y.split("/")[0]) - BE_OFFSET,
            "income": dict(i, farm_total=round(farm_in, 2), total=round(total_in, 2)),
            "expense": dict(e, farm_total=round(farm_ex, 2), living_total=round(living, 2),
                            total=round(total_ex, 2)),
            "net_farm_cash_income": nc,
            "net_cash": round(total_in - total_ex, 2),
            "net_cash_monthly": round((total_in - total_ex) / 12.0, 2),
            # The headline ratio. A crop-price shock reaches only this share of household cash.
            "farm_share_of_income_pct": round(farm_in / total_in * 100, 1) if total_in else None,
            "nonfarm_share_of_income_pct": round(nonfarm_in / total_in * 100, 1) if total_in else None,
            "household": b,
        })

    latest = out[-1]
    first = out[0]
    return {
        "meta": {
            "title": "MEASURED Thai farm-household cash P&L (OAE socio-economic survey)",
            "generated_by": "pipeline/build_farm_household.py",
            "source": "OAE catalog.oae.go.th package dataoae2104 "
                      "(ข้อมูลภาวะเศรษฐกิจสังคมครัวเรือนและแรงงานเกษตร) — survey year runs "
                      "1 May to 30 April.",
            "label": "MEASURED — a sample SURVEY of farm households, published as NATIONAL means. "
                     "Baht per household per year unless stated.",
            "scope_warning": "NATIONAL ONLY. OAE publishes one set of national means, not province "
                             "figures, so this is a BACKDROP and a sanity check on the modelled "
                             "per-province farm income — never a per-province input. Nothing "
                             "downstream should join it to geography.",
            "headline": "Non-farm cash income is %s%% of a Thai farm household's cash income (%s). "
                        "A crop-price move therefore reaches only about the farm half of the "
                        "household's cash — wages, remittances and off-season work are untouched "
                        "by it. Read every price shock in this product against that."
                        % (latest["nonfarm_share_of_income_pct"], latest["crop_year"]),
            "crop_years": [r["crop_year"] for r in out],
            "span": "%s..%s" % (first["crop_year"], latest["crop_year"]),
            "not_covered": "Debt and assets are in the same OAE package but only as PDF, so they "
                           "are NOT in this layer. Household debt here would be the natural "
                           "cross-check on the tape's farm book and is the obvious next pull.",
        },
        "latest": latest,
        "years": out,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pull", action="store_true", help="refresh the CSVs from catalog.oae.go.th")
    ap.add_argument("--check", action="store_true", help="verify byte-exact reproduce")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if args.pull:
        pull()
        if not args.check:
            return

    doc = build()
    if doc is None:
        print("build_farm_household.py: SKIP (source-data/oae_household/*.csv absent)")
        sys.exit(3)
    payload = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_farm_household.py --check: drifted — re-run the builder.")
        print("build_farm_household.py --check: OK (byte-exact)")
        return
    # newline="\n": the Windows default writes CRLF, inflating the byte size provenance censuses.
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    L = doc["latest"]
    print("wrote %s (%d crop years, %s)" % (OUT, len(doc["years"]), doc["meta"]["span"]))
    print("  %s: farm income ฿%s + non-farm ฿%s = ฿%s"
          % (L["crop_year"], format(int(L["income"]["farm_total"]), ","),
             format(int(L["income"]["nonfarm"]), ","), format(int(L["income"]["total"]), ",")))
    print("  expense ฿%s  ->  net cash ฿%s/yr (฿%s/month)"
          % (format(int(L["expense"]["total"]), ","), format(int(L["net_cash"]), ","),
             format(int(L["net_cash_monthly"]), ",")))
    print("  farm share of income: %s%%   (non-farm %s%%)"
          % (L["farm_share_of_income_pct"], L["nonfarm_share_of_income_pct"]))


if __name__ == "__main__":
    main()
