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
SRC = Path(__file__).resolve().parents[2] / "source-data"
COLLAT = "7A4FE0"             # the platform's collateral purple
ROLL = "D97A3A"               # the 30-89 rolling band, same as the app's bucket ladder


def load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def load_src(name):
    """One published series the app keeps upstream of platform/data/ — the BoT monthly arrivals.

    platform/data/macro_indicators.json carries only the trailing-twelve-month LEVEL, so the year-on-
    year move on that window has to come from the monthly series itself. It is the same measured BoT
    feed, one step earlier in the pipeline, and reading it here is the difference between a computed
    figure and a transcribed one.
    """
    with open(SRC / name, encoding="utf-8") as f:
        return json.load(f)


def trailing12_yoy(monthly):
    """Percent change of the last 12 months against the 12 before them, on a {'YYYY-MM': value} map."""
    ms = sorted(monthly)
    cur = sum(monthly[m] for m in ms[-12:])
    prev = sum(monthly[m] for m in ms[-24:-12])
    return 100.0 * (cur / prev - 1.0)


def ym(period):
    """'2026-05' / '2026M05' -> decimal year, so a monthly series can be plotted on one axis."""
    y, m = period.replace("M", "-").split("-")
    return int(y) + (int(m) - 1) / 12.0


_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
          "fifteen sixteen seventeen eighteen nineteen twenty").split()


def word(n):
    """A small count spelled out, because these read as prose: 'the three crops', not 'the 3 crops'.

    The counts on these slides are computed now rather than typed, and a bare integer dropped into a
    sentence is the tell that it was — especially at the start of one.
    """
    return _WORDS[n] if 0 <= n < len(_WORDS) else f"{n:,}"


def pct(v, dp=1, sign=True):
    """A percentage with the typographic minus (U+2212) the rest of the deck's prose uses.

    Python writes a hyphen; the hyphen is visibly shorter than the minus already sitting in every
    hand-written figure on these slides, so an interpolated number would not match the one beside it.
    """
    return (f"{v:+.{dp}f}%" if sign else f"{v:.{dp}f}%").replace("-", "−")


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
    MI = load("macro_indicators.json")["indicators"]
    FII = load("farm_income_impact.json")["national"]
    # The commodity board and its FALLING subset, counted rather than transcribed. A hand-typed
    # "nine of seventeen are negative" is true only until the next NABC pull: it was nine when this
    # deck was first written and the same board now reads eight, with six of the nine rows on
    # different numbers. Anything that moves with a price vintage is computed here.
    BOARD = load("commodities.json")["board"]
    B_THAI = [r for r in BOARD if r.get("local_yoy") is not None]
    B_FALL = sorted((r for r in B_THAI if r["local_yoy"] < 0), key=lambda r: r["local_yoy"])
    BEEF = next(r for r in BOARD if r["lab"] == "Beef")
    TOUR_YOY = trailing12_yoy(
        load_src("bot_tourist_arrivals.json")["series"]["foreign_arrivals_thousand"])
    # Farm-gate YoY per crop, on the measured Thai gate (NOT the world index — they can disagree in
    # sign, which is the whole argument of slide 03).
    gyoy = {c["en"]: c["yoy"] for c in FB["crops"] if c.get("yoy") is not None}
    FALLING = sorted(((k, v) for k, v in gyoy.items() if v < 0), key=lambda kv: kv[1])
    fall_str = ", ".join(f"{k.lower()} {pct(v)}" for k, v in FALLING)
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

    # Figures used only on this slide — each read fresh off its own layer so the verdict below
    # never drifts from the detail slide that unpacks it.
    gdp, cpi, pol = MI["gdp_growth"], MI["cpi_inflation"], MI["policy_rate"]
    P = WEO["peers"]

    UV = load("used_vehicle_value.json")["series"]
    Wd = VM["windows"]
    y12_pu = 100 * (Wd["m12"]["pu"]["units"] / Wd["m12"]["pu"]["prior_units"] - 1)
    pl = VM["plates_last12"]
    pu_all = sorted(pl["pickup"]["top"] + pl["ppv"]["top"], key=lambda r: -r["units"])
    top_pu = pu_all[0]
    worst_pu = min(pu_all[:5], key=lambda r: r.get("yoy_pct") or 0)

    II = load("income_impact.json")
    prov_by_region = {}
    for pname, pr in II["provinces"].items():
        prov_by_region.setdefault(pr["region"], []).append(pr)
    farm_vals, wage_vals = [], []
    for rg in II["regions"]:
        ps = prov_by_region.get(rg["key"], [])
        incs = [p["occ"]["Agriculture"]["income"] for p in ps
                if (p["occ"].get("Agriculture") or {}).get("income") is not None]
        if incs:
            farm_vals.append(sum(incs) / len(incs))
        wr = (rg.get("nso_wage_ref") or {}).get("headline")
        if wr:
            wage_vals.append(wr)
    farm_lo, farm_hi = min(farm_vals), max(farm_vals)
    wage_lo, wage_hi = min(wage_vals), max(wage_vals)

    CFI = load("crop_farmer_income.json")
    n_loss = sum(1 for c in CFI["crops"] if c["national"]["loss"])
    n_cfi = len(CFI["crops"])

    npl = MB["npl"]
    s4 = npl["series"][-5:]
    nq = len(s4) - 1
    risen = sum(1 for i in range(1, len(s4)) if s4[i] > s4[i - 1])

    y += d.qa(L, y, W, [
        ("Is the economy\nthe problem?",
         "No — stable, not strong.\n"
         f"• GDP {pct(gdp['value'])}, CPI {pct(cpi['value'], 2)} — both above the IMF's 2026 "
         f"forecast. Policy rate {pol['value']:.2f}%.\n"
         f"• Slowest growth in ASEAN-5: Thailand {P['NGDP_RPCH']['THA']:.1f}% vs Vietnam "
         f"{P['NGDP_RPCH']['VNM']:.1f}%.\n"
         f"• Government debt {P['GGXWDG_NGDP']['THA']:.1f}% of GDP vs Vietnam's "
         f"{P['GGXWDG_NGDP']['VNM']:.1f}% — thinnest cushion in the group."),
        ("Are crop prices\nthe problem?",
         "Not on the world index — the farm gate (ราคาที่เกษตรกรขายได้) says otherwise.\n"
         f"• {word(len(B_FALL)).capitalize()} of {word(len(B_THAI))} Thai farm-gate prices are "
         "falling year on year.\n"
         f"• Beef: farm gate {pct(BEEF['local_yoy'])} vs world index {pct(BEEF['global_yoy'])}.\n"
         f"• Margin over price: a {FII['price_impact_pct']:.0f}% price move becomes an "
         f"{FII['margin_impact_pct']:.0f}% swing in crop income."),
        ("What is\ndeteriorating?",
         "The collateral — the used-pickup (รถกระบะ) market.\n"
         f"• Resale value {pct(UV['truck']['change_since_peak_pct'], 0)} off peak, "
         f"{UV['truck']['vs_2015_base_pp']:+.0f} pts below its 2015 base.\n"
         f"• New pickup registrations {pct(y12_pu)} year on year.\n"
         f"• {top_pu['plate'].title()} {pct(top_pu['yoy_pct'])}, worst nameplate "
         f"{worst_pu['plate'].title()} {pct(worst_pu['yoy_pct'])}."),
        ("And the\nborrower?",
         "Thin before any of this.\n"
         f"• Farming pays ฿{farm_lo:,.0f}–{farm_hi:,.0f}/month vs an employee wage of "
         f"฿{wage_lo:,.0f}–{wage_hi:,.0f}.\n"
         f"• {word(n_loss).capitalize()} of {word(n_cfi)} full-cost crops pay below cost of "
         "production.\n"
         f"• {mn['cushion_lt3mo_pct']:.0f}% of households have no 3-month cushion; arrears rose "
         f"in {word(risen)} of the last {word(nq)} quarters."),
    ], qw=2.15, size=11) + 0.20
    y += d.source(L, y, W, MEAS, GREEN,
                  "NESDC · TPSO · Bank of Thailand · BIS · ECB · IMF · World Bank · NABC · OAE · "
                  "DLT · MOT · NSO · ThaiWater. Each page carries its own chip and vintage; where a "
                  "figure is modelled rather than published it is labelled ESTIMATED.") + 0.20
    d.text(L, y, W, "What follows", size=10, bold=True, color=NAVY)
    d.text(L, y + 0.22, W,
           "01–02  macro backdrop        03–08  agriculture: prices, belts, cost, income, water   "
           "     09  where to reach out first        10  collateral        11  what it asks of us",
           size=10, color=GREY, lh=14)
    d.notes("If they take one thing: the macro is stable, the crops are mixed, the collateral is "
            "deteriorating — and the borrower was already thin before any of it. Scope is external "
            "conditions; the book readouts live on Exposure and Risk, not here.")

    # ================================================================ 3 macro overlay + region
    y = d.content("01 · Macro overlay",
                  "Benign at home, slowest in the region, and system arrears are turning.")
    # Every chip reads its own value AND its own vintage out of macro_indicators.json. They were
    # transcribed until 2026-08-04, when a macro pull moved the ECB reference rate and the typed
    # figure stayed on the previous day's fixing.
    gdp, cpi, pol = MI["gdp_growth"], MI["cpi_inflation"], MI["policy_rate"]
    fx, hdebt, tour = MI["usd_thb"], MI["household_debt_gdp"], MI["tourist_arrivals"]
    y += d.cards(L, y, W, [
        ("GDP growth", pct(gdp["value"]),
         f"YoY · measured quarter, not a projection · NESDC {gdp['period']}", GREEN),
        ("Inflation", pct(cpi["value"], 2), f"headline CPI YoY · TPSO · {cpi['period']}", GOLD),
        ("Policy rate", f"{pol['value']:.2f}%", f"Bank of Thailand · {pol['period']}", NAVY),
        ("USD / THB", f"{fx['value']:.2f}", f"ECB reference · {fx['period']}", NAVY),
        ("Household debt หนี้ครัวเรือน", f"{hdebt['value']:.1f}%",
         f"of GDP · BIS · {hdebt['period']}", GOLD),
        ("Tourist arrivals นักท่องเที่ยว", f"{tour['value']:.1f}M",
         f"trailing 12m · {pct(TOUR_YOY)} YoY · BoT {tour['period']}", RED),
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
    # "Risen in N of the last 4 quarters" used to be typed prose beside the same series it describes
    # and had drifted a quarter stale. Computed off npl['series'] itself so it can't drift again.
    npl_last4, npl_prev4 = npl["series"][-4:], npl["series"][-5:-1]
    npl_risen = sum(1 for c, p in zip(npl_last4, npl_prev4) if c > p)
    qmap = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}
    pts = [(ym(lab[:4] + "-" + qmap[lab[-2:]]), v)
           for lab, v in zip(npl["labels"], npl["series"])]
    d.linechart(L + 6.75, y, W - 6.75, 1.70, [("System NPL", RED, pts)],
                ylab="Thai banking-system NPL หนี้เสีย, % of loans · 40 quarters",
                xticks=[(2017, "2017"), (2020, "2020"), (2023, "2023"), (2026, "2026")],
                ymin=2, ymax=6)
    y += 1.70 + 0.18
    y += d.source(L, y, W, MEAS, GREEN,
                  f"NESDC {gdp['period']} · TPSO {cpi['period']} · Bank of Thailand {pol['period']} "
                  f"· BIS {hdebt['period']} · ECB {fx['period']}, each pulled from the publishing "
                  f"agency. IMF World Economic Outlook 2026 (pulled {WEO['meta']['pulled']}) for "
                  "the peer table. BoT published NPL "
                  f"ratio — {npl['latest']}% at {npl['period']}, {npl['prev']}% the quarter before, "
                  f"{npl['yoy']:+.2f}pp on the year, {npl['min']}% low in {npl['min_period']}.",
                  size=9) + 0.20
    cw2 = (W - 0.25) / 2
    pj_g, pj_i = P["NGDP_RPCH"]["THA"], P["PCPIPCH"]["THA"]
    # Peer growth range computed from the same table above, not typed — it used to read a rounded
    # "4-7%" that was already off once Vietnam's own print moved.
    peer_lo = min(P["NGDP_RPCH"][c] for c in ("VNM", "IDN", "MYS", "PHL"))
    peer_hi = max(P["NGDP_RPCH"][c] for c in ("VNM", "IDN", "MYS", "PHL"))
    b1 = [
        f"Growth: IMF forecast {pj_g:.1f}%, actual {pct(gdp['value'])}.",
        f"Inflation: IMF forecast {pj_i:.1f}%, actual {pct(cpi['value'], 2)}.",
        "We use the Thai number over the projection, wherever one exists.",
        f"Exception: tourism, {pct(TOUR_YOY)} YoY (trailing 12 months) — feeds informal income in "
        "the South and East, missing from crop and fleet data.",
    ]
    d.callout(L, y, cw2, "Growth beat the IMF's own 2026 forecast",
              "\n".join(f"• {ln}" for ln in b1), tone="warn", size=10)
    b2 = [
        f"Thailand grows {P['NGDP_RPCH']['THA']:.1f}%. The rest of the region runs "
        f"{peer_lo:.1f}–{peer_hi:.1f}%.",
        f"Govt debt {P['GGXWDG_NGDP']['THA']:.1f}% of GDP vs Vietnam's "
        f"{P['GGXWDG_NGDP']['VNM']:.1f}%.",
        "Less fiscal room for relief than in 2020–21.",
        f"System arrears rose in {word(npl_risen)} of the last {word(len(npl_last4))} quarters — "
        "bank loans, a direction not a benchmark.",
    ]
    d.callout(L + cw2 + 0.25, y, cw2, "Slowest growth in the region, least room to cushion it",
              "\n".join(f"• {ln}" for ln in b2), tone="risk", size=10)
    d.notes("Economy is fine — the region and the arrears line are the story. Slow growth, thin "
            "fiscal cushion, arrears up in most of the last year. Less relief room than 2020–21.")

    # ================================================================ 4 conditions at our grain
    # Moved up to sit beside the macro overlay: it is the same question at a finer grain —
    # what the national numbers look like once you drill to a region, a province, a district.
    # Household debt now reads in MONTHS OF MONTHLY INCOME (debt ÷ income) — the AutoX underwriting
    # frame — computed at NATIONAL grain, the only grain macro_book carries both fields at. The
    # region table stays in baht: BoT publishes debt for all five regions but income for almost
    # none, so a region-level "months" figure can't be built honestly (macro_book's own grain_note).
    # The two vintages differ too — national is BoT/NSO 2019, the region cut is a newer 2023 read —
    # both read off region_debt.json rather than typed, so a re-pull can't drift silently out of sync.
    LC = load("labour_context.json")["informality"]
    RD = load("region_debt.json")["series"]
    debt_months = mn["debt_hh_thb"] / mn["income_hh_thb_month"]
    nat_debt_vint = next(r["vintage"] for r in RD["national"]
                         if r["indicator"] == "debt_per_household_thb")
    reg_debt_vint = next(r["vintage"] for r in RD["region"]
                         if r["indicator"] == "debt_per_household_thb" and r["geo"] == "Northeast"
                         and r["value"] == MB["regions"]["Isan"]["debt_hh_thb"])
    y = d.content("02 · Conditions on the ground", "Five lenses, from the country down to a district.")
    y += d.cards(L, y, W, [
        ("Labour force กำลังแรงงาน", f"{mn['labor_force_k'] / 1000:.1f}M",
         f"unemployment {mn['unemployment_pct']}% · seasonal idle {mn['seasonal_share_pct']}%, "
         f"{mn['seasonal_waiting_k']:.0f}k waiting", NAVY),
        ("Informal work นอกระบบ", f"{LC['rate_pct']:.1f}%",
         f"no payslip or social cover · core borrower base ({LC['as_of']})", GOLD),
        ("Vehicle fleet รถจดทะเบียน", f"{mn['fleet_total'] / 1e6:.1f}M",
         f"diesel {mn['diesel_share_pct']:.1f}% · EV {mn['electrified_pct']:.2f}%", NAVY),
        ("Districts dry ภัยแล้ง", f"{mn['dry_share_pct']}%",
         f"{mn['n_dry']} of {mn['n_districts']} districts · {mn['flood_high']} of "
         f"{mn['flood_stations']} rivers high", RED),
        ("Household debt หนี้ครัวเรือน", f"{debt_months:.1f} months",
         f"debt ÷ monthly income, all households · {mn['hh_with_debt_pct']:.0f}% carry debt", GOLD),
        ("No cushion กันชนทางการเงิน", f"{mn['cushion_lt3mo_pct']:.0f}%",
         "savings buffer, not debt — would last under 3 months without income", RED),
    ], cols=3, ch=1.16) + 0.20
    # The same lenses one level down. Only the EXTERNAL fields of macro_book's region record are
    # read here — labour, fleet, water, household debt. The book fields sitting beside them in that
    # layer (n, os, ticket, dpd) belong to Exposure and Risk and are not touched.
    order = ["Isan", "North", "South", "East", "Central&BKK"]
    rows = []
    for k in [k for k in order if k in MB["regions"]]:
        r2 = MB["regions"][k]
        rows.append([(k, True, NAVY),
                     (f"{r2['labor_force_k'] / 1000:.1f}M", False, NAVY),
                     (f"{r2['unemployment_pct']:.2f}%", False, NAVY),
                     (f"{r2['seasonal_waiting_k']:,.0f}k", True,
                      RED if r2["seasonal_waiting_k"] > 100 else NAVY),
                     (f"{r2['fleet_total'] / 1e6:.1f}M", False, NAVY),
                     (f"{r2['diesel_share_pct']:.1f}%", False, NAVY),
                     (f"{r2['dry_share_pct']:.0f}%", True,
                      RED if r2["dry_share_pct"] >= 40 else NAVY),
                     (f"{r2['flood_high']}/{r2['flood_stations']}", False, NAVY),
                     (thb(r2["debt_hh_thb"]), True,
                      RED if r2["debt_hh_thb"] > mn["debt_hh_thb"] else NAVY),
                     (f"{r2['new_biz_per_1k_lf']:.2f}", False, NAVY)])
    y += d.table(L, y, W, ["Region", "labour force", "unemployment", "seasonal idle",
                           "vehicle fleet", "diesel", "districts dry", "rivers high",
                           "household debt", "new firms"], rows,
                 colw=[1.4, 1.3, 1.4, 1.3, 1.2, 0.9, 1.35, 1.15, 1.5, 0.93], size=9, rh=0.268,
                 aligns=["l", "r", "r", "r", "r", "r", "r", "r", "r", "r"]) + 0.14
    # Both the source row and the callout below are deliberately tight: the first draft of this
    # slide ran its callout to y≈7.49, past the 7.38 footer bar, because the pre-callout cursor was
    # measured instead of the callout's own bottom edge. Every disclosure survives, in fewer words.
    y += d.source(L, y, W, MEAS, GREEN,
                  "NSO LFS · ILOSTAT · DLT · MOT · DBD · ThaiWater · BoT/NSO household debt. "
                  "Labour, fleet and water roll province → region → national on their own weight, "
                  f"never a plain average. The debt card is BoT/NSO {nat_debt_vint}, ALL households "
                  f"— not only the {mn['hh_with_debt_pct']:.0f}% carrying debt. The table's region "
                  f"column is a newer cut, {reg_debt_vint}, in baht: income is not published at "
                  "region grain for enough regions to convert it. East shares Central's figure.",
                  size=9) + 0.16
    isan_w = MB["regions"]["Isan"]["seasonal_waiting_k"]
    north_w = MB["regions"]["North"]["seasonal_waiting_k"]
    d.callout(L, y, W,
              f"{pct(mn['unemployment_pct'], 2, sign=False)} unemployment hides informal work",
              "A lost formal job reappears as informal work, not as unemployment — on lower, less "
              "predictable pay. Read informality, seasonal idle and the cushion instead. Isan's "
              f"seasonal idle is {isan_w / north_w:.1f}× the North's.", tone="warn", size=10)
    d.notes("This drill goes from a national number to a district without changing instrument. "
            "Household debt is now months of income, not baht — that's the underwriting frame. "
            "If someone reaches for near-zero unemployment as evidence the borrower is fine, this "
            "is the slide.")

    # ================================================================ 5 commodity board
    # The accounts column is FARMER accounts, not all accounts — the owner's correction on
    # 2026-08-04, after the app's own "Book exposed" column was read as a farmer count and is not
    # one. `exposure.book_accounts` counts every borrower living in the belt, office workers and
    # traders included; ~78% of them are not farmers.
    #
    # This is the ONE place in this deck that reads the loan tape. The Macro tab is external data by
    # the owner's own scope rule, and the exception was granted explicitly and only for this column:
    # "i'm fine with using the autox account farmer accounts by province for this one instance."
    # Everything else on the slide is published external data, and the column is labelled as ours.
    GEO = load("tape_geo_occ.json")
    FARMER_OCC = "เกษตร"

    def farmers_in_belt(r):
        """Accounts recorded as farming occupation, summed over the crop's belt provinces.

        A belt province is one of the provinces making up ~80% of national planted area for that
        crop, so this is 'our farming borrowers who live where this crop is grown' — NOT 'borrowers
        confirmed to grow it'. The distinction is in the source row, and it is not a small one."""
        tot, seen = 0, 0
        for p in (r.get("exposure") or {}).get("top", []):
            for o in GEO["provinces"].get(p["prov"], []):
                if o["occupation"] == FARMER_OCC:
                    tot += o["n"]
                    seen += 1
        return tot, seen

    def six_month(lab):
        """Thai farm-gate move over six months, from the measured monthly series."""
        h = (TPH_S or {}).get(lab)
        if not h or h.get("cadence") != "monthly" or len(h.get("values") or []) < 7:
            return None
        v = h["values"]
        return 100.0 * (v[-1] / v[-7] - 1.0)

    TPH_S = load("thai_price_history.json")["series"]
    y = d.content("03 · Commodity board", "The world index says tailwind. The Thai farm gate does not.")
    y += d.bullets(L, y, W, [
        f"{word(len(B_THAI)).capitalize()} of the {word(len(BOARD))} commodities we track have a "
        f"measured Thai farm-gate price (ราคาที่เกษตรกรขายได้). {word(len(B_FALL)).capitalize()} "
        "are falling year on year.",
        "Six months beside the year: they disagree on direction more often than they agree on size.",
        "The last column is OUR farming customers living in that belt — the only loan-book number "
        "in this deck.",
    ], size=11, gap=0.09) + 0.16

    def tri(v):
        return GREEN if v > 0 else (RED if v < 0 else GREY)

    rows = []
    for r in B_FALL:
        s6 = six_month(r["lab"])
        nf, nprov = farmers_in_belt(r)
        allacc = (r.get("exposure") or {}).get("book_accounts") or 0
        rows.append([
            (r["lab"], True, NAVY), r["seg"], r["reg"].replace("·", " · "),
            (pct(r["local_yoy"]), True, RED),
            (pct(s6), True, tri(s6)) if s6 is not None else ("no series", False, GREY),
            (f"{nf:,}", True, COLLAT) if nf else ("—", False, GREY),
            (f"{100 * nf / allacc:.0f}%" if nf and allacc else "—", False, GREY),
        ])
    y += d.table(L, y, W, ["Falling at the farm gate", "Segment", "Belt", "Farm-gate YoY",
                           "Farm-gate 6m", "Farming accounts in belt", "share of our accounts"],
                 rows, colw=[2.25, 1.20, 1.80, 1.50, 1.50, 2.20, 1.98], size=10, rh=0.278,
                 aligns=["l", "l", "l", "r", "r", "r", "r"]) + 0.14
    y += d.source(L, y, W, MIX, NAVY,
                  "Prices MEASURED — NABC daily quotes for the Thai farm gate, OCSB announced cane "
                  f"price; newest quote {max(r['local_date'] for r in B_THAI)}. The six-month move "
                  "is computed from NABC's own monthly series (thai_price_history, vintage "
                  f"{load('thai_price_history.json')['meta']['vintage']}); a crop with no monthly "
                  "series is marked, never estimated. Belt is an ESTIMATED read of where each "
                  "commodity is produced, and belts overlap. Farming accounts are OURS and "
                  "MEASURED — accounts whose recorded occupation is เกษตร in the belt provinces, "
                  f"from the {GEO['meta']['n_accounts']:,}-account tape at {GEO['meta']['mob_anchor']}; "
                  f"no cell below {GEO['meta']['min_cell']} accounts is published. They live where "
                  "the crop grows; they are not confirmed to grow it.", size=9) + 0.16
    bf, _ = farmers_in_belt(BEEF)
    d.callout(L, y, W, "Beef: the world index is the wrong instrument",
              f"World beef {pct(BEEF['global_yoy'])}, Thai farm gate {pct(BEEF['local_yoy'])} — a "
              f"{abs(BEEF['divergence']):.1f}-point gap, opposite directions. {bf:,} of our farming "
              "customers live in the beef belt, Isan.", tone="risk")
    d.notes("Two points. First, the world index and the Thai farm gate can face opposite ways, and "
            "only one of them is what a Thai grower is paid — beef is the clean example. Second, "
            "the last column is farmers, not all accounts: the app's 'book exposed' number counts "
            "every borrower in the belt and about four in five of them are not farming.")

    # ================================================================ 6 five-year price history
    y = d.content("04 · Five years of price", "Sugar has not fallen for a year. It has fallen for four.")
    KEYS = [("rubber", "Rubber ยางพารา", GREEN), ("rice", "Rice ข้าว", NAVY),
            ("palm", "Palm oil ปาล์มน้ำมัน", GOLD), ("sugar", "Sugar น้ำตาล", RED)]
    hist = price_history([k for k, _, _ in KEYS])
    d.linechart(L, y, 7.55, 3.05, [(lab, col, hist[k]) for k, lab, col in KEYS],
                ylab="World price rebased to 100 at 2021-07 · 60 monthly observations",
                baseline=100, ymin=40, ymax=200,
                xticks=[(2021.5, "2021"), (2023, "2023"), (2024.5, "2024"), (2026, "2026")])
    CH = load("commodity_history.json")          # .meta.vintage is what the source row cites
    raw = CH["series"]
    fx = MI["usd_thb"]                            # measured ECB reference rate — read, not typed

    def series_vals(k):
        return [(m, v) for m, v in zip(raw[k]["months"], raw[k]["values"]) if v is not None]

    # The two callout facts, computed off the same series the chart plots, not transcribed. Sugar's
    # own peak inside the 60-month window (not the window's start) is what "falling for four" refers
    # to; rubber's own 2021 starting level is its natural comparison point, the same base the chart
    # rebases every series to.
    sv = series_vals("sugar")
    pk_i = max(range(len(sv)), key=lambda i: sv[i][1])
    sugar_off = 100 * (sv[-1][1] / sv[pk_i][1] - 1)
    sugar_since_peak = len(sv) - 1 - pk_i
    sugar_down = sum(1 for i in range(pk_i, len(sv) - 1) if sv[i + 1][1] <= sv[i][1])
    sugar_peak_period = sv[pk_i][0].replace("M", "-")
    rv = [v for _, v in series_vals("rubber")]
    rub_below = sum(1 for v in rv if v < rv[0])
    rub_run = 0
    for v in reversed(rv):
        if v >= rv[0]:
            rub_run += 1
        else:
            break
    d.callout(L + 7.75, y, W - 7.75, "A year-on-year number hides the shape",
              f"• Sugar (น้ำตาล): world price {pct(sugar_off, 0)} against its {sugar_peak_period} "
              f"peak — down in {sugar_down} of the last {sugar_since_peak} months, not a one-year "
              "dip.\n"
              f"• Rubber (ยางพารา): spent {rub_below} of the last {len(rv)} months below its own "
              f"2021 level — only just cleared it, after {rub_run} months running above.",
              tone="warn", size=10)
    y += 3.05 + 0.20

    def bfmt(v):
        """Baht formatting only: sub-100 crop prices keep 2dp, tonne prices round to the baht."""
        return f"{v:,.2f}" if v < 1000 else f"{v:,.0f}"

    # Baht only replaces the LATEST price. Converting the 5-yr peak at today's rate would price a
    # 2021–24 dollar figure on a 2026 exchange rate — a number nobody was ever actually paid. Latest
    # is safe to convert because today's price and today's FX are the same today.
    rows = []
    for k, lab, _ in KEYS:
        vs = [v for v in raw[k]["values"] if v is not None]
        pk, now = max(vs), vs[-1]
        rows.append([(f"{lab} {raw[k]['unit']}", True, NAVY),
                     (f"{AREA[{'rubber': 'Rubber', 'rice': 'Rice', 'palm': 'Oil palm', 'sugar': 'Sugarcane'}[k]]:.1f}%",
                      False, NAVY),
                     (f"{pk:,.2f}", False, NAVY),
                     (bfmt(now * fx['value']), True, NAVY),
                     (f"{100 * (now / pk - 1):+.1f}%", True,
                      RED if now / pk < 0.85 else NAVY),
                     (f"{100 * (now / vs[0] - 1):+.1f}%", True,
                      GREEN if now > vs[0] else RED)])
    y += d.table(L, y, 8.60, ["World price, five years", "of planted area", "5-yr peak, US$",
                              "latest, ฿", "off peak", "vs 5 yrs ago"], rows,
                 colw=[2.6, 1.3, 1.2, 1.1, 1.2, 1.2], size=10, rh=0.278,
                 aligns=["l", "r", "r", "r", "r", "r"]) + 0.10
    y += d.text(L, y, W, "Only ‘latest’ is converted to baht — today’s FX is right for today’s "
                "price, not a 2021–23 one, so ‘5-yr peak’ stays in US$.",
                size=9.5, color=GREY) + 0.14
    d.source(L, y, W, MEAS, GREEN,
             f"World Bank Pink Sheet nominal-USD monthly prices, vintage {CH['meta']['vintage']} (60 "
             "observations per series, rebased to 100 at 2021-07 for the chart — units differ, so "
             "raw levels can’t share an axis). Baht conversion at the ECB reference rate USD/THB "
             f"{fx['value']:.3f}, {fx['period']}. Planted-area share MEASURED, OAE/DOAE crop mix "
             "(crop_mix.json). Nominal, not deflated: five years of Thai CPI sit under every "
             "‘vs 5 yrs ago’ figure.", size=9)
    d.notes("YoY hides a slow move: sugar is down most months since its 2023 peak, not a one-off "
            "dip; rubber only just cleared its own 2021 level. We convert only the latest price to "
            "baht — the five-year peak stays in US$ so we don’t mix an old price with today’s FX.")

    # ================================================================ 6 the crop belts
    y = d.content("05 · The crop belts",
                  "Which crop each region grows, and what the price round did to its income.")
    y += d.cards(L, y, W, [
        ("Crops with a Thai farm-gate price", f"{len(gyoy)}",
         ", ".join(k.lower() for k in gyoy), NAVY),
        ("Falling at the farm gate", f"{len(FALLING)}", f"{fall_str} year on year", RED),
        ("Median province crop-income shock", f"{CM['national']['median_shock_pct']:+.1f}%",
         "most of the country gained from this price round", GREEN),
        ("Provinces where it went backwards", f"{CM['national']['negative_provinces']}",
         "all four are coconut belts on the western gulf", RED),
    ], cols=4, ch=1.12) + 0.18
    y += d.text(L, y, W, "Farm gate (ราคาที่เกษตรกรขายได้) = what the farmer is paid at first sale — "
                "before trading, milling or transport take a cut.", size=10, color=GREY, lh=13.5) + 0.14
    RG = CM["regions"]
    rows = [[(k, True, NAVY),
             (f"{v['provinces']}", False, NAVY),
             (f"{v['shock_pct']:+.1f}%", True, GREEN if v["shock_pct"] > 0 else RED),
             (f"{v['negative']}", True, RED if v["negative"] else NAVY),
             (v["worst_prov"], False, NAVY),
             (f"{v['worst_shock']:+.1f}%", True, GREEN if v["worst_shock"] > 0 else RED)]
            for k, v in sorted(RG.items(), key=lambda kv: kv[1]["shock_pct"])]
    th = d.table(L, y, 6.05, ["Region", "provs", "income shock", "backwards", "weakest", ""], rows,
                colw=[1.25, 0.75, 1.25, 1.05, 1.05, 0.7], size=9.5, rh=0.272,
                aligns=["l", "r", "r", "r", "l", "r"])
    negp = sorted(((n2, v["shock_pct"]) for n2, v in CM["provinces"].items() if v["shock_pct"] < 0),
                  key=lambda kv: kv[1])
    ch = d.callout(L + 6.30, y - 0.05, W - 6.30, "Good for farming, almost everywhere",
              f"•  {pct(gyoy['Rubber'], 0)} rubber, {pct(gyoy['Cassava'], 0)} cassava, "
              f"{pct(gyoy['Oil palm'], 0)} palm, {pct(gyoy['Rice'], 0)} rice at the farm gate. "
              "Crop income rose in every region.\n"
              f"•  {word(len(negp)).capitalize()} provinces fell — all coconut, all on the "
              f"western gulf. Coconut price is down {abs(gyoy['Coconut']):.0f}%.\n"
              "•  A gain on paper is not cash yet — the next table nets prices against cost.",
              tone="warn", size=10)
    y += max(th, ch - 0.05) + 0.16

    def crop_share_str(p2):
        """Every crop OAE tracks for this province, share of planted area, summing to 100%."""
        cs = sorted(p2["crops"], key=lambda c: -c["share"])
        parts, ssum = [], 0.0
        for c in cs:
            v = 100.0 * c["share"]
            ssum += c["share"]
            parts.append(f"{c['en']} {v:.0f}%" if v >= 0.5 else f"{c['en']} <1%")
        rem = max(0.0, 100.0 * (1.0 - ssum))
        if rem >= 0.5:                                     # honest rounding residual, not a real crop
            parts.append(f"other {rem:.0f}%")
        return ", ".join(parts)

    top = sorted(CM["provinces"].items(), key=lambda kv: -kv[1]["area_rai"])[:6]
    rows = []
    for nm2, p2 in top:
        fbp = FB["provinces"].get(nm2, {})
        rain = fbp.get("rain_pct_of_normal")
        rows.append([(nm2, True, NAVY), (p2["region"], False, GREY),
                     (f"{p2['area_rai'] / 1e6:.2f}M", False, NAVY),
                     (crop_share_str(p2), False, NAVY),
                     (f"{p2['shock_pct']:+.1f}%", True,
                      GREEN if p2["shock_pct"] > 0 else RED),
                     (f"{p2['income_base_thb']:,.0f}", False, NAVY),
                     (f"{rain:.0f}%" if rain is not None else "—", True,
                      RED if (rain is not None and rain < 90) else NAVY)])
    y += d.table(L, y, W, ["Largest planted areas", "region", "planted rai",
                           "crop mix, % of planted area", "shock", "farm ฿/mo", "rain"], rows,
                 colw=[1.45, 0.85, 0.80, 6.65, 0.80, 1.25, 0.63], size=8, hsize=9.5, rh=0.25,
                 hh=0.32, aligns=["l", "l", "r", "l", "r", "r", "r"]) + 0.14
    d.source(L, y, W, MIX, NAVY,
             "Planted area MEASURED (OAE, by province). Crop mix MEASURED — every crop OAE tracks "
             "for that province, share of planted area, rounded to the nearest point and shown for "
             "all of them, not just the lead crop; a share that rounds to zero reads “<1%”, and any "
             "rounding gap is shown honestly as “other”. Farm-gate price moves MEASURED (NABC/OCSB); "
             "farm income level MEASURED (NSO/OAE, baht per month). The income shock is ESTIMATED — "
             "each province's crop mix weighted by the measured price move, as a percentage of its "
             "measured farm income. Six of 77 provinces shown, ordered by planted area.", size=9)
    d.notes("What earns agriculture a section is that its hazards are external and forecastable — "
            "price, cost, rainfall — which is rare. The crop-mix column is now the full published "
            "mix for each province, every crop, summing to 100 — not just the lead crop.")

    # ============================================ 8 margin and cost, on ONE price basis
    # Rewritten 2026-08-04 on the owner's instruction: "if the conflicting reports on profitability
    # by crop are going to create problems, take it out and mention more crops."
    #
    # What came out: the margin-versus-cost argument. This slide used to spend its whole surface
    # reconciling two published prices per crop — OAE's farm gate against NABC's market quote — and
    # concluding that three of FIVE crops lose money. The reconciliation was correct but it cost the
    # slide to make, it only ever covered the five crops with an OAE cost series, and a room hearing
    # two contradictory profitability numbers argues about the numbers instead of the exposure.
    #
    # What went in: every crop with a MEASURED Thai farm-gate price, each with its own six-month
    # line. Thirteen of them carry a real monthly baht series in thai_price_history.json — a layer
    # that has been built and gated since 2026-08-02 and that the deck had never read. No cost, no
    # margin, no netting: just the price the grower is paid and its direction.
    TPH = load("thai_price_history.json")
    HS = TPH["series"]

    def six_month(h):
        """Latest against six months earlier, on a series that is genuinely monthly.

        Sugar is the reason for the cadence test: OCSB announces one administered cane price per
        season, so its six points are YEARS. Slicing the last seven and calling the result a
        six-month move would be arithmetic on the wrong clock."""
        if h.get("cadence") != "monthly" or len(h.get("values") or []) < 7:
            return None
        v = h["values"]
        return 100.0 * (v[-1] / v[-7] - 1.0)

    panels, noseries = [], []
    for r in B_THAI:
        h = HS.get(r["lab"])
        s6 = six_month(h) if h else None
        (panels if s6 is not None else noseries).append((r, h, s6))
    panels.sort(key=lambda p: p[0]["local_yoy"])          # worst farm gate first
    n_dis = sum(1 for r, _h, s6 in panels if (r["local_yoy"] < 0) != (s6 < 0))

    y = d.content("06 · Every crop at the farm gate",
                  "What the grower is paid, and which way it has moved.")
    y += d.bullets(L, y, W, [
        f"{word(len(B_THAI)).capitalize()} commodities have a measured Thai farm-gate price "
        f"(ราคาที่เกษตรกรขายได้). {word(len(panels)).capitalize()} also have a real monthly price "
        "series — those are the lines below.",
        f"Year on year and six months disagree on direction for {word(n_dis)} of them. A single "
        "annual number can point the wrong way.",
        "Every line is scaled to its own range: read the shape, not the height.",
    ], size=10.5, gap=0.07) + 0.16

    def money(v):
        return f"{v:,.0f}" if v >= 1000 else f"{v:,.2f}"

    def tri(v):
        return GREEN if v > 0 else (RED if v < 0 else GREY)

    COLS, GAPX = 5, 0.16
    cwp = (W - GAPX * (COLS - 1)) / COLS
    for i, (r, h, s6) in enumerate(panels):
        px, py = L + (i % COLS) * (cwp + GAPX), y + (i // COLS) * 1.21
        yoy = r["local_yoy"]
        d.text(px, py, cwp, f"{r['lab']}  {h.get('category_th', '')}", size=9, bold=True, color=NAVY)
        d.text(px, py + 0.155, cwp,
               f"฿{money(h['values'][-1])} {h['unit'].replace('บาท/', '/')} · {r['reg']}",
               size=7.5, color=GREY)
        d.text(px, py + 0.30, cwp * 0.5, f"YoY {pct(yoy)}", size=8, bold=True, color=tri(yoy))
        d.text(px + cwp * 0.5, py + 0.30, cwp * 0.5, f"6m {pct(s6)}", size=8, bold=True,
               color=tri(s6))
        d.sparkline(px, py + 0.47, cwp, 0.60,
                    list(zip(h["months"][-6:], h["values"][-6:])), color=tri(s6))
    y += ((len(panels) + COLS - 1) // COLS) * 1.21 + 0.04

    # The remaining board rows are named rather than dropped: a grid that silently shows 13 of 17
    # reads as "these are the crops", and two of the four absentees are falling.
    y += d.text(L, y, W, "Priced but not plotted — no monthly series: "
                + " · ".join(f"{r['lab']} {pct(r['local_yoy'])}"
                             + (" (annual, administered)" if (h or {}).get("cadence") == "annual"
                                else "")
                             for r, h, _s in sorted(noseries, key=lambda p: p[0]["local_yoy"])),
                size=9, color=GREY, lh=12.5) + 0.14
    d.source(L, y, W, MEAS, GREEN,
             "Farm-gate prices MEASURED — NABC daily quotes, monthly means, in baht as published "
             f"(no currency conversion); newest quote {max(r['local_date'] for r in B_THAI)}, "
             f"history vintage {TPH['meta']['vintage']}. Farm gate (ราคาที่เกษตรกรขายได้) is what "
             "the grower is paid at first sale, before trading, milling or transport take a cut — "
             "not the world index and not a supermarket price. Belts are an ESTIMATED read of where "
             "each commodity is produced, and they overlap. Sugar is OCSB's announced season price, "
             "one point a year, so it has no six-month move to show.", size=9)
    d.notes("The profitability argument is gone on purpose — it covered five crops and invited a "
            "fight about which published price is right. This shows the price the grower is "
            "actually paid, for every commodity we can measure, with its own six-month line. The "
            "point to land: year-on-year and six-month disagree on direction for several of them, "
            "so a single annual number is not enough to act on.")

    # ================================================================ 9 income now, by region
    II = load("income_impact.json")
    y = d.content("07 · Income right now, by region",
                  "What each occupation earns, where the floor is, and which way it moved.")
    y += d.text(L, y, W, "Monthly income now, by region and job — each region set against its own "
                "wage.", size=11, color=GREY, lh=15) + 0.16
    prov_by_region = {}
    for pname, pr in II["provinces"].items():
        prov_by_region.setdefault(pr["region"], []).append((pname, pr))

    def occ_mean(ps, key, field="income"):
        vals = [p["occ"][key] for _, p in ps if (p["occ"].get(key) or {}).get(field) is not None]
        return sum(v[field] for v in vals) / len(vals) if vals else None

    rows, reg = [], {}
    for rg in II["regions"]:
        ps = prov_by_region.get(rg["key"], [])
        ag = sorted(((p["occ"]["Agriculture"]["income"], n) for n, p in ps
                     if (p["occ"].get("Agriculture") or {}).get("income")))
        farm = occ_mean(ps, "Agriculture")
        dp = occ_mean(ps, "Agriculture", "d_pct")
        wage = (rg.get("nso_wage_ref") or {}).get("headline")
        reg[rg["key"]] = {"farm": farm, "wage": wage, "weak": ag[0] if ag else None}
        rows.append([(rg["key"], True, NAVY),
                     (f"{farm:,.0f}", True, NAVY),
                     (pct(dp), True, GREEN if dp >= 0 else RED),
                     (f"{ag[0][1]} {ag[0][0]:,.0f}" if ag else "—", False, RED),
                     (f"{occ_mean(ps, 'FactoryWorkers'):,.0f}", False, NAVY),
                     (f"{occ_mean(ps, 'Transport'):,.0f}", False, NAVY),
                     (f"{occ_mean(ps, 'SMEOwners'):,.0f}", False, NAVY),
                     (f"{occ_mean(ps, 'OfficeStaff'):,.0f}", False, NAVY),
                     (f"{wage:,.0f}" if wage else "—", True, NAVY),
                     (f"{100 * farm / wage:.0f}%" if wage else "—", True,
                      RED if wage and farm / wage < 0.6 else NAVY)])
    y += d.table(L, y, W, ["Region", "Farming ฿/mo", "move", "weakest farming province",
                           "Factory", "Transport", "SME", "Office", "employee wage",
                           "farm vs wage"], rows,
                 colw=[1.3, 1.25, 0.9, 2.35, 1.0, 1.15, 0.95, 0.95, 1.4, 1.18], size=9, rh=0.30,
                 aligns=["l", "r", "r", "l", "r", "r", "r", "r", "r", "r"]) + 0.12
    y += d.source(L, y, W, MIX, NAVY,
                  "Income MEASURED — NSO SES province income "
                  f"({II['meta']['vintage']['income']}), NSO LFS regional wages "
                  f"({II['meta']['vintage']['wage_anchor']}), ฿/month; region = unweighted mean of "
                  "its provinces. Move is ESTIMATED — one first-order model of the price and fuel "
                  f"round (fuel driver {II['meta']['vintage']['fuel']}), at documented "
                  "coefficients, not fitted. No monthly SES/LFS series exists, so no 6-month figure "
                  "sits beside it.", size=9) + 0.20

    # Farming and SME are the only occupations with a per-province driver; factory, transport and
    # office each move by one fixed national number — sensitivity x the single measured fuel driver.
    SEN, DRV = II["meta"]["sensitivity"], II["meta"]["drivers"]["fuel_move_pct"]
    tmove = SEN["Transport"]["fuel"] * DRV
    _, floor = min(((k, v) for k, v in reg.items() if v["weak"]),
                   key=lambda kv: kv[1]["weak"][0])
    cw2 = (W - 0.25) / 2
    # "Under half, both" was in the copy this replaces, and the table two inches above disproves it:
    # Isan farms on 54% of its own regional wage, not under 50%. Both ratios are now printed from the
    # same `reg` dict the table reads, so the sentence cannot contradict the row beneath it again.
    n_ratio = 100 * reg["North"]["farm"] / reg["North"]["wage"]
    i_ratio = 100 * reg["Isan"]["farm"] / reg["Isan"]["wage"]
    d.callout(L, y, cw2, "Farming (เกษตรกร) — up everywhere, still the floor",
              "• Best-moving job in every region — and still the lowest-paid.\n"
              f"• North ฿{reg['North']['farm']:,.0f} against a ฿{reg['North']['wage']:,.0f} wage "
              f"({n_ratio:.0f}%); Isan ฿{reg['Isan']['farm']:,.0f} against "
              f"฿{reg['Isan']['wage']:,.0f} ({i_ratio:.0f}%).\n"
              f"• Floor: {floor['weak'][1]} farms on ฿{floor['weak'][0]:,.0f}/mo — size a "
              "programme against this, not the mean.", tone="warn", size=10)
    d.callout(L + cw2 + 0.25, y, cw2, "Transport (ขนส่ง) — one number, not five",
              f"• Down {pct(tmove, 2)} in every region. Factory moves the same way; office is flat "
              "— no channel modelled for it, which is not the same as no change.\n"
              "• One measured crude-oil move through one chosen coefficient. No Thai diesel or "
              "freight series behind it.\n"
              "• Still matters: here the vehicle IS the income. An early call beats a late one.",
              tone="risk", size=10)
    d.notes("Two things: farming is up everywhere and still under half the local wage — size the "
            "programme off the floor province, not the mean. Be upfront that the transport number "
            "is one national assumption, not five measurements.")

    # ============================================ 10 water: the season and the live pulse
    # Drought and the live rain/river pulse read on two different clocks and answer two
    # different questions, so each now gets its own table rather than one merged read: SPEI is
    # MODELLED and monthly — has the season had enough water; ThaiWater is MEASURED and live —
    # what is happening today. GISTDA's repeated-flood census is a third, separate thing, kept
    # to its own card and never blended into either table.
    y = d.content("08 · Water", "Where it is driest, and where it is wettest — right now.")
    y += d.bullets(L, y, W, [
        "SPEI (ภัยแล้ง, drought) is modelled once a month — how the season has gone, not "
        "today’s weather.",
        "ThaiWater is measured every day — rain gauges and river levels (น้ำท่วม, flood), live.",
        "GISTDA is a separate 12-year census — ground that has flooded before, not what is "
        "happening now.",
    ], size=10.5) + 0.18
    ac = load("amphoe_crops.json")
    # Distinct province·district·crop cells at severe-or-worse SPEI that actually have planted area —
    # the same dedup build_amphoe_crops.py uses for its own headline, since the raw rows carry the
    # same cell more than once where two OAE sources cover it.
    sev_cells = {(r["province_th"], r["amphoe_th"], r["crop"]) for r in ac["rows"]
                 if r.get("drought") in ("severe", "extreme") and (r.get("planted_rai") or 0) > 0}
    TWR, TWF = load("thaiwater_rain.json"), load("thaiwater_flood.json")
    # ThaiWater's own observation window, not the pull timestamp: the gauges report to 05:00 Bangkok,
    # so the file is fetched on one date and is current to the next. append_history dates the series
    # the same way. Rain and river are two separate feeds and occasionally land a day apart, so each
    # keeps its own stamp rather than sharing one.
    rain_to = (TWR["meta"].get("observed_to") or TWR["meta"]["pulled"])[:10]
    flood_to = (TWF["meta"].get("observed_to") or TWF["meta"]["pulled"])[:10]
    heavy = sum(1 for v in TWR["provinces"].values() if v["pct_heavy"] > 0)
    FLH = load("flood_hazard.json")["meta"]
    chronic = FLH["n_branches_chronic"]
    y += d.cards(L, y, W, [
        ("Districts in drought", f"{mn['n_dry']}",
         f"of {mn['n_districts']} ({mn['dry_share_pct']}%) · SPEI mean {mn['spei_mean']:.2f}", RED),
        ("Extreme band", f"{mn['n_extreme']}", "districts at the extreme drought band", RED),
        ("District-crop cells", f"{len(sev_cells)}",
         f"of {len(ac['rows']):,} measured cells at severe drought or worse", GOLD),
        ("Stations above high mark", f"{mn['flood_high']}",
         f"of {mn['flood_stations']} ({mn['flood_high_pct']}%) · live · {flood_to}", RED),
        ("Provinces with heavy rain", f"{heavy}", f"latest daily reading · {rain_to}", GOLD),
        ("Ground that floods anyway", f"{100 * chronic / FLH['n_branches']:.0f}%",
         f"{chronic:,} of {FLH['n_branches']:,} branch locations flooded in "
         f"{FLH['chronic_threshold']}+ of 12 years", GOLD),
    ], cols=6, ch=1.16) + 0.20

    cw2 = (W - 0.25) / 2
    # Bilingual short crop labels for the drought table — the OAE Thai names run long (18
    # characters for cassava's factory-grade name), and a short English word beside a short Thai
    # term is what the bilingual pass asked for. Falls back to the OAE Thai name for any crop
    # code not in this list, so an unmapped crop still prints something rather than crashing.
    CROP_LABEL = {
        "black_pepper": "Pepper (พริกไทย)", "cassava": "Cassava (มัน)",
        "coconut_aromatic": "Coconut (มะพร้าว)", "coconut_mature": "Coconut (มะพร้าว)",
        "coffee": "Coffee (กาแฟ)", "durian": "Durian (ทุเรียน)",
        "feed_corn_round1": "Maize (ข้าวโพด)", "feed_corn_round2": "Maize (ข้าวโพด)",
        "longan": "Longan (ลำไย)", "longkong": "Longkong (ลองกอง)",
        "mangosteen": "Mangosteen (มังคุด)", "oil_palm": "Oil palm (ปาล์ม)",
        "pineapple": "Pineapple (สับปะรด)", "rambutan": "Rambutan (เงาะ)",
        "rice_dry_season": "Rice, dry (นาปรัง)", "rice_wet_season": "Rice, wet (นาปี)",
        "rubber": "Rubber (ยาง)",
    }
    d.text(L, y, cw2, "Drought (ภัยแล้ง) — worst planted-area cells", size=10, bold=True, color=NAVY)
    d.text(L + cw2 + 0.25, y, cw2, "Rain & rivers (น้ำท่วม) — worst today, live", size=10,
           bold=True, color=NAVY)
    y += 0.26
    rows_dry = [[(h["province_th"], True, NAVY), h["amphoe_th"],
                 CROP_LABEL.get(h["crop"], h["crop_th"]),
                 (f"{h['planted_rai']:,.0f}", False, NAVY), (f"{h['spei']:.2f}", True, RED),
                 (h["drought"], False, RED)] for h in ac["hotspots"][:6]]
    ty = y
    th1 = d.table(L, ty, cw2, ["Driest cells", "District", "Crop", "Rai", "SPEI", "Band"],
                  rows_dry, colw=[1.00, 1.35, 1.35, 0.85, 0.70, 0.84], size=9, rh=0.27,
                  aligns=["l", "l", "l", "r", "r", "l"])
    # Same 77 provinces ranked worst-first: river level (5 = bank overflow) leads, rain intensity
    # is the tiebreak — a live read, re-ranked on every pull, never a fixed watch-list.
    wet = []
    for p, r in TWR["provinces"].items():
        f = TWF["provinces"].get(p, {})
        wet.append((p, r["n_stations"], r["max_mm"], r["pct_heavy"], f.get("n_high"),
                    f.get("n_stations"), f.get("max_level")))
    wet.sort(key=lambda w: (-(w[6] or 0), -w[3]))
    rows_wet = []
    for p, nrain, mm, ph, nhigh, nriver, lvl in wet[:6]:
        rows_wet.append([(p, True, NAVY), (f"{nrain}", False, NAVY), (f"{mm:.0f}", False, NAVY),
                         (f"{ph:.1f}%", True, GOLD if ph > 0 else GREY),
                         (f"{nhigh}/{nriver}" if nhigh is not None else "—", True,
                          RED if (nhigh or 0) > 0 else NAVY),
                         (f"{lvl}" if lvl is not None else "—", True,
                          RED if (lvl or 0) >= 5 else (GOLD if lvl == 4 else NAVY))])
    th2 = d.table(L + cw2 + 0.25, ty, cw2,
                  ["Wettest today", "Rain gauges", "Max mm/24h", "% heavy+", "River ≥high",
                   "Level"], rows_wet, colw=[1.25, 1.00, 1.05, 0.95, 1.00, 0.84], size=9, rh=0.27,
                  aligns=["l", "r", "r", "r", "r", "r"])
    y += max(th1, th2) + 0.12
    h1 = d.text(L, y, cw2, "Severe drought at planting means a lighter harvest and less cash "
                "this season.", size=9.5, color=GREY, lh=13)
    h2 = d.text(L + cw2 + 0.25, y, cw2, "High rivers and heavy rain threaten roads, fields and "
                "branches right now — today’s reading, not a forecast.", size=9.5, color=GREY,
                lh=13)
    y += max(h1, h2) + 0.14
    y += d.source(L, y, W, MIX, NAVY,
                  f"Planted area MEASURED (OAE — {len(ac['rows']):,} amphoe crop rows). Drought "
                  "is a MODELLED SPEI index from rainfall and evapotranspiration, refreshed "
                  f"monthly, retrieved {ac['meta']['retrieved']} — the best national-coverage "
                  "signal available, but nobody has walked those districts. Rain and river "
                  "telemetry MEASURED (ThaiWater, live, pulled daily and accumulated — a missed "
                  f"pull leaves a gap rather than an invented point) · rain to {rain_to}, river "
                  f"to {flood_to}. Structural flood exposure MEASURED (GISTDA 1:50,000 "
                  f"repeated-flooding census, {FLH['data_vintage']} — a 12-year ground record, "
                  "not a forecast).", size=9)
    d.notes("Two clocks, kept apart: SPEI is the season (modelled, monthly), ThaiWater is today "
            "(measured, live). GISTDA is a third, separate thing — which ground floods anyway — "
            "its own card, never blended into either table.")

    # ==================================== 11 where a pre-emptive conversation is worth having
    # The ranking IS the signal count (the measured debt/unemployment composite only breaks ties),
    # and the lead crop is the full eight-crop OAE mix, not income_impact's rice/rubber/palm-only one.
    PSI = load("province_stress_index.json")
    y = d.content("09 · Where to reach out first",
                  "Provinces ranked by how many stress signals tripped.")
    SIGNALS = [
        ("1  Debt (หนี้)", "debt-to-income ≥ 100% of a year's income"),
        ("2  Unemployment (การว่างงาน)", "unemployment ≥ 2%"),
        ("3  Crop (พืชหลัก)", "lead crop pays below cost"),
        ("4  Rain (ฝน)", "rainfall < 90% of normal"),
    ]
    cw2s = (W - 0.30) / 2
    for i, (lab, desc) in enumerate(SIGNALS):
        col, row = i % 2, i // 2
        d.text(L + col * (cw2s + 0.30), y + row * 0.27, cw2s, f"{lab}  —  {desc}",
               size=10.5, color=NAVY)
    y += 2 * 0.27 + 0.08
    y += d.text(L, y, W, "Ordered by signals tripped; ties broken on debt + unemployment.",
                size=9.5, color=GREY) + 0.14
    croploss = {c["crop_en"]: c["national"]["loss"] for c in CFI["crops"]}
    psi = {p["province"]: p for p in PSI["provinces"]}
    scored = []
    for nm2, pm in CM["provinces"].items():
        st = psi.get(nm2)
        if not st:
            continue
        lead = max(pm["crops"], key=lambda c: c["share"])
        lossy = croploss.get(lead["en"])                       # None = no OAE cost series
        rain = FB["provinces"].get(nm2, {}).get("rain_pct_of_normal")
        flags = [st["debt_to_income"] >= 1.0, st["unemployment_rate"] >= 2.0,
                 lossy is True, rain is not None and rain < 90]
        scored.append((sum(flags), st["composite_stress"], nm2, pm, st, lead, lossy, rain))
    scored.sort(key=lambda r: (-r[0], -r[1]))
    rows = []
    for flags, _cs, nm2, pm, st, lead, lossy, rain in scored[:8]:
        agri = ((II["provinces"].get(nm2, {}).get("occ") or {}).get("Agriculture") or {})
        rows.append([(nm2, True, NAVY), (pm["region"], False, GREY),
                     (f"{100 * st['debt_to_income']:.0f}%", True,
                      RED if st["debt_to_income"] >= 1.0 else NAVY),
                     (f"{st['unemployment_rate']:.2f}%", True,
                      RED if st["unemployment_rate"] >= 2.0 else NAVY),
                     (f"{lead['en']} {100 * lead['share']:.0f}%", False, NAVY),
                     ("below cost" if lossy else ("covers cost" if lossy is False else "not published"),
                      True, RED if lossy else (GREEN if lossy is False else GREY)),
                     (f"{rain:.0f}%" if rain is not None else "—", True,
                      RED if (rain is not None and rain < 90) else NAVY),
                     (f"{agri['income']:,.0f}" if agri.get("income") else "—", False, NAVY),
                     (f"{pm['area_rai'] / 1e6:.2f}M", False, NAVY),
                     (f"{flags} of 4", True, RED if flags >= 3 else GOLD)])
    y += d.table(L, y, W, ["Province", "region", "household debt", "unemployment", "lead crop",
                           "crop economics", "rain vs normal", "farm ฿/mo", "planted rai",
                           "tripped"], rows,
                 colw=[1.65, 1.05, 1.35, 1.35, 1.85, 1.35, 1.3, 1.0, 1.05, 0.78], size=9,
                 rh=0.278,
                 aligns=["l", "l", "r", "r", "l", "l", "r", "r", "r", "r"]) + 0.16
    y += d.source(L, y, W, MIX, NAVY,
                  "Household debt-to-income MEASURED (NSO SES 2566 — debt as a share of ANNUAL "
                  "income, so above 100% is more debt than a year of earnings). Unemployment "
                  "MEASURED (NSO LFS, by province). Lead crop MEASURED (OAE planted area, all eight "
                  "crops); its economics ESTIMATED from OAE cost of production "
                  f"({CFI['crops'][0]['vintage']}). Rainfall MEASURED as "
                  "precipitation against the long-run normal, a different instrument from the SPEI "
                  "index two slides back; two provinces carry no gauge and cannot trip this signal.",
                  size=9) + 0.18
    crop_trip = sum(1 for r in scored if r[6] is True)
    d.callout(L, y, W, "Crop is a poor discriminator",
              f"It trips {crop_trip} of {len(scored)} provinces — national exposure, not who to "
              "call. Debt, jobs and rain are what separate this list.", tone="warn", size=10.5)
    d.notes("Ranked on how many of four signals tripped, not on two of them — that is why "
            "สิงห์บุรี appears despite low debt. The crop test trips almost everywhere and does "
            "not discriminate; debt, jobs and rain do. Geographies, not people.")

    # ================================================================ 11 collateral divider
    d.divider("10 · Collateral", "This is the half with a decision attached.",
              "We lend against titles, so the used-vehicle market is an external condition that "
              "prices our security directly. Five things are moving at once: what a used vehicle is "
              "worth, how many are entering the pool, which brands they are, which nameplates "
              "underneath those brands, and how easily any of them can be sold on. A model with no "
              "Thai residual history is a recovery assumption nobody can make yet.")
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
                     (pct(p6), True, GREEN if p6 > 0 else RED),
                     (pct(p12), True, GREEN if p12 > 0 else RED),
                     (f"{t12['low']['value']:.1f}", False, NAVY),
                     (f"{t12['high']['value']:.1f}", False, NAVY),
                     (f"{s['vs_2015_base_pp']:+.1f}", True, RED),
                     (pct(s['change_since_peak_pct']), True, RED)])
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
    d.callout(L + 7.75, y, W - 7.75, "Two windows, one message",
              "\n".join(f"• {b}" for b in [
                  f"Pickup {pct(t6)} in 6 months, {pct(t12)} in 12 — the fall has stopped.",
                  f"Car {pct(c6)} in 6 months, {pct(c12)} in 12 — same shape, weaker level.",
                  f"Pickup is {abs(UV['truck']['vs_2015_base_pp']):.0f} pts below its 2015 base, "
                  f"car {abs(UV['car']['vs_2015_base_pp']):.0f} pts.",
                  "Pre-2022 advance rates price a market that no longer exists.",
              ]), tone="risk", size=10)
    y += 2.20 + 0.16
    d.source(L, y, W, MEAS, GREEN,
             "Bank of Thailand used-vehicle price index (EC_EI_040), 185 monthly points; 6- and "
             "12-month moves computed from the published series, rebased to 2015 = 100. Pickup = "
             "confirmed pickup trucks (รถกระบะ), not heavy commercial (BoT Stat-Horizon "
             "methodology, 2019). Latest month preliminary.", size=9)
    d.notes(f"Two windows: pickup {pct(t6)} over six months but {pct(t12)} over twelve — the fall "
            "has stopped, not reversed. Level still well below 2015.")

    # ================================================================ 13 registration windows
    y = d.content("10b · Collateral supply", "Two vehicle markets, moving opposite ways.")
    y += d.text(L, y, W, "DLT first registrations, AutoX’s own pickup definition — any pickup or "
                "PPV, any class. Six- and 12-month windows, side by side.",
                size=11, color=GREY, lh=15) + 0.16
    Wd = VM["windows"]

    # The six-month window ends on a month the pipeline itself flags. Both the pickup's positive
    # slope and the car's YoY spike are computed WITH it, so the trend column is re-derived without
    # it — the chart below makes the reason visible before the callouts make the argument.
    m6 = Wd["m6"]
    last = m6["to"] in m6["contains_flagged_months"]

    def wrow(basis, label):
        w6, m12 = m6[basis], Wd["m12"][basis]
        y6 = 100 * (w6["units"] / w6["prior_units"] - 1)
        y12 = 100 * (m12["units"] / m12["prior_units"] - 1)
        sl = ols_slope(w6["monthly"][:-1] if last else w6["monthly"])
        return [(label, True, NAVY),
                (f"{m12['units']:,}", False, NAVY),
                (pct(y12), True, GREEN if y12 > 0 else RED),
                (f"{w6['units']:,}", False, NAVY),
                (pct(y6), True, GREEN if y6 > 0 else RED),
                (f"{sl:+,.0f}", True, GREEN if sl > 0 else RED)]
    y += d.table(L, y, W, ["", "12-month units", "12m YoY", "6-month units †", "6m YoY †",
                           "6m trend ex-flag, units/mo"],
                 [wrow("pu", "Pickup + PPV รถกระบะ"), wrow("pa", "Passenger car รถยนต์นั่ง")],
                 colw=[2.6, 2.1, 1.6, 2.1, 1.6, 2.4], size=11, rh=0.36,
                 aligns=["l", "r", "r", "r", "r", "r"]) + 0.06
    y += d.text(L, y, W, f"† flagged months in this window: {', '.join(m6['contains_flagged_months'])} "
                "— registrations pulled forward before an incentive deadline. Only the last is "
                "stripped from the trend column; both YoY columns keep it.",
                size=9, color=GREY, lh=12) + 0.18

    def month_range(frm, to):
        """Every 'YYYY-MM' from frm to to inclusive — computed, not assumed, so a shifted window
        can't silently mislabel the bars below."""
        yy, mm = int(frm[:4]), int(frm[5:7])
        out = []
        while True:
            out.append(f"{yy}-{mm:02d}")
            if out[-1] == to:
                return out
            mm += 1
            if mm > 12:
                mm, yy = 1, yy + 1
    months = month_range(m6["from"], m6["to"])
    cw = (W - 0.25) / 2
    for i, (basis, lab, col) in enumerate([("pu", "Pickup + PPV", RED), ("pa", "Passenger car", NAVY)]):
        mo = m6[basis]["monthly"]
        d.text(L + i * (cw + 0.25), y - 0.02, cw,
               f"{lab} — registrations by month, {m6['from']} → {m6['to']}",
               size=9.5, bold=True, color=NAVY)
        d.bars(L + i * (cw + 0.25), y + 0.20, cw, 1.40,
               [(mm[2:], v, j == len(mo) - 1) for j, (mm, v) in enumerate(zip(months, mo))],
               color=col, fmt=lambda v: f"{v / 1000:,.1f}k")
    y += 0.20 + 1.40 + 0.20

    y12pa = 100 * (Wd["m12"]["pa"]["units"] / Wd["m12"]["pa"]["prior_units"] - 1)
    pu6, pa6 = m6["pu"]["monthly"], m6["pa"]["monthly"]
    pu_ex = ols_slope(pu6[:-1]) if last else ols_slope(pu6)
    pa_ex_units = (sum(pa6[:-1]) / (len(pa6) - 1)) + sum(pa6[:-1]) if last else sum(pa6)
    pa_ex_yoy = 100 * (pa_ex_units / m6["pa"]["prior_units"] - 1)
    pa_y6 = 100 * (m6["pa"]["units"] / m6["pa"]["prior_units"] - 1)

    # The flagged month's own YoY, read off the monthly series rather than typed — it confirms the
    # story even for pickup: the "spike" month is still down against a year ago.
    mo_all = {r["ym"]: r for r in VM["monthly"]}
    prior_ym = f"{int(m6['to'][:4]) - 1}-{m6['to'][5:]}"
    pu_flag_yoy = pa_flag_yoy = None
    if m6["to"] in mo_all and prior_ym in mo_all:
        pu_flag_yoy = 100 * (mo_all[m6["to"]]["pu"] / mo_all[prior_ym]["pu"] - 1)
        pa_flag_yoy = 100 * (mo_all[m6["to"]]["pa"] / mo_all[prior_ym]["pa"] - 1)

    pu_bul = ["Five months fall in a row, then one month jumps — a bar, not a turn.",
              f"Slope with that month in: {m6['pu']['slope_units_per_month']:+,.0f}/mo. "
              f"Without it: {pu_ex:+,.0f}/mo."]
    if pu_flag_yoy is not None:
        pu_bul.append(f"Even that month was {pct(pu_flag_yoy)} YoY for pickups — still falling.")
    ch = d.callout(L, y, cw, "The pickup “trend” is one flagged month",
                   "\n".join(f"• {b}" for b in pu_bul), tone="risk", size=10)
    pa_bul = [f"6-month car growth: {pct(pa_y6)}. Ex-flag: {pct(pa_ex_yoy)}."]
    if pa_flag_yoy is not None:
        pa_bul.append(f"That month alone ran {pct(pa_flag_yoy)} YoY — pulled forward, not demand.")
    pa_bul.append(f"The 12-month figure, {pct(y12pa)}, is the safer read.")
    d.callout(L + cw + 0.25, y, cw, "Most of the car “boom” is one month",
              "\n".join(f"• {b}" for b in pa_bul), tone="warn", size=10)
    y += ch + 0.16
    d.source(L, y, W, MIX, NAVY,
             "Registrations MEASURED — DLT gdcatalog first registrations, 48 months from 2022-01. "
             "Ex-flag figures are our arithmetic on that series — ESTIMATED, a judgement call on "
             "which month to trust.", size=9)
    d.notes(f"Pickup's six-month slope is not a recovery — ex-flag it is {pu_ex:+,.0f}/mo. The same "
            f"month inflates car growth from {pct(pa_ex_yoy)} to {pct(pa_y6)}. Quote the 12-month "
            "windows.")

    # ================================================================ 14 concentration
    y = d.content("10c · Brand concentration", "Two vehicle markets, and only one is holding its shape.")
    pu12, pa12 = Wd["m12"]["pu"], Wd["m12"]["pa"]
    pl = VM["plates_last12"]
    # Nameplates moved to their own slide (10d), so these cards stay strictly at brand grain — two
    # denominators for one Hilux on adjacent slides reads as a contradiction even when both are right.
    ENTRANTS = ("BYD", "MG", "JAECOO", "AION", "DEEPAL")
    ent_share = sum(b["share_pct"] for b in pa12["top_brands"] if b["brand"] in ENTRANTS)
    pu_rest = [b for b in pu12["top_brands"] if b["brand"] not in pu12["majors"]]
    pu3, pu4 = pu_rest[0], pu_rest[1]
    y += d.cards(L, y, W, [
        ("Top 2 pickup brands", f"{pu12['major_share_pct']:.1f}%",
         f"{' + '.join(pu12['majors'])} · was {pu12['prior_major_share_pct']:.1f}% a year ago", GOLD),
        ("Top 2 car brands", f"{pa12['major_share_pct']:.1f}%",
         f"{' + '.join(pa12['majors'])} · down "
         f"{pa12['prior_major_share_pct'] - pa12['major_share_pct']:.1f} points in a year", RED),
        ("Third PU brand", f"{pu3['share_pct']:.1f}%",
         f"{pu3['brand']} · next is {pu4['brand']} at {pu4['share_pct']:.1f}%", NAVY),
        ("New car brands", f"{ent_share:.1f}%",
         "BYD + MG + Jaecoo + AION + Deepal · no Thai residual record", RED),
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
    d.callout(L, y, W, "Two markets, opposite directions",
              "\n".join(f"• {b}" for b in [
                  f"Pickup: Toyota + Isuzu hold {pu12['major_share_pct']:.1f}%, down only "
                  f"{pu12['prior_major_share_pct'] - pu12['major_share_pct']:.1f} points in a year. "
                  "The pool shrinks; its shape barely changes.",
                  f"Car: {pa12['prior_major_share_pct'] - pa12['major_share_pct']:.1f} points "
                  f"surrendered in a year. {ent_share:.1f}% of new cars now carry no Thai residual "
                  "record.",
                  "We know what a five-year-old Hilux is worth. We do not yet know what a "
                  "five-year-old BYD is worth.",
              ]), tone="risk", size=10)
    d.notes("Pickup pool shrinks without changing shape — residual values stay predictable. Cars are "
            "the opposite: a growing share carries no Thai residual record to price against.")

    # ============================================ 17 nameplates as a share of their own market
    # Brands were the previous slide; this is the grain below it, because a title is written against
    # a MODEL, not a marque. Shares are computed against each market's OWN 12-month total — PU over
    # pickup+PPV combined (183k), PA over cars (444k) — rather than the sub-totals the layer emits,
    # so "share of its market" means the same thing on both sides of the slide.
    pu_units = pl["pickup"]["units"] + pl["ppv"]["units"]
    pa_units = pl["car"]["units"]
    pu_all = sorted(pl["pickup"]["top"] + pl["ppv"]["top"], key=lambda r: -r["units"])
    pa_all = pl["car"]["top"]
    pu_top5 = 100.0 * sum(r["units"] for r in pu_all[:5]) / pu_units
    pa_top5 = 100.0 * sum(r["units"] for r in pa_all[:5]) / pa_units
    pa_top1 = 100.0 * pa_all[0]["units"] / pa_units
    y = d.content("10d · The nameplates",
                  f"Top 5 pickups are {pu_top5:.1f}% of the market. The top car is {pa_top1:.1f}%.")
    y += d.cards(L, y, W, [
        ("Top 5 PU nameplates", f"{pu_top5:.1f}%",
         f"of the {pu_units:,} pickups and PPVs registered in 12 months", GOLD),
        ("Top 5 PA nameplates", f"{pa_top5:.1f}%",
         f"of the {pa_units:,} cars — the same five-model test, less than half the answer", RED),
        ("Biggest PU nameplate", f"{100.0 * pu_all[0]['units'] / pu_units:.1f}%",
         f"{pu_all[0]['plate']} · {pu_all[0]['units']:,} units · {pu_all[0]['yoy_pct']:+.1f}% YoY", RED),
        ("Biggest PA nameplate", f"{pa_top1:.1f}%",
         f"{pa_all[0]['plate']} · {pa_all[0]['units']:,} units · {pa_all[0]['yoy_pct']:+.1f}% YoY", NAVY),
    ], cols=4, ch=1.14) + 0.20
    cw2 = (W - 0.25) / 2

    def prow(r, tot, ppv_set):
        yv = r.get("yoy_pct")
        return [(r["plate"], True, NAVY),
                ("PPV" if r["plate"] in ppv_set else "", False, GREY),
                (f"{r['units']:,}", False, NAVY),
                (f"{100.0 * r['units'] / tot:.2f}%", True, NAVY),
                ((f"{yv:+.1f}%" if yv is not None else "new"), True,
                 (GREEN if yv > 0 else RED) if yv is not None else GOLD)]
    ppv_set = {r["plate"] for r in pl["ppv"]["top"]}
    d.text(L, y, cw2, f"PU nameplates — share of the {pu_units:,}-unit pickup + PPV market",
           size=9.5, bold=True, color=NAVY)
    d.text(L + cw2 + 0.25, y, cw2, f"PA nameplates — share of the {pa_units:,}-unit car market",
           size=9.5, bold=True, color=NAVY)
    y += 0.24
    d.table(L, y, cw2, ["PU nameplate", "", "12-month units", "share of PU", "YoY"],
            [prow(r, pu_units, ppv_set) for r in pu_all[:8]],
            colw=[2.05, 0.6, 1.35, 1.25, 0.84], size=9, rh=0.258,
            aligns=["l", "l", "r", "r", "r"])
    y += d.table(L + cw2 + 0.25, y, cw2, ["PA nameplate", "12-month units", "share of PA", "YoY"],
                 [[c for i, c in enumerate(prow(r, pa_units, set())) if i != 1]
                  for r in pa_all[:8]],
                 colw=[2.65, 1.35, 1.25, 0.84], size=9, rh=0.258,
                 aligns=["l", "r", "r", "r"]) + 0.16
    y += d.source(L, y, W, MEAS, GREEN,
                  "DLT first registrations at the registrar's own ยี่ห้อ + รุ่น grain, trailing 12 "
                  "months to " + VM["meta"]["latest_month"] + ", NATIONAL only. PU shares are over "
                  "pickup + PPV combined, PA shares over cars, so each is a share of its own market. "
                  "One caveat that only bites the right-hand table: DLT files many car models per "
                  "TRIM — 1,235 distinct car nameplate strings against 443,641 cars, Toyota alone "
                  "filing 172 — so each PA share is a floor. Merging every trim would not close the "
                  "gap: BYD's entire car volume is 11.3%, still under the single biggest PU "
                  "nameplate.", size=9) + 0.18
    d.bullets(L, y, W, [
        f"Top 5 pickup nameplates cover {pu_top5:.1f}% of the market — priced off years of Thai "
        "resale history.",
        f"Top 5 car nameplates cover only {pa_top5:.1f}%, and the single biggest is just "
        f"{pa_top1:.1f}%.",
        "New brands — BYD, MG, Jaecoo, AION, Deepal — carry no Thai resale record; some registered "
        "for the first time this year.",
        "An advance rate is set per model. PU is five rows we can price. PA is a long tail we "
        "cannot, yet.",
    ], size=10.5)
    d.notes("Advance rates are set per model, not brand. PU is five rows we can price from "
            "history. PA is a long tail of models registered for the first time this year — the "
            "trim-split caveat makes PA shares a floor, but it does not change the conclusion.")

    # ============================================ 17b four years of nameplates
    # The owner asked for "the total stock of the models in the market going back as many years as
    # you have data". The honest answer is that no such series exists: DLT publishes a true
    # registered stock (จดทะเบียนสะสม) but only by class, province and fuel — it carries no brand or
    # model column. The longest nameplate history any Thai source supports is FIRST registrations,
    # 2022 onward, which is a flow into the fleet, not the parc. The slide says so in its own
    # headline rather than in a footnote, because "stock" and "flow" answer different questions and
    # a four-year fall in the flow is the more useful of the two here anyway.
    PAN = VM["plates_annual"]
    yrs = sorted(PAN)

    def kunits(yy, kinds):
        return sum(PAN[yy][k]["units"] for k in kinds if k in PAN[yy])

    pu_u = [kunits(v, ("pickup", "ppv")) for v in yrs]
    pa_u = [kunits(v, ("car",)) for v in yrs]
    pu_fall = 100.0 * (pu_u[-1] / pu_u[0] - 1)
    pa_move = 100.0 * (pa_u[-1] / pa_u[0] - 1)
    y = d.content("10f · Four years of nameplates",
                  f"Pickups entering the road are down {abs(pu_fall):.0f}% since {yrs[0]}. "
                  f"Cars are {'down' if pa_move < 0 else 'up'} {abs(pa_move):.0f}%.")
    y += d.cards(L, y, W, [
        (f"Pickups + PPV, {yrs[0]}", f"{pu_u[0]:,}", "first registrations that year", NAVY),
        (f"Pickups + PPV, {yrs[-1]}", f"{pu_u[-1]:,}", f"{pct(pu_fall)} over four years", RED),
        (f"Cars, {yrs[0]}", f"{pa_u[0]:,}", "first registrations that year", NAVY),
        (f"Cars, {yrs[-1]}", f"{pa_u[-1]:,}", f"{pct(pa_move)} over four years", GREEN),
    ], cols=4, ch=1.10) + 0.18

    def plate_rows(kinds, n=7):
        """Top nameplates of the LATEST year, traced back through the earlier ones.

        Each year publishes its own top 15, so a nameplate outside an early year's top 15 has no
        figure here — that prints as an em-dash rather than a zero, because "we did not rank it"
        and "none were registered" are different claims and only one of them is true."""
        per = {}
        for v in yrs:
            agg = {}
            for k in kinds:
                for t in PAN[v].get(k, {}).get("top", []):
                    agg[t["plate"]] = agg.get(t["plate"], 0) + t["units"]
            per[v] = agg
        order = sorted(per[yrs[-1]], key=lambda p: -per[yrs[-1]][p])[:n]
        out = []
        for p in order:
            first, last = per[yrs[0]].get(p), per[yrs[-1]][p]
            out.append([(p.title(), True, NAVY)]
                       + [(f"{per[v][p]:,}" if p in per[v] else "—", False,
                           NAVY if p in per[v] else GREY) for v in yrs]
                       + [(pct(100.0 * (last / first - 1), 0) if first else "—", True,
                           (GREEN if last > first else RED) if first else GREY)])
        return out

    cw2 = (W - 0.25) / 2
    d.text(L, y, cw2, "Pickup + PPV nameplates", size=9.5, bold=True, color=NAVY)
    d.text(L + cw2 + 0.25, y, cw2, "Car nameplates", size=9.5, bold=True, color=NAVY)
    y += 0.24
    hdr = ["Nameplate"] + list(yrs) + ["4-yr"]
    cwl = [1.85, 0.82, 0.82, 0.82, 0.82, 0.96]
    d.table(L, y, cw2, hdr, plate_rows(("pickup", "ppv")), colw=cwl, size=9, rh=0.262,
            aligns=["l", "r", "r", "r", "r", "r"])
    y += d.table(L + cw2 + 0.25, y, cw2, hdr, plate_rows(("car",)), colw=cwl, size=9, rh=0.262,
                 aligns=["l", "r", "r", "r", "r", "r"]) + 0.14
    y += d.source(L, y, W, MEAS, GREEN,
                  "DLT first registrations at the registrar's own ยี่ห้อ + รุ่น grain, from the "
                  f"yearly roll-up files so the mirror's missing 2023-12 month cannot distort a "
                  f"year. {yrs[0]}–{yrs[-1]} are the only complete years published. These are "
                  "vehicles entering the fleet, NOT the stock on the road — no DLT dataset carries "
                  "brand or model against registered stock, so a total parc by nameplate does not "
                  "exist and is not shown here. An em-dash means the nameplate was outside that "
                  f"year's top {len(PAN[yrs[-1]]['car']['top'])}, not that none were registered.",
                  size=9) + 0.16
    d.callout(L, y, W, "The collateral pool is shrinking faster than it is changing shape",
              f"Four years took {pu_u[0] - pu_u[-1]:,} pickups a year out of the flow — "
              f"{abs(pu_fall):.0f}% — while cars held roughly flat. Fewer new pickups now means a "
              "thinner supply of five-year-old pickups to lend against later, and the nameplates "
              "are the same ones: this is a volume problem, not a mix problem.", tone="risk",
              size=10)
    d.notes("Say the caveat first: this is what ENTERED the road each year, not what is on it — "
            "DLT publishes no stock by model, so the parc by nameplate cannot be built. What it "
            "shows is a four-year collapse in pickup supply with the same nameplates on top "
            "throughout, which is a volume problem rather than a mix problem.")

    # ================================================================ 17 recovery depth + EV
    # The owner's ask: show pickup, car AND motorcycle as a share of the same regional parc — not
    # pickup alone — so the comparison across all three classes is the point of the table, not a
    # side note. Shares and turnover both come from the same collateral_book used_flow rows.
    uf_rows = CB["used_flow"]
    tot_parc = sum(r["all"]["processed"] for r in uf_rows)
    pu_nat = 100.0 * sum(r["pickup"]["processed"] for r in uf_rows) / tot_parc
    car_nat = 100.0 * sum(r["car"]["processed"] for r in uf_rows) / tot_parc
    moto_nat = 100.0 * sum(r["moto"]["processed"] for r in uf_rows) / tot_parc
    y = d.content("10e · The second-hand market",
                  f"Pickups are {pu_nat:.0f}% of the parc — cars {car_nat:.0f}%, motorcycles "
                  f"{moto_nat:.0f}%.")
    fc = {f["key"]: f for f in CB["fleet_classes"]}
    y += d.cards(L, y, W, [
        ("Pickup stock รถกระบะ", f"{fc['pickup']['latest'] / 1e6:.2f}M",
         f"registered pickups nationally · {fc['pickup']['yoy_pct']:+.2f}% YoY", RED),
        ("Car stock รถยนต์นั่ง", f"{fc['car']['latest'] / 1e6:.2f}M",
         f"{fc['car']['yoy_pct']:+.2f}% YoY · +{fc['car']['since_2563_pct']:.1f}% since 2563", GREEN),
        ("Diesel share", f"{mn['diesel_share_pct']:.1f}%",
         f"of the {mn['fleet_total'] / 1e6:.1f}M fleet — what the market runs on today", NAVY),
        ("BEV share", f"{mn['bev_pct']:.2f}%",
         f"electrified {mn['electrified_pct']:.2f}% — not a factor this quarter", GOLD),
    ], cols=4, ch=1.12) + 0.20
    # How deep the second-hand market is, region by region — this is the market a repossessed title
    # has to be sold into, so it is the external half of any recovery assumption. Pickup, car and
    # motorcycle each get a share-of-parc column AND a turnover column, on equal footing, so the
    # reader compares all three classes rather than reading pickup against an unlabelled remainder.
    def urow(uf):
        parc = uf["all"]["processed"]
        pu_t = uf["pickup"]["transfer_rate"] * 100
        return [(uf["region"], True, NAVY),
                (f"{parc / 1e6:.2f}M", False, NAVY),
                (f"{100 * uf['pickup']['processed'] / parc:.1f}%", False, NAVY),
                (f"{100 * uf['car']['processed'] / parc:.1f}%", False, NAVY),
                (f"{100 * uf['moto']['processed'] / parc:.1f}%", False, NAVY),
                (f"{pu_t:.2f}%", True, RED if pu_t < 6 else NAVY),
                (f"{uf['car']['transfer_rate'] * 100:.2f}%", False, NAVY),
                (f"{uf['moto']['transfer_rate'] * 100:.2f}%", False, NAVY)]
    y += d.table(L, y, W, ["Region", "Registered", "PU share", "Car share", "Moto share",
                           "PU turnover", "Car turnover", "Moto turnover"],
                 [urow(uf) for uf in uf_rows],
                 colw=[1.55, 1.55, 1.45, 1.45, 1.55, 1.60, 1.60, 1.68], size=10, rh=0.30,
                 aligns=["l", "r", "r", "r", "r", "r", "r", "r"]) + 0.16
    y += d.source(L, y, W, MEAS, GREEN,
                  "DLT registered stock and ownership transfers by region and class (PU รถกระบะ · "
                  "car รถยนต์นั่ง · moto รถจักรยานยนต์), plus MOT fleet totals. Share = class "
                  "stock ÷ all registered vehicles in the region. Turnover = "
                  "transfers ÷ registered stock — how much of the parc changes hands a year, the "
                  "depth a repossessed title sells into.", size=9) + 0.20
    cw2 = (W - 0.25) / 2
    pu_rates = [r["pickup"]["transfer_rate"] * 100 for r in uf_rows]
    car_rates = [r["car"]["transfer_rate"] * 100 for r in uf_rows]
    pu_slowest = min(uf_rows, key=lambda r: r["pickup"]["transfer_rate"])
    d.callout(L, y, cw2, "Small and slow, at the same time",
              f"Pickups are only {pu_nat:.0f}% of the vehicle parc — cars {car_nat:.0f}%, "
              f"motorcycles {moto_nat:.0f}% — and still turn over slowest: "
              f"{min(pu_rates):.1f}–{max(pu_rates):.1f}% of pickups change hands a year against "
              f"{min(car_rates):.1f}–{max(car_rates):.1f}% for cars, worst in "
              f"{pu_slowest['region']}.\n\nA smaller, slower market means a longer disposal and a "
              "wider discount on a repossessed title.", tone="risk", size=10)
    d.callout(L + cw2 + 0.25, y, cw2, "Electrification is a clock, not a problem",
              f"BEVs are {mn['bev_pct']:.1f}% of the fleet, electrified {mn['electrified_pct']:.1f}% "
              "— not a factor today.\n\nBut titles resell over five to ten years, and "
              f"{ent_share:.0f}% of new cars already carry no Thai resale history. That fleet ages "
              "into the used market before 2032.", tone="warn", size=10)
    d.notes("The point of the table: pickup is both the smallest class of the three and the "
            "slowest to turn over. Turnover is the depth a repossession actually sells into.")

    # ================================================================ 20 so what
    # Cut to five short asks per the owner's plain-language pass. The farm-income ask used to quote
    # the OAE cost-of-production table on 06 — that table is dropping off 06 entirely, so this ask
    # now stands on the farm-gate PRICE shock (crop_mix.json), the same basis 05 uses, not a cost
    # netting. `scored`/`three_sig` reuse 09's own ranked list rather than retyping its names.
    y = d.content("11 · So what", "Five things the macro picture asks of us.")
    CROP_TH = {"Rice": "ข้าว", "Rubber": "ยางพารา", "Oil palm": "ปาล์มน้ำมัน", "Cassava": "มันสำปะหลัง",
               "Maize": "ข้าวโพด", "Coconut": "มะพร้าว", "Pineapple": "สับปะรด", "Sugarcane": "อ้อย"}
    four_sig = [r[2] for r in scored if r[0] == 4]
    three_sig = [r[2] for r in scored if r[0] == 3]
    worst_neg = CM["national"]["worst"][0]
    fall_names = ", ".join(f"{k} ({CROP_TH.get(k, k)})" for k, _ in FALLING)
    fall_area = sum(AREA.get(k, 0.0) for k, _ in FALLING)
    transport_move = (II["meta"]["sensitivity"]["Transport"]["fuel"]
                      * II["meta"]["drivers"]["fuel_move_pct"])
    y += d.qa(L, y, W, [
        ("Call the four-signal provinces first",
         f"{four_sig[0]} trips all four warning flags. {word(len(three_sig)).capitalize()} more trip "
         f"three — {', '.join(three_sig)}."),
        ("Watch the provinces left behind",
         f"Median crop income rose {pct(CM['national']['median_shock_pct'])}, but "
         f"{word(CM['national']['negative_provinces'])} provinces fell — all on the coconut "
         f"({CROP_TH['Coconut']}) belt, worst {worst_neg['prov']} at {pct(worst_neg['shock_pct'])}."),
        (f"Track the {word(len(FALLING))} crops still falling",
         f"{fall_names} keep falling at the farm gate (ราคาที่เกษตรกรขายได้) — {fall_area:.0f}% of "
         "the country’s planted land."),
        ("Reprice the vehicle we lend against",
         f"Pickup resale is still {abs(UV['truck']['vs_2015_base_pp']):.0f} points below its 2015 "
         f"level, the slowest-selling class on the road. Five nameplates cover {pu_top5:.0f}% of "
         "that market; new car brands do not."),
        ("Read two signals as models, not facts",
         f"Transport income moves {pct(transport_move)} on one national fuel number, no Thai "
         "freight data behind it. Drought (ภัยแล้ง) is a rainfall model — nobody has walked those "
         "districts."),
    ], qw=3.60, size=13.5) + 0.22
    y += d.callout(L, y, W, "Scope, stated",
                   "External data only — the economy, crops, water, vehicles. It points at places, "
                   "never at people; turning a place into a call list is the Assistance tab’s job. "
                   "Nothing here argues to open, close or expand anything.") + 0.14
    # The vintage line is the deck's own provenance footer, so it reads every stamp it can off the
    # layer rather than restating one. A vintage line that has to be hand-edited after a refresh is
    # the first thing to go stale and the last thing anyone checks.
    d.text(L, y, W, "Vintages — world prices 2026M06 · Thai farm gate "
           f"{max(r['local_date'] for r in B_THAI)} · Thai price history "
           f"{load('thai_price_history.json')['meta']['vintage']} · crop cost of production OAE "
           f"Cai-up {CFI['crops'][0]['vintage']} · "
           f"drought 2026-06-21 · CPI {cpi['period']} · GDP {gdp['period']} · IMF WEO 2026 · resale "
           f"index 2026-05 · registrations to {VM['meta']['latest_month']} · household debt NSO SES "
           f"2566 · wages NSO LFS 2568 · telemetry {rain_to}.",
           size=9, color=GREY, lh=12.5)
    d.notes("Five short asks, easiest slide in the deck to read. The farm-income ask now stands on "
            "the price shock, not the OAE cost table — that argument left with 06. Close on scope: "
            "external conditions only, no book, no open/close/expand call.")

    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--preview", action="store_true", help="render PNG thumbnails to check fit")
    ap.add_argument("--review", action="store_true",
                    help="also write mcom-review.html — the sign-off page (implies --preview)")
    a = ap.parse_args()

    d = build()
    d.fit_vertical()          # horizontal fit is checked as each box is made; this is the other axis
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
    if a.preview or a.review:
        pngs = d.preview(Path(a.out) / "preview")
        print("preview written")
        if a.review:
            p = d.review(pngs, Path(a.out) / "mcom-review.html",
                         "MCOM · Wednesday 5 August 2026<br>The Macro tab",
                         "Scope is one tab and nothing else: external conditions only — no loan "
                         "book, no competition, no branch readouts. Every image below is rendered "
                         "from the real PowerPoint geometry, and every figure in it is read out of "
                         "platform/data/ at build time rather than transcribed.",
                         out.name)
            print(f"review page written -> {p}")


if __name__ == "__main__":
    main()
