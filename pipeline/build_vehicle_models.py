#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_vehicle_models.py — what is entering the collateral pool, on AUTOX'S definition of a pickup.

Reads the DLT first-registration mirror at MODEL grain
(source-data/dlt/raw/stat_1_1_01_first_regis_vehicles_car/*.csv — monthly, ยี่ห้อ/รุ่น/จำนวน by
ประเภทรถ, NATIONAL ONLY, no จังหวัด column) and projects it into
platform/data/vehicle_models.json.

WHY THIS EXISTS — the registration class lies about our collateral.
The Land Transport Department files a double-cab D-Max under รย.1, "passenger car ≤7 seats", because
it carries passengers. AutoX does not care: a D-Max is a PICKUP to us, and so is a PPV. Read on the
class column alone, 30.7% of the "car" class is in fact pickup collateral — 21.2% pickup nameplates
plus 9.5% PPV. Any pickup-vs-car split built on the class column is therefore wrong for our purposes,
which is exactly why this layer classifies on the NAMEPLATE instead and states the rule out loud.

The mirror check the other way round is the reassuring one: 95.9% of the personal-truck class matches
a pickup nameplate, and the 4.1% that does not is genuinely not a pickup (Suzuki Carry microvans,
Isuzu NLR/FTR ELF light trucks, Hino XZU, Hiace/Commuter vans). So the nameplate list is complete at
both ends, not merely generous.

WHAT IT ANSWERS
  * The CEO's question is about RECOVERY: these are first registrations, so this is the pool we will
    be seizing and reselling in a few years, not today's book. Labelled that way on the page.
  * MAJOR vs MINOR brand resilience, separately for PU and PA. Our book is concentrated in the major
    brands, so a major-brand share that holds is a different risk picture from one that is eroding —
    and the two classes are behaving completely differently.
  * Trend windows (6 / 12 / 24 / 36 months) so "is it still moving" can be read at more than one
    horizon, anchored on the newest month IN THE DATA, never wall clock.

GRAIN AND HONESTY
  * NATIONAL only. This series carries no province column, so there is no province split to make and
    none is invented. (Brand x province exists elsewhere and is labelled ESTIMATED for that reason.)
  * The mirror ends at the newest month DLT has published, which lags — the layer publishes
    meta.latest_month and meta.months_behind so a stale feed can never read as a collapse in demand.
  * Model strings carry trim and sometimes repeat the brand ("GWM" + "GWM TANK 300", but also
    "GWM TANK" + "300 HYBRID"; "BYD DOLPHIN (435KM-STD)" vs "(490KM-EXT)"). Everything here matches on
    the JOINED "<brand> <model>" string and rolls trims up to a nameplate, so a model split across
    trims is not double-counted as two models.

Deterministic + network-free; --check byte-exact. Exits 3 (SKIP) when the raw mirror is absent — the
mirror is gitignored (it is 380 files of raw gov CSV), so CI has no copy, same convention as
build_brand_trends.py / build_vehicle_flow.py.

  python3 build_vehicle_models.py
  python3 build_vehicle_models.py --check
"""
import argparse
import collections
import csv
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "source-data", "dlt", "raw", "stat_1_1_01_first_regis_vehicles_car")
OUT = os.path.join(ROOT, "platform", "data", "vehicle_models.json")

TH_MONTH = {"มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5, "มิถุนายน": 6,
            "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12}

# ── the taxonomy ──────────────────────────────────────────────────────────────────────────────
# Ordered longest-first WITHIN each group so "HILUX REVO" claims the row before a bare "HILUX", and
# PICKUP is tested before PPV so a Ranger Raptor cannot be mistaken for anything else. Every plate
# below was confirmed present in the mirror before being listed; plates kept at zero volume are
# marked, so the list documents the market rather than a guess.
PICKUP_PLATES = [
    "HILUX REVO", "HILUX CHAMP", "HILUX TRAVO", "HILUX VIGO", "HILUX TIGER", "HILUX",
    "RANGER RAPTOR", "RANGER", "D-MAX", "DMAX", "TRITON", "NAVARA", "BT-50", "BT50",
    "EXTENDER", "COLORADO", "TUNLAND", "POER", "CANNON", "XENON", "AMAROK", "L200",
    "STRADA", "FRONTIER", "NP300", "RODEO", "TFR",
]
# PPV = ladder-frame SUV built on a pickup platform. AutoX counts these as pickups too ("our PU
# includes PPV"), because they recover like a pickup, not like a car.
#   TANK 300 / TANK 500 — GWM, on the Pao/Cannon pickup ladder frame. Tank 300 was the #3 PPV in
#     Thailand in 2025 (7,563 units, 17.2% of the segment) — ahead of the Everest. Do not delete
#     these thinking they are ordinary SUVs.
#   LAND CRUISER FJ — Hilux Champ IMV-0 ladder frame; launches Q2 2026, so it matches zero in a
#     mirror ending 2026-02. Listed now so it is counted the month it appears.
PPV_PLATES = [
    "FORTUNER", "MU-X", "MUX", "PAJERO SPORT", "EVEREST", "TERRA", "TRAILBLAZER", "SW4",
    "TANK 300", "TANK 500", "LAND CRUISER FJ",
]

# The word boundary is load-bearing, not decorative: a plain substring match on "TERRA" also catches
# Lamborghini "HURACAN STERRATO", which is present in this mirror. Digits are excluded on both sides
# too, so "TANK 300" cannot match inside "TANK 3000".
_RE = {p: re.compile(r"(?<![A-Z0-9])" + re.escape(p) + r"(?![A-Z0-9])")
       for p in PICKUP_PLATES + PPV_PLATES}

# Registration classes. We only *report* on the two that carry our collateral; the rest (motorcycles,
# tractors, taxis, trailers) are counted into meta so the totals reconcile rather than vanishing.
CLS_CAR = "รถยนต์นั่งส่วนบุคคลไม่เกิน 7 คน"      # รย.1 passenger car <=7 seats
CLS_TRUCK = "รถยนต์บรรทุกส่วนบุคคล"               # รย.3 personal truck
CLS_CAR7 = "รถยนต์นั่งส่วนบุคคลเกิน 7 คน"        # รย.2 passenger car >7 seats
COLLATERAL_CLASSES = (CLS_CAR, CLS_TRUCK, CLS_CAR7)

# "Major" is defined by what OUR BOOK is concentrated in, not by global size — that is the whole point
# of the resilience question. Kept explicit rather than "top N by volume", because a top-N rule would
# silently reclassify a brand mid-series and make the trend line meaningless.
MAJOR_PU = ("TOYOTA", "ISUZU")
MAJOR_PA = ("TOYOTA", "HONDA")

WINDOWS = (6, 12, 24, 36)

# DLT files the GWM Tank sometimes as brand "GWM" + model "GWM TANK 300", and sometimes as brand
# "GWM TANK" + model "300 HYBRID". Left alone that splits one manufacturer into two brands and
# understates its share in every ranking.
BRAND_ALIAS = {"GWM TANK": "GWM"}

# A trailing month can appear on the catalog as a near-empty stub before the real file lands
# (2026-02 arrived as SIX data rows against a normal ~1,450). Averaged into a share or a slope that
# stub reads as demand collapsing to zero, so it has to be detected rather than trusted: a month
# holding less than this fraction of the median of the months around it is INCOMPLETE, not a month.
STUB_FRACTION = 0.20
# A month whose year-on-year move exceeds this is flagged (not dropped) — Jan-2026 ran +54% YoY in
# the car class while motorcycles were flat, which is a pull-forward ahead of an incentive deadline,
# not underlying demand. Flagged so a window containing it can be read with that in mind.
OUTLIER_YOY = 0.40


def _ym_add(ym, months_delta):
    """Shift a 'YYYY-MM' key by N months. Used so a seasonal comparison is anchored on the CALENDAR,
    not on list position — a gap in the series would otherwise silently shift the comparison."""
    y, m = int(ym[:4]), int(ym[5:])
    t = (y * 12 + (m - 1)) + months_delta
    return "%04d-%02d" % (t // 12, t % 12 + 1)


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _fold_be(year):
    """Thai Buddhist-era years fold to CE by -543, only when > 2400 (repo convention)."""
    return year - 543 if year > 2400 else year


def classify(joined):
    """-> ('pu','<plate>') | ('pa', None). AutoX basis: nameplate wins over registration class."""
    for p in PICKUP_PLATES:
        if _RE[p].search(joined):
            return "pu", p
    for p in PPV_PLATES:
        if _RE[p].search(joined):
            return "pu", p
    return "pa", None


def kind_of(joined):
    """Finer label for reporting: pickup vs ppv vs car."""
    for p in PICKUP_PLATES:
        if _RE[p].search(joined):
            return "pickup", p
    for p in PPV_PLATES:
        if _RE[p].search(joined):
            return "ppv", p
    return "car", None


def _read():
    """-> rows of (ym, cls, brand, model, joined, n). Sorted for determinism."""
    rows = []
    for path in sorted(glob.glob(os.path.join(SRC, "*.csv"))):
        with io.open(path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    y = _fold_be(int(r["ปี พ.ศ."]))
                    n = int(float(r.get("จำนวน") or 0))
                except (KeyError, TypeError, ValueError):
                    continue
                m = TH_MONTH.get((r.get("เดือน") or "").strip())
                if not m or n <= 0:
                    continue
                cls = (r.get("ประเภทรถ") or "").strip()
                brand = (r.get("ยี่ห้อ") or "").strip().upper()
                model = (r.get("รุ่น") or "").strip().upper()
                # The joined string is built from the RAW brand so nameplate matching still sees
                # "GWM TANK 300"; only the reporting brand is folded.
                joined = brand + " " + model
                rows.append(("%04d-%02d" % (y, m), cls, BRAND_ALIAS.get(brand, brand), model,
                             joined, n))
    rows.sort()
    return rows


def _read_annual():
    """Yearly roll-ups (…_ปี_25xx.csv). Same columns MINUS เดือน, so the monthly reader skips them.

    Used for the year table because they are complete by construction: the monthly files are missing
    2023-12 from this mirror, so summing months would understate 2023 and invent a fall that did not
    happen. Returns {ce_year: Counter(class -> units)} plus the nameplate split.
    """
    out = collections.defaultdict(lambda: collections.Counter())
    for path in sorted(glob.glob(os.path.join(SRC, "*_ปี_25*.csv"))):
        with io.open(path, encoding="utf-8-sig", newline="") as fh:
            rdr = csv.DictReader(fh)
            if "เดือน" in (rdr.fieldnames or []):
                continue                      # a monthly file that happens to match the glob
            for r in rdr:
                try:
                    y = _fold_be(int(r["ปี พ.ศ."]))
                    n = int(float(r.get("จำนวน") or 0))
                except (KeyError, TypeError, ValueError):
                    continue
                if n <= 0:
                    continue
                cls = (r.get("ประเภทรถ") or "").strip()
                joined = ((r.get("ยี่ห้อ") or "").strip().upper() + " "
                          + (r.get("รุ่น") or "").strip().upper())
                kind, _p = kind_of(joined)
                c = out[y]
                c["total"] += n
                c["__cls__" + cls] += n
                if cls in COLLATERAL_CLASSES and kind in ("pickup", "ppv"):
                    c["pu"] += n
                    c["pu_" + kind] += n
                elif cls in COLLATERAL_CLASSES:
                    c["pa"] += n
    return out


def _slope(series):
    """Least-squares slope in units per month over an evenly spaced series. None if too short."""
    n = len(series)
    if n < 3:
        return None
    xm = (n - 1) / 2.0
    ym = sum(series) / float(n)
    num = sum((i - xm) * (v - ym) for i, v in enumerate(series))
    den = sum((i - xm) ** 2 for i in range(n))
    return round(num / den, 1) if den else None


def build():
    rows = _read()
    if not rows:
        return None

    all_months = sorted({r[0] for r in rows})

    # ── which months are real months ─────────────────────────────────────────────────────────
    # Total units per calendar month across every class, used only to judge completeness.
    tot_by_month = collections.Counter()
    for ym, _cls, _b, _mo, _j, n in rows:
        tot_by_month[ym] += n
    ref = _median([tot_by_month[m] for m in all_months[-13:-1]] or
                  [tot_by_month[m] for m in all_months])
    incomplete = [m for m in all_months if ref and tot_by_month[m] < STUB_FRACTION * ref]
    months = [m for m in all_months if m not in incomplete]
    if not months:
        return None
    latest = months[-1]

    # Calendar gaps: months absent from the mirror entirely. A window is counted in PRESENT months,
    # so a hole must be declared rather than quietly closing up.
    span, cur = [], all_months[0]
    while cur <= all_months[-1]:
        span.append(cur)
        cur = _ym_add(cur, 1)
    missing = [m for m in span if m not in set(all_months)]

    # ── monthly totals on the AutoX basis ────────────────────────────────────────────────────
    # by_month[ym]['pu'|'pa'] = units, restricted to the collateral classes. Motorcycles and the rest
    # are counted separately so nothing is silently dropped.
    by_month = collections.defaultdict(lambda: collections.Counter())
    brand_month = collections.defaultdict(lambda: collections.Counter())   # (basis, ym) -> brand
    plate_month = collections.defaultdict(lambda: collections.Counter())   # (kind, ym) -> plate
    cls_units = collections.Counter()
    cls_split = collections.defaultdict(lambda: collections.Counter())     # cls -> kind

    for ym, cls, brand, _model, joined, n in rows:
        cls_units[cls] += n
        kind, plate = kind_of(joined)
        cls_split[cls][kind] += n
        if cls not in COLLATERAL_CLASSES:
            continue
        basis = "pu" if kind in ("pickup", "ppv") else "pa"
        by_month[ym][basis] += n
        brand_month[(basis, ym)][brand] += n
        if plate:
            plate_month[(kind, ym)][plate] += n

    # ── window aggregates ────────────────────────────────────────────────────────────────────
    def window_months(k):
        return months[-k:] if len(months) >= k else months

    present = set(months)

    windows = {}
    for k in WINDOWS:
        wm = window_months(k)
        # The comparison window is the SAME CALENDAR MONTHS one year earlier, not the k months
        # immediately before. Thai registrations are strongly seasonal — January runs far above a
        # normal month every year — so comparing Sep-Feb against Mar-Aug would price a season as a
        # trend. For k=12 and k=24 the two definitions coincide; for k=6 they do not, and the naive
        # version made the pickup class look 26% worse than it is.
        prev = [_ym_add(m, -12) for m in wm]
        prev = [m for m in prev if m in present]
        blk = {"months": len(wm), "from": wm[0], "to": wm[-1],
               "complete": len(months) >= k, "prior_complete": len(prev) == k,
               "prior_from": prev[0] if prev else None, "prior_to": prev[-1] if prev else None,
               "prior_basis": "same calendar months, 12 months earlier (seasonally aligned)",
               "contains_flagged_months": []}
        for basis, majors in (("pu", MAJOR_PU), ("pa", MAJOR_PA)):
            cur = collections.Counter()
            for ym in wm:
                cur.update(brand_month[(basis, ym)])
            tot = sum(cur.values())
            maj = sum(cur.get(b, 0) for b in majors)
            ent = {
                "units": tot,
                "major_units": maj,
                "minor_units": tot - maj,
                "major_share_pct": round(100.0 * maj / tot, 2) if tot else None,
                "majors": list(majors),
                "top_brands": [{"brand": b, "units": v,
                                "share_pct": round(100.0 * v / tot, 2) if tot else None}
                               for b, v in cur.most_common(12)],
            }
            # Same window one YEAR earlier, so "resilience" is a change and not a level.
            if len(prev) == k:
                p = collections.Counter()
                for ym in prev:
                    p.update(brand_month[(basis, ym)])
                ptot = sum(p.values())
                pmaj = sum(p.get(b, 0) for b in majors)
                ent["prior_units"] = ptot
                ent["prior_major_share_pct"] = round(100.0 * pmaj / ptot, 2) if ptot else None
                ent["units_change_pct"] = (round(100.0 * (tot - ptot) / ptot, 2)
                                           if ptot else None)
                ent["major_share_change_pp"] = (
                    round(100.0 * maj / tot - 100.0 * pmaj / ptot, 2) if tot and ptot else None)
            # Monthly path inside the window + its slope: a flat 6 inside a falling 12 is the turn.
            path = [by_month[ym][basis] for ym in wm]
            ent["monthly"] = path
            ent["slope_units_per_month"] = _slope(path)
            maj_share_path = []
            for ym in wm:
                bm = brand_month[(basis, ym)]
                t = sum(bm.values())
                maj_share_path.append(round(100.0 * sum(bm.get(b, 0) for b in majors) / t, 2)
                                      if t else None)
            ent["major_share_monthly"] = maj_share_path
            clean = [v for v in maj_share_path if v is not None]
            ent["major_share_slope_pp_per_month"] = (
                round(_slope(clean) / 1.0, 3) if _slope(clean) is not None else None)
            blk[basis] = ent
        windows["m%d" % k] = blk

    # ── months that need a caveat rather than a deletion ─────────────────────────────────────
    # A month whose YoY move is extreme in ONE class while the others are normal is a pull-forward,
    # not demand. Jan-2026 is the live example: cars +54% YoY while motorcycles were flat, ahead of
    # an incentive deadline. Flagged, never dropped — dropping it would be editing the market.
    flagged = []
    for ym in months:
        prior = _ym_add(ym, -12)
        if prior not in present:
            continue
        for basis in ("pu", "pa"):
            a, b = by_month[ym][basis], by_month[prior][basis]
            if b and abs(a - b) / float(b) > OUTLIER_YOY:
                flagged.append({"ym": ym, "basis": basis, "units": a, "prior_units": b,
                                "yoy_pct": round(100.0 * (a - b) / b, 1)})
    flagged_months = sorted({f["ym"] for f in flagged})
    for k in WINDOWS:
        wkey = "m%d" % k
        wm = window_months(k)
        windows[wkey]["contains_flagged_months"] = [m for m in flagged_months if m in set(wm)]

    # ── nameplate leaderboards over the last 12 months ───────────────────────────────────────
    last12 = window_months(12)
    plates = {}
    for kind in ("pickup", "ppv"):
        c = collections.Counter()
        for ym in last12:
            c.update(plate_month[(kind, ym)])
        tot = sum(c.values())
        plates[kind] = {
            "units": tot,
            "top": [{"plate": p, "units": v,
                     "share_pct": round(100.0 * v / tot, 2) if tot else None}
                    for p, v in c.most_common(15)],
        }

    # ── the class-vs-nameplate reconciliation, the reason this layer exists ──────────────────
    recon = {}
    for cls in (CLS_CAR, CLS_TRUCK):
        tot = cls_units[cls]
        s = cls_split[cls]
        recon[cls] = {
            "units": tot,
            "pickup_plate_units": s["pickup"],
            "ppv_plate_units": s["ppv"],
            "car_units": s["car"],
            "pickup_plate_pct": round(100.0 * s["pickup"] / tot, 2) if tot else None,
            "ppv_plate_pct": round(100.0 * s["ppv"] / tot, 2) if tot else None,
            "autox_pu_pct": round(100.0 * (s["pickup"] + s["ppv"]) / tot, 2) if tot else None,
        }

    monthly = [{"ym": ym, "pu": by_month[ym]["pu"], "pa": by_month[ym]["pa"]} for ym in months]

    # ── the year table, and it has to ADD UP ─────────────────────────────────────────────────
    # "Pickup + passenger car" is nowhere near all new registrations, and the old table showed the
    # three numbers side by side with no way to see why. Every class is now accounted for, and the
    # residual is named rather than left as a silent 2.1M gap. The motorcycle line is most of it.
    MOTO = ("รถจักรยานยนต์", "รถจักรยานยนต์สาธารณะ")
    TRACTOR = ("รถแทร็กเตอร์", "รถใช้ในงานเกษตรกรรม")
    annual_raw = _read_annual()
    annual = []
    for y in sorted(annual_raw):
        c = annual_raw[y]
        cls_units_y = {k[len("__cls__"):]: v for k, v in c.items() if k.startswith("__cls__")}
        moto = sum(v for k, v in cls_units_y.items() if k in MOTO)
        trac = sum(v for k, v in cls_units_y.items() if k in TRACTOR)
        pu, pa, tot = c["pu"], c["pa"], c["total"]
        other = tot - pu - pa - moto - trac
        annual.append({
            "year_ce": y, "year_be": y + 543,
            "pu": pu, "pu_pickup": c["pu_pickup"], "pu_ppv": c["pu_ppv"],
            "pa": pa, "motorcycle": moto, "tractor": trac, "other": other, "total": tot,
            # An explicit reconciliation flag beats trusting the reader to add five numbers.
            "reconciles": (pu + pa + moto + trac + other) == tot,
            "pu_pct": round(100.0 * pu / tot, 2) if tot else None,
            "pa_pct": round(100.0 * pa / tot, 2) if tot else None,
            "motorcycle_pct": round(100.0 * moto / tot, 2) if tot else None,
            "other_classes": {k: v for k, v in sorted(cls_units_y.items())
                              if k not in MOTO and k not in TRACTOR
                              and k not in COLLATERAL_CLASSES},
        })

    return {
        "meta": {
            "title": "New vehicle registrations by nameplate — on AutoX's pickup definition",
            "generated_by": "pipeline/build_vehicle_models.py",
            "label": "MEASURED — Department of Land Transport first-registration counts at "
                     "brand/model grain. NATIONAL only (this series carries no province column). "
                     "The PICKUP/PA split is AutoX's, not the registrar's: we classify on the "
                     "NAMEPLATE, so a double-cab D-Max filed under 'passenger car' counts as a "
                     "pickup, and PPVs count as pickups too.",
            "source": "gdcatalog.dlt.go.th — สถิติจำนวนรถจดทะเบียนครั้งแรก ตามกฎหมายว่าด้วยรถยนต์ "
                      "(จำแนกตามยี่ห้อและรุ่น)",
            "what_this_is_not": "These are FIRST registrations — the collateral pool we will be "
                                "seizing and reselling in future years, NOT our current book and "
                                "NOT used-vehicle sales.",
            "first_month": months[0],
            "latest_month": latest,
            "n_months": len(months),
            # Everything the reader needs to distrust the right parts of this layer.
            "incomplete_months_excluded": incomplete,
            "incomplete_rule": "a month holding <%d%% of the median month is a catalog stub, not a "
                               "month, and is excluded from every series and window"
                               % int(STUB_FRACTION * 100),
            "missing_months": missing,
            "flagged_months": flagged,
            "flagged_rule": "a month moving more than %d%% year-on-year in one class is flagged, "
                            "never dropped — Jan-2026 ran +54%% in cars while motorcycles were flat, "
                            "which is registrations pulled forward ahead of an incentive deadline"
                            % int(OUTLIER_YOY * 100),
            "brand_alias": BRAND_ALIAS,
            "autox_rule": "PU = any pickup nameplate + any PPV nameplate, in any registration "
                          "class. PA = everything else in the personal passenger classes.",
            "pickup_plates": PICKUP_PLATES,
            "ppv_plates": PPV_PLATES,
            "major_pu": list(MAJOR_PU),
            "major_pa": list(MAJOR_PA),
            "major_basis": "Fixed brand lists, not top-N by volume: a top-N rule would reclassify a "
                           "brand mid-series and make the resilience trend meaningless.",
            "class_reconciliation": recon,
            "classes_excluded": {c: n for c, n in sorted(cls_units.items())
                                 if c not in COLLATERAL_CLASSES},
        },
        "monthly": monthly,
        "annual": annual,
        "windows": windows,
        "plates_last12": plates,
    }


def _dump(doc):
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(SRC) or not glob.glob(os.path.join(SRC, "*.csv")):
        print("[SKIP] build_vehicle_models.py — DLT model-grain mirror absent "
              "(%s) — gitignored raw pull, not data drift" % os.path.relpath(SRC, ROOT))
        sys.exit(3)

    doc = build()
    if doc is None:
        print("[SKIP] build_vehicle_models.py — mirror present but no parseable rows")
        sys.exit(3)
    payload = _dump(doc)

    if args.check:
        if not os.path.exists(OUT):
            # SKIP, not DRIFT — matching build_brand_trends.py. "The output has never been built"
            # is not the same claim as "the committed output disagrees with its input", and the
            # gate reports them differently. Only the second one is a data-integrity failure.
            print("[SKIP] build_vehicle_models.py — platform/data/vehicle_models.json not built yet; "
                  "run without --check to generate it")
            sys.exit(3)
        with io.open(OUT, encoding="utf-8") as fh:
            if fh.read() != payload:
                print("DRIFT: platform/data/vehicle_models.json differs from a fresh build")
                sys.exit(1)
        print("OK: vehicle_models.json reproduces (%d months, %s .. %s)"
              % (doc["meta"]["n_months"], doc["meta"]["first_month"], doc["meta"]["latest_month"]))
        return

    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(payload)
    m12 = doc["windows"]["m12"]
    print("wrote %s — %d months (%s .. %s)"
          % (os.path.relpath(OUT, ROOT), doc["meta"]["n_months"],
             doc["meta"]["first_month"], doc["meta"]["latest_month"]))
    print("  last 12m  PU %s units, major (%s) %.1f%%   |   PA %s units, major (%s) %.1f%%"
          % (format(m12["pu"]["units"], ","), "+".join(MAJOR_PU), m12["pu"]["major_share_pct"],
             format(m12["pa"]["units"], ","), "+".join(MAJOR_PA), m12["pa"]["major_share_pct"]))


if __name__ == "__main__":
    main()
