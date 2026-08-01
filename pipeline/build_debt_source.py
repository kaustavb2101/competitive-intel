#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_debt_source.py — household debt IN the system vs OUTSIDE it (objectives #1 and #2).

  in : source-data/nso_debt_by_source.json   MEASURED — NSO household survey extract, 7 waves
  out: platform/data/debt_source.json         (--check: byte-exact reproduce)

  python3 build_debt_source.py --extract   # re-derive the extract from the gdcatalog harvest
  python3 build_debt_source.py             # extract -> platform/data/debt_source.json
  python3 build_debt_source.py --check     # byte-exact reproduce (gate)

WHAT IT IS. The National Statistical Office's household survey asks how much a household owes and
WHERE IT BORROWED FROM — หนี้ในระบบ (in the formal system) versus หนี้นอกระบบ (outside it) — broken
out by region, by borrowing purpose, and by the household's socio-economic class. Seven waves,
2554..2566 (2011..2023). It has been sitting in the gdcatalog harvest unread.

WHY IT MATTERS HERE. AutoX is a non-bank title lender: the informal/out-of-system pool is the pool
its product converts, and the socio-economic classes NSO uses line up almost exactly with the
occupation groups the loan tape records (farm operators owning vs renting land, farm labourers,
transport workers, production workers, sales/clerical, non-farm own-account business). So this is
the closest thing available to a measured, independent read of the borrower population — by region,
by occupation, over twelve years.

WHAT IT SAYS, INCLUDING THE PART THAT CUTS AGAINST THE HOUSE VIEW. Nationally, out-of-system debt is
SMALL and SHRINKING as a share of household debt: 2.9% of the average household's debt in 2554,
1.3% by 2566. If the strategy story assumes a large informal pool, this measured series does not
support it at the national level.

THE CAVEAT THAT MUST TRAVEL WITH IT. This is self-reported in a government survey. Informal
borrowing is exactly the kind of thing households under-report to an official interviewer, so the
level is a FLOOR, not an estimate of the true pool. The TREND and the RANKING between regions and
classes are the defensible readings; the absolute share is not. Stated in meta and on the page.
"""
import argparse, csv, io, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data", "nso_debt_by_source.json")
OUT = os.path.join(ROOT, "platform", "data", "debt_source.json")
HARVEST = os.path.join(ROOT, "source-data", "gdcatalog_harvest", "gdcatalog.go.th")
BE_OFFSET = 543

TOTAL = "รวม"
IN_SYS = "หนี้ในระบบ"
OUT_SYS = "หนี้นอกระบบ"
AGRI = "ใช้ในการทำการเกษตร"
BIZ = "ใช้ในการทำธุรกิจ"
CONSUME = "ใช้จ่ายอุปโภคบริโภคอื่นๆ ในครัวเรือน"

# NSO socio-economic class -> the loan tape's occupation vocabulary. Not a join key (the survey is
# regional, the tape is per-branch) — a LABEL, so a reader can see which class corresponds to which
# part of the book without having to parse the Thai.
CLASS_EN = {
    "รวม": "All households",
    "ผู้ถือครองทำการเกษตร/เพาะเลี้ยง : ปลูกพืช/เลี้ยงสัตว์/เพาะเลี้ยง : ส่วนใหญ่เป็นเจ้าของที่ดิน":
        "Farm operator — owns most of the land",
    "ผู้ถือครองทำการเกษตร/เพาะเลี้ยง : ปลูกพืช/เลี้ยงสัตว์/เพาะเลี้ยง : ส่วนใหญ่เช่าที่ดิน/ทำฟรี":
        "Farm operator — rents most of the land",
    "ผู้ถือครองทำการเกษตร/เพาะเลี้ยง : ประมง,ป่าไม้,ล่าสัตว์,หาของป่า,บริการทางการเกษตร":
        "Fishing / forestry / agri services",
    "ลูกจ้าง : คนงานเกษตร ป่าไม้ และประมง": "Farm / forestry / fishery labourer",
    "ลูกจ้าง : คนงาน ด้านการขนส่ง และงานพื้นฐาน": "Transport & elementary worker",
    "ลูกจ้าง : ผู้ปฏิบัติงาน ในกระบวนการผลิต ก่อสร้างและเหมืองแร่": "Production / construction worker",
    "ลูกจ้าง : เสมียน พนักงานขาย และให้บริการ": "Clerical / sales / service",
    "ลูกจ้าง : ผู้จัดการ นักวิชาการ และผู้ปฏิบัติงานวิชาชีพ": "Manager / professional",
    "ผู้ประกอบธุรกิจของตนเองที่ไม่ใช่การเกษตร": "Own-account non-farm business",
    "ผู้ไม่ได้ปฏิบัติงานเชิงเศรษฐกิจ": "Not economically active",
}
REGION_EN = {
    "ทั่วราชอาณาจักร": "Whole kingdom",
    "ภาคกลาง": "Central", "ภาคเหนือ": "North",
    "ภาคตะวันออกเฉียงเหนือ": "Northeast (Isan)", "ภาคใต้": "South",
    "กรุงเทพมหานคร นนทบุรี ปทุมธานี และสมุทรปราการ": "Greater Bangkok",
}
NATION = "ทั่วราชอาณาจักร"


def extract():
    """Re-derive source-data/nso_debt_by_source.json from the (gitignored) gdcatalog harvest.

    Only the cells this layer renders are kept — the raw CSV is 3.5MB of mostly repeated Thai
    labels, and committing it whole to serve ~460 records would be waste, not provenance.
    """
    man = os.path.join(HARVEST, "_manifest.jsonl")
    if not os.path.exists(man):
        sys.exit("gdcatalog harvest absent — nothing to extract from (%s)" % HARVEST)
    sep = chr(92)
    path = None
    for line in io.open(man, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        n = d.get("name") or ""
        if ("หนี้สินเฉลี่ยต่อครัวเรือน" in n and "แหล่งเงินกู้" in n
                and (d.get("format") or "").upper() == "CSV"):
            c = os.path.join(HARVEST, (d.get("path") or "").replace(sep, "/"))
            if os.path.exists(c) and (path is None or os.path.getsize(c) > os.path.getsize(path)):
                path = c
    if not path:
        sys.exit("the debt-by-source CSV is not in the harvest manifest")

    raw = io.open(path, "rb").read()
    txt = None
    for enc in ("utf-8-sig", "utf-8", "cp874"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    rows = list(csv.DictReader(io.StringIO(txt)))
    # Exactly the (source, purpose) pairs build() reads — not the cross product. The source splits
    # are only ever needed at Purpose=total, and the purpose splits only at Source=total, so
    # keeping all 3x4 combinations would double the committed extract for cells nothing renders.
    keep_pairs = {(TOTAL, TOTAL), (IN_SYS, TOTAL), (OUT_SYS, TOTAL),
                  (TOTAL, AGRI), (TOTAL, BIZ), (TOTAL, CONSUME)}
    keep_purpose = sorted({p for _, p in keep_pairs})
    cells = {}
    for r in rows:
        pur = (r.get("Purpose_borrow") or "").strip()
        if ((r.get("Source_loan") or "").strip(), pur) not in keep_pairs:
            continue
        try:
            v = float((r.get("value") or "").replace(",", "").strip())
        except ValueError:
            continue
        k = "|".join([(r.get("Year") or "").strip(), (r.get("Region") or "").strip(),
                      (r.get("Soc_eco_class") or "").strip(),
                      (r.get("Source_loan") or "").strip(), pur])
        cells[k] = v
    doc = {
        "meta": {
            "title": "MEASURED household debt by source of loan (NSO household survey)",
            "generated_by": "pipeline/build_debt_source.py --extract",
            "source": "สำนักงานสถิติแห่งชาติ (NSO) — จำนวนหนี้สินเฉลี่ยต่อครัวเรือน จำแนกตาม"
                      "แหล่งเงินกู้ วัตถุประสงค์ของการกู้ยืม และสถานะทางเศรษฐสังคมของครัวเรือน; "
                      "gdcatalog dataset gdpublish-os_08_00011, via the local harvest.",
            "unit": "baht per household (average)",
            "key": "Year|Region|Soc_eco_class|Source_loan|Purpose_borrow",
            "purposes_kept": keep_purpose,
            "note": "Extract, not the whole CSV: the source is 3.5MB of mostly repeated Thai labels "
                    "and only these purposes are rendered.",
            "n_cells": len(cells),
        },
        "cells": {k: cells[k] for k in sorted(cells)},
    }
    with open(SRC, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    print("wrote %s (%d cells, %.0f KB) from %s"
          % (SRC, len(cells), os.path.getsize(SRC) / 1024.0, os.path.basename(path)))


def build():
    if not os.path.exists(SRC):
        return None
    with open(SRC, encoding="utf-8") as f:
        cells = json.load(f)["cells"]

    def v(y, reg, cls, src, pur):
        return cells.get("|".join([y, reg, cls, src, pur]))

    years = sorted({k.split("|")[0] for k in cells})
    regions = sorted({k.split("|")[1] for k in cells})
    classes = sorted({k.split("|")[2] for k in cells})

    def block(y, reg, cls):
        tot = v(y, reg, cls, TOTAL, TOTAL)
        ins = v(y, reg, cls, IN_SYS, TOTAL)
        inf = v(y, reg, cls, OUT_SYS, TOTAL)
        if tot in (None, 0):
            return None
        agri = v(y, reg, cls, TOTAL, AGRI)
        return {
            "year_be": int(y), "year_ce": int(y) - BE_OFFSET,
            "total": tot, "in_system": ins, "informal": inf,
            "informal_pct": round(inf / tot * 100, 2) if inf is not None else None,
            "agri_debt": agri,
            "agri_pct": round(agri / tot * 100, 1) if agri is not None else None,
            "business_debt": v(y, reg, cls, TOTAL, BIZ),
            "consumption_debt": v(y, reg, cls, TOTAL, CONSUME),
        }

    national = [b for b in (block(y, NATION, TOTAL) for y in years) if b]
    latest = years[-1]

    by_region, by_class = [], []
    for reg in regions:
        b = block(latest, reg, TOTAL)
        if b:
            hist = [x for x in (block(y, reg, TOTAL) for y in years) if x]
            by_region.append(dict(b, region=reg, region_en=REGION_EN.get(reg, reg),
                                  informal_series=[{"year_ce": x["year_ce"],
                                                    "informal_pct": x["informal_pct"]} for x in hist]))
    for cls in classes:
        b = block(latest, NATION, cls)
        if b:
            by_class.append(dict(b, cls=cls, cls_en=CLASS_EN.get(cls, cls)))
    # Informal share desc, then debt size, then the Thai label — a total order, so a tie can never
    # be broken by dict/set iteration and fail the byte-exact --check under hash randomization.
    by_region.sort(key=lambda r: (-(r["informal_pct"] or 0), -r["total"], r["region"]))
    by_class.sort(key=lambda r: (-(r["informal_pct"] or 0), -r["total"], r["cls"]))

    n0, n1 = national[0], national[-1]
    return {
        "meta": {
            "title": "MEASURED household debt: inside the formal system vs outside it (NSO)",
            "generated_by": "pipeline/build_debt_source.py",
            "label": "MEASURED — National Statistical Office household survey, 7 waves "
                     "%d..%d. Baht per household, survey means by region and socio-economic class."
                     % (n0["year_ce"], n1["year_ce"]),
            "source": "NSO gdpublish-os_08_00011 (จำแนกตามแหล่งเงินกู้ วัตถุประสงค์ และสถานะ"
                      "ทางเศรษฐสังคมของครัวเรือน), via the gdcatalog harvest.",
            "headline": "Out-of-system debt is SMALL and SHRINKING as a share of household debt "
                        "nationally: %.1f%% of the average household's debt in %d, %.1f%% in %d. "
                        "If a strategy assumes a large informal pool to convert, this measured "
                        "series does not support it at the national level."
                        % (n0["informal_pct"], n0["year_ce"], n1["informal_pct"], n1["year_ce"]),
            "under_reporting_caveat": "SELF-REPORTED to a government interviewer. Informal "
                                      "borrowing is precisely what households under-state in an "
                                      "official survey, so the level is a FLOOR, not an estimate "
                                      "of the true pool. The defensible readings are the TREND and "
                                      "the RANKING between regions and classes — not the absolute "
                                      "share.",
            "scope_warning": "REGIONAL, not provincial, and the classes are the survey's own "
                             "socio-economic categories. They line up closely with the loan tape's "
                             "occupation groups but are NOT the same population and must not be "
                             "joined to a branch or a province.",
            "survey_years_be": years,
            "latest_year_be": latest,
            "latest_year_ce": int(latest) - BE_OFFSET,
        },
        "national": national,
        "by_region": by_region,
        "by_class": by_class,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extract", action="store_true", help="re-derive the extract from the harvest")
    ap.add_argument("--check", action="store_true", help="verify byte-exact reproduce")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if args.extract:
        extract()
        if not args.check:
            return

    doc = build()
    if doc is None:
        print("build_debt_source.py: SKIP (source-data/nso_debt_by_source.json absent — "
              "run: python3 pipeline/build_debt_source.py --extract)")
        sys.exit(3)
    payload = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_debt_source.py --check: drifted — re-run the builder.")
        print("build_debt_source.py --check: OK (byte-exact)")
        return
    # newline="\n": the Windows default writes CRLF, inflating the byte size provenance censuses.
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    n = doc["national"][-1]
    print("wrote %s" % OUT)
    print("  national %d: total ฿%s · in-system ฿%s · informal ฿%s (%.2f%%)"
          % (n["year_ce"], format(int(n["total"]), ","), format(int(n["in_system"]), ","),
             format(int(n["informal"]), ","), n["informal_pct"]))
    print("  most informal-exposed regions (%d):" % doc["meta"]["latest_year_ce"])
    for r in doc["by_region"][:4]:
        print("    %-18s %5.2f%% informal   total ฿%s"
              % (r["region_en"], r["informal_pct"] or 0, format(int(r["total"]), ",")))
    print("  most informal-exposed classes:")
    for r in doc["by_class"][:4]:
        print("    %-34s %5.2f%%   total ฿%s"
              % (r["cls_en"][:34], r["informal_pct"] or 0, format(int(r["total"]), ",")))


if __name__ == "__main__":
    main()
