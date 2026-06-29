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
    check_amphoe(n)
    check_provinces(n)
    check_crop_stress()
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
