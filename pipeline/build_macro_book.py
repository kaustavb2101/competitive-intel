#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_macro_book.py — the macro backdrop at OUR grain: national → region → province → branch.

Owner review 2026-08-02. This one layer answers five of the review comments, because they were all
the same comment:

  * point 16, provincial labour stress: "What value does this have? Please follow point 13."
  * point 17, debt per household: "nice but what do we get out of it if its only regional level?
    We have more granular datasets no?"
  * point 15, the EV table: "very good data, just presentation should be better. Always think of the
    roll-up mentioned in point 13."
  * point 20, business formation: "Follow point 13 for format of data drilldowns."
  * point 22, live hazard: "This entire section can be made into small graphs or a combined table.
    You decide... Hazard should also include draught and have the relevant data/graph."

And point 13 itself: "All provinces, roll up into regional summaries, roll up into national summary.
This type of format can be used to analyze impact by branch, by province, and by region for AutoX."

WHAT MAKES A MACRO NUMBER USEFUL HERE is not the number — it is the baht sitting next to it. A
province unemployment rate on its own is a statistic; the same rate beside the outstanding we have
lent into that province is an exposure. So every row on every level carries our MEASURED book
(accounts, outstanding, 90+) from collateral_book.json, and the macro columns hang off it.

GRAIN, STATED HONESTLY PER COLUMN — this is the part that must not be fudged:
  * OUR BOOK          national / region / province / branch   MEASURED (real tape)
  * Labour (NSO LFS)  province → region                       MEASURED; rolled by labour force
  * Fleet + EV (DLT)  province → region                       MEASURED; rolled by fleet stock
  * Business (DBD)    province → region                       MEASURED; rolled by count
  * Flood (ThaiWater) province → region                       MEASURED, live; rolled by station count
  * Drought (OAE)     district → province → region            MODELLED (SPEI); rolled by district count
  * Household debt    REGION ONLY                             MEASURED (BoT/NSO SES 2019)

The last one is the honest answer to point 17. There is no province household-debt table: the BoT
publishes none and the per-household figures trace to the 2019 socio-economic survey. What IS more
granular is OUR OWN book, which is measured at branch level — so the drill carries the regional debt
backdrop as a region-scoped column (`lev:'r'`, so it never renders as a column of em-dashes on the
province list) and puts our measured ticket and arrears at the finer grains beside it.

Branch rows carry the book plus the province's hazard/labour backdrop, marked INHERITED rather than
estimated: we are not modelling a branch-level unemployment rate, we are saying which provincial
conditions that branch operates under. That distinction is the whole point of labelling.

Deterministic + network-free + --check, per the house rule.
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "..", "platform", "data")
OUT = os.path.join(P, "macro_book.json")

# SPEI classes the OAE district layer emits, worst → mildest. "dry" = anything at moderate or worse;
# that threshold is stated here once rather than scattered through the rollup.
DROUGHT_DRY = ("extreme", "severe", "moderate")


def _load(name):
    p = os.path.join(P, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _r(v, nd=2):
    return None if v is None else round(float(v), nd)


def _wavg(pairs, nd=2):
    """Weighted mean of (value, weight); None when nothing carries a value or all weights are 0."""
    num = den = 0.0
    for v, w in pairs:
        if v is None or w is None:
            continue
        w = float(w)
        if w <= 0:
            continue
        num += float(v) * w
        den += w
    return None if den <= 0 else round(num / den, nd)


# The BoT publishes household debt on the conventional NSO four-region cut. Our book uses five
# regions because the East is a distinct commercial market for us. In the NSO/BoT scheme the eastern
# provinces sit INSIDE ภาคกลาง (Central), so both of our regions read the same measured Central row —
# and the layer says so rather than leaving the East blank or inventing a number for it.
DEBT_REGION = {"Northeast": ["Isan"], "North": ["North"], "South": ["South"],
               "Central": ["Central&BKK", "East"]}
# The only province-grain household-debt figures the BoT publishes: a vulnerable-household share for
# five provinces. Transliterations are NOT trusted — each is verified against the measured province
# list at build time and silently dropped if it does not match, so a wrong Thai string can never
# become a silent mis-join.
DEBT_PROV = {"Buriram": "บุรีรัมย์", "Krabi": "กระบี่", "Satun": "สตูล",
             "Sisaket": "ศรีสะเกษ", "Surin": "สุรินทร์"}


def _debt_rows(rd, level):
    """Indicator rows at one level of region_debt.json, as {geo: {indicator: value}}.

    region_debt.json is a flat list of rows carrying their own `geo`, not a table keyed by geo —
    pivot it. Later vintages win where an indicator repeats (the file carries e.g. both the 2009 and
    2019 share-of-households-with-debt), so the newest measured figure is the one that surfaces."""
    out = {}
    rows = ((rd or {}).get("series") or {}).get(level) or []
    for row in sorted(rows, key=lambda r: str(r.get("vintage") or "")):
        geo, ind, val = row.get("geo"), row.get("indicator"), row.get("value")
        if ind is None or val is None:
            continue
        out.setdefault(geo, {})[ind] = val
    return out


def _debt_by_region(rd):
    """{our_region_key: {debt_hh_thb, cushion_lt3mo_pct, debt_installment_thb_month, ...}}."""
    piv = _debt_rows(rd, "region")
    out = {}
    for bot_geo, ours in DEBT_REGION.items():
        src = piv.get(bot_geo)
        if not src:
            continue
        cell = {}
        if src.get("debt_per_household_thb") is not None:
            cell["debt_hh_thb"] = int(round(float(src["debt_per_household_thb"])))
        for key, out_key, nd in (("financial_cushion_under_3mo_share_pct", "cushion_lt3mo_pct", 1),
                                 ("consumption_debt_share_pct", "consumption_debt_pct", 1),
                                 ("debt_per_household_growth_10yr_pct", "debt_growth_10yr_pct", 1),
                                 ("debt_installment_thb_month", "debt_installment_thb_month", 0)):
            if src.get(key) is not None:
                cell[out_key] = _r(src[key], nd)
        if cell:
            cell["debt_basis"] = ("BoT/NSO %s region" % bot_geo) if len(ours) == 1 else \
                "BoT/NSO Central region (the NSO four-region cut places the East inside Central)"
            for r in ours:
                out[r] = dict(cell)
    return out


def _debt_by_province(rd, known_provinces):
    """The five province rows the BoT does publish, joined only where the Thai name is real."""
    piv = _debt_rows(rd, "province")
    out = {}
    for en, th in DEBT_PROV.items():
        if th not in known_provinces:
            continue                      # transliteration did not match the measured list — drop it
        src = piv.get(en) or {}
        if src.get("vulnerable_household_share_pct") is not None:
            out[th] = {"vulnerable_hh_pct": _r(src["vulnerable_household_share_pct"], 1)}
    return out


def _drought_by_province(dd):
    """{province_th: {n_districts, n_dry, dry_share_pct, spei_mean, worst_cls, n_extreme}}.

    Districts are the published grain; a province is the count-weighted rollup of its districts.
    `dry_share_pct` — the share of a province's districts at moderate drought or worse — travels
    better than a mean SPEI, because a mean hides a province with two extreme districts inside
    twenty wet ones."""
    out = {}
    for d in (dd or {}).get("districts") or []:
        prov = d.get("province_th")
        if not prov:
            continue
        cell = out.setdefault(prov, {"n_districts": 0, "n_dry": 0, "n_extreme": 0,
                                     "_spei": [], "worst_cls": None})
        cell["n_districts"] += 1
        cls = (d.get("cls") or "").lower()
        if cls in DROUGHT_DRY:
            cell["n_dry"] += 1
        if cls == "extreme":
            cell["n_extreme"] += 1
        spei = d.get("spei")
        if spei is not None:
            cell["_spei"].append(float(spei))
        # worst class seen, ordered by DROUGHT_DRY (index 0 is worst)
        if cls in DROUGHT_DRY:
            cur = cell["worst_cls"]
            if cur is None or DROUGHT_DRY.index(cls) < DROUGHT_DRY.index(cur):
                cell["worst_cls"] = cls
    for cell in out.values():
        sp = cell.pop("_spei")
        cell["spei_mean"] = _r(sum(sp) / len(sp), 3) if sp else None
        cell["dry_share_pct"] = _r(100.0 * cell["n_dry"] / cell["n_districts"], 1) if cell["n_districts"] else None
    return out


def _lfs_by_province(lfs):
    out = {}
    for p in (lfs or {}).get("provinces") or []:
        th = p.get("name_th")
        if not th:
            continue
        out[th] = {
            "labor_force_k": _r(p.get("labor_force_k"), 2),
            "unemployment_pct": _r(p.get("unemployment_rate_pct"), 2),
            "seasonal_share_pct": _r(p.get("seasonal_share_pct"), 2),
            "seasonal_waiting_k": _r(p.get("seasonal_waiting_k"), 2),
        }
    return out


def _dbd_by_province(dbd):
    out = {}
    for th, v in ((dbd or {}).get("by_province") or {}).items():
        n = int(v.get("n") or 0)
        cap = float(v.get("capital_thb") or 0.0)
        out[th] = {
            "new_biz_n": n,
            "new_biz_capital_thb": cap,
            # Median would be better than a mean, but the DBD layer publishes only the province total
            # and the count. Named as an average so nobody reads it as a typical registration.
            "new_biz_avg_capital_thb": int(round(cap / n)) if n else None,
        }
    return out


def _flood_by_province(tw):
    out = {}
    for th, v in ((tw or {}).get("provinces") or {}).items():
        out[th] = {
            "flood_stations": int(v.get("n_stations") or 0),
            "flood_high": int(v.get("n_high") or 0),
            "flood_high_pct": _r(v.get("pct_high"), 1),
            "flood_max_level": v.get("max_level"),
        }
    return out


# --- the fields carried straight off collateral_book.json --------------------------------------
BOOK_FIELDS = ("n", "os", "ticket", "dpd90p_pct", "dpd30p_pct", "current_pct", "ltv_proxy_pct")
# DLT fleet / EV fields, province grain (point 15 — the EV table onto the roll-up)
FLEET_FIELDS = ("fleet_total", "electrified_pct", "bev_pct", "diesel_share_pct",
                "pickup_stock", "car_pickup_stock", "truck_stock")


def _book_cell(src):
    return {k: src.get(k) for k in BOOK_FIELDS if src.get(k) is not None}


def build():
    cb = _load("collateral_book.json")
    lfs = _lfs_by_province(_load("province_lfs.json"))
    dbd = _dbd_by_province(_load("dbd_formation.json"))
    flood = _flood_by_province(_load("thaiwater_flood.json"))
    drought = _drought_by_province(_load("drought_district.json"))
    rd = _load("region_debt.json")
    debt = _debt_by_region(rd)
    sfi = _load("sfi_credit.json") or {}

    CB_P = cb["provinces"]
    CB_R = cb["regions"]
    CB_B = cb["branches"]
    debt_p = _debt_by_province(rd, set(CB_P))

    # ---- provinces: our book + every province-grain macro layer, joined on the Thai name --------
    provinces = {}
    for th, pv in CB_P.items():
        cell = _book_cell(pv)
        cell["region"] = pv.get("region")
        for f in FLEET_FIELDS:
            if pv.get(f) is not None:
                cell[f] = pv[f]
        cell.update(lfs.get(th) or {})
        cell.update(dbd.get(th) or {})
        cell.update(flood.get(th) or {})
        dr = drought.get(th)
        if dr:
            cell.update({k: dr[k] for k in ("n_districts", "n_dry", "n_extreme",
                                            "dry_share_pct", "spei_mean", "worst_cls")})
        cell.update(debt_p.get(th) or {})
        # New business registrations per 1,000 of the labour force — the DBD count on its own ranks
        # by province size and says nothing (BKK is always first). Per capita it is a formation RATE,
        # which is the thing that varies. Only computed where both measured inputs exist.
        lf = cell.get("labor_force_k")
        if cell.get("new_biz_n") is not None and lf:
            cell["new_biz_per_1k_lf"] = _r(cell["new_biz_n"] / lf, 2)
        provinces[th] = cell

    # ---- regions: roll each layer by ITS OWN correct weight, never a flat mean ------------------
    regions = {}
    for rk, rv in CB_R.items():
        if not rk or rk.startswith("("):        # head-office / direct-sales pseudo-region
            continue
        members = [(th, p) for th, p in provinces.items() if p.get("region") == rk]
        cell = _book_cell(rv)
        cell["n_prov"] = len(members)
        cell["n_br"] = len(CB_B.get(rk) or []) if isinstance(CB_B.get(rk), list) else \
            sum(len(CB_B.get(th) or []) for th, _ in members)
        # labour — weighted by labour force, the population the rate is a rate OF
        cell["labor_force_k"] = _r(sum(p["labor_force_k"] for _, p in members
                                       if p.get("labor_force_k")), 2) or None
        cell["unemployment_pct"] = _wavg([(p.get("unemployment_pct"), p.get("labor_force_k")) for _, p in members])
        cell["seasonal_share_pct"] = _wavg([(p.get("seasonal_share_pct"), p.get("labor_force_k")) for _, p in members])
        cell["seasonal_waiting_k"] = _r(sum(p.get("seasonal_waiting_k") or 0 for _, p in members), 2)
        # fleet / EV — weighted by fleet stock
        cell["fleet_total"] = sum(int(p.get("fleet_total") or 0) for _, p in members) or None
        for f in ("electrified_pct", "bev_pct", "diesel_share_pct"):
            cell[f] = _wavg([(p.get(f), p.get("fleet_total")) for _, p in members])
        for f in ("pickup_stock", "car_pickup_stock", "truck_stock"):
            tot = sum(int(p.get(f) or 0) for _, p in members)
            cell[f] = tot or None
        # business formation — plain sums, then the rate recomputed from the sums
        cell["new_biz_n"] = sum(int(p.get("new_biz_n") or 0) for _, p in members) or None
        cap = sum(float(p.get("new_biz_capital_thb") or 0.0) for _, p in members)
        cell["new_biz_capital_thb"] = cap or None
        if cell.get("new_biz_n") and cell.get("labor_force_k"):
            cell["new_biz_per_1k_lf"] = _r(cell["new_biz_n"] / cell["labor_force_k"], 2)
        # hazard — flood by station count, drought by district count
        cell["flood_stations"] = sum(int(p.get("flood_stations") or 0) for _, p in members)
        cell["flood_high"] = sum(int(p.get("flood_high") or 0) for _, p in members)
        cell["flood_high_pct"] = _r(100.0 * cell["flood_high"] / cell["flood_stations"], 1) \
            if cell["flood_stations"] else None
        cell["n_districts"] = sum(int(p.get("n_districts") or 0) for _, p in members)
        cell["n_dry"] = sum(int(p.get("n_dry") or 0) for _, p in members)
        cell["n_extreme"] = sum(int(p.get("n_extreme") or 0) for _, p in members)
        cell["dry_share_pct"] = _r(100.0 * cell["n_dry"] / cell["n_districts"], 1) \
            if cell["n_districts"] else None
        cell["spei_mean"] = _wavg([(p.get("spei_mean"), p.get("n_districts")) for _, p in members], 3)
        # household debt — REGION IS THE ONLY GRAIN THAT EXISTS (point 17's honest answer)
        cell.update(debt.get(rk) or {})
        regions[rk] = cell

    # ---- branches: our measured book + the provincial conditions it operates under --------------
    INHERIT = ("unemployment_pct", "seasonal_share_pct", "flood_high_pct", "flood_max_level",
               "dry_share_pct", "worst_cls", "electrified_pct", "diesel_share_pct",
               "new_biz_per_1k_lf")
    branches = {}
    for th, rows in CB_B.items():
        pv = provinces.get(th) or {}
        out_rows = []
        for b in rows or []:
            cell = _book_cell(b)
            cell["name"] = b.get("name")
            for f in INHERIT:
                if pv.get(f) is not None:
                    cell[f] = pv[f]
            out_rows.append(cell)
        if out_rows:
            branches[th] = out_rows

    # ---- national ------------------------------------------------------------------------------
    nat = _book_cell(cb["national"])
    nat["provinces"] = len(provinces)
    nat["branches"] = sum(len(v) for v in branches.values())
    nat["labor_force_k"] = _r(sum(p["labor_force_k"] for p in provinces.values()
                                  if p.get("labor_force_k")), 2)
    nat["unemployment_pct"] = _wavg([(p.get("unemployment_pct"), p.get("labor_force_k"))
                                     for p in provinces.values()])
    nat["seasonal_share_pct"] = _wavg([(p.get("seasonal_share_pct"), p.get("labor_force_k"))
                                       for p in provinces.values()])
    nat["seasonal_waiting_k"] = _r(sum(p.get("seasonal_waiting_k") or 0 for p in provinces.values()), 2)
    nat["fleet_total"] = sum(int(p.get("fleet_total") or 0) for p in provinces.values()) or None
    for f in ("electrified_pct", "bev_pct", "diesel_share_pct"):
        nat[f] = _wavg([(p.get(f), p.get("fleet_total")) for p in provinces.values()])
    nat["new_biz_n"] = sum(int(p.get("new_biz_n") or 0) for p in provinces.values()) or None
    nat["new_biz_capital_thb"] = sum(float(p.get("new_biz_capital_thb") or 0.0)
                                     for p in provinces.values()) or None
    if nat.get("new_biz_n") and nat.get("labor_force_k"):
        nat["new_biz_per_1k_lf"] = _r(nat["new_biz_n"] / nat["labor_force_k"], 2)
    nat["flood_stations"] = sum(int(p.get("flood_stations") or 0) for p in provinces.values())
    nat["flood_high"] = sum(int(p.get("flood_high") or 0) for p in provinces.values())
    nat["flood_high_pct"] = _r(100.0 * nat["flood_high"] / nat["flood_stations"], 1) \
        if nat["flood_stations"] else None
    nat["n_districts"] = sum(int(p.get("n_districts") or 0) for p in provinces.values())
    nat["n_dry"] = sum(int(p.get("n_dry") or 0) for p in provinces.values())
    nat["n_extreme"] = sum(int(p.get("n_extreme") or 0) for p in provinces.values())
    nat["dry_share_pct"] = _r(100.0 * nat["n_dry"] / nat["n_districts"], 1) if nat["n_districts"] else None
    nat["spei_mean"] = _wavg([(p.get("spei_mean"), p.get("n_districts")) for p in provinces.values()], 3)
    natrow = _debt_rows(rd, "national").get(None) or {}
    if natrow.get("debt_per_household_thb") is not None:
        nat["debt_hh_thb"] = int(round(float(natrow["debt_per_household_thb"])))
    for key, out_key, nd in (("financial_cushion_under_3mo_share_pct", "cushion_lt3mo_pct", 1),
                             ("household_income_thb_month", "income_hh_thb_month", 0),
                             ("share_households_with_debt_pct", "hh_with_debt_pct", 1),
                             ("vulnerable_household_share_pct", "vulnerable_hh_pct", 1)):
        if natrow.get(key) is not None:
            nat[out_key] = _r(natrow[key], nd)
    nat["n_prov_with_debt"] = len(debt_p)

    # ---- the state-bank NPL series, as a sparkline and nothing more (point 21) ------------------
    # "This can be a small graph somewhere, doesn't need its own section." So it ships as a series
    # on this layer instead of a table of its own: 73 quarters in, one line out.
    npl_rows = [r for r in (sfi.get("series") or []) if r.get("npl_ratio") is not None]
    npl = None
    if npl_rows:
        npl_rows = sorted(npl_rows, key=lambda r: r.get("period") or "")
        vals = [_r(r["npl_ratio"], 2) for r in npl_rows]
        npl = {
            "latest": vals[-1], "period": npl_rows[-1].get("period"),
            "prev": vals[-2] if len(vals) > 1 else None,
            "yoy": _r(vals[-1] - vals[-5], 2) if len(vals) > 4 else None,
            "min": min(vals), "max": max(vals),
            "min_period": npl_rows[vals.index(min(vals))].get("period"),
            "max_period": npl_rows[vals.index(max(vals))].get("period"),
            "n_quarters": len(vals),
            "series": vals[-40:],
            "labels": [r.get("period") for r in npl_rows[-40:]],
        }

    return {
        "meta": {
            "title": "Macro backdrop at our grain — national, region, province, branch",
            "generated_by": "pipeline/build_macro_book.py",
            "deterministic": True,
            "network_free": True,
            "label": "MEASURED book (real loan tape) crossed with MEASURED macro layers, except "
                     "drought which is MODELLED (OAE SPEI). Our accounts, outstanding, ticket and "
                     "arrears are measured at every level including branch. Labour (NSO LFS), fleet "
                     "and EV (DLT), business formation (DBD) and flood (ThaiWater) are published at "
                     "PROVINCE grain and rolled up by their own correct weight — labour force, fleet "
                     "stock, registration count and station count respectively, never a flat mean. "
                     "Drought is published per district and rolled to province by district count.",
            "grain_note": "Household debt exists at REGION grain only — the BoT publishes no routine "
                          "province table and the per-household figures trace to the NSO "
                          "socio-economic survey of 2019. It is carried as a region-scoped column "
                          "rather than spread down to provinces it was never measured at. What IS "
                          "more granular is our own book, which is measured to the branch.",
            "branch_note": "Branch rows carry MEASURED book plus INHERITED provincial conditions "
                           "(unemployment, seasonal share, flood, drought, EV, formation rate). "
                           "Inherited means 'the conditions this branch operates under', not a "
                           "branch-level estimate of a provincial statistic. Nothing here models a "
                           "per-branch unemployment rate.",
            "sources": ["collateral_book.json", "province_lfs.json", "dbd_formation.json",
                        "thaiwater_flood.json", "drought_district.json", "region_debt.json",
                        "sfi_credit.json"],
            "drought_dry_classes": list(DROUGHT_DRY),
            "n_provinces": len(provinces),
            "n_branches": nat["branches"],
        },
        "national": nat,
        "regions": regions,
        "provinces": provinces,
        "branches": branches,
        "npl": npl,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the committed file reproduces byte-for-byte")
    args = ap.parse_args()

    for need in ("collateral_book.json", "province_lfs.json"):
        if not os.path.exists(os.path.join(P, need)):
            print("build_macro_book.py: SKIP (%s absent)" % need)
            return 0

    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            print("DRIFT: platform/data/macro_book.json missing — run build_macro_book.py")
            return 1
        with open(OUT, encoding="utf-8") as f:
            if f.read() != payload:
                print("DRIFT: platform/data/macro_book.json differs from a fresh build")
                return 1
        n = json.loads(payload)["national"]
        print("OK: macro_book.json reproduces (%d provinces, %d branches, %s dry districts of %s)"
              % (n["provinces"], n["branches"], f"{n['n_dry']:,}", f"{n['n_districts']:,}"))
        return 0

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    doc = json.loads(payload)
    n = doc["national"]
    print("wrote %s" % OUT)
    print("  book        THB%.2fbn over %s accounts, %d provinces, %d branches"
          % (n["os"] / 1e9, f"{n['n']:,}", n["provinces"], n["branches"]))
    print("  labour      %.2f%% unemployment, %.2f%% seasonal-waiting, %s k labour force"
          % (n["unemployment_pct"] or 0, n["seasonal_share_pct"] or 0, f"{n['labor_force_k']:,.0f}"))
    print("  fleet/EV    %s vehicles, %.2f%% electrified, %.2f%% diesel"
          % (f"{n['fleet_total']:,}", n["electrified_pct"] or 0, n["diesel_share_pct"] or 0))
    print("  formation   %s new registrations, %.2f per 1k labour force"
          % (f"{n['new_biz_n']:,}", n.get("new_biz_per_1k_lf") or 0))
    print("  hazard      %s of %s stations high (%.1f%%), %s of %s districts dry (%.1f%%), %d extreme"
          % (f"{n['flood_high']:,}", f"{n['flood_stations']:,}", n["flood_high_pct"] or 0,
             f"{n['n_dry']:,}", f"{n['n_districts']:,}", n["dry_share_pct"] or 0, n["n_extreme"]))
    if doc.get("npl"):
        q = doc["npl"]
        print("  system NPL  %.2f%% (%s), %d quarters, range %.2f–%.2f%%"
              % (q["latest"], q["period"], q["n_quarters"], q["min"], q["max"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
