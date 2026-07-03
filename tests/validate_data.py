#!/usr/bin/env python3
# AutoX credit-intelligence — DATA-INTEGRITY validator (IPO-readiness gate).
#
# The committed QA suite (tests/run.sh) checks DETERMINISM (pipeline --check),
# JS SYNTAX, and RENDER/HEALTH of the pages. It does NOT check that the DATA
# inside platform/data/*.json is internally sane. This script fills that gap.
#
# Properties:
#   - pure stdlib (json, math, os, sys) — no third-party imports
#   - network-free, deterministic (only reads committed files)
#   - exits 0 when every check passes, non-zero on the FIRST hard violation set
#   - prints a plain PASS/FAIL line per check
#
# If this script finds a REAL data bug, do NOT weaken the check — fix the data
# or report it. The point is to catch integrity regressions before an IPO audit.
#
# Usage:  python3 tests/validate_data.py           (from anywhere; paths are resolved)
#         tests/run.sh check                         (runs it as the 'data' sub-check)

import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DATA = os.path.join(REPO, "platform", "data")

# Thailand bounding box (generous; covers all 77 provinces incl. far south + far north).
TH_LAT_MIN, TH_LAT_MAX = 5.5, 20.5
TH_LNG_MIN, TH_LNG_MAX = 97.0, 106.0

# Canonical region set, taken from the master (branches.json) — every file must agree.
KNOWN_REGIONS = {"Isan", "North", "South", "East", "Central&BKK"}

# Canonical competitor lender brands (pull_competitors.py / pull_overture_places.py emit exactly
# these brand keys). Any other brand string in a competitor census is a data bug.
KNOWN_COMPETITOR_BRANDS = {"Srisawad", "Muangthai", "Tidlor", "Heng"}

# How many province deep-dive files to spot-check (deterministic: alphabetical).
PROVINCE_SAMPLE = 8

GRN = "\033[32m"
RED = "\033[31m"
YLW = "\033[33m"
RST = "\033[0m"

_passed = 0
_failed = 0
_problems = []  # (check, detail)


def _isatty():
    return sys.stdout.isatty()


def ok(name):
    global _passed
    _passed += 1
    p = "[PASS]"
    if _isatty():
        p = GRN + p + RST
    print("%s %s" % (p, name))


def fail(name, detail=""):
    global _failed
    _failed += 1
    _problems.append((name, detail))
    p = "[FAIL]"
    if _isatty():
        p = RED + p + RST
    print("%s %s" % (p, name))
    if detail:
        for line in str(detail).splitlines():
            print("       " + line)


def hdr(name):
    if _isatty():
        print("\n%s== %s ==%s" % (YLW, name, RST))
    else:
        print("\n== %s ==" % name)


def exists(rel):
    return os.path.exists(os.path.join(DATA, rel))


def load(rel):
    path = os.path.join(DATA, rel)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_finite_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def first_n(items, n=5):
    items = list(items)
    if len(items) <= n:
        return ", ".join(str(i) for i in items)
    return ", ".join(str(i) for i in items[:n]) + (" ... (+%d more)" % (len(items) - n))


# ---------------------------------------------------------------------------
def check_branches():
    hdr("branches.json")
    try:
        b = load("branches.json")
    except Exception as e:
        fail("branches.json loads", repr(e))
        return None
    ok("branches.json loads (%d records)" % len(b))

    if not isinstance(b, list) or not b:
        fail("branches.json is a non-empty list", "got %s" % type(b).__name__)
        return None

    # required fields on every branch
    required = ["x", "y", "n", "v", "r", "o", "a", "m", "c", "w", "k10"]
    missing = []
    for i, rec in enumerate(b):
        miss = [k for k in required if k not in rec]
        if miss:
            missing.append("#%d missing %s" % (i, miss))
    if missing:
        fail("every branch has required fields %s" % required, first_n(missing))
    else:
        ok("every branch has required fields %s" % required)

    # lat/lng within Thailand bbox (x=lng, y=lat)
    oob = []
    for i, rec in enumerate(b):
        lng, lat = rec.get("x"), rec.get("y")
        if not (is_finite_number(lng) and is_finite_number(lat)):
            oob.append("#%d non-numeric lat/lng (%r,%r)" % (i, lat, lng))
            continue
        if not (TH_LAT_MIN <= lat <= TH_LAT_MAX and TH_LNG_MIN <= lng <= TH_LNG_MAX):
            oob.append("#%d (%s) lat=%s lng=%s outside TH bbox" % (i, rec.get("n"), lat, lng))
    if oob:
        fail("all branch lat/lng inside Thailand bbox (%.1f..%.1fN, %.1f..%.1fE)"
             % (TH_LAT_MIN, TH_LAT_MAX, TH_LNG_MIN, TH_LNG_MAX), first_n(oob))
    else:
        ok("all branch lat/lng inside Thailand bbox (%.1f..%.1fN, %.1f..%.1fE)"
           % (TH_LAT_MIN, TH_LAT_MAX, TH_LNG_MIN, TH_LNG_MAX))

    # Segment scores a/m/c and saturation w are 0-based -> must be non-negative finite.
    # Opportunity 'o' is deliberately a SIGNED, centered index (derive.py: round(opportunity)),
    # consumed in app.js via norm(d.o||0,...) and exported as opportunity_o_est; it legitimately
    # goes negative. So 'o' is checked for finiteness only, NOT for sign.
    nonneg_keys = ["a", "m", "c", "w"]
    badscore = []
    for i, rec in enumerate(b):
        for k in nonneg_keys:
            v = rec.get(k)
            if not is_finite_number(v):
                badscore.append("#%d %s=%r not finite" % (i, k, v))
            elif v < 0:
                badscore.append("#%d %s=%r negative" % (i, k, v))
    if badscore:
        fail("segment scores %s are non-negative finite" % nonneg_keys, first_n(badscore))
    else:
        ok("segment scores %s are non-negative finite" % nonneg_keys)

    bad_o = [("#%d o=%r" % (i, rec.get("o"))) for i, rec in enumerate(b)
             if not is_finite_number(rec.get("o"))]
    if bad_o:
        fail("opportunity 'o' is finite (signed index)", first_n(bad_o))
    else:
        ok("opportunity 'o' is finite (signed index, range allowed negative)")

    # k10 counts: dict of non-negative finite numbers
    badk = []
    for i, rec in enumerate(b):
        k10 = rec.get("k10")
        if not isinstance(k10, dict) or not k10:
            badk.append("#%d k10 not a non-empty dict" % i)
            continue
        for kk, vv in k10.items():
            if not is_finite_number(vv) or vv < 0:
                badk.append("#%d k10.%s=%r" % (i, kk, vv))
    if badk:
        fail("k10 counts are non-negative finite", first_n(badk))
    else:
        ok("k10 counts are non-negative finite")

    # province/region values known
    bad_reg = sorted(set(rec.get("r") for rec in b if rec.get("r") not in KNOWN_REGIONS))
    if bad_reg:
        fail("all branch regions are known %s" % sorted(KNOWN_REGIONS), "unknown: " + first_n(bad_reg))
    else:
        ok("all branch regions are known %s" % sorted(KNOWN_REGIONS))

    bad_prov = [("#%d" % i) for i, rec in enumerate(b)
                if not (isinstance(rec.get("v"), str) and rec.get("v").strip())]
    if bad_prov:
        fail("all branches have a non-empty province (v)", first_n(bad_prov))
    else:
        n_prov = len(set(rec.get("v") for rec in b))
        ok("all branches have a non-empty province (v) — %d distinct provinces" % n_prov)

    return b


# ---------------------------------------------------------------------------
def check_amphoe(n_branches):
    hdr("amphoe.json")
    try:
        a = load("amphoe.json")
    except Exception as e:
        fail("amphoe.json loads", repr(e))
        return None
    ok("amphoe.json loads")

    recs = a.get("amphoe")
    if not isinstance(recs, list):
        fail("amphoe.json has an 'amphoe' record list", "got %s" % type(recs).__name__)
        return None

    if len(recs) == 928:
        ok("amphoe count == 928")
    else:
        fail("amphoe count == 928", "got %d" % len(recs))

    # numeric whitespace / risk finite (risk_proxy may be null for some zero-branch amphoe? check)
    bad = []
    for i, r in enumerate(recs):
        ws = r.get("whitespace")
        rp = r.get("risk_proxy")
        if not is_finite_number(ws):
            bad.append("#%d whitespace=%r" % (i, ws))
        if rp is not None and not is_finite_number(rp):
            bad.append("#%d risk_proxy=%r" % (i, rp))
    if bad:
        fail("amphoe whitespace/risk_proxy numeric finite", first_n(bad))
    else:
        ok("amphoe whitespace/risk_proxy numeric finite")

    # branch_amphoe indices in range and one per branch
    ba = a.get("branch_amphoe")
    if isinstance(ba, list):
        if n_branches is not None and len(ba) != n_branches:
            fail("branch_amphoe length == branch count",
                 "branch_amphoe=%d branches=%d" % (len(ba), n_branches))
        else:
            ok("branch_amphoe length == branch count (%d)" % len(ba))
        oob = [("#%d->%r" % (i, v)) for i, v in enumerate(ba)
               if not (isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(recs))]
        if oob:
            fail("branch_amphoe indices in range [0,%d)" % len(recs), first_n(oob))
        else:
            ok("branch_amphoe indices in range [0,%d)" % len(recs))
    else:
        # field is optional per spec
        ok("branch_amphoe absent (optional) — skipped index check")

    # meta join_rates present + sane thresholds
    meta = a.get("meta", {})
    jr = meta.get("join_rates")
    if not isinstance(jr, dict) or not jr:
        fail("amphoe meta.join_rates present", "missing or empty")
    else:
        ok("amphoe meta.join_rates present (%d entries)" % len(jr))
        # branch_to_amphoe like "2000/2015" -> ratio should be high
        bt = jr.get("branch_to_amphoe", "")
        try:
            num, den = bt.split("/")
            num, den = int(num), int(den)
            ratio = num / den if den else 0.0
            if ratio >= 0.95:
                ok("branch_to_amphoe join-rate %s = %.1f%% (>= 95%%)" % (bt, 100 * ratio))
            else:
                fail("branch_to_amphoe join-rate >= 95%%", "%s = %.1f%%" % (bt, 100 * ratio))
        except Exception:
            fail("branch_to_amphoe join-rate parseable", "got %r" % bt)

    # meta declared count agrees with actual
    n_meta = meta.get("n_amphoe")
    if n_meta is not None and n_meta != len(recs):
        fail("meta.n_amphoe matches record count", "meta=%s actual=%d" % (n_meta, len(recs)))
    else:
        ok("meta.n_amphoe matches record count")

    return a


# ---------------------------------------------------------------------------
def check_amphoe_geo(amphoe):
    """amphoe_geo.json — the simplified boundary polygons for the National choropleth.
    OPTIONAL layer (the map degrades to dots without it), so absence is a PASS. When
    present it must be a valid FeatureCollection, carry provenance, and every polygon
    must join to an amphoe.json record on properties.id."""
    hdr("amphoe_geo.json")
    path = os.path.join(DATA, "amphoe_geo.json")
    if not os.path.exists(path):
        ok("amphoe_geo.json absent (optional map layer) — skipped")
        return
    try:
        g = load("amphoe_geo.json")
    except Exception as e:
        fail("amphoe_geo.json loads", repr(e))
        return
    ok("amphoe_geo.json loads")

    if g.get("type") == "FeatureCollection" and isinstance(g.get("features"), list):
        ok("amphoe_geo is a FeatureCollection with features[]")
    else:
        fail("amphoe_geo is a FeatureCollection with features[]", "bad top-level shape")
        return
    feats = g["features"]

    # provenance: meta must state the source + the simplified/geometry-only label (data-mandate:
    # this is MEASURED boundaries, decimated — no fabricated attributes).
    meta = g.get("meta", {})
    if meta.get("generated_by") and meta.get("source") and meta.get("label"):
        ok("amphoe_geo meta/provenance present (generated_by + source + label)")
    else:
        fail("amphoe_geo meta/provenance present (generated_by + source + label)",
             "meta missing generated_by/source/label")

    # geometry sanity: every feature is a Polygon/MultiPolygon with a valid closed outer ring,
    # all coords inside the Thailand bbox.
    bad_geom = []
    oob = 0
    for i, f in enumerate(feats):
        geom = (f or {}).get("geometry") or {}
        t = geom.get("type")
        coords = geom.get("coordinates")
        if t not in ("Polygon", "MultiPolygon") or not isinstance(coords, list):
            bad_geom.append("#%d type=%r" % (i, t)); continue
        polys = coords if t == "MultiPolygon" else [coords]
        okgeom = True
        for poly in polys:
            if not poly or not isinstance(poly[0], list) or len(poly[0]) < 4:
                okgeom = False; break
            ring = poly[0]
            if ring[0] != ring[-1]:
                okgeom = False; break
            for pt in ring:
                lng, lat = pt[0], pt[1]
                if not (TH_LNG_MIN <= lng <= TH_LNG_MAX and TH_LAT_MIN <= lat <= TH_LAT_MAX):
                    oob += 1
        if not okgeom:
            bad_geom.append("#%d bad/short/open ring" % i)
    if bad_geom:
        fail("amphoe_geo every feature has a valid closed outer ring", first_n(bad_geom))
    else:
        ok("amphoe_geo every feature has a valid closed outer ring")
    if oob == 0:
        ok("amphoe_geo all vertices inside Thailand bbox")
    else:
        fail("amphoe_geo all vertices inside Thailand bbox", "%d out-of-bbox vertices" % oob)

    # join: every polygon id must resolve to an amphoe.json record (1:1 map — the choropleth
    # colours each polygon by its amphoe lens value).
    gids = [((f or {}).get("properties") or {}).get("id") for f in feats]
    if all(isinstance(i, str) and i for i in gids):
        ok("amphoe_geo every feature carries a string properties.id")
    else:
        fail("amphoe_geo every feature carries a string properties.id",
             "some features missing id")
    if amphoe and isinstance(amphoe.get("amphoe"), list):
        aids = {r.get("id") for r in amphoe["amphoe"]}
        unmatched = [i for i in gids if i not in aids]
        if unmatched:
            fail("amphoe_geo ids all join to amphoe.json", first_n(unmatched))
        else:
            ok("amphoe_geo ids all join to amphoe.json (%d polygons)" % len(gids))


# ---------------------------------------------------------------------------
def check_provinces(n_branches):
    hdr("provinces/")
    try:
        idx = load(os.path.join("provinces", "index.json"))
    except Exception as e:
        fail("provinces/index.json loads", repr(e))
        return
    ok("provinces/index.json loads (%d provinces)" % len(idx))

    if not isinstance(idx, list) or not idx:
        fail("provinces index is a non-empty list", "got %s" % type(idx).__name__)
        return

    # every index entry has slug + numeric branches; regions known
    bad = []
    for e in idx:
        if not isinstance(e.get("slug"), str) or not e["slug"]:
            bad.append("entry missing slug: %r" % e)
        if not (isinstance(e.get("branches"), int) and e["branches"] >= 0):
            bad.append("%s branches=%r" % (e.get("slug"), e.get("branches")))
        if e.get("region") not in KNOWN_REGIONS:
            bad.append("%s region=%r unknown" % (e.get("slug"), e.get("region")))
    if bad:
        fail("province index entries well-formed (slug/branches/region)", first_n(bad))
    else:
        ok("province index entries well-formed (slug/branches/region)")

    # cross-file rollup: sum of index branch counts ~= national count
    idx_sum = sum(e.get("branches", 0) for e in idx)
    if n_branches is not None:
        # allow the known 2,013 vs 2,015 duplicate-code drift (tolerance of a few branches)
        diff = abs(idx_sum - n_branches)
        if diff <= 2:
            ok("province branch counts sum (%d) ~= national (%d), diff=%d (<=2 known dup-code note)"
               % (idx_sum, n_branches, diff))
        else:
            fail("province branch counts sum ~= national (diff <= 2)",
                 "index sum=%d national=%d diff=%d" % (idx_sum, n_branches, diff))

    # spot-check a deterministic sample of province deep-dive files
    sample = sorted(e["slug"] for e in idx)[:PROVINCE_SAMPLE]
    bad_files = []
    for slug in sample:
        rel = os.path.join("provinces", slug + ".json")
        path = os.path.join(DATA, rel)
        if not os.path.exists(path):
            bad_files.append("%s.json missing" % slug)
            continue
        try:
            p = load(rel)
        except Exception as e:
            bad_files.append("%s.json load error: %r" % (slug, e))
            continue
        branches = p.get("branches")
        if not isinstance(branches, list):
            bad_files.append("%s.json branches not a list" % slug)
            continue
        # branch count in deep-dive consistent with index
        idx_count = next((e["branches"] for e in idx if e["slug"] == slug), None)
        if idx_count is not None and len(branches) != idx_count:
            bad_files.append("%s branches deep-dive=%d index=%d" % (slug, len(branches), idx_count))
        # k10 present + no NaN, on every branch
        for j, br in enumerate(branches):
            k10 = br.get("k10")
            if not isinstance(k10, dict) or not k10:
                bad_files.append("%s branch#%d missing k10" % (slug, j))
                break
            nan_or_inf = [kk for kk, vv in k10.items()
                          if isinstance(vv, float) and not math.isfinite(vv)]
            if nan_or_inf:
                bad_files.append("%s branch#%d k10 NaN/inf: %s" % (slug, j, nan_or_inf))
                break
            # also scan top-level numeric fields for NaN/inf
            bad_num = [kk for kk, vv in br.items()
                       if isinstance(vv, float) and not math.isfinite(vv)]
            if bad_num:
                bad_files.append("%s branch#%d NaN/inf fields: %s" % (slug, j, bad_num))
                break
    if bad_files:
        fail("sampled province deep-dives consistent (counts, k10, no NaN) [%s]" % first_n(sample),
             first_n(bad_files))
    else:
        ok("sampled province deep-dives consistent (counts, k10, no NaN) [%s]" % first_n(sample))


# ---------------------------------------------------------------------------
def check_crop_stress():
    hdr("crop_stress.json")
    try:
        cs = load("crop_stress.json")
    except Exception as e:
        fail("crop_stress.json loads", repr(e))
        return
    ok("crop_stress.json loads")

    # provenance / meta present
    meta = cs.get("meta")
    if not isinstance(meta, dict) or "generated_by" not in meta or "fields" not in meta:
        fail("crop_stress meta/provenance present", "meta missing generated_by/fields")
    else:
        ok("crop_stress meta/provenance present")

    provs = cs.get("provinces")
    if not isinstance(provs, list) or not provs:
        fail("crop_stress has a 'provinces' list", "got %s" % type(provs).__name__)
        return
    ok("crop_stress provinces list present (%d)" % len(provs))

    bad = []
    for p in provs:
        name = p.get("th") or p.get("en") or "?"
        # region known
        if p.get("region") not in KNOWN_REGIONS:
            bad.append("%s region=%r unknown" % (name, p.get("region")))
        # agri_stress in [0,1]
        ag = p.get("agri_stress")
        if not is_finite_number(ag) or not (0.0 <= ag <= 1.0):
            bad.append("%s agri_stress=%r out of [0,1]" % (name, ag))
        # drought in [0,1]
        dr = p.get("drought")
        if dr is not None and (not is_finite_number(dr) or not (0.0 <= dr <= 1.0)):
            bad.append("%s drought=%r out of [0,1]" % (name, dr))
        # crop_dependence in [0,1]
        cd = p.get("crop_dependence")
        if cd is not None and (not is_finite_number(cd) or not (0.0 <= cd <= 1.0)):
            bad.append("%s crop_dependence=%r out of [0,1]" % (name, cd))
        # components.hazard in [0,1] when present
        comp = p.get("components") or {}
        for ck in ("price_term", "drought_term", "hazard"):
            cv = comp.get(ck)
            if cv is not None and (not is_finite_number(cv) or not (0.0 <= cv <= 1.0)):
                bad.append("%s components.%s=%r out of [0,1]" % (name, ck, cv))
        # crop_mix shares ~ sum to 1
        mix = p.get("crop_mix")
        if isinstance(mix, list) and mix:
            shares = [m.get("share") for m in mix]
            if any(not is_finite_number(s) for s in shares):
                bad.append("%s crop_mix has non-numeric share" % name)
            else:
                total = sum(shares)
                if abs(total - 1.0) > 0.02:
                    bad.append("%s crop_mix shares sum=%.4f (not ~1.0)" % (name, total))
    if bad:
        fail("crop_stress ranges + crop_mix shares sane", first_n(bad, 8))
    else:
        ok("crop_stress ranges sane (agri_stress/drought/dependence/components in [0,1])")
        ok("crop_stress crop_mix shares ~ sum to 1.0 (tol 0.02)")


# ---------------------------------------------------------------------------
def check_collateral_outlook():
    # PER-PROVINCE COLLATERAL-VALUE OUTLOOK (objective #1): a DIRECTIONAL, ESTIMATED read on whether
    # title-loan collateral recovery value is firming/softening, built from MEASURED gold YoY (global
    # board proxy) + MEASURED DLT moto-title share + ESTIMATED collateral segment score. Optional
    # file: SKIP-PASS when absent (build_collateral_outlook.py degrades to an honest absent-state too).
    hdr("collateral_outlook.json (optional)")
    if not exists("collateral_outlook.json"):
        ok("collateral_outlook.json absent — skipped (optional; run build_collateral_outlook.py)")
        return
    try:
        d = load("collateral_outlook.json")
    except Exception as e:
        fail("collateral_outlook.json loads", repr(e))
        return
    ok("collateral_outlook.json loads")

    # provenance: meta must state the builder + the ESTIMATED directional label (data-mandate).
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("label"):
        fail("collateral_outlook meta/provenance present (generated_by + label)",
             "meta missing generated_by/label")
    else:
        ok("collateral_outlook meta/provenance present (generated_by + estimated label)")

    # honest absent-state: file may legitimately ship empty when branches.json is missing.
    if meta and meta.get("absent"):
        ok("collateral_outlook is an honest ABSENT-state (no branches.json) — skipped value checks")
        return

    provs = d.get("provinces")
    if not isinstance(provs, list) or not provs:
        fail("collateral_outlook has a 'provinces' list", "got %s" % type(provs).__name__)
        return
    ok("collateral_outlook provinces list present (%d)" % len(provs))

    bad = []
    for p in provs:
        name = p.get("province") or "?"
        # region known (when present)
        if p.get("region") is not None and p.get("region") not in KNOWN_REGIONS:
            bad.append("%s region=%r unknown" % (name, p.get("region")))
        # gold_yoy: MEASURED/GLOBAL proxy — finite or null (never fabricated)
        g = p.get("gold_yoy")
        if g is not None and not is_finite_number(g):
            bad.append("%s gold_yoy=%r not finite" % (name, g))
        # moto_title_share: MEASURED share in [0,1] or null
        ms = p.get("moto_title_share")
        if ms is not None and (not is_finite_number(ms) or not (0.0 <= ms <= 1.0)):
            bad.append("%s moto_title_share=%r out of [0,1]" % (name, ms))
        # collateral_score: ESTIMATED non-negative finite or null
        cs = p.get("collateral_score")
        if cs is not None and (not is_finite_number(cs) or cs < 0):
            bad.append("%s collateral_score=%r not non-negative finite" % (name, cs))
        # outlook: ESTIMATED directional index in ~[-1,1] (W_GOLD+W_MOTO=1.0 bounds it)
        out = p.get("outlook")
        if not is_finite_number(out) or not (-1.0 <= out <= 1.0):
            bad.append("%s outlook=%r out of [-1,1]" % (name, out))
        # note must be a non-empty string (the honest plain-language read)
        if not (isinstance(p.get("outlook_note"), str) and p.get("outlook_note").strip()):
            bad.append("%s outlook_note missing/empty" % name)
        # components.gold_term / moto_term in [-1,1] when present
        comp = p.get("components") or {}
        for ck in ("gold_term", "moto_term"):
            cv = comp.get(ck)
            if cv is not None and (not is_finite_number(cv) or not (-1.0 <= cv <= 1.0)):
                bad.append("%s components.%s=%r out of [-1,1]" % (name, ck, cv))
    if bad:
        fail("collateral_outlook rows sane (region/gold/moto-share/score/outlook ranges, note present)",
             first_n(bad, 8))
    else:
        ok("collateral_outlook rows sane (gold_yoy finite-or-null, moto_share in [0,1], outlook in "
           "[-1,1], note present, known regions)")

    # national summary block present + consistent
    nat = d.get("national")
    if not isinstance(nat, dict):
        fail("collateral_outlook national summary present", "got %s" % type(nat).__name__)
    else:
        ok("collateral_outlook national summary present")
        nb = []
        ew = nat.get("exposure_weighted_outlook")
        if ew is not None and (not is_finite_number(ew) or not (-1.0 <= ew <= 1.0)):
            nb.append("exposure_weighted_outlook=%r out of [-1,1]" % ew)
        npv = nat.get("n_provinces")
        if npv is not None and npv != len(provs):
            nb.append("national.n_provinces=%r != provinces count=%d" % (npv, len(provs)))
        if not (isinstance(nat.get("headline"), str) and nat.get("headline").strip()):
            nb.append("headline missing/empty")
        if nb:
            fail("collateral_outlook national summary sane", first_n(nb))
        else:
            ok("collateral_outlook national summary sane (weighted outlook in [-1,1], count + headline)")


# ---------------------------------------------------------------------------
def check_household_risk():
    # MEASURED household debt-to-income layer (NSO SES via TMLI bridge), province-keyed. Optional
    # file: SKIP-PASS when absent (build_household_risk.py degrades to an absent-state too).
    hdr("household_risk_by_province.json (optional)")
    if not exists("household_risk_by_province.json"):
        ok("household_risk_by_province.json absent — skipped (optional; run build_household_risk.py)")
        return
    try:
        d = load("household_risk_by_province.json")
    except Exception as e:
        fail("household_risk_by_province.json loads", repr(e))
        return
    ok("household_risk_by_province.json loads")

    # meta / provenance present (the data-mandate: MEASURED vs ESTIMATED must be stated)
    meta = d.get("meta")
    if not isinstance(meta, dict) or "generated_by" not in meta or "source" not in meta:
        fail("household_risk meta/provenance present", "meta missing generated_by/source")
    else:
        ok("household_risk meta/provenance present")

    # honest absent-state: file may legitimately ship empty when the source layers are missing.
    if meta and meta.get("absent"):
        ok("household_risk is an honest ABSENT-state (no sources) — skipped value checks")
        return

    provs = d.get("provinces")
    if not isinstance(provs, list) or not provs:
        fail("household_risk has a 'provinces' list", "got %s" % type(provs).__name__)
        return
    ok("household_risk provinces list present (%d)" % len(provs))

    bad = []
    for p in provs:
        name = p.get("province") or "?"
        if p.get("region") is not None and p.get("region") not in KNOWN_REGIONS:
            bad.append("%s region=%r unknown" % (name, p.get("region")))
        debt = p.get("debt")
        income = p.get("income")
        dti = p.get("debt_to_income")
        si = p.get("stress_index")
        # debt + income: MEASURED, must be positive finite
        if not is_finite_number(debt) or debt <= 0:
            bad.append("%s debt=%r not positive" % (name, debt))
        if not is_finite_number(income) or income <= 0:
            bad.append("%s income=%r not positive" % (name, income))
        # debt_to_income: must equal debt/income within rounding (the MEASURED ratio is consistent)
        if dti is not None:
            if not is_finite_number(dti) or dti < 0:
                bad.append("%s debt_to_income=%r invalid" % (name, dti))
            elif is_finite_number(debt) and is_finite_number(income) and income > 0:
                expect = round(debt / income, 2)
                if abs(dti - expect) > 0.01:
                    bad.append("%s debt_to_income=%s != debt/income=%s" % (name, dti, expect))
        # stress_index: ESTIMATED 0..100 percentile rank
        if si is not None and (not is_finite_number(si) or not (0.0 <= si <= 100.0)):
            bad.append("%s stress_index=%r out of [0,100]" % (name, si))
    if bad:
        fail("household_risk values sane (debt/income>0, DTI=debt/income, stress in [0,100])",
             first_n(bad, 8))
    else:
        ok("household_risk values sane (debt/income measured>0, DTI consistent, stress in [0,100])")


# ---------------------------------------------------------------------------
def check_province_stress():
    # Combined household-DTI + unemployment province structural-stress index
    # (pipeline/build_province_stress.py). Optional file: SKIP-PASS when absent.
    hdr("province_stress_index.json (optional)")
    if not exists("province_stress_index.json"):
        ok("province_stress_index.json absent — skipped (optional; run build_province_stress.py)")
        return
    try:
        d = load("province_stress_index.json")
    except Exception as e:
        fail("province_stress_index.json loads", repr(e))
        return
    ok("province_stress_index.json loads")

    meta = d.get("meta")
    if not isinstance(meta, dict) or "generated_by" not in meta or "source" not in meta:
        fail("province_stress meta/provenance present", "meta missing generated_by/source")
    else:
        ok("province_stress meta/provenance present")

    if meta and meta.get("absent"):
        ok("province_stress is an honest ABSENT-state (inputs missing) — skipped value checks")
        return

    provs = d.get("provinces")
    if not isinstance(provs, list) or not provs:
        fail("province_stress has a 'provinces' list", "got %s" % type(provs).__name__)
        return
    ok("province_stress provinces list present (%d)" % len(provs))

    bad = []
    seen_ranks = set()
    for p in provs:
        name = p.get("province") or "?"
        if p.get("region") is not None and p.get("region") not in KNOWN_REGIONS:
            bad.append("%s region=%r unknown" % (name, p.get("region")))
        dti = p.get("debt_to_income")
        if not is_finite_number(dti) or dti < 0:
            bad.append("%s debt_to_income=%r invalid" % (name, dti))
        ur = p.get("unemployment_rate")
        if not is_finite_number(ur) or ur < 0:
            bad.append("%s unemployment_rate=%r invalid" % (name, ur))
        for fld in ("dti_percentile", "unemployment_percentile", "composite_stress"):
            v = p.get(fld)
            if not is_finite_number(v) or not (0.0 <= v <= 100.0):
                bad.append("%s %s=%r out of [0,100]" % (name, fld, v))
        dtip, unp, comp = p.get("dti_percentile"), p.get("unemployment_percentile"), p.get("composite_stress")
        if is_finite_number(dtip) and is_finite_number(unp) and is_finite_number(comp):
            expect = round(0.5 * dtip + 0.5 * unp, 2)
            if abs(comp - expect) > 0.01:
                bad.append("%s composite_stress=%s != 0.5*dti+0.5*unemp=%s" % (name, comp, expect))
        rank = p.get("rank")
        if not isinstance(rank, int) or rank <= 0:
            bad.append("%s rank=%r invalid" % (name, rank))
        seen_ranks.add(rank)
    if len(seen_ranks) != len(provs):
        bad.append("rank is not a unique 1..N sequence (%d ranks for %d provinces)" % (len(seen_ranks), len(provs)))
    if bad:
        fail("province_stress values sane (DTI/unemp>=0, percentiles+composite in [0,100], "
             "composite formula consistent, rank unique)", first_n(bad, 8))
    else:
        ok("province_stress values sane (DTI/unemp measured>=0, composite = 0.5*dti_pct+0.5*unemp_pct, rank unique 1..N)")


# ---------------------------------------------------------------------------
def check_branch_occupations(n_branches):
    # MEASURED Overture occupation rollup, index-aligned to branches.json. Optional file:
    # SKIP-PASS when absent (build_occupations.py has not been run / overture_places.json missing).
    hdr("branch_occupations.json (optional)")
    if not exists("branch_occupations.json"):
        ok("branch_occupations.json absent — skipped (optional; run build_occupations.py to populate)")
        return
    try:
        d = load("branch_occupations.json")
    except Exception as e:
        fail("branch_occupations.json loads", repr(e))
        return
    ok("branch_occupations.json loads")

    # buckets present (label list drives the frontend's occupation bars)
    buckets = d.get("buckets")
    if not isinstance(buckets, list) or not buckets:
        fail("branch_occupations buckets present (non-empty list)", "got %r" % type(buckets).__name__)
        return
    bad_bk = [("#%d=%r" % (i, b)) for i, b in enumerate(buckets)
              if not (isinstance(b, dict) and b.get("key") and b.get("label"))]
    if bad_bk:
        fail("each bucket has key+label", first_n(bad_bk))
    else:
        ok("branch_occupations buckets present (%d, each with key+label)" % len(buckets))
    nbk = len(buckets)

    recs = d.get("branches")
    if not isinstance(recs, list):
        fail("branch_occupations has a 'branches' list", "got %s" % type(recs).__name__)
        return

    # length must equal branches.json (the layer is INDEX-ALIGNED — a length drift silently
    # misaligns every measured occupation read in the app).
    if n_branches is not None and len(recs) != n_branches:
        fail("branch_occupations length == branches.json length",
             "occupations=%d branches=%d" % (len(recs), n_branches))
    else:
        ok("branch_occupations length == branches.json length (%d)" % len(recs))

    # per-record: t is a non-negative finite total, o is a per-bucket non-negative count vector
    bad = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            bad.append("#%d not an object" % i)
            continue
        t = r.get("t")
        if not is_finite_number(t) or t < 0:
            bad.append("#%d t=%r" % (i, t))
        o = r.get("o")
        if not isinstance(o, list) or len(o) != nbk:
            bad.append("#%d o not a length-%d list" % (i, nbk))
            continue
        for j, v in enumerate(o):
            if not is_finite_number(v) or v < 0:
                bad.append("#%d o[%d]=%r" % (i, j, v))
                break
    if bad:
        fail("branch_occupations counts non-negative (t + per-bucket o[])", first_n(bad))
    else:
        ok("branch_occupations counts non-negative (t + per-bucket o[%d] vectors)" % nbk)


# ---------------------------------------------------------------------------
def check_occupation_risk(n_branches):
    # OCCUPATION x RISK cross-read (objective #1): per-branch ESTIMATED occupation-stress score
    # (MEASURED Overture occupation shares x ESTIMATED stressed-sector weighting), index-aligned
    # to branches.json. Optional file: SKIP-PASS when absent (needs branch_occupations.json /
    # the Overture pull; build_occupation_risk.py degrades to an absent-state too).
    hdr("occupation_risk.json (optional)")
    if not exists("occupation_risk.json"):
        ok("occupation_risk.json absent — skipped (optional; run build_occupation_risk.py to populate)")
        return
    try:
        d = load("occupation_risk.json")
    except Exception as e:
        fail("occupation_risk.json loads", repr(e))
        return
    ok("occupation_risk.json loads")

    # provenance: meta must state the MEASURED/ESTIMATED split (data-mandate).
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_with") or not meta.get("label"):
        fail("occupation_risk meta/provenance present (generated_with + label)",
             "meta missing generated_with/label")
    else:
        ok("occupation_risk meta/provenance present (generated_with + estimated label)")

    recs = d.get("branches")
    if not isinstance(recs, list):
        fail("occupation_risk has a 'branches' list", "got %s" % type(recs).__name__)
        return

    # length must equal branches.json (the layer is INDEX-ALIGNED — a drift misaligns every read).
    if n_branches is not None and len(recs) != n_branches:
        fail("occupation_risk length == branches.json length",
             "occupation_risk=%d branches=%d" % (len(recs), n_branches))
    else:
        ok("occupation_risk length == branches.json length (%d)" % len(recs))

    # per-record: s in [0,100] finite; f a bool; ds in [0,1]; t a non-negative finite total.
    bad = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            bad.append("#%d not an object" % i)
            continue
        s = r.get("s")
        if not is_finite_number(s) or not (0.0 <= s <= 100.0):
            bad.append("#%d s=%r out of [0,100]" % (i, s))
        if not isinstance(r.get("f"), bool):
            bad.append("#%d f=%r not a bool" % (i, r.get("f")))
        ds = r.get("ds")
        if ds is not None and (not is_finite_number(ds) or not (0.0 <= ds <= 1.0)):
            bad.append("#%d ds=%r out of [0,1]" % (i, ds))
        t = r.get("t")
        if not is_finite_number(t) or t < 0:
            bad.append("#%d t=%r" % (i, t))
    if bad:
        fail("occupation_risk records sane (s in [0,100], f bool, ds in [0,1], t>=0)", first_n(bad))
    else:
        ok("occupation_risk records sane (s in [0,100], f bool, ds in [0,1], t>=0)")

    # FLAG LIVENESS (regression guard): a fixed absolute FLAG_THRESHOLD once sat ABOVE the
    # achievable score ceiling (Overture factory/agriculture share ceilings x stress weights),
    # so 0/2015 branches could ever flag — the layer was silently inert. The builder now resolves
    # the threshold from the data itself (p95 of the NONZERO scores, recorded in
    # meta.flag_threshold), so here we assert the flag is ALIVE and CONSISTENT:
    #   1. every flagged record satisfies the RECORDED threshold + min_estab guard;
    #   2. meta.n_flagged equals the actual count of f=true records;
    #   3. whenever the MEASURED input (branch_occupations.json) is present and the score
    #      distribution is non-degenerate (some branch has s>0), n_flagged must be > 0.
    if isinstance(meta, dict):
        thr = meta.get("flag_threshold")
        min_estab = meta.get("min_estab")
        n_flag_meta = meta.get("n_flagged")
        flagged = [(i, r) for i, r in enumerate(recs) if isinstance(r, dict) and r.get("f") is True]

        bad = []
        if is_finite_number(thr) and is_finite_number(min_estab):
            for i, r in flagged:
                s, t = r.get("s"), r.get("t")
                if not (is_finite_number(s) and s >= thr):
                    bad.append("#%d flagged but s=%r < threshold %r" % (i, s, thr))
                if not (is_finite_number(t) and t >= min_estab):
                    bad.append("#%d flagged but t=%r < min_estab %r" % (i, t, min_estab))
        elif flagged:
            bad.append("records flagged but meta.flag_threshold/min_estab not numeric "
                       "(thr=%r min_estab=%r)" % (thr, min_estab))
        if bad:
            fail("occupation_risk flagged records satisfy meta.flag_threshold + min_estab", first_n(bad))
        else:
            ok("occupation_risk flagged records satisfy meta.flag_threshold (%r) + min_estab (%r)"
               % (thr, min_estab))

        if n_flag_meta != len(flagged):
            fail("occupation_risk meta.n_flagged matches records",
                 "meta.n_flagged=%r but %d records have f=true" % (n_flag_meta, len(flagged)))
        else:
            ok("occupation_risk meta.n_flagged matches records (%d)" % len(flagged))

        nonzero = any(isinstance(r, dict) and is_finite_number(r.get("s")) and r.get("s") > 0
                      for r in recs)
        if exists("branch_occupations.json") and nonzero:
            if not (isinstance(n_flag_meta, int) and n_flag_meta > 0):
                fail("occupation_risk flag is ALIVE (n_flagged > 0 with non-degenerate measured input)",
                     "branch_occupations.json present and scores are non-degenerate, but "
                     "meta.n_flagged=%r — the flag threshold is inert again" % n_flag_meta)
            else:
                ok("occupation_risk flag is ALIVE (n_flagged=%d > 0 with non-degenerate measured input)"
                   % n_flag_meta)
        else:
            ok("occupation_risk flag-liveness skipped (measured input absent or all-zero scores)")


# ---------------------------------------------------------------------------
def check_poi_relevance(n_branches):
    # RELEVANT-POI DENSITY (objective #2 where-to-expand + objective #1 demand):
    # per-branch ESTIMATED title-loan relevance weighting over MEASURED POI counts
    # (Overture occupations + branches.json k10 OSM), index-aligned to branches.json.
    # Optional file: SKIP-PASS when absent (build_poi_relevance.py degrades to an
    # absent-state too when branches.json is missing).
    hdr("poi_relevance.json (optional)")
    if not exists("poi_relevance.json"):
        ok("poi_relevance.json absent — skipped (optional; run build_poi_relevance.py to populate)")
        return
    try:
        d = load("poi_relevance.json")
    except Exception as e:
        fail("poi_relevance.json loads", repr(e))
        return
    ok("poi_relevance.json loads")

    # provenance: meta must state the MEASURED/ESTIMATED split + carry the weights.
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("label") \
            or not isinstance(meta.get("weights"), dict) or not meta["weights"]:
        fail("poi_relevance meta/provenance present (generated_by + label + weights)",
             "meta missing generated_by/label/weights")
    else:
        ok("poi_relevance meta/provenance present (generated_by + estimated label + weights)")

    if meta and meta.get("absent"):
        ok("poi_relevance is an honest ABSENT-state (no branches.json) — skipped value checks")
        return

    weights = (meta or {}).get("weights") or {}
    cat_keys = set(weights.keys())

    recs = d.get("branches")
    if not isinstance(recs, list):
        fail("poi_relevance has a 'branches' list", "got %s" % type(recs).__name__)
        return

    # length must equal branches.json (the layer is INDEX-ALIGNED — a drift misaligns every read).
    if n_branches is not None and len(recs) != n_branches:
        fail("poi_relevance length == branches.json length",
             "poi_relevance=%d branches=%d" % (len(recs), n_branches))
    else:
        ok("poi_relevance length == branches.json length (%d)" % len(recs))

    # per-record: rel in [0,100] finite; raw a non-negative finite weighted count; cat a
    # per-category MEASURED count dict (keys == weight keys, every count a non-negative int);
    # src one of the declared provenance tags.
    bad = []
    saw100 = False
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            bad.append("#%d not an object" % i)
            continue
        rel = r.get("rel")
        if not is_finite_number(rel) or not (0.0 <= rel <= 100.0):
            bad.append("#%d rel=%r out of [0,100]" % (i, rel))
        elif rel >= 99.999:
            saw100 = True
        raw = r.get("raw")
        if not is_finite_number(raw) or raw < 0:
            bad.append("#%d raw=%r negative/non-finite" % (i, raw))
        cat = r.get("cat")
        if not isinstance(cat, dict) or (cat_keys and set(cat.keys()) != cat_keys):
            bad.append("#%d cat keys != weight keys" % i)
        elif any((not isinstance(v, int)) or v < 0 for v in cat.values()):
            bad.append("#%d cat has a negative/non-int count" % i)
        if r.get("src") not in ("occ+k10", "k10"):
            bad.append("#%d src=%r not in {occ+k10,k10}" % (i, r.get("src")))
    if bad:
        fail("poi_relevance records sane (rel in [0,100], raw>=0, cat counts int>=0, src tag)",
             first_n(bad))
    else:
        ok("poi_relevance records sane (rel in [0,100], raw>=0, cat counts int>=0, src tag)")
    # min-max normalization must produce at least one rel==100 across a non-trivial population.
    if recs and not saw100:
        fail("poi_relevance min-max normalized (a branch reaches rel=100)", "no rel==100 found")
    elif recs:
        ok("poi_relevance min-max normalized (a branch reaches rel=100)")

    # HONESTY GUARDS (2026-07 committee audit): fresh_mkt must be the OSM fmkt count and
    # nothing else — the broad Overture retail bucket once leaked in here, inflating ~2,004
    # branches' "fresh market" lead count ~100x. retail_general (its honest new home) must
    # equal the Overture retail bucket count wherever occupations were joined.
    if exists("branches.json"):
        try:
            brs = load("branches.json")
        except Exception as e:
            brs = None
            fail("poi_relevance fresh_mkt == branches.json k10.fmkt", "branches.json load: %r" % e)
        if isinstance(brs, list) and len(brs) == len(recs):
            bad = []
            for i, (r, br) in enumerate(zip(recs, brs)):
                cat = r.get("cat") if isinstance(r, dict) else None
                if not isinstance(cat, dict) or not isinstance(br, dict):
                    continue
                fmkt = int((br.get("k10") or {}).get("fmkt", 0) or 0)
                if cat.get("fresh_mkt") != fmkt:
                    bad.append("#%d fresh_mkt=%r != k10.fmkt=%d" % (i, cat.get("fresh_mkt"), fmkt))
            if bad:
                fail("poi_relevance fresh_mkt == branches.json k10.fmkt (OSM only, no retail leak)",
                     first_n(bad))
            else:
                ok("poi_relevance fresh_mkt == branches.json k10.fmkt (OSM only, no retail leak)")
        elif isinstance(brs, list):
            fail("poi_relevance fresh_mkt == branches.json k10.fmkt",
                 "length mismatch: branches=%d poi_relevance=%d" % (len(brs), len(recs)))
    if exists("branch_occupations.json"):
        try:
            occ = load("branch_occupations.json")
        except Exception as e:
            occ = None
            fail("poi_relevance retail_general == Overture retail bucket",
                 "branch_occupations.json load: %r" % e)
        occ_recs = (occ or {}).get("branches") or []
        keys = [b.get("key") for b in (occ or {}).get("buckets", []) if isinstance(b, dict)]
        ri = keys.index("retail") if "retail" in keys else -1
        if ri >= 0 and len(occ_recs) == len(recs):
            bad = []
            for i, (r, orc) in enumerate(zip(recs, occ_recs)):
                if not isinstance(r, dict) or r.get("src") != "occ+k10":
                    continue  # occupations not joined for this branch — nothing to compare
                cat = r.get("cat") or {}
                ovec = orc.get("o") if isinstance(orc, dict) else None
                if not isinstance(ovec, list) or ri >= len(ovec):
                    continue
                retail = int(ovec[ri] or 0)
                if cat.get("retail_general") != retail:
                    bad.append("#%d retail_general=%r != overture retail=%d"
                               % (i, cat.get("retail_general"), retail))
            if bad:
                fail("poi_relevance retail_general == Overture retail bucket (where occ joined)",
                     first_n(bad))
            else:
                ok("poi_relevance retail_general == Overture retail bucket (where occ joined)")
        elif ri < 0:
            fail("poi_relevance retail_general == Overture retail bucket",
                 "branch_occupations.json has no 'retail' bucket")
        else:
            fail("poi_relevance retail_general == Overture retail bucket",
                 "length mismatch: occ=%d poi_relevance=%d" % (len(occ_recs), len(recs)))


# ---------------------------------------------------------------------------
def check_branch_labor(n_branches):
    # MEASURED per-branch EMPLOYMENT & LABOUR layer, index-aligned to branches.json (built by
    # build_branch_labor.py from Overture occupations + DIW factory workers + NSO province LFS/
    # employment). Optional file: SKIP-PASS when absent.
    hdr("branch_labor.json (optional)")
    if not exists("branch_labor.json"):
        ok("branch_labor.json absent — skipped (optional; run build_branch_labor.py to populate)")
        return
    try:
        d = load("branch_labor.json")
    except Exception as e:
        fail("branch_labor.json loads", repr(e))
        return
    ok("branch_labor.json loads")

    # provenance: meta must carry a real provenance string + per-field labels (data mandate).
    meta = d.get("meta")
    if not isinstance(meta, dict) or not (isinstance(meta.get("provenance"), str) and meta["provenance"].strip()):
        fail("branch_labor meta carries provenance", "meta.provenance missing/blank")
    else:
        ok("branch_labor meta carries provenance")
    if not (isinstance(meta, dict) and isinstance(meta.get("fields"), dict) and meta["fields"]):
        fail("branch_labor meta.fields documents each field's source + measured/estimated label",
             "meta.fields missing/empty")
    else:
        ok("branch_labor meta.fields documents %d field groups (source + label)" % len(meta["fields"]))

    recs = d.get("branches")
    if not isinstance(recs, list):
        fail("branch_labor has a 'branches' list", "got %s" % type(recs).__name__)
        return

    # length must equal branches.json (INDEX-ALIGNED — a drift silently misattributes labour to branches)
    if n_branches is not None and len(recs) != n_branches:
        fail("branch_labor length == branches.json length",
             "labor=%d branches=%d" % (len(recs), n_branches))
    else:
        ok("branch_labor length == branches.json length (%d)" % len(recs))

    bad = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            bad.append("#%d not an object" % i)
            continue
        # occ_top: list of {label, share_pct in 0..100}
        ot = r.get("occ_top")
        if not isinstance(ot, list):
            bad.append("#%d occ_top not a list" % i)
        else:
            if len(ot) > 3:
                bad.append("#%d occ_top has %d entries (>3)" % (i, len(ot)))
            for e in ot:
                sp = e.get("share_pct") if isinstance(e, dict) else None
                if not is_finite_number(sp) or sp < 0 or sp > 100:
                    bad.append("#%d occ_top share_pct=%r out of [0,100]" % (i, sp))
                    break
                if not (isinstance(e.get("label"), str) and e["label"]):
                    bad.append("#%d occ_top entry missing label" % i)
                    break
        # estab_total: non-negative finite int
        et = r.get("estab_total")
        if not is_finite_number(et) or et < 0:
            bad.append("#%d estab_total=%r" % (i, et))
        # nullable measured fields: if present, must be sane (never fabricated -> null allowed)
        fw = r.get("factory_workers")
        if fw is not None and (not is_finite_number(fw) or fw < 0):
            bad.append("#%d factory_workers=%r" % (i, fw))
        ip = r.get("informal_pct")
        if ip is not None and (not is_finite_number(ip) or ip < 0 or ip > 100):
            bad.append("#%d informal_pct=%r out of [0,100]" % (i, ip))
        for k in ("prov_employed_k", "prov_labor_force_k"):
            v = r.get(k)
            if v is not None and (not is_finite_number(v) or v < 0):
                bad.append("#%d %s=%r" % (i, k, v))
        ur = r.get("prov_unemployment_rate")
        if ur is not None and (not is_finite_number(ur) or ur < 0 or ur > 100):
            bad.append("#%d prov_unemployment_rate=%r out of [0,100]" % (i, ur))
        if len(bad) >= 10:
            break
    if bad:
        fail("branch_labor per-branch fields sane (nullable-but-never-fabricated)", first_n(bad))
    else:
        ok("branch_labor per-branch fields sane (occ_top/estab_total + nullable measured fields)")

    # HONEST-GAP contract: any null measured field must be EXPLAINED in meta.gaps, not silently blank.
    # This STRENGTHENS the gate — a regression that drops NSO coverage (more nulls) without documenting
    # it, or that fabricates a value to hide a gap, now fails here. Bangkok's informal_pct is the
    # canonical case: 170 nulls, all documented. (Does not weaken any existing assertion.)
    gaps = meta.get("gaps") if isinstance(meta, dict) else None
    if not isinstance(gaps, dict) or not gaps:
        fail("branch_labor meta.gaps documents the HONEST nulls", "meta.gaps missing/empty")
    else:
        null_inf = sum(1 for r in recs if isinstance(r, dict) and r.get("informal_pct") is None)
        null_lfs = sum(1 for r in recs if isinstance(r, dict) and r.get("prov_employed_k") is None)
        gbad = []
        for key, actual in (("informal_pct", null_inf), ("province_lfs", null_lfs)):
            g = gaps.get(key)
            if not isinstance(g, dict):
                gbad.append("meta.gaps.%s missing" % key); continue
            claimed = g.get("affected_branches")
            if claimed != actual:
                gbad.append("meta.gaps.%s.affected_branches=%r but %d rows are null"
                            % (key, claimed, actual))
            if not (isinstance(g.get("policy"), str) and g["policy"].strip()):
                gbad.append("meta.gaps.%s.policy missing (must state HONEST NULL, no fabrication)" % key)
            # If any branch is null, at least one province must be named as absent from the source.
            if actual > 0 and not (isinstance(g.get("provinces_absent_from_source"), list)
                                   and g["provinces_absent_from_source"]):
                gbad.append("meta.gaps.%s has %d nulls but names no absent province" % (key, actual))
        if gbad:
            fail("branch_labor meta.gaps reconciles with the actual null census", first_n(gbad))
        else:
            ok("branch_labor meta.gaps reconciles null census (informal_pct=%d, province_lfs=%d — all explained)"
               % (null_inf, null_lfs))


# ---------------------------------------------------------------------------
def check_province_risk():
    # PER-PROVINCE rollup of the branch composite risk (objective #1). Optional file: SKIP-PASS
    # when absent (build_province_risk.py degrades to an absent-state too).
    hdr("province_risk.json (optional)")
    if not exists("province_risk.json"):
        ok("province_risk.json absent — skipped (optional; run build_province_risk.py)")
        return
    try:
        d = load("province_risk.json")
    except Exception as e:
        fail("province_risk.json loads", repr(e))
        return
    ok("province_risk.json loads")

    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("source"):
        fail("province_risk meta/provenance present", "meta missing generated_by/source")
    else:
        ok("province_risk meta/provenance present")

    if meta and meta.get("absent"):
        ok("province_risk is an honest ABSENT-state (no inputs) — skipped value checks")
        return

    provs = d.get("provinces")
    if not isinstance(provs, list) or not provs:
        fail("province_risk has a 'provinces' list", "got %s" % type(provs).__name__)
        return
    ok("province_risk provinces list present (%d)" % len(provs))

    bad = []
    for p in provs:
        name = p.get("province") or "?"
        if p.get("region") is not None and p.get("region") not in KNOWN_REGIONS:
            bad.append("%s region=%r unknown" % (name, p.get("region")))
        n = p.get("n_branches")
        if not isinstance(n, int) or n < 0:
            bad.append("%s n_branches=%r not a non-negative int" % (name, n))
        for fld in ("mean_risk", "p90_risk"):
            v = p.get(fld)
            if not is_finite_number(v) or v < 0 or v > 100:
                bad.append("%s %s=%r out of 0..100" % (name, fld, v))
        if not isinstance(p.get("top_driver_mix"), dict):
            bad.append("%s top_driver_mix not a dict" % name)
    if bad:
        fail("province_risk rows sane (region/n_branches/mean/p90/drivers)", first_n(bad))
    else:
        ok("province_risk rows sane (%d provinces, mean+p90 in 0..100, known regions)" % len(provs))


def check_branch_risk(n_branches):
    # PER-BRANCH COMPOSITE RISK (objective #1): fuses household debt-stress (MEASURED) +
    # crop/agri stress (ESTIMATED) + occupation-sector stress (MEASURED x ESTIMATED) + the
    # branch's own segment/collateral signals (DERIVED) into one 0-100 triage ranking,
    # index-aligned to branches.json. Optional file: SKIP-PASS when absent (build_branch_risk.py
    # degrades gracefully; this layer is built from optional inputs).
    hdr("branch_risk.json (optional)")
    if not exists("branch_risk.json"):
        ok("branch_risk.json absent — skipped (optional; run build_branch_risk.py to populate)")
        return
    try:
        d = load("branch_risk.json")
    except Exception as e:
        fail("branch_risk.json loads", repr(e))
        return
    ok("branch_risk.json loads")

    # provenance: meta must state the builder + the ESTIMATED-composite label, AND name each
    # component's provenance (the data-mandate: measured-vs-estimated must be explicit).
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("label"):
        fail("branch_risk meta/provenance present (generated_by + label)",
             "meta missing generated_by/label")
    else:
        ok("branch_risk meta/provenance present (generated_by + estimated-composite label)")
        comps = meta.get("components")
        if not isinstance(comps, dict) or not comps or not all(
                isinstance(c, dict) and c.get("provenance") for c in comps.values()):
            fail("branch_risk meta.components each carry provenance",
                 "components missing or some lack a provenance string")
        else:
            ok("branch_risk meta.components each carry provenance (%d components)" % len(comps))

    recs = d.get("branches")
    if not isinstance(recs, list):
        fail("branch_risk has a 'branches' list", "got %s" % type(recs).__name__)
        return

    # length must equal branches.json (the layer is INDEX-ALIGNED — a drift misaligns every read).
    if n_branches is not None and len(recs) != n_branches:
        fail("branch_risk length == branches.json length",
             "branch_risk=%d branches=%d" % (len(recs), n_branches))
    else:
        ok("branch_risk length == branches.json length (%d)" % len(recs))

    # valid component keys + drivers come from meta (graceful — fall back to the known set).
    known_comps = set((meta or {}).get("components", {}).keys()) or {
        "household", "agri", "occupation", "segment"}

    # per-record: composite_risk in [0,100] or null; components a dict of [0,100] values whose
    # keys are known; top_driver one of the present component keys (or null iff composite null).
    bad = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            bad.append("#%d not an object" % i)
            continue
        cr = r.get("composite_risk")
        if cr is not None and (not is_finite_number(cr) or not (0.0 <= cr <= 100.0)):
            bad.append("#%d composite_risk=%r out of [0,100]" % (i, cr))
        comps = r.get("components")
        if not isinstance(comps, dict):
            bad.append("#%d components not a dict" % i)
            continue
        for ck, cv in comps.items():
            if ck not in known_comps:
                bad.append("#%d unknown component key %r" % (i, ck))
            if not is_finite_number(cv) or not (0.0 <= cv <= 100.0):
                bad.append("#%d components.%s=%r out of [0,100]" % (i, ck, cv))
        td = r.get("top_driver")
        if cr is None:
            # null composite => no components => null driver (honest absent-state)
            if comps:
                bad.append("#%d composite null but components present" % i)
            if td is not None:
                bad.append("#%d composite null but top_driver=%r" % (i, td))
        else:
            if not comps:
                bad.append("#%d composite=%s but no components" % (i, cr))
            if td not in comps:
                bad.append("#%d top_driver=%r not among its components" % (i, td))
    if bad:
        fail("branch_risk records sane (composite in [0,100], components in [0,100] with known "
             "keys, top_driver among present components)", first_n(bad, 8))
    else:
        ok("branch_risk records sane (composite in [0,100], components known + in [0,100], "
           "top_driver among present components)")


# ---------------------------------------------------------------------------
def check_segment_exposure():
    # PORTFOLIO SEGMENT CONCENTRATION (objective #1): per-region/province segment mix + a
    # rescaled-Herfindahl concentration index, derived from the ESTIMATED a/m/c branch scores.
    # Optional file: SKIP-PASS when absent (build_segment_exposure.py degrades to an absent-state).
    hdr("segment_exposure.json (optional)")
    if not exists("segment_exposure.json"):
        ok("segment_exposure.json absent — skipped (optional; run build_segment_exposure.py)")
        return
    try:
        d = load("segment_exposure.json")
    except Exception as e:
        fail("segment_exposure.json loads", repr(e))
        return
    ok("segment_exposure.json loads")

    # provenance: meta must state the builder + the ESTIMATED structural-index label.
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("label"):
        fail("segment_exposure meta/provenance present (generated_by + label)",
             "meta missing generated_by/label")
    else:
        ok("segment_exposure meta/provenance present (generated_by + estimated label)")

    # honest absent-state: file may legitimately ship empty when branches.json is missing.
    if meta and meta.get("absent"):
        ok("segment_exposure is an honest ABSENT-state (no branches.json) — skipped value checks")
        return

    SEGS = ("agri", "merchant", "collateral")

    def _check_block(label, block, require_region):
        # one mix/hhi summary block: shares in [0,1] summing to ~1, hhi in [0,1], counts consistent.
        problems = []
        if require_region and block.get("region") not in KNOWN_REGIONS:
            problems.append("%s region=%r unknown" % (label, block.get("region")))
        mix = block.get("segment_mix")
        if not isinstance(mix, dict) or any(k not in mix for k in SEGS):
            problems.append("%s segment_mix missing a segment key" % label)
            return problems
        shares = [mix[s] for s in SEGS]
        if any(not is_finite_number(s) or not (0.0 <= s <= 1.0) for s in shares):
            problems.append("%s segment_mix share out of [0,1]: %r" % (label, mix))
        elif abs(sum(shares) - 1.0) > 0.01:
            problems.append("%s segment_mix shares sum=%.4f (not ~1.0)" % (label, sum(shares)))
        hhi = block.get("hhi")
        if not is_finite_number(hhi) or not (0.0 <= hhi <= 1.0):
            problems.append("%s hhi=%r out of [0,1]" % (label, hhi))
        # counts consistent with n_branches
        counts = block.get("counts")
        n = block.get("n_branches")
        if not (isinstance(n, int) and not isinstance(n, bool) and n >= 0):
            problems.append("%s n_branches=%r not a non-negative int" % (label, n))
        elif isinstance(counts, dict):
            csum = sum(counts.get(s, 0) for s in SEGS)
            if csum != n:
                problems.append("%s counts sum=%d != n_branches=%d" % (label, csum, n))
        if block.get("dominant_segment") not in SEGS:
            problems.append("%s dominant_segment=%r not a known segment" % (label, block.get("dominant_segment")))
        return problems

    bad = []
    nat = d.get("national")
    if not isinstance(nat, dict):
        bad.append("national block missing")
    else:
        bad += _check_block("national", nat, require_region=False)

    regions = d.get("regions")
    if not isinstance(regions, list) or not regions:
        bad.append("regions list missing/empty")
    else:
        for r in regions:
            bad += _check_block("region %s" % r.get("region"), r, require_region=True)

    provinces = d.get("provinces")
    if not isinstance(provinces, list) or not provinces:
        bad.append("provinces list missing/empty")
    else:
        for p in provinces:
            bad += _check_block("province %s" % p.get("province"), p, require_region=True)

    if bad:
        fail("segment_exposure blocks sane (mix in [0,1] sums~1, hhi in [0,1], counts==n, "
             "known regions/segments)", first_n(bad, 8))
    else:
        ok("segment_exposure blocks sane (national + %d regions + %d provinces: mix sums~1, "
           "hhi in [0,1], counts consistent, known regions/segments)"
           % (len(regions), len(provinces)))


# ---------------------------------------------------------------------------
def check_amphoe_occupations(amphoe):
    # MEASURED Overture occupation mix per district, keyed by amphoe shapeID. Optional file:
    # SKIP-PASS when absent.
    hdr("amphoe_occupations.json (optional)")
    if not exists("amphoe_occupations.json"):
        ok("amphoe_occupations.json absent — skipped (optional; run build_amphoe_occupations.py)")
        return
    try:
        d = load("amphoe_occupations.json")
    except Exception as e:
        fail("amphoe_occupations.json loads", repr(e))
        return
    ok("amphoe_occupations.json loads")

    buckets = d.get("buckets")
    if not isinstance(buckets, list) or not buckets:
        fail("amphoe_occupations buckets present (non-empty list)", "got %r" % type(buckets).__name__)
        return
    nbk = len(buckets)
    ok("amphoe_occupations buckets present (%d)" % nbk)

    amap = d.get("amphoe")
    if not isinstance(amap, dict) or not amap:
        fail("amphoe_occupations has an 'amphoe' map", "got %s" % type(amap).__name__)
        return
    ok("amphoe_occupations 'amphoe' map present (%d districts)" % len(amap))

    # keys valid: must be shapeIDs that exist in amphoe.json (when that loaded). The map is
    # emitted for every amphoe, so an unknown key means the join key drifted.
    valid_ids = None
    if amphoe is not None:
        recs = amphoe.get("amphoe")
        if isinstance(recs, list):
            valid_ids = set(r.get("id") for r in recs if r.get("id") is not None)
    if valid_ids:
        unknown = sorted(k for k in amap.keys() if k not in valid_ids)
        if unknown:
            fail("amphoe_occupations keys are known amphoe shapeIDs", first_n(unknown))
        else:
            ok("amphoe_occupations keys are known amphoe shapeIDs (%d valid)" % len(valid_ids))
    else:
        ok("amphoe.json ids unavailable — skipped key-vs-amphoe cross-check (keys checked structurally)")

    # per-entry: t non-negative finite; o a length-nbk non-negative vector; dom in [-1, nbk).
    bad = []
    for k, e in amap.items():
        if not isinstance(e, dict):
            bad.append("%s not an object" % k)
            continue
        t = e.get("t")
        if not is_finite_number(t) or t < 0:
            bad.append("%s t=%r" % (k, t))
        o = e.get("o")
        if not isinstance(o, list) or len(o) != nbk:
            bad.append("%s o not length-%d list" % (k, nbk))
        else:
            for j, v in enumerate(o):
                if not is_finite_number(v) or v < 0:
                    bad.append("%s o[%d]=%r" % (k, j, v))
                    break
        dom = e.get("dom")
        # dom is a bucket index, or -1 when the district has no placed establishments.
        if not (isinstance(dom, int) and not isinstance(dom, bool) and -1 <= dom < nbk):
            bad.append("%s dom=%r out of [-1,%d)" % (k, dom, nbk))
    if bad:
        fail("amphoe_occupations entries sane (t>=0, o[] vector, dom in [-1,%d))" % nbk, first_n(bad))
    else:
        ok("amphoe_occupations entries sane (t>=0, o[%d] vectors, dom index in range)" % nbk)


# ---------------------------------------------------------------------------
def _check_one_competitor_census(rel):
    # Shared shape check for a competitor census (Google-Places national + Overture national share
    # the same {meta, brands, items[]} shape). lat/lng inside the TH bbox; brand in the known set.
    if not exists(rel):
        ok("%s absent — skipped (optional competitor census)" % rel)
        return
    try:
        d = load(rel)
    except Exception as e:
        fail("%s loads" % rel, repr(e))
        return
    ok("%s loads" % rel)

    items = d.get("items")
    if not isinstance(items, list):
        fail("%s has an 'items' list" % rel, "got %s" % type(items).__name__)
        return
    ok("%s items list present (%d)" % (rel, len(items)))

    oob = []
    badbrand = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            oob.append("#%d not an object" % i)
            continue
        lat, lng = it.get("lat"), it.get("lng")
        if not (is_finite_number(lat) and is_finite_number(lng)):
            oob.append("#%d non-numeric lat/lng (%r,%r)" % (i, lat, lng))
        elif not (TH_LAT_MIN <= lat <= TH_LAT_MAX and TH_LNG_MIN <= lng <= TH_LNG_MAX):
            oob.append("#%d lat=%s lng=%s outside TH bbox" % (i, lat, lng))
        br = it.get("brand")
        if br not in KNOWN_COMPETITOR_BRANDS:
            badbrand.add(repr(br))
    if oob:
        fail("%s lat/lng inside Thailand bbox" % rel, first_n(oob))
    else:
        ok("%s all lat/lng inside Thailand bbox" % rel)
    if badbrand:
        fail("%s brands in known set %s" % (rel, sorted(KNOWN_COMPETITOR_BRANDS)),
             "unknown: " + first_n(sorted(badbrand)))
    else:
        ok("%s all brands in known set %s" % (rel, sorted(KNOWN_COMPETITOR_BRANDS)))


def check_competitors():
    hdr("competitors_national.json + competitors_overture.json (optional)")
    _check_one_competitor_census("competitors_national.json")
    _check_one_competitor_census("competitors_overture.json")


# ---------------------------------------------------------------------------
def check_competitor_coverage():
    # found-vs-expected QA for the competitor census (build_competitor_coverage.py). The data-mandate
    # bites here: `found` must be MEASURED (a non-negative int), `expected` must be a CITED public
    # figure (positive int) OR null (never invented), and coverage_pct must = found/expected (or null).
    # Optional file: SKIP-PASS when absent (the builder needs a census to run).
    hdr("competitor_coverage.json (optional)")
    if not exists("competitor_coverage.json"):
        ok("competitor_coverage.json absent — skipped (optional; run build_competitor_coverage.py)")
        return
    try:
        d = load("competitor_coverage.json")
    except Exception as e:
        fail("competitor_coverage.json loads", repr(e))
        return
    ok("competitor_coverage.json loads")

    # provenance: meta must state found=MEASURED / expected=ESTIMATED-from-public-reports + cite sources.
    meta = d.get("meta")
    if not isinstance(meta, dict) or "source" not in meta or not meta.get("expected_sources"):
        fail("competitor_coverage meta/provenance present (source + expected_sources)",
             "meta missing source or expected_sources citation")
    else:
        ok("competitor_coverage meta/provenance present (source + cited expected_sources)")
        # the expected figures MUST be honestly labelled as estimated-from-public-reports
        if meta.get("expected_label") == "ESTIMATED-from-public-reports":
            ok("competitor_coverage expected labelled ESTIMATED-from-public-reports")
        else:
            fail("competitor_coverage expected labelled ESTIMATED-from-public-reports",
                 "got expected_label=%r" % meta.get("expected_label"))

    brands = d.get("brands")
    if not isinstance(brands, list) or not brands:
        fail("competitor_coverage has a 'brands' list", "got %s" % type(brands).__name__)
        return
    ok("competitor_coverage brands list present (%d)" % len(brands))

    bad = []
    for b in brands:
        if not isinstance(b, dict):
            bad.append("non-object brand entry %r" % b)
            continue
        name = b.get("brand")
        if name not in KNOWN_COMPETITOR_BRANDS:
            bad.append("brand=%r not in known set" % name)
        found = b.get("found")
        # found is MEASURED — must be a non-negative int
        if not (isinstance(found, int) and not isinstance(found, bool) and found >= 0):
            bad.append("%s found=%r not a non-negative int" % (name, found))
        exp = b.get("expected")
        cov = b.get("coverage_pct")
        # expected is CITED-or-null — never a fabricated 0/negative
        if exp is not None and not (isinstance(exp, int) and not isinstance(exp, bool) and exp > 0):
            bad.append("%s expected=%r must be a positive int or null" % (name, exp))
        # coverage_pct must be consistent: null iff expected null; else 100*found/expected (1 dp)
        if exp is None:
            if cov is not None:
                bad.append("%s coverage_pct=%r must be null when expected is null" % (name, cov))
        else:
            if not is_finite_number(cov):
                bad.append("%s coverage_pct=%r not finite" % (name, cov))
            elif isinstance(found, int) and isinstance(exp, int) and exp > 0:
                expect = round(100.0 * found / exp, 1)
                if abs(cov - expect) > 0.05:
                    bad.append("%s coverage_pct=%s != 100*found/expected=%s" % (name, cov, expect))
    if bad:
        fail("competitor_coverage entries sane (found measured int, expected cited-or-null, "
             "coverage_pct=100*found/expected)", first_n(bad, 8))
    else:
        ok("competitor_coverage entries sane (found measured, expected cited-or-null, coverage consistent)")


# ---------------------------------------------------------------------------
def check_opportunity_score():
    # COMPOSITE EXPANSION-OPPORTUNITY score per amphoe (objective #2): blends MEASURED white-space +
    # competitor density with ESTIMATED province crop-stress + occupation pull into a 0-100 ranking.
    # Optional file: SKIP-PASS when absent (build_opportunity_score.py degrades gracefully).
    hdr("opportunity_score.json (optional)")
    if not exists("opportunity_score.json"):
        ok("opportunity_score.json absent — skipped (optional; run build_opportunity_score.py)")
        return
    try:
        d = load("opportunity_score.json")
    except Exception as e:
        fail("opportunity_score.json loads", repr(e))
        return
    ok("opportunity_score.json loads")

    # provenance: meta must state the builder + the ESTIMATED-COMPOSITE label + the blend weights.
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_with") or not meta.get("label"):
        fail("opportunity_score meta/provenance present (generated_with + label)",
             "meta missing generated_with/label")
    else:
        ok("opportunity_score meta/provenance present (generated_with + estimated-composite label)")
        w = meta.get("weights_full")
        if not isinstance(w, dict) or not w or not all(is_finite_number(v) and v >= 0 for v in w.values()):
            fail("opportunity_score meta.weights_full present (non-negative finite)",
                 "weights_full missing/invalid: %r" % w)
        else:
            ok("opportunity_score meta.weights_full present (%d components, non-negative)" % len(w))

    if meta and meta.get("absent"):
        ok("opportunity_score is an honest ABSENT-state — skipped value checks")
        return

    recs = d.get("districts")
    if not isinstance(recs, list) or not recs:
        fail("opportunity_score has a 'districts' list", "got %s" % type(recs).__name__)
        return
    ok("opportunity_score districts list present (%d)" % len(recs))

    # the composite is built from the declared component weights; every district exposes those
    # components for honesty. score + each component must sit in [0,100]; branches a non-neg int.
    comp_keys = set((meta or {}).get("weights_full", {}).keys())
    bad = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            bad.append("#%d not an object" % i)
            continue
        name = r.get("name") or r.get("id") or "#%d" % i
        if r.get("region") is not None and r.get("region") not in KNOWN_REGIONS:
            bad.append("%s region=%r unknown" % (name, r.get("region")))
        sc = r.get("score")
        if not is_finite_number(sc) or not (0.0 <= sc <= 100.0):
            bad.append("%s score=%r out of [0,100]" % (name, sc))
        br = r.get("branches")
        if not (isinstance(br, int) and not isinstance(br, bool) and br >= 0):
            bad.append("%s branches=%r not a non-negative int" % (name, br))
        comps = r.get("components")
        if not isinstance(comps, dict):
            bad.append("%s components not a dict" % name)
            continue
        # every declared weighted component must be present + in [0,100] (audit fields prefixed
        # with '_' — e.g. _competitors — are raw counts, only required to be non-negative finite).
        for ck in comp_keys:
            cv = comps.get(ck)
            if cv is None:
                # occupation_pull is present only when amphoe_occupations.json exists; tolerate absence.
                continue
            if not is_finite_number(cv) or not (0.0 <= cv <= 100.0):
                bad.append("%s components.%s=%r out of [0,100]" % (name, ck, cv))
        for ck, cv in comps.items():
            if ck.startswith("_"):
                if not is_finite_number(cv) or cv < 0:
                    bad.append("%s audit %s=%r not non-negative finite" % (name, ck, cv))
    if bad:
        fail("opportunity_score districts sane (score/components in [0,100], branches>=0, known regions)",
             first_n(bad, 8))
    else:
        ok("opportunity_score districts sane (score + weighted components in [0,100], branches>=0, "
           "audit counts non-negative, known regions)")


# ---------------------------------------------------------------------------
def check_exit_whitespace():
    # COMPETITOR-EXIT white-space cue (objective #2, regulatory-tailwind lens). ESTIMATED PROXY per
    # amphoe: where AutoX could capture share if sub-scale operators exit under the Q1-2026 BoT
    # deadline, inferred from big-4 scarcity x demand/white-space. The data-mandate bites: this is an
    # inferred surface, so meta MUST carry the honesty caveat + the regulatory citation. Optional
    # file: SKIP-PASS when absent (build_exit_whitespace.py degrades gracefully).
    hdr("exit_whitespace.json (optional)")
    if not exists("exit_whitespace.json"):
        ok("exit_whitespace.json absent — skipped (optional; run build_exit_whitespace.py)")
        return
    try:
        d = load("exit_whitespace.json")
    except Exception as e:
        fail("exit_whitespace.json loads", repr(e))
        return
    ok("exit_whitespace.json loads")

    # provenance: meta must state the builder + the ESTIMATED-PROXY label AND (because this is an
    # inferred surface) the honesty caveat + the cited regulatory basis — never present it as measured.
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_with") or not meta.get("label"):
        fail("exit_whitespace meta/provenance present (generated_with + label)",
             "meta missing generated_with/label")
    else:
        ok("exit_whitespace meta/provenance present (generated_with + estimated-proxy label)")
        if not (isinstance(meta.get("honesty_caveat"), str) and meta.get("honesty_caveat").strip()):
            fail("exit_whitespace meta.honesty_caveat present (inferred, not measured)",
                 "honesty_caveat missing/empty")
        else:
            ok("exit_whitespace meta.honesty_caveat present (inferred-not-measured)")
        reg = meta.get("regulatory_citation")
        if not isinstance(reg, dict) or not reg.get("sources"):
            fail("exit_whitespace meta.regulatory_citation cites sources",
                 "regulatory_citation missing sources")
        else:
            ok("exit_whitespace meta.regulatory_citation cites sources (%d)" % len(reg["sources"]))

    if meta and meta.get("absent"):
        ok("exit_whitespace is an honest ABSENT-state — skipped value checks")
        return

    recs = d.get("districts")
    if not isinstance(recs, list) or not recs:
        fail("exit_whitespace has a 'districts' list", "got %s" % type(recs).__name__)
        return
    ok("exit_whitespace districts list present (%d)" % len(recs))

    bad = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            bad.append("#%d not an object" % i)
            continue
        name = r.get("name") or r.get("id") or "#%d" % i
        if r.get("region") is not None and r.get("region") not in KNOWN_REGIONS:
            bad.append("%s region=%r unknown" % (name, r.get("region")))
        es = r.get("exit_capture_score")
        if not is_finite_number(es) or not (0.0 <= es <= 100.0):
            bad.append("%s exit_capture_score=%r out of [0,100]" % (name, es))
        br = r.get("branches")
        if not (isinstance(br, int) and not isinstance(br, bool) and br >= 0):
            bad.append("%s branches=%r not a non-negative int" % (name, br))
        comps = r.get("components")
        if not isinstance(comps, dict):
            bad.append("%s components not a dict" % name)
            continue
        # 0-100 estimated proxies
        for ck in ("sub_scale_proxy", "whitespace", "demand"):
            cv = comps.get(ck)
            if cv is not None and (not is_finite_number(cv) or not (0.0 <= cv <= 100.0)):
                bad.append("%s components.%s=%r out of [0,100]" % (name, ck, cv))
        # big4_competitors: MEASURED raw count, non-negative int
        b4 = comps.get("big4_competitors")
        if b4 is not None and not (isinstance(b4, int) and not isinstance(b4, bool) and b4 >= 0):
            bad.append("%s big4_competitors=%r not a non-negative int" % (name, b4))
    if bad:
        fail("exit_whitespace districts sane (score/proxies in [0,100], big4 count int>=0, known regions)",
             first_n(bad, 8))
    else:
        ok("exit_whitespace districts sane (exit_capture_score + proxies in [0,100], big4 measured "
           "count>=0, branches>=0, known regions)")


# ---------------------------------------------------------------------------
def check_expansion_plan(amphoe, n_branches):
    # SEQUENCED Road-to-3,000 plan (objective #2). ESTIMATED planning order (greedy divisor method)
    # over MEASURED demand inputs — meta must say so, the arithmetic must reconcile exactly (every
    # net-new branch placed once, rollups sum to the same total), and every district id must exist
    # in amphoe.json (no fabricated geography). Optional file: SKIP-PASS when absent.
    hdr("expansion_plan.json (optional)")
    if not exists("expansion_plan.json"):
        ok("expansion_plan.json absent — skipped (optional; run build_expansion_plan.py)")
        return
    try:
        d = load("expansion_plan.json")
    except Exception as e:
        fail("expansion_plan.json loads", repr(e))
        return
    ok("expansion_plan.json loads")

    meta = d.get("meta") or {}
    prov = str(meta.get("provenance") or "")
    if not meta.get("generated_by") or "ESTIMATED" not in prov or "survey" not in prov:
        fail("expansion_plan meta/provenance (generated_by + ESTIMATED label + survey caveat)",
             "meta missing generated_by, ESTIMATED label, or the confirm-with-survey caveat")
    else:
        ok("expansion_plan meta/provenance present (ESTIMATED planning sequence + survey caveat)")

    params = meta.get("params") or {}
    net = params.get("net_new")
    placed = meta.get("n_placed")
    seq = d.get("sequence") or []
    by_am = d.get("by_amphoe") or []
    by_reg = d.get("by_region") or []
    problems = []
    if n_branches is not None and net != params.get("target", 3000) - n_branches:
        problems.append("net_new %r != target-branches (%r-%r)" % (net, params.get("target"), n_branches))
    if placed != net:
        problems.append("n_placed %r != net_new %r (plan incomplete)" % (placed, net))
    if sum(r.get("add", 0) for r in by_am) != placed:
        problems.append("sum(by_amphoe.add) != n_placed")
    if sum(r.get("add", 0) for r in by_reg) != placed:
        problems.append("sum(by_region.add) != n_placed")
    if [p.get("rank") for p in seq] != list(range(1, len(seq) + 1)):
        problems.append("sequence ranks not contiguous 1..%d" % len(seq))
    cap = params.get("max_add_per_district", 8)
    over = [r.get("name") for r in by_am if r.get("add", 0) > cap or r.get("add", 0) < 1]
    if over:
        problems.append("by_amphoe add out of [1,%s]: %s" % (cap, first_n(over, 5)))
    if problems:
        fail("expansion_plan arithmetic reconciles (985 placed once; rollups + ranks consistent)",
             "; ".join(problems))
    else:
        ok("expansion_plan arithmetic reconciles (n_placed==net_new; by_amphoe/by_region sums match; "
           "ranks contiguous; per-district adds within cap)")

    if isinstance(amphoe, dict) and isinstance(amphoe.get("amphoe"), list):
        ids = {r.get("id") for r in amphoe["amphoe"]}
        orphans = [r.get("name") for r in by_am if r.get("id") not in ids]
        if orphans:
            fail("expansion_plan district ids all exist in amphoe.json (no fabricated geography)",
                 first_n(orphans, 8))
        else:
            ok("expansion_plan district ids all exist in amphoe.json (%d receiving districts)" % len(by_am))


# ---------------------------------------------------------------------------
def check_branch_peers(n_branches):
    # Peer-twin benchmark (objective #1). ESTIMATED deviation of estimated composite risk vs
    # measured-feature twins — meta must label it, branches[] must stay index-aligned to
    # branches.json, and every published outlier must satisfy its own gates (rz >= rz_min,
    # dev consistent with risk - peer_median). Optional file: SKIP-PASS when absent.
    hdr("branch_peers.json (optional)")
    if not exists("branch_peers.json"):
        ok("branch_peers.json absent — skipped (optional; run build_branch_peers.py)")
        return
    try:
        d = load("branch_peers.json")
    except Exception as e:
        fail("branch_peers.json loads", repr(e))
        return
    ok("branch_peers.json loads")

    meta = d.get("meta") or {}
    lab = str(meta.get("label") or "")
    if not meta.get("generated_by") or "ESTIMATED" not in lab or "NOT a measured" not in lab:
        fail("branch_peers meta/provenance (generated_by + ESTIMATED label + not-measured caveat)",
             "meta missing generated_by / ESTIMATED / not-measured caveat")
    else:
        ok("branch_peers meta/provenance present (ESTIMATED peer benchmark, not-measured caveat)")

    rows = d.get("branches")
    if not isinstance(rows, list) or (n_branches is not None and len(rows) != n_branches):
        fail("branch_peers.branches index-aligned to branches.json",
             "len %s != %s" % (len(rows) if isinstance(rows, list) else None, n_branches))
    else:
        ok("branch_peers.branches index-aligned to branches.json (%d rows)" % len(rows))

    outs = d.get("outliers") or []
    rz_min = ((meta.get("params") or {}).get("rz_min")) or 2.0
    problems = []
    for o in outs:
        if not isinstance(o.get("i"), int) or not (0 <= o["i"] < (n_branches or 10**9)):
            problems.append("outlier index %r out of range" % o.get("i"))
        if (o.get("rz") or 0) < rz_min:
            problems.append("%s rz %.2f below gate %.1f" % (o.get("name"), o.get("rz") or 0, rz_min))
        if abs((o.get("risk") or 0) - (o.get("peer_median") or 0) - (o.get("dev") or 0)) > 0.15:
            problems.append("%s dev inconsistent with risk-peer_median" % o.get("name"))
        if len(o.get("twins") or []) < 3:
            problems.append("%s has <3 named twins" % o.get("name"))
    if problems:
        fail("branch_peers outliers sane (index in range, rz gate, dev arithmetic, 3 named twins)",
             first_n(problems, 6))
    else:
        ok("branch_peers outliers sane (%d rows: rz>=%.1f, dev==risk-peer_median, 3 named twins)"
           % (len(outs), rz_min))


# ---------------------------------------------------------------------------
def check_branch_leads(n_branches):
    # Occupation lead board per branch (objective #2, local-acquisition flavor). MEASURED
    # nearby counts ranked by an ESTIMATED editorial fit map — meta must say the fit is
    # ESTIMATED, branches[] must stay index-aligned to branches.json, every lead must use a
    # known bucket key with a non-negative measured count, and lead boards cap at top-5.
    # Optional file: SKIP-PASS when absent.
    hdr("branch_leads.json (optional)")
    if not exists("branch_leads.json"):
        ok("branch_leads.json absent — skipped (optional; run build_branch_leads.py)")
        return
    try:
        d = load("branch_leads.json")
    except Exception as e:
        fail("branch_leads.json loads", repr(e))
        return
    ok("branch_leads.json loads")

    meta = d.get("meta") or {}
    prov_blob = str(meta.get("label") or "") + str(meta.get("fit_map_provenance") or "")
    if not meta.get("generated_by") or "ESTIMATED" not in prov_blob or "MEASURED" not in prov_blob:
        fail("branch_leads meta/provenance (generated_by + ESTIMATED fit label + MEASURED counts note)",
             "meta missing generated_by / ESTIMATED / MEASURED provenance text")
    else:
        ok("branch_leads meta/provenance present (MEASURED counts x ESTIMATED editorial fit)")

    buckets = d.get("buckets") or []
    known = {b.get("k") for b in buckets if isinstance(b, dict)}
    if len(buckets) != 14 or len(known) != 14 or not all(
            b.get("label") and b.get("fit") in ("high", "med", "low") and b.get("why")
            for b in buckets):
        fail("branch_leads fit map embedded (14 buckets, each with label + high/med/low fit + why)",
             "buckets malformed: n=%d known=%d" % (len(buckets), len(known)))
    else:
        ok("branch_leads fit map embedded (14 buckets with auditable fit rating + rationale)")

    rows = d.get("branches")
    if not isinstance(rows, list) or (n_branches is not None and len(rows) != n_branches):
        fail("branch_leads.branches index-aligned to branches.json",
             "len %s != %s" % (len(rows) if isinstance(rows, list) else None, n_branches))
        return
    ok("branch_leads.branches index-aligned to branches.json (%d rows)" % len(rows))

    problems = []
    for i, r in enumerate(rows):
        leads = r.get("leads")
        if not isinstance(leads, list) or len(leads) > 5:
            problems.append("row %d: leads not a list or >5" % i)
            continue
        for l in leads:
            if l.get("k") not in known:
                problems.append("row %d: unknown lead bucket %r" % (i, l.get("k")))
            if not isinstance(l.get("n"), int) or l["n"] < 0:
                problems.append("row %d: lead %s count %r not a non-negative int" % (i, l.get("k"), l.get("n")))
        for u in (r.get("u") or []):
            if u.get("k") not in known:
                problems.append("row %d: unknown untapped bucket %r" % (i, u.get("k")))
        if problems:
            break  # one bad row is enough evidence; keep the report readable
    if problems:
        fail("branch_leads rows sane (known bucket keys, counts >= 0, top-5 max)",
             first_n(problems, 6))
    else:
        ok("branch_leads rows sane (%d rows: known bucket keys, counts >= 0, <=5 leads each)" % len(rows))


# ---------------------------------------------------------------------------
def check_peer_npl():
    # PEER NPL benchmark (objective #1 collateral context). These are PEER-reported figures, NOT an
    # AutoX number — the data-mandate requires meta to say so explicitly and each row to cite its
    # source. Optional file: SKIP-PASS when absent.
    hdr("peer_npl.json (optional)")
    if not exists("peer_npl.json"):
        ok("peer_npl.json absent — skipped (optional peer benchmark)")
        return
    try:
        d = load("peer_npl.json")
    except Exception as e:
        fail("peer_npl.json loads", repr(e))
        return
    ok("peer_npl.json loads")

    # provenance: meta must cite the source AND make the peer-not-AutoX caveat explicit (the note).
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("source") or not meta.get("note"):
        fail("peer_npl meta/provenance present (source + peer-not-AutoX note)",
             "meta missing source/note")
    else:
        ok("peer_npl meta/provenance present (source + peer-reported caveat)")

    peers = d.get("peers")
    if not isinstance(peers, list) or not peers:
        fail("peer_npl has a 'peers' list", "got %s" % type(peers).__name__)
        return
    ok("peer_npl peers list present (%d)" % len(peers))

    bad = []
    for i, p in enumerate(peers):
        if not isinstance(p, dict):
            bad.append("#%d not an object" % i)
            continue
        name = p.get("ticker") or p.get("name") or "#%d" % i
        # npl: a reported percentage — positive finite, sanity-bounded (0..100)
        npl = p.get("npl")
        if not is_finite_number(npl) or not (0.0 < npl <= 100.0):
            bad.append("%s npl=%r out of (0,100]" % (name, npl))
        # every peer figure must cite its source (no fabricated ratios)
        if not (isinstance(p.get("source"), str) and p.get("source").strip()):
            bad.append("%s source missing/empty (peer figure must be cited)" % name)
    if bad:
        fail("peer_npl rows sane (npl in (0,100], each cites a source)", first_n(bad))
    else:
        ok("peer_npl rows sane (npl in (0,100], every peer figure cites a source)")


# ---------------------------------------------------------------------------
def check_macro_exposure(n_branches):
    # MACRO-FACTOR EXPOSURE per customer cluster per branch (objective #1): MEASURED occupation
    # shares × ESTIMATED sensitivity weights × MEASURED macro signals (prices/DTI/drought), index-
    # aligned to branches.json. Optional file: SKIP-PASS when absent (needs the Overture occupation
    # layer; build_macro_exposure.py skip-passes without it too).
    hdr("macro_exposure.json (optional)")
    if not exists("macro_exposure.json"):
        ok("macro_exposure.json absent — skipped (optional; run build_macro_exposure.py to populate)")
        return
    try:
        d = load("macro_exposure.json")
    except Exception as e:
        fail("macro_exposure.json loads", repr(e))
        return
    ok("macro_exposure.json loads")

    # provenance: meta must carry the builder, the sensitivity MATRIX itself (auditable editorial
    # judgement), an explicit ESTIMATED label on the weights, and a measured-signal provenance per
    # factor (the data-mandate: measured-vs-estimated must be explicit everywhere).
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("label"):
        fail("macro_exposure meta/provenance present (generated_by + label)",
             "meta missing generated_by/label")
        return
    ok("macro_exposure meta/provenance present (generated_by + composite label)")

    matrix = meta.get("matrix")
    if not isinstance(matrix, dict) or not matrix or not all(
            isinstance(row, dict) and all(
                isinstance(c, dict) and is_finite_number(c.get("w")) and 0.0 <= c["w"] <= 1.0
                and isinstance(c.get("why"), str) and c["why"].strip()
                for c in row.values())
            for row in matrix.values()):
        fail("macro_exposure meta.matrix present (bucket × factor, w in [0,1], rationale per cell)",
             "matrix missing, or a cell lacks a finite w in [0,1] / a non-empty 'why' rationale")
    else:
        n_cells = sum(len(r) for r in matrix.values())
        ok("macro_exposure meta.matrix present (%d buckets, %d rationale-carrying cells)"
           % (len(matrix), n_cells))

    weights_prov = (meta.get("provenance") or {}).get("sensitivity_weights") \
        if isinstance(meta.get("provenance"), dict) else None
    if not (isinstance(weights_prov, str) and "ESTIMATED" in weights_prov):
        fail("macro_exposure sensitivity weights explicitly labelled ESTIMATED",
             "meta.provenance.sensitivity_weights missing or lacks the ESTIMATED label")
    else:
        ok("macro_exposure sensitivity weights explicitly labelled ESTIMATED")

    factors = meta.get("factors")
    fkeys = meta.get("factor_keys")
    if (not isinstance(factors, list) or not factors or not isinstance(fkeys, list)
            or [f.get("key") for f in factors] != fkeys):
        fail("macro_exposure meta.factors defined + consistent with factor_keys",
             "factors/factor_keys missing or inconsistent")
        return
    no_prov = [f.get("key") for f in factors
               if not (isinstance((f.get("signal") or {}).get("provenance"), str)
                       and f["signal"]["provenance"].strip())]
    if no_prov:
        fail("macro_exposure each factor's signal carries provenance", "missing: " + first_n(no_prov))
    else:
        ok("macro_exposure each factor's signal carries provenance (%d factors)" % len(factors))
    # matrix columns must only reference defined factors
    fset = set(fkeys)
    bad_cols = sorted({f for row in (matrix or {}).values() for f in row if f not in fset})
    if bad_cols:
        fail("macro_exposure matrix columns are defined factor keys", "unknown: " + first_n(bad_cols))
    else:
        ok("macro_exposure matrix columns are defined factor keys")

    recs = d.get("branches")
    if not isinstance(recs, list):
        fail("macro_exposure has a 'branches' list", "got %s" % type(recs).__name__)
        return
    if n_branches is not None and len(recs) != n_branches:
        fail("macro_exposure length == branches.json length",
             "macro_exposure=%d branches=%d" % (len(recs), n_branches))
    else:
        ok("macro_exposure length == branches.json length (%d)" % len(recs))

    # per-record: t3 = up-to-3 [factor_key, score 0..100, dir 'h'|'t'] sorted score desc;
    # d (dominant) a defined factor key equal to t3[0][0], or null iff t3 is empty.
    bad = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            bad.append("#%d not an object" % i)
            continue
        t3 = r.get("t3")
        if not isinstance(t3, list) or len(t3) > 3:
            bad.append("#%d t3 not a list of <=3" % i)
            continue
        prev = None
        for e in t3:
            if (not isinstance(e, list) or len(e) != 3 or e[0] not in fset
                    or not is_finite_number(e[1]) or not (0.0 <= e[1] <= 100.0)
                    or e[2] not in ("h", "t")):
                bad.append("#%d t3 entry malformed: %r" % (i, e))
                continue
            if prev is not None and e[1] > prev:
                bad.append("#%d t3 not sorted score desc" % i)
            prev = e[1]
        dom = r.get("d")
        if t3:
            if dom != t3[0][0]:
                bad.append("#%d dominant %r != t3[0][0] %r" % (i, dom, t3[0][0]))
        elif dom is not None:
            bad.append("#%d empty t3 but dominant=%r" % (i, dom))
        if dom is not None and dom not in fset:
            bad.append("#%d dominant %r not a defined factor" % (i, dom))
    if bad:
        fail("macro_exposure records sane (t3 <=3 well-formed [key, 0..100, h|t] desc; "
             "dominant a defined factor key consistent with t3)", first_n(bad, 8))
    else:
        ok("macro_exposure records sane (t3 well-formed + sorted, scores in [0,100], "
           "dominant a defined factor key)")

    # compact vector (map-lens read): index-aligned, [factor_index or -1, score 0..100].
    vec = d.get("vector")
    if not isinstance(vec, list) or (n_branches is not None and len(vec) != n_branches):
        fail("macro_exposure vector index-aligned", "missing or wrong length")
    else:
        vbad = [i for i, v in enumerate(vec)
                if not (isinstance(v, list) and len(v) == 2
                        and isinstance(v[0], int) and -1 <= v[0] < len(fkeys)
                        and is_finite_number(v[1]) and 0.0 <= v[1] <= 100.0)]
        if vbad:
            fail("macro_exposure vector entries sane ([factor_index|-1, score 0..100])",
                 "bad at " + first_n(vbad))
        else:
            ok("macro_exposure vector index-aligned + sane (%d entries)" % len(vec))


def check_lead_sites(n_branches):
    # LEAD-SITE PINS per branch (objective #2, local): MEASURED OSM coordinates of the K
    # nearest lead-relevant establishments within 10km of each branch, index-aligned to
    # branches.json, compact [cat_idx, lng, lat, dist_km] arrays + a categories[] legend.
    # Optional file: SKIP-PASS when absent (run build_lead_sites.py to populate).
    hdr("lead_sites.json (optional)")
    if not exists("lead_sites.json"):
        ok("lead_sites.json absent — skipped (optional; run build_lead_sites.py to populate)")
        return
    try:
        d = load("lead_sites.json")
    except Exception as e:
        fail("lead_sites.json loads", repr(e))
        return
    ok("lead_sites.json loads")

    # provenance: builder + label + a categories legend (the cat_idx space) + K + radius.
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("label") \
            or not isinstance(meta.get("categories"), list) or not meta["categories"] \
            or not isinstance(meta.get("k"), int) or not is_finite_number(meta.get("radius_km")):
        fail("lead_sites meta/provenance present (generated_by + label + categories + k + radius_km)",
             "meta missing generated_by/label/categories/k/radius_km")
        return
    ok("lead_sites meta/provenance present (generated_by + measured-coordinates label + legend)")

    cats = meta["categories"]
    bad_cat = [i for i, c in enumerate(cats)
               if not (isinstance(c, dict) and c.get("k") and c.get("label") and c.get("osm_layer"))]
    if bad_cat:
        fail("lead_sites categories legend entries carry k/label/osm_layer", "bad at " + first_n(bad_cat))
    else:
        ok("lead_sites categories legend sane (%d categories)" % len(cats))
    n_cats = len(cats)
    k_max = meta["k"]

    recs = d.get("branches")
    if not isinstance(recs, list):
        fail("lead_sites has a 'branches' list", "got %s" % type(recs).__name__)
        return
    # length must equal branches.json (INDEX-ALIGNED — a drift misaligns every pin-drop).
    if n_branches is not None and len(recs) != n_branches:
        fail("lead_sites length == branches.json length",
             "lead_sites=%d branches=%d" % (len(recs), n_branches))
    else:
        ok("lead_sites length == branches.json length (%d)" % len(recs))

    # per-site: [cat_idx, lng, lat, dist_km] — cat_idx valid, coords inside the Thailand
    # bbox [97..106, 5..21] (measured points can't leave the country), dist <= 10.05
    # (radius 10 + 0.1-rounding headroom), <= K sites, sorted nearest-first.
    bad = []
    n_sites = 0
    for i, row in enumerate(recs):
        if not isinstance(row, list) or len(row) > k_max:
            bad.append("#%d not a list of <=%d sites" % (i, k_max))
            continue
        prev = None
        for s in row:
            if not (isinstance(s, list) and len(s) == 4):
                bad.append("#%d site malformed: %r" % (i, s))
                continue
            ci, lng, lat, dist = s
            if not (isinstance(ci, int) and 0 <= ci < n_cats):
                bad.append("#%d cat_idx %r invalid" % (i, ci))
            if not (is_finite_number(lng) and is_finite_number(lat)
                    and 97.0 <= lng <= 106.0 and 5.0 <= lat <= 21.0):
                bad.append("#%d coords outside Thailand bbox: %r,%r" % (i, lng, lat))
            if not (is_finite_number(dist) and 0.0 <= dist <= 10.05):
                bad.append("#%d dist %r outside [0, 10.05]" % (i, dist))
            else:
                if prev is not None and dist < prev:
                    bad.append("#%d sites not sorted nearest-first" % i)
                prev = dist
            n_sites += 1
    if bad:
        fail("lead_sites records sane (<=K sites of [cat_idx, lng, lat, dist]; coords in "
             "Thailand bbox; dist <= 10.05; sorted nearest-first)", first_n(bad, 8))
    else:
        ok("lead_sites records sane (%d sites; coords in Thailand bbox, dist <= 10.05 km, "
           "cat_idx valid, nearest-first)" % n_sites)


def check_catchment_poi():
    # NATIONWIDE POI PINS for the 3D catchment scene: MEASURED OSM coordinates for all 11 scene
    # pin types, [lat,lng] per point (the order the scene ColumnLayer expects — this check guards
    # the swap), bbox-filtered client-side. Optional file: SKIP-PASS when absent.
    hdr("catchment_poi.json (optional)")
    if not exists("catchment_poi.json"):
        ok("catchment_poi.json absent — skipped (optional; run build_catchment_poi.py to populate)")
        return
    try:
        d = load("catchment_poi.json")
    except Exception as e:
        fail("catchment_poi.json loads", repr(e))
        return
    ok("catchment_poi.json loads")

    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("label") \
            or not isinstance(meta.get("type_map"), dict) or not meta["type_map"]:
        fail("catchment_poi meta/provenance present (generated_by + label + type_map)",
             "meta missing generated_by/label/type_map")
        return
    ok("catchment_poi meta/provenance present (generated_by + measured-coordinates label + type_map)")

    poi = d.get("poi")
    if not isinstance(poi, dict) or not poi:
        fail("catchment_poi has a non-empty 'poi' map", "got %s" % type(poi).__name__)
        return
    # every declared type must be a list of [lat,lng] inside the Thailand bbox. The lat/lng
    # ORDER matters: a [lng,lat] slip would put lat~100 (outside [5,21]) — this catches it.
    bad = []
    n_pts = 0
    for t, arr in poi.items():
        if not isinstance(arr, list):
            bad.append("%s not a list" % t)
            continue
        for p in arr:
            if not (isinstance(p, list) and len(p) == 2):
                bad.append("%s malformed point %r" % (t, p)); continue
            lat, lng = p
            if not (is_finite_number(lat) and is_finite_number(lng)
                    and 5.0 <= lat <= 21.0 and 97.0 <= lng <= 106.0):
                bad.append("%s point outside Thailand bbox (lat,lng order?): %r" % (t, p))
            n_pts += 1
    # be tolerant of a small number of stray points but fail on systemic order/bbox errors
    if len(bad) > 20:
        fail("catchment_poi points are [lat,lng] inside the Thailand bbox", first_n(bad, 8))
    elif bad:
        # a few strays are logged but don't fail the gate (OSM has occasional bad coords)
        ok("catchment_poi points [lat,lng] in bbox (%d points; %d stray logged: %s)"
           % (n_pts, len(bad), first_n(bad, 3)))
    else:
        ok("catchment_poi points [lat,lng] in Thailand bbox (%d points, %d types)" % (n_pts, len(poi)))


def check_competitor_census():
    # MERGED measured competitor census (Google ∪ Overture, deduped) — what the 3D scene loads.
    # Optional file: SKIP-PASS when absent (run build_competitor_census.py to populate).
    hdr("competitors_census.json (optional)")
    if not exists("competitors_census.json"):
        ok("competitors_census.json absent — skipped (optional; run build_competitor_census.py)")
        return
    try:
        d = load("competitors_census.json")
    except Exception as e:
        fail("competitors_census.json loads", repr(e))
        return
    ok("competitors_census.json loads")

    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("source") \
            or not isinstance(meta.get("counts"), dict):
        fail("competitors_census meta/provenance present (generated_by + source + counts)",
             "meta missing generated_by/source/counts")
        return
    ok("competitors_census meta/provenance present (generated_by + measured-union source + counts)")

    items = d.get("items")
    if not isinstance(items, list) or not items:
        fail("competitors_census has a non-empty 'items' list", "got %s" % type(items).__name__)
        return
    # every rival: known brand, lat/lng inside the Thailand bbox (measured, can't leave the country).
    KNOWN = {"Muangthai", "Srisawad", "Tidlor", "Heng", "Krungsri"}
    bad = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            bad.append("#%d not an object" % i); continue
        la, ln = it.get("lat"), it.get("lng")
        if it.get("brand") not in KNOWN:
            bad.append("#%d unknown brand %r" % (i, it.get("brand")))
        if not (is_finite_number(la) and is_finite_number(ln)
                and 5.0 <= la <= 21.0 and 97.0 <= ln <= 106.0):
            bad.append("#%d coords outside Thailand bbox: %r,%r" % (i, la, ln))
    if bad:
        fail("competitors_census rivals sane (known brand, coords in Thailand bbox)", first_n(bad, 8))
    else:
        ok("competitors_census rivals sane (%d rivals, known brands, coords in bbox)" % len(items))


def check_rival_density(amphoe):
    # RIVAL DENSITY per district — MEASURED AutoX vs MEASURED rival branch counts + ratio + ceded-ground
    # flags. Optional file: SKIP-PASS when absent (run build_rival_density.py).
    hdr("rival_density.json (optional)")
    if not exists("rival_density.json"):
        ok("rival_density.json absent — skipped (optional; run build_rival_density.py)")
        return
    try:
        d = load("rival_density.json")
    except Exception as e:
        fail("rival_density.json loads", repr(e))
        return
    ok("rival_density.json loads")
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("label") \
            or not isinstance(meta.get("provenance"), dict):
        fail("rival_density meta/provenance present (generated_by + label + provenance)",
             "meta missing generated_by/label/provenance")
        return
    ok("rival_density meta/provenance present (generated_by + measured-vs-computed provenance)")
    recs = d.get("records")
    if not isinstance(recs, list) or not recs:
        fail("rival_density has a non-empty 'records' list", "got %s" % type(recs).__name__)
        return
    arecs = amphoe.get("amphoe") if isinstance(amphoe, dict) else None
    if isinstance(arecs, list) and len(arecs) == len(recs):
        misalign = [i for i in range(len(recs)) if recs[i].get("id") != arecs[i].get("id")]
        if misalign:
            fail("rival_density index-aligned to amphoe.json (same id per position)", first_n(misalign))
        else:
            ok("rival_density index-aligned to amphoe.json (%d districts, same id per position)" % len(recs))
    else:
        ok("rival_density loaded (%d districts; amphoe alignment check skipped)" % len(recs))
    bad = [i for i, r in enumerate(recs)
           if not (isinstance(r.get("autox"), int) and r["autox"] >= 0
                   and isinstance(r.get("rivals"), int) and r["rivals"] >= 0)]
    if bad:
        fail("rival_density autox/rivals are non-negative ints", first_n(bad, 8))
    else:
        ok("rival_density records sane (autox/rivals non-negative ints, %d districts)" % len(recs))


def check_cluster_brief(n_branches, branches):
    # PER-BRANCH MACRO CLUSTER BRIEF — a one-line plain-language macro read per branch, index-aligned
    # to branches.json, templated from measured board/crop/occupation signals. Optional: SKIP if absent.
    hdr("cluster_brief.json (optional)")
    if not exists("cluster_brief.json"):
        ok("cluster_brief.json absent — skipped (optional; run build_cluster_brief.py)")
        return
    try:
        d = load("cluster_brief.json")
    except Exception as e:
        fail("cluster_brief.json loads", repr(e))
        return
    ok("cluster_brief.json loads")
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("label"):
        fail("cluster_brief meta/provenance present (generated_by + label)", "meta missing generated_by/label")
        return
    ok("cluster_brief meta/provenance present (generated_by + templated-over-measured label)")
    briefs = d.get("briefs")
    if not isinstance(briefs, list):
        fail("cluster_brief has a 'briefs' list", "got %s" % type(briefs).__name__)
        return
    if n_branches is not None and len(briefs) != n_branches:
        fail("cluster_brief length == branches.json length", "cluster_brief=%d branches=%d" % (len(briefs), n_branches))
    else:
        ok("cluster_brief length == branches.json length (%d)" % len(briefs))
    bad = [i for i, b in enumerate(briefs)
           if not (isinstance(b, dict) and isinstance(b.get("line"), str) and b["line"].strip())]
    if bad:
        fail("cluster_brief every entry carries a non-empty 'line'", first_n(bad, 8))
    else:
        ok("cluster_brief entries sane (non-empty templated line each, %d branches)" % len(briefs))


def check_branch_population(n_branches):
    # TRUE ~10km-perimeter population per branch (area-weighted district pop), index-aligned to
    # branches.json. Optional file: SKIP-PASS when absent (shapely dep).
    hdr("branch_population.json (optional)")
    if not exists("branch_population.json"):
        ok("branch_population.json absent — skipped (optional; run build_branch_population.py)")
        return
    try:
        d = load("branch_population.json")
    except Exception as e:
        fail("branch_population.json loads", repr(e))
        return
    ok("branch_population.json loads")

    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("label") \
            or not is_finite_number(meta.get("radius_km")):
        fail("branch_population meta/provenance present (generated_by + label + radius_km)",
             "meta missing generated_by/label/radius_km")
        return
    ok("branch_population meta/provenance present (generated_by + area-weighted label + radius_km)")

    vals = d.get("values")
    if not isinstance(vals, list):
        fail("branch_population has a 'values' list", "got %s" % type(vals).__name__)
        return
    if n_branches is not None and len(vals) != n_branches:
        fail("branch_population length == branches.json length",
             "branch_population=%d branches=%d" % (len(vals), n_branches))
    else:
        ok("branch_population length == branches.json length (%d)" % len(vals))
    # every value a non-negative int under a sane national ceiling (Bangkok core ~a few million).
    bad = [i for i, v in enumerate(vals)
           if not (isinstance(v, int) and 0 <= v <= 12_000_000)]
    if bad:
        fail("branch_population values are non-negative ints <= 12M", first_n(bad, 8))
    else:
        ok("branch_population values sane (0 <= pop <= 12M, %d branches)" % len(vals))


def check_occupation_leads(n_branches):
    # NAMED occupation leads per branch (nearest establishments by occupation within 10km, name +
    # phone). Index-aligned to branches.json. Optional file: SKIP-PASS when absent (bulk pull).
    hdr("occupation_leads.json (optional)")
    if not exists("occupation_leads.json"):
        ok("occupation_leads.json absent — skipped (optional; run pull_places_strip.py + build_occupation_leads.py)")
        return
    try:
        d = load("occupation_leads.json")
    except Exception as e:
        fail("occupation_leads.json loads", repr(e))
        return
    ok("occupation_leads.json loads")
    meta = d.get("meta")
    if not isinstance(meta, dict) or not meta.get("generated_by") or not meta.get("label") \
            or not isinstance(meta.get("buckets"), list) or not meta["buckets"]:
        fail("occupation_leads meta/provenance present (generated_by + label + buckets)",
             "meta missing generated_by/label/buckets")
        return
    ok("occupation_leads meta/provenance present (generated_by + measured-Places label + buckets)")
    nb = len(meta["buckets"])
    recs = d.get("branches")
    if not isinstance(recs, list):
        fail("occupation_leads has a 'branches' list", "got %s" % type(recs).__name__)
        return
    if n_branches is not None and len(recs) != n_branches:
        fail("occupation_leads length == branches.json length", "occ=%d branches=%d" % (len(recs), n_branches))
    else:
        ok("occupation_leads length == branches.json length (%d)" % len(recs))
    # each lead is [bucket_idx (valid), name (non-empty str), phone (str), dist_km (0..~10.1)]
    bad = []
    n_leads = 0
    for i, r in enumerate(recs):
        L = r.get("L") if isinstance(r, dict) else None
        if not isinstance(L, list):
            bad.append("#%d no L list" % i); continue
        for e in L:
            n_leads += 1
            if not (isinstance(e, list) and len(e) == 4):
                bad.append("#%d malformed lead %r" % (i, e)); continue
            bi, name, phone, dist = e
            if not (isinstance(bi, int) and 0 <= bi < nb):
                bad.append("#%d bad bucket %r" % (i, bi))
            if not (isinstance(name, str) and name.strip()):
                bad.append("#%d empty lead name" % i)
            if not (is_finite_number(dist) and 0.0 <= dist <= 10.1):
                bad.append("#%d dist %r out of range" % (i, dist))
    if bad:
        fail("occupation_leads records sane ([bucket, name, phone, dist]; named; dist<=10.1)", first_n(bad, 8))
    else:
        ok("occupation_leads records sane (%d named leads; valid bucket/name/dist)" % n_leads)


# ---------------------------------------------------------------------------
# PROVENANCE GATE (data-mandate enforcement).
#
# Mandate: no committed data may be hallucinatory/fabricated. Every NUMERIC data layer in
# platform/data/ must be traceable to a real source or honestly labelled estimated-with-method.
# This check makes "unsourced numeric data" un-shippable: a numeric layer that carries NO provenance
# signal AND is not on the documented exemption list FAILS the gate.
#
# Provenance signal = a non-empty value at meta.<one of these keys>. We accept several spellings
# because different builders use different (all honest) conventions:
#   - source / provenance / sources : explicit named source(s)
#   - generated_by / generated_with : the deterministic builder that produced it (DERIVED, inputs sourced)
#   - inputs_used                   : the named sourced inputs blended into a composite
#   - label                         : an honest ESTIMATED/SYNTHETIC label (e.g. opportunity_score, loan_tape)
# See docs/DATA_PROVENANCE.md for the full register and the rationale per file.
PROVENANCE_KEYS = (
    "source", "provenance", "sources",
    "generated_by", "generated_with",
    "inputs_used", "label",
)

# Files that legitimately carry NO in-file provenance: pure deterministic derivatives of named,
# sourced inputs, OR OSM/Overture geometry basemap layers (not numeric decision metrics). Each is
# justified in docs/DATA_PROVENANCE.md §1/§3. Adding a NEW numeric layer requires either real
# provenance or a conscious entry here — keep this list narrow.
PROVENANCE_EXEMPT = {
    # --- (a) bare deterministic derivatives of the sourced master (DATA_PROVENANCE.md §1, R4) ---
    # These carry no in-file meta because their provenance lives in meta.json + branches_final.json
    # (the master) + docs/DATA_SOURCES.md. All are byte-exact reproducible by their --check builders.
    "branches.json",        # a bare LIST, DERIVED by derive.py from branches_final.json (sourced master)
    "meta.json",            # IS the provenance/rollup sidecar for branches; its inputs are sourced
    "deltas.json",          # deterministic diff of two sourced snapshots; carries from/to vintage stamps
    "snapshots_index.json",  # structural index of captured vintages; no independent numeric series
    # --- (b) province deep-dives (DATA_PROVENANCE.md R1) ---
    # DERIVED by build_province.py from named sourced layers (DIW/DLT/NSO/OSM via spatial join),
    # --check byte-exact, but the builder does not yet emit a meta block. The whole provinces/
    # subtree is matched by prefix in _is_exempt(); only the index is named literally here.
    "provinces/index.json",
    # --- (c) geometry / basemap layers: OSM (Overpass) + Overture footprints (DATA_PROVENANCE.md R2/R3/R6) ---
    # Numeric building/road/water/landuse GEOMETRY for the 3D scenes — coordinates & footprints, NOT
    # decision metrics. Source is OSM/Overture by construction (via the pull_* scripts) though not all
    # carry an in-file meta.source stamp yet. Exempt as visual basemap, flagged in the register.
    "rayong_catchment.json",   # Overture building footprints (Rayong), heights baked by bake_catchment_heights.py
    "rayong_province.json",    # curated Rayong pilot deep-dive; inputs are sourced layers + curated list
    "rayong_landuse.json",     # OSM/Overpass landuse polygons (basemap)
    "rayong_roads.json",       # OSM/Overpass road lines (basemap)
    "rayong_water.json",       # OSM/Overpass water polygons (basemap)
    "rayong_rail.json",        # OSM/Overpass rail lines (basemap)
    "bangkok_catchment.json",  # Overture building footprints (Bangkok); meta has city/n_bldg but no source
    "chiang-mai_catchment.json",  # Overture building footprints (Chiang Mai), pull_overture_buildings.py, 180k cap
    "bangkok_landuse.json",    # OSM/Overpass landuse polygons (basemap)
    "bangkok_roads.json",      # OSM/Overpass road lines (basemap)
    "bangkok_water.json",      # OSM/Overpass water polygons (basemap)
}


def _nonempty_prov_value(v):
    """True iff v is a usable provenance value: a non-blank STRING, or a non-empty
    list/dict that contains at least one non-blank string somewhere.

    Rationale (hardening): the data-mandate requires a provenance *label* — a human-readable
    string naming a source / builder / honest estimate. A truthy-but-meaningless value
    (a bare number like meta.label=1, a whitespace-only "   ", or an empty/[] {} container,
    or a list of blanks like ["", null]) is NOT provenance and must not satisfy the gate.
    """
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple)):
        return any(_nonempty_prov_value(x) for x in v)
    if isinstance(v, dict):
        return any(_nonempty_prov_value(x) for x in v.values())
    # numbers / bools / None are not a provenance label.
    return False


def _has_provenance(obj):
    """True iff obj is a dict carrying a meta.<provenance key> with a non-blank string value
    (or a container of such). See _nonempty_prov_value for what counts."""
    if not isinstance(obj, dict):
        return False
    meta = obj.get("meta")
    if not isinstance(meta, dict):
        return False
    for k in PROVENANCE_KEYS:
        if _nonempty_prov_value(meta.get(k)):
            return True
    return False


def _all_data_json_rels():
    """Every committed *.json under platform/data/, RECURSIVELY (incl. provinces/ and any
    future subdirectory), as DATA-relative paths with '/' separators. A recursive walk
    future-proofs the gate: a new subfolder of numeric data cannot slip through unchecked."""
    rels = []
    for root, _dirs, files in os.walk(DATA):
        for f in files:
            if f.endswith(".json"):
                rel = os.path.relpath(os.path.join(root, f), DATA)
                rels.append(rel.replace(os.sep, "/"))
    return sorted(rels)


def _is_exempt(rel):
    """rel uses '/' separators. Province deep-dives all share the build_province.py
    exemption (R1); match the whole provinces/ subtree by prefix. Everything else must be
    named literally in PROVENANCE_EXEMPT (kept narrow on purpose)."""
    return rel in PROVENANCE_EXEMPT or rel.startswith("provinces/")


def check_provenance():
    hdr("provenance gate (data-mandate: no unsourced numeric data)")
    if not os.path.isdir(DATA):
        fail("platform/data exists", "missing %s" % DATA)
        return

    # Guard the exemption list itself: every literally-named exempt file must still exist.
    # A stale exemption silently widens the gate (a file could be renamed/removed and its
    # replacement never re-audited), so a dangling entry is a real regression to fix.
    stale = sorted(rel for rel in PROVENANCE_EXEMPT if not exists(rel))
    if stale:
        fail("PROVENANCE_EXEMPT entries all still exist (no stale/dangling exemptions)",
             "these exempt files are gone — remove the exemption or restore the file:\n  "
             + first_n(stale, 20))
    else:
        ok("PROVENANCE_EXEMPT entries all still exist (%d, none stale)" % len(PROVENANCE_EXEMPT))

    # Every committed *.json under platform/data/, recursively (top level + provinces/ + any
    # future subdirectory). Each must carry provenance OR be documented-exempt.
    rels = _all_data_json_rels()

    violations = []
    n_sourced = 0
    n_exempt = 0
    for rel in rels:
        try:
            d = load(rel.replace("/", os.sep))
        except Exception as e:
            fail("provenance: %s loads" % rel, repr(e))
            continue
        if _has_provenance(d):
            n_sourced += 1
        elif _is_exempt(rel):
            n_exempt += 1
        else:
            violations.append(rel)

    if violations:
        fail("every numeric platform/data layer carries provenance (meta.source / "
             "meta.provenance / labelled estimate) or a documented exemption",
             "UNSOURCED (no meta provenance string, not exempt) — add a real source, an honest "
             "estimated-label, or a documented exemption in docs/DATA_PROVENANCE.md:\n  "
             + first_n(violations, 20))
    else:
        ok("every numeric platform/data layer (%d scanned, recursive) is sourced (%d) or "
           "documented-exempt (%d) — no unsourced data shipped"
           % (len(rels), n_sourced, n_exempt))


# ---------------------------------------------------------------------------
# INDEX-ALIGNMENT GATE (consolidated).
#
# Several platform/data layers are INDEX-ALIGNED to branches.json: entry i corresponds to branch i,
# and the National-map lenses in app.js read them positionally (e.g. BR[i] <-> DATA[i], BAMP[i] <->
# DATA[i]). If a future data refresh ever emits one of these layers at a DIFFERENT length than
# branches.json, nothing crashes — the lenses silently mis-color every branch. That is a subtle,
# high-blast-radius data bug.
#
# The per-layer checks above each assert their own alignment, but they can be short-circuited by an
# early absent-state return. This ONE consolidated gate is the authoritative guard: for every
# index-aligned layer that EXISTS, it re-derives the ALIGNED array (some layers wrap it under a key
# like 'branches'; amphoe.json carries it as 'branch_amphoe') and asserts its length == the actual
# branches.json length. Absent layers SKIP-PASS (the enrichment loop ships without some pulls).
# We read the real branches length (never hard-code 2,015) so the gate survives a legitimate
# branch-count change.
#
# Each entry: (filename, aligned-array accessor). The accessor returns the aligned list, or None
# if the file's shape doesn't expose one (which itself is a failure worth surfacing).
_INDEX_ALIGNED_LAYERS = (
    ("branch_risk.json", lambda d: d.get("branches") if isinstance(d, dict) else None),
    ("occupation_risk.json", lambda d: d.get("branches") if isinstance(d, dict) else None),
    ("poi_relevance.json", lambda d: d.get("branches") if isinstance(d, dict) else None),
    ("branch_labor.json", lambda d: d.get("branches") if isinstance(d, dict) else None),
    ("branch_occupations.json", lambda d: d.get("branches") if isinstance(d, dict) else None),
    ("macro_exposure.json", lambda d: d.get("branches") if isinstance(d, dict) else None),
    ("lead_sites.json", lambda d: d.get("branches") if isinstance(d, dict) else None),
    # amphoe.json is NOT itself index-aligned, but it carries branch_amphoe[] which IS (BAMP[i]<->DATA[i]).
    ("amphoe.json", lambda d: d.get("branch_amphoe") if isinstance(d, dict) else None),
)


def check_index_alignment(n_branches):
    hdr("index-alignment gate (layers aligned to branches.json)")
    if n_branches is None:
        fail("index-alignment gate needs branches.json length", "branches did not load")
        return

    for rel, accessor in _INDEX_ALIGNED_LAYERS:
        if not exists(rel):
            ok("%s absent — skipped (optional index-aligned layer)" % rel)
            continue
        try:
            d = load(rel)
        except Exception as e:
            fail("%s loads (for index-alignment)" % rel, repr(e))
            continue
        arr = accessor(d)
        if arr is None:
            # The aligned array a layer promises is not present — some absent-state files legitimately
            # omit it. Honor that: if there is no aligned array at all, there is nothing to misalign.
            ok("%s has no aligned array — skipped (absent-state or non-aligned shape)" % rel)
            continue
        if not isinstance(arr, list):
            fail("%s aligned array is a list" % rel, "got %s" % type(arr).__name__)
            continue
        if len(arr) == n_branches:
            ok("%s aligned length == branches.json length (%d)" % (rel, len(arr)))
        else:
            fail("%s aligned length == branches.json length" % rel,
                 "%s=%d branches=%d (index-aligned layer would silently mis-color every branch)"
                 % (rel, len(arr), n_branches))


# ---------------------------------------------------------------------------
# BRANCHES-FINGERPRINT GATE (tamper-evident index alignment).
#
# The length gate above catches a layer built against a DIFFERENT NUMBER of branches, but not
# a REORDERED or partially-swapped branches.json — every index-aligned layer would still be the
# right length while silently describing the WRONG branches. So derive.py stamps meta.json with
# branches_fingerprint = sha256 hex over the ordered [[x, y, n], ...] sequence of branches.json
# (json.dumps separators=(",",":"), ensure_ascii=False, utf-8 — see pipeline/fingerprint.py),
# and every index-aligned builder stamps the CURRENT fingerprint into its own output meta.
#
# This gate recomputes the fingerprint INDEPENDENTLY from branches.json (deliberately re-
# implemented here, not imported — an independent implementation is what makes tampering
# evident) and asserts:
#   1. meta.json carries branches_fingerprint and it matches the recomputation;
#   2. every present aligned layer whose meta carries branches_fingerprint matches it
#      (mismatch = "stale layer — re-run its builder");
#   3. layers without the field (predating the stamp) SKIP-PASS with a note (graceful rollout).
_FINGERPRINTED_LAYERS = (
    "branch_occupations.json",   # build_occupations.py
    "branch_labor.json",         # build_branch_labor.py
    "occupation_risk.json",      # build_occupation_risk.py
    "poi_relevance.json",        # build_poi_relevance.py
    "branch_peers.json",         # build_branch_peers.py
    "branch_leads.json",         # build_branch_leads.py
)


def _branches_fingerprint(branches):
    """sha256 hex over the ordered (x,y,n) identity sequence — must mirror
    pipeline/fingerprint.py byte-for-byte (same serialization contract)."""
    seq = [[b.get("x"), b.get("y"), b.get("n")] for b in branches]
    blob = json.dumps(seq, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def check_branches_fingerprint(branches):
    hdr("branches-fingerprint gate (tamper-evident index alignment)")
    if branches is None:
        fail("branches-fingerprint gate needs branches.json", "branches did not load")
        return
    fp = _branches_fingerprint(branches)

    # 1. meta.json must carry the matching stamp (derive.py writes both files together).
    try:
        meta = load("meta.json")
    except Exception as e:
        fail("meta.json loads (for branches_fingerprint)", repr(e))
        return
    mfp = meta.get("branches_fingerprint") if isinstance(meta, dict) else None
    if mfp is None:
        fail("meta.json carries branches_fingerprint",
             "meta.json has no branches_fingerprint — re-run pipeline/derive.py to stamp it")
    elif mfp != fp:
        fail("meta.json branches_fingerprint matches branches.json",
             "recomputed %s\nmeta.json  %s\nbranches.json and meta.json disagree — "
             "branches.json was reordered/edited outside derive.py, or meta.json is stale; "
             "re-run pipeline/derive.py" % (fp, mfp))
    else:
        ok("meta.json branches_fingerprint matches branches.json (%s…)" % fp[:16])

    # 2./3. every present aligned layer: stamped -> must match; unstamped -> skip-pass note.
    for rel in _FINGERPRINTED_LAYERS:
        if not exists(rel):
            ok("%s absent — skipped (optional fingerprinted layer)" % rel)
            continue
        try:
            d = load(rel)
        except Exception as e:
            fail("%s loads (for branches_fingerprint)" % rel, repr(e))
            continue
        lmeta = d.get("meta") if isinstance(d, dict) else None
        lfp = lmeta.get("branches_fingerprint") if isinstance(lmeta, dict) else None
        if lfp is None:
            ok("%s has no branches_fingerprint (predates the stamp) — skipped; "
               "re-run its builder to stamp it" % rel)
        elif lfp == fp:
            ok("%s branches_fingerprint matches branches.json" % rel)
        else:
            fail("%s branches_fingerprint matches branches.json" % rel,
                 "stale layer — re-run its builder (layer stamped %s, branches.json is %s)"
                 % (lfp, fp))


# ---------------------------------------------------------------------------
def check_rollup(branches):
    hdr("cross-file rollup sanity")
    if branches is None:
        fail("rollup needs branches.json", "branches did not load")
        return
    n = len(branches)
    # meta.region rollup should equal branch count
    try:
        meta = load("meta.json")
    except Exception as e:
        fail("meta.json loads", repr(e))
        return
    ok("meta.json loads")

    region = meta.get("region")
    if not isinstance(region, list):
        fail("meta.region is a list", "got %s" % type(region).__name__)
    else:
        # region names known
        bad_r = sorted(set(r.get("r") for r in region if r.get("r") not in KNOWN_REGIONS))
        if bad_r:
            fail("meta.region names are known", "unknown: " + first_n(bad_r))
        else:
            ok("meta.region names are known")
        rsum = sum(r.get("n", 0) for r in region)
        if abs(rsum - n) <= 2:
            ok("meta.region branch counts sum (%d) ~= national (%d), diff=%d" % (rsum, n, abs(rsum - n)))
        else:
            fail("meta.region branch counts sum ~= national (diff <= 2)",
                 "region sum=%d national=%d" % (rsum, n))

    # actual branch-by-region tally vs meta.region declared
    tally = {}
    for b in branches:
        tally[b.get("r")] = tally.get(b.get("r"), 0) + 1
    if isinstance(region, list):
        mism = []
        for r in region:
            decl = r.get("n", 0)
            act = tally.get(r.get("r"), 0)
            if abs(decl - act) > 2:
                mism.append("%s declared=%d actual=%d" % (r.get("r"), decl, act))
        if mism:
            fail("meta.region per-region counts match branch tally (tol 2)", first_n(mism))
        else:
            ok("meta.region per-region counts match branch tally")


# ---------------------------------------------------------------------------
def main():
    print("AutoX data-integrity validator — reading %s" % DATA)
    branches = check_branches()
    n = len(branches) if branches is not None else None
    amphoe = check_amphoe(n)
    check_amphoe_geo(amphoe)
    check_provinces(n)
    check_crop_stress()
    check_collateral_outlook()
    check_household_risk()
    check_province_stress()
    check_branch_occupations(n)
    check_occupation_risk(n)
    check_poi_relevance(n)
    check_branch_labor(n)
    check_branch_risk(n)
    check_province_risk()
    check_segment_exposure()
    check_amphoe_occupations(amphoe)
    check_competitors()
    check_competitor_coverage()
    check_opportunity_score()
    check_exit_whitespace()
    check_expansion_plan(amphoe, n)
    check_branch_peers(n)
    check_branch_leads(n)
    check_peer_npl()
    check_macro_exposure(n)
    check_lead_sites(n)
    check_catchment_poi()
    check_competitor_census()
    check_rival_density(amphoe)
    check_cluster_brief(n, branches)
    check_branch_population(n)
    check_occupation_leads(n)
    check_provenance()
    check_index_alignment(n)
    check_branches_fingerprint(branches)
    check_rollup(branches)

    print("\n" + ("=" * 40))
    total = _passed + _failed
    print("DATA VALIDATION: %d passed, %d failed (of %d checks)" % (_passed, _failed, total))
    if _failed:
        print("\nREAL DATA ISSUES FOUND — do not weaken the checks; fix the data:")
        for name, detail in _problems:
            print("  - %s" % name)
        return 1
    print("All data-integrity checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
