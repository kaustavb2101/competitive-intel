#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_livelihood_area.py — province-grain PRODUCTION BASE for the non-crop commodities on the
board: fisheries and forestry. OWNER-SIDE (like ingest_real_tape.py) — it reads the gitignored
gdcatalog harvest and writes one small committed file.

WHY THIS EXISTS
The commodities board answers "who is exposed" by naming the provinces that grow a commodity and
counting our book accounts sitting in them. That worked for the eight crops with a province
planted-area source (rice, rubber, palm, cassava, maize, coconut, pineapple, sugarcane) and left
nine rows with an empty "book exposed" column — pork, white shrimp, eggs, lime, fishmeal, beef,
chicken, sawnwood, logs. Owner, 2026-08-02: "i want the 'book exposed' data for all the commods
meaning you need to find out where the belts of these commods are."

For fisheries and forestry the belts ARE measured and published, just not as planted area:

  white shrimp  DOF marine-shrimp aquaculture — farm AREA (rai) by province.  Directly analogous
                to planted area, so it drops straight into the existing belt logic.
  fishmeal      DOF fishmeal production — there is no area to report (it is a processing industry,
                not a farm), so the belt is built on OUTPUT VOLUME. The borrower behind a fishmeal
                price is the operator and the boats supplying it, not a grower — the board row says
                so rather than implying a farm belt.
  logs,         RFD registered commercial forest plantations (พ.ร.บ. สวนป่า พ.ศ. 2535) — area in
  sawnwood      rai across all 77 provinces. This is where timber is legally GROWN FOR HARVEST.
                Deliberately NOT the reserve-forest layer (ป่าสงวนแห่งชาติ, 66 provinces), which
                measures where forest exists — protected area is where logging does not happen, so
                it would have inverted the signal.

Also carried, because the same DOF release covers them and they are livelihood layers in their own
right even though no board row prices them yet: freshwater aquaculture (77 provinces, the widest
fisheries footprint in the country), brackish-water fish, marine shellfish and mud crab.

NOT COVERED, stated rather than faked:
  pork, eggs, beef, chicken   DLD publishes province livestock counts as PDF only — pending OCR.
  lime                        absent from the DOAE farmer registry (18 crops, no มะนาว) and from
                              every province source held here. No belt is emitted for it.

Thai BE years are folded to CE (‑543). The anchor year is the newest year IN THE DATA, never wall
clock. Province names are canonicalised through lib.regionmap so they join the loan book.

    python3 ingest_livelihood_area.py
    python3 ingest_livelihood_area.py --harvest <path to gdcatalog.go.th>
"""
import argparse, csv, json, os, re, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPE)
from lib.regionmap import canonical, REGION

HARVEST = os.path.join(ROOT, "source-data", "gdcatalog_harvest", "gdcatalog.go.th")
OUT = os.path.join(ROOT, "source-data", "livelihood_area.json")

# dataset folder → (file substring, what we pull out of it)
DOF_AQUA = "gdpublish-dofd07-05-0101-04"
DOF_MEAL = "gdpublish-dofd07-05-0101-05"
RFD_PLANT = "gdpublish-2535"

# aquaculture releases we read, and the column that carries the belt measure for each
AQUA = {
    "shrimp_marine":     ("กุ้งทะเล",     "เนื้อที่เลี้ยง"),
    "fish_freshwater":   ("สัตว์น้ำจืด",  "เนื้อที่เลี้ยง"),
    "fish_brackish":     ("ปลาน้ำกร่อย",  "เนื้อที่เลี้ยง"),
    "shellfish_marine":  ("หอยทะเล",      "เนื้อที่เลี้ยง"),
    "crab_mud":          ("ปูทะเล",       "เนื้อที่เลี้ยง"),
}


def _num(x):
    """Thai CSVs carry thousands separators and stray spaces; blank means absent, not zero."""
    s = str(x or "").replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _be_to_ce(y):
    """Buddhist-era year → CE. Bare BE years read 543 in the future if left alone."""
    try:
        y = int(str(y).strip())
    except (TypeError, ValueError):
        return None
    return y - 543 if y > 2400 else y


def _read_csv(path):
    """DOF ships utf-8-sig; the RFD plantation registry is cp874. Try both, never guess silently."""
    for enc in ("utf-8-sig", "cp874"):
        try:
            with open(path, encoding=enc) as f:
                rows = list(csv.DictReader(f))
            if rows and any("จังหวัด" in (c or "") for c in rows[0].keys()):
                return rows, enc
        except (UnicodeDecodeError, LookupError):
            continue
    return [], None


def _find(harvest, folder, substr):
    d = os.path.join(harvest, "data", folder)
    if not os.path.isdir(d):
        return None
    for name in sorted(os.listdir(d)):
        if name.lower().endswith(".csv") and substr in name:
            return os.path.join(d, name)
    return None


def _pcol(row):
    for k in row:
        if k and "จังหวัด" in k:
            return k
    return None


def aqua_layer(harvest, substr, valcol):
    """{province_th: measure} for the newest year present, plus the year and a national total."""
    path = _find(harvest, DOF_AQUA, substr)
    if not path:
        return None
    rows, _ = _read_csv(path)
    if not rows:
        return None
    pk = _pcol(rows[0])
    years = {_be_to_ce(r.get("ปี")) for r in rows}
    years.discard(None)
    if not years:
        return None
    newest = max(years)
    prov = defaultdict(float)
    for r in rows:
        if _be_to_ce(r.get("ปี")) != newest:
            continue
        p = canonical((r.get(pk) or "").strip())
        v = _num(r.get(valcol))
        if p in REGION and v:
            prov[p] += v          # sum across culture types / species within the province
    return {"year": newest, "provinces": {k: round(v, 2) for k, v in prov.items() if v > 0}}


def fishmeal_layer(harvest):
    """Fishmeal has no area — the belt is OUTPUT VOLUME (ปริมมาณปลาป่น, the source's own spelling)."""
    path = _find(harvest, DOF_MEAL, "ปลาป่น")
    if not path:
        return None
    rows, _ = _read_csv(path)
    if not rows:
        return None
    pk = _pcol(rows[0])
    years = {_be_to_ce(r.get("ปี")) for r in rows}
    years.discard(None)
    if not years:
        return None
    newest = max(years)
    prov, ops = defaultdict(float), defaultdict(float)
    for r in rows:
        if _be_to_ce(r.get("ปี")) != newest:
            continue
        p = canonical((r.get(pk) or "").strip())
        if p not in REGION:
            continue
        v = _num(r.get("ปริมมาณปลาป่น"))
        if v:
            prov[p] += v
        n = _num(r.get("จำนวนผู้ประกอบการ"))
        if n:
            ops[p] += n
    return {"year": newest,
            "provinces": {k: round(v, 2) for k, v in prov.items() if v > 0},
            "operators": {k: int(v) for k, v in ops.items() if v > 0}}


RAI_RE = re.compile(r"^\s*(-?[\d,.]+)\s*-\s*(-?[\d,.]+)\s*-\s*(-?[\d,.]+)\s*$")


def _thai_area_to_rai(s):
    """'1343 - 2 - 85.89' = rai - ngan - square wa.  1 rai = 4 ngan = 400 sq wa."""
    m = RAI_RE.match(str(s or ""))
    if not m:
        return _num(s)
    rai, ngan, wa = (_num(g) or 0 for g in m.groups())
    return round(rai + ngan / 4.0 + wa / 400.0, 4)


def plantation_layer(harvest):
    """RFD registered commercial forest plantations — where timber is legally grown for harvest."""
    path = _find(harvest, RFD_PLANT, "สวนป่า")
    if not path:
        return None
    rows, enc = _read_csv(path)
    if not rows:
        return None
    pk = _pcol(rows[0])
    acol = next((k for k in rows[0] if k and "เนื้อที่" in k), None)
    rcol = next((k for k in rows[0] if k and "ราย" in k), None)
    tcol = next((k for k in rows[0] if k and "ต้นไม้" in k), None)
    prov, holders, trees = {}, {}, {}
    for r in rows:
        p = canonical((r.get(pk) or "").strip())
        if p not in REGION:
            continue           # drops the "รวม" total row as well as any unmatched name
        a = _thai_area_to_rai(r.get(acol)) if acol else None
        if a and a > 0:
            prov[p] = a
        if rcol and (_num(r.get(rcol)) or 0) > 0:
            holders[p] = int(_num(r.get(rcol)))
        if tcol and (_num(r.get(tcol)) or 0) > 0:
            trees[p] = int(_num(r.get(tcol)))
    if not prov:
        return None
    return {"encoding": enc, "provinces": prov, "holders": holders, "trees": trees}


def build(harvest):
    fisheries = {}
    for key, (substr, valcol) in AQUA.items():
        lay = aqua_layer(harvest, substr, valcol)
        if lay:
            fisheries[key] = lay
    meal = fishmeal_layer(harvest)
    if meal:
        fisheries["fishmeal"] = meal
    plant = plantation_layer(harvest)

    return {
        "meta": {
            "title": "Province production base for the non-crop board rows (fisheries + forestry)",
            "generated_by": "pipeline/ingest_livelihood_area.py",
            "label": "MEASURED — Department of Fisheries aquaculture and fishmeal releases, and the "
                     "Royal Forest Department register of commercial forest plantations under the "
                     "Forest Plantation Act B.E. 2535. Province grain, newest year in the data.",
            "owner_side": True,
            "note": "Belt measure differs by commodity and each layer says which it uses: farm AREA "
                    "in rai for aquaculture and plantations, OUTPUT VOLUME for fishmeal (a "
                    "processing industry with no farm area to report). Thai BE years folded to CE.",
            "not_covered": {
                "pork/eggs/beef/chicken": "DLD publishes province livestock counts as PDF only — "
                                          "pending OCR. No belt emitted rather than a guessed one.",
                "lime": "absent from the DOAE farmer registry (18 crops, no มะนาว) and from every "
                        "province source held here. No belt emitted.",
            },
            "source_paths": {"aquaculture": DOF_AQUA, "fishmeal": DOF_MEAL,
                             "plantation": RFD_PLANT},
        },
        "fisheries": fisheries,
        "forestry": {"plantation": plant} if plant else {},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harvest", default=HARVEST)
    a = ap.parse_args()
    if not os.path.isdir(a.harvest):
        sys.exit("ingest_livelihood_area.py: harvest not found at %s\n"
                 "  This is an OWNER-SIDE ingest — it needs the gitignored gdcatalog harvest."
                 % a.harvest)
    doc = build(a.harvest)
    if not doc["fisheries"] and not doc["forestry"]:
        sys.exit("ingest_livelihood_area.py: no layers built — harvest present but empty?")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    print("wrote %s" % OUT)
    for k, v in sorted(doc["fisheries"].items()):
        print("  fisheries %-18s %2d provinces (year %s)"
              % (k, len(v["provinces"]), v.get("year", "—")))
    for k, v in sorted(doc["forestry"].items()):
        print("  forestry  %-18s %2d provinces" % (k, len(v["provinces"])))


if __name__ == "__main__":
    main()
