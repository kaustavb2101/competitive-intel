#!/usr/bin/env python3
"""build_live_board.py — the LIVE BOARD: every live feed, how fresh it is, and its trend line.

Kaustav: "since we have so much live data, we should be displaying all these live data on a
dashboard somewhere with historical trend lines. This creates a level of dynamism that regular
platforms wouldn't have."

He is right, and this is the honest version of it. The platform pulls from ~20 independent
sources on cadences from DAILY (pump diesel, rain gauges) to ANNUAL (OAE production). Nowhere
did the app say, in one place, *what is live, when it last moved, and whether it is still
current*. That is what this layer is: one row per feed, carrying its own stamp, its own cadence,
and a pointer to real history where real history exists.

TWO RULES THIS BUILDER WILL NOT BEND
------------------------------------
1. **No invented history.** A trend line is drawn ONLY where a stored series actually exists.
   Four feeds have one (see HISTORY below); ~18 do not — they are point-in-time pulls that
   overwrite on each run. Those get an explicit "history not retained yet" state and a named
   reason, never a fabricated line, never a two-point line pretending to be a trend.

2. **No wall clock in this file.** Everything under platform/data/ is byte-reproducible and
   --check-gated; reading datetime.now() here would make the output differ on every run and
   break the gate. So the builder records each feed's STAMP and its cadence thresholds, and the
   BROWSER computes age against the reader's own clock at render time. That is also the more
   correct split: "is this stale?" is a question about now, not about build time.

HISTORY — the four feeds that genuinely carry a series
-----------------------------------------------------
  sfi_credit.json        73 quarters, 2008-Q1 -> 2026-Q1  (FPO: SFI NPL ratio + credit stock)
  commodity_history.json 60 months, 11 series             (World Bank Pink Sheet)
  imf_weo.json           12 years x 5 indicators          (IMF WEO — INCLUDES FORECAST YEARS)
  macro_indicators.json  6 points x 2 indicators          (BIS: household debt, policy rate)

The IMF series is the one that needs care: it runs past the current year into projection. The
builder marks `actual_through` so the page can render forecast years differently. A forecast
drawn as if it were measured history would be exactly the kind of quiet dishonesty this product
is supposed to avoid.

Usage:  python3 build_live_board.py [--check]
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "platform", "data")
OUT = os.path.join(DATA, "live_board.json")

# The newest year the IMF WEO vintage carries as an OUTTURN rather than a projection. The WEO
# publishes actuals through the year before the release and projects onward; this pull is the
# 2025 vintage, so 2025 is the last actual. Kept as a named constant because it must move when
# the WEO vintage moves — a stale value would mislabel a projection as measured history.
WEO_ACTUAL_THROUGH = 2025


# ---------------------------------------------------------------- stamp handling
# Feed stamps arrive in whatever shape their publisher uses: '2026-07-31', '2026-06', '2026M06',
# '2026-Q1', '2026 Q1 (BE 2569)', '2025 (BE 2568)', '2026-02-28'. Normalise each to the ISO date
# the period ENDS on, because that is the moment the data is current to — a '2026-Q1' figure is
# not one day old on 2 Jan, it is current through 31 Mar. Returns None when a stamp cannot be
# parsed, and the page then shows the raw string with no age rather than guessing.
_MONTH_END = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
              7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


def stamp_to_iso(s):
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", t)                      # 2026-07-31
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{4})[-\s]?Q([1-4])", t)                        # 2026-Q1 / 2026 Q1 (BE ...)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        mo = q * 3
        return f"{y:04d}-{mo:02d}-{_MONTH_END[mo]:02d}"
    m = re.match(r"^(\d{4})[-M](\d{2})$", t)                          # 2026-06 / 2026M06
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return f"{y:04d}-{mo:02d}-{_MONTH_END[mo]:02d}"
    m = re.match(r"^(\d{4})\b", t)                                    # 2025 (BE 2568) / 2568 (...)
    if m:
        return f"{be_to_ce(int(m.group(1))):04d}-12-31"
    return None


def be_to_ce(y):
    """Thai sources stamp in the Buddhist era, and they do not always say so. NSO's wage anchor
    is stamped '2568 (4-quarter average)' with no 'BE' marker — read literally that is the year
    2568 CE and the board would report the feed as 542 years in the FUTURE, i.e. permanently
    fresh. Anything past 2400 is unambiguously BE (CE 2400 is centuries away; BE 2400 = 1857),
    so fold it back. Years already in CE pass through untouched."""
    return y - 543 if y > 2400 else y


def read(fn):
    p = os.path.join(DATA, fn)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def dig(obj, path):
    """Walk a dotted path; integer segments index lists. Missing -> None, never an exception:
    an absent field must degrade to an honest '—' on the board, not take the build down."""
    cur = obj
    for seg in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            if not seg.lstrip("-").isdigit():
                return None
            i = int(seg)
            cur = cur[i] if -len(cur) <= i < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
    return cur


def stamp_of(doc, override=None):
    """Pick a feed's stamp, preferring the most specific thing it publishes about itself:
    when it was pulled > what it is as-of > what vintage it is > when the app updated it.

    `override` names a layer-specific field for feeds that carry their vintage under a name of
    their own — the loan tape stamps itself `meta.mob_anchor` (the newest disbursement month IN
    the data, never wall clock), which is a truer vintage than anything in the standard chain."""
    m = (doc or {}).get("meta") or {}
    keys = ([override] if override else []) + ["pulled", "as_of", "vintage", "updated"]
    for k in keys:
        v = m.get(k)
        if isinstance(v, str) and v.strip() and v.strip().lower() != "none":
            return v.strip(), k
    return None, None


# ---------------------------------------------------------------- cadence thresholds
# fresh_days / aging_days are the age at which a feed stops being current and then stops being
# usable, expressed relative to its OWN cadence — a 3-day-old daily pump price is stale, a
# 3-day-old annual census is brand new. 'reference' feeds are registries/censuses that only move
# when the publisher reissues them; ageing them would cry wolf, so they carry no thresholds.
CADENCE = {
    "daily":     {"fresh": 2,   "aging": 7},
    "weekly":    {"fresh": 10,  "aging": 21},
    "monthly":   {"fresh": 45,  "aging": 75},
    "quarterly": {"fresh": 130, "aging": 210},
    "annual":    {"fresh": 400, "aging": 550},
    "reference": {"fresh": None, "aging": None},
}


def money_bn(v):
    """FPO/BoT publish in millions of baht; the board reads in billions."""
    return None if v is None else round(v / 1000.0, 1)


# ---------------------------------------------------------------- the feed registry
# One entry per live source. `what` is deliberately written in plain language and in terms of the
# BOOK, not in terms of the dataset — "what does this move for us" is the only reason a feed is
# on this page at all. `pick` returns (display_value, unit) from the loaded doc.
def _n(x):
    return len(x) if isinstance(x, (list, dict)) else None


# NABC quotes each commodity in its own trade unit and can change a category's quoted product. The
# board therefore reads the unit out of the data rather than asserting one: hardcoding "฿/tonne"
# would keep printing it against a per-kg number if rice ever moved to a kg-quoted product, which
# is a wrong number rather than a missing one.
_THB_UNIT = {"บาท/ตัน": "฿/tonne", "บาท/กก.": "฿/kg", "บาท/ร้อยผล": "฿/100 fruit"}


def _farmgate_rice(d):
    price = dig(d, "commodities.rice.price")
    unit = dig(d, "commodities.rice.unit")
    return price, _THB_UNIT.get(unit, unit or "")


def _thai_price_history():
    """History block for the Thai farm-gate row, read from the file instead of hardcoded.

    The four static history dicts below carry a literal point count that has to be bumped by hand
    when the series grows. This series gains a month every month, so a literal would start
    under-reporting it immediately. Returns None if the file is absent, which leaves the row with
    the usual honest no-history line rather than a broken link."""
    doc = read("thai_price_history.json") or {}
    series = doc.get("series") or {}
    rice = series.get("Rice") or {}
    n = rice.get("n_months") or len(rice.get("months") or [])
    if not n:
        return None
    return {
        "file": "thai_price_history.json", "kind": "thai_farmgate", "series": "Rice", "points": n,
        "note": "%d months, %s → %s, %d commodities — NABC Thai farm-gate, %d provinces quoting"
                % (n, rice.get("first_month"), rice.get("last_month"), len(series),
                   rice.get("n_provinces") or 0),
    }


REGISTRY = [
    # ---- daily -------------------------------------------------------------
    dict(key="fuel_prices", file="fuel_prices.json", cadence="daily",
         label="Diesel · retail pump", group="Cost of living",
         what="the cost line under every vehicle-collateral borrower — pickups and trucks run on it",
         pick=lambda d: (dig(d, "headline.diesel"), "฿/L"), measured=True,
         hist_series="fuel_diesel"),
    dict(key="thaiwater_rain", file="thaiwater_rain.json", cadence="daily",
         label="Rain gauges reporting", group="Hazard",
         what="live rain telemetry behind the farm book — the early half of drought and flood",
         pick=lambda d: (sum((p or {}).get("n_stations", 0) for p in (d.get("provinces") or {}).values()) or None,
                         "stations"), measured=True,
         hist_series="rain_max_mm"),
    dict(key="thaiwater_flood", file="thaiwater_flood.json", cadence="daily",
         label="River stations above high mark", group="Hazard",
         what="branches whose catchment is flooding now — collateral and collection both stop",
         pick=lambda d: (sum((p or {}).get("n_high", 0) for p in (d.get("provinces") or {}).values()),
                         "of " + str(sum((p or {}).get("n_stations", 0)
                                         for p in (d.get("provinces") or {}).values()))), measured=True,
         hist_series="flood_high"),
    # The DOMESTIC farm-gate price. It sorts directly above "Rice · world price" in the same group,
    # which is deliberate — they are the two rice numbers on this page and a reader should see them
    # together and see that they differ. ฿/tonne daily vs $/mt monthly keeps them apart at a glance.
    dict(key="farmgate_prices", file="farmgate_prices.json", cadence="daily",
         label="Rice · Thai farm-gate", group="Farm income",
         what="what a borrower's crop actually sells for at home, today — the number behind farm "
              "repayment capacity, not the world price beside it",
         pick=_farmgate_rice, measured=True,
         history=_thai_price_history),

    # ---- weekly / monthly --------------------------------------------------
    dict(key="rival_ads", file="rival_ads.json", cadence="weekly",
         label="Rivals running paid ads", group="Competition",
         what="which title lenders are buying demand right now, and at what advertised rate",
         pick=lambda d: (_n(d.get("brands")), "brands live"), measured=True,
         hist_series="rival_ads_live"),
    dict(key="rival_youtube", file="rival_youtube.json", cadence="weekly",
         label="Rival YouTube channels", group="Competition",
         what="the rivals' own broadcast reach — upload cadence and audience",
         pick=lambda d: (_n(d.get("channels")), "channels"), measured=True),
    dict(key="social_themes", file="social_themes.json", cadence="weekly",
         label="Borrower themes tracked", group="Competition",
         what="what borrowers are actually asking for, from reviews and forums, vs what lenders answer",
         pick=lambda d: (_n(d.get("demand")), "demand themes"), measured=True),
    dict(key="commodity_history", file="commodity_history.json", cadence="monthly",
         label="Rice · world price", group="Farm income",
         what="the GLOBAL benchmark in $/mt, monthly — context for the Thai farm-gate price above "
              "it, not a substitute for it",
         pick=lambda d: (dig(d, "series.rice.values.-1"), "$/mt"), measured=True,
         history=dict(file="commodity_history.json", kind="commodity", points=60,
                      note="60 months, 11 series — World Bank Pink Sheet")),
    dict(key="dbd_formation", file="dbd_formation.json", cadence="monthly",
         label="New businesses registered", group="Merchant book",
         what="merchant-segment formation — new small firms are the merchant book's feedstock",
         pick=lambda d: (sum((p or {}).get("n", 0) for p in (d.get("by_province") or {}).values()) or None,
                         "juristic persons"), measured=True),

    # ---- quarterly ---------------------------------------------------------
    dict(key="macro_indicators", file="macro_indicators.json", cadence="quarterly",
         label="Household debt", group="Macro",
         what="the national leverage backdrop every borrower sits inside",
         pick=lambda d: (dig(d, "indicators.household_debt_gdp.value"), "% GDP"), measured=True,
         history=dict(file="macro_indicators.json", kind="bis", points=6,
                      note="6 quarters — BIS household debt + policy rate")),
    dict(key="sfi_credit", file="sfi_credit.json", cadence="quarterly",
         label="SFI system NPL", group="Macro",
         what="18 years of state-lender credit quality — the closest public read on the same borrower",
         pick=lambda d: (dig(d, "series.-1.npl_ratio"), "%"), measured=True,
         history=dict(file="sfi_credit.json", kind="sfi", points=73,
                      note="73 quarters, 2008-Q1 onward — FPO SFI aggregates")),
    dict(key="province_lfs", file="province_lfs.json", cadence="quarterly",
         label="Labour force survey", group="Macro",
         what="employment and wage base per province — whether borrowers can pay",
         pick=lambda d: (_n(d.get("provinces")), "provinces"), measured=True),
    dict(key="credit_anchor", file="credit_anchor.json", cadence="quarterly",
         label="Banking-system NPL", group="Macro",
         what="the BoT anchor our own book is read against",
         pick=lambda d: (dig(d, "metrics.0.value"), "%"), measured=True),

    # ---- annual / reference ------------------------------------------------
    dict(key="imf_weo", file="imf_weo.json", cadence="annual",
         label="Real GDP growth", group="Macro",
         what="the growth backdrop, with ASEAN peers as an external benchmark",
         pick=lambda d: (dig(d, f"thailand.NGDP_RPCH.series.{WEO_ACTUAL_THROUGH}"), "% (latest actual)"),
         measured=True,
         history=dict(file="imf_weo.json", kind="weo", points=12,
                      actual_through=WEO_ACTUAL_THROUGH,
                      note="12 years x 5 indicators — IMF WEO, later years are PROJECTIONS")),
    dict(key="tape_real", file="tape_real.json", cadence="reference",
         label="Loan tape", group="The book",
         what="the real book — every published figure on Risk, Assistance and Exposure comes from here",
         pick=lambda d: (dig(d, "meta.n_accounts"), "accounts"), measured=True,
         stamp_path="mob_anchor"),
    dict(key="pico_census", file="pico_census.json", cadence="reference",
         label="Licensed PICO operators", group="Competition",
         what="the licensed small-lender field around our branches",
         pick=lambda d: (sum((p or {}).get("total", 0) for p in (d.get("by_province") or {}).values()) or None,
                         "service points"), measured=True),
    dict(key="ev_penetration", file="ev_penetration.json", cadence="annual",
         label="Vehicle registry (DLT)", group="Collateral",
         what="the collateral pool itself — what is registered, and how fast EVs are displacing it",
         pick=lambda d: (_n(d.get("provinces")), "provinces"), measured=True),
    dict(key="search_demand", file="search_demand.json", cadence="weekly",
         label="Brand share of search", group="Competition",
         what="where borrowers look for a lender first, and whether they type our name",
         pick=lambda d: (_n(d.get("provinces")), "provinces"), measured=True,
         hist_series="search_share_autox"),
    # 'reference', not quarterly: the BoT Regional Letters sit on NSO SES vintages (4-region cut =
    # SES 2019, Northern deep-dive = SES 2023), so this moves when BoT reissues, not each quarter.
    # Ageing it on a quarterly clock would flag a permanently-red feed that is behaving normally.
    # The count is series ROWS across national/region/province — series.province holds 5 indicator
    # records, not 5 provinces, so counting it as provinces was simply wrong.
    dict(key="region_debt", file="region_debt.json", cadence="reference",
         label="BoT regional debt series", group="Macro",
         what="BoT household-debt indicators by region — the backdrop nearer the grain we lend at",
         pick=lambda d: (sum(_n(dig(d, "series." + k)) or 0
                             for k in ("national", "region", "province")), "indicator rows"),
         measured=True),
    dict(key="nso_wage_anchor", file="nso_wage_anchor.json", cadence="annual",
         label="NSO wage anchor", group="Macro",
         what="measured wages by region — the income base under every affordability read",
         pick=lambda d: (_n(d.get("headline_rows")), "region rows"), measured=True),
    dict(key="peer_scoreboard", file="peer_scoreboard.json", cadence="quarterly",
         label="Listed rival scoreboard", group="Competition",
         what="the listed title lenders' own filings — external benchmark, not a target",
         pick=lambda d: (_n(d.get("peers")), "listed peers"), measured=True,
         # MTC's own market cap as the representative history line — peer_scoreboard.json is
         # built straight from source-data/set_peers.json (build_peer_scoreboard.py), the same
         # file append_history.py now accumulates, so this is the same underlying pull.
         hist_series="set_mtc_mcap"),
]

# Feeds with no stored series, and WHY — shown verbatim on the board so "no trend line" reads as
# a known state with a fix, not as something missing. These are the append-history candidates.
NO_HISTORY_REASON = {
    "fuel_prices": "each pull overwrites the last; appending a daily row would give a price line",
    "thaiwater_rain": "each pull overwrites the last; appending would give a rainfall line",
    "thaiwater_flood": "each pull overwrites the last; appending would give a flood-stage line",
    "rival_ads": "creative-level first_seen/last_seen is kept; the live-creative count is now being "
                 "accumulated too, and becomes a line once several weekly pulls have landed",
    "rival_youtube": "channel stats are point-in-time; subscriber history is not stored",
    "social_themes": "theme mix is recomputed per run, not accumulated",
    "dbd_formation": "one month per pull; the DBD monthly files would stack into a series",
    "province_lfs": "one NSO quarter per pull",
    "credit_anchor": "one FSR vintage per pull",
    "tape_real": "one export; a second dated export unlocks book-over-book movement",
    "pico_census": "one FPO registry snapshot per pull",
    "ev_penetration": "one DLT vintage per pull",
    "search_demand": "Google Trends is already relative-to-window; absolute history is not kept",
    "region_debt": "one BoT vintage per pull",
    "nso_wage_anchor": "one NSO vintage per pull",
    "peer_scoreboard": "one filing round per pull",
}


def accumulated_history():
    """The series append_history.py has accumulated, keyed by series name.

    These are the feeds whose SOURCE only publishes 'now'. Their history is not something the
    publisher offers — it is something this repo has been keeping, one dated row per pull, so it
    only exists once enough pulls have landed. The registry names a series; this decides whether
    there is yet enough of it to draw. Absent file -> no series -> every one of them keeps its
    honest 'not retained yet' line, which is exactly the state before the accumulator ran."""
    doc = read("feed_history.json") or {}
    # chart_min comes from that layer's own meta rather than being restated here: one definition of
    # "enough points to draw", owned by the builder that enforces it.
    return doc.get("series") or {}, ((doc.get("meta") or {}).get("chart_min") or 4)


def build():
    feeds, missing = [], []
    accum, chart_min = accumulated_history()
    for spec in REGISTRY:
        doc = read(spec["file"])
        if doc is None:
            missing.append(spec["file"])
            continue
        stamp, stamp_kind = stamp_of(doc, spec.get("stamp_path"))
        try:
            value, unit = spec["pick"](doc)
        except Exception:
            # A registry path that no longer matches its layer must not take the build down —
            # the feed still belongs on the board, with an honest blank where the number was.
            value, unit = None, ""
        cad = CADENCE[spec["cadence"]]
        row = {
            "key": spec["key"],
            "label": spec["label"],
            "group": spec["group"],
            "what": spec["what"],
            "file": spec["file"],
            "cadence": spec["cadence"],
            "fresh_days": cad["fresh"],
            "aging_days": cad["aging"],
            "stamp": stamp,
            "stamp_kind": stamp_kind,
            "stamp_iso": stamp_to_iso(stamp),
            "value": value,
            "unit": unit,
            "measured": bool(spec.get("measured")),
            "source": ((doc.get("meta") or {}).get("source") or "")[:180],
            # A callable history block is read from its own file at build time, so a growing series
            # cannot be under-reported by a literal that nobody remembered to bump.
            "history": spec["history"]() if callable(spec.get("history")) else spec.get("history"),
        }
        # A feed with an accumulated series gets a real history block — same shape as the ones
        # whose publisher ships history, because by this point it IS the same thing: dated
        # observations we can draw. Until it clears the chartable bar it keeps its no-history line,
        # so a two-point stub never masquerades as a trend.
        acc = accum.get(spec.get("hist_series") or "")
        if not row["history"] and acc and acc.get("chartable"):
            row["history"] = {
                "file": "feed_history.json", "kind": "accumulated",
                "series": spec["hist_series"], "points": acc["n"],
                "note": "%d observations from %s, accumulated here one pull at a time — "
                        "the source itself publishes only today's value"
                        % (acc["n"], acc["first_seen"]),
            }
        if not row["history"]:
            # An accumulator that has started but not yet filled says so, with its real count —
            # "waiting for 3 more nightly pulls" is a different and far more useful state than
            # "this will never have history", and the registry's static reason cannot tell them apart.
            if acc:
                row["no_history"] = ("accumulating — %d observation%s since %s; the line is drawn "
                                     "once %d have landed"
                                     % (acc["n"], "" if acc["n"] == 1 else "s",
                                        acc["first_seen"], chart_min))
            else:
                row["no_history"] = NO_HISTORY_REASON.get(spec["key"], "point-in-time pull")
        feeds.append(row)

    feeds.sort(key=lambda f: (f["group"], f["label"]))
    with_hist = [f for f in feeds if f.get("history")]

    out = {
        "meta": {
            "source": "Per-feed stamps read from each platform/data layer's own meta block "
                      "(pulled / as_of / vintage / updated). No value is re-derived here.",
            "n_feeds": len(feeds),
            "n_with_history": len(with_hist),
            "history_points": sum(f["history"]["points"] for f in with_hist),
            "missing_files": sorted(missing),
            "freshness_note": "Age is computed in the browser against the reader's clock, not "
                              "baked in here — this layer is deterministic and --check-gated, so "
                              "it carries no wall clock. Each feed's fresh/aging thresholds are "
                              "relative to its OWN cadence.",
            "history_note": "A trend line is drawn only where a stored series exists. "
                            f"{len(with_hist)} of {len(feeds)} feeds carry one; the rest are "
                            "point-in-time pulls that overwrite on each run and say so.",
            "forecast_note": f"IMF WEO years after {WEO_ACTUAL_THROUGH} are PROJECTIONS and are "
                             "rendered distinctly from measured history.",
        },
        "feeds": feeds,
    }
    return out


def main():
    out = build()
    body = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        if not os.path.exists(OUT):
            print("FAIL: live_board.json missing")
            return 1
        with open(OUT, encoding="utf-8", newline="") as fh:
            cur = fh.read()
        if cur == body:
            print("OK: live_board.json reproduces exactly")
            return 0
        print(f"FAIL: live_board.json differs (have {len(cur)}B, rebuilt {len(body)}B)")
        return 1
    # newline="" so the file is LF on every platform: build_provenance.py records byte sizes and
    # a CRLF write here would fail the gate on CI with a phantom size drift.
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
    m = out["meta"]
    print(f"live_board.json written — {m['n_feeds']} feeds, {m['n_with_history']} with real history "
          f"({m['history_points']} stored points)")
    if m["missing_files"]:
        print("  absent layers (skipped, not faked): " + ", ".join(m["missing_files"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
