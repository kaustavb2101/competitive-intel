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
    # bare derivatives of the sourced master (provenance lives in meta.json + the master + DATA_SOURCES.md)
    "branches.json",        # list, DERIVED by derive.py from branches_final.json
    "meta.json",            # the provenance/rollup sidecar itself; inputs sourced
    "deltas.json",          # deterministic diff of sourced snapshots (carries from/to vintage labels)
    "snapshots_index.json",  # structural index of vintages, no independent numeric series
    # province deep-dives: DERIVED by build_province.py from sourced layers (no meta block yet — R1)
    "provinces/index.json",
    # geometry / visual catchment + basemap layers (OSM/Overture; numeric footprints, not metrics) — R2/R3/R6
    "rayong_catchment.json",
    "rayong_province.json",
    "rayong_landuse.json",
    "rayong_roads.json",
    "rayong_water.json",
    "rayong_rail.json",
    "bangkok_catchment.json",
    "bangkok_landuse.json",
    "bangkok_roads.json",
    "bangkok_water.json",
}


def _has_provenance(obj):
    """True iff obj is a dict carrying a non-empty meta.<provenance key>."""
    if not isinstance(obj, dict):
        return False
    meta = obj.get("meta")
    if not isinstance(meta, dict):
        return False
    for k in PROVENANCE_KEYS:
        v = meta.get(k)
        if v not in (None, "", [], {}):
            return True
    return False


def check_provenance():
    hdr("provenance gate (data-mandate: no unsourced numeric data)")
    if not os.path.isdir(DATA):
        fail("platform/data exists", "missing %s" % DATA)
        return

    # Every committed *.json directly under platform/data/ plus provinces/*.json.
    rels = sorted(f for f in os.listdir(DATA) if f.endswith(".json"))
    prov_dir = os.path.join(DATA, "provinces")
    if os.path.isdir(prov_dir):
        rels += [os.path.join("provinces", f)
                 for f in sorted(os.listdir(prov_dir)) if f.endswith(".json")]

    violations = []
    n_sourced = 0
    n_exempt = 0
    for rel in rels:
        try:
            d = load(rel)
        except Exception as e:
            fail("provenance: %s loads" % rel, repr(e))
            continue
        # Province deep-dives all share the build_province.py exemption (R1); match by directory.
        is_exempt = rel in PROVENANCE_EXEMPT or rel.startswith("provinces" + os.sep)
        if _has_provenance(d):
            n_sourced += 1
        elif is_exempt:
            n_exempt += 1
        else:
            violations.append(rel)

    if violations:
        fail("every numeric platform/data layer carries provenance (meta.source / "
             "meta.provenance / labelled estimate) or a documented exemption",
             "UNSOURCED (no meta provenance, not exempt) — add a real source, an honest "
             "estimated-label, or a documented exemption in docs/DATA_PROVENANCE.md:\n  "
             + first_n(violations, 20))
    else:
        ok("every numeric platform/data layer is sourced (%d) or documented-exempt (%d) — "
           "no unsourced data shipped" % (n_sourced, n_exempt))


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
    check_provinces(n)
    check_crop_stress()
    check_household_risk()
    check_branch_occupations(n)
    check_occupation_risk(n)
    check_branch_risk(n)
    check_province_risk()
    check_amphoe_occupations(amphoe)
    check_competitors()
    check_competitor_coverage()
    check_provenance()
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
