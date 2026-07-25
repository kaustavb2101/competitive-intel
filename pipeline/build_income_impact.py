"""
build_income_impact.py — the income-impact engine (TMLI-convergence move 2, owner ask 2026-07-25)

TMLI's headline idea was "what does a macro move do to each occupation's income, by province."
This is the HONEST version: a deterministic FIRST-ORDER pass-through over MEASURED layers. No LLM
in this build — the layer is pure arithmetic; narration (if any) is a separate, labelled step.

The chain (all first-order, all transparent):
  crop-price YoY moves ─┐
   (commodity_board,    ├─► per-province income shock per occupation ─► book-weighted pressure
    weighted by each    │        (× a documented sensitivity matrix)      (× tape occupation mix)
    province's crop area)│
  fuel-cost move ───────┘

  in : platform/data/occupation_income_individual.json  MEASURED — NSO SES 2566 income per occ×prov
       source-data/crop_prov_area.json                  MEASURED — rice/rubber/oilpalm area per prov
       source-data/commodity_board.json                 MEASURED — commodity YoY price moves
       platform/data/fuel_prices.json                   MEASURED — live retail fuel (cost driver)
       platform/data/tape_real.json                     MEASURED — book occupation mix per geo region
  out: platform/data/income_impact.json                 (--check: byte-exact reproduce)

ESTIMATED, and labelled so: the SENSITIVITY coefficients (how much of a price/fuel move reaches an
occupation's take-home income) are a documented first-order assumption, not a measured elasticity —
they live in SENS below and are echoed into meta. The crop driver is weighted only over the three
crops with province-level area (rice/rubber/oilpalm); other crops (sugar/maize/cassava) are not
weighted into the province shock — stated in meta. Everything the coefficients multiply is measured.
"""
import json
import os
import sys

from regionmap import REGION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "platform", "data")
S = os.path.join(ROOT, "source-data")
OUT = os.path.join(P, "income_impact.json")

REGIONS = ["Isan", "Central&BKK", "South", "East", "North"]

# ── SES occupations we carry baseline income for (occupation_income_individual) ──
SES_OCC = ["Agriculture", "FactoryWorkers", "OfficeStaff", "Transport", "SMEOwners"]
SES_TH = {"Agriculture": "เกษตรกร", "FactoryWorkers": "แรงงาน/รับจ้าง",
          "OfficeStaff": "พนักงาน/ข้าราชการ", "Transport": "ขนส่ง", "SMEOwners": "ค้าขาย/ธุรกิจ"}

# ── FIRST-ORDER sensitivity matrix (ESTIMATED, documented) ──────────────────────
# fraction of a +1.0 (100%) driver move that reaches that occupation's take-home income.
# crop: farm net income tracks crop-gate prices only partially — input costs are semi-fixed, so
#       net-return elasticity < 1 (OAE net-return tables show costs ~40-60% of gross). 0.55 mid.
# fuel: diesel is a direct margin line for transport/haulage and an input cost for farming; salaried
#       incomes are fixed in the near term, so 0. (Signs: +crop lifts farm income; +fuel cuts income.)
SENS = {
    "Agriculture":   {"crop": 0.55, "fuel": -0.08},
    "Transport":     {"crop": 0.0,  "fuel": -0.18},
    "FactoryWorkers": {"crop": 0.0, "fuel": -0.03},
    "SMEOwners":     {"crop": 0.05, "fuel": -0.05},   # mild rural-demand + own-vehicle cost
    "OfficeStaff":   {"crop": 0.0,  "fuel": 0.0},     # salaried / civil-servant — fixed short-run
}

# ── tape occupation group → SES occupation (for the book-weighted rollup) ────────
TAPE_TO_SES = {
    "เกษตร": "Agriculture",
    "รับจ้างทั่วไป": "FactoryWorkers",
    "พนักงานบริษัท": "OfficeStaff",
    "ข้าราชการ": "OfficeStaff",
    "กลุ่มวิชาชีพ": "OfficeStaff",
    "ค้าขาย": "SMEOwners",
    "ผู้ประกอบการ": "SMEOwners",
    "ธุรกิจเฉพาะ": "SMEOwners",
    "บริการ": "SMEOwners",
}

# board label → crop_prov_area key (only the three crops with province-level area)
BOARD_TO_AREA = {"Rice": "rice", "Rubber": "rubber", "Palm oil": "oilpalm"}


def load(*path):
    return json.load(open(os.path.join(*path), encoding="utf-8"))


def build():
    occinc = load(P, "occupation_income_individual.json")["provinces"]
    area = load(S, "crop_prov_area.json")
    board = {it["lab"]: it for it in load(S, "commodity_board.json")}
    fuel = load(P, "fuel_prices.json")
    try:
        energy = load(S, "energy_prices.json")
    except FileNotFoundError:
        energy = {}
    tape = load(P, "tape_real.json")
    prov_region = dict(REGION)

    # crop YoY moves (fraction) for the three area-weighted crops
    crop_yoy = {}
    for lab, akey in BOARD_TO_AREA.items():
        it = board.get(lab)
        if it:
            crop_yoy[akey] = it["yoy"] / 100.0

    # fuel driver: crude-oil YoY from the World Bank Pink Sheet (source-data/energy_prices.json) —
    # the SAME workbook and 12-month-YoY method as the crop drivers (owner ask: use the same
    # comparison period as crops, not a bare same-day snapshot). Global crude is a PROXY for the
    # Thai borrower's fuel cost — Thai retail diesel is subsidy/fund-buffered, so pass-through is
    # partial — exactly as the crop drivers are a global proxy for Thai farm-gate. +ve = cost UP,
    # which SUBTRACTS from fuel-sensitive incomes via the negative fuel coefficients in SENS.
    diesel = fuel.get("headline", {}).get("diesel")
    crude = energy.get("crude_avg") or {}
    fuel_drv = (crude.get("yoy") or 0.0) / 100.0

    # ── per-province agri price shock: area-weighted over rice/rubber/oilpalm ────
    agri_shock = {}     # province -> fraction income-driver from crop prices
    crop_mix = {}       # province -> {crop: area_share} (for the drill/explanation)
    for pv in prov_region:
        parts = {c: (area.get(c, {}) or {}).get(pv, 0) or 0 for c in BOARD_TO_AREA.values()}
        tot = sum(parts.values())
        if tot <= 0:
            continue
        mix = {c: parts[c] / tot for c in parts}
        crop_mix[pv] = {c: round(v, 3) for c, v in mix.items() if v > 0}
        agri_shock[pv] = sum(mix[c] * crop_yoy.get(c, 0.0) for c in parts)

    # ── per-province, per-occupation income delta ───────────────────────────────
    provinces = {}
    for pv, occs in occinc.items():
        if pv not in prov_region:
            continue
        shock = agri_shock.get(pv, 0.0)
        rows = {}
        for o in SES_OCC:
            base = (occs.get(o) or {}).get("individual_est")
            if not base:
                continue
            s = SENS[o]
            d_pct = s["crop"] * shock + s["fuel"] * fuel_drv
            rows[o] = {"income": base, "d_pct": round(d_pct * 100, 2),
                       "d_baht": round(base * d_pct)}
        if rows:
            provinces[pv] = {
                "region": prov_region[pv],
                "agri_price_shock_pct": round(shock * 100, 2),
                "crop_mix": crop_mix.get(pv, {}),
                "occ": rows,
            }

    # ── book-weighted regional pressure (tape occupation mix → SES → sensitivity) ─
    occ_x = tape["geo"]["occ_x_region"]
    regions = []
    for r in REGIONS:
        # tape book weight per SES occupation in this region
        w = {o: 0 for o in SES_OCC}
        rtot = 0
        for k, cell in occ_x.items():
            occ, reg = k.rsplit("|", 1)
            if reg != r:
                continue
            ses = TAPE_TO_SES.get(occ)
            if ses:
                w[ses] += cell["n"]
                rtot += cell["n"]
        if not rtot:
            continue
        # region-representative income delta per occ = mean over that region's provinces
        rprov = [pv for pv in provinces if provinces[pv]["region"] == r]
        occ_dpct = {}
        for o in SES_OCC:
            vals = [provinces[pv]["occ"][o]["d_pct"] for pv in rprov
                    if o in provinces[pv]["occ"]]
            if vals:
                occ_dpct[o] = sum(vals) / len(vals)
        # book-weighted income pressure = Σ share_o × Δincome%_o
        pressure = sum((w[o] / rtot) * occ_dpct.get(o, 0.0) for o in SES_OCC)
        declining = sum(w[o] for o in SES_OCC if occ_dpct.get(o, 0.0) < 0)
        worst = min(occ_dpct.items(), key=lambda kv: kv[1]) if occ_dpct else (None, 0)
        best = max(occ_dpct.items(), key=lambda kv: kv[1]) if occ_dpct else (None, 0)
        regions.append({
            "key": r,
            "income_pressure_pct": round(pressure, 2),
            "book_share_declining_pct": round(declining * 100.0 / rtot, 1),
            "book_mix": {o: round(w[o] * 100.0 / rtot, 1) for o in SES_OCC if w[o]},
            "worst_occ": {"occ": worst[0], "th": SES_TH.get(worst[0]),
                          "d_pct": round(worst[1], 2)},
            "best_occ": {"occ": best[0], "th": SES_TH.get(best[0]),
                         "d_pct": round(best[1], 2)},
        })
    regions.sort(key=lambda g: g["income_pressure_pct"])   # most-pressured first

    return {
        "meta": {
            "title": "Income-impact engine — macro moves → occupation income → book pressure",
            "generated_by": "pipeline/build_income_impact.py",
            "label": "ESTIMATED (first-order). Every quantity the model MULTIPLIES is measured "
                     "(NSO SES income, crop area, commodity YoY, retail diesel); the SENSITIVITY "
                     "coefficients — how much of a price/fuel move reaches take-home income — are "
                     "a documented first-order assumption (see sensitivity), not a fitted "
                     "elasticity. Read directions and relative magnitudes, not precise levels.",
            "method": "Δincome%[prov,occ] = crop_sens[occ]·agri_price_shock[prov] + "
                      "fuel_sens[occ]·fuel_move. agri_price_shock = area-weighted (rice/rubber/"
                      "oilpalm) commodity YoY. Book pressure = Σ tape-book-share[occ]·Δincome%.",
            "sensitivity": SENS,
            "crop_note": "province crop driver is weighted only over rice/rubber/oilpalm (the crops "
                         "with province-level planted area); sugar/maize/cassava are not weighted.",
            "drivers": {
                "crop_yoy_pct": {k: round(v * 100, 1) for k, v in crop_yoy.items()},
                "diesel_thb_l": diesel,
                "crude_usd_bbl": crude.get("latest"),
                "fuel_move_pct": round(fuel_drv * 100, 2),
                "fuel_basis": ("crude-oil YoY (World Bank Pink Sheet 'Crude oil, average', %s) — the "
                               "same source and 12-month period as the crop drivers, per the owner "
                               "ask. Global crude is a proxy for Thai fuel cost (Thai retail diesel "
                               "is subsidy/fund-buffered, so pass-through is partial), the same "
                               "global-proxy caveat the crop drivers carry. +ve = fuel cost up."
                               % (crude.get("date") or "n/a")),
                "fuel_ytd_pct": crude.get("ytd"),
            },
            "vintage": {"income": "NSO SES 2566", "commodity": "Pink Sheet (board)",
                        "fuel": (energy.get("meta") or {}).get("vintage")
                                or (fuel.get("meta") or {}).get("pulled")},
            "occupations": SES_TH,
        },
        "regions": regions,
        "provinces": provinces,
    }


def main():
    if not os.path.exists(os.path.join(P, "tape_real.json")):
        # exit 3 = the gate's SKIP contract (tape ingest wave absent, not data drift)
        print("build_income_impact.py: SKIP (tape_real.json absent — run the tape ingest first)")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if "--check" in sys.argv[1:]:
        if not os.path.exists(OUT):
            sys.exit("build_income_impact.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_income_impact.py --check: drifted — re-run the builder.")
        print("build_income_impact.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d regions, %d provinces" % (OUT, len(obj["regions"]),
                                                    len(obj["provinces"])))


if __name__ == "__main__":
    main()
