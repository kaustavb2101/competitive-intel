#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_dlt_mix.py — VEHICLE-MIX ingest (owner review points 11/12/18): what is the composition
of all new vehicle registrations, the full mix to 100% for every province, and does the truck /
bus fleet (Land Transport Act) show up alongside the car-law classes.

Streams the OWNER-SIDE raw DLT mirror (source-data/dlt/raw/ — gitignored, .gitignore:90) into a
small COMMITTED staging file of plain province-level COUNTS. Like ingest_real_tape.py this is NOT
in the determinism gate (its input is off-repo); the deterministic gated shaping (shares, region /
national rollups, the new-vs-stock gap) lives downstream in build_vehicle_mix.py.

Four raw inputs, two different DLT legal regimes, plus one nameplate-level overlay:
  dataset_1_1_04/*.csv       — cumulative registered STOCK, Motor Vehicle Act (รถยนต์) only, all
                                18 รย. classes, one snapshot file (as-of date parsed from its name).
                                There is NO stock file for Land-Transport-Act (truck/bus) vehicles
                                in this mirror — that gap is carried forward honestly (see below).
  dataset_stat_1_008/*.csv   — monthly registration-ACTIONS, Motor Vehicle Act (รถยนต์), one file
                                per month. รถจดใหม่ป้ายแดง (new red-plate) is the new-registration count.
  dataset_stat_1_009/*.csv   — the SAME shape, Land Transport Act (รถขนส่ง — trucks/buses). This is
                                the truck/bus data point 18 asks for; build_vehicle_flow.py (the
                                sibling flow script) only read dataset_stat_1_008 and logged this as
                                a follow-up — this ingest is that follow-up.
  stat_1_1_01_first_regis_vehicles_car/*.csv — monthly first-registration counts by ยี่ห้อ/รุ่น
                                (brand/model), NATIONAL ONLY (no จังหวัด column). Used only for the
                                PPV (pickup-based SUV) nameplate overlay below — owner's house rule
                                is "for autox, our PU (pickup) includes PPV in as well", and PPVs
                                (Fortuner, MU-X, Pajero Sport, Everest, Terra, GWM Tank 300/500, and
                                the not-yet-launched Land Cruiser FJ) register in รย.1
                                (≤7 seats), not รย.3, so they're invisible to the class-based mix
                                unless pulled out by nameplate at model grain.

Method:
  stock  — every dataset_1_1_04 row -> (province, MVA class, fuel bucket). Summed to per-province
           counts. Class id = "ry<N>" parsed from the "รย. N ..." label (robust to trailing-text
           drift across releases). Fuel bucket = ordered substring classifier (plug-in -> hybrid;
           benzin+electric or diesel+electric -> hybrid; exact "ไฟฟ้า" -> ev; any CNG/LPG/แก๊ส/LNG
           -> gas; "ดีเซล" -> diesel; "เบนซิน" -> petrol; else -> other). No Transport-Act stock
           exists in the mirror, so LTA classes carry NO stock entry — not a fabricated zero.
  new    — dataset_stat_1_008 (MVA) + dataset_stat_1_009 (LTA), TRAILING 12 MONTHS available in
           BOTH (they were pulled together and cover the identical 50-month span here; the
           intersection is taken defensively in case a future pull drifts), รถจดใหม่ป้ายแดง summed
           per province per class. LTA classes are matched by keyword (not exact string — the raw
           export has trailing-whitespace and an extra "รถขนาดเล็ก" class that only appears in some
           months) into 10 stable ids; anything that matches neither the MVA รย.-number pattern nor
           a known LTA keyword lands in a genuine "other" bucket, counted, never guessed away.
  ppv    — stat_1_1_01_first_regis_vehicles_car, TRAILING 12 MONTHS of its own (this series is not
           joined to the mva/lta window; it happens to land on the same span here). Every row's
           "<ยี่ห้อ> <รุ่น>" is uppercased and matched against PPV_NAMEPLATES with a word-boundary
           regex (a plain substring match on "TERRA" also catches Lamborghini "HURACAN STERRATO",
           which is present in this mirror — the boundary is load-bearing, not decorative). The
           boundary also guards against a DIGIT on either side, not just a letter — otherwise a
           plate like "TANK 300" would match inside a hypothetical "TANK 3000" (no such nameplate
           exists in this mirror today; checked empirically, see PPV_RE below). National total
           only; this series carries no จังหวัด column so there is no province split to make.

Thai Buddhist-era years fold to CE by -543 (only when > 2400, per convention). The trailing-12
anchor is the newest month IN THE DATA, never wall clock. Province strings are canonicalised via
lib.regionmap.canonical(); anything that does not resolve into REGION is dropped and counted.

Exits 3 (SKIP) if any of the four raw directories is absent, or the new-registration window has
fewer than 12 common months — not data drift, re-run pull_dlt_all.py for a fresh mirror.

    python3 ingest_dlt_mix.py
"""
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
DIR_STOCK = os.path.join(RAW, "dataset_1_1_04")
DIR_MVA_FLOW = os.path.join(RAW, "dataset_stat_1_008")
DIR_LTA_FLOW = os.path.join(RAW, "dataset_stat_1_009")
DIR_PPV = os.path.join(RAW, "stat_1_1_01_first_regis_vehicles_car")
OUT = os.path.join(ROOT, "source-data", "vehicle_mix_province.json")
WINDOW = 12  # trailing months for the new-registration mix

THAI_MONTHS = {"มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4, "พฤษภาคม": 5,
               "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8, "กันยายน": 9, "ตุลาคม": 10,
               "พฤศจิกายน": 11, "ธันวาคม": 12}
MVA_RE = re.compile(r"รย\.\s*(\d+)")
STOCK_NAME_RE = re.compile(r"ณ_วันที่_(\d+)_(\S+)_(\d+)")

# AutoX house definition: "for autox, our PU (pickup) includes PPV in as well." PPVs seat <=7 so
# they register in รย.1, not รย.3 — identified here by nameplate at model grain, national only
# (stat_1_1_01_first_regis_vehicles_car has no จังหวัด column). SW4 kept in the list for
# completeness even though it is not a Thailand-market badge (always 0 here).
# GWM TANK 300 counts as a PPV, not an SUV — it rides GWM's Pao/Cannon PICKUP ladder-frame platform
# (same body-on-frame architecture as Fortuner/MU-X/Everest above) and GWM launched it explicitly
# into the Thai PPV segment; it was the #3 PPV nameplate in 2025 (7,563 units, 17.2% of the PPV
# segment) — AHEAD of the Everest, which is already on this list. TANK 500 is the same platform
# family. Do not delete either thinking they are unrelated SUVs. LAND CRUISER FJ is added ahead of
# its Q2-2026 launch (confirmed on the same Hilux Champ IMV-0 ladder platform as the Champ pickup);
# it will match 0 until then and is kept so it is counted the moment it appears in the mirror.
PPV_NAMEPLATES = ["FORTUNER", "MU-X", "PAJERO SPORT", "EVEREST", "TERRA", "TRAILBLAZER", "SW4",
                  "TANK 300", "TANK 500", "LAND CRUISER FJ"]
# The word boundary is NOT optional — a plain substring match on "TERRA" also catches Lamborghini
# "HURACAN STERRATO" (present in this mirror). Anchor both sides to a non-letter AND non-digit: a
# few plates now contain a space + digits (TANK 300, TANK 500), and a letter-only boundary would
# let "TANK 300" match inside a hypothetical "TANK 3000" (no such nameplate exists in this mirror
# today, checked empirically — but the guard is free and protects future pulls).
PPV_RE = {plate: re.compile(r"(?<![A-Z0-9])" + re.escape(plate) + r"(?![A-Z0-9])") for plate in PPV_NAMEPLATES}

FUEL_RULES = [
    ("hybrid", lambda f: "เสียบปลั๊ก" in f),
    ("hybrid", lambda f: ("เบนซิน" in f and "ไฟฟ้า" in f) or ("ดีเซล" in f and "ไฟฟ้า" in f)),
    ("ev", lambda f: f == "ไฟฟ้า"),
    ("gas", lambda f: any(g in f for g in ("CNG", "LPG", "แก๊ส", "LNG"))),
    ("diesel", lambda f: "ดีเซล" in f),
    ("petrol", lambda f: "เบนซิน" in f),
]

LTA_RULES = [
    ("lta_small", lambda s: "ขนาดเล็ก" in s),
    ("lta_truck_personal", lambda s: "บรรทุก" in s and "ส่วนบุคคล" in s),
    ("lta_truck_nonsched", lambda s: "บรรทุก" in s and "ไม่ประจำทาง" in s),
    ("lta_bus_intl", lambda s: "โดยสาร" in s and "ระหว่างประเทศ" in s),
    ("lta_bus_cat1", lambda s: "โดยสาร" in s and "หมวด 1" in s),
    ("lta_bus_cat2", lambda s: "โดยสาร" in s and "หมวด 2" in s),
    ("lta_bus_cat3", lambda s: "โดยสาร" in s and "หมวด 3" in s),
    ("lta_bus_cat4", lambda s: "โดยสาร" in s and "หมวด 4" in s),
    ("lta_bus_personal", lambda s: "โดยสาร" in s and "ส่วนบุคคล" in s),
    ("lta_bus_nonsched", lambda s: "โดยสาร" in s and "ไม่ประจำทาง" in s),
]


def _to_int(x):
    try:
        return int(float(str(x or 0).replace(",", "").strip() or 0))
    except Exception:
        return 0


def _be_to_ce(y):
    y = int(y)
    return y - 543 if y > 2400 else y


def classify_fuel(raw):
    f = (raw or "").strip()
    for name, pred in FUEL_RULES:
        if pred(f):
            return name
    return "other"


def classify_mva(label):
    m = MVA_RE.match((label or "").strip())
    return f"ry{m.group(1)}" if m else "other"


def classify_lta(label):
    s = (label or "").strip()
    for cid, pred in LTA_RULES:
        if pred(s):
            return cid
    return "other"


def _list_months(raw_dir):
    """Every monthly CSV in raw_dir, parsed to (be_year, month_num, path), sorted ascending.
    File naming: "...__<ThaiMonth>_<BEyear>.csv" — same convention as build_vehicle_flow.py."""
    out = []
    for path in glob.glob(os.path.join(raw_dir, "*.csv")):
        name = os.path.splitext(os.path.basename(path))[0]
        tail = name.split("__")[-1]
        try:
            mth, yr = tail.rsplit("_", 1)
            out.append((int(yr), THAI_MONTHS[mth], path))
        except (ValueError, KeyError):
            continue  # not a month file we recognize — skip, don't guess
    out.sort()
    return out


def _list_ppv_months(raw_dir):
    """Every monthly nameplate-level CSV in raw_dir, parsed to (be_year, month_num, path), sorted
    ascending. KNOWN TRAP: these filenames do NOT parse under _list_months()'s "__"-split — the
    remainder collapses to "รถยนต์_-จำแนกตามยี่ห้อและรุ่น_<month>", which is never a THAI_MONTHS key,
    so _list_months() would silently match ZERO files here. Use a standalone year/month regex
    search on the filename instead. This also naturally skips the annual "..._ปี_<BEyear>.csv"
    rollups (no Thai month name for the regex to anchor on, so they never match)."""
    out = []
    for path in glob.glob(os.path.join(raw_dir, "*.csv")):
        name = os.path.splitext(os.path.basename(path))[0]
        for mth, num in THAI_MONTHS.items():
            m = re.search(r"_" + re.escape(mth) + r"_(\d{4})$", name)
            if m:
                out.append((int(m.group(1)), num, path))
                break
    out.sort()
    return out


def _stock_asof(path):
    """Parse the single dataset_1_1_04 file's "ณ_วันที่_<d>_<ThaiMonth>_<BEyear>" as-of date."""
    name = os.path.splitext(os.path.basename(path))[0]
    m = STOCK_NAME_RE.search(name)
    if not m:
        return None
    day, mth, yr = m.group(1), m.group(2), m.group(3)
    if mth not in THAI_MONTHS:
        return None
    return f"{_be_to_ce(yr)}-{THAI_MONTHS[mth]:02d}-{int(day):02d}"


def new_class_dict():
    return defaultdict(int)


def build():
    if not os.path.isdir(DIR_STOCK) or not os.path.isdir(DIR_MVA_FLOW) or not os.path.isdir(DIR_LTA_FLOW) \
            or not os.path.isdir(DIR_PPV):
        return None  # ABSENT — not data drift

    stock_files = glob.glob(os.path.join(DIR_STOCK, "*.csv"))
    if len(stock_files) != 1:
        return None  # expected exactly one cumulative-stock snapshot file
    stock_path = stock_files[0]
    stock_asof = _stock_asof(stock_path)

    mva_months = _list_months(DIR_MVA_FLOW)
    lta_months = _list_months(DIR_LTA_FLOW)
    common = sorted(set((y, m) for y, m, _ in mva_months) & set((y, m) for y, m, _ in lta_months))
    if len(common) < WINDOW:
        return None  # not enough overlapping months for a trailing-12 window — ABSENT
    window = set(common[-WINDOW:])
    mva_window_files = [p for y, m, p in mva_months if (y, m) in window]
    lta_window_files = [p for y, m, p in lta_months if (y, m) in window]

    # ---- stock (Motor Vehicle Act only) --------------------------------------------------
    stock_class = defaultdict(new_class_dict)     # province -> class_id -> count
    stock_fuel = defaultdict(new_class_dict)       # province -> fuel_bucket -> count
    class_labels = {}                               # class_id -> {label, law}
    dropped_stock_rows = 0
    dropped_stock_provs = set()
    with open(stock_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw_p = (row.get("จังหวัด") or "").strip()
            p = canonical(raw_p)
            if p not in REGION:
                dropped_stock_rows += 1
                dropped_stock_provs.add(raw_p)
                continue
            label = (row.get("ประเภทรถ") or "").strip()
            cid = classify_mva(label)
            class_labels.setdefault(cid, {"label": label, "law": "mva"})
            n = _to_int(row.get("จำนวนรถ"))
            stock_class[p][cid] += n
            stock_fuel[p][classify_fuel(row.get("ประเภทเชื้อเพลิง"))] += n

    # ---- new registrations, MVA (dataset_stat_1_008) -------------------------------------
    new_class = defaultdict(new_class_dict)        # province -> class_id -> count (MVA + LTA)
    dropped_new_rows = 0
    dropped_new_provs = set()
    for path in mva_window_files:
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                raw_p = (row.get("จังหวัด") or "").strip()
                p = canonical(raw_p)
                if p not in REGION:
                    dropped_new_rows += 1
                    dropped_new_provs.add(raw_p)
                    continue
                label = (row.get("ประเภทรถ") or "").strip()
                cid = classify_mva(label)
                class_labels.setdefault(cid, {"label": label, "law": "mva"})
                new_class[p][cid] += _to_int(row.get("รถจดใหม่ป้ายแดง"))

    # ---- new registrations, Land Transport Act truck/bus (dataset_stat_1_009) ------------
    for path in lta_window_files:
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                raw_p = (row.get("จังหวัด") or "").strip()
                p = canonical(raw_p)
                if p not in REGION:
                    dropped_new_rows += 1
                    dropped_new_provs.add(raw_p)
                    continue
                label = (row.get("ประเภทรถ") or "").strip()
                cid = classify_lta(label)
                class_labels.setdefault(cid, {"label": label, "law": "transport"})
                new_class[p][cid] += _to_int(row.get("รถจดใหม่ป้ายแดง"))

    # ---- PPV nameplate overlay, national only (stat_1_1_01_first_regis_vehicles_car) -----
    # Independent trailing-12 of this series' own months — not joined to the mva/lta window
    # above (it happens to land on the same span here, since the mirror was pulled together).
    ppv_months = _list_ppv_months(DIR_PPV)
    assert ppv_months, ("stat_1_1_01_first_regis_vehicles_car matched 0 month files — the "
                         "filename pattern drifted, see _list_ppv_months()")
    if len(ppv_months) < WINDOW:
        return None  # not enough months for a trailing-12 PPV window — ABSENT, not data drift
    ppv_window = ppv_months[-WINDOW:]
    ppv_totals = {plate: 0 for plate in PPV_NAMEPLATES}
    for _y, _m, path in ppv_window:
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                nameplate = f"{(row.get('ยี่ห้อ') or '').strip()} {(row.get('รุ่น') or '').strip()}".upper()
                n = _to_int(row.get("จำนวน"))
                for plate in PPV_NAMEPLATES:
                    if PPV_RE[plate].search(nameplate):
                        ppv_totals[plate] += n
                        break  # nameplates are mutually exclusive by construction

    # seed every MVA class (ry1..ry18, whatever the stock file actually carried) into every
    # province's new dict at 0 so consumers get a stable key set even for classes with zero
    # trailing-12mo new registrations (e.g. รย.5 never appears in dataset_stat_1_008 at all).
    mva_ids = sorted([cid for cid, v in class_labels.items() if v["law"] == "mva" and cid != "other"],
                      key=lambda c: int(c[2:]))
    for p in stock_class:
        for cid in mva_ids:
            new_class[p][cid] += 0
            stock_class[p][cid] += 0  # also ensure stock carries every known class at 0

    provinces = {}
    for p in sorted(REGION):
        if p not in stock_class and p not in new_class:
            continue
        provinces[p] = {
            "stock": dict(sorted(stock_class.get(p, {}).items())),
            "stock_fuel": dict(sorted(stock_fuel.get(p, {}).items())),
            "new": dict(sorted(new_class.get(p, {}).items())),
        }

    lo = f"{common[-WINDOW][0] - 543:04d}-{common[-WINDOW][1]:02d}"
    hi = f"{common[-1][0] - 543:04d}-{common[-1][1]:02d}"

    ppv_new_national = {
        "window_months": [f"{y - 543:04d}-{m:02d}" for y, m, _ in ppv_window],
        "total": sum(ppv_totals.values()),
        "by_nameplate": ppv_totals,
        "granularity": "NATIONAL ONLY — this DLT series has no จังหวัด column",
    }

    return {
        "meta": {
            "title": "Vehicle stock + new-registration mix, by province (owner-side staging, MEASURED)",
            "generated_by": "pipeline/ingest_dlt_mix.py",
            "label": "MEASURED — DLT gdcatalog raw mirror (source-data/dlt/raw/, gitignored). Owner-side "
                      "aggregation of plain province-level counts; not in the determinism gate (input is "
                      "off-repo). build_vehicle_mix.py projects this into platform/data/vehicle_mix.json.",
            "stock_source": "dataset_1_1_04 (สถิติจำนวนรถจดทะเบียนสะสม) — cumulative STOCK, Motor Vehicle "
                             "Act (รถยนต์) only, all 18 รย. classes, as-of a single snapshot date. There is "
                             "NO stock file for Land-Transport-Act (truck/bus) vehicles in this mirror — "
                             "their classes carry no stock entry at all (not a fabricated zero); only their "
                             "new-registration flow is measured here.",
            "new_source": "dataset_stat_1_008 (การดำเนินการทางทะเบียน, รถยนต์ — Motor Vehicle Act monthly "
                           "actions) + dataset_stat_1_009 (same shape, รถขนส่ง — Land Transport Act "
                           "truck/bus monthly actions), รถจดใหม่ป้ายแดง (new red-plate) summed over the "
                           "trailing 12 months common to both releases.",
            "ppv_source": "stat_1_1_01_first_regis_vehicles_car (รถจดทะเบียนครั้งแรก, จำแนกตามยี่ห้อและรุ่น) "
                           "— monthly first-registration counts by brand/model, national only. AutoX house "
                           "definition folds PPVs (Fortuner, MU-X, Pajero Sport, Everest, Terra, GWM Tank "
                           "300/500, and the not-yet-launched Land Cruiser FJ) into 'pickup' because they "
                           "register in รย.1 (<=7 seats), not รย.3; see ppv_new_national below. Trailing "
                           "12 months of this series' own data.",
            "stock_asof": stock_asof,
            "new_window_months": [f"{y - 543:04d}-{m:02d}" for y, m in sorted(window)],
            "new_window_label": f"{lo} -> {hi}",
            "class_labels": class_labels,
            "n_provinces": len(provinces),
            "n_dropped_stock_rows": dropped_stock_rows,
            "dropped_stock_provinces": sorted(dropped_stock_provs),
            "n_dropped_new_rows": dropped_new_rows,
            "dropped_new_provinces": sorted(dropped_new_provs),
        },
        "provinces": provinces,
        "ppv_new_national": ppv_new_national,
    }


def run():
    data = build()
    if data is None:
        print("SKIP: source-data/dlt/raw/{dataset_1_1_04,dataset_stat_1_008,dataset_stat_1_009,"
              "stat_1_1_01_first_regis_vehicles_car}/ absent or <12 common/own months present — "
              "not data drift, run pull_dlt_all.py for a fresh mirror")
        return 3
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    m = data["meta"]
    ppv = data["ppv_new_national"]
    print(f"wrote source-data/vehicle_mix_province.json "
          f"({m['n_provinces']} provinces, {len(m['class_labels'])} classes, "
          f"window {m['new_window_label']}, stock as-of {m['stock_asof']}, "
          f"dropped {m['n_dropped_stock_rows']} stock rows / {m['n_dropped_new_rows']} new rows, "
          f"PPV overlay {ppv['total']} across {len(ppv['by_nameplate'])} nameplates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
