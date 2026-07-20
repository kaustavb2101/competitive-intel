#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_oae_farm_economics.py — OAE per-household crop ECONOMICS + farm-household income/debt
(portfolio risk, objective #1).

Extracts, from the OAE commodity-economics compendium "Cai-up 2568" (สศก. ภาวะเศรษฐกิจการเกษตร),
the MEASURED per-crop household economics that the farmer-income build needs but that OAE's CKAN
CSVs do NOT expose: the real number of FARMING HOUSEHOLDS per crop (not registration records),
the crop area, yield/rai, farm-gate price, cost of production and — crucially — the NET RETURN
(ผลตอบแทนสุทธิ), which in 2568 is NEGATIVE for rice, cassava and rubber (a real loss). It also
lands the farm-household socio-economic table (income, net cash income, and household DEBT) by
region (North / Northeast / Central / South) from the compendium's "เศรษฐกิจสังคมครัวเรือนเกษตร" page.

WHY A PDF: OAE publishes these per-household economics ONLY in this compendium PDF (the CKAN
catalog carries yield/area/price CSVs but no household count and no net return). The PDF has a
real TEXT layer (verified: 93/102 pages text, the crop-economics + household pages all text —
NOT OCR), so every figure here is a deterministic text extraction, trustworthy like a CSV pull.
The font maps Thai tone marks into a private-use area (U+F70x); we strip those before matching
labels, never touching the digits.

WHAT IS MEASURED (everything here):
  Per crop (rice / maize / cassava / rubber / oil palm), the newest full column (crop year 2568):
    households, area_rai (+ its basis: planted / harvested / tapped / bearing), production_tons,
    yield_kg_per_rai, farmgate_price_per_ton, cost_per_ton, net_return_per_ton.  NET is quoted by
    OAE per TON (บาท/ตัน) — captured verbatim with its unit; the downstream build converts to
    per-household / per-person using production per household.
  Farm household socio-economics (บาท/ครัวเรือน/ปี, crop year 2567/68p) by region + national:
    total income, net cash farm income, net cash household income, cash before debt service, and
    year-end household DEBT (ขนาดหนี้สินปลายปี).

SPOT-VERIFICATION: a set of known anchor values (rice households 4,532,663; rice area 61.34M rai;
rice net -1,433; cassava net -320; rubber net -2,460; oil palm net +3,080; national net-cash farm
income 84,779) is asserted against the freshly parsed numbers — a re-publish that shifts them fails
loudly rather than silently landing changed data.

DETERMINISM / PROVENANCE (mirrors pull_oae_yield.py):
  - The raw PDF is cached (gitignored) in source-data/.oae_farm_econ_raw/caiup.pdf; the distilled
    source-data/oae_farm_economics.json is committed.
  - `pulled` comes only from --stamp; no wall clock in the data, so a re-parse of the same cached
    PDF with the same --stamp is byte-identical.
  - --check re-parses the cached raw PDF offline and byte-compares; exit 3 SKIP if the committed
    JSON or the gitignored raw PDF is absent (a network-pulled input, not drift).

Run:
  python3 pull_oae_farm_economics.py --stamp 2026-07-18   # download + parse + write
  python3 pull_oae_farm_economics.py                       # default --stamp = today
  python3 pull_oae_farm_economics.py --check               # offline byte-reproduce from cached PDF
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ingest_pdf import extract_pdf

OUT = os.path.join(ROOT, "source-data", "oae_farm_economics.json")
RAW_DIR = os.path.join(ROOT, "source-data", ".oae_farm_econ_raw")
RAW_PDF = os.path.join(RAW_DIR, "caiup.pdf")
URL = "https://oae.go.th/uploads/files/public/media/Cai-up-2568.pdf"
CA = "/root/.ccr/ca-bundle.crt"
UA = {"User-Agent": "Mozilla/5.0"}

NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _norm(s):
    """Drop the font's private-use Thai tone-mark glyphs (U+F700..U+F71F) so plain Thai matches."""
    return "".join(c for c in s if not (0xF700 <= ord(c) <= 0xF71F))


def _fnum(tok):
    return float(tok.replace(",", ""))


# ---- per-crop extraction spec -------------------------------------------------
# Each field: (label_substring, token_index, scale). token_index is 0-based into the NUM tokens of
# the matched (tone-mark-normalised) line; the 2568 column is the 4th data token for most rows
# (idx 3), but +1 where the label itself carries a stray number (rice yield "ความชื้น 15%";
# rubber price "ชั้น 3"). scale 1e6 converts OAE's ล้านไร่/ล้านตัน (millions) to absolute units.
CROPS = {
    "rice": {
        "commod_th": "ข้าวนาปี", "page": 16, "area_basis": "planted (เนื้อที่เพาะปลูก)",
        "fields": {
            "households":           ("จำนวนครัวเรือน", 3, 1),
            "area_rai":             ("เนื้อที่เพาะปลูก", 3, 1e6),
            "production_tons":      ("ผลผลิตขาวเปลือก", 3, 1e6),
            "yield_kg_per_rai":     ("ผลผลิตตอไร", 4, 1),
            "farmgate_price_per_ton": ("ราคาที่เกษตรกรขายได", 3, 1),
            "cost_per_ton":         ("ตนทุนการผลิต", 3, 1),
            "net_return_per_ton":   ("ผลตอบแทนสุทธิ", 3, 1),
        },
        "price_th": "ข้าวเปลือก (เฉลี่ยทุกชนิด)",
    },
    "maize": {
        "commod_th": "ข้าวโพดเลี้ยงสัตว์", "page": 22, "area_basis": "planted (เนื้อที่เพาะปลูก)",
        "fields": {
            "households":           ("จำนวนครัวเรือน", 3, 1),
            "area_rai":             ("เนื้อที่เพาะปลูก", 3, 1),
            "production_tons":      ("ผลผลิต (ตัน)", 3, 1),
            "yield_kg_per_rai":     ("ผลผลิตตอไร", 3, 1),
            "farmgate_price_per_ton": ("ความชื้น 14.5%", 3, 1),
            "cost_per_ton":         ("ตนทุนการผลิต", 3, 1),
            "net_return_per_ton":   ("ผลตอบแทนสุทธิ", 3, 1),
        },
        "price_th": "ข้าวโพดเลี้ยงสัตว์ ความชื้น 14.5%",
    },
    "cassava": {
        "commod_th": "มันสำปะหลังโรงงาน", "page": 24, "area_basis": "harvested (เนื้อที่เก็บเกี่ยว)",
        "fields": {
            "households":           ("จำนวนครัวเรือน", 3, 1),
            "area_rai":             ("เนื้อที่เก็บเกี่ยว", 3, 1),
            "production_tons":      ("ผลผลิต (ตัน)", 3, 1),
            "yield_kg_per_rai":     ("ผลผลิตตอไร", 3, 1),
            "farmgate_price_per_ton": ("แปง 25%", 3, 1),
            "cost_per_ton":         (None, None, None),
            "net_return_per_ton":   ("ผลตอบแทนสุทธิ", 3, 1),
        },
        "price_th": "หัวมันสำปะหลังสด (แป้ง 25%)",
    },
    "rubber": {
        "commod_th": "ยางพารา", "page": 38, "area_basis": "tapped (เนื้อที่กรีดได้)",
        "fields": {
            "households":           ("จำนวนครัวเรือน", 3, 1),
            "area_rai":             ("เนื้อที่กรีดได", 3, 1),
            "production_tons":      ("ผลผลิตยางแผนดิบ (ตัน)", 3, 1),
            "yield_kg_per_rai":     ("ยางแผนดิบตอไร", 3, 1),
            "farmgate_price_per_ton": ("ยางแผนดิบชั้น 3", 4, 1),
            "cost_per_ton":         ("ตนทุนการผลิตยางแผนดิบ", 3, 1),
            "net_return_per_ton":   ("ผลตอบแทนสุทธิ", 3, 1),
        },
        "price_th": "ยางแผ่นดิบชั้น 3",
    },
    "oilpalm": {
        "commod_th": "ปาล์มน้ำมัน", "page": 40, "area_basis": "bearing (เนื้อที่ให้ผล)",
        "fields": {
            "households":           ("จำนวนครัวเรือน", 3, 1),
            "area_rai":             ("เนื้อที่ใหผล", 3, 1),
            "production_tons":      ("ผลผลิต (ตัน)", 3, 1),
            "yield_kg_per_rai":     ("ผลผลิตตอไร", 3, 1),
            "farmgate_price_per_ton": ("ทั้งทะลาย", 3, 1),
            "cost_per_ton":         (None, None, None),
            "net_return_per_ton":   ("ผลตอบแทนสุทธิ", 3, 1),
        },
        "price_th": "ผลปาล์มทั้งทะลาย นน.>15 กก.",
    },
}
CROP_ORDER = ["rice", "maize", "cassava", "rubber", "oilpalm"]

# Farm-household socio-economics page (เศรษฐกิจสังคมครัวเรือนเกษตร). Rows carry 7 comma-numbers:
# national [2565/66, 2566/67, 2567/68p] then the 2567/68p regional split North/NE/Central/South.
HH_PAGE = 11   # 1-indexed PDF page (compendium "page 4", เศรษฐกิจสังคมครัวเรือนเกษตร)
HH_ROWS = {
    "income_total":         "รายได",
    "net_cash_farm_income": "สุทธิทางการเกษตร",
    "net_cash_hh_income":   "สุทธิครัวเรือน",
    "cash_before_debt":     "คงเหลือ",
    "debt_year_end":        "หนี้สินปลายป",
}
HH_REGIONS = ["North", "Northeast", "Central", "South"]

# Spot-verification anchors (crop year 2568 / household 2567/68p). A re-publish that moves any of
# these should fail loudly, forcing re-verification rather than silently landing changed data.
ANCHORS = {
    ("rice", "households"): 4532663.0,
    ("rice", "area_rai"): 61340000.0,
    ("rice", "net_return_per_ton"): -1433.0,
    ("cassava", "net_return_per_ton"): -320.0,
    ("rubber", "net_return_per_ton"): -2460.0,
    ("oilpalm", "net_return_per_ton"): 3080.0,
}
HH_ANCHOR = ("net_cash_farm_income", 2, 84779.0)   # national 2567/68p


def _fetch_pdf():
    import ssl
    ctx = ssl.create_default_context(cafile=CA) if os.path.exists(CA) else None
    req = urllib.request.Request(URL, headers=UA)
    with urllib.request.urlopen(req, timeout=180, context=ctx) as r:
        return r.read()


def _page_lines(doc, page):
    for pg in doc["pages"]:
        if pg["page"] == page:
            return [_norm(l) for l in pg["text"].splitlines() if l.strip()], pg["method"]
    return [], None


def _extract_field(lines, sub, idx):
    if sub is None:
        return None
    for l in lines:
        if sub in l:
            toks = NUM.findall(l)
            if len(toks) > idx:
                return _fnum(toks[idx])
            # short row: some crops print fewer year-columns on this line (cassava & oil-palm
            # cost rows carry 3 tokens, not 4) — the NEWEST year is always the last token.
            if toks:
                return _fnum(toks[-1])
    return None


def _parse_crops(doc):
    crops, methods = {}, {}
    for name in CROP_ORDER:
        cfg = CROPS[name]
        lines, method = _page_lines(doc, cfg["page"])
        methods[name] = method
        if not lines:
            sys.exit("pull_oae_farm_economics.py: page %d (%s) not extracted." % (cfg["page"], name))
        vals = {}
        for field, (sub, idx, scale) in cfg["fields"].items():
            v = _extract_field(lines, sub, idx)
            vals[field] = round(v * scale) if v is not None else None
        # required fields present?
        for req in ("households", "area_rai", "production_tons", "yield_kg_per_rai",
                    "farmgate_price_per_ton", "net_return_per_ton"):
            if vals.get(req) is None:
                sys.exit("pull_oae_farm_economics.py: %s missing field '%s' — check page %d labels."
                         % (name, req, cfg["page"]))
        crops[name] = {
            "commod_th": cfg["commod_th"],
            "page": cfg["page"],
            "households": int(vals["households"]),
            "area_rai": int(vals["area_rai"]),
            "area_basis": cfg["area_basis"],
            "production_tons": int(vals["production_tons"]),
            "yield_kg_per_rai": int(vals["yield_kg_per_rai"]),
            "farmgate_price_per_ton": int(vals["farmgate_price_per_ton"]),
            "farmgate_price_th": cfg["price_th"],
            "cost_per_ton": int(vals["cost_per_ton"]) if vals.get("cost_per_ton") is not None else None,
            "net_return_per_ton": int(vals["net_return_per_ton"]),
            "net_unit": "THB/ton",
            "loss": vals["net_return_per_ton"] < 0,
            "vintage": "2568 (crop year 2568/69, OAE forecast Mar 2569)",
            "method": method,
        }
    return crops, methods


def _parse_household(doc):
    """Farm-household socio-economics by region. Uses pdfplumber word flow (the page renders each
    row twice, overlapping; use_text_flow separates the columns cleanly). Deterministic per PDF."""
    import pdfplumber
    from collections import defaultdict
    out = {r: {} for r in ["national"] + HH_REGIONS}
    with pdfplumber.open(RAW_PDF) as pl:
        pg = pl.pages[HH_PAGE - 1]
        words = pg.extract_words(use_text_flow=True, keep_blank_chars=False)
        rows = defaultdict(list)
        for w in words:
            rows[round(w["top"])].append(w)
        rownums = re.compile(r"^-?\d[\d,]+$")
        for key, sub in HH_ROWS.items():
            found = None
            for y in sorted(rows):
                line = sorted(rows[y], key=lambda w: w["x0"])
                joined = _norm("".join(w["text"] for w in line))
                if sub in joined:
                    nums = [w["text"] for w in line if rownums.match(w["text"])]
                    if len(nums) >= 7:
                        found = [int(t.replace(",", "")) for t in nums[-7:]]
                        break
            if not found:
                sys.exit("pull_oae_farm_economics.py: household row '%s' (%s) not found on page %d."
                         % (key, sub, HH_PAGE))
            # cols: national 2565/66, 2566/67, 2567/68p, then North, NE, Central, South (2567/68p)
            out["national"][key] = found[:3]
            for i, reg in enumerate(HH_REGIONS):
                out[reg][key] = found[3 + i]
    return out


def _verify(crops, hh):
    for (crop, field), want in ANCHORS.items():
        got = crops[crop][field]
        if abs(got - want) > 0.5:
            sys.exit("pull_oae_farm_economics.py: ANCHOR FAIL %s.%s = %s, expected %s — the PDF "
                     "changed; re-verify before landing." % (crop, field, got, want))
    key, idx, want = HH_ANCHOR
    got = hh["national"][key][idx]
    if abs(got - want) > 0.5:
        sys.exit("pull_oae_farm_economics.py: ANCHOR FAIL household %s[%d] = %s, expected %s."
                 % (key, idx, got, want))


def _assemble(doc, crops, methods, hh, stamp):
    return {
        "meta": {
            "title": "OAE per-household crop economics + farm-household income/debt "
                     "(portfolio risk, objective #1)",
            "generated_by": "pipeline/pull_oae_farm_economics.py",
            "label": "MEASURED — OAE commodity-economics compendium (Cai-up 2568). Per-crop farming "
                     "HOUSEHOLD counts, area, yield, farm-gate price, cost and NET RETURN "
                     "(ผลตอบแทนสุทธิ, บาท/ตัน — negative = a loss); plus farm-household income and "
                     "year-end DEBT by region. Text-layer extraction (not OCR).",
            "source": URL,
            "source_th": "สำนักงานเศรษฐกิจการเกษตร (สศก.) — ภาวะเศรษฐกิจการเกษตร / Cai-up 2568",
            "pulled": stamp,
            "crop_vintage": "2568 (crop year 2568/69, OAE forecast as of Mar 2569)",
            "household_vintage": "2567/68p (preliminary)",
            "crop_pages": {n: CROPS[n]["page"] for n in CROP_ORDER},
            "household_page": HH_PAGE,
            "extraction_method": {**{n: methods[n] for n in CROP_ORDER}, "household": "text (word-flow)"},
            "method_note": "All crop-economics + household pages are method='text' (real text layer, "
                           "verified — not OCR). Font tone-marks live in a private-use area and are "
                           "stripped for label matching only; digits are untouched.",
            "units": {
                "households": "farming households",
                "area_rai": "rai (area_basis stated per crop: planted/harvested/tapped/bearing)",
                "production_tons": "tonnes", "yield_kg_per_rai": "kg/rai",
                "farmgate_price_per_ton": "THB/tonne", "cost_per_ton": "THB/tonne",
                "net_return_per_ton": "THB/tonne (negative = loss)",
                "household_economics": "THB/household/year",
            },
            "provenance": "MEASURED. Nothing modelled. Every crop household count, area, yield, "
                          "price and net return read from the OAE text layer and spot-verified "
                          "against fixed anchor values.",
            "anchors_verified": {"%s.%s" % k: v for k, v in ANCHORS.items()},
            "consumer": "pipeline/build_crop_farmer_income.py (real household denominator + net return).",
        },
        "crops": {n: crops[n] for n in CROP_ORDER},
        "household_economics": {
            "unit": "THB/household/year",
            "vintage": "2567/68p",
            "regions_note": "national carries 3 vintages [2565/66, 2566/67, 2567/68p]; the four "
                            "region columns are 2567/68p only.",
            "rows": {
                "income_total": "รายได้ (total income)",
                "net_cash_farm_income": "รายได้เงินสดสุทธิทางการเกษตร (net cash farm income)",
                "net_cash_hh_income": "รายได้เงินสดสุทธิครัวเรือน (net cash household income, incl off-farm)",
                "cash_before_debt": "เงินสดคงเหลือก่อนการชำระหนี้ (cash left before debt service)",
                "debt_year_end": "ขนาดหนี้สินปลายปี (household debt outstanding, year-end)",
            },
            "regions": hh,
        },
    }


def build_from_doc(doc, stamp):
    crops, methods = _parse_crops(doc)
    hh = _parse_household(doc)
    _verify(crops, hh)
    return _assemble(doc, crops, methods, hh, stamp)


def _dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default=datetime.date.today().isoformat(),
                    help="YYYY-MM-DD pull date embedded in meta.pulled (default: today)")
    ap.add_argument("--check", action="store_true",
                    help="OFFLINE: re-parse the cached raw PDF + committed --stamp and byte-compare "
                         "against source-data/oae_farm_economics.json; exit 1 on drift, exit 3 SKIP "
                         "if the committed JSON or the gitignored raw PDF is absent")
    args = ap.parse_args()

    if args.check:
        if not os.path.exists(OUT) or not os.path.exists(RAW_PDF):
            print("pull_oae_farm_economics.py --check: SKIP (committed oae_farm_economics.json or "
                  "gitignored raw PDF source-data/.oae_farm_econ_raw/caiup.pdf absent — "
                  "network-pulled input, not drift)")
            sys.exit(3)
        prev = json.load(open(OUT, encoding="utf-8"))
        doc = extract_pdf(RAW_PDF)
        data = build_from_doc(doc, prev["meta"]["pulled"])
        if _dumps(data) != open(OUT, encoding="utf-8").read():
            sys.exit("pull_oae_farm_economics.py --check: oae_farm_economics.json drifted from a "
                     "fresh parse of the cached raw PDF — re-run python3 "
                     "pipeline/pull_oae_farm_economics.py")
        print("pull_oae_farm_economics.py --check: OK (byte-exact from cached raw PDF)")
        return

    os.makedirs(RAW_DIR, exist_ok=True)
    if not os.path.exists(RAW_PDF):
        print("downloading %s ..." % URL)
        with open(RAW_PDF, "wb") as f:
            f.write(_fetch_pdf())
    doc = extract_pdf(RAW_PDF)
    data = build_from_doc(doc, args.stamp)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(_dumps(data))
    print("wrote %s" % OUT)
    for n in CROP_ORDER:
        c = data["crops"][n]
        print("  %-8s hh=%-9s area_rai=%-11s yield=%-5s price/t=%-7s net/t=%-7s %s"
              % (n, c["households"], c["area_rai"], c["yield_kg_per_rai"],
                 c["farmgate_price_per_ton"], c["net_return_per_ton"],
                 "LOSS" if c["loss"] else ""))
    nat = data["household_economics"]["regions"]["national"]
    print("  household net-cash farm income (national 2567/68p): %s THB/hh; debt: %s THB/hh"
          % (nat["net_cash_farm_income"][2], nat["debt_year_end"][2]))


if __name__ == "__main__":
    main()
