#!/usr/bin/env python3
# vehicle_base_staleness_guard.py — the STALE-COLLATERAL-BASE tripwire for the DLT vehicle stock.
#
# CLAUDE.md: "Always state whether a number is measured or estimated" and prefer something honest
# over something that merely looks like progress. This guard closes a silent-aging hazard in the
# vehicle collateral base — the title-loan collateral pool (motorcycle title ~= 50% of the book,
# car/pickup ~= 25%), objective #1.
#
# THE TWO FILES (both committed, both per-province DLT vehicle stock, DIFFERENT refresh paths):
#   source-data/vehicles_by_province.json   — THE LIVE BASE. Read by 10+ builders
#       (build_vehicle_registry / build_vehicle_fleet / build_branch_vehicles / build_amphoe /
#       build_province / build_collateral_outlook / build_impact_cards / build_peer_province /
#       build_vehicle_flow). Produced ONLY by pipeline/ingest_gov.py's build_vehicles,
#       which reads the fine-grained raw DLT CSV (vehicles_dlt__dataset_1_1_04__*.csv) from the
#       Thai-IP-only data.go.th pull (pipeline/dgt_out/, absent in CI). So it can be refreshed ONLY
#       from Kaustav's Thai laptop — it CANNOT self-heal in CI. It uniquely carries per-province `ev`
#       (from the raw CSV's fuel-type column), which ev_penetration.json / ev_exposure.json depend on.
#   source-data/vehicle_census_province.json — THE FRESH CI FEED. Written + committed WEEKLY by the
#       cloud census job (.github/workflows/data-gov-census.yml -> committee/census.py's
#       build_vehicle_census), which streams the DLT department CKAN (gdcatalog.dlt.go.th, reachable
#       from ANY IP). Its `total`/`motorcycle`/`pickup` counts are the same DLT stock the base carries.
#
# THE HAZARD (exactly the argument behind mandate_guard / unverified_gpp_guard / the doc-vintage
# tripwire): the CI census refreshes every week into a file NOTHING downstream reads, while the file
# everything reads can only be updated by hand from a Thai IP. So the day DLT publishes a newer
# vehicle vintage, CI silently advances vehicle_census_province.json, the collateral base stays frozen
# at the old numbers, and NOTHING flags the divergence — the app keeps quoting a stale collateral pool
# with a MEASURED label. Good labelling does not catch this; only a gate does.
#
# THE INVARIANT (self-clearing): today all 77 provinces match EXACTLY on the three fields the CI
# census can authoritatively refresh — `total`, motorcycle (base `moto` == census `motorcycle`) and
# `pickup` (verified: 0/77 mismatch on each). The guard asserts that equality. While it holds, the
# base is in sync with the newest CI-reachable DLT stock. The moment a DLT vintage bump moves the
# census past the frozen base, the equality breaks and the gate goes RED — turning silent staleness
# into a visible, actionable failure: re-pull the base from the Thai IP (autox_dgt_ingest.py ->
# ingest_gov.py) and reconcile, or migrate the base onto a CI census projection (the same move already
# made for factories_by_district.json). When the base is refreshed to match, the guard passes again.
#
# DELIBERATELY NOT COMPARED (false-positive-free):
#   - `car`: the two DLT sources classify passenger cars differently (base includes rows the CKAN
#     census's coarser type map excludes), so base.car != census.car on all 77 provinces TODAY by
#     design — comparing it would fire immediately and forever. Not a staleness signal.
#   - `ev`: present only in the base (the CKAN census has no fuel-type field). Its absence from the
#     census is expected, never a mismatch.
#
# Offline, stdlib-only, deterministic. Exit 0 = clean (in sync, OR a file is absent); 1 = the CI
# census has diverged from the collateral base (the base is stale — see the fix in the message).

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BASE = os.path.join(REPO, "source-data", "vehicles_by_province.json")
CENSUS = os.path.join(REPO, "source-data", "vehicle_census_province.json")

# base field -> census field, for the counts the CI census can authoritatively refresh.
# (base `moto` is the CKAN census's `motorcycle`; `car` and `ev` are deliberately excluded above.)
COMPARE = {"total": "total", "moto": "motorcycle", "pickup": "pickup"}


def _i(x):
    """DLT census values arrive as floats (e.g. 297414.0); the base carries ints. Compare as ints so
    a pure float/int representation difference is never read as staleness. None stays None."""
    if x is None:
        return None
    try:
        return int(round(float(x)))
    except (TypeError, ValueError):
        return None


def compare(base_provinces, census):
    """Pure diff of the collateral base against the fresh CI census on the CI-refreshable fields.
    Returns (missing_in_census, missing_in_base, field_mismatches) where field_mismatches is a list of
    (province, field, base_value, census_value). Pure function so the self-test can feed synthetic
    inputs and the guard can never pass vacuously."""
    bk, ck = set(base_provinces), set(census)
    missing_in_census = sorted(bk - ck)   # a province the base has but the fresh census does not
    missing_in_base = sorted(ck - bk)     # a province the fresh census has but the base does not
    field_mismatches = []
    for p in sorted(bk & ck):
        b, c = base_provinces[p], census[p]
        for bf, cf in COMPARE.items():
            bv, cv = _i(b.get(bf)), _i(c.get(cf))
            if bv is not None and cv is not None and bv != cv:
                field_mismatches.append((p, bf, bv, cv))
    return missing_in_census, missing_in_base, field_mismatches


def _selftest():
    """Prove the guard FIRES when the census diverges from the base (total moved, or a province set
    mismatch) and stays QUIET when they agree — INCLUDING when only `car` differs (the expected
    classification gap) or the census lacks `ev`. A drift here is itself a gate failure."""
    fails = []
    base = {"ก": {"total": 100, "moto": 60, "pickup": 20, "car": 18, "ev": 2},
            "ข": {"total": 200, "moto": 120, "pickup": 40, "car": 38, "ev": 2}}

    # in sync: base.car != census.car and census has no ev -> must stay QUIET
    cen_ok = {"ก": {"total": 100.0, "motorcycle": 60.0, "pickup": 20.0, "car": 17.0, "moto_share": 60},
              "ข": {"total": 200.0, "motorcycle": 120.0, "pickup": 40.0, "car": 35.0, "moto_share": 60}}
    mc, mb, fm = compare(base, cen_ok)
    if mc or mb or fm:
        fails.append("FALSE POSITIVE: in-sync base/census (car-only diff, no ev) was flagged: %r" % (fm,))

    # total moved on province ก -> must FIRE on exactly that field
    cen_stale = json.loads(json.dumps(cen_ok))
    cen_stale["ก"]["total"] = 111.0
    _, _, fm2 = compare(base, cen_stale)
    if [(p, f) for p, f, _, _ in fm2] != [("ก", "total")]:
        fails.append("SHOULD-FIRE: a moved `total` was not the sole flagged mismatch: %r" % (fm2,))

    # census gained a province the base lacks -> must FIRE as missing_in_base
    cen_extra = json.loads(json.dumps(cen_ok))
    cen_extra["ค"] = {"total": 5.0, "motorcycle": 3.0, "pickup": 1.0, "car": 1.0, "moto_share": 60}
    mc3, mb3, _ = compare(base, cen_extra)
    if mb3 != ["ค"] or mc3:
        fails.append("SHOULD-FIRE: a census-only province was not flagged as missing_in_base")

    # moto (base) vs motorcycle (census) mismatch -> must FIRE
    cen_moto = json.loads(json.dumps(cen_ok))
    cen_moto["ข"]["motorcycle"] = 130.0
    _, _, fm4 = compare(base, cen_moto)
    if ("ข", "moto") not in [(p, f) for p, f, _, _ in fm4]:
        fails.append("SHOULD-FIRE: a moved motorcycle count (base `moto`) was not flagged")

    return fails


def _load(path, key=None):
    try:
        d = json.load(open(path, encoding="utf-8"))
        return d.get(key, {}) if key else d
    except Exception:
        return None


def main():
    st = _selftest()
    if st:
        print("vehicle_base_staleness_guard: SELF-TEST FAILED (guard logic is unsound, not a data problem):")
        for f in st:
            print("   -", f)
        return 1

    base = _load(BASE, "provinces")
    census = _load(CENSUS)
    if not base:
        print("vehicle_base_staleness_guard: OK — vehicles_by_province.json absent/empty, nothing to compare.")
        return 0
    if not census:
        print("vehicle_base_staleness_guard: OK — vehicle_census_province.json absent/empty (no CI census "
              "feed committed yet), nothing to compare against.")
        return 0

    missing_in_census, missing_in_base, field_mismatches = compare(base, census)

    if not missing_in_census and not missing_in_base and not field_mismatches:
        print("vehicle_base_staleness_guard: OK — the collateral base (vehicles_by_province.json) is in "
              "sync with the fresh CI DLT census (vehicle_census_province.json): all %d provinces match "
              "exactly on total / motorcycle / pickup. (car differs by DLT classification and ev is "
              "base-only, both excluded by design.)" % len(set(base) & set(census)))
        return 0

    print("vehicle_base_staleness_guard: the CI-refreshable DLT census has DIVERGED from the live "
          "collateral base — the base (vehicles_by_province.json, read by 10+ builders) is STALE.")
    if missing_in_census:
        print("   province(s) in the base but not the fresh census: %s" % ", ".join(missing_in_census))
    if missing_in_base:
        print("   province(s) in the fresh census but not the base: %s" % ", ".join(missing_in_base))
    if field_mismatches:
        print("   %d field mismatch(es) on total/motorcycle/pickup (base -> fresh census):"
              % len(field_mismatches))
        for p, f, bv, cv in field_mismatches[:8]:
            print("      %s %s: base %s vs census %s" % (p, f, bv, cv))
        if len(field_mismatches) > 8:
            print("      ... and %d more" % (len(field_mismatches) - 8))
    print("   WHY: vehicle_census_province.json refreshes WEEKLY from CI (DLT department CKAN, any IP), "
          "but the base can be refreshed only from Kaustav's Thai IP (autox_dgt_ingest.py -> "
          "ingest_gov.py's build_vehicles, which reads the raw dgt_out/ CSV incl. the ev fuel column).")
    print("   FIX (CI, no laptop): re-run `python3 pipeline/build_vehicle_base.py` — it projects the "
          "fresh census onto the base's total/moto/pickup (preserving per-province car/ev) and commit "
          "the refreshed base. (Or, for a fuller refresh incl. car/ev, re-pull from the Thai IP via "
          "ingest_gov.py.) Do NOT silence this by editing the guard.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
