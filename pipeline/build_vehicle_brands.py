#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_vehicle_brands.py — VEHICLE BRAND x PROVINCE (owner directive: "i want brand x province.
extrapolate if need be"). DLT does not publish brand x province anywhere in its public catalog
(14 packages mirrored under source-data/dlt/raw/, none pairs yี่ห้อ with จังหวัด) — this is a
deliberate, explicitly-authorised EXTRAPOLATION, honestly labelled ESTIMATED end to end.

  in : source-data/dlt/raw/stat_1_1_01_first_regis_vehicles_car/  (NATIONAL first registrations,
       brand + model, monthly CSVs — no province column)
       source-data/dlt/raw/dataset_stat_1_008/  (PROVINCE x vehicle-type new registrations, monthly
       CSVs, MEASURED — the correct join partner: same basis, first/new registrations)
       source-data/dlt/raw/dataset_1_1_04/  (PROVINCE x vehicle-type x FUEL, MEASURED accumulated
       stock, one snapshot — supplies the battery-electric correction)
  out: platform/data/vehicle_brands.json

Deterministic + network-free over the raw mirror on disk. These three input folders are the
OWNER-SIDE gitignored DLT mirror (source-data/dlt/raw/, same as ingest_dlt_mix.py's inputs), so
neither they nor this script's output are in the repo's commit history — `--check` verifies this
run reproduces the CURRENTLY WRITTEN platform/data/vehicle_brands.json byte-for-byte from whatever
raw mirror happens to be on disk right now, same convention as ingest_dlt_mix.py. Exits 3 (SKIP,
not drift) when any raw folder is absent or the two monthly releases share fewer than 12 common
months.

TYPE SCOPE — deliberately the "automobile" Motor Vehicle Act classes only (รย. 1,2,3,4,6,7,8,9,
10,11,18 — car / van / pickup / three-wheeler / taxi / business-tour-rental service / e-hailing).
Motorcycle (รย.12/17), tractor (รย.13), road roller (รย.14), agri machinery (รย.15) and trailer
(รย.16) are EXCLUDED: they are not the collateral class this build serves (AutoX's title-loan book
is cars/pickups), dataset_1_1_04's fuel classification for that country is largely irrelevant to
the BEV question this build answers, and a defensible brand classification for the ~120-brand
Chinese e-scooter long tail is a distinct, much larger research task. See meta.limitation.

METHOD (must match exactly — see the two-tier spec this was commissioned against):
  Tier 1 (MEASURED) — province x type, new registrations (รถจดใหม่ป้ายแดง), trailing 12 months,
    straight from dataset_stat_1_008. This is the honest floor; every other number is built to
    reproduce this exactly when summed back up (the "measured-marginal guarantee").
  Tier 2 (ESTIMATED) — est(province,type,brand) = measured_new(province,type) x
    national_share(brand|type), where national_share is computed from stat_1_1_01 over the SAME
    trailing-12-month window (the newest 12 months common to BOTH monthly releases).
  Tier 2b (the measured correction) — a flat national spread is known to be wrong in one
    quantifiable direction: BEV brands concentrate in Bangkok / the eastern corridor. Corrected
    using dataset_1_1_04 (MEASURED stock, one snapshot):
      bev_share(geo,type)  = count of exact fuel "ไฟฟ้า" / stock total, for that geo x type
                              (ONLY exact "ไฟฟ้า" counts as battery-electric — NOT any of the
                              hybrid/plug-in-hybrid fuel strings the raw file also carries; see
                              meta.fuel_values_seen for the full distinct list found and how each
                              was bucketed).
      ratio_p(province,type) = bev_share(province,type) / bev_share(national,type), clipped to
                              [0, 5] and requiring >=30 vehicles of that type in the province's
                              stock before applying any correction at all (else ratio_p = 1.0, i.e.
                              no correction) — a small-sample guard against a single stray EV
                              registration producing a 100x multiplier in a thin-stock province.
      weight(brand) = ratio_p                          if brand is BEV-ONLY
                     = 1 + (ratio_p - 1) * 0.5          if brand is MIXED
                     = 1.0                              if brand is NON-BEV
      est_count(province,type,brand) = measured_new(province,type)
                                        * (national_share(brand|type) * weight(brand))
                                        / sum_over_brands(national_share * weight)
    This renormalisation makes sum_brand(est_count) == measured_new(province,type) EXACTLY (to
    floating-point epsilon) by construction — Tier 1 is never violated; only its INTERNAL split
    across brands is estimated.

    python3 build_vehicle_brands.py
    python3 build_vehicle_brands.py --check
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPE)
from lib.regionmap import canonical, REGION  # noqa: E402

RAW = os.path.join(ROOT, "source-data", "dlt", "raw")
DIR_BRAND = os.path.join(RAW, "stat_1_1_01_first_regis_vehicles_car")   # national, brand+model
DIR_FLOW = os.path.join(RAW, "dataset_stat_1_008")                      # province x type, new regs
DIR_STOCK = os.path.join(RAW, "dataset_1_1_04")                         # province x type x fuel, stock
OUT = os.path.join(ROOT, "platform", "data", "vehicle_brands.json")

WINDOW = 12          # trailing months for both the province flow and the national brand shares
MIN_STOCK_FOR_RATIO = 30   # vehicles of that type in a province's stock before ratio_p is trusted
RATIO_CLIP = 5.0     # ratio_p ceiling — guards a thin-stock province against a spurious multiplier
TOP_N_PROVINCE_BRANDS = 15  # province x type brand lists are capped for size/noise; national is not

THAI_MONTHS = {"มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5,
               "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10,
               "พฤศจิกายน": 11, "ธันวาคม": 12}
MONTH_TAIL_RE = re.compile(r"(" + "|".join(THAI_MONTHS.keys()) + r")_(\d{4})$")
MVA_RE = re.compile(r"รย\.\s*(\d+)")
# Model-name signal for "this specific (brand,type) has an electrified variant registered" — see
# the MIXED-brand type-gate in build(): a brand named MIXED (e.g. TOYOTA, which sells hybrid cars)
# does not automatically get the BEV correction on a type where it demonstrably sells none (e.g.
# TOYOTA's pickup line — HILUX REVO/CHAMP — is 100% diesel in this data, zero hybrid/EV trims).
EV_SIGNAL_RE = re.compile(r"\b(EV|BEV|PHEV|E-?TRON|E-?HEV|HYBRID)\b", re.I)

# The "automobile" MVA classes this build covers — see module docstring TYPE SCOPE.
CAR_SCOPE = {"ry1", "ry2", "ry3", "ry4", "ry6", "ry7", "ry8", "ry9", "ry10", "ry11", "ry18"}
TYPE_LABELS_EN = {
    "ry1": "Cars <=7 seats", "ry2": "Cars/vans >7 seats", "ry3": "Pickups (personal)",
    "ry4": "Three-wheelers (personal)", "ry6": "Taxis <=7 seats", "ry7": "Small 4-wheel taxis",
    "ry8": "Three-wheel taxis / tuk-tuks", "ry9": "Business-service cars",
    "ry10": "Tour-service cars", "ry11": "Rental cars", "ry18": "E-hailing cars",
}

# ── BEV classification (audited, correctable — see meta.bev_classification for what actually
#    shipped) ─────────────────────────────────────────────────────────────────────────────────
# BEV-ONLY: brand's entire registered lineup in this data is battery-electric — no ICE variant.
BEV_ONLY_BRANDS = {
    "BYD", "NETA", "ORA", "AION", "DEEPAL", "TESLA", "ZEEKR", "XPENG", "VOLT", "MINE",
    "MINE MOBILITY", "ETRAN", "HIGER", "KEYTON", "LEAPMOTOR", "OMODA", "FOMM", "KYBURZ",
    "RIDDARA", "SERES", "SRM", "SKYWELL", "STELATO", "SMART", "XEV", "XIAOMI", "E-TUK", "EVT",
    "FARIZON", "AVATR", "LUMIN", "AIWAYS",
}
# MIXED: brand sells both BEV/PHEV/hybrid AND plain-ICE models in this data.
MIXED_BRANDS = {
    "MG", "TOYOTA", "HONDA", "BMW", "MERCEDES BENZ", "MERCEDES", "MERCEDES-AMG",
    "MERCEDESBENZ-MAYBACH", "BENZ", "VOLVO", "GWM", "HAVAL", "GWM TANK",
    "AUDI", "BENTLEY", "GAC", "GMC", "HYUNDAI", "JAECOO", "JEEP", "KIA", "LAND ROVER",
    "RANGE ROVER", "MASERATI", "MCLAREN", "POER", "PORSCHE", "VOLKSWAGEN", "WULING", "HONGQI",
    "MAXUS", "DENZA", "LOTUS", "LEVC", "MINI", "TKI",
}
# Everything else (ISUZU, MAZDA, NISSAN, MITSUBISHI, FORD, SUZUKI explicitly, plus the long tail
# of legacy/commercial/luxury-ICE marques) defaults to NON-BEV — see classify().


def classify(brand):
    b = (brand or "").strip().upper()
    if b in BEV_ONLY_BRANDS:
        return "bev_only"
    if b in MIXED_BRANDS:
        return "mixed"
    return "non_bev"


def _to_int(x):
    try:
        return int(float(str(x or 0).replace(",", "").strip() or 0))
    except Exception:
        return 0


def _be_to_ce(y):
    y = int(y)
    return y - 543 if y > 2400 else y


def classify_mva(label):
    m = MVA_RE.match((label or "").strip())
    return f"ry{m.group(1)}" if m else "other"


def _list_months(raw_dir):
    """Every monthly CSV in raw_dir with a "<ThaiMonth>_<BEyear>" tail, parsed to
    (year_ce, month_num, path), sorted ascending. Deliberately anchors at end-of-filename so it
    works for both the plain "..__<type>__<month>_<year>.csv" flow files AND the brand file's
    messier "..__<type>_-จำแนก..._<month>_<year>.csv" names; annual "..._ปี_<year>.csv" rollups
    (present alongside the monthly files in the brand folder) don't match and are skipped — using
    them would double-count against the monthly files."""
    out = []
    for path in glob.glob(os.path.join(raw_dir, "*.csv")):
        name = os.path.splitext(os.path.basename(path))[0]
        m = MONTH_TAIL_RE.search(name)
        if not m:
            continue
        out.append((_be_to_ce(m.group(2)), THAI_MONTHS[m.group(1)], path))
    out.sort()
    return out


def _rows(path):
    for enc in ("utf-8-sig", "cp874"):
        try:
            with open(path, encoding=enc) as f:
                yield from csv.DictReader(f)
            return
        except UnicodeDecodeError:
            continue


def build():
    if not os.path.isdir(DIR_BRAND) or not os.path.isdir(DIR_FLOW) or not os.path.isdir(DIR_STOCK):
        return None  # ABSENT — not data drift

    flow_months = _list_months(DIR_FLOW)
    brand_months = _list_months(DIR_BRAND)
    flow_set = set((y, m) for y, m, _ in flow_months)
    brand_set = set((y, m) for y, m, _ in brand_months)
    common = sorted(flow_set & brand_set)
    if len(common) < WINDOW:
        return None  # not enough overlapping months for a trailing-12 window — ABSENT
    window = set(common[-WINDOW:])
    flow_files = [p for y, m, p in flow_months if (y, m) in window]
    brand_files = [p for y, m, p in brand_months if (y, m) in window]

    # ---- Tier 1: MEASURED province x type new registrations (dataset_stat_1_008) --------------
    measured_new = defaultdict(lambda: defaultdict(int))   # province -> ry -> count
    dropped_flow_rows = 0
    dropped_flow_provs = set()
    for path in flow_files:
        for row in _rows(path):
            raw_p = (row.get("จังหวัด") or "").strip()
            p = canonical(raw_p)
            if p not in REGION:
                dropped_flow_rows += 1
                dropped_flow_provs.add(raw_p)
                continue
            ryid = classify_mva(row.get("ประเภทรถ"))
            if ryid not in CAR_SCOPE:
                continue
            measured_new[p][ryid] += _to_int(row.get("รถจดใหม่ป้ายแดง"))

    # ---- national brand shares, SAME trailing-12mo window (stat_1_1_01) ------------------------
    nat_brand_count = defaultdict(lambda: defaultdict(int))   # ry -> brand -> count
    nat_type_total = defaultdict(int)                          # ry -> total count
    # per (ry,brand): does ANY registered model in this window show an EV/hybrid signal word?
    # (see EV_SIGNAL_RE) — the empirical gate that stops a MIXED brand's correction from bleeding
    # from one type (e.g. a hybrid car) into another type of the same brand with no electrified
    # variant at all (e.g. that brand's 100%-diesel pickup line).
    electrified_seen = defaultdict(lambda: defaultdict(bool))  # ry -> brand -> bool
    for path in brand_files:
        for row in _rows(path):
            t = (row.get("ประเภทรถ") or "").strip()
            # brand file's ประเภทรถ has no "รย. N" prefix — match by bare label text.
            ryid = RY_BY_LABEL.get(t)
            if ryid not in CAR_SCOPE:
                continue
            brand = (row.get("ยี่ห้อ") or "").strip()
            n = _to_int(row.get("จำนวน"))
            nat_brand_count[ryid][brand] += n
            nat_type_total[ryid] += n
            model = (row.get("รุ่น") or "").strip()
            if not electrified_seen[ryid][brand] and (EV_SIGNAL_RE.search(model) or "ไฟฟ้า" in model):
                electrified_seen[ryid][brand] = True

    # ---- BEV stock correction (dataset_1_1_04, single snapshot) --------------------------------
    stock_files = glob.glob(os.path.join(DIR_STOCK, "*.csv"))
    if len(stock_files) != 1:
        return None  # expected exactly one cumulative-stock snapshot file
    stock_total = defaultdict(lambda: defaultdict(int))   # province -> ry -> count
    stock_bev = defaultdict(lambda: defaultdict(int))     # province -> ry -> exact-"ไฟฟ้า" count
    nat_stock_total = defaultdict(int)
    nat_stock_bev = defaultdict(int)
    fuel_values_seen = defaultdict(int)
    dropped_stock_rows = 0
    dropped_stock_provs = set()
    for row in _rows(stock_files[0]):
        raw_p = (row.get("จังหวัด") or "").strip()
        p = canonical(raw_p)
        if p not in REGION:
            dropped_stock_rows += 1
            dropped_stock_provs.add(raw_p)
            continue
        ryid = classify_mva(row.get("ประเภทรถ"))
        if ryid not in CAR_SCOPE:
            continue
        fuel = (row.get("ประเภทเชื้อเพลิง") or "").strip()
        n = _to_int(row.get("จำนวนรถ"))
        fuel_values_seen[fuel] += n
        is_bev = (fuel == "ไฟฟ้า")
        stock_total[p][ryid] += n
        nat_stock_total[ryid] += n
        if is_bev:
            stock_bev[p][ryid] += n
            nat_stock_bev[ryid] += n

    def ratio_p(prov, ryid):
        pt = stock_total.get(prov, {}).get(ryid, 0)
        nt = nat_stock_total.get(ryid, 0)
        nb = nat_stock_bev.get(ryid, 0)
        if pt < MIN_STOCK_FOR_RATIO or nt == 0 or nb == 0:
            return 1.0
        pb = stock_bev.get(prov, {}).get(ryid, 0)
        bev_share_prov = pb / pt
        bev_share_nat = nb / nt
        r = bev_share_prov / bev_share_nat
        return max(0.0, min(RATIO_CLIP, r))

    # ---- assemble national by_type -------------------------------------------------------------
    national_by_type = {}
    for ryid in sorted(CAR_SCOPE, key=lambda r: int(r[2:])):
        total = nat_type_total.get(ryid, 0)
        brands = []
        for brand, count in sorted(nat_brand_count.get(ryid, {}).items(), key=lambda kv: -kv[1]):
            if count <= 0:
                continue
            brands.append({"brand": brand, "count": count,
                            "share_pct": round(count / total * 100.0, 2) if total else None})
        national_by_type[ryid] = {"brands": brands, "total": total}

    # ---- assemble provinces ----------------------------------------------------------------------
    provinces_out = {}
    for p in sorted(REGION):
        block = {}
        for ryid in sorted(CAR_SCOPE, key=lambda r: int(r[2:])):
            m_total = measured_new.get(p, {}).get(ryid, 0)
            nat_brands = [(b, c) for b, c in nat_brand_count.get(ryid, {}).items() if c > 0]
            if m_total <= 0 or not nat_brands or nat_type_total.get(ryid, 0) <= 0:
                block[ryid] = {"measured_total": m_total, "brands": []}
                continue
            r = ratio_p(p, ryid)
            weights = {}
            for brand, nat_count in nat_brands:
                share = nat_count / nat_type_total[ryid]
                cls = classify(brand)
                if cls == "bev_only":
                    w = r
                elif cls == "mixed" and electrified_seen[ryid][brand]:
                    # MIXED only counts FOR THIS TYPE if this brand actually registered an
                    # electrified model under it — stops e.g. TOYOTA's hybrid-car classification
                    # from correcting its 100%-diesel pickup line (see electrified_seen above).
                    w = 1.0 + (r - 1.0) * 0.5
                else:
                    w = 1.0
                weights[brand] = share * w
            total_w = sum(weights.values())
            rows_out = []
            if total_w > 0:
                for brand, w in weights.items():
                    est_raw = m_total * w / total_w
                    rows_out.append((brand, est_raw))
                # measured-marginal guarantee: the unrounded split must sum back to m_total exactly
                assert abs(sum(v for _, v in rows_out) - m_total) < 1e-6, \
                    f"Tier-1 marginal violated at {p}/{ryid}"
                rows_out.sort(key=lambda kv: -kv[1])
                rows_out = rows_out[:TOP_N_PROVINCE_BRANDS]
            brands_out = [{"brand": b, "est_count": round(v, 2),
                            "est_share_pct": round(v / m_total * 100.0, 2)} for b, v in rows_out]
            block[ryid] = {"measured_total": m_total, "brands": brands_out}
        provinces_out[p] = block

    all_brands_present = set()
    for ryid, blk in national_by_type.items():
        for b in blk["brands"]:
            all_brands_present.add(b["brand"])
    bev_classification = {b: classify(b) for b in sorted(all_brands_present)}
    # every (type,brand) pair where the brand is MIXED at brand level but the type-gate demoted it
    # to NON-BEV for this type specifically (no electrified model registered under it) — see method.
    mixed_type_gate_off = sorted(
        f"{ryid}:{brand}"
        for ryid in CAR_SCOPE
        for brand in nat_brand_count.get(ryid, {})
        if classify(brand) == "mixed" and not electrified_seen[ryid][brand]
    )

    lo = f"{common[-WINDOW][0]:04d}-{common[-WINDOW][1]:02d}"
    hi = f"{common[-1][0]:04d}-{common[-1][1]:02d}"

    return {
        "meta": {
            "title": "Vehicle brand x province (ESTIMATED — extrapolated; DLT does not publish "
                      "brand x province anywhere in its public catalog)",
            "generated_by": "pipeline/build_vehicle_brands.py",
            "provenance": "ESTIMATED",
            "label": "ESTIMATED. Tier 1 (measured_total, per province x type) is MEASURED straight "
                      "from DLT dataset_stat_1_008 and is never modelled. Every brand split under it "
                      "is an EXTRAPOLATION: national brand shares (from stat_1_1_01, the only DLT "
                      "release that carries a brand column at all — it has no province field) are "
                      "allocated onto each province's measured total, corrected by a MEASURED "
                      "battery-electric concentration ratio computed from dataset_1_1_04's stock x "
                      "fuel-type breakdown. No sub-national brand data was pulled from anywhere else.",
            "method": "est(province,type,brand) = measured_new(province,type) x "
                      "[national_share(brand|type) x weight(brand,type)] / sum_over_brands(same), "
                      "where weight = ratio_p for BEV-ONLY brands, 1 + (ratio_p - 1) x 0.5 for MIXED "
                      "brands IF that brand registered an electrified (EV/BEV/PHEV/hybrid) model "
                      "under THIS SPECIFIC type in the window (else 1.0 — see the type-gate below), "
                      "and 1.0 for NON-BEV brands always. ratio_p(province,type) = "
                      "bev_share(province,type) / bev_share(national,type), bev_share computed "
                      "against dataset_1_1_04's cumulative stock using ONLY the exact fuel string "
                      "'ไฟฟ้า' as battery-electric (hybrid / plug-in-hybrid fuel strings are excluded "
                      "— see fuel_values_seen). ratio_p is clipped to [0, 5] and requires >= "
                      f"{MIN_STOCK_FOR_RATIO} vehicles of that type in the province's stock before any "
                      "correction is applied (else ratio_p = 1.0) — guards a thin-stock province "
                      "against a single stray EV registration producing an extreme multiplier. The "
                      "renormalisation by total_w makes sum_brand(est_count) reproduce "
                      "measured_total to floating-point epsilon by construction (asserted at build "
                      "time) — Tier 1 is never violated, only its internal brand split is estimated. "
                      "MIXED type-gate: a brand is classified BEV-ONLY/MIXED/NON-BEV at the BRAND "
                      "level (see bev_classification), but a MIXED brand only receives the MIXED "
                      "weight on a (province,type) cell if that brand's registrations under THAT "
                      "TYPE, nationally, actually include an electrified model name (EV_SIGNAL_RE: "
                      "EV/BEV/PHEV/HYBRID/e-tron/e-hev, or the Thai string ไฟฟ้า) — otherwise it is "
                      "treated as NON-BEV for that type only. This was added after finding TOYOTA "
                      "(brand-level MIXED, from its hybrid car lineup) was picking up a large, "
                      "spurious BEV correction on its pickup line even though every registered "
                      "TOYOTA pickup model in this window (HILUX REVO, HILUX CHAMP, ...) is plain "
                      "diesel with zero hybrid/EV trims — see mixed_type_gate_off for the full list "
                      "of (type,brand) pairs this gate demoted. BEV-ONLY brands are NOT type-gated "
                      "(by definition they have no ICE variant of anything, so there is no bleed "
                      "risk); NON-BEV brands were never getting a correction to begin with.",
            "measured_marginal_guarantee": "For every (province, type), sum(brands[].est_count) == "
                      "measured_total exactly (to floating-point epsilon; verified by an assertion "
                      "at build time) — the estimate can redistribute a province's measured "
                      "registrations across brands, it can never inflate or shrink the total.",
            "type_scope": "MVA 'automobile' classes only: car <=7 seats, car/van >7 seats, pickup, "
                      "three-wheeler, taxi <=7, small 4-wheel taxi, three-wheel taxi, business/tour/"
                      "rental service car, e-hailing car (รย. 1,2,3,4,6,7,8,9,10,11,18). Motorcycle "
                      "(รย.12/17), tractor (รย.13), road roller (รย.14), agri machinery (รย.15) and "
                      "trailer (รย.16) are OUT OF SCOPE — see limitation.",
            "bev_classification_method": "Empirical where possible (model-name scan for EV/BEV/"
                      "PHEV/HYBRID/e-tron/e-hev signal words across every brand's registered model "
                      "list in this window) plus well-known 2024-2026 Thailand-market fact for "
                      "brands the scan couldn't resolve (mostly single-digit-registration luxury/"
                      "commercial marques). BEV-ONLY = every registered model for that brand in "
                      "this data is battery-electric, no ICE variant found. MIXED = the brand's "
                      "registered lineup includes both electrified (BEV/PHEV/hybrid) and plain-ICE "
                      "models. NON-BEV = default for everything else, including the six brands "
                      "specified as NON-BEV (ISUZU, MAZDA, NISSAN, MITSUBISHI, FORD, SUZUKI) even "
                      "where a single grey-import hybrid model exists in their Thai lineup (e.g. "
                      "Nissan Serena Hybrid, Suzuki Hustler Hybrid — low-volume JDM grey imports).",
            "bev_classification": bev_classification,
            "mixed_type_gate_off": mixed_type_gate_off,
            "fuel_values_seen": dict(sorted(fuel_values_seen.items(), key=lambda kv: -kv[1])),
            "limitation": "This is a two-hop extrapolation (national brand mix x province volume x "
                      "a measured BEV-concentration correction), NOT a province-level brand census — "
                      "DLT has never published one and this cannot substitute for a real one; do not "
                      "read any single province x brand cell as a measured count, and do not use this "
                      "for anything finer than a directional read (e.g. 'is Isuzu likely dominant in "
                      "pickups in Chiang Mai'). Motorcycles, tractors, construction equipment and "
                      "trailers are entirely excluded (see type_scope) — this file says nothing about "
                      "those classes. Non-BEV/BEV/MIXED classification for very-low-volume luxury and "
                      "commercial marques (typically 1-5 national registrations in the window) is "
                      "lower-confidence than for the volume brands; because their counts are tiny "
                      "this barely moves any total, but treat those specific cells as the least "
                      "reliable in the file. The MIXED type-gate (mixed_type_gate_off) is keyword-"
                      "based and only catches model names that literally spell out EV/BEV/PHEV/"
                      "HYBRID/e-tron/e-hev/ไฟฟ้า; it MISSES brand-specific EV naming that doesn't "
                      "(e.g. BMW's 'i'/'e' prefixes, Mercedes' 'EQ' prefix, VW's 'ID.' prefix, "
                      "Volvo's 'Recharge' suffix), so some genuinely-electrified (province,type) "
                      "cells for those brands were conservatively demoted to a flat NON-BEV weight "
                      "instead of getting the MIXED correction they arguably deserve — see e.g. "
                      "ry1:BMW in mixed_type_gate_off. This makes the BEV correction UNDER-state "
                      "rather than OVER-state concentration for those specific brand x type cells, "
                      "which is the safer failure direction given this whole layer is ESTIMATED, but "
                      "it means BMW/Mercedes/VW/Volvo's true Bangkok EV concentration is likely "
                      "somewhat higher than what this file shows.",
            "new_window_months": [f"{y:04d}-{m:02d}" for y, m in sorted(window)],
            "new_window_label": f"{lo} -> {hi}",
            "min_stock_for_ratio": MIN_STOCK_FOR_RATIO,
            "ratio_clip": RATIO_CLIP,
            "top_n_province_brands": TOP_N_PROVINCE_BRANDS,
            "type_labels_en": TYPE_LABELS_EN,
            "n_provinces": len(provinces_out),
            "n_types": len(CAR_SCOPE),
            "n_brands_national": len(all_brands_present),
            "n_dropped_flow_rows": dropped_flow_rows,
            "dropped_flow_provinces": sorted(dropped_flow_provs),
            "n_dropped_stock_rows": dropped_stock_rows,
            "dropped_stock_provinces": sorted(dropped_stock_provs),
        },
        "national": {"by_type": national_by_type},
        "provinces": provinces_out,
    }


# Bare MVA-class label (no "รย. N " prefix) -> ry id, as used by the brand file's ประเภทรถ column.
# Built once at import time from a fixed, hand-verified mapping (both files were inspected directly
# — see the module docstring) rather than re-derived from a flow-file read on every build() call.
RY_BY_LABEL = {
    "รถยนต์นั่งส่วนบุคคลไม่เกิน 7 คน": "ry1",
    "รถยนต์นั่งส่วนบุคคลเกิน 7 คน": "ry2",
    "รถยนต์บรรทุกส่วนบุคคล": "ry3",
    "รถยนต์สามล้อส่วนบุคคล": "ry4",
    "รถยนต์รับจ้างระหว่างจังหวัด": "ry5",
    "รถยนต์รับจ้างบรรทุกคนโดยสารไม่เกิน 7 คน": "ry6",
    "รถยนต์สี่ล้อเล็กรับจ้าง (โดยสารไม่เกิน 7 คน)": "ry7",
    "รถยนต์รับจ้างสามล้อ": "ry8",
    "รถยนต์บริการธุรกิจ": "ry9",
    "รถยนต์บริการทัศนาจร": "ry10",
    "รถยนต์บริการให้เช่า": "ry11",
    "รถจักรยานยนต์": "ry12",
    "รถแทร็กเตอร์": "ry13",
    "รถบดถนน": "ry14",
    "รถใช้ในงานเกษตรกรรม": "ry15",
    "รถพ่วง": "ry16",
    "รถจักรยานยนต์สาธารณะ": "ry17",
    "รถยนต์รับจ้างผ่านระบบอิเล็กทรอนิกส์": "ry18",
}


def run(check=False):
    data = build()
    if data is None:
        print("SKIP: source-data/dlt/raw/{stat_1_1_01_first_regis_vehicles_car,dataset_stat_1_008,"
              "dataset_1_1_04}/ absent, or the brand + flow monthly releases share <12 common "
              "months — not data drift, re-pull the DLT mirror for a fresh window")
        return 3
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: platform/data/vehicle_brands.json")
            return 1
        print(f"OK: vehicle_brands.json reproduces byte-exact "
              f"({data['meta']['n_provinces']} provinces, {data['meta']['n_types']} types, "
              f"{data['meta']['n_brands_national']} brands)")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote platform/data/vehicle_brands.json "
          f"({data['meta']['n_provinces']} provinces, {data['meta']['n_types']} types, "
          f"{data['meta']['n_brands_national']} brands, window {data['meta']['new_window_label']})")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
