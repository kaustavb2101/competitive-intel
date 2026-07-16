#!/usr/bin/env python3
"""
build_regions.py — province -> region rollup engine for the numbers-first Data Book (platform/data.html).

Reads the committed, network-free inputs:
    platform/data/provinces/<slug>.json   (gov.*, districts FeatureCollection, region, branches)
    platform/data/provinces/index.json     (flat 77-row master; slug/th/en/region)
    platform/data/competitors_census.json   (16,503 measured rival branches; prov == province_th)

and writes:
    platform/data/regions.json              (national super-row + 5 region objects + per-province rows)

ROLLUP MATH (the whole point — a region is NOT an average of province ratios):
  * EXTENSIVE counts SUM: branches, districts, factories, workers, vehicles.*, employment.informal/formal,
    unemployment.*_k, rival_branches (census), contested_districts.
  * INTENSIVE shares/rates are RECOMPUTED as ratio-of-sums (Σnum / Σden), never averaged:
    rivals_per_branch, informal_share, moto/pickup/car/ev share, unemployment_rate, collateral_per_branch.
  * TRUE per-capita figures are labor_force_k-WEIGHTED averages: avg_monthly_income + per-occupation incomes.
    "Income vs national" uses the COMPUTED labor-weighted national mean as the baseline (internally consistent
    with every other tile), NOT the editorial facts.natl_avg constant.
  * NULL-SKIP: Bangkok has informal=formal=null -> it drops out of the informal_share numerator AND denominator
    only, while still contributing to every sum and to income/labor weights. Never coerce null to 0.

Regions are grouped on the raw 5-value region field {Central&BKK, East, Isan, North, South}; 'Isan' is
displayed as 'Northeast (Isan)' but all logic keys on the raw string. (There is no 'Northeast'/'West' in the data.)

Determinism: pure integer sums + single divisions + fixed rounding; incomes weighted via integer-scaled labor
(labor_force_k*10) so the result byte-reproduces across CPython 3.11/3.14. run()/--check mirror build_province.py.
"""
import os, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DATA = os.path.join(REPO, "platform", "data")
PROV = os.path.join(DATA, "provinces")
OUT = os.path.join(DATA, "regions.json")

# raw region string -> display label (logic always keys on the raw string)
REGION_LABEL = {
    "Central&BKK": "Central & Bangkok",
    "East": "East",
    "Isan": "Northeast (Isan)",
    "North": "North",
    "South": "South",
}
# stable display order (population/branch weight, biggest first-ish; deterministic regardless)
REGION_ORDER = ["Central&BKK", "Isan", "North", "South", "East"]

OCC_KEYS = ["Agriculture", "FactoryWorkers", "OfficeStaff", "SMEOwners", "Transport"]


def _num(x):
    return x if isinstance(x, (int, float)) else None


def load_provinces():
    """Return list of per-province dicts with exactly the fields the rollup needs (deterministic order)."""
    idx = json.load(open(os.path.join(PROV, "index.json"), encoding="utf-8"))
    out = []
    for row in sorted(idx, key=lambda r: r["slug"]):
        slug = row["slug"]
        d = json.load(open(os.path.join(PROV, slug + ".json"), encoding="utf-8"))
        gov = d.get("gov", {}) or {}
        veh = gov.get("vehicles", {}) or {}
        emp = gov.get("employment", {}) or {}
        un = gov.get("unemployment", {}) or {}
        inc = gov.get("income", {}) or {}
        feats = (d.get("districts") or {}).get("features") or []
        contested = 0
        for ft in feats:
            p = ft.get("properties", {}) or {}
            c = p.get("competitors") or 0
            b = p.get("branches") or 0
            if c > b:
                contested += 1
        out.append({
            "slug": slug,
            "th": d.get("province_th", row.get("th", "")),
            "en": d.get("province_en", row.get("en", "")),
            "region": d.get("region", row.get("region", "")),
            "branches": len(d.get("branches") or []),
            "districts": len(feats),
            "contested_districts": contested,
            "factories": _num(gov.get("factories")) or 0,
            "workers": _num(gov.get("workers")) or 0,
            "veh_total": _num(veh.get("total")) or 0,
            "veh_car": _num(veh.get("car")) or 0,
            "veh_pickup": _num(veh.get("pickup")) or 0,
            "veh_moto": _num(veh.get("moto")) or 0,
            "veh_ev": _num(veh.get("ev")) or 0,
            "informal": _num(emp.get("informal")),   # may be None (Bangkok)
            "formal": _num(emp.get("formal")),        # may be None (Bangkok)
            "labor_force_k": _num(un.get("labor_force_k")) or 0,
            "employed_k": _num(un.get("employed_k")) or 0,
            "unemployed_k": _num(un.get("unemployed_k")) or 0,
            "avg_income": _num(inc.get("avg_monthly_income")),
            "occ_income": {k: _num(inc.get(k)) for k in OCC_KEYS},
        })
    return out


def rival_counts_by_province():
    """Count measured census rival branches per province (census.prov == province_th)."""
    cen = json.load(open(os.path.join(DATA, "competitors_census.json"), encoding="utf-8"))
    counts = {}
    for it in cen.get("items", []):
        p = it.get("prov")
        if p:
            counts[p] = counts.get(p, 0) + 1
    return counts


# --- deterministic aggregation helpers -------------------------------------------------------------
def pct1(num, den):
    return round(100.0 * num / den, 1) if den else None


def ratio2(num, den):
    return round(num / den, 2) if den else None


def wavg_income(rows, get):
    """labor_force_k-weighted mean income (integer THB/month). Integer-scaled weights => version-stable."""
    num = 0
    den = 0
    for r in rows:
        v = get(r)
        lf = r["labor_force_k"]
        if v is None or not lf:
            continue
        w = int(round(lf * 10))       # 0.1-thousand precision, exact integer
        num += int(round(v)) * w
        den += w
    return int(round(num / den)) if den else None


def aggregate(rows, national_income_base):
    """Roll a set of province rows into one aggregate object. national_income_base = labor-weighted national means."""
    S = lambda k: sum(r[k] for r in rows)
    branches = S("branches")
    veh_total = S("veh_total")
    rivals = S("rivals")
    # informal share: ratio-of-sums, skipping provinces with null informal/formal
    inf_num = sum(r["informal"] for r in rows if r["informal"] is not None and r["formal"] is not None)
    inf_den = sum((r["informal"] + r["formal"]) for r in rows if r["informal"] is not None and r["formal"] is not None)
    labor_k = S("labor_force_k")
    avg_income = wavg_income(rows, lambda r: r["avg_income"])
    occ = {k: wavg_income(rows, lambda r, kk=k: r["occ_income"].get(kk)) for k in OCC_KEYS}
    natl_avg = national_income_base["avg_income"]
    natl_occ = national_income_base["occ"]
    agg = {
        # extensive counts (sums)
        "branches": branches,
        "districts": S("districts"),
        "contested_districts": S("contested_districts"),
        "rival_branches": rivals,
        "factories": S("factories"),
        "workers": S("workers"),
        "vehicles": {"total": veh_total, "car": S("veh_car"), "pickup": S("veh_pickup"),
                     "moto": S("veh_moto"), "ev": S("veh_ev")},
        "informal": inf_num or None,
        "formal": (inf_den - inf_num) if inf_den else None,
        "labor_force_k": round(labor_k, 1),
        "employed_k": round(S("employed_k"), 1),
        "unemployed_k": round(S("unemployed_k"), 1),
        # intensive ratios (recomputed ratio-of-sums)
        "rivals_per_branch": ratio2(rivals, branches),
        "informal_share_pct": pct1(inf_num, inf_den),
        "moto_share_pct": pct1(S("veh_moto"), veh_total),
        "pickup_share_pct": pct1(S("veh_pickup"), veh_total),
        "car_share_pct": pct1(S("veh_car"), veh_total),
        "ev_share_pct": pct1(S("veh_ev"), veh_total),
        "unemployment_rate_pct": pct1(S("unemployed_k"), labor_k),
        "collateral_per_branch": ratio2(S("veh_moto") + S("veh_pickup"), branches),
        # per-capita (labor-weighted) + vs computed national baseline
        "avg_income": avg_income,
        "avg_income_vs_national": round(avg_income / natl_avg, 3) if (avg_income and natl_avg) else None,
        "occ_income": occ,
        "occ_income_vs_national": {k: (round(occ[k] / natl_occ[k], 3) if (occ.get(k) and natl_occ.get(k)) else None)
                                   for k in OCC_KEYS},
    }
    return agg


def build():
    provs = load_provinces()
    rivals = rival_counts_by_province()
    for r in provs:
        r["rivals"] = rivals.get(r["th"], 0)

    # national labor-weighted income baseline (the "vs national" denominator)
    national_income_base = {
        "avg_income": wavg_income(provs, lambda r: r["avg_income"]),
        "occ": {k: wavg_income(provs, lambda r, kk=k: r["occ_income"].get(kk)) for k in OCC_KEYS},
    }

    def prov_summary(r):
        return {
            "slug": r["slug"], "th": r["th"], "en": r["en"], "region": r["region"],
            "branches": r["branches"], "districts": r["districts"],
            "contested_districts": r["contested_districts"],
            "rival_branches": r["rivals"],
            "rivals_per_branch": ratio2(r["rivals"], r["branches"]),
            "factories": r["factories"], "workers": r["workers"],
            "vehicles_total": r["veh_total"],
            "moto_share_pct": pct1(r["veh_moto"], r["veh_total"]),
            "pickup_share_pct": pct1(r["veh_pickup"], r["veh_total"]),
            "ev_share_pct": pct1(r["veh_ev"], r["veh_total"]),
            "informal_share_pct": (pct1(r["informal"], r["informal"] + r["formal"])
                                   if (r["informal"] is not None and r["formal"] is not None) else None),
            "labor_force_k": round(r["labor_force_k"], 1),
            "unemployment_rate_pct": pct1(r["unemployed_k"], r["labor_force_k"]),
            "avg_income": r["avg_income"],
            "avg_income_vs_national": (round(r["avg_income"] / national_income_base["avg_income"], 3)
                                       if (r["avg_income"] and national_income_base["avg_income"]) else None),
        }

    # group by raw region
    by_region = {}
    for r in provs:
        by_region.setdefault(r["region"], []).append(r)

    regions = []
    for reg in REGION_ORDER:
        rows = by_region.get(reg, [])
        if not rows:
            continue
        agg = aggregate(rows, national_income_base)
        agg["region"] = reg
        agg["label"] = REGION_LABEL.get(reg, reg)
        agg["n_provinces"] = len(rows)
        agg["provinces"] = [prov_summary(r) for r in sorted(rows, key=lambda x: -x["rivals"] / x["branches"] if x["branches"] else 0)]
        regions.append(agg)

    national = aggregate(provs, national_income_base)
    national["region"] = "TH"
    national["label"] = "Thailand (all 77)"
    national["n_provinces"] = len(provs)

    obj = {
        "meta": {
            "generated_by": "pipeline/build_regions.py",
            "label": "Province -> region rollup for the numbers-first Data Book. Counts SUM; shares/rates are "
                     "ratio-of-sums (never averaged); incomes are labor_force_k-weighted; 'vs national' uses the "
                     "computed labor-weighted national mean. Bangkok (null informal/formal) is skipped in the "
                     "informal-share ratio only.",
            "source": "platform/data/provinces/*.json (DIW factories, DLT vehicles, NSO labour/income) + "
                      "competitors_census.json (measured big-4 rival census).",
            "income_baseline": "computed labor_force_k-weighted national mean (not editorial facts.natl_avg)",
            "weight": "labor_force_k",
            "bangkok_informal_excluded": True,
            "n_provinces": len(provs),
            "n_regions": len(regions),
        },
        "national": national,
        "regions": regions,
    }
    return obj


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: platform/data/regions.json (run: python3 pipeline/build_regions.py)")
            return 1
        print(f"OK: regions.json reproduces ({obj['meta']['n_regions']} regions, {obj['meta']['n_provinces']} provinces)")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    n = obj["national"]
    print(f"wrote platform/data/regions.json — {obj['meta']['n_regions']} regions, {obj['meta']['n_provinces']} provinces")
    print(f"  national: {n['branches']} branches, {n['rival_branches']} rivals "
          f"({n['rivals_per_branch']}x/branch), informal {n['informal_share_pct']}%, "
          f"moto {n['moto_share_pct']}%, avg income ฿{n['avg_income']:,}/mo")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="province -> region rollup engine (Data Book)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
