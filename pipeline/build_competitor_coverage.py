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
  Heng              450  — 30 Jun 2026 (Heng SET filings; branches 1,018→743→450, the ONE
                          contracting listed peer — RESEARCH_DIGEST.md §B). Now cited AND
                          confirmed by its own official locator (see below).

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
TAPE = os.path.join(DATA, "tape_real.json")

# The MERGED full census (official store-locators for ALL four big brands — Muangthai/Srisawad/Tidlor
# from their web locators, Heng province-walked from hengleasing.com via pull_heng_locator.py from a
# Thai IP, already deduped). For all 4 brands this is now the near-COMPLETE network, so
# found ≈ (often ≥) the public headline; no sampled layer remains (competitors_census.json meta).
CENSUS_FILES = ["competitors_census.json"]

# Canonical brand order (matches validate_data.KNOWN_COMPETITOR_BRANDS).
BRANDS = ["Muangthai", "Tidlor", "Srisawad", "Heng"]

# Brands whose `found` count is a near-COMPLETE official store-locator pull (comparable to AutoX's
# own operating-network count) — so their MEASURED points-on-the-ground can be ranked apples-to-apples.
# Heng is now included: the earlier Cloudflare-blocked Google/Overture SAMPLE was REPLACED by an
# official province-walk of hengleasing.com (pull_heng_locator.py, from a Thai IP), so its `found`
# (450) is now a near-complete official locator — and it matches Heng's cited SET-filing count (450),
# confirming completeness. All four rivals are on the same official-locator footing.
LOCATOR_COMPLETE_BRANDS = ["Muangthai", "Srisawad", "Tidlor", "Heng"]

# EXPECTED nationwide branch counts — CITED real public figures (ESTIMATED-from-public-reports).
# Source per brand recorded in meta.expected_sources. Leave null when no figure can be cited.
EXPECTED = {
    "Muangthai": 8673,   # FY2025 total branches (MTC company IR / kaohoon)
    "Tidlor":    1873,   # FY2025 branches (Ngern Tid Lor IR, tidlorinvestor.com)
    "Srisawad":  1138,   # ~late-2025 branches (SAWAD IR oppday deck)
    "Heng":      450,    # 30 Jun 2026 branches (Heng SET filings; 1,018→743→450, contracting) —
                         # cited AND confirmed by its own official locator (450 measured points)
}
EXPECTED_SOURCES = {
    "Muangthai": "MTC FY2025 — 8,673 total branches (opened 518 in 2025); company IR / kaohoon. "
                 "https://investor.muangthaicap.com/en/newsroom/press-releases/144063/",
    "Tidlor":    "Ngern Tid Lor FY2025 — 1,873 branches; company IR / thaipr. "
                 "https://www.tidlorinvestor.com/en/home",
    "Srisawad":  "Srisawad (SAWAD) ~late-2025 — ~1,138 branches; IR oppday deck.",
    "Heng":      "Heng Leasing & Capital (HENG) — 450 branches as of 30 Jun 2026, per its own SET "
                 "filings (branch count 1,018→743→450 over Dec 2024→Dec 2025→Jun 2026, the one "
                 "contracting listed title-lender); docs/RESEARCH_DIGEST.md §B. Confirmed by the "
                 "official hengleasing.com locator (450 measured points).",
}

# REPORTED peer SCALE + EXPANSION PACE — the direction behind the static branch counts, from the
# operators' own FY2025 / 2025 IR (docs/RESEARCH_DIGEST.md §B). Objective #2: AutoX is CONSOLIDATING
# its ~2,015-branch network while the #1 rival keeps adding branches into the same districts — a
# margin-erosion-on-the-existing-network read the static count alone can't show. Every figure is a
# CITED public number; leave a field None when no figure is cited (never inferred). `net_adds_yr` is
# reported only where the operator disclosed a branch-count delta (MTC alone), so the pace column is
# populated only for MTC — the others stay honestly blank rather than back-computed.
PEER_FINANCIALS = {
    # loan_book_bn = total loans outstanding, ฿bn; net_adds_yr = branches opened net in the stated
    # year; prior_year_branches = current cited count − net_adds_yr (arithmetic on cited figures, MTC
    # only); book_yoy_pct = reported YoY growth of the book; asof = the book's observation label.
    "Muangthai": {"loan_book_bn": 183.222, "net_adds_yr": 518, "net_adds_year": 2025,
                  "prior_year_branches": 8155, "book_yoy_pct": None, "book_asof": "FY2025",
                  "growth_target_pct": "10–15"},
    "Tidlor":    {"loan_book_bn": 109.586, "net_adds_yr": None, "net_adds_year": 2025,
                  "prior_year_branches": None, "book_yoy_pct": 5.4, "book_asof": "FY2025",
                  "growth_target_pct": None},
    "Srisawad":  {"loan_book_bn": 93.155, "net_adds_yr": None, "net_adds_year": 2025,
                  "prior_year_branches": None, "book_yoy_pct": None, "book_asof": "30 Jun 2025",
                  "growth_target_pct": None},
    "Heng":      None,   # cited branch count (450) now in EXPECTED, but its book is a GROSS
                         # hire-purchase/leasing receivable (฿8,002.8m, 30 Jun 2026) on a different
                         # basis from the others' total loans OUTSTANDING — omitted from the
                         # apples-to-apples book-per-branch read (not invented, and not mixed-basis)
}
PEER_FINANCIALS_SOURCES = {
    "Muangthai": "MTC FY2025 — loan portfolio ฿183,222m, opened 518 branches in 2025 (→ 8,673 "
                 "total, i.e. 8,155 prior-year), targets 10–15% portfolio growth; company IR / kaohoon. "
                 "https://www.kaohooninternational.com/markets/577190",
    "Tidlor":    "Ngern Tid Lor FY2025 — outstanding loans ฿109,586m (+5.4% YoY); thaipr / company IR. "
                 "https://www.thaipr.net/en/finance_en/3695435",
    "Srisawad":  "Srisawad (SAWAD) — total loans outstanding ฿93,155m as of 30 Jun 2025; IR oppday deck. "
                 "https://sawad.listedcompany.com/misc/presentation/20250523-sawad-oppday-1q2025.pdf",
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


def _autox_book_bn():
    """MEASURED AutoX outstanding loan book in ฿bn = tape_real.json bucket_ladder.book_total.os_sum
    (the whole-book outstanding total from the real loan-level export — comparable in kind to a peer's
    REPORTED total-loans-outstanding IR figure). Returns None if the tape or the field is absent
    (stripped sandbox) so the intensity block degrades honestly rather than inventing a book."""
    if not os.path.exists(TAPE):
        return None
    with open(TAPE, encoding="utf-8") as f:
        d = json.load(f)
    try:
        os_sum = d["bucket_ladder"]["book_total"]["os_sum"]
    except (KeyError, TypeError):
        return None
    if not isinstance(os_sum, (int, float)) or os_sum <= 0:
        return None
    return round(os_sum / 1e9, 3)


def _book_intensity(autox_n, autox_book_bn):
    """BOOK PER BRANCH — outstanding loan book ÷ branch-network size, for AutoX + each peer that
    carries a cited book. It reframes the raw book-scale chain (peers' bigger books) as a STRUCTURAL
    density read: how much book each door carries. AutoX's book is MEASURED (real tape, current
    outstanding); each peer's is REPORTED (cited FY2025 / 2025 IR). Branch counts follow the network-size
    ranking (AutoX MEASURED own network; peers REPORTED listed-entity IR). Heng is excluded — it now
    carries a cited branch count (450) but reports a GROSS hire-purchase/leasing receivable, a
    different basis from the others' total loans OUTSTANDING, so mixing it into a book-per-branch
    density read would not be apples-to-apples. Returns None when the AutoX book or count is
    unavailable, so the block degrades honestly."""
    if not autox_n or not autox_book_bn:
        return None
    pool = [{"operator": "AutoX", "book_bn": autox_book_bn, "branches": autox_n,
             "book_per_branch_m": round(autox_book_bn * 1000.0 / autox_n, 1),
             "basis": "MEASURED book (real loan tape, current outstanding) / MEASURED own network"}]
    for b in BRANDS:
        exp = EXPECTED.get(b)
        fin = PEER_FINANCIALS.get(b)
        book = fin.get("loan_book_bn") if fin else None
        if exp and book:
            pool.append({"operator": b, "book_bn": book, "branches": exp,
                         "book_per_branch_m": round(book * 1000.0 / exp, 1),
                         "basis": "REPORTED book (cited IR) / REPORTED listed-entity IR branches"})
    # rank by book carried per branch, desc; deterministic tie-break by the fixed pool order.
    order = ["AutoX"] + BRANDS
    ranked = sorted(pool, key=lambda o: (-o["book_per_branch_m"], order.index(o["operator"])))
    for i, o in enumerate(ranked, 1):
        o["rank"] = i
    autox_rank = next(o["rank"] for o in ranked if o["operator"] == "AutoX")
    excluded = [b for b in BRANDS
                if not (EXPECTED.get(b) and (PEER_FINANCIALS.get(b) or {}).get("loan_book_bn"))]
    # peers that carry MORE book per branch than AutoX (fewer, larger branches) vs fewer (denser, thinner).
    heavier = [o["operator"] for o in ranked
               if o["operator"] != "AutoX" and o["rank"] < autox_rank]
    lighter = [o["operator"] for o in ranked
               if o["operator"] != "AutoX" and o["rank"] > autox_rank]
    autox_ppb = next(o["book_per_branch_m"] for o in ranked if o["operator"] == "AutoX")
    nearest = min((o for o in ranked if o["operator"] != "AutoX"),
                  key=lambda o: abs(o["book_per_branch_m"] - autox_ppb), default=None)
    insight = None
    if nearest is not None:
        insight = (
            "AutoX carries ~฿%.0fm of book per branch — a dense, thin-per-branch model, closest to %s "
            "(~฿%.0fm)%s. Under margin pressure (objective #2) that is a structural read: AutoX competes "
            "on network density and per-branch throughput, not per-branch scale."
            % (autox_ppb, nearest["operator"], nearest["book_per_branch_m"],
               (", and well below " + " & ".join("%s (~฿%.0fm)" % (o["operator"], o["book_per_branch_m"])
                for o in ranked if o["operator"] in heavier)) if heavier else "")
        )
    return {
        "autox_rank": autox_rank,
        "n_ranked": len(ranked),
        "ranking": ranked,
        "heavier_per_branch": heavier,
        "lighter_per_branch": lighter,
        "excluded_uncited": excluded,
        "insight": insight,
        "label": "BOOK PER BRANCH — outstanding loan book ÷ branch-network size. AutoX book is MEASURED "
                 "(tape_real.json book_total, current outstanding from the real loan-level export); each "
                 "peer's book is REPORTED (cited FY2025 / 2025 IR). Branch counts as in the network-size "
                 "ranking (AutoX MEASURED own network; peers REPORTED listed-entity IR).",
        "caveat": "Mixed observation basis: AutoX is a current loan-tape snapshot while peer books are "
                  "their latest reported IR figures (FY2025 / 30 Jun 2025), and AutoX branches are the "
                  "own-network count vs peers' listed-entity IR counts — so book-per-branch is a "
                  "STRUCTURAL intensity read (how much book each branch carries), NOT profitability, "
                  "NPL or market share. Heng is excluded — it reports a GROSS hire-purchase/leasing "
                  "receivable (฿8.0bn, 30 Jun 2026), a different basis from the others' total loans "
                  "outstanding, so a book-per-branch read would not be apples-to-apples.",
    }


def _book_per_point(autox_n, autox_book_bn, counts):
    """BOOK PER MEASURED SERVICE POINT — the consistent-denominator companion to _book_intensity.
    book_intensity divides each operator's book by its BRANCH count, but that count is not measured the
    same way for everyone: AutoX uses its own operating network while each peer uses its REPORTED
    listed-entity IR figure. For a GROUP brand the listed entity is a fraction of the doors it actually
    runs (Srisawad: 1,138 listed-entity vs 5,203 store-locator points, ~4.6×), so dividing its book by
    1,138 inflates its per-branch intensity ~4.6× and the IR-basis ranking is not apples-to-apples on
    the denominator. This block fixes exactly that: it divides the SAME books by the MEASURED footprint
    (each operator's de-duplicated store-locator count on the ground, the same `found` figures the
    footprint ranking uses; AutoX by its own network). The NUMERATOR basis is unchanged and still mixed
    (AutoX book MEASURED from the real tape, peers REPORTED IR) — that is inherent, we only hold AutoX's
    real tape — but the DENOMINATOR is now measured identically for all, which is the specific correction.
    Heng is excluded for the same reason as book_intensity (GROSS HP/leasing receivable, not total loans
    outstanding). Returns None when the AutoX book or count is unavailable, so it degrades honestly."""
    if not autox_n or not autox_book_bn:
        return None
    pool = [{"operator": "AutoX", "book_bn": autox_book_bn, "points": autox_n,
             "book_per_point_m": round(autox_book_bn * 1000.0 / autox_n, 1),
             "basis": "MEASURED book (real loan tape, current outstanding) / MEASURED own network"}]
    for b in LOCATOR_COMPLETE_BRANDS:
        pts = counts.get(b)
        fin = PEER_FINANCIALS.get(b)
        book = fin.get("loan_book_bn") if fin else None
        if pts and book:
            pool.append({"operator": b, "book_bn": book, "points": pts,
                         "book_per_point_m": round(book * 1000.0 / pts, 1),
                         "basis": "REPORTED book (cited IR) / MEASURED store-locator footprint"})
    order = ["AutoX"] + BRANDS
    ranked = sorted(pool, key=lambda o: (-o["book_per_point_m"], order.index(o["operator"])))
    for i, o in enumerate(ranked, 1):
        o["rank"] = i
    autox_rank = next(o["rank"] for o in ranked if o["operator"] == "AutoX")
    # brands in our set that carry a cited book but are NOT ranked here (no near-complete locator).
    # All four locator-complete brands with a cited book enter; Heng lacks a comparable book basis.
    excluded = [b for b in BRANDS
                if not (b in LOCATOR_COMPLETE_BRANDS and (PEER_FINANCIALS.get(b) or {}).get("loan_book_bn"))]
    autox_ppp = next(o["book_per_point_m"] for o in ranked if o["operator"] == "AutoX")
    heavier = [o["operator"] for o in ranked
               if o["operator"] != "AutoX" and o["rank"] < autox_rank]
    lighter = [o["operator"] for o in ranked
               if o["operator"] != "AutoX" and o["rank"] > autox_rank]
    insight = None
    if len(ranked) > 1:
        lead = ranked[0]
        # Contrast with the IR-basis read: name the operators that look heavier per IR-branch but
        # lighter (or comparable) per measured point, which is the whole point of this companion block.
        lighter_txt = (" — ahead of " + " & ".join("%s (~฿%.0fm)" % (o["operator"], o["book_per_point_m"])
                       for o in ranked if o["operator"] in lighter)) if lighter else ""
        insight = (
            "On a CONSISTENT measured-footprint denominator AutoX carries ~฿%.0fm of book per physical "
            "service point, ranking #%d of %d%s. This reorders the per-branch read: Srisawad looks heaviest "
            "per IR-listed branch (~฿82m) only because its listed entity (1,138) is a fraction of its "
            "~5,203 store-locator doors — per actual point on the ground it carries ~฿18m, LIGHTER than "
            "AutoX. Measured door-for-door, %s leads; AutoX's density is heavier than the group brands' "
            "(Srisawad, Muangthai) and below only %s. A structural intensity read for objective #2, NOT "
            "profitability, NPL or market share."
            % (autox_ppp, autox_rank, len(ranked), lighter_txt, lead["operator"], lead["operator"])
        )
    return {
        "autox_rank": autox_rank,
        "n_ranked": len(ranked),
        "ranking": ranked,
        "heavier_per_point": heavier,
        "lighter_per_point": lighter,
        "excluded_uncited": excluded,
        "insight": insight,
        "label": "BOOK PER MEASURED SERVICE POINT — outstanding loan book ÷ MEASURED footprint (physical "
                 "doors on the ground). The consistent-denominator companion to book-per-branch: every "
                 "operator's denominator is its de-duplicated store-locator count (AutoX its own network), "
                 "measured identically — unlike book-per-branch, which divides peers' books by their "
                 "REPORTED listed-entity IR counts. AutoX book is MEASURED (real tape, current "
                 "outstanding); each peer's book is REPORTED (cited FY2025 / 2025 IR).",
        "caveat": "The DENOMINATOR is now measured identically for all operators (store-locator footprint), "
                  "which is the correction over book-per-branch. The NUMERATOR basis is still mixed — AutoX "
                  "book is a current loan-tape snapshot, peer books are their latest reported IR figures "
                  "(FY2025 / 30 Jun 2025) — so this remains a STRUCTURAL intensity read (book per door), NOT "
                  "profitability, NPL or market share. Heng is excluded (GROSS HP/leasing receivable, a "
                  "different basis from the others' total loans outstanding).",
    }


def _footprint_measured(autox_n, counts):
    """SECOND, all-MEASURED ranking that complements the IR-count ranking: operators by physical
    POINTS ON THE GROUND — AutoX's own operating network (branches.json) vs each near-complete-locator
    rival's de-duplicated store-locator count (the SAME `found` figures on the brand board). Unlike the
    IR ranking (peers = REPORTED listed-entity counts), every number here is MEASURED, so it answers a
    different question: not "who reports the biggest listed-entity network" but "who has the most doors
    open on the ground". All four rivals now carry an official locator (Heng was province-walked from
    hengleasing.com, replacing its earlier sample), so all are ranked. Returns None when the AutoX
    count is unavailable."""
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
    # brands in our set NOT ranked here (no near-complete locator) -> disclosed. All four now have an
    # official locator, so this is empty; kept for honest degradation if a brand's locator is ever lost.
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
        "caveat": "All four rivals are official-locator networks now (Heng's hengleasing.com province-walk "
                  "replaced its earlier Cloudflare-blocked sample), so all are ranked. A store-locator "
                  "lists every service point, so for a GROUP brand this footprint exceeds the listed-entity "
                  "IR count (Srisawad's 5,203 locator points ≈ 4.6× its 1,138 listed-entity figure). Points "
                  "on the ground ≠ market share.",
    }


def _national_standing(autox_n, counts):
    """Where AutoX sits nationally among the big-4 by BRANCH-NETWORK SIZE — the read the
    found-vs-expected board hides (it never places AutoX in its own peer set). AutoX's size is
    MEASURED (its own committed network); each peer's size is its cited public 'expected' figure
    (REPORTED). Only operators with a cited figure enter the ranking pool; all four rivals now carry
    one (Heng's 450 is cited in its SET filings), so all are ranked. This is a NETWORK-SIZE
    comparison, NOT market share and NOT the local per-province density read (peer_province.json,
    where clustering makes AutoX read as a modal-3rd) — the two answer different questions and are
    cross-referenced in the caveat. Returns None when the AutoX count is unavailable."""
    if not autox_n:
        return None
    # pool = AutoX (measured own network) + each peer WITH a cited reported figure.
    pool = [{"operator": "AutoX", "branches": autox_n,
             "basis": "MEASURED (own operating network, branches.json)",
             # AutoX is CONSOLIDATING its network (CLAUDE.md) — no branch-growth target. Stated as a
             # posture, never as an invented positive net-adds number.
             "net_adds_yr": None, "expansion": "consolidating (no branch-growth target)"}]
    for b in BRANDS:
        exp = EXPECTED.get(b)
        if exp:
            entry = {"operator": b, "branches": exp, "basis": "REPORTED (cited public IR figure)"}
            fin = PEER_FINANCIALS.get(b)
            if fin:
                # attach only the cited fields; None-valued keys stay present (honest ABSENT), so the
                # UI can tell "not reported" from a genuine zero.
                entry["loan_book_bn"] = fin.get("loan_book_bn")
                entry["book_asof"] = fin.get("book_asof")
                entry["book_yoy_pct"] = fin.get("book_yoy_pct")
                entry["net_adds_yr"] = fin.get("net_adds_yr")
                entry["net_adds_year"] = fin.get("net_adds_year")
                entry["prior_year_branches"] = fin.get("prior_year_branches")
                entry["growth_target_pct"] = fin.get("growth_target_pct")
            pool.append(entry)
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
    book_intensity = _book_intensity(autox_n, _autox_book_bn())
    book_per_point = _book_per_point(autox_n, _autox_book_bn(), counts)
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
        "book_intensity": book_intensity,
        "book_per_point": book_per_point,
        "reported_vs_measured_insight": insight,
        "basis": "NETWORK SIZE — AutoX's MEASURED own-network branch count vs each peer's REPORTED "
                 "(cited public IR) branch count. A national footprint-scale read, NOT market share.",
        "caveat": "This ranks operators by total branch-NETWORK size nationally, where AutoX is the "
                  "2nd-largest title-loan network. It is a DIFFERENT question from the per-province "
                  "density board (peer_province.json), where rivals cluster in dense provinces and "
                  "AutoX reads as a modal-3rd locally — national scale and local density tell "
                  "different stories, both true. All four rivals carry a cited count now (Heng 450, "
                  "the one contracting peer, per its SET filings). Peer figures are listed-ENTITY IR "
                  "counts; a group's full retail footprint can be larger (see the Srisawad note above).",
        "expansion_label": "REPORTED — each peer's own FY2025 / 2025 IR (loan book ฿bn, branch net-adds "
                           "where disclosed). AutoX is MEASURED own-network + CONSOLIDATING posture "
                           "(no branch-growth target). Direction, not just static counts.",
        "expansion_note": "The #1 rival (MTC) kept opening branches — +518 in 2025 (8,155 → 8,673) — "
                          "and runs a ฿183bn loan book, ~2.6x AutoX's ~2,015-branch network, while AutoX "
                          "consolidates. That is competitive pressure / margin erosion on the network we "
                          "already run (objective #2), not a case for matching branch count. Tidlor's book "
                          "grew +5.4% YoY to ฿110bn; Srisawad's is ฿93bn (30 Jun 2025). Branch net-adds are "
                          "shown only for MTC (the one operator that disclosed a delta) — never back-computed.",
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
        "peer_financials_label": "REPORTED-from-public-reports (peer loan book & branch net-adds — "
                                 "cited FY2025 / 2025 IR, see peer_financials_sources).",
        "peer_financials_sources": PEER_FINANCIALS_SOURCES,
        "totals": {"found": total_found, "expected": total_expected or None,
                   "coverage_pct": overall_cov},
        "national_standing": national_standing,
        "caveat": "found now comes from each operator's OFFICIAL store-locator for all four big brands "
                  "(Muangthai, Srisawad, Tidlor from their web locators; Heng province-walked from "
                  "hengleasing.com, replacing its earlier Cloudflare-blocked sample), so coverage_pct is "
                  "~100% and can exceed 100% because a locator lists every service point / sub-branch "
                  "beyond the company's headline branch count. Heng's 450 measured points match its cited "
                  "450-branch SET-filing count (30 Jun 2026). Read coverage as a data-completeness flag, "
                  "not market share.",
        "note": "expected counts are CITED real figures (not modelled). coverage_pct >100% for the "
                "official-locator brands is expected, not an error: a locator lists every service point, "
                "and for a GROUP brand it covers the whole retail network while the IR 'branches' figure "
                "counts only the LISTED ENTITY. Srisawad is the clearest case — the sawad.co.th locator "
                "returns 5,203 measured points vs the 1,138 listed-entity IR figure, i.e. the SAWAD "
                "group's retail footprint is ~4.6x its reported branch count. Heng is the one contracting "
                "listed peer (branches 1,018→743→450 over Dec 2024→Jun 2026, SET filings).",
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
        bi = ns.get("book_intensity")
        if bi:
            print("  book per branch (structural intensity): AutoX #%d of %d — %s"
                  % (bi["autox_rank"], bi["n_ranked"],
                     " > ".join("%s ฿%sm" % (o["operator"], o["book_per_branch_m"]) for o in bi["ranking"])))
        bpp = ns.get("book_per_point")
        if bpp:
            print("  book per measured point (consistent denominator): AutoX #%d of %d — %s"
                  % (bpp["autox_rank"], bpp["n_ranked"],
                     " > ".join("%s ฿%sm" % (o["operator"], o["book_per_point_m"]) for o in bpp["ranking"])))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="competitor-census coverage QA (found vs expected)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
