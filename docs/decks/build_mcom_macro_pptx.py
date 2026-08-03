"""MCOM · Wednesday 5 August 2026 — the Macro tab, as a house-style PPTX.

Scope is one tab, and the tab is EXTERNAL DATA. Every figure here is published by an agency, a
ministry or a market — what is happening outside the company, not what it costs us. That line is
the owner's, set when `renderRecoverySensitivity` was moved off the tab on 2026-08-02: "it is a
balance-sheet reading, and this tab is external data."

No figure in this deck comes from the loan tape. Where the tab's own layers join our outstanding to
an external number (farm_book, collateral_book, macro_book all do), only the external side is used —
crop mix and planted area from OAE rather than allocated outstanding, registered stock and transfers
from DLT rather than the collateral book. Book readouts belong on Exposure and Risk.

The deck's job is to point at REGIONS, PROVINCES and DISTRICTS where published statistics say a
household is being squeezed, early enough for a pre-emptive conversation. Turning a geography into
a call list is the Assistance tab's work and needs the book beside it; that is a different room.

Numbers are read live out of `platform/data/` at build time wherever the layer exists, so a rebuild
after a data refresh picks up the new vintage rather than quoting a transcribed figure. Provenance
travels with each number: MEASURED means a source published it, ESTIMATED means we modelled it,
MIXED means the parts differ.

    python docs/decks/build_mcom_macro_pptx.py [--out DIR] [--preview]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deckkit import GOLD, GREEN, GREY, NAVY, RED, Deck, TX  # noqa: E402

L, W = 0.45, 12.43            # content column
MEAS, EST, MIX = "MEASURED", "ESTIMATED", "MIXED"
DATA = Path(__file__).resolve().parents[2] / "platform" / "data"
COLLAT = "7A4FE0"             # the platform's collateral purple
ROLL = "D97A3A"               # the 30-89 rolling band, same as the app's bucket ladder


def load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def ym(period):
    """'2026-05' / '2026M05' -> decimal year, so a monthly series can be plotted on one axis."""
    y, m = period.replace("M", "-").split("-")
    return int(y) + (int(m) - 1) / 12.0


def uvpi_series():
    """The BoT used-vehicle index — 185 monthly points per series. Plotted rather than summarised
    because the argument is about the SHAPE: pickups tracked cars until 2022 and then did not."""
    d = load("used_vehicle_value.json")
    return {k: [(ym(r["period"]), r["value"]) for r in d["series"][k]["history"]]
            for k in ("truck", "car")}


def ols_slope(ys):
    """Least-squares units-per-month slope of a short monthly series."""
    n = len(ys)
    mx, my = (n - 1) / 2.0, sum(ys) / n
    sxy = sum((i - mx) * (y - my) for i, y in enumerate(ys))
    sxx = sum((i - mx) ** 2 for i in range(n))
    return sxy / sxx


def price_history(keys):
    """Pink Sheet monthly prices REBASED to 100 at each series' first month.

    Rebasing is not cosmetic: rice is quoted in $/tonne, rubber and sugar in $/kg, so the raw values
    cannot share an axis. What the slide is about is relative movement over five years, which a
    common base shows and raw levels hide.
    """
    d = load("commodity_history.json")["series"]
    out = {}
    for k in keys:
        pts = [(ym(m), v) for m, v in zip(d[k]["months"], d[k]["values"]) if v is not None]
        base = pts[0][1]
        out[k] = [(x, 100.0 * v / base) for x, v in pts]
    return out


def build():
    d = Deck()
    FB, CB, MB = load("farm_book.json"), load("collateral_book.json"), load("macro_book.json")
    FH, VM, WEO = load("farm_household.json"), load("vehicle_models.json"), load("imf_weo.json")
    mn = MB["national"]        # macro_book's EXTERNAL national roll-up (labour, fleet, hazard)
    thb = lambda v: f"฿{v:,.0f}"
    cr = {c["en"]: c for c in FB["crops"]}
    CM = load("crop_mix.json")
    # National share of PLANTED AREA per crop, area-weighted from the measured per-province OAE mix.
    _rai, _crop = 0.0, {}
    for _p in CM["provinces"].values():
        _rai += _p["area_rai"]
        for _c in _p["crops"]:
            _crop[_c["en"]] = _crop.get(_c["en"], 0.0) + _c["share"] * _p["area_rai"]
    AREA = {k: 100.0 * v / _rai for k, v in _crop.items()}   # % of the 113.6M national rai

    # ================================================================ 1 cover
    d.cover("Macro: the conditions\nwe are lending into.",
            "MCOM · Wednesday 5 August 2026 · AutoX / บริษัท ออโต้ เอกซ์ จำกัด (เงินไชโย)",
            "Aug ’26")
    d.notes("Scope: the Macro tab — external conditions only. The economy, crop prices and the "
            "used-vehicle market, all published by someone else. What any of it costs us is the "
            "Exposure and Risk conversation; competition and the branch views are separate again.")

    # ================================================================ 2 the answer
    y = d.content("The answer first", "Four questions about the world outside the company.")
    y += d.text(L, y, W, "Everything on this tab is external — published by an agency, a ministry or "
                "a market, none of it by us. Where a line says what an external move touches, that "
                "is one column of context, not the subject.", size=11.5, color=GREY, lh=15.5) + 0.20
    y += d.qa(L, y, W, [
        ("Is the economy the problem?",
         "No. Growth and inflation both came in above what the IMF projected for 2026 and the policy "
         "rate is 1.00%. But Thailand is projected to grow slowest in ASEAN-5 — 1.5% against "
         "Vietnam’s 7.1%, on the narrowest fiscal room in the group. Stable, not strong."),
        ("Are crop prices the problem?",
         "Not on the world index — but that is the wrong instrument. On the measured Thai farm gate "
         "nine commodities are falling, beef by 6.1% while the world index reads +11.8%. And margin "
         "matters more than price: netted of cost, a 24% price move becomes a 73% swing in crop "
         "income."),
        ("So what is deteriorating?",
         "The collateral. Used pickup values sit 50% below their peak and 33 points below their own "
         "2015 base, new pickup registrations are down 15.3% on the year, and no pickup nameplate is "
         "growing. Pickups turn over more slowly than any other class in every region."),
        ("And the borrower?",
         "Thin before any of this. Farming pays ฿7,200–14,200 a month depending on region against a "
         "฿17,700 national wage, three of the five crops with full economics do not cover their "
         "own cost, and 60% of households could not cover three months without income. System "
         "arrears have risen in three of the last four quarters."),
    ], size=12) + 0.24
    y += d.source(L, y, W, MEAS, GREEN,
                  "NESDC · TPSO · Bank of Thailand · BIS · ECB · IMF · World Bank · NABC · OAE · "
                  "DLT · MOT · NSO · ThaiWater. Each page carries its own chip and vintage; where a "
                  "figure is modelled rather than published it is labelled ESTIMATED.") + 0.26
    d.text(L, y, W, "What follows", size=10, bold=True, color=NAVY)
    d.text(L, y + 0.24, W,
           "01  the macro backdrop and the region        "
           "02–08  agriculture: the farm gate against the world index, the belts, cost of "
           "production, income now, drought        09  where to reach out first        "
           "10  collateral, in four parts        11–13  conditions at branch grain, and what it "
           "asks of us", size=10, color=GREY, lh=14)
    d.notes("If they take one thing: the macro is stable, the crops are mixed, the collateral is "
            "deteriorating — and the borrower was already thin before any of it. Scope is external "
            "conditions; the book readouts live on Exposure and Risk, not here.")

    # ================================================================ 3 macro overlay + region
    y = d.content("01 · Macro overlay",
                  "Benign at home, slowest in the region, and system arrears are turning.")
    y += d.cards(L, y, W, [
        ("GDP growth", "+2.8%", "YoY · measured quarter, not a projection · NESDC 2026-Q1", GREEN),
        ("Inflation", "+2.79%", "headline CPI YoY · TPSO · 2026-05", GOLD),
        ("Policy rate", "1.00%", "Bank of Thailand · 2026-06", NAVY),
        ("USD / THB", "33.47", "ECB reference · 2026-07-31", NAVY),
        ("Household debt", "87.5%", "of GDP · BIS · 2025-Q4", GOLD),
        ("Tourist arrivals", "32.2M", "trailing 12m · −6.6% YoY · BoT 2026-06", RED),
    ], cols=6, ch=1.22) + 0.20
    P = WEO["peers"]
    rows = []
    for code, nm2 in [("THA", "Thailand"), ("VNM", "Vietnam"), ("IDN", "Indonesia"),
                      ("MYS", "Malaysia"), ("PHL", "Philippines")]:
        th = code == "THA"
        rows.append([(nm2, th, NAVY),
                     (f"{P['NGDP_RPCH'][code]:.1f}%", True, RED if th else NAVY),
                     (f"{P['PCPIPCH'][code]:.1f}%", False, NAVY),
                     (f"{P['LUR'][code]:.1f}%", False, NAVY),
                     (f"{P['GGXWDG_NGDP'][code]:.1f}%", False, NAVY)])
    d.table(L, y, 6.45, ["IMF 2026 projection", "GDP growth", "Inflation", "Unemployment",
                         "Govt debt/GDP"], rows,
            colw=[2.1, 1.3, 1.15, 1.5, 1.6], size=10, rh=0.283, aligns=["l", "r", "r", "r", "r"])
    npl = MB["npl"]
    qmap = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}
    pts = [(ym(lab[:4] + "-" + qmap[lab[-2:]]), v)
           for lab, v in zip(npl["labels"], npl["series"])]
    d.linechart(L + 6.75, y, W - 6.75, 1.70, [("System NPL", RED, pts)],
                ylab="Thai banking-system NPL, % of loans · 40 quarters",
                xticks=[(2017, "2017"), (2020, "2020"), (2023, "2023"), (2026, "2026")],
                ymin=2, ymax=6)
    y += 1.70 + 0.18
    y += d.source(L, y, W, MEAS, GREEN,
                  "NESDC · TPSO · Bank of Thailand · BIS · ECB, each pulled from the publishing "
                  "agency. IMF World Economic Outlook 2026 for the peer projections; BoT published "
                  f"NPL ratio — {npl['latest']}% at {npl['period']}, from {npl['prev']}% the quarter "
                  f"before, {npl['yoy']:+.2f} points on the year, against a {npl['min']}% low in "
                  f"{npl['min_period']}.", size=9) + 0.20
    cw2 = (W - 0.25) / 2
    d.callout(L, y, cw2, "Thailand has already overtaken the IMF’s own 2026 projection",
              "The IMF projected 1.5% growth and 0.9% inflation. The measured outturns are +2.8% and "
              "+2.79% — 1.3 and 1.9 points higher. Where a Thai measurement exists we show it "
              "instead of the projection.\n\nThe one falling chip is tourism: arrivals −6.6% on a "
              "trailing-twelve-month basis. That income is a large part of the informal cash economy "
              "in the South and on the eastern seaboard, and it shows up in no crop or fleet series.",
              tone="warn", size=10)
    d.callout(L + cw2 + 0.25, y, cw2, "Slowest growth, narrowest room to cushion it",
              f"Thailand grows at {P['NGDP_RPCH']['THA']:.1f}% while the region runs 4–7%, so "
              "the informal wage most of our borrowers are paid out of will not be lifted by the "
              f"cycle. And government debt is {P['GGXWDG_NGDP']['THA']:.1f}% of GDP against "
              f"Vietnam's {P['GGXWDG_NGDP']['VNM']:.1f}% — the fiscal space for the household relief "
              "that carried people through 2020–21 is materially narrower this time.\n\nSystem "
              "arrears have risen in three of the last four quarters. Read that line as a direction, "
              "not a benchmark: it is bank loans on a regulatory definition.", tone="risk", size=10)
    d.notes("Two slides merged. The economy is fine and the region is not the story — the story is "
            "that growth is slow, the fiscal cushion is thin, and arrears are turning up. If relief "
            "comes, less of it will come from government this time.")

    # ================================================================ 5 commodity board
    y = d.content("02 · Commodity board", "The world index says tailwind. The Thai farm gate does not.")
    y += d.text(L, y, W, "The board carries 21 commodities. Seventeen have a measured Thai farm-gate "
                "price beside the world index, and nine of those seventeen are negative year on year.",
                size=11, color=GREY, lh=15) + 0.16
    rows = [
        [("Coconut", True, NAVY), "Crops", "S · E", ("−70.9%", True, RED), ("—", False, GREY)],
        [("Pineapple", True, NAVY), "Crops", "E · W · N", ("−20.0%", True, RED), ("—", False, GREY)],
        [("Sugar", True, NAVY), "Crops", "Isan · Central", ("−17.9%", True, RED), ("−13.5%", False, RED)],
        [("Rambutan", True, NAVY), "Crops", "S · E", ("−13.5%", True, RED), ("—", False, GREY)],
        [("Pork", True, NAVY), "Livestock", "C · W · E", ("−6.7%", True, RED), ("—", False, GREY)],
        [("Beef", True, NAVY), "Livestock", "Isan", ("−6.1%", True, RED), ("+11.8%", True, GREEN)],
        [("White shrimp", True, NAVY), "Fisheries", "S · E coast", ("−4.3%", True, RED), ("—", False, GREY)],
        [("Chicken", True, NAVY), "Livestock", "C · E", ("−2.4%", True, RED), ("−0.6%", False, GREY)],
        [("Eggs", True, NAVY), "Livestock", "C · E", ("−1.7%", True, RED), ("—", False, GREY)],
    ]
    y += d.table(L, y, W, ["Falling at the farm gate", "Segment", "Belt", "Thai farm-gate YoY",
                           "World index YoY"], rows,
                 colw=[2.6, 1.9, 3.4, 2.4, 2.13], size=10, rh=0.278,
                 aligns=["l", "l", "l", "r", "r"]) + 0.14
    y += d.source(L, y, W, MIX, NAVY,
                  "Prices MEASURED — NABC daily and monthly market feeds, Thai farm gate, OCSB "
                  "announced cane price, World Bank Pink Sheet 2026M06; farm-gate vintage "
                  "2026-08-02. The belt column is an ESTIMATED read of where each is produced, and "
                  "the belts overlap — the same household often keeps poultry and grows rice.",
                  size=9) + 0.16
    d.callout(L, y, W, "Beef is the row that shows why the world index is the wrong instrument",
              "The world beef index is +11.8%. The measured Thai farm-gate price is −6.1% — a 17.9 "
              "point divergence. A cattle household in Isan is not experiencing +11.8%. Rubber, palm "
              "and cassava run the other way and are genuinely up on both measures.", tone="risk")
    d.notes("The divergence rows are the point: the world index and the Thai farm gate can face "
            "opposite directions, and only one of them is what a Thai grower is paid.")

    # ================================================================ 6 five-year price history
    y = d.content("03 · Five years of price", "Sugar has not fallen for a year. It has fallen for four.")
    KEYS = [("rubber", "Rubber", GREEN), ("rice", "Rice", NAVY),
            ("palm", "Palm oil", GOLD), ("sugar", "Sugar", RED)]
    hist = price_history([k for k, _, _ in KEYS])
    d.linechart(L, y, 7.55, 3.05, [(lab, col, hist[k]) for k, lab, col in KEYS],
                ylab="World price rebased to 100 at 2021-07 · 60 monthly observations",
                baseline=100, ymin=40, ymax=200,
                xticks=[(2021.5, "2021"), (2023, "2023"), (2024.5, "2024"), (2026, "2026")])
    d.callout(L + 7.75, y, W - 7.75, "A year-on-year number hides the shape",
              "Sugar reads −13.5% on the year. Across five it has gone from a 0.58 $/kg peak to "
              "0.32 — roughly 45% off, falling almost continuously since early 2023. A grower who "
              "planted against 2023 economics has had three bad years, not one.\n\nRubber is the "
              "mirror image: three years below its 2021 base, recovering only in the last eighteen "
              "months. Those households are repairing a balance sheet, not enjoying a windfall.",
              tone="warn", size=10)
    y += 3.05 + 0.20
    raw = load("commodity_history.json")["series"]
    rows = []
    for k, lab, _ in KEYS:
        vs = [v for v in raw[k]["values"] if v is not None]
        pk, now = max(vs), vs[-1]
        rows.append([(f"{lab} {raw[k]['unit']}", True, NAVY),
                     (f"{AREA[{'rubber': 'Rubber', 'rice': 'Rice', 'palm': 'Oil palm', 'sugar': 'Sugarcane'}[k]]:.1f}%",
                      False, NAVY),
                     (f"{pk:,.2f}", False, NAVY),
                     (f"{now:,.2f}", True, NAVY),
                     (f"{100 * (now / pk - 1):+.1f}%", True,
                      RED if now / pk < 0.85 else NAVY),
                     (f"{100 * (now / vs[0] - 1):+.1f}%", True,
                      GREEN if now > vs[0] else RED)])
    y += d.table(L, y, 8.60, ["World price, five years", "of planted area", "5-yr peak", "latest",
                              "off peak", "vs 5 yrs ago"], rows,
                 colw=[2.6, 1.3, 1.2, 1.1, 1.2, 1.2], size=10, rh=0.278,
                 aligns=["l", "r", "r", "r", "r", "r"]) + 0.18
    d.source(L, y, W, MEAS, GREEN,
             "World Bank Pink Sheet nominal-USD monthly prices, last 60 observations per series, "
             "rebased to 100 at 2021-07 for the chart — the series are quoted in different units and "
             "cannot otherwise share an axis. The table is in each series’ own published unit. "
             "Nominal, not deflated: five years of Thai CPI sits under every ‘vs 5 yrs ago’ figure.",
             size=9)
    d.notes("The point: YoY is a poor instrument for a slow decline. Sugar's −13.5% is the fourth "
            "year of one move, not a new event.")

    # ================================================================ 6 the crop belts
    y = d.content("04 · The crop belts",
                  "Which crop each region grows, and what the price round did to its income.")
    y += d.cards(L, y, W, [
        ("Crops with a Thai farm-gate price", "8",
         "rice, rubber, sugarcane, palm, cassava, maize, coconut, pineapple", NAVY),
        ("Falling at the farm gate", "3",
         "sugarcane −17.9%, coconut −70.9%, pineapple −20.0% year on year", RED),
        ("Median province crop-income shock", f"{CM['national']['median_shock_pct']:+.1f}%",
         "most of the country gained from this price round", GREEN),
        ("Provinces where it went backwards", f"{CM['national']['negative_provinces']}",
         "all four are coconut belts on the western gulf", RED),
    ], cols=4, ch=1.12) + 0.22
    RG = CM["regions"]
    rows = [[(k, True, NAVY),
             (f"{v['provinces']}", False, NAVY),
             (f"{v['shock_pct']:+.1f}%", True, GREEN if v["shock_pct"] > 0 else RED),
             (f"{v['negative']}", True, RED if v["negative"] else NAVY),
             (v["worst_prov"], False, NAVY),
             (f"{v['worst_shock']:+.1f}%", True, GREEN if v["worst_shock"] > 0 else RED)]
            for k, v in sorted(RG.items(), key=lambda kv: kv[1]["shock_pct"])]
    d.table(L, y, 6.05, ["Region", "provs", "income shock", "backwards", "weakest", ""], rows,
            colw=[1.25, 0.75, 1.25, 1.05, 1.05, 0.7], size=9.5, rh=0.272,
            aligns=["l", "r", "r", "r", "l", "r"])
    d.callout(L + 6.30, y - 0.05, W - 6.30, "The price round was good for farming almost everywhere",
              "Rubber +38%, cassava +57%, palm +32% and rice +12% at the farm gate lifted crop "
              "income in every region — the South by 34.9%, the East by 23.9%. On a mix basis "
              "this is the best crop year in several.\n\nThe exception is narrow and worth "
              "naming: four provinces on the western gulf — สมุทรสงคราม, สมุทรสาคร, "
              "ราชบุรี and ประจวบคีรีขันธ์ — all coconut, all negative, the worst at −66.4%. "
              "A single crop collapsing 70.9% is enough to take a whole province backwards while "
              "the national picture improves.\n\nAnd a gain on a mix basis is not cash in hand: "
              "the next slide nets these same prices against cost of production.",
              tone="warn", size=10)
    y += 1.85
    top = sorted(CM["provinces"].items(), key=lambda kv: -kv[1]["area_rai"])[:6]
    rows = []
    for nm2, p2 in top:
        cs = sorted(p2["crops"], key=lambda c: -c["share"])
        lead = cs[0]
        drag = min(p2["crops"], key=lambda c: c["pp"])
        fbp = FB["provinces"].get(nm2, {})
        rain = fbp.get("rain_pct_of_normal")
        rows.append([(nm2, True, NAVY), (p2["region"], False, GREY),
                     (f"{p2['area_rai'] / 1e6:.2f}M", False, NAVY),
                     (f"{lead['en']} {100 * lead['share']:.0f}% ({lead['yoy']:+.0f}%)", False,
                      GREEN if lead["yoy"] > 0 else RED),
                     (f"{drag['en']} ({drag['yoy']:+.0f}%)", False, RED),
                     (f"{p2['shock_pct']:+.1f}%", True,
                      GREEN if p2["shock_pct"] > 0 else RED),
                     (f"{p2['income_base_thb']:,.0f}", False, NAVY),
                     (f"{p2['income_thb_month']:+,.0f}", True,
                      GREEN if p2["income_thb_month"] > 0 else RED),
                     (f"{rain:.0f}%" if rain is not None else "—", True,
                      RED if (rain is not None and rain < 90) else NAVY)])
    y += d.table(L, y, W, ["Largest planted areas", "region", "planted rai", "lead crop, share, YoY",
                           "the drag", "shock", "farm ฿/mo", "in baht", "rain"], rows,
                 colw=[1.75, 1.05, 1.1, 2.75, 1.7, 0.9, 1.05, 0.95, 0.68], size=9, rh=0.268,
                 aligns=["l", "l", "r", "l", "l", "r", "r", "r", "r"]) + 0.14
    d.source(L, y, W, MIX, NAVY,
             "Planted area and crop mix MEASURED (OAE, by province); farm-gate price moves MEASURED "
             "(NABC/OCSB); farm income level MEASURED (NSO/OAE, baht per month). The income shock is "
             "ESTIMATED — each province's crop mix weighted by the measured price move, expressed as "
             "a percentage of its measured farm income and as the baht that implies. Six of 77 "
             "provinces shown, ordered by planted area.", size=9)
    d.notes("What earns agriculture a section is that its hazards are external and forecastable — "
            "price, cost, rainfall — which is rare. The last column is context for how much of it "
            "reaches us; the belts themselves are the subject.")

    # ================================================================ 8 crop margins
    y = d.content("05 · Margin, not price", "Price is the headline. Cost decides whether they pay us.")
    rows = []
    for c in FB["crops"]:
        has = c.get("margin_per_rai") is not None
        yv = c.get("yoy")
        rows.append([
            (c["en"], True, NAVY),
            (f"{AREA.get(c['en'], 0):.1f}%", False, NAVY),
            ((f"{yv:+.1f}%" if yv is not None else "—"), True,
             GREEN if (yv or 0) > 0 else RED),
            (f"{c['price_kg']:.2f}" if has else "—", False, NAVY),
            (f"{c['cost_kg']:.2f}" if has else "—", False, NAVY),
            (f"{c['margin_per_rai']:,.0f}" if has else "no cost series", has,
             NAVY if has else RED),
            (f"{c['margin_pct']:.1f}%" if has else "—", has,
             (GREEN if has and c["margin_pct"] >= 40 else GOLD) if has else GREY),
        ])
    y += d.table(L, y, W, ["Crop", "of planted area", "Farm-gate YoY", "Price ฿/kg", "Cost ฿/kg",
                           "Margin ฿/rai", "Margin %"], rows,
                 colw=[1.9, 1.6, 1.7, 1.5, 1.5, 2.1, 1.4], size=10, rh=0.295,
                 aligns=["l", "r", "r", "r", "r", "r", "r"]) + 0.16
    y += d.source(L, y, W, MIX, NAVY,
                  "Farm-gate prices MEASURED (NABC / OAE / OCSB). Costs MEASURED from OAE "
                  "cost-of-production returns — rice direct for crop year 2567/68, the others derived "
                  "from cost per tonne for 2568. Margin per rai is the arithmetic of the two and is "
                  "ESTIMATED.", size=9) + 0.18
    y += d.callout(L, y, W, "The three crops with no cost series are the three whose prices are falling",
                   f"Sugarcane (−17.9%), coconut (−70.9%) and pineapple (−20.0%) are the only crops "
                   f"here without an OAE cost series, so their margin cannot be computed. They are "
                   "Between them they are 12.2% of the country’s planted area. We can see the price "
                   "move and cannot see whether it has taken the grower below cost.",
                   tone="risk", size=10) + 0.14
    d.callout(L, y, W, "Why margin is the number that matters",
              "Netted of cost, a 24.3% move in crop prices becomes a 73.2% swing in crop income "
              "nationally — about three times the headline. Palm at 65.2% margin can absorb a price "
              "fall that would wipe out rubber at 24.9%, whose price is up 38%.", size=10)
    d.notes("If you present one agriculture slide, present this. Rubber's price is up 38% and it "
            "still carries the thinnest margin on the table.")

    # ================================================================ 8b who is growing at a loss
    CFI = load("crop_farmer_income.json")
    y = d.content("06 · Farming at a loss",
                  "Three of the five crops with full economics do not cover their own cost.")
    y += d.text(L, y, W, "OAE publishes yield, price and cost of production per crop. Netted out per "
                "household, and divided by the people in it, this is what a month of farming that "
                "crop is actually worth right now.", size=11, color=GREY, lh=15) + 0.16
    rows = []
    for c in sorted(CFI["crops"], key=lambda c: c["national"]["net_per_person_month"]):
        n = c["national"]
        rows.append([(c["crop_en"], True, NAVY),
                     (f"{n['households']:,}", False, NAVY),
                     (f"{n['area_rai'] / 1e6:.1f}M", False, NAVY),
                     (f"{c['price_thb_per_kg']:.2f}", False, NAVY),
                     (f"{n['yield_kg_per_rai']:,}", False, NAVY),
                     (f"{n['gross_per_person_month']:,.0f}", False, NAVY),
                     (f"{n['net_per_person_month']:+,.0f}", True,
                      RED if n["net_per_person_month"] < 0 else GREEN),
                     ("at a loss" if n["loss"] else "covers cost", True,
                      RED if n["loss"] else GREEN)])
    y += d.table(L, y, W, ["Crop", "households", "area (rai)", "฿/kg", "kg per rai",
                           "gross ฿/person/mo", "net ฿/person/mo", "verdict"], rows,
                 colw=[1.8, 1.5, 1.3, 1.0, 1.4, 2.0, 1.9, 1.53], size=10, rh=0.30,
                 aligns=["l", "r", "r", "r", "r", "r", "r", "l"]) + 0.16
    y += d.source(L, y, W, MIX, NAVY,
                  f"OAE — {CFI['crops'][0]['vintage']}. Households, area, yield, price and cost of "
                  "production all MEASURED. Net per person per month is our arithmetic on those "
                  "MEASURED inputs and is therefore ESTIMATED; national economics are applied flat "
                  "to every province except where a province publishes its own yield. Only these "
                  "five crops have a full cost series — sugarcane, coconut and pineapple do not, "
                  "which is why they are absent.", size=9) + 0.20
    cw2 = (W - 0.25) / 2
    d.callout(L, y, cw2, "Rice is the one that matters most, and it is negative",
              "4.53 million households — by far the largest farming population in the country — "
              "growing a crop that returns −฿444 per person per month once cost of production is "
              "netted off, on a price that is UP 12.4% year on year.\n\nA rising price and a "
              "negative margin at the same time is the whole argument for reading cost, not price. "
              "Rubber (−฿379) and cassava (−฿702) are in the same position.", tone="risk", size=10)
    d.callout(L + cw2 + 0.25, y, cw2, "Palm is the exception, and it is small",
              "Oil palm returns +฿7,486 per person per month — twelve times maize, the only other "
              "crop in the black. But it is 453,000 households against rice's 4.53 million, and it "
              "is concentrated in the South.\n\nSo the geography of who is under water is not "
              "subtle: rice and cassava provinces in Isan and the North are, palm provinces in the "
              "South are not. That is where a pre-emptive conversation is worth having.",
              tone="warn", size=10)
    d.notes("Say the rice line out loud: 4.5 million households, price up 12.4%, and still −฿444 a "
            "person a month after cost. Cost of production is the variable, not price.")

    # ================================================================ 9 income now, by region
    II = load("income_impact.json")
    y = d.content("07 · Income right now, by region",
                  "Monthly income by occupation, and which way it just moved.")
    y += d.text(L, y, W, "The annual farm survey is a national mean two crop years old. This is the "
                "current monthly picture: measured wage and income levels by region and occupation, "
                "with the move the latest price round has already put through them.",
                size=11, color=GREY, lh=15) + 0.16
    OCC = [("Agriculture", "Farming"), ("FactoryWorkers", "Factory"), ("Transport", "Transport"),
           ("SMEOwners", "SME"), ("OfficeStaff", "Office")]
    prov_by_region = {}
    for pname, pr in II["provinces"].items():
        prov_by_region.setdefault(pr["region"], []).append((pname, pr))
    rows = []
    for rg in II["regions"]:
        ps = prov_by_region.get(rg["key"], [])
        cells = [(rg["key"], True, NAVY)]
        for key, _ in OCC:
            vals = [p["occ"][key] for _, p in ps if p["occ"].get(key, {}).get("income")]
            inc = sum(v["income"] for v in vals) / len(vals) if vals else None
            dp = sum(v["d_pct"] for v in vals) / len(vals) if vals else None
            cells.append((f"{inc:,.0f}" if inc else "—", False, NAVY))
            cells.append((f"{dp:+.1f}%" if dp is not None else "—", True,
                          GREEN if (dp or 0) > 0.5 else (RED if (dp or 0) < -0.5 else GREY)))
        rows.append(cells)
    hdr = ["Region"]
    for _, lab in OCC:
        hdr += [f"{lab} ฿/mo", "move"]
    y += d.table(L, y, W, hdr, rows,
                 colw=[1.35] + [1.16, 0.95] * 5, size=9, rh=0.30,
                 aligns=["l"] + ["r", "r"] * 5) + 0.18
    y += d.source(L, y, W, MIX, NAVY,
                  "Income levels MEASURED — NSO Labour Force Survey wages and OAE farm income, by "
                  "province, in baht per month. The move is ESTIMATED: our model of what the latest "
                  "measured price round does to each occupation's income. Only farming and SME "
                  "income are modelled with a per-province driver — factory, transport and office "
                  "carry a single national move, which is why those three columns repeat down the "
                  "table. Region figures are the mean of their provinces.", size=9) + 0.20
    cw2 = (W - 0.25) / 2
    worst = sorted(II["regions"], key=lambda r: r["worst_occ"]["d_pct"])[0]
    d.callout(L, y, cw2, "Farming is the only occupation moving up, and it is the poorest",
              "Agriculture is the best-moving occupation in every region — the price round has been "
              "kind to it. It is also the lowest-paid: around ฿7,700–9,000 a month against ฿17,700 "
              "for the national wage headline.\n\nA good month on a very low base is not the same "
              "as resilience. This is the group with the least room between income and instalment, "
              "which is why it should be watched even when its arrow is green.", tone="warn", size=10)
    d.callout(L + cw2 + 0.25, y, cw2, "Transport is falling in every region",
              f"Transport is the worst-moving occupation across the board — {worst['key']} at "
              f"{worst['worst_occ']['d_pct']:+.2f}%. Fuel and freight rates move it, and neither is "
              "in the crop data.\n\nIt is also an occupation whose vehicle IS the income, so a "
              "squeeze there has a different character: the asset cannot be given up without ending "
              "the earning. That is the population where an early conversation is worth more than a "
              "late collection.", tone="risk", size=10)
    d.notes("This replaces the 2023 annual national survey with current monthly figures by region "
            "and occupation. Farming up but poorest; transport down everywhere. Both are reasons to "
            "make contact early rather than wait.")

    # ================================================================ 10 drought
    y = d.content("08 · Drought", "36.4% of districts are dry, and it lands on the rice belt.")
    y += d.cards(L, y, W, [
        ("Districts in drought", f"{mn['n_dry']}",
         f"of {mn['n_districts']} ({mn['dry_share_pct']}%) · SPEI mean {mn['spei_mean']:.2f}", RED),
        ("Extreme band", f"{mn['n_extreme']}", "districts at the extreme drought band", RED),
        ("District-crop cells", "318", "of 3,295 measured cells at severe drought or worse", GOLD),
        ("Double-stressed", "0", "on the world-price test — see the note below", GOLD),
    ], cols=4, ch=1.10) + 0.20
    ac = load("amphoe_crops.json")
    rows = [[(h["province_th"], True, NAVY), h["amphoe_th"], h["crop_th"],
             (f"{h['planted_rai']:,.0f}", False, NAVY), (f"{h['spei']:.2f}", True, RED),
             (h["drought"], False, RED)] for h in ac["hotspots"][:6]]
    y += d.table(L, y, W, ["Province", "District", "Crop", "Planted (rai)", "SPEI", "Band"], rows,
                 colw=[2.2, 2.2, 2.4, 2.0, 1.4, 1.6], size=10, rh=0.288,
                 aligns=["l", "l", "l", "r", "r", "l"]) + 0.16
    y += d.source(L, y, W, MIX, NAVY,
                  "Planted area MEASURED (OAE — 3,295 amphoe crop rows). Drought is a MODELLED SPEI "
                  "index derived from rainfall and evapotranspiration: the best national-coverage "
                  "signal available, but nobody has walked those districts.", size=9) + 0.16
    d.callout(L, y, W, "สุพรรณบุรี is the coincidence to watch",
              "Drought 0.95 — effectively the top of the scale — and a third of its planted area is "
              "sugarcane, at a −17.9% farm gate. The formal double-stress count reads zero because "
              "that test is scored on world prices; on the Thai farm gate this province is drought "
              "and falling price at once.", tone="warn")
    d.notes("Zero double-stressed provinces is a world-price result. สุพรรณบุรี is the worked "
            "counter-example — say it rather than presenting a clean zero.")

    # ============================================== 10b where a pre-emptive conversation is worth it
    PSI = load("province_stress_index.json")
    y = d.content("09 · Where to reach out first",
                  "Ranking provinces on stress nobody can see from a payment file.")
    y += d.text(L, y, W, "Four independent external signals, none of them a repayment record: how "
                "indebted the household already is, how many people cannot find work, whether the "
                "crop underneath the province covers its cost, and whether the rain arrived. Three "
                "or more tripped is a province to contact before it deteriorates, not after.",
                size=11, color=GREY, lh=15) + 0.16
    croploss = {c["crop_en"]: c["national"]["loss"] for c in CFI["crops"]}
    CROPKEY = {"rice": "Rice", "rubber": "Rubber", "oilpalm": "Oil palm",
               "cassava": "Cassava", "maize": "Maize"}
    rows = []
    for p in PSI["provinces"][:8]:
        nm2 = p["province"]
        ip = II["provinces"].get(nm2, {})
        mix = ip.get("crop_mix") or {}
        lead = max(mix.items(), key=lambda kv: kv[1])[0] if mix else None
        leadname = CROPKEY.get(lead, lead or "—")
        lossy = croploss.get(leadname)
        fbp = FB["provinces"].get(nm2, {})
        rain = fbp.get("rain_pct_of_normal")
        agri = (ip.get("occ", {}).get("Agriculture") or {})
        flags = sum([p["debt_to_income"] >= 1.0, p["unemployment_rate"] >= 2.0,
                     bool(lossy), bool(rain is not None and rain < 90)])
        rows.append([(nm2, True, NAVY), (p["region"], False, GREY),
                     (f"{100 * p['debt_to_income']:.0f}%", True,
                      RED if p["debt_to_income"] >= 1.0 else NAVY),
                     (f"{p['unemployment_rate']:.2f}%", True,
                      RED if p["unemployment_rate"] >= 2.0 else NAVY),
                     (f"{leadname} {100 * mix.get(lead, 0):.0f}%" if lead else "—", False, NAVY),
                     ("below cost" if lossy else ("covers cost" if lossy is False else "—"), True,
                      RED if lossy else (GREEN if lossy is False else GREY)),
                     (f"{rain:.0f}%" if rain is not None else "—", True,
                      RED if (rain is not None and rain < 90) else NAVY),
                     (f"{agri['income']:,.0f}" if agri.get("income") else "—", False, NAVY),
                     (f"{flags} of 4", True, RED if flags >= 3 else GOLD)])
    y += d.table(L, y, W, ["Province", "region", "household debt", "unemployment", "lead crop",
                           "crop economics", "rain vs normal", "farm ฿/mo", "tripped"], rows,
                 colw=[1.85, 1.15, 1.5, 1.5, 1.7, 1.5, 1.4, 1.05, 0.78], size=9, rh=0.278,
                 aligns=["l", "l", "r", "r", "l", "l", "r", "r", "r"]) + 0.16
    y += d.source(L, y, W, MIX, NAVY,
                  "Household debt-to-income MEASURED (NSO SES 2566, debt as a share of ANNUAL "
                  "income — above 100% means more debt than a year of earnings). Unemployment "
                  "MEASURED (NSO LFS, by province). Crop mix MEASURED (OAE planted area); crop "
                  "economics ESTIMATED from OAE cost of production. Rainfall MEASURED against the "
                  "long-run normal. The eight shown are the worst of 77 on the combined debt + "
                  "unemployment rank; the signal count is a plain tally, not a weighted score.",
                  size=9) + 0.18
    cw2 = (W - 0.25) / 2
    d.callout(L, y, cw2, "The stressed list is the rice list",
              "Every province in the top eight leads on a crop that does not cover its cost, and in "
              "seven of the eight that crop is rice. Isan and the North dominate; the one southern "
              "entry, นราธิวาส, is rubber — also below cost, and on the lowest farm income on the "
              "table at ฿2,742 a month.\n\nอำนาจเจริญ trips all four: debt at 114% of a year's "
              "income, unemployment 2.84%, rice below cost, and rain at 86% of normal.",
              tone="risk", size=10)
    d.callout(L + cw2 + 0.25, y, cw2, "What this list is, and what it is not",
              "It is where external conditions say a household is likely to be squeezed, before that "
              "shows up as a missed payment. Built entirely from published statistics, so it points "
              "at provinces, not at people — turning it into names is the Assistance tab's job, and "
              "it should be crossed with who is currently paying before anyone is contacted.\n\nIt "
              "is not a distress list. Most households in these provinces are paying normally. The "
              "value is timing: reaching someone while restructuring is still cheap.",
              tone="warn", size=10)
    d.notes("This is the slide the assistance programme comes out of. Four independent external "
            "signals; three or more tripped is the shortlist. Say clearly that it points at "
            "geographies, not people, and that Assistance does the name-level work.")

    # ================================================================ 11 collateral divider
    d.divider("10 · Collateral", "This is the half with a decision attached.",
              "We lend against titles, so the used-vehicle market is an external condition that "
              "prices our security directly. Four things are moving at once: what a used vehicle is "
              "worth, how many are entering the pool, which nameplates they are, and how easily any "
              "of them can be sold on. A brand with no Thai residual history is a recovery "
              "assumption nobody can make yet.")
    d.notes("Slow down here. Everything before was conditions on the borrower; this is conditions on "
            "the security, which is the part with an underwriting consequence.")

    # ================================================================ 12 resale value
    UV = load("used_vehicle_value.json")["series"]
    y = d.content("10a · Resale value", "The fall has stopped. The level has not recovered.")

    def win(key, n):
        """Change over the last n months of the 36-month sparkline, in index points and percent."""
        v = UV[key]["sparkline"]["values"]
        a, b = v[-1 - n], v[-1]
        return b - a, 100 * (b / a - 1)

    rows = []
    for key, lab in [("truck", "Pickup (รถกระบะ)"), ("car", "Passenger car"),
                     ("overall", "All used vehicles")]:
        s = UV[key]
        d6, p6 = win(key, 6)
        d12, p12 = win(key, 12)
        t12 = s["trailing_12m"]
        rows.append([(lab, True, NAVY),
                     (f"{s['latest']['value']:.1f}", True, NAVY),
                     (f"{p6:+.1f}%", True, GREEN if p6 > 0 else RED),
                     (f"{p12:+.1f}%", True, GREEN if p12 > 0 else RED),
                     (f"{t12['low']['value']:.1f}", False, NAVY),
                     (f"{t12['high']['value']:.1f}", False, NAVY),
                     (f"{s['vs_2015_base_pp']:+.1f}", True, RED),
                     (f"{s['change_since_peak_pct']:+.1f}%", True, RED)])
    y += d.table(L, y, W, ["BoT used-vehicle price index", "latest (2026-05)", "6-month move",
                           "12-month move", "12m low", "12m high", "vs 2015 base",
                           "off all-time peak"], rows,
                 colw=[2.5, 1.6, 1.4, 1.5, 1.1, 1.1, 1.5, 1.73], size=10, rh=0.315,
                 aligns=["l", "r", "r", "r", "r", "r", "r", "r"]) + 0.20
    uv = uvpi_series()
    d.linechart(L, y, 7.55, 2.20, [("Pickup", RED, uv["truck"]), ("Car", NAVY, uv["car"])],
                ylab="Index, 2015 = 100 · monthly, 2011-01 → 2026-05", baseline=100,
                ymin=50, ymax=150,
                xticks=[(2011, "2011"), (2015, "2015"), (2019, "2019"), (2022, "2022"), (2026, "2026")])
    t6, t12 = win("truck", 6)[1], win("truck", 12)[1]
    c6, c12 = win("car", 6)[1], win("car", 12)[1]
    d.callout(L + 7.75, y, W - 7.75, "The two windows say different things — both are true",
              f"Over twelve months pickup is flat at {t12:+.1f}% and cars are down {c12:+.1f}%. Over "
              f"six months both are sharply up — pickup {t6:+.1f}%, cars {c6:+.1f}% — because the "
              "series bottomed in November and has climbed since.\n\nSo the fall has stopped; the "
              "level has not recovered. Pickup still sits "
              f"{UV['truck']['vs_2015_base_pp']:.1f} points below its own 2015 base against "
              f"{UV['car']['vs_2015_base_pp']:.1f} for cars, and {UV['truck']['change_since_peak_pct']:.0f}% "
              "off its 2012 peak. The gap between the two lines is recent: they sat on top of each "
              "other through 2013–2021 and separated only from 2022. Advance rates calibrated on "
              "pre-2022 behaviour are calibrated against a market that no longer exists.",
              tone="risk", size=10)
    y += 2.20 + 0.16
    d.source(L, y, W, MEAS, GREEN,
             "Bank of Thailand used-vehicle price index (EC_EI_040), 185 monthly observations; the "
             "6- and 12-month moves are computed off the published monthly series. Both rebased so "
             "their own 2015 average = 100. The pickup series is confirmed pickup trucks (รถกระบะ), "
             "not heavy commercial — BoT’s 2019 Stat-Horizon methodology paper. Latest month "
             "preliminary.", size=9)
    d.notes("Lead with the two windows: pickup +12.5% over six months but −0.4% over twelve, so the "
            "fall has stopped rather than reversed. Then the level — still 33 points below its own "
            "2015 base. Direction improving, level still bad.")

    # ================================================================ 13 registration windows
    y = d.content("10b · Collateral supply", "Two vehicle markets, moving opposite ways.")
    y += d.text(L, y, W, "DLT first registrations on AutoX’s own pickup definition — any pickup or "
                "PPV nameplate, in any registration class. Read on trailing windows rather than "
                "calendar years: the last six months say something the twelve-month figure hides.",
                size=11, color=GREY, lh=15) + 0.16
    Wd = VM["windows"]

    # The six-month window ends on 2026-01, a month the pipeline itself flags. Both the pickup's
    # positive slope and the car's +34.3% are computed WITH it, so the trend column is re-derived
    # without it — the chart below makes the reason visible before the callouts make the argument.
    m6 = Wd["m6"]
    last = m6["to"] in m6["contains_flagged_months"]

    def wrow(basis, label):
        w6, m12 = m6[basis], Wd["m12"][basis]
        y6 = 100 * (w6["units"] / w6["prior_units"] - 1)
        y12 = 100 * (m12["units"] / m12["prior_units"] - 1)
        sl = ols_slope(w6["monthly"][:-1] if last else w6["monthly"])
        return [(label, True, NAVY),
                (f"{m12['units']:,}", False, NAVY),
                (f"{y12:+.1f}%", True, GREEN if y12 > 0 else RED),
                (f"{w6['units']:,}", False, NAVY),
                (f"{y6:+.1f}%", True, GREEN if y6 > 0 else RED),
                (f"{sl:+,.0f}", True, GREEN if sl > 0 else RED)]
    y += d.table(L, y, W, ["", "12-month units", "12m YoY", "6-month units †", "6m YoY †",
                           "6m trend ex-flagged, units/mo"],
                 [wrow("pu", "Pickup + PPV"), wrow("pa", "Passenger car")],
                 colw=[2.6, 2.1, 1.6, 2.1, 1.6, 2.4], size=11, rh=0.36,
                 aligns=["l", "r", "r", "r", "r", "r"]) + 0.06
    y += d.text(L, y, W, "† the six-month window contains flagged months — "
                f"{', '.join(m6['contains_flagged_months'])}. The trend column strips the flagged "
                "January; the two YoY columns do not.", size=9, color=GREY, lh=12) + 0.18
    months = [f"{m6['from'][:4]}-{m:02d}" for m in
              [8, 9, 10, 11, 12]] + [m6["to"]]
    cw = (W - 0.25) / 2
    for i, (basis, lab, col) in enumerate([("pu", "Pickup + PPV", RED), ("pa", "Passenger car", NAVY)]):
        mo = m6[basis]["monthly"]
        d.text(L + i * (cw + 0.25), y - 0.02, cw,
               f"{lab} — registrations by month, {m6['from']} → {m6['to']}",
               size=9.5, bold=True, color=NAVY)
        d.bars(L + i * (cw + 0.25), y + 0.20, cw, 1.62,
               [(mm[2:], v, j == len(mo) - 1) for j, (mm, v) in enumerate(zip(months, mo))],
               color=col, fmt=lambda v: f"{v / 1000:,.1f}k")
    y += 0.20 + 1.62 + 0.20

    y12pa = 100 * (Wd["m12"]["pa"]["units"] / Wd["m12"]["pa"]["prior_units"] - 1)
    pu6, pa6 = m6["pu"]["monthly"], m6["pa"]["monthly"]
    pu_ex = ols_slope(pu6[:-1]) if last else ols_slope(pu6)
    pa_ex_units = (sum(pa6[:-1]) / (len(pa6) - 1)) + sum(pa6[:-1]) if last else sum(pa6)
    pa_ex_yoy = 100 * (pa_ex_units / m6["pa"]["prior_units"] - 1)
    ch = d.callout(L, y, cw, "Why any “positive pickup trend” is an artifact",
                   "Look at the left chart. Five months fall steadily — 14.9k, 15.3k, 13.2k, 12.3k, "
                   f"11.4k — then January jumps to 18.3k. Fit a line through all six and that one "
                   f"bar drags the slope to {m6['pu']['slope_units_per_month']:+,.0f} a month, which "
                   "reads as a recovery. Fit it through the five months before January and it is "
                   f"{pu_ex:+,.0f} a month.\n\nJanuary is a flagged month, not demand: registrations "
                   "pulled forward before an incentive deadline. Pickups are still falling at "
                   "roughly a thousand units a month.", tone="risk", size=10)
    d.callout(L + cw + 0.25, y, cw, "Two thirds of the car boom is one month",
              f"January 2026 ran +54% in cars while motorcycles were flat — registrations pulled "
              f"forward ahead of an incentive deadline, not demand appearing. Replace that month "
              f"with the average of the other five and six-month growth falls from "
              f"{100 * (m6['pa']['units'] / m6['pa']['prior_units'] - 1):+.1f}% to "
              f"{pa_ex_yoy:+.1f}%. The twelve-month {y12pa:+.1f}% is the safer number.",
              tone="warn", size=10)
    y += ch + 0.16
    d.source(L, y, W, MIX, NAVY,
             "Registrations MEASURED — DLT gdcatalog first registrations at brand and model grain, 48 "
             "months from 2022-01. A month holding under 20% of the median month is treated as a "
             "catalog stub and excluded; a month moving more than 40% year on year is flagged and "
             "kept, never dropped. The ex-January figures are our own arithmetic on that measured "
             "series — ESTIMATED, a judgement about which month to trust.", size=9)
    d.notes("Correction worth making out loud: the pickup six-month slope is NOT a recovery — strip "
            "the flagged January and it is about −986 units a month. Same month inflates the car "
            "boom from +11% to +34%. Quote the twelve-month windows.")

    # ================================================================ 14 concentration
    y = d.content("10c · Brand concentration", "Two vehicle markets, and only one is holding its shape.")
    pu12, pa12 = Wd["m12"]["pu"], Wd["m12"]["pa"]
    pl = VM["plates_last12"]
    pk, pv = pl["pickup"]["top"][:2], pl["ppv"]["top"][:2]
    y += d.cards(L, y, W, [
        ("Top 2 pickup brands", f"{pu12['major_share_pct']:.1f}%",
         f"{' + '.join(pu12['majors'])} · was {pu12['prior_major_share_pct']:.1f}% a year ago", GOLD),
        ("Top 2 car brands", f"{pa12['major_share_pct']:.1f}%",
         f"{' + '.join(pa12['majors'])} · was {pa12['prior_major_share_pct']:.1f}% — "
         f"{pa12['prior_major_share_pct'] - pa12['major_share_pct']:.1f} points gone in a year", RED),
        ("Biggest pickup nameplate", f"{pk[0]['yoy_pct']:+.1f}%",
         f"{pk[0]['plate']} · {pk[0]['share_pct']:.1f}% of pickups · {pk[1]['plate']} "
         f"{pk[1]['yoy_pct']:+.1f}%", RED),
        ("Fastest-growing PPV", "+802%",
         f"TANK 300 · from 650 to 5,865 units · {pv[0]['plate']} {pv[0]['yoy_pct']:+.1f}%", GOLD),
    ], cols=4, ch=1.16) + 0.20
    cw2 = (W - 0.25) / 2
    # Brands, not nameplates, and the two markets side by side — the concentration argument only
    # lands when you can see 78.7% on the left against 48.5% on the right.
    def brow(b, w):
        maj = b["brand"] in w["majors"]
        return [(b["brand"], maj, NAVY),
                ("incumbent" if maj else "", False, GREY),
                (f"{b['units']:,}", False, NAVY),
                (f"{b['share_pct']:.2f}%", True, NAVY if maj else RED)]
    d.text(L, y, cw2, f"Pickup + PPV — {pu12['units']:,} registered in 12 months",
           size=9.5, bold=True, color=NAVY)
    d.text(L + cw2 + 0.25, y, cw2, f"Passenger car — {pa12['units']:,} registered in 12 months",
           size=9.5, bold=True, color=NAVY)
    y += 0.24
    d.table(L, y, cw2, ["PU + PPV brand", "", "12-month units", "share"],
            [brow(b, pu12) for b in pu12["top_brands"][:8]],
            colw=[2.2, 1.5, 1.6, 0.79], size=9.5, rh=0.268, aligns=["l", "l", "r", "r"])
    y += d.table(L + cw2 + 0.25, y, cw2, ["Car brand", "", "12-month units", "share"],
                 [brow(b, pa12) for b in pa12["top_brands"][:8]],
                 colw=[2.2, 1.5, 1.6, 0.79], size=9.5, rh=0.268,
                 aligns=["l", "l", "r", "r"]) + 0.16
    y += d.source(L, y, W, MEAS, GREEN,
                  "DLT first registrations at nameplate grain, trailing 12 months, NATIONAL only — "
                  "no province column exists. First registrations are the FUTURE collateral pool, "
                  "not a stock of what is on the road, and not used-vehicle sales.", size=9) + 0.18
    d.callout(L, y, W, "The two markets are moving in opposite directions, and that is the point",
              f"Pickup stays concentrated: Toyota and Isuzu hold {pu12['major_share_pct']:.1f}% of "
              f"new pickups, down only {pu12['prior_major_share_pct'] - pu12['major_share_pct']:.1f} "
              "points in a year, and the nearest challenger is GWM at 3.5%. Every pickup nameplate "
              "is shrinking, so the pool gets smaller without changing shape — residual values there "
              f"stay predictable.\n\nCars are the opposite: {pa12['prior_major_share_pct'] - pa12['major_share_pct']:.1f} "
              "points surrendered in one year to BYD, MG, Jaecoo, AION and Deepal, brands with "
              "little or no Thai residual record. Those vehicles age into the used pool over the "
              "next five years and there is no history to price them against.", tone="risk")
    d.notes("Every pickup nameplate on the left table is down double digits — there is no pickup "
            "nameplate growing. The commercial point: we know what a five-year-old Hilux is worth. "
            "We do not know what a five-year-old BYD or Jaecoo is worth, and a fifth of new cars "
            "are now those.")

    # ================================================================ 17 recovery depth + EV
    y = d.content("10d · The second-hand market", "How deep the market is that a title sells into.")
    fc = {f["key"]: f for f in CB["fleet_classes"]}
    y += d.cards(L, y, W, [
        ("Pickup stock", f"{fc['pickup']['latest'] / 1e6:.2f}M",
         f"registered pickups nationally · {fc['pickup']['yoy_pct']:+.2f}% YoY", RED),
        ("Car stock", f"{fc['car']['latest'] / 1e6:.2f}M",
         f"{fc['car']['yoy_pct']:+.2f}% YoY · +{fc['car']['since_2563_pct']:.1f}% since 2563", GREEN),
        ("Diesel share", f"{mn['diesel_share_pct']:.1f}%",
         f"of the {mn['fleet_total'] / 1e6:.1f}M fleet — what the market runs on today", NAVY),
        ("BEV share", f"{mn['bev_pct']:.2f}%",
         f"electrified {mn['electrified_pct']:.2f}% — not a factor this quarter", GOLD),
    ], cols=4, ch=1.12) + 0.20
    # How deep the second-hand market is, region by region — this is the market a repossessed title
    # has to be sold into, so it is the external half of any recovery assumption.
    rows = []
    for uf in CB["used_flow"]:
        pshare = 100 * uf["pickup"]["processed"] / uf["all"]["processed"]
        rows.append([(uf["region"], True, NAVY),
                     (f"{uf['all']['processed'] / 1e6:.2f}M", False, NAVY),
                     (f"{pshare:.1f}%", False, NAVY),
                     (f"{uf['pickup']['transferred']:,}", False, NAVY),
                     (f"{uf['pickup']['transfer_rate'] * 100:.2f}%", True,
                      RED if uf["pickup"]["transfer_rate"] < 0.06 else NAVY),
                     (f"{uf['car']['transfer_rate'] * 100:.2f}%", False, NAVY),
                     (f"{uf['moto']['transfer_rate'] * 100:.2f}%", False, NAVY)])
    y += d.table(L, y, W, ["Region", "vehicles registered", "of them pickups",
                           "pickups changing hands", "pickup turnover", "car turnover",
                           "motorcycle turnover"], rows,
                 colw=[1.9, 1.9, 1.7, 2.2, 1.7, 1.5, 1.53], size=10, rh=0.30,
                 aligns=["l", "r", "r", "r", "r", "r", "r"]) + 0.16
    y += d.source(L, y, W, MEAS, GREEN,
                  "DLT registered stock and ownership-transfer counts by region and vehicle class, "
                  "plus MOT fleet totals. Turnover is transfers divided by registered stock — how "
                  "much of the parc changes hands in a year, which is the depth a repossessed title "
                  "has to be sold into.", size=9) + 0.20
    cw2 = (W - 0.25) / 2
    d.callout(L, y, cw2, "Pickups are the slowest-moving thing on the road",
              "Transfers run 5.2–7.6% of registered pickups a year against 5.6–10.2% for cars — "
              "pickup is the slowest-turning class in every single region, and the East is the "
              "extreme at 5.21%.\n\nA thinner secondary market is a longer disposal and a wider "
              "discount, and it compounds the resale-value slide: the asset that fell furthest is "
              "also the one hardest to sell.", tone="risk", size=10)
    d.callout(L + cw2 + 0.25, y, cw2, "Electrification is a clock, not a problem",
              "BEVs are 0.95% of the fleet and electrified vehicles 2.57%. Nothing on the road today "
              "is priced by that.\n\nBut a title has a five-to-ten-year resale tail, and the fleet "
              "mix that sets used values in 2032 is being registered now — a fifth of new cars are "
              "already brands with no Thai residual history. The question it raises is how to price "
              "a title we cannot yet benchmark, not what to do this quarter.",
              tone="warn", size=10)
    d.notes("Turnover is the depth a repossession is actually sold into. Pickup is the "
            "slowest-turning class in every region, and the East is the extreme.")

    # ================================================================ 18 conditions at our grain
    y = d.content("11 · Conditions on the ground", "Five lenses, from the country down to a district.")
    y += d.cards(L, y, W, [
        ("Labour force", f"{mn['labor_force_k'] / 1000:.1f}M",
         f"unemployment {mn['unemployment_pct']}% · seasonal idle {mn['seasonal_share_pct']}% "
         f"({mn['seasonal_waiting_k']:.0f}k waiting)", NAVY),
        ("Informality", "63.2%",
         "of employment has no payslip or social cover — our core demographic (2024)", GOLD),
        ("Vehicle fleet", f"{mn['fleet_total'] / 1e6:.1f}M",
         f"diesel {mn['diesel_share_pct']:.1f}% · electrified {mn['electrified_pct']:.2f}% · BEV "
         f"{mn['bev_pct']:.2f}%", NAVY),
        ("Districts dry", f"{mn['dry_share_pct']}%",
         f"{mn['n_dry']} of {mn['n_districts']} · {mn['flood_high']} of {mn['flood_stations']} river "
         f"stations above high mark", RED),
        ("Household debt", thb(mn["debt_hh_thb"]),
         f"per indebted household · {mn['hh_with_debt_pct']}% carry debt · income "
         f"{thb(mn['income_hh_thb_month'])}/month", GOLD),
        ("No cushion", f"{mn['cushion_lt3mo_pct']:.0f}%",
         f"could not cover three months without income · {mn['vulnerable_hh_pct']}% classed "
         "vulnerable", RED),
    ], cols=3, ch=1.16) + 0.18
    y += d.source(L, y, W, MEAS, GREEN,
                  "NSO Labour Force Survey · ILOSTAT mirror of Thailand’s official submissions · DLT "
                  "registry · MOT · DBD business registrations · ThaiWater telemetry · BoT. Every "
                  "lens rolls national → region → province → district on its own correct weight — "
                  "labour force, fleet stock, district count. Never a plain average of provinces.",
                  size=9) + 0.18
    d.callout(L, y, W, "Read 0.94% unemployment together with 63.2% informality, never instead of it",
              "Headline unemployment is structurally near zero in Thailand because informal work "
              "absorbs the slack. A borrower who loses formal work does not appear in the "
              "unemployment number — they appear in the informal count, on a lower and less "
              "predictable income. The unemployment rate is not a stress signal for this book. "
              "Informality, the seasonal-idle share and the cushion figure are.", tone="warn")
    d.notes("This drill goes from a national number to a district without changing instrument. "
            "If someone reaches for 0.94% unemployment as evidence the borrower is fine, this is the "
            "slide.")

    # ================================================================ 19 live
    y = d.content("12 · Live", "The one feed that changes daily.")
    y += d.text(L, y, W, "Everything else on this tab is monthly or quarterly. River levels and "
                "rainfall are pulled every day from ThaiWater — the early-warning layer under the "
                "drought and flood picture.", size=11, color=GREY, lh=15) + 0.16
    y += d.cards(L, y, W, [
        ("Stations above high mark", f"{mn['flood_high']}",
         f"of {mn['flood_stations']} ({mn['flood_high_pct']}%) · up from 84 on 11 July", RED),
        ("Provinces with heavy rain", "31", "latest reading · 2026-08-03", GOLD),
        ("Heaviest 24h gauge", "180mm", "2026-08-03 · the 08-02 reading hit 608mm", NAVY),
        ("Structural flood exposure", "34%",
         "685 of 2,015 branches on ground that flooded ≥7 of 12 yrs", GOLD),
    ], cols=4, ch=1.12) + 0.20
    y += d.source(L, y, W, MEAS, GREEN,
                  "ThaiWater live telemetry, pulled daily and accumulated — nothing interpolated, a "
                  "missed pull leaves a gap rather than an invented point. Structural flood exposure "
                  "is the GISTDA 1:50,000 repeated-flooding census, 2005–2016.", size=9) + 0.20
    d.callout(L, y, W, "Two different things, deliberately kept apart",
              "The live pulse says what is happening this week. The structural census says which "
              "ground floods repeatedly whatever the weather is doing today. The second is a hazard "
              "flag — did the ground flood, how often — and explicitly not a flooded-area or loss "
              "estimate, because the source’s per-event polygons overlap and any area total drawn "
              "from them would be wrong.")
    d.notes("34% of branches on repeatedly-flooded ground is a hazard flag on the footprint we "
            "already run. Not a loss estimate, not an argument to close anything.")

    # ================================================================ 20 so what
    y = d.content("13 · So what", "Four things the macro picture asks of us.")
    y += d.qa(L, y, W, [
        ("Contact the four-signal provinces before they miss",
         "อำนาจเจริญ trips all four external signals and สุโขทัย three. Both are rice provinces with "
         "household debt above three quarters of a year’s income, rain below normal and a crop that "
         "does not cover its cost. Cross that list with who is CURRENT and make contact while a "
         "restructure is still cheap — the whole point is to arrive before the arrears do."),
        ("Treat the transport occupation as its own programme",
         "Transport is the only occupation falling in every region, and it is the one where the "
         "vehicle IS the income — the asset cannot be surrendered without ending the earning. Fuel "
         "and freight rates drive it and appear in no crop series, so it needs watching separately "
         "from the farm belts."),
        ("Reprice against a used-vehicle market that changed in 2022",
         "Pickup resale is 33 points below its own 2015 base and the slowest-turning class in every "
         "region; the six-month bounce has not recovered the level. Separately, a fifth of new cars "
         "are brands with no Thai residual record, so there is a pricing decision for titles that "
         "cannot yet be benchmarked."),
        ("Read cost of production, not the price headline",
         "Rice prices are UP 12.4% and rice still returns −฿444 per person per month after cost. "
         "Three of the five crops with a full cost series are below cost; the three crops whose "
         "prices are FALLING have no cost series at all, so we cannot yet see how far under they "
         "are. Ask OAE for it, or infer it."),
    ], qw=4.30, size=11) + 0.20
    y += d.callout(L, y, W, "Scope, stated",
                   "Everything above is external data — published statistics about the economy, the "
                   "crops and the used-vehicle market. It points at regions, provinces and the "
                   "districts under them, never at a person. Turning a geography into a call list "
                   "is the Assistance tab’s job and belongs in that conversation, with the book "
                   "beside it. Nothing here is an argument to open, close or expand anything.") + 0.16
    d.text(L, y, W, "Vintages — world prices 2026M06 · Thai farm gate 2026-08-02 · drought "
           "2026-06-21 · CPI 2026-05 · GDP 2026-Q1 · IMF WEO 2026 · resale index 2026-05 · "
           f"registrations to {VM['meta']['latest_month']} · crop cost of production "
           f"{CFI['crops'][0]['vintage'][:4]} · household debt NSO SES 2566 · telemetry 2026-08-03.",
           size=9, color=GREY, lh=12.5)
    d.notes("Close on scope: external conditions on the network we already run — no open, close or "
            "expand recommendation, and no book readout, by design.")

    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--preview", action="store_true", help="render PNG thumbnails to check fit")
    a = ap.parse_args()

    d = build()
    out = Path(a.out) / "mcom-2026-08-05-macro.pptx"
    out.parent.mkdir(parents=True, exist_ok=True)
    d.save(out)
    print(f"wrote {out}  ({len(d.slides)} slides, {out.stat().st_size // 1024} KB)")
    print("Kanit metrics:", "available" if TX.ok else "NOT FOUND — fit unchecked")
    if d.findings:
        print(f"\n{len(d.findings)} fit finding(s):")
        for f in d.findings:
            print("  -", f)
    else:
        print("fit: no findings")
    if a.preview:
        d.preview(Path(a.out) / "preview")
        print("preview written")


if __name__ == "__main__":
    main()
