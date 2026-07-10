#!/usr/bin/env python3
"""
build_competitor_coverage.py — competitor-census COVERAGE QA (found vs expected)
===============================================================================
Objective #2 (WHERE TO EXPAND). Our competitor census (competitors_national.json,
a Google-Places Text-Search pull, optionally + competitors_overture.json) is a
deliberate LOWER BOUND — Places caps ~60 results/query/province and we do not
hit every brand in every district. The strategy team must NOT read the measured
counts as a registry. This step makes the undercount EXPLICIT and honest.

For each known competitor brand it emits:
  found        MEASURED  — count of that brand's locations in our census
                          (de-duplicated by place_id across the input files).
  expected     ESTIMATED — the brand's publicly-reported nationwide branch count,
                          a CITED real figure from docs/RESEARCH_DIGEST.md (company
                          IR / annual reports). null when no figure can be cited
                          (we NEVER invent one).
  coverage_pct DERIVED   — round(100 * found / expected, 1), or null when expected
                          is null.

EXPECTED FIGURES — cited, real, ESTIMATED-from-public-reports (see EXPECTED below
and docs/RESEARCH_DIGEST.md §B "Competitors — listed peers' 2025 scoreboard"):
  Muangthai (MTC) 8,673  — FY2025, opened 518 new branches in 2025 (company IR / kaohoon)
  Tidlor          1,873  — FY2025 (thaipr / company IR, tidlorinvestor.com)
  Srisawad        1,138  — late 2025 (SAWAD IR oppday deck)
  Heng             null  — no nationwide branch count cited in our research; left null

Output: platform/data/competitor_coverage.json
  { meta:{...provenance + citation...}, brands:[{brand, found, expected, coverage_pct}, ...] }

Deterministic + network-free (reads only committed census files).
    python3 build_competitor_coverage.py            # write the JSON
    python3 build_competitor_coverage.py --check     # verify byte-for-byte reproduce
"""
import os, json, argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
OUT  = os.path.join(DATA, "competitor_coverage.json")

# The MERGED full census (official store-locators for Muangthai/Srisawad/Tidlor + Google/Overture
# sample for Heng — already deduped). For 3 of 4 brands this is now the near-COMPLETE network, so
# found ≈ (often ≥) the public headline; Heng alone remains a partial sample.
CENSUS_FILES = ["competitors_census.json"]

# Canonical brand order (matches validate_data.KNOWN_COMPETITOR_BRANDS).
BRANDS = ["Muangthai", "Tidlor", "Srisawad", "Heng"]

# EXPECTED nationwide branch counts — CITED real public figures (ESTIMATED-from-public-reports).
# Source per brand recorded in meta.expected_sources. Leave null when no figure can be cited.
EXPECTED = {
    "Muangthai": 8673,   # FY2025 total branches (MTC company IR / kaohoon)
    "Tidlor":    1873,   # FY2025 branches (Ngern Tid Lor IR, tidlorinvestor.com)
    "Srisawad":  None,   # IR figure (1,138, oppday deck) counts the LISTED ENTITY only while our
                         # census measures the whole SAWAD-group locator network (~4.6x larger) —
                         # scope-mismatched denominators produced a nonsense 457% / 141% coverage
                         # (committee finding #4, 2026-07-10). No cited GROUP figure => null.
    "Heng":      None,   # no nationwide branch count cited in our research — do NOT invent
}
EXPECTED_SOURCES = {
    "Muangthai": "MTC FY2025 — 8,673 total branches (opened 518 in 2025); company IR / kaohoon. "
                 "https://investor.muangthaicap.com/en/newsroom/press-releases/144063/",
    "Tidlor":    "Ngern Tid Lor FY2025 — 1,873 branches; company IR / thaipr. "
                 "https://www.tidlorinvestor.com/en/home",
    "Srisawad":  "IR cites ~1,138 listed-entity branches (oppday deck) but the sawad.co.th locator "
                 "measures the whole group network (5,203 points) — scope mismatch, so expected is "
                 "null until a cited GROUP figure exists (never invented).",
    "Heng":      "No nationwide branch count cited in docs/RESEARCH_DIGEST.md — left null (not invented).",
}


def _count_found():
    """De-duplicated MEASURED per-brand counts across the census files (by place_id; falls
    back to brand+rounded-lat/lng when a record has no place_id). Returns (counts, sources)."""
    seen = set()
    counts = {b: 0 for b in BRANDS}
    sources = []
    for rel in CENSUS_FILES:
        path = os.path.join(DATA, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        items = d.get("items") if isinstance(d, dict) else None
        if not isinstance(items, list):
            continue
        sources.append(rel)
        for it in items:
            if not isinstance(it, dict):
                continue
            br = it.get("brand")
            if br not in counts:
                continue
            pid = it.get("place_id")
            if pid:
                key = ("pid", pid)
            else:
                lat, lng = it.get("lat"), it.get("lng")
                key = ("geo", br, round(lat, 5) if isinstance(lat, (int, float)) else lat,
                       round(lng, 5) if isinstance(lng, (int, float)) else lng)
            if key in seen:
                continue
            seen.add(key)
            counts[br] += 1
    return counts, sources


def build():
    counts, sources = _count_found()
    brands = []
    for b in BRANDS:
        found = counts[b]
        expected = EXPECTED.get(b)
        cov = round(100.0 * found / expected, 1) if (expected and expected > 0) else None
        brands.append({"brand": b, "found": found, "expected": expected, "coverage_pct": cov})

    total_found = sum(counts.values())
    # coverage is only meaningful where found and expected measure the SAME network — sum both
    # sides over the comparable brands only (a full-census found over a partial expected read 141%).
    comparable = [b for b in BRANDS if EXPECTED.get(b)]
    comparable_found = sum(counts[b] for b in comparable)
    total_expected = sum(EXPECTED[b] for b in comparable)
    overall_cov = round(100.0 * comparable_found / total_expected, 1) if total_expected else None

    meta = {
        "generated_by": "pipeline/build_competitor_coverage.py",
        "source": "found = MEASURED (de-duplicated count from %s); expected = ESTIMATED-from-public-"
                  "reports (cited company IR / annual reports, see expected_sources)."
                  % (", ".join(sources) if sources else "competitor census (none found)"),
        "census_files_used": sources,
        "expected_label": "ESTIMATED-from-public-reports",
        "expected_sources": {b: EXPECTED_SOURCES[b] for b in BRANDS},
        "totals": {"found": total_found, "expected": total_expected or None,
                   "coverage_pct": overall_cov,
                   "comparable_found": comparable_found, "comparable_brands": comparable},
        "caveat": "found now comes from each operator's OFFICIAL store-locator for Muangthai, "
                  "Srisawad and Tidlor (the near-complete network), so coverage_pct is ~100% and "
                  "can exceed 100% because a locator lists every service point / sub-branch beyond "
                  "the company's headline branch count. Heng is the ONE exception — still a Google/"
                  "Overture SAMPLE (its locator is behind a Cloudflare challenge), so Heng's count is "
                  "a genuine lower bound. Read coverage as a data-completeness flag, not market share.",
        "note": "expected counts are CITED real figures (not modelled); Heng expected is null because "
                "no nationwide branch count was cited in our research — never invented. coverage_pct "
                "can exceed 100% for an official-locator brand (a locator lists every service point beyond "
                "the IR headline). Srisawad's expected is null: its IR figure (1,138) counts the listed "
                "entity only while the sawad.co.th locator measures the whole group (5,203 points, "
                "~4.6x) — scope-mismatched denominators are excluded rather than shown as 457%. "
                "totals.coverage_pct is computed over comparable_brands only.",
    }
    return {"meta": meta, "brands": brands}


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print("DRIFT: %s" % os.path.relpath(OUT, REPO)); return 1
        print("OK: competitor_coverage.json reproduces (%d brands)" % len(obj["brands"]))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %d brands -> platform/data/competitor_coverage.json" % len(obj["brands"]))
    for b in obj["brands"]:
        exp = b["expected"]
        cov = b["coverage_pct"]
        print("  %-10s found=%-5d expected=%-7s coverage=%s"
              % (b["brand"], b["found"], (exp if exp is not None else "n/a"),
                 ("%.1f%%" % cov) if cov is not None else "n/a"))
    t = obj["meta"]["totals"]
    print("  TOTAL      found=%-5d expected=%-7s coverage=%s"
          % (t["found"], (t["expected"] if t["expected"] is not None else "n/a"),
             ("%.1f%%" % t["coverage_pct"]) if t["coverage_pct"] is not None else "n/a"))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="competitor-census coverage QA (found vs expected)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
