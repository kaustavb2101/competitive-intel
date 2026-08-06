#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_doae_fruit.py — province-grain fruit & perennial-crop planted area, from DOAE's "รต."
(rortor) annual crop-situation PDF series. OWNER-SIDE, same pattern as ingest_real_tape.py /
ingest_livelihood_area.py: reads PDFs that were already pulled to disk and writes one small
committed no-network-needed file. Parsing itself is network-free.

WHY THIS EXISTS
ingest_livelihood_area.py closed the fisheries/forestry belt gap but left lime (มะนาว) with no
belt at all: "absent from the DOAE farmer registry (18 crops, no มะนาว) and from every province
source held here. No belt is emitted for it." Lime prices a board row today (NABC มะนาว → "Lime")
with no book-exposure drill. This is the source that closes it — the DOAE Agricultural Information
Center's own crop-situation report DOES carry lime, one PDF per crop, ranking every producing
province by planted/damaged/bearing area, production and price. It also carries ten OTHER
fruit/perennial crops not on the board today; all 11 are parsed here so the file is ready the next
time one of them gets a board row, even though only lime is wired into build_commodities.py now.

SOURCE
  http://www.agriinfo.doae.go.th/year63/plant/rortor/ — DOAE's annual crop-situation ("รต.")
  series, one PDF per crop. Every PDF here is dated ปี 2562 (crop year 2019 CE) — that is the
  NEWEST vintage this series ever published, not a failed pull: year64/65/67 return a clean HTTP
  404 ("The requested URL /yearNN/ was not found on this server"); year66 exists but holds an
  unrelated document set (farmer-group / budget PDFs, not crop-production reports); year68 exists
  but is login-gated. A prior research pass verified this exhaustively; re-checked here against the
  saved snapshot HTML the pull left behind. Crawling .../plant/rortor/ directly now serves a login
  form rather than a directory listing, so the exact per-file download URLs are not independently
  re-derivable from this machine any more — the PDFs are committed as the retrieved artifact and
  read from disk from here on, the same relationship ingest_real_tape.py has to its source xlsx.

  Lime is not in ANY other province-grain source this repo holds: not the DOAE farmer registry
  (platform/data/province_cropland.json, 18 crops, no มะนาว), not the planted-area census
  (source-data/crop_prov_area.json — rice/rubber/oilpalm only), not SPAM 2010, not OCSB (sugarcane
  only). This 2019 รต. PDF is the ONLY province-grain lime figure that exists anywhere in this
  pipeline as of four independent searches — which is why a 7-year-old vintage is used rather than
  leaving the row without a belt.

PARSING — reuses the two font traps solved in the scratch parse (parse_lamon.py) and generalizes
one of them, because it turned out to be bidirectional across this 11-PDF set:
  (a) extract_text(use_text_flow=True, x_tolerance=1) — without it this font's embedded ToUnicode
      CMap injects spurious mid-number spaces ("4 0,525" for 40,525).
  (b) sara-am (ำ, U+0E33) / sara-aa (า, U+0E32) confusion. lamon_year63.pdf (lime) DROPS ำ to a
      bare space + า (the case parse_lamon.py documented, against the 5 provinces that actually
      contain ำ: กำแพงเพชร/ลำปาง/ลำพูน/อำนาจเจริญ/หนองบัวลำภู). fruit_langan.pdf (longan) and
      fruit_lichee.pdf (lychee) do the OPPOSITE — า is extracted AS ำ, corrupting province names
      that never had a ำ at all (เชียงราย → "เชียงรำย", พะเยา → "พะเยำ"). Folding BOTH characters to
      one token before matching against the canonical 77-province list (lib.regionmap.REGION)
      resolves both directions with a single map. Verified no two of the 77 canonical names
      collide under this fold, so it cannot introduce a false match.
  Every crop's row-sum is cross-checked against the PDF's own printed "รวมทั้งหมด" total; the delta
  is recorded in meta rather than silently corrected. All 11 land within 9 rai of their stated
  total (lime: -5) — the source's own footing/rounding, not a parse error.

    python3 ingest_doae_fruit.py
    python3 ingest_doae_fruit.py --src <dir holding the pulled PDFs>
"""
import argparse
import datetime
import json
import os
import re
import sys

import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPE)
from lib.regionmap import REGION

# Ephemeral pulled-artifact location from the research session that fetched these PDFs (like
# ingest_real_tape.py's DEFAULT_SRC, off-repo and owner/session-specific). Override with --src or
# DOAE_FRUIT_SRC once the PDFs live somewhere more permanent.
DEFAULT_SRC = (
    r"C:\Users\KAUSTA~1\AppData\Local\Temp\claude\c--Users-Kaustav-Bagchi-competitive-intel-"
    r"competitive-intel\ca1875f5-165d-49f3-99c5-29f4e9820c7e\scratchpad\doae_fruit"
)
OUT = os.path.join(ROOT, "source-data", "doae_fruit_area.json")

# crop key -> (pdf filename, Thai crop name straight off that PDF's own header line). Superseded /
# niche-variety duplicates in the same pull (fruit_longan.pdf, fruit_mangosteen.pdf,
# fruit_durian2.pdf, perennial_coconut3.pdf) are deliberately NOT listed here.
CROPS = {
    "lime":       ("lamon_year63.pdf",      "มะนาว"),
    "durian":     ("fruit_durian.pdf",      "ทุเรียน"),
    "longan":     ("fruit_langan.pdf",      "ลำไย"),
    "longkong":   ("fruit_longong.pdf",     "ลองกอง"),
    "rambutan":   ("fruit_rambutan.pdf",    "เงาะ"),
    "mangosteen": ("fruit_magosteen.pdf",   "มังคุด"),
    "lychee":     ("fruit_lichee.pdf",      "ลิ้นจี่"),
    "mango":      ("fruit_mango.pdf",       "มะม่วง"),
    "pomelo":     ("fruit_pomelo.pdf",      "ส้มโอ"),
    "coconut":    ("perennial_coconut.pdf", "มะพร้าว"),
    "coffee":     ("perennial_coffee.pdf",  "กาแฟ"),
}

# --- province-name canonicalization -------------------------------------------------------------
# lib.regionmap.REGION is this repo's canonical 77-province Thai key set (the same one
# source-data/livestock_province.json joins on). Fold BOTH ำ and า to one token before matching —
# see the module docstring for why both directions of the font's ำ/า confusion show up across
# these 11 files. Checked: no two of the 77 canonical names collide under this fold.
CANON = set(REGION)
assert len(CANON) == 77, "lib.regionmap.REGION drifted off 77 provinces: got %d" % len(CANON)
CANON_EXACT = {p.replace(" ", ""): p for p in CANON}
CANON_FOLD = {}
for _p in CANON:
    _key = _p.replace(" ", "").replace("\xa0", "").replace("ำ", "*").replace("า", "*")
    CANON_FOLD[_key] = _p


def canon_match(raw):
    """raw is a Thai chunk possibly carrying pdfplumber's stray internal spaces / dropped or
    substituted sara-am glyphs. Exact no-space match first, then the ำ/า-folded match. Returns
    None (not a guess) when neither matches, so callers can report it rather than silently drop."""
    stripped = raw.replace(" ", "").replace("\xa0", "")
    if stripped in CANON_EXACT:
        return CANON_EXACT[stripped]
    folded = stripped.replace("ำ", "*").replace("า", "*")
    return CANON_FOLD.get(folded)


NUMFIELD = r"([\d,]+(?:\.\d+)?|-)"
ROW_RE = re.compile(r"^(\d+)\s+(.+?)\s+" + r"\s+".join([NUMFIELD] * 6) + r"$")
TOTAL_RE = re.compile(r"^รวมทั้งหมด\s+" + r"\s+".join([NUMFIELD] * 6) + r"$")


def to_num(s):
    if s is None or s == "-":
        return None
    s = s.replace(",", "")
    return float(s) if "." in s else int(s)


def parse_pdf(path):
    """Returns (year_be, total_dict_or_None, {province: row_dict}, unmatched_lines)."""
    with pdfplumber.open(path) as pdf:
        full = "\n".join(
            page.extract_text(use_text_flow=True, x_tolerance=1) or "" for page in pdf.pages
        )

    m = re.search(r"ปี\s*(25\d{2})", full)
    year_be = int(m.group(1)) if m else None

    total = None
    rows = {}
    unmatched = []
    for line in full.splitlines():
        line = line.strip()
        if not line:
            continue
        mt = TOTAL_RE.match(line)
        if mt:
            total = {
                "planted_area_rai": to_num(mt.group(1)),
                "damaged_area_rai": to_num(mt.group(2)),
                "bearing_area_rai": to_num(mt.group(3)),
                "production_kg": to_num(mt.group(4)),
                "yield_kg_per_rai": to_num(mt.group(5)),
                "price_baht_per_kg": to_num(mt.group(6)),
            }
            continue
        mr = ROW_RE.match(line)
        if mr:
            prov = canon_match(mr.group(2))
            if prov is None:
                unmatched.append(line)
                continue
            rows[prov] = {
                "planted_area_rai": to_num(mr.group(3)),
                "damaged_area_rai": to_num(mr.group(4)),
                "bearing_area_rai": to_num(mr.group(5)),
                "production_kg": to_num(mr.group(6)),
                "yield_kg_per_rai": to_num(mr.group(7)),
                "price_baht_per_kg": to_num(mr.group(8)),
            }
    return year_be, total, rows, unmatched


# --- acceptance test: reproduce the verified lime facts before trusting anything else ------------
LIME_ACCEPT = {
    "year_be": 2562, "n_provinces": 75,
    "planted": 150342, "bearing": 85451, "production_kg": 366228708, "price": 41.13,
    "missing": {"ปัตตานี", "ระนอง"},
    "top10": [("เพชรบุรี", 40525), ("ราชบุรี", 13492), ("สมุทรสาคร", 8398),
              ("กำแพงเพชร", 8392), ("พิจิตร", 8206), ("นครศรีธรรมราช", 5478),
              ("ลำปาง", 5248), ("กาญจนบุรี", 4982), ("นครปฐม", 4212),
              ("ประจวบคีรีขันธ์", 4060)],
    "suphanburi_rank": (22, 1339),
}


def assert_lime(year_be, total, rows):
    errs = []
    if year_be != LIME_ACCEPT["year_be"]:
        errs.append("year_be %r != %r" % (year_be, LIME_ACCEPT["year_be"]))
    if len(rows) != LIME_ACCEPT["n_provinces"]:
        errs.append("n_provinces %d != %d" % (len(rows), LIME_ACCEPT["n_provinces"]))
    for f, key in (("planted_area_rai", "planted"), ("bearing_area_rai", "bearing"),
                   ("production_kg", "production_kg"), ("price_baht_per_kg", "price")):
        if (total or {}).get(f) != LIME_ACCEPT[key]:
            errs.append("%s %r != %r" % (f, (total or {}).get(f), LIME_ACCEPT[key]))
    missing = CANON - set(rows)
    if missing != LIME_ACCEPT["missing"]:
        errs.append("missing provinces %r != %r" % (missing, LIME_ACCEPT["missing"]))
    ranked = sorted(rows.items(), key=lambda kv: -(kv[1]["planted_area_rai"] or 0))
    top10 = [(pv, r["planted_area_rai"]) for pv, r in ranked[:10]]
    if top10 != LIME_ACCEPT["top10"]:
        errs.append("top10 %r != %r" % (top10, LIME_ACCEPT["top10"]))
    supp_rank = next((i + 1 for i, (pv, _) in enumerate(ranked) if pv == "สุพรรณบุรี"), None)
    supp_area = rows.get("สุพรรณบุรี", {}).get("planted_area_rai")
    if (supp_rank, supp_area) != LIME_ACCEPT["suphanburi_rank"]:
        errs.append("suphanburi %r != %r" % ((supp_rank, supp_area), LIME_ACCEPT["suphanburi_rank"]))
    if errs:
        sys.exit("ingest_doae_fruit.py: LIME ACCEPTANCE TEST FAILED — parser or source drifted:\n  "
                  + "\n  ".join(errs))


def build(src):
    crops = {}
    deltas = {}
    warnings = []
    for key, (fname, th_name) in CROPS.items():
        path = os.path.join(src, fname)
        if not os.path.isfile(path):
            warnings.append("%s: PDF not found at %s — skipped" % (key, path))
            continue
        try:
            year_be, total, rows, unmatched = parse_pdf(path)
        except Exception as e:  # keep going — one bad PDF should not sink the other 10
            warnings.append("%s: parse raised %r — skipped" % (key, e))
            continue
        if not total or not rows:
            warnings.append("%s: no total/province rows parsed — skipped" % key)
            continue
        if unmatched:
            warnings.append("%s: %d unmatched province line(s) — %s"
                             % (key, len(unmatched), " | ".join(unmatched)))
        if key == "lime":
            assert_lime(year_be, total, rows)

        planted_sum = sum(r["planted_area_rai"] for r in rows.values() if r["planted_area_rai"])
        printed_total = total.get("planted_area_rai")
        planted_delta = (printed_total - planted_sum) if printed_total is not None else None
        year_ce = year_be - 543 if year_be and year_be > 2400 else year_be

        crops[key] = {
            "crop_th": th_name,
            "year_ce": year_ce,
            "year_be": year_be,
            "unit": "rai",
            "national_planted_rai": printed_total,
            "national_bearing_rai": total.get("bearing_area_rai"),
            "national_output_kg": total.get("production_kg"),
            "price_baht_kg": total.get("price_baht_per_kg"),
            "provinces": {pv: r["planted_area_rai"] for pv, r in rows.items()
                          if r["planted_area_rai"]},
            "bearing": {pv: r["bearing_area_rai"] for pv, r in rows.items()
                        if r["bearing_area_rai"]},
        }
        deltas[key] = {
            "n_provinces": len(rows),
            "printed_total_planted_rai": printed_total,
            "row_sum_planted_rai": planted_sum,
            "delta_rai": planted_delta,
        }
    return crops, deltas, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.environ.get("DOAE_FRUIT_SRC", DEFAULT_SRC))
    a = ap.parse_args()
    if not os.path.isdir(a.src):
        sys.exit("ingest_doae_fruit.py: source dir not found at %s (set --src or DOAE_FRUIT_SRC)"
                  % a.src)

    crops, deltas, warnings = build(a.src)
    if "lime" not in crops:
        sys.exit("ingest_doae_fruit.py: lime failed to parse — refusing to write without it "
                  "(it is the whole point of this ingest).")

    doc = {
        "meta": {
            "title": "Province planted area — DOAE annual crop-situation ('รต.') series, 11 fruit "
                     "and perennial crops including lime",
            "generated_by": "pipeline/ingest_doae_fruit.py",
            "label": "MEASURED — DOAE Agricultural Information Center annual crop-situation "
                     "report, province grain, one PDF per crop.",
            "owner_side": True,
            "pulled_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "http://www.agriinfo.doae.go.th/year63/plant/rortor/ — DOAE's annual "
                      "crop-situation ('รต.') PDF series, one file per crop.",
            "vintage": "ปี 2562 (crop year 2019 CE) on EVERY crop in this file. This is the "
                      "NEWEST vintage this series ever published, not a failed/partial pull: "
                      "year64, year65 and year67 return a clean HTTP 404 ('The requested URL "
                      "/yearNN/ was not found on this server'); year66 exists but holds an "
                      "unrelated document set (farmer-group / project-budget PDFs, not "
                      "crop-production reports); year68 exists but is login-gated. Crawling "
                      ".../plant/rortor/ directly now serves a login form rather than a "
                      "directory listing, so the exact per-crop download URLs are not "
                      "independently re-derivable from this machine any more — these PDFs are "
                      "committed as the retrieved artifact, read from disk from here on "
                      "(network-free, like ingest_real_tape.py's relationship to its source "
                      "xlsx).",
            "lime_uniqueness": "Lime (มะนาว) is in NO OTHER province-grain source this repo "
                               "holds — absent from the DOAE farmer registry "
                               "(platform/data/province_cropland.json, 18 crops, no มะนาว), "
                               "from the planted-area census (source-data/crop_prov_area.json, "
                               "rice/rubber/oilpalm only), from SPAM 2010, and from OCSB "
                               "(sugarcane only). This 2019 รต. PDF is the ONLY province-grain "
                               "lime figure found anywhere across four independent searches — "
                               "which is why a 7-year-old vintage is used rather than leaving "
                               "the board's lime row without a belt.",
            "parsing_note": "Two font traps, both solved in the scratch parse this reuses: (a) "
                            "extract_text(use_text_flow=True, x_tolerance=1) — without it the "
                            "embedded font injects spurious mid-number spaces; (b) this font's "
                            "ำ (sara-am, U+0E33) / า (sara-aa, U+0E32) confusion runs BOTH "
                            "directions across the 11 files — lime drops ำ to a bare space + า, "
                            "longan and lychee do the reverse (า extracted as ำ, corrupting "
                            "names that never had a ำ at all). Folding both characters to one "
                            "token before matching the canonical 77-province list "
                            "(lib.regionmap.REGION) resolves both directions with one map; "
                            "verified no two of the 77 canonical names collide under this fold.",
            "row_sum_vs_printed_total": deltas,
            "row_sum_note": "Every crop's provinces{} sums are cross-checked against the PDF's "
                            "own printed 'รวมทั้งหมด' total; delta_rai is the (small, ≤9 rai "
                            "everywhere in this pull) gap, recorded rather than corrected — it "
                            "is the source's own footing/rounding, not a parse error.",
            "excluded_files": {
                "fruit_longan.pdf": "superseded — older vintage of the same longan series kept "
                                    "as fruit_langan.pdf",
                "fruit_mangosteen.pdf": "superseded — older vintage of the same series kept as "
                                        "fruit_magosteen.pdf",
                "fruit_durian2.pdf": "niche-variety duplicate of fruit_durian.pdf, not used",
                "perennial_coconut3.pdf": "niche-variety duplicate of perennial_coconut.pdf, "
                                         "not used",
            },
            "warnings": warnings,
        },
        "crops": crops,
    }

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    print("wrote %s — %d/%d crops parsed" % (OUT, len(crops), len(CROPS)))
    for key in CROPS:
        if key in crops:
            c = crops[key]
            print("  %-11s %2d provinces  planted=%-9s bearing=%-9s delta=%s rai"
                  % (key, len(c["provinces"]), c["national_planted_rai"],
                     c["national_bearing_rai"], deltas[key]["delta_rai"]))
        else:
            print("  %-11s SKIPPED" % key)
    if warnings:
        print("warnings:")
        for w in warnings:
            print("  -", w)


if __name__ == "__main__":
    main()
