#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_vehicle_base.py — refresh the DLT vehicle collateral base from the CI-reachable census.

  in : source-data/vehicle_census_province.json   per-province DLT vehicle stock, written + committed
                                                   WEEKLY by the cloud census job
                                                   (.github/workflows/data-gov-census.yml ->
                                                   committee/census.py's build_vehicle_census), which
                                                   streams the DLT department CKAN
                                                   (gdcatalog.dlt.go.th) — REACHABLE from ANY IP incl.
                                                   GitHub Actions. Carries total / motorcycle / pickup
                                                   (+ car under a coarser type map, + moto_share).
  in : source-data/vehicles_by_province.json       THE LIVE BASE it refreshes in place (read by 10+
                                                   builders). Supplies the fields the census cannot:
                                                   per-province `ev` (fuel-type, census has none) and
                                                   `car` (a different DLT classification), plus the
                                                   province set, key order and top-level `source`.
  out: source-data/vehicles_by_province.json       {source, n_vehicles, provinces{prov:{total,car,
                                                   pickup,moto,ev}}} — the exact shape ingest_gov.py
                                                   writes and every downstream builder reads.

WHY THIS EXISTS. vehicles_by_province.json is produced ONLY by ingest_gov.py's build_vehicles, which
reads the fine-grained raw DLT CSV from the **Thai-IP-only data.go.th pull** (pipeline/dgt_out/, absent
in CI). So the collateral base — the title-loan collateral pool, objective #1 — could be refreshed
only from Kaustav's Thai laptop and could not self-heal in CI. Meanwhile committee/census.py already
lands the SAME DLT stock weekly as vehicle_census_province.json from the department CKAN (any IP), but
nothing projected it into the base. tests/vehicle_base_staleness_guard.py already turns the resulting
silent-aging hazard into a RED gate when the two diverge, and its own fix note prescribes exactly this:
"migrate the base onto a CI census projection as was done for factories_by_district.json." This builder
is that projection: it gives the census its first real consumer and the collateral base a CI refresh
path (run this builder — no laptop), and makes the base byte-checkable in the determinism gate.

WHAT IT REFRESHES, AND WHAT IT PRESERVES (matching the guard's field split exactly, no fabrication):
  - REFRESHED from the census, the fields it can authoritatively carry:
        base.total  <- census.total
        base.moto   <- census.motorcycle
        base.pickup <- census.pickup
    (census values arrive as floats, e.g. 297414.0; emitted as ints to match the base's shape.)
  - PRESERVED verbatim from the existing base, because the census cannot source them:
        base.car  — the two DLT sources classify passenger cars differently (base.car != census.car
                    on all 77 provinces BY DESIGN, per the staleness guard); the census's coarser car
                    is NOT authoritative for the base, so we keep the base's own car.
        base.ev   — present only in the base (from the raw CSV's fuel-type column); the CKAN census has
                    no fuel field. ev_penetration.json / ev_exposure.json depend on it.
    The province SET, its key ORDER, and the top-level `source` string are preserved from the base too:
    a province the census lacks keeps its base values untouched (never dropped), and a census-only
    province is NOT invented into the base (its car/ev cannot be sourced without the Thai-IP pull) —
    the staleness guard is what flags a province-set divergence; this builder never fabricates one.

Because base.total/moto/pickup already equal the census today (the invariant the staleness guard
asserts, 0/77 mismatch), a normal run reproduces the committed base BYTE-FOR-BYTE (verified). The day a
DLT vintage bump moves the census, re-running this builder advances those three fields in the base
(preserving car/ev), CI --check flags the drift until the refreshed base is committed, and the
staleness guard clears — the base self-heals from CI instead of waiting on an owner-side laptop pull.

Provenance: MEASURED (official DLT registered-vehicle stock). Deterministic + network-free; `--check`
byte-compares; SKIPs (exit 3) if the CI census is absent (mirrors build_factories_by_district.py).
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENSUS = os.path.join(ROOT, "source-data", "vehicle_census_province.json")
BASE = os.path.join(ROOT, "source-data", "vehicles_by_province.json")


def _i(x):
    """Census counts arrive as floats (e.g. 297414.0); the base carries ints. None stays None."""
    if x is None:
        return None
    try:
        return int(round(float(x)))
    except (TypeError, ValueError):
        return None


def build():
    census = json.load(open(CENSUS, encoding="utf-8"))
    base = json.load(open(BASE, encoding="utf-8"))
    old = base.get("provinces") or {}
    provinces = {}
    # Iterate the BASE's own province order so the output key order is preserved byte-for-byte, and so
    # car/ev (which only the base carries) are never lost. A base province the census lacks keeps its
    # existing values; a census-only province is NOT added (its car/ev cannot be sourced in CI).
    for p, b in old.items():
        c = census.get(p) or {}
        total = _i(c.get("total"))
        moto = _i(c.get("motorcycle"))
        pickup = _i(c.get("pickup"))
        provinces[p] = {
            "total": total if total is not None else b.get("total"),
            "car": b.get("car"),                                   # preserved (base-only classification)
            "pickup": pickup if pickup is not None else b.get("pickup"),
            "moto": moto if moto is not None else b.get("moto"),
            "ev": b.get("ev"),                                     # preserved (census has no fuel field)
        }
    return {
        "source": base.get("source"),
        "n_vehicles": sum((v.get("total") or 0) for v in provinces.values()),
        "provinces": provinces,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(CENSUS):
        if args.check:
            print("build_vehicle_base.py --check: SKIP (vehicle_census_province.json absent)")
            sys.exit(3)
        sys.exit("build_vehicle_base.py: source-data/vehicle_census_province.json missing")
    if not os.path.exists(BASE):
        sys.exit("build_vehicle_base.py: source-data/vehicles_by_province.json missing (needs the "
                 "base's car/ev/source to project onto)")
    payload = serialize(build())
    if args.check:
        if open(BASE, encoding="utf-8").read() != payload:
            sys.exit("build_vehicle_base.py --check: vehicles_by_province.json drifted from the CI "
                     "census — run: python3 pipeline/build_vehicle_base.py")
        print("build_vehicle_base.py --check: OK (byte-exact)")
        return
    open(BASE, "w", encoding="utf-8").write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d provinces, %d vehicles (total/moto/pickup from CI census; car/ev preserved)"
          % (BASE, len(obj["provinces"]), obj["n_vehicles"]))


if __name__ == "__main__":
    main()
