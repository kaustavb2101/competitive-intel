#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_factories_by_district.py — project the CI-refreshable DIW factory CENSUS into the canonical
per-district factory layer the app already consumes (objective #1 merchant / collateral demand proxy).

  in : source-data/factory_census_national.json   DIW category-3 (factype3) registry, aggregated to
                                                   province|district by committee/census.py from the
                                                   DIW CKAN (diw-dataset.diw.go.th) — REACHABLE from
                                                   ANY IP incl. GitHub Actions (the data.go.th
                                                   geoblock-bypass; refreshed weekly by
                                                   .github/workflows/data-gov-census.yml).
  out: source-data/factories_by_district.json      {source, n_factories, districts{key:{fac,workers}},
                                                   provinces{prov:{fac,workers}}} — the exact shape
                                                   derive.py / build_amphoe.py / build_province.py /
                                                   build_branch_labor.py read.

WHY THIS EXISTS. factories_by_district.json used to be built by ingest_gov.py's build_factories from
pipeline/dgt_out/*.csv — the **data.go.th aggregator pull, which is geoblocked from every foreign /
cloud IP** and only runs from Kaustav's Thai laptop. Its input is off-repo, so the file could never
be reproduced (or gate-checked) in CI and only refreshed on an owner-side laptop pull. The DIW
department CKAN carries the SAME factype3 registry and IS reachable from CI, and census.py already
lands it weekly as factory_census_national.json — but nothing consumed it. This builder wires that
census in as the single source of truth, so the app's district factory intelligence now refreshes
from CI (no laptop) AND becomes byte-checkable in the determinism gate (its input is now on-repo).

THE JOIN. census.py keys by the RAW DIW จังหวัด/อำเภอ strings; this builder re-applies the SAME
canonical() + norm_district() normalizers every other layer uses, so every output key provably
conforms to the app's district identity (the identity documented in build_pico_district.py). The
normalizers are idempotent, so already-canonical DIW names pass through unchanged; the one place it
matters is a bare "เมือง" expanding to "เมือง<province>". Colliding raw keys (if any) are summed,
never dropped. `capital` is carried in the census but not emitted (no consumer). `hp` (summed DIW
installed horsepower — factory SCALE / capital-intensity of the local industrial base, a merchant /
collateral demand-mass proxy the raw factory COUNT can't express) IS now emitted per district and
province; the existing downstream consumers read fac/workers by explicit key and ignore the extra
field, so their outputs are unchanged — only amphoe.json surfaces hp (as `fac_hp`, MEASURED).

Provenance: MEASURED (DIW category-3 factory registry, an official government census — not an OSM
proxy). Deterministic + network-free; `--check` byte-compares; SKIPs (exit 3) if the census is absent.
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.regionmap import canonical, norm_district  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "source-data", "factory_census_national.json")
OUT = os.path.join(ROOT, "source-data", "factories_by_district.json")

SOURCE = ("DIW โรงงาน (factype3, DIW CKAN diw-dataset.diw.go.th) — national factory registry; "
          "measured, not OSM proxy")


def build():
    census = json.load(open(IN, encoding="utf-8"))
    districts = collections.defaultdict(lambda: {"fac": 0, "workers": 0, "hp": 0})
    provinces = collections.defaultdict(lambda: {"fac": 0, "workers": 0, "hp": 0})
    for key, v in census.items():
        if key in ("meta", "_meta"):
            continue
        p_raw, _, d_raw = key.partition("|")
        p = canonical(p_raw.strip())
        d = norm_district(d_raw.strip(), p)
        if not p or not d:
            continue
        fac = int(v.get("factories") or 0)
        workers = int(v.get("workers") or 0)
        hp = int(round(v.get("horsepower") or 0))
        k = f"{p}|{d}"
        districts[k]["fac"] += fac
        districts[k]["workers"] += workers
        districts[k]["hp"] += hp
        provinces[p]["fac"] += fac
        provinces[p]["workers"] += workers
        provinces[p]["hp"] += hp
    return {
        "source": SOURCE,
        "n_factories": sum(v["fac"] for v in provinces.values()),
        "districts": dict(sorted(districts.items())),
        "provinces": dict(sorted(provinces.items())),
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN):
        if args.check:
            print("build_factories_by_district.py --check: SKIP (factory_census_national.json absent)")
            sys.exit(3)
        sys.exit("build_factories_by_district.py: source-data/factory_census_national.json missing")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_factories_by_district.py --check: output missing")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_factories_by_district.py --check: drifted — re-run the builder.")
        print("build_factories_by_district.py --check: OK (byte-exact)")
        return
    open(OUT, "w", encoding="utf-8").write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d districts, %d provinces, %d factories"
          % (OUT, len(obj["districts"]), len(obj["provinces"]), obj["n_factories"]))


if __name__ == "__main__":
    main()
