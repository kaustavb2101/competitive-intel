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
BRANCHES = os.path.join(DATA, "branches.json")

# The MERGED full census (official store-locators for Muangthai/Srisawad/Tidlor + Google/Overture
# sample for Heng — already deduped). For 3 of 4 brands this is now the near-COMPLETE network, so
# found ≈ (often ≥) the public headline; Heng alone remains a partial sample.
CENSUS_FILES = ["competitors_census.json"]

# Canonical brand order (matches validate_data.KNOWN_COMPETITOR_BRANDS).
BRANDS = ["Muangthai", "Tidlor", "Srisawad", "Heng"]

# Brands whose `found` count is a near-COMPLETE official store-locator pull (comparable to AutoX's
# own operating-network count) — so their MEASURED points-on-the-ground can be ranked apples-to-apples.
# Heng is deliberately excluded: its locator is Cloudflare-blocked, so its `found` is a Google/Overture
# SAMPLE (lower bound), and ranking AutoX above an undercount would be unsafe (mirrors the never-invent
# rule that keeps uncited Heng out of the IR-count ranking).
LOCATOR_COMPLETE_BRANDS = ["Muangthai", "Srisawad", "Tidlor"]

# EXPECTED nationwide branch counts — CITED real public figures (ESTIMATED-from-public-reports).
# Source per brand recorded in meta.expected_sources. Leave null when no figure can be cited.
EXPECTED = {
    "Muangthai": 8673,   # FY2025 total branches (MTC company IR / kaohoon)
    "Tidlor":    1873,   # FY2025 branches (Ngern Tid Lor IR, tidlorinvestor.com)
    "Srisawad":  1138,   # ~late-2025 branches (SAWAD IR oppday deck)
    "Heng":      None,   # no nationwide branch count cited in our research — do NOT invent
}
EXPECTED_SOURCES = {
    "Muangthai": "MTC FY2025 — 8,673 total branches (opened 518 in 2025); company IR / kaohoon. "
                 "https://investor.muangthaicap.com/en/newsroom/press-releases/144063/",
    "Tidlor":    "Ngern Tid Lor FY2025 — 1,873 branches; company IR / thaipr. "
                 "https://www.tidlorinvestor.com/en/home",
    "Srisawad":  "Srisawad (SAWAD) ~late-2025 — ~1,138 branches; IR oppday deck.",
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


def _autox_branch_count():
    """MEASURED count of AutoX's OWN operating network = number of committed branches
    (branches.json is a top-level array, one object per branch). Returns None if absent
    (stripped sandbox) so the standing block degrades honestly rather than inventing a count."""
    if not os.path.exists(BRANCHES):
        return None
    with open(BRANCHES, encoding="utf-8") as f:
        d = json.load(f)
    return len(d) if isinstance(d, list) else None


def _footprint_measured(autox_n, counts):
    """SECOND, all-MEASURED ranking that complements the IR-count ranking: operators by physical
    POINTS ON THE GROUND — AutoX's own operating network (branches.json) vs each near-complete-locator
    rival's de-duplicated store-locator count (the SAME `found` figures on the brand board). Unlike the
    IR ranking (peers = REPORTED listed-entity counts), every number here is MEASURED, so it answers a
    different question: not "who reports the biggest listed-entity network" but "who has the most doors
    open on the ground". Heng is excluded (its locator is Cloudflare-blocked -> `found` is a lower-bound
    SAMPLE). Returns None when the AutoX count is unavailable."""
    if not autox_n:
        return None
    pool = [{"operator": "AutoX", "points": autox_n,
             "basis": "MEASURED (own operating network, branches.json)"}]
    for b in LOCATOR_COMPLETE_BRANDS:
        pts = counts.get(b)
        if pts:
            pool.append({"operator": b, "points": pts,
                         "basis": "MEASURED (official store-locator, de-duplicated)"})
    order = ["AutoX"] + BRANDS
    ranked = sorted(pool, key=lambda o: (-o["points"], order.index(o["operator"])))
    for i, o in enumerate(ranked, 1):
        o["rank"] = i
    autox_rank = next(o["rank"] for o in ranked if o["operator"] == "AutoX")
    # brands in our set NOT ranked here (no near-complete locator) -> disclosed as lower bounds.
    excluded = [b for b in BRANDS if b not in LOCATOR_COMPLETE_BRANDS]
    return {
        "autox_rank": autox_rank,
        "n_ranked": len(ranked),
        "ranking": ranked,
        "excluded_lowerbound": excluded,
        "basis": "MEASURED FOOTPRINT — physical points on the ground: AutoX's own operating network vs "
                 "each near-complete-locator rival's de-duplicated store-locator count (the same MEASURED "
                 "`found` figures on the brand board). Every number is MEASURED; complements the IR-count "
                 "ranking, which uses peers' REPORTED listed-entity counts.",
        "caveat": "Heng is excluded — its locator is Cloudflare-blocked, so its count is a lower-bound "
                  "SAMPLE, not a near-complete network. A store-locator lists every service point, so for "
                  "a GROUP brand this footprint exceeds the listed-entity IR count (Srisawad's 5,203 "
                  "locator points ≈ 4.6× its 1,138 listed-entity figure). Points on the ground ≠ market "
                  "share.",
    }


def _national_standing(autox_n, counts):
    """Where AutoX sits nationally among the big-4 by BRANCH-NETWORK SIZE — the read the
    found-vs-expected board hides (it never places AutoX in its own peer set). AutoX's size is
    MEASURED (its own committed network); each peer's size is its cited public 'expected' figure
    (REPORTED). Only operators with a cited figure enter the ranking pool — Heng (uncited) is
    listed but excluded from the rank, mirroring the never-invent rule. This is a NETWORK-SIZE
    comparison, NOT market share and NOT the local per-province density read (peer_province.json,
    where clustering makes AutoX read as a modal-3rd) — the two answer different questions and are
    cross-referenced in the caveat. Returns None when the AutoX count is unavailable."""
    if not autox_n:
        return None
    # pool = AutoX (measured own network) + each peer WITH a cited reported figure.
    pool = [{"operator": "AutoX", "branches": autox_n, "basis": "MEASURED (own operating network, branches.json)"}]
    for b in BRANDS:
        exp = EXPECTED.get(b)
        if exp:
            pool.append({"operator": b, "branches": exp, "basis": "REPORTED (cited public IR figure)"})
    # rank by network size desc; deterministic tie-break by the fixed pool order (AutoX first,
    # then census brand order) — matches build_peer_province's tie-break convention.
    order = ["AutoX"] + BRANDS
    ranked = sorted(pool, key=lambda o: (-o["branches"], order.index(o["operator"])))
    for i, o in enumerate(ranked, 1):
        o["rank"] = i
    autox_rank = next(o["rank"] for o in ranked if o["operator"] == "AutoX")
    n_ranked = len(ranked)
    ahead = [o["operator"] for o in ranked if o["rank"] < autox_rank]
    behind = [o["operator"] for o in ranked if o["rank"] > autox_rank]
    # peers named in our brand set that carry NO cited figure -> excluded from the pool, disclosed.
    excluded = [b for b in BRANDS if not EXPECTED.get(b)]
    footprint = _footprint_measured(autox_n, counts)
    # The one-line reframe the exec should read: IR-count basis vs measured-footprint basis can rank
    # AutoX differently, and both are true. Built from the two rankings, never hard-coded.
    insight = None
    if footprint and footprint["autox_rank"] != autox_rank:
        ordw = {1: "largest", 2: "2nd-largest", 3: "3rd-largest", 4: "4th-largest", 5: "5th-largest"}
        insight = (
            "By REPORTED listed-entity branch count AutoX is the %s title-loan network; by MEASURED "
            "store-locator footprint it is %s — a rival's near-complete retail network (which a locator "
            "counts in full, beyond its listed-entity IR figure) overtakes AutoX on points-on-the-ground. "
            "Both are true and answer different questions."
            % (ordw.get(autox_rank, "#%d" % autox_rank),
               ordw.get(footprint["autox_rank"], "#%d" % footprint["autox_rank"]))
        )
    return {
        "autox_branches": autox_n,
        "autox_rank": autox_rank,
        "n_ranked": n_ranked,
        "ranking": ranked,
        "ahead_of_autox": ahead,
        "behind_autox": behind,
        "excluded_uncited": excluded,
        "footprint_measured": footprint,
        "reported_vs_measured_insight": insight,
        "basis": "NETWORK SIZE — AutoX's MEASURED own-network branch count vs each peer's REPORTED "
                 "(cited public IR) branch count. A national footprint-scale read, NOT market share.",
        "caveat": "This ranks operators by total branch-NETWORK size nationally, where AutoX is the "
                  "2nd-largest title-loan network. It is a DIFFERENT question from the per-province "
                  "density board (peer_province.json), where rivals cluster in dense provinces and "
                  "AutoX reads as a modal-3rd locally — national scale and local density tell "
                  "different stories, both true. Heng carries no cited branch count so it is excluded "
                  "from the rank (never invented). Peer figures are listed-ENTITY IR counts; a group's "
                  "full retail footprint can be larger (see the Srisawad note above).",
    }


def build():
    counts, sources = _count_found()
    brands = []
    for b in BRANDS:
        found = counts[b]
        expected = EXPECTED.get(b)
        cov = round(100.0 * found / expected, 1) if (expected and expected > 0) else None
        brands.append({"brand": b, "found": found, "expected": expected, "coverage_pct": cov})

    total_found = sum(counts.values())
    total_expected = sum(v for v in EXPECTED.values() if v)
    overall_cov = round(100.0 * total_found / total_expected, 1) if total_expected else None
    national_standing = _national_standing(_autox_branch_count(), counts)

    meta = {
        "generated_by": "pipeline/build_competitor_coverage.py",
        "source": "found = MEASURED (de-duplicated count from %s); expected = ESTIMATED-from-public-"
                  "reports (cited company IR / annual reports, see expected_sources)."
                  % (", ".join(sources) if sources else "competitor census (none found)"),
        "census_files_used": sources,
        "expected_label": "ESTIMATED-from-public-reports",
        "expected_sources": {b: EXPECTED_SOURCES[b] for b in BRANDS},
        "totals": {"found": total_found, "expected": total_expected or None,
                   "coverage_pct": overall_cov},
        "national_standing": national_standing,
        "caveat": "found now comes from each operator's OFFICIAL store-locator for Muangthai, "
                  "Srisawad and Tidlor (the near-complete network), so coverage_pct is ~100% and "
                  "can exceed 100% because a locator lists every service point / sub-branch beyond "
                  "the company's headline branch count. Heng is the ONE exception — still a Google/"
                  "Overture SAMPLE (its locator is behind a Cloudflare challenge), so Heng's count is "
                  "a genuine lower bound. Read coverage as a data-completeness flag, not market share.",
        "note": "expected counts are CITED real figures (not modelled); Heng expected is null because "
                "no nationwide branch count was cited in our research — never invented. coverage_pct "
                ">100% for the official-locator brands is expected, not an error: a locator lists every "
                "service point, and for a GROUP brand it covers the whole retail network while the IR "
                "'branches' figure counts only the LISTED ENTITY. Srisawad is the clearest case — the "
                "sawad.co.th locator returns 5,203 measured points vs the 1,138 listed-entity IR "
                "figure, i.e. the SAWAD group's retail footprint is ~4.6x its reported branch count.",
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
    ns = obj["meta"].get("national_standing")
    if ns:
        print("  national standing (by network size): AutoX #%d of %d — %s"
              % (ns["autox_rank"], ns["n_ranked"],
                 " > ".join("%s %s" % (o["operator"], "{:,}".format(o["branches"])) for o in ns["ranking"])))
        fp = ns.get("footprint_measured")
        if fp:
            print("  measured footprint (points on the ground): AutoX #%d of %d — %s"
                  % (fp["autox_rank"], fp["n_ranked"],
                     " > ".join("%s %s" % (o["operator"], "{:,}".format(o["points"])) for o in fp["ranking"])))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="competitor-census coverage QA (found vs expected)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
