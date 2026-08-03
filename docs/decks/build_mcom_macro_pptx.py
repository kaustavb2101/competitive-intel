"""MCOM · Wednesday 5 August 2026 — the Macro tab, as a house-style PPTX.

Scope is deliberately one tab. The Macro tab answers a narrower question than the rest of the
platform — what is happening OUTSIDE the company that will show up inside it — and Kaustav's
instruction was that the deck covers that and nothing else. The loan book, competition and
branch-level readouts are separate tabs and are not in here.

Every figure is transposed from `docs/decks/mcom-2026-08-05-macro.html`, which was itself checked
figure-by-figure against `platform/data/`. Provenance travels with each number: a MEASURED chip
means a source published it, ESTIMATED means we modelled it, MIXED means the parts differ.

    python docs/decks/build_mcom_macro_pptx.py [--out DIR] [--preview]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deckkit import CARD, GOLD, GREEN, GREY, LINE, NAVY, RED, WHITE, Deck, TX  # noqa: E402

L, W = 0.45, 12.43            # content column
MEAS, EST, MIX = "MEASURED", "ESTIMATED", "MIXED"
DATA = Path(__file__).resolve().parents[2] / "platform" / "data"


def load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def uvpi_series():
    """The BoT used-vehicle index, straight out of the layer the app reads — 185 monthly points
    per series. Plotted rather than summarised because the whole argument on that slide is about
    the SHAPE: pickups tracked cars until 2022 and then did not."""
    d = load("used_vehicle_value.json")
    out = {}
    for key in ("truck", "car"):
        h = d["series"][key]["history"]
        pts = []
        for row in h:
            y, m = row["period"].split("-")
            pts.append((int(y) + (int(m) - 1) / 12.0, row["value"]))
        out[key] = pts
    return out


def build():
    d = Deck()

    # ---------------------------------------------------------------- 1 cover
    d.cover(
        "Macro: the external conditions\nmoving the book.",
        "MCOM · Wednesday 5 August 2026 · AutoX / บริษัท ออโต้ เอกซ์ จำกัด (เงินไชโย)",
        "Aug ’26")
    d.notes("Scope note up front: this is the Macro tab only — external data, none of it is our "
            "loan book. The book, competition and branch views are separate tabs and separate "
            "conversations. Four questions, and the fourth one is the answer.")

    # ---------------------------------------------------------------- 2 the answer
    y = d.content("The answer first", "Four questions. The fourth one is the deck.")
    y += d.text(L, y, W, "Nothing on this page is our loan book. The question the Macro tab answers "
                "is narrower and more useful: what is happening outside the company that will show "
                "up inside it.", size=11.5, color=GREY, lh=15.5) + 0.22
    y += d.qa(L, y, W, [
        ("Is the economy the problem?",
         "No. Growth and inflation both came in above what the IMF projected for 2026, and the "
         "policy rate is at 1.00%. The macro backdrop is a mild tailwind."),
        ("Are crop prices the problem?",
         "Not on the world index — rice +17.9%, rubber +32.4%, palm +18.2%. But on the measured Thai "
         "farm gate nine commodities are falling, led by coconut −70.9%, pineapple −20.0% and sugar "
         "−17.9%. Six of those nine were invisible on our own board until 2 August."),
        ("So what is deteriorating?",
         "The collateral. Used pickup values sit 50% below their peak and 33 points below their own "
         "2015 base, and new pickup registrations have fallen 59% in three years. That is the pool "
         "we lend against, shrinking and cheapening at the same time."),
        ("And the borrower?",
         "Drought first — 338 of 928 districts (36.4%) are dry, and a price tailwind does not reach "
         "a household whose field did not yield. But the farm gate is now a second, separate hazard "
         "rather than the same story told twice."),
    ], size=12.5) + 0.26
    d.source(L, y, W, MEAS,
             GREEN, "Each figure on the following pages carries its own provenance chip. MEASURED "
             "means a source published it; ESTIMATED means we modelled it. They should be read "
             "differently.")
    d.notes("Lead with this. If they take one thing away: the macro is fine, the crops are fine, "
            "the collateral is not, and the borrower stress is drought rather than price.")

    # ---------------------------------------------------------------- 3 macro overlay
    y = d.content("01 · Macro overlay", "The backdrop is benign — and it is finally current.")
    y += d.cards(L, y, W, [
        ("GDP growth", "+2.8%", "YoY · a measured quarter, not a projection · NESDC 2026-Q1", GREEN),
        ("Inflation", "+2.79%", "headline CPI YoY · TPSO, Ministry of Commerce · 2026-05", GOLD),
        ("Policy rate", "1.00%", "Bank of Thailand policy rate · 2026-06", NAVY),
        ("USD / THB", "33.47", "ECB reference rate · 2026-07-31", NAVY),
        ("Household debt", "87.5%", "of GDP · BIS · 2025-Q4", GOLD),
        ("Tourist arrivals", "32.2M", "trailing 12 months · −6.6% YoY · BoT 2026-06", RED),
    ], cols=3) + 0.18
    y += d.source(L, y, W, MEAS, GREEN,
                  "All six are pulled from the publishing agency, not typed in. NESDC · TPSO · "
                  "Bank of Thailand · BIS · ECB.") + 0.20
    y += d.callout(L, y, W, "Thailand has already overtaken the IMF’s 2026 projection",
                   "The IMF projected 1.5% growth and 0.9% inflation for 2026. The measured "
                   "outturns are +2.8% and +2.79% — 1.3 and 1.9 points higher. Where a Thai "
                   "measurement exists we show it instead of the projection, and say which is "
                   "which.") + 0.16
    d.callout(L, y, W, "One number is deliberately not on this page",
              "The current account printed −7,591 USD million in April 2026, but the trailing twelve "
              "months of the same series net to roughly +847M. A single month shown alone would read "
              "as a national crisis and would be wrong. The honest trailing figure is not built yet, "
              "so the chip waits.", tone="warn")
    d.notes("Until last week this page quoted a World Bank annual average showing Thailand in "
            "deflation at −0.13%, when the Ministry of Commerce had already measured +2.79% for "
            "May. Every chip now comes from a Thai official source with its vintage stamped on it.")

    # ---------------------------------------------------------------- 4 commodity board
    y = d.content("02 · Commodity board", "The world index says tailwind. The Thai farm gate does not.")
    y += d.text(L, y, W, "The board carries 21 commodities. Seventeen now have a measured Thai "
                "farm-gate price beside the world index — and nine of those seventeen are negative "
                "year on year. Six of them were invisible here until 2 August, because the feed kept "
                "crop forms only and silently dropped livestock, fishery and orchard prices.",
                size=11, color=GREY, lh=15) + 0.16
    dn = RED
    rows = [
        [("Coconut", True, NAVY), "Crops", "S · E", ("−70.9%", True, dn), ("—", False, GREY), "40,394"],
        [("Pineapple", True, NAVY), "Crops", "E · W · N", ("−20.0%", True, dn), ("—", False, GREY), "27,227"],
        [("Sugar", True, NAVY), "Crops", "Isan · Central", ("−17.9%", True, dn), ("−13.5%", False, dn), "90,216"],
        [("Rambutan", True, NAVY), "Crops", "S · E", ("−13.5%", True, dn), ("—", False, GREY), "42,960"],
        [("Pork", True, NAVY), "Livestock", "C · W · E", ("−6.7%", True, dn), ("—", False, GREY), "145,045"],
        [("Beef", True, NAVY), "Livestock", "Isan", ("−6.1%", True, dn), ("+11.8%", True, GREEN), "136,293"],
        [("White shrimp", True, NAVY), "Fisheries", "S · E coast", ("−4.3%", True, dn), ("—", False, GREY), "102,961"],
        [("Chicken", True, NAVY), "Livestock", "C · E", ("−2.4%", True, dn), ("−0.6%", False, GREY), "181,413"],
        [("Eggs", True, NAVY), "Livestock", "C · E", ("−1.7%", True, dn), ("—", False, GREY), "181,413"],
    ]
    y += d.table(L, y, W, ["Falling at the farm gate", "Segment", "Belt", "Thai farm-gate YoY",
                           "World index YoY", "Accounts in the belt"], rows,
                 colw=[2.3, 1.5, 2.0, 2.2, 2.0, 2.4], size=10, rh=0.278,
                 aligns=["l", "l", "l", "r", "r", "r"]) + 0.14
    y += d.source(L, y, W, MIX, NAVY,
                  "Prices measured — NABC daily and monthly market feeds, Thai farm-gate, OCSB "
                  "announced cane price, World Bank Pink Sheet 2026M06; farm-gate vintage 2026-08-02. "
                  "The account counts are an ESTIMATED book-footprint read (accounts in each "
                  "commodity’s belt) and they OVERLAP heavily — eggs and chicken are the same "
                  "181,413 poultry keepers. Do not add this column up.", size=9) + 0.16
    d.callout(L, y, W, "Beef is the row that proves the point",
              "The world beef index is +11.8%. The measured Thai farm-gate price is −6.1% — a 17.9 "
              "point divergence. A cattle household in Isan is not experiencing +11.8%, and until "
              "the farm-gate layer landed we had no measured way to say so. Rubber, palm and "
              "cassava run the other way and are genuinely up on both.", tone="risk")
    d.notes("This slide changed on 2 August. The old board showed sugar as the only falling price; "
            "the farm-gate feed had been dropping livestock, fishery and orchard series. If anyone "
            "saw the earlier version, that is the difference. Do not sum the accounts column — the "
            "belts overlap.")

    # ---------------------------------------------------------------- 5 farm households
    y = d.content("03 · Farm households", "Drought is the bigger hazard — and no longer the only one.")
    y += d.text(L, y, W, "Rice, rubber and palm are up, and that tailwind reaches a household only if "
                "the field yielded — 36.4% of Thailand’s districts are in drought, concentrated in the "
                "rice belt that carries most of our farm exposure. The stress scores below are built on "
                "the GLOBAL price proxy, so they do not yet see the falling farm-gate prices on the "
                "previous page.",
                size=11, color=GREY, lh=15) + 0.16
    y += d.cards(L, y, W, [
        ("Districts in drought", "338", "of 928 (36.4%) · SPEI mean −0.84", RED),
        ("Extreme band", "2", "districts at the extreme drought band", RED),
        ("Provinces scored", "77", "all of them, crop mix by planted area", NAVY),
        ("Double-stressed", "0", "but the test runs on world prices — see the note below", GOLD),
    ], cols=4, ch=1.06) + 0.20
    y += d.table(L, y, W, ["Province", "Region", "Dominant crops", "Drought", "Crop-stress rank"], [
        ["อุบลราชธานี", "Isan", "Rice 79% · Rubber 12%", ("0.52", True, GOLD), ("1st — highest", True, RED)],
        ["ร้อยเอ็ด", "Isan", "Rice 92% · Sugarcane 5%", ("0.74", True, RED), ("2nd", False, NAVY)],
        ["สุรินทร์", "Isan", "Rice 88% · Rubber 7%", ("0.59", True, GOLD), ("3rd", False, NAVY)],
        ["ศรีสะเกษ", "Isan", "Rice 86% · Rubber 10%", ("0.55", True, GOLD), ("4th", False, NAVY)],
        ["สุพรรณบุรี", "Central", "Rice 65% · Sugarcane 31%", ("0.95", True, RED), ("5th", False, NAVY)],
        ["นครสวรรค์", "North", "Rice 65% · Sugarcane 20%", ("0.47", True, GOLD), ("6th", False, NAVY)],
    ], colw=[2.2, 1.5, 3.6, 1.5, 3.6], size=10, rh=0.295,
        aligns=["l", "l", "l", "r", "l"]) + 0.16
    y += d.source(L, y, W, MIX, NAVY,
                  "Crop area measured, drought modelled. Crop mix is measured planted area (OAE). "
                  "Drought is a modelled SPEI index, not a field observation. The combined stress "
                  "score is estimated.") + 0.18
    d.callout(L, y, W, "สุพรรณบุรี is the one to watch — and the reason the zero above is soft",
              "Drought 0.95, effectively the top of the scale, and a third of its planted area is "
              "sugarcane, whose Thai farm-gate price is −17.9%. The double-stress test reads 0 "
              "because it runs on the GLOBAL price proxy; on the farm-gate layer that landed on "
              "2 August, this province is drought and falling price at the same time. The test has "
              "not been refitted to the new layer yet, and the zero should be read with that "
              "caveat, not as an all-clear.", tone="warn")
    d.notes("Do not present the zero as an all-clear. The double-stress test still runs on the "
            "global price proxy; the measured Thai farm-gate layer is newer than the test. "
            "สุพรรณบุรี is the worked example of what the refit will pick up.")

    # ---------------------------------------------------------------- 6 divider
    d.divider("04 · Collateral outlook",
              "This is the slide that matters.",
              "We lend against vehicle titles. Both halves of that collateral are deteriorating at "
              "once: what a used vehicle is worth, and how many new ones are entering the pool that "
              "becomes our collateral in three to five years.")
    d.notes("Slow down here. Everything before this was context; this is the part with a decision "
            "attached to it.")

    # ---------------------------------------------------------------- 7 resale
    y = d.content("04a · Resale value", "What a title is worth: 33 points below its own 2015 base.")
    y += d.text(L, y, W, "Bank of Thailand used-vehicle price index, 2015 = 100, 185 monthly "
                "observations.", size=11, color=GREY, lh=15) + 0.16
    y += d.cards(L, y, W, [
        ("Pickup (รถกระบะ)", "66.8", "2026-05 · −50.0% off its 2012 peak · 33.2 pts below base", RED),
        ("Passenger car", "87.8", "2026-05 · −40.5% off peak · 12.2 pts below base", RED),
        ("Overall index", "75.2", "2026-05 · −46.3% off peak · 185 months of history", RED),
        ("Trough behind us?", "Yes", "pickup bottomed at 54.6 in 2024-10 — recovered, not to base", GOLD),
    ], cols=4, ch=1.10) + 0.18
    uv = uvpi_series()
    d.linechart(L, y, 7.55, 2.55, [
        ("Pickup", RED, uv["truck"]),
        ("Car", NAVY, uv["car"]),
    ], ylab="Index, 2015 = 100 · monthly, 2011-01 → 2026-05", baseline=100, ymin=50, ymax=150,
        xticks=[(2011, "2011"), (2015, "2015"), (2019, "2019"), (2022, "2022"), (2026, "2026")])
    d.callout(L + 7.75, y, W - 7.75, "The pickup–car gap is recent, not structural",
              "Through most of 2013–2021 the two lines sit on top of each other — the mean gap was "
              "1.1 index points. It only opens from 2022, and the last twelve months average 26.9 "
              "points. Pickups are now 33.2 points below their own 2015 base against 12.2 for cars: "
              "2.7 times the decline.\n\nWhatever is depressing pickup resale started four years "
              "ago and has not reversed. It is not a long-run property of the asset class — which "
              "means advance rates calibrated on pre-2022 behaviour are calibrated against a market "
              "that no longer exists.", tone="risk", size=10)
    y += 2.55 + 0.16
    d.source(L, y, W, MEAS, GREEN,
             "Bank of Thailand used-vehicle price index (EC_EI_040), 185 monthly observations, both "
             "series independently rebased so their own 2015 average = 100. The pickup series is "
             "confirmed to be pickup trucks (รถกระบะ), not heavy commercial — BoT’s own 2019 "
             "Stat-Horizon methodology paper. The latest month is preliminary.", size=9)
    d.notes("The 2022 break is the useful part. A structural gap would be a fact of the asset class; "
            "a four-year-old gap is something that happened, and things that happen can be "
            "diagnosed.")

    # ---------------------------------------------------------------- 8 inflow
    y = d.content("04b · Collateral supply", "The pool refilling our collateral has more than halved.")
    y += d.text(L, y, W, "DLT first registrations at nameplate grain, on AutoX’s own definition of a "
                "pickup.", size=11, color=GREY, lh=15) + 0.16
    y += d.table(L, y, W, ["Year", "Pickups (PU)", "of which PPV", "Passenger car", "Motorcycle"], [
        ["2022", "453,745", "62,879", "388,164", "1,802,995"],
        ["2023", "359,042", "67,398", "436,636", "1,879,838"],
        ["2024", "222,807", "41,234", "377,374", "1,709,157"],
        [("2025", True, NAVY), ("186,405", True, RED), "42,067", "413,968", "1,736,355"],
    ], colw=[1.5, 2.6, 2.4, 2.7, 2.7], size=11, rh=0.34,
        aligns=["l", "r", "r", "r", "r"]) + 0.22
    # Bars and the callout share one horizontal band — the chart carries the shape of the fall,
    # the callout carries what it means. Both start at the same y on purpose.
    d.bars(L, y, 5.60, 1.90, [
        ("2022", 453745, False), ("2023", 359042, False),
        ("2024", 222807, False), ("2025", 186405, True),
    ])
    d.callout(L + 5.80, y, W - 5.80, "Pickup inflow is down 59% in three years",
              "453,745 → 186,405. Passenger cars and motorcycles are broadly flat over the same "
              "period, so this is specific to pickups, not a general vehicle-market decline.\n\nThe "
              "stock we already lend against is 6.98 million pickups, −0.8% year on year. The "
              "pipeline refilling it has more than halved.", tone="risk", size=10)
    y += 1.90 + 0.20
    d.source(L, y, W, MEAS, GREEN,
             "PU = any pickup nameplate plus any PPV nameplate, in any registration class. A "
             "double-cab D-Max and a Fortuner are both pickups to this business even though the "
             "registrar files them under “passenger car ≤7 seats”. On the registrar’s class column "
             "2025 would read 99,984 — an 86% understatement of what we lend against.", size=9)
    d.notes("The nameplate point is worth making explicitly — on the registrar's own class column "
            "2025 reads 99,984, and anyone quoting that number is understating our collateral "
            "universe by 86%.")

    # ---------------------------------------------------------------- 9 conditions at our grain
    y = d.content("05 · Conditions at our grain", "The same five lenses, country down to a branch.")
    y += d.cards(L, y, W, [
        ("Labour force", "41.9M", "unemployment 0.94% · seasonal idle 0.77% (325k waiting)", NAVY),
        ("Informality", "63.2%", "of employment has no payslip or social cover — our core demographic (2024)", GOLD),
        ("Vehicle fleet", "44.3M", "diesel 56.3% · electrified 2.6% · BEV 0.95%", NAVY),
        ("Districts dry", "36.4%", "338 of 928 · 134 of 794 river stations above high mark (16.9%)", RED),
        ("Household debt", "฿163,930", "per indebted household · 45% of households carry debt", GOLD),
        ("No cushion", "60%", "of households could not cover three months without income", RED),
    ], cols=3) + 0.18
    y += d.source(L, y, W, MEAS, GREEN,
                  "NSO Labour Force Survey · ILOSTAT mirror of Thailand’s official submissions · DLT "
                  "registry · MOT · DBD business registrations · ThaiWater telemetry · BoT. Each "
                  "lens rolls national → region → province → branch on its own correct weight — "
                  "labour force, fleet stock, account count, district count — never a plain average "
                  "of provinces.") + 0.20
    y += d.callout(L, y, W, "Read 0.94% unemployment together with 63.2% informality, never instead of it",
                   "Headline unemployment is structurally near zero in Thailand because informal work "
                   "absorbs the slack. A borrower who loses formal work does not appear in the "
                   "unemployment number — they appear in the informal count, on a lower and less "
                   "predictable income. The unemployment rate is not a stress signal for this book. "
                   "Informality and the seasonal-idle share are.", tone="warn") + 0.14
    d.callout(L, y, W, "Electrification is not a collateral problem yet — but it is the clock",
              "BEVs are 0.95% of the fleet and diesel is still 56.3%. Nothing to act on this quarter. "
              "It is worth watching precisely because our collateral has a five-to-ten-year resale "
              "tail: the fleet mix that matters for recoveries in 2032 is being registered now.")
    d.notes("If someone reaches for the unemployment rate as evidence the borrower is fine, this is "
            "the slide. 0.94% is not a measure of borrower stress in a 63% informal economy.")

    # ---------------------------------------------------------------- 10 live telemetry
    y = d.content("06 · Live", "The one feed that changes daily.")
    y += d.text(L, y, W, "Everything else on this tab is monthly or quarterly. River levels and "
                "rainfall are pulled every day from ThaiWater, and they are the early-warning layer "
                "under the drought and flood picture.", size=11, color=GREY, lh=15) + 0.16
    y += d.cards(L, y, W, [
        ("Stations above high mark", "134", "of 794 (16.9%) · up from 84 on 11 July", RED),
        ("Provinces with heavy rain", "31", "latest reading · 2026-08-03", GOLD),
        ("Heaviest 24h gauge", "180mm", "2026-08-03 · the 08-02 reading hit 608mm", NAVY),
        ("Structural flood exposure", "34%", "685 of 2,015 branches on ground that flooded ≥7 of 12 yrs", GOLD),
    ], cols=4, ch=1.12) + 0.20
    y += d.source(L, y, W, MEAS, GREEN,
                  "ThaiWater live telemetry, pulled daily and accumulated — nothing interpolated, a "
                  "missed pull leaves a gap rather than an invented point. Structural flood exposure "
                  "is the GISTDA 1:50,000 repeated-flooding census, 2005–2016.") + 0.22
    d.callout(L, y, W, "Two different things, deliberately kept apart",
              "The live pulse says what is happening this week. The structural census says which "
              "ground floods repeatedly, whatever the weather is doing today. The second is a hazard "
              "flag — did the ground flood, how often — and explicitly not a flooded-area or loss "
              "estimate, because the source’s per-event polygons overlap and any area total drawn "
              "from them would be wrong.")
    d.notes("34% of branches on repeatedly-flooded ground is a hazard flag on the footprint we "
            "already run. It is not an argument to close anything, and it is not a loss estimate.")

    # ---------------------------------------------------------------- 11 gaps
    y = d.content("07 · What this tab cannot tell you", "Four gaps, said plainly.")
    y += d.text(L, y, W, "A number whose weakness is stated is worth more in a committee room than "
                "one that is quietly wrong.", size=11, color=GREY, lh=15) + 0.22
    for head, body in [
        ("The current account is a single month, not a trend",
         "April 2026 shows −7,591 USD million against a trailing-twelve-month figure of roughly "
         "+847M. The trailing aggregate is not built yet, so the chip is withheld rather than shown "
         "misleadingly."),
        ("Government debt has no Thai source yet",
         "It still reads from the IMF at 2025 vintage while every other chip on the strip is "
         "Thai-official and current."),
        ("The ฿44bn co-pay figure is unconfirmed",
         "The likely referent is ไทยช่วยไทย พลัส — cabinet-approved 2026-05-19, government portion "
         "≈฿49.6bn at its two-month mark — but it does not cleanly match ฿44bn, so it has been left "
         "rather than guessed at."),
        ("Drought is modelled, not observed",
         "SPEI is an index derived from rainfall and evapotranspiration. It is the best "
         "national-coverage signal available, but no one has walked those 338 districts."),
    ]:
        y += d.callout(L, y, W, head, body, tone="warn", size=10) + 0.13
    d.notes("Volunteering the gaps is the point. Two of these — the trailing current account and a "
            "Thai government-debt source — are on the build list; the co-pay figure needs an owner "
            "to confirm the referent.")

    # ---------------------------------------------------------------- 12 so what
    y = d.content("08 · So what", "Three things the macro picture asks of us.")
    y += d.qa(L, y, W, [
        ("Collateral valuation",
         "Pickup resale is 33 points below its own 2015 base and the gap to cars opened only in 2022. "
         "If advance rates on pickup titles were set against pre-2022 behaviour, they are set against "
         "a market that no longer exists."),
        ("Collateral supply",
         "New pickup inflow is down 59% in three years while cars and motorcycles are flat. The pool "
         "we will be lending against in 2030 is being determined now, and it is shrinking faster "
         "than the fleet is."),
        ("Borrower stress",
         "Watch drought, the Thai farm gate and informality — and not the unemployment rate, which "
         "is meaningless in a 63.2% informal economy. 36.4% of districts are dry; nine farm-gate "
         "prices are negative; 60% of households cannot cover three months without income."),
    ], qw=2.90, size=12.5) + 0.24
    y += d.callout(L, y, W, "Scope, stated",
                   "All three are readings of the network and book we already run. Nothing on this "
                   "tab is an argument to open, close or expand anything.") + 0.20
    d.text(L, y, W, "Vintages — world prices 2026M06 · Thai farm gate 2026-08-02 · drought "
           "2026-06-21 · CPI 2026-05 · GDP 2026-Q1 · resale index 2026-05 · registrations 2025 · "
           "telemetry 2026-08-03.   Every figure is reproducible from platform/data/ and gated by "
           "tests/run.sh check.",
           size=9, color=GREY, lh=12.5)
    d.notes("Close on scope. This is a risk lens on the footprint we already run — it makes no "
            "open, close or expand recommendation, by design.")

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
        for p in d.preview(Path(a.out) / "preview"):
            print("preview", p)


if __name__ == "__main__":
    main()
