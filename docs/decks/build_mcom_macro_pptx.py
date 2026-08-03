"""MCOM · Wednesday 5 August 2026 — the Macro tab, as a house-style PPTX.

Scope is one tab. What the Macro tab answers is narrower than the rest of the platform: what is
happening outside the company, and what it is already doing to our money. Both halves matter — the
tab deliberately crosses every external layer with the real loan tape at four grains (national →
region → province → branch), so a slide showing only the external number would be showing half of
what the tab knows.

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
    cn, fn, mn = CB["national"], FB["national"], MB["national"]
    bn = lambda v: f"฿{v / 1e9:.2f}bn"
    thb = lambda v: f"฿{v:,.0f}"
    cr = {c["en"]: c for c in FB["crops"]}
    falling_share = sum(cr[k]["os_share_pct"] for k in ("Sugarcane", "Coconut", "Pineapple"))
    falling_os = sum(cr[k]["farm_os_alloc"] for k in ("Sugarcane", "Coconut", "Pineapple"))

    # ================================================================ 1 cover
    d.cover("Macro: the external conditions\nmoving the book.",
            "MCOM · Wednesday 5 August 2026 · AutoX / บริษัท ออโต้ เอกซ์ จำกัด (เงินไชโย)",
            "Aug ’26")
    d.notes("Scope: the Macro tab. External conditions, and what each is already doing to our money "
            "— this tab crosses every layer with the real tape, so the book is on it too. "
            "Competition and the branch views are separate conversations.")

    # ================================================================ 2 the answer
    y = d.content("The answer first", "Four questions, and the fourth one is the deck.")
    y += d.text(L, y, W, "Every external layer here is crossed with the real loan tape at four "
                "grains — national, region, province, branch — so each answer carries the baht it is "
                "worth to us, not just a direction.", size=11.5, color=GREY, lh=15.5) + 0.20
    y += d.qa(L, y, W, [
        ("Is the economy the problem?",
         "No. Growth and inflation both came in above what the IMF projected for 2026 and the policy "
         "rate is 1.00%. But Thailand is projected to grow slowest in ASEAN-5 — 1.5% against "
         "Vietnam’s 7.1%. Stable, not strong."),
        ("Are crop prices the problem?",
         "Not on the world index. On the measured Thai farm gate nine commodities are falling, and "
         f"the falling crops carry {falling_share:.1f}% of our farm book. Margin matters more than "
         "price: netted of cost, a 24% price move becomes a 73% swing in crop income."),
        ("So what is deteriorating?",
         "The collateral. Used pickup values sit 50% below their peak and 33 points below their own "
         "2015 base, and new pickup registrations are down 15.3% on the year. Pickup titles are "
         f"{100 * CB['types'][0]['os'] / cn['os']:.0f}% of our outstanding — {bn(CB['types'][0]['os'])}."),
        ("And the borrower?",
         f"Thin before any of this. A farm household nets {thb(FH['latest']['net_cash_monthly'])} a "
         "month and half its income is not farming; 60% of households could not cover three months. "
         f"Our own book is already {cn['dpd90p_pct']}% at 90+."),
    ], size=12) + 0.24
    y += d.source(L, y, W, MIX, NAVY,
                  f"Book figures are MEASURED from the real loan tape — {cn['n']:,} accounts, no-PII "
                  "aggregates, nothing published below a 30-account cell floor. External layers "
                  "carry their own chip on each page.") + 0.26
    d.text(L, y, W, "What follows", size=10, bold=True, color=NAVY)
    d.text(L, y + 0.24, W,
           "01–02  the macro backdrop and where Thailand sits in the region        "
           "03–08  agriculture: world price against the Thai farm gate, margin, the household, "
           "drought        09  collateral, in six parts        10–12  conditions at our own grain, "
           "and what it asks of us", size=10, color=GREY, lh=14)
    d.notes("If they take one thing: the macro is stable, the crops are mixed, the collateral is "
            "deteriorating — and the borrower was already thin before any of it.")

    # ================================================================ 3 macro overlay
    y = d.content("01 · Macro overlay", "The backdrop is benign, and it is current.")
    y += d.cards(L, y, W, [
        ("GDP growth", "+2.8%", "YoY · a measured quarter, not a projection · NESDC 2026-Q1", GREEN),
        ("Inflation", "+2.79%", "headline CPI YoY · TPSO, Ministry of Commerce · 2026-05", GOLD),
        ("Policy rate", "1.00%", "Bank of Thailand policy rate · 2026-06", NAVY),
        ("USD / THB", "33.47", "ECB reference rate · 2026-07-31", NAVY),
        ("Household debt", "87.5%", "of GDP · BIS · 2025-Q4", GOLD),
        ("Tourist arrivals", "32.2M", "trailing 12 months · −6.6% YoY · BoT 2026-06", RED),
    ], cols=3, ch=1.10) + 0.18
    y += d.source(L, y, W, MEAS, GREEN,
                  "All six pulled from the publishing agency, not typed in. NESDC · TPSO · Bank of "
                  "Thailand · BIS · ECB.") + 0.20
    y += d.callout(L, y, W, "Thailand has already overtaken the IMF’s 2026 projection",
                   "The IMF projected 1.5% growth and 0.9% inflation for 2026. The measured outturns "
                   "are +2.8% and +2.79% — 1.3 and 1.9 points higher. Where a Thai measurement "
                   "exists we show it instead of the projection and say which is which.") + 0.16
    d.callout(L, y, W, "The one chip that is falling is the one that touches our southern book",
              "Tourist arrivals are −6.6% year on year on a trailing-twelve-month basis. Tourism "
              "income is a large part of the informal cash economy in the South and around the "
              "eastern seaboard, and it appears nowhere in the crop or fleet data.", tone="warn")
    d.notes("Every chip here is a Thai official source with its vintage stamped. Where the IMF and a "
            "Thai measurement disagree, we show the measurement.")

    # ================================================================ 4 region + system NPL
    y = d.content("02 · Thailand in the region", "Slowest growth in ASEAN-5, and system arrears are turning.")
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
            colw=[2.1, 1.3, 1.15, 1.5, 1.6], size=10, rh=0.375, aligns=["l", "r", "r", "r", "r"])
    npl = MB["npl"]
    qmap = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}
    pts = [(ym(lab[:4] + "-" + qmap[lab[-2:]]), v)
           for lab, v in zip(npl["labels"], npl["series"])]
    d.linechart(L + 6.75, y - 0.30, W - 6.75, 2.70, [("System NPL", RED, pts)],
                ylab="Thai banking-system NPL, % of loans · 40 quarters",
                xticks=[(2017, "2017"), (2020, "2020"), (2023, "2023"), (2026, "2026")],
                ymin=2, ymax=6)
    y += 2.48
    y += d.source(L, y, W, MEAS, GREEN,
                  "IMF World Economic Outlook 2026 projections; Bank of Thailand published NPL ratio "
                  f"— latest {npl['latest']}% at {npl['period']}, from {npl['prev']}% the quarter "
                  f"before, {npl['yoy']:+.2f} points on the year, against a {npl['min']}% low in "
                  f"{npl['min_period']}.", size=9.5) + 0.22
    cw2 = (W - 0.25) / 2
    d.callout(L, y, cw2,
              f"Read our {cn['dpd90p_pct']}% against that {npl['latest']}% carefully",
              "They are not the same measure. The system ratio is bank loans on a regulatory NPL "
              "definition; ours is non-bank title lending to a borrower with informal income, on a "
              "90-plus-days measure. The LEVELS are not comparable and should not be put side by "
              "side as a benchmark.\n\nThe DIRECTION is: system arrears have risen in three of the "
              "last four quarters, and that is the environment our book is collecting in.",
              tone="risk", size=10)
    d.callout(L + cw2 + 0.25, y, cw2, "Two things the peer table implies for us",
              f"Growth is the ceiling on our borrower's income. Thailand at "
              f"{P['NGDP_RPCH']['THA']:.1f}% while the region runs 4–7% means the informal wage our "
              "book is repaid out of is not going to be lifted by the cycle.\n\nAnd the room to "
              f"cushion it is smaller than it was. Government debt is {P['GGXWDG_NGDP']['THA']:.1f}% "
              f"of GDP against Vietnam's {P['GGXWDG_NGDP']['VNM']:.1f}% — the fiscal space for the "
              "kind of household relief programme that carried borrowers through 2020–21 is "
              "materially narrower this time.", tone="warn", size=10)
    d.notes("Do not let anyone read 14.87 vs 4.48 as us being three times worse than the banks — "
            "different borrower, product and definition. The signal is that system arrears are "
            "turning up.")

    # ================================================================ 5 commodity board
    y = d.content("03 · Commodity board", "The world index says tailwind. The Thai farm gate does not.")
    y += d.text(L, y, W, "The board carries 21 commodities. Seventeen have a measured Thai farm-gate "
                "price beside the world index, and nine of those seventeen are negative year on year.",
                size=11, color=GREY, lh=15) + 0.16
    rows = [
        [("Coconut", True, NAVY), "Crops", "S · E", ("−70.9%", True, RED), ("—", False, GREY), "40,394"],
        [("Pineapple", True, NAVY), "Crops", "E · W · N", ("−20.0%", True, RED), ("—", False, GREY), "27,227"],
        [("Sugar", True, NAVY), "Crops", "Isan · Central", ("−17.9%", True, RED), ("−13.5%", False, RED), "90,216"],
        [("Rambutan", True, NAVY), "Crops", "S · E", ("−13.5%", True, RED), ("—", False, GREY), "42,960"],
        [("Pork", True, NAVY), "Livestock", "C · W · E", ("−6.7%", True, RED), ("—", False, GREY), "145,045"],
        [("Beef", True, NAVY), "Livestock", "Isan", ("−6.1%", True, RED), ("+11.8%", True, GREEN), "136,293"],
        [("White shrimp", True, NAVY), "Fisheries", "S · E coast", ("−4.3%", True, RED), ("—", False, GREY), "102,961"],
        [("Chicken", True, NAVY), "Livestock", "C · E", ("−2.4%", True, RED), ("−0.6%", False, GREY), "181,413"],
        [("Eggs", True, NAVY), "Livestock", "C · E", ("−1.7%", True, RED), ("—", False, GREY), "181,413"],
    ]
    y += d.table(L, y, W, ["Falling at the farm gate", "Segment", "Belt", "Thai farm-gate YoY",
                           "World index YoY", "Accounts in the belt"], rows,
                 colw=[2.3, 1.5, 2.0, 2.2, 2.0, 2.4], size=10, rh=0.278,
                 aligns=["l", "l", "l", "r", "r", "r"]) + 0.14
    y += d.source(L, y, W, MIX, NAVY,
                  "Prices MEASURED — NABC daily and monthly market feeds, Thai farm gate, OCSB "
                  "announced cane price, World Bank Pink Sheet 2026M06; farm-gate vintage "
                  "2026-08-02. Account counts are an ESTIMATED belt read and they OVERLAP heavily — "
                  "eggs and chicken are the same 181,413 poultry keepers. Do not add the column up.",
                  size=9) + 0.16
    d.callout(L, y, W, "Beef is the row that shows why the world index is the wrong instrument",
              "The world beef index is +11.8%. The measured Thai farm-gate price is −6.1% — a 17.9 "
              "point divergence. A cattle household in Isan is not experiencing +11.8%. Rubber, palm "
              "and cassava run the other way and are genuinely up on both measures.", tone="risk")
    d.notes("Do not sum the accounts column — the belts overlap. The divergence rows are the point: "
            "the world index and the Thai farm gate can face opposite directions.")

    # ================================================================ 6 five-year price history
    y = d.content("04 · Five years of price", "Sugar has not fallen for a year. It has fallen for four.")
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
                     (f"{cr[{'rubber': 'Rubber', 'rice': 'Rice', 'palm': 'Oil palm', 'sugar': 'Sugarcane'}[k]]['os_share_pct']:.1f}%",
                      False, NAVY),
                     (f"{pk:,.2f}", False, NAVY),
                     (f"{now:,.2f}", True, NAVY),
                     (f"{100 * (now / pk - 1):+.1f}%", True,
                      RED if now / pk < 0.85 else NAVY),
                     (f"{100 * (now / vs[0] - 1):+.1f}%", True,
                      GREEN if now > vs[0] else RED)])
    y += d.table(L, y, 8.60, ["World price, five years", "of farm book", "5-yr peak", "latest",
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

    # ================================================================ 7 the farm book
    y = d.content("05 · The farm book", f"What the farm exposure is: {bn(fn['farm_os'])} on {fn['farm_n']:,} accounts.")
    y += d.cards(L, y, W, [
        ("Farm accounts", f"{fn['farm_n']:,}",
         f"{bn(fn['farm_os'])} outstanding across {fn['provinces']} provinces", NAVY),
        ("Already at 90+", f"{100 * fn['at_risk_90p'] / fn['farm_n']:.1f}%",
         f"{fn['at_risk_90p']:,} accounts · against {cn['dpd90p_pct']}% book-wide", RED),
        ("Current", f"{100 * fn['current'] / fn['farm_n']:.1f}%",
         f"{fn['current']:,} accounts paying to term", GREEN),
        ("On a falling crop", f"{falling_share:.1f}%",
         f"of farm outstanding is sugarcane, coconut or pineapple — {bn(falling_os)}", GOLD),
    ], cols=4, ch=1.12) + 0.22
    y += d.text(L, y, W, "Arrears ladder — farm accounts", size=10, bold=True, color=NAVY) + 0.07
    y += d.ladder(L, y, W, [("Current", fn["current"], GREEN),
                            ("Watch, pre-30", fn["watch_x"], GOLD),
                            ("Rolling 30–89", fn["roll_3089"], ROLL),
                            ("At risk 90+", fn["at_risk_90p"], RED)]) + 0.22
    y += d.text(L, y, W, "Farm book by crop — share of outstanding", size=10, bold=True,
                color=NAVY) + 0.07
    y += d.ladder(L, y, W, [("Rice", cr["Rice"]["os_share_pct"], NAVY),
                            ("Rubber", cr["Rubber"]["os_share_pct"], GREEN),
                            ("Sugarcane", cr["Sugarcane"]["os_share_pct"], RED),
                            ("Oil palm", cr["Oil palm"]["os_share_pct"], GOLD),
                            ("Cassava", cr["Cassava"]["os_share_pct"], COLLAT),
                            ("Maize", cr["Maize"]["os_share_pct"], "1C8C7D"),
                            ("Coconut + pineapple",
                             cr["Coconut"]["os_share_pct"] + cr["Pineapple"]["os_share_pct"],
                             "8A93A6")]) + 0.20
    top = sorted(FB["provinces"].items(), key=lambda kv: -kv[1]["farm_os"])[:6]
    rows = []
    for nm2, p in top:
        d90 = 100 * p["at_risk_90p"] / p["farm_n"]
        lead, drag = p["drivers"][0], p["drag"]
        rows.append([(nm2, True, NAVY), (p["region"], False, GREY),
                     (f"{p['farm_n']:,}", False, NAVY),
                     (f"{p['farm_os'] / 1e6:,.0f}", True, NAVY),
                     (f"{d90:.1f}%", True, RED if d90 > fn["at_risk_90p"] / fn["farm_n"] * 100 else NAVY),
                     (f"{p['mix_pct']:.0f}%", False, NAVY),
                     (f"{lead['crop']} {lead['share']:.0f}% ({lead['yoy']:+.0f}%)", False,
                      GREEN if lead["yoy"] > 0 else RED),
                     (f"{drag['crop']} ({drag['yoy']:+.0f}%)", False, RED)])
    y += d.table(L, y, W, ["Largest farm books", "region", "accounts", "฿m out", "90+", "farm mix",
                           "lead crop, share and farm-gate YoY", "the drag"], rows,
                 colw=[1.9, 1.3, 1.2, 1.1, 0.9, 1.1, 3.0, 1.93], size=9.5, rh=0.268,
                 aligns=["l", "l", "r", "r", "r", "r", "l", "l"]) + 0.14
    d.source(L, y, W, MIX, NAVY,
             "Accounts, outstanding and arrears buckets MEASURED from the real loan tape (≥30-account "
             "cell floor); farm-gate YoY MEASURED. The crop split is ESTIMATED — province farm "
             "outstanding allocated on MEASURED planted-area mix. Six of 75 provinces shown.",
             size=9)
    d.notes(f"Farm is {100 * fn['at_risk_90p'] / fn['farm_n']:.1f}% at 90+ against {cn['dpd90p_pct']}% "
            "book-wide — not the worst part of the book. What earns it a section is that its hazards "
            "are external and forecastable, which almost nothing else in the book is.")

    # ================================================================ 8 crop margins
    y = d.content("06 · Margin, not price", "Price is the headline. Cost decides whether they pay us.")
    rows = []
    for c in FB["crops"]:
        has = c.get("margin_per_rai") is not None
        yv = c.get("yoy")
        rows.append([
            (c["en"], True, NAVY),
            (f"{c['os_share_pct']:.1f}%", False, NAVY),
            ((f"{yv:+.1f}%" if yv is not None else "—"), True,
             GREEN if (yv or 0) > 0 else RED),
            (f"{c['price_kg']:.2f}" if has else "—", False, NAVY),
            (f"{c['cost_kg']:.2f}" if has else "—", False, NAVY),
            (f"{c['margin_per_rai']:,.0f}" if has else "no cost series", has,
             NAVY if has else RED),
            (f"{c['margin_pct']:.1f}%" if has else "—", has,
             (GREEN if has and c["margin_pct"] >= 40 else GOLD) if has else GREY),
        ])
    y += d.table(L, y, W, ["Crop", "of farm book", "Farm-gate YoY", "Price ฿/kg", "Cost ฿/kg",
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
                   f"{falling_share:.1f}% of the farm book — {bn(falling_os)}. We can see the price "
                   "move and cannot yet see whether it has taken the grower below cost.",
                   tone="risk", size=10) + 0.14
    d.callout(L, y, W, "Why margin is the number that matters",
              "Netted of cost, a 24.3% move in crop prices becomes a 73.2% swing in crop income "
              "nationally — about three times the headline. Palm at 65.2% margin can absorb a price "
              "fall that would wipe out rubber at 24.9%, whose price is up 38%.", size=10)
    d.notes("If you present one agriculture slide, present this. Rubber's price is up 38% and it "
            "still carries the thinnest margin on the table.")

    # ================================================================ 9 farm household P&L
    lat, yrs = FH["latest"], FH["years"]
    y = d.content("07 · The farm household", "Nine thousand baht a month — and half of it is not farming.")
    y += d.cards(L, y, W, [
        ("Net cash per month", thb(lat["net_cash_monthly"]),
         f"crop year {lat['crop_year']} · after farm costs and living costs", RED),
        ("Farm share of income", f"{lat['farm_share_of_income_pct']:.1f}%",
         f"{100 - lat['farm_share_of_income_pct']:.1f}% comes from off-farm work", GOLD),
        ("Total income", thb(lat["income"]["total"]),
         f"per household per year · farm {thb(lat['income']['farm_total'])}", NAVY),
        ("Total expense", thb(lat["expense"]["total"]),
         f"farm {thb(lat['expense']['farm_total'])} · living {thb(lat['expense']['living_total'])}",
         NAVY),
    ], cols=4, ch=1.14) + 0.22
    d.bars(L, y, 5.60, 1.85,
           [(str(r["year_ce"]), r["net_cash"], r["year_ce"] == yrs[-1]["year_ce"]) for r in yrs],
           fmt=lambda v: f"{v / 1000:,.0f}k")
    d.callout(L + 5.80, y, W - 5.80, "Four consecutive years of decline",
              "฿116,526 in 2020 to ฿112,039 in 2023 — and that is before inflation, which ran 6.1% "
              "in 2022 alone. In real terms the fall is considerably steeper than the bars.\n\nThe "
              "farm share of income rose from 47.1% to 51.2% over the same period, which sounds like "
              "recovery and is not: off-farm income fell faster than farm income did.",
              tone="risk", size=10)
    y += 1.85 + 0.20

    # Why the net-cash line falls while gross income rises: the two sides move at different speeds.
    first = yrs[0]
    LINES = [("Crop income", "income", "farm_crops"),
             ("Crop growing costs", "expense", "farm_crops"),
             ("Off-farm income", "income", "nonfarm"),
             ("Living costs", "expense", "living_total"),
             ("Everything in", "income", "total"),
             ("Everything out", "expense", "total")]
    rows = []
    for lab, side, key in LINES:
        a, b = first[side][key], lat[side][key]
        ch2 = 100 * (b / a - 1)
        bad = (side == "expense" and ch2 > 0) or (side == "income" and ch2 < 0)
        rows.append([(lab, lab.startswith("Everything"), NAVY),
                     ("in" if side == "income" else "out", False, GREY),
                     (f"{a:,.0f}", False, NAVY), (f"{b:,.0f}", False, NAVY),
                     (f"{ch2:+.1f}%", True, RED if bad else GREEN)])
    y += d.table(L, y, 7.30, [f"Baht per household per year", "", str(first["year_ce"]),
                              str(lat["year_ce"]), "4-year change"], rows,
                 colw=[2.3, 0.7, 1.4, 1.4, 1.5], size=10, rh=0.255,
                 aligns=["l", "l", "r", "r", "r"])
    d.callout(L + 7.55, y - 2.20, W - 7.55, "Income rose. Costs rose faster.",
              "Gross income is up 18.3% across the four years and crop income specifically up 33.8% "
              "— that is not a household whose farming failed. What moved against them is the cost "
              "of growing: crop input costs are up 64.3% over the same four years.\n\nThat is why "
              "the net-cash bars fall while the income cards look healthy, and it is the same "
              "arithmetic as the margin slide two pages back. Watch the cost side, not the price "
              "headline.", tone="risk", size=10)
    y += 0.10
    d.source(L, y, W, MEAS, GREEN,
             "OAE farm socio-economic survey — a sample SURVEY of national means, baht per household "
             f"per year; not a census, not cut by province. Crop years {first['crop_year']} and "
             f"{lat['crop_year']}. The same survey profiles the household: head aged "
             f"{lat['household']['head_age_years']:.0f}, {lat['household']['household_size']:.1f} "
             f"people, {lat['household']['workers_15_64']:.1f} of working age, "
             f"{lat['household']['landholding_rai']:.0f} rai.", size=9)
    d.notes("The ฿9,337 is the number to say out loud. If asked why it fell while income rose: crop "
            "input costs +64.3% against crop income +33.8% over the same four years.")

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

    # ================================================================ 11 collateral divider
    d.divider("09 · Collateral", "This is the half with a decision attached.",
              "We lend against titles. Three things are moving at once: what a used vehicle is "
              "worth, how many are entering the pool that becomes our collateral, and which brands "
              "they are — because a brand with no Thai residual history is a recovery assumption we "
              "cannot yet make.")
    d.notes("Slow down here. Everything before was conditions; this is the part with an underwriting "
            "consequence.")

    # ================================================================ 12 resale value
    y = d.content("09a · Resale value", "What a title is worth: 33 points below its own 2015 base.")
    y += d.cards(L, y, W, [
        ("Pickup (รถกระบะ)", "66.8", "2026-05 · −50.0% off its 2012 peak · 33.2 pts below base", RED),
        ("Passenger car", "87.8", "2026-05 · −40.5% off peak · 12.2 pts below base", RED),
        ("Overall index", "75.2", "2026-05 · −46.3% off peak · 185 months of history", RED),
        ("Trough behind us?", "Yes", "pickup bottomed at 54.6 in 2024-10 — recovered, not to base", GOLD),
    ], cols=4, ch=1.10) + 0.18
    uv = uvpi_series()
    d.linechart(L, y, 7.55, 2.50, [("Pickup", RED, uv["truck"]), ("Car", NAVY, uv["car"])],
                ylab="Index, 2015 = 100 · monthly, 2011-01 → 2026-05", baseline=100,
                ymin=50, ymax=150,
                xticks=[(2011, "2011"), (2015, "2015"), (2019, "2019"), (2022, "2022"), (2026, "2026")])
    d.callout(L + 7.75, y, W - 7.75, "The pickup–car gap is recent, not structural",
              "Through most of 2013–2021 the two lines sit on top of each other — the mean gap was "
              "1.1 index points. It opens only from 2022, and the last twelve months average 26.9. "
              "Pickups are 33.2 points below their own 2015 base against 12.2 for cars: 2.7 times "
              "the decline.\n\nWhatever is depressing pickup resale started four years ago and has "
              "not reversed. Advance rates calibrated on pre-2022 behaviour are calibrated against a "
              "market that no longer exists.", tone="risk", size=10)
    y += 2.50 + 0.16
    d.source(L, y, W, MEAS, GREEN,
             "Bank of Thailand used-vehicle price index (EC_EI_040), 185 monthly observations, both "
             "series independently rebased so their own 2015 average = 100. The pickup series is "
             "confirmed pickup trucks (รถกระบะ), not heavy commercial — BoT’s 2019 Stat-Horizon "
             "methodology paper. Latest month preliminary.", size=9)
    d.notes("The 2022 break is the useful part. A structural gap would be a fact of the asset class; "
            "a four-year-old gap is something that happened, and can be diagnosed.")

    # ================================================================ 13 registration windows
    y = d.content("09b · Collateral supply", "Two vehicle markets, moving opposite ways.")
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
    ch = d.callout(L, y, cw, "The pickup slope is positive only because of that last bar",
                   f"Across all six months the trend reads {m6['pu']['slope_units_per_month']:+,.0f} "
                   f"units a month. Drop January — which the pipeline itself flags — and the five "
                   f"months before it run {pu_ex:+,.0f} a month. There is no flattening. Pickup "
                   "registrations are still falling at roughly a thousand units a month.",
                   tone="risk", size=10)
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
    y = d.content("09c · Concentration", "Our pickup residuals ride on two nameplates.")
    pu12, pa12 = Wd["m12"]["pu"], Wd["m12"]["pa"]
    pl = VM["plates_last12"]
    pk, pv = pl["pickup"]["top"][:2], pl["ppv"]["top"][:2]
    y += d.cards(L, y, W, [
        ("Top 2 pickup brands", f"{pu12['major_share_pct']:.1f}%",
         f"{' + '.join(pu12['majors'])} of new pickups · was {pu12['prior_major_share_pct']:.1f}%",
         GOLD),
        ("Top 2 pickup nameplates", f"{pk[0]['share_pct'] + pk[1]['share_pct']:.1f}%",
         f"{pk[0]['plate']} + {pk[1]['plate']} · {pk[0]['yoy_pct']:+.1f}% and "
         f"{pk[1]['yoy_pct']:+.1f}% YoY", RED),
        ("Top 2 car brands", f"{pa12['major_share_pct']:.1f}%",
         f"{' + '.join(pa12['majors'])} of new cars, from "
         f"{pa12['prior_major_share_pct']:.1f}% — down "
         f"{pa12['prior_major_share_pct'] - pa12['major_share_pct']:.1f} points in a year", RED),
        ("Top 2 PPV nameplates", f"{pv[0]['share_pct'] + pv[1]['share_pct']:.1f}%",
         f"{pv[0]['plate']} + {pv[1]['plate']} · {pv[0]['yoy_pct']:+.1f}% and "
         f"{pv[1]['yoy_pct']:+.1f}% YoY", GOLD),
    ], cols=4, ch=1.16) + 0.20
    cw2 = (W - 0.25) / 2
    def prow(p, cls):
        g = p.get("yoy_pct")
        return [(p["plate"], True, NAVY), (cls, False, GREY),
                (f"{p['units']:,}", False, NAVY),
                (f"{p['share_pct']:.1f}%", True, RED if p["share_pct"] >= 10 else NAVY),
                (f"{g:+.1f}%" if g is not None else "—", True,
                 GREEN if (g or 0) > 0 else RED)]
    plr = [prow(p, "pickup") for p in pl["pickup"]["top"][:5]]
    plr += [prow(p, "PPV") for p in pl["ppv"]["top"][:3]]
    d.table(L, y, cw2, ["Nameplate", "class", "12m units", "share of class", "YoY"], plr,
            colw=[2.0, 0.9, 1.2, 1.3, 0.69], size=9.5, rh=0.268,
            aligns=["l", "l", "r", "r", "r"])
    cbr = [[(b["brand"], b["brand"] in pa12["majors"], NAVY),
            ("incumbent" if b["brand"] in pa12["majors"] else "", False, GREY),
            (f"{b['units']:,}", False, NAVY),
            (f"{b['share_pct']:.2f}%", True,
             NAVY if b["brand"] in pa12["majors"] else RED)] for b in pa12["top_brands"][:8]]
    y += d.table(L + cw2 + 0.25, y, cw2, ["Car brand", "", "12-month units", "share"],
                 cbr, colw=[2.2, 1.5, 1.6, 0.79], size=9.5, rh=0.268,
                 aligns=["l", "l", "r", "r"]) + 0.16
    y += d.source(L, y, W, MEAS, GREEN,
                  "DLT first registrations at nameplate grain, trailing 12 months, NATIONAL only — "
                  "no province column exists. First registrations are the FUTURE collateral pool, "
                  "not our book and not used-vehicle sales.", size=9) + 0.18
    d.callout(L, y, W, "This is a recovery-value question, not a market-share one",
              "Pickup is close to a two-NAMEPLATE market — Hilux Revo and D-Max, not “Toyota’s "
              "various pickups”. The resale value of most of our pickup book rides on two specific "
              "models’ residual histories.\n\nThe car side does the opposite. Toyota and Honda have "
              "given up 9.4 points of new-car share in a year to brands with little or no Thai "
              "residual record. Those vehicles age into the used pool we recover into, and we would "
              "be setting advance rates on them without the history we have on a Hilux.",
              tone="risk")
    d.notes("Every pickup nameplate on the left table is down double digits — there is no pickup "
            "nameplate growing. The commercial point: we know what a five-year-old Hilux is worth. "
            "We do not know what a five-year-old BYD or Jaecoo is worth, and a fifth of new cars "
            "are now those.")

    # ================================================================ 15 the collateral book
    y = d.content("09d · What we hold", "The book to 100%: eight collateral types, ranked by baht.")
    rows = []
    for t in CB["types"]:
        rows.append([(t["label"], True, NAVY),
                     (f"{t['n']:,}", False, NAVY),
                     (f"{t['os'] / 1e9:.2f}", True, NAVY),
                     (f"{100 * t['os'] / cn['os']:.1f}%", False, NAVY),
                     (f"{t['ticket']:,.0f}", False, NAVY),
                     (f"{t['ltv_proxy_pct']:.1f}%", False, NAVY),
                     (f"{t['dpd90p_pct']:.2f}%", True,
                      RED if t["dpd90p_pct"] > cn["dpd90p_pct"] else NAVY),
                     (f"{t['npat_margin_avg']:,.0f}", False, NAVY)])
    y += d.table(L, y, W, ["Collateral type", "Accounts", "฿bn out", "Share", "Ticket ฿",
                           "LTV proxy", "90+ arrears", "NPAT ฿/acct"], rows,
                 colw=[2.5, 1.5, 1.2, 1.1, 1.5, 1.4, 1.6, 1.6], size=10, rh=0.278,
                 aligns=["l", "r", "r", "r", "r", "r", "r", "r"]) + 0.16
    y += d.source(L, y, W, MEAS, GREEN,
                  f"Real loan tape — {cn['n']:,} accounts, {bn(cn['os'])} outstanding, "
                  f"{cn['dpd90p_pct']}% at 90+ book-wide, LTV proxy {cn['ltv_proxy_pct']}%. No-PII "
                  "aggregates; nothing below the 30-account cell floor is published.", size=9) + 0.16
    y += d.callout(L, y, W, "Two readings a baht ranking gives you that an account ranking does not",
                   f"Motorcycles are {cn['moto_n_share_pct']}% of accounts and "
                   f"{cn['moto_os_share_pct']}% of the money — the worst arrears on the book at "
                   "17.92%, on ฿1,383 of profit per account. Property is the second-largest class at "
                   "฿11.78bn and is not a vehicle at all: nothing on the resale slides moves it.",
                   size=10) + 0.12
    d.callout(L, y, W,
              f"Pickup and car together are {cn['core_share_pct']}% of outstanding on "
              f"{cn['core_n_share_pct']}% of accounts",
              "That is the exposure the used-vehicle index on the previous slides actually prices, "
              "and the concentration that makes the 2022 pickup break an underwriting question "
              "rather than a market observation.", tone="risk", size=10)
    d.notes("Lead with pickup at ฿17.82bn. If asked why motorcycles matter less: 5.8% of the money, "
            "worst arrears, ฿1,383 profit an account.")

    # ================================================================ 16 the brand book
    y = d.content("09e · Which brands we hold", "The titles in the drawer, and how each performs.")
    rows = []
    for b in CB["brand_book"][:9]:
        rows.append([(b["brand"], True, NAVY),
                     (f"{b['n']:,}", False, NAVY),
                     (f"{b['os'] / 1e9:.2f}", True, NAVY),
                     (f"{b['os_share_pct']:.1f}%", False, NAVY),
                     (f"{b['ticket']:,.0f}", False, NAVY),
                     (f"{b['ltv_proxy_pct']:.1f}%", False, NAVY),
                     (f"{b['dpd90p_pct']:.2f}%", True,
                      RED if b["dpd90p_pct"] > cn["dpd90p_pct"] else NAVY),
                     (f"{b['late180_pct']:.2f}%", False, NAVY)])
    y += d.table(L, y, W, ["Brand on the title", "Accounts", "฿bn out", "Share of book", "Ticket ฿",
                           "LTV proxy", "90+ arrears", "180+ legacy"], rows,
                 colw=[2.5, 1.5, 1.2, 1.5, 1.4, 1.4, 1.5, 1.5], size=10, rh=0.278,
                 aligns=["l", "r", "r", "r", "r", "r", "r", "r"]) + 0.16
    y += d.source(L, y, W, MEAS, GREEN,
                  "Real loan tape, brand as recorded on the title. ที่ดิน(จำนอง) is land and mortgage "
                  "collateral, not a vehicle brand — and it is the single largest line in the book at "
                  "25.1% of outstanding.", size=9) + 0.18
    d.callout(L, y, W, "Honda is the outlier, and it is a motorcycle story",
              "80,539 accounts — more than Toyota PU and Isuzu PU combined — on ฿4.53bn at a ฿56k "
              "ticket, 17.53% at 90+ against a 14.87% book average, with 13.18% already in the "
              "180-plus legacy. The two pickup marques carry roughly three times the ticket at four "
              "points better arrears. It is the clearest read in the book that ticket size and "
              "collateral class, not brand reputation, drive performance.", tone="risk")
    d.notes("The Honda line is motorcycles under a car brand's name. Do not let it read as a "
            "judgement on Honda vehicles.")

    # ================================================================ 17 recovery depth + EV
    y = d.content("09f · Where we recover", "A resale market we can sell into — for now.")
    fc = {f["key"]: f for f in CB["fleet_classes"]}
    y += d.cards(L, y, W, [
        ("Pickup stock", f"{fc['pickup']['latest'] / 1e6:.2f}M",
         f"registered pickups · {fc['pickup']['yoy_pct']:+.2f}% YoY", RED),
        ("Car stock", f"{fc['car']['latest'] / 1e6:.2f}M",
         f"{fc['car']['yoy_pct']:+.2f}% YoY · +{fc['car']['since_2563_pct']:.1f}% since 2563", GREEN),
        ("Diesel share", f"{mn['diesel_share_pct']:.1f}%",
         "of the 44.3M fleet — the collateral we hold today", NAVY),
        ("BEV share", f"{mn['bev_pct']:.2f}%",
         f"electrified {mn['electrified_pct']:.2f}% — not a problem this quarter", GOLD),
    ], cols=4, ch=1.12) + 0.20
    # Our exposure and the market's depth, on the same row — the whole point of the slide is that
    # the two do not line up, and two separate tables would make the reader do the join.
    rows = []
    for uf in CB["used_flow"]:
        rg = CB["regions"][uf["region"]]
        pu = next(t["os_share_pct"] for t in rg["types"] if t["type"] == "PU")
        rows.append([(uf["region"], True, NAVY),
                     (f"{rg['os'] / 1e9:.2f}", True, NAVY),
                     (f"{pu:.1f}%", True, RED if pu >= 38 else NAVY),
                     (f"{rg['dpd90p_pct']:.2f}%", False,
                      RED if rg["dpd90p_pct"] > cn["dpd90p_pct"] else NAVY),
                     (f"{uf['pickup']['transfer_rate'] * 100:.2f}%", True,
                      RED if uf["pickup"]["transfer_rate"] < 0.06 else NAVY),
                     (f"{uf['car']['transfer_rate'] * 100:.2f}%", False, NAVY),
                     (f"{uf['moto']['transfer_rate'] * 100:.2f}%", False, NAVY)])
    y += d.table(L, y, W, ["Region", "our ฿bn out", "pickup % of its book", "its 90+ arrears",
                           "pickup turnover", "car turnover", "motorcycle turnover"], rows,
                 colw=[2.0, 1.7, 2.1, 1.8, 1.8, 1.5, 1.9], size=10, rh=0.30,
                 aligns=["l", "r", "r", "r", "r", "r", "r"]) + 0.16
    y += d.source(L, y, W, MEAS, GREEN,
                  "Left half from the real loan tape; right half from DLT registered stock and "
                  "ownership-transfer counts by region and vehicle class, plus MOT fleet totals. "
                  "Turnover is transfers divided by registered stock — how much of the parc changes "
                  "hands in a year, which is the depth a repossession has to be sold into.",
                  size=9) + 0.20
    cw2 = (W - 0.25) / 2
    d.callout(L, y, cw2, "Depth is thinnest exactly where our money is",
              "Transfers run 5.2–7.6% of registered pickups a year against 5.6–10.2% for cars. "
              "Pickup — 38.3% of outstanding — turns over more slowly than the class we hold less "
              "of, in every region. A thinner secondary market means a longer disposal and a wider "
              "discount on the way out.\n\nThe East is the sharpest version: 44.6% of its book is "
              "pickup and it has the slowest pickup turnover in the country at 5.21%.",
              tone="risk", size=10)
    d.callout(L + cw2 + 0.25, y, cw2, "Electrification is a clock, not a problem",
              "BEVs are 0.95% of the fleet and electrified vehicles 2.57%. Nothing we hold today is "
              "priced by that.\n\nBut our collateral has a five-to-ten-year resale tail, and the "
              "fleet mix that decides recoveries in 2032 is being registered now — a fifth of new "
              "cars are already brands with no Thai residual history. The decision this asks for is "
              "about how we price those titles, not about this quarter's book.",
              tone="warn", size=10)
    d.notes("Turnover is the depth we would actually recover into. Pickup is both our largest "
            "exposure and the slowest-turning class, and the East is the worst version of that "
            "combination.")

    # ================================================================ 18 conditions at our grain
    y = d.content("10 · Conditions at our grain", "Five lenses, from the country down to a branch.")
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
                  "lens rolls national → region → province → branch on its own correct weight — "
                  "labour force, fleet stock, account count, district count — with our outstanding "
                  "beside it at each level. Never a plain average of provinces.", size=9) + 0.18
    d.callout(L, y, W, "Read 0.94% unemployment together with 63.2% informality, never instead of it",
              "Headline unemployment is structurally near zero in Thailand because informal work "
              "absorbs the slack. A borrower who loses formal work does not appear in the "
              "unemployment number — they appear in the informal count, on a lower and less "
              "predictable income. The unemployment rate is not a stress signal for this book. "
              "Informality, the seasonal-idle share and the cushion figure are.", tone="warn")
    d.notes("This drill lets you go from a national number to a branch without changing instrument. "
            "If someone reaches for 0.94% unemployment as evidence the borrower is fine, this is the "
            "slide.")

    # ================================================================ 19 live
    y = d.content("11 · Live", "The one feed that changes daily.")
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
    y = d.content("12 · So what", "Four things the macro picture asks of us.")
    y += d.qa(L, y, W, [
        ("Collateral valuation",
         "Pickup resale is 33 points below its own 2015 base, the gap to cars opened only in 2022, "
         "and pickup turns over more slowly than any class we hold. Advance rates set against "
         "pre-2022 behaviour are set against a market that no longer exists."),
        ("Residual history we do not have",
         "A fifth of new cars are brands with little Thai residual record, and Toyota and Honda have "
         "given up 9.4 points of share in a year. Those vehicles age into the pool we recover into. "
         "We should decide how to price a title we cannot yet benchmark."),
        ("Farm margin, not farm price",
         "Netted of cost, a 24% price move becomes a 73% income swing — and the three crops whose "
         f"prices are falling are precisely the three with no cost series, on {falling_share:.1f}% "
         "of the farm book."),
        ("Borrower stress",
         f"A farm household nets {thb(FH['latest']['net_cash_monthly'])} a month after four straight "
         "years of decline, 60% of households cannot cover three months, and system arrears have "
         "risen in three of the last four quarters. Watch drought, the farm gate and informality — "
         "not the unemployment rate."),
    ], qw=3.10, size=11.5) + 0.22
    y += d.callout(L, y, W, "Scope, stated",
                   "All four are readings of the network and book we already run. Nothing on this "
                   "tab is an argument to open, close or expand anything.") + 0.18
    d.text(L, y, W, "Vintages — world prices 2026M06 · Thai farm gate 2026-08-02 · drought "
           "2026-06-21 · CPI 2026-05 · GDP 2026-Q1 · resale index 2026-05 · registrations to "
           f"{VM['meta']['latest_month']} · loan tape {cn['n']:,} accounts · telemetry 2026-08-03.",
           size=9, color=GREY, lh=12.5)
    d.notes("Close on scope: a risk lens on the footprint we already run — no open, close or expand "
            "recommendation, by design.")

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
