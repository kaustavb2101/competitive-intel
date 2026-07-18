#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_newcar_brandprovince.py — OWNER-DESKTOP STUB (run from a THAI IP only).

################################################################################
#  DO NOT RUN THIS FROM THE CLOUD / CI — IT WILL 403.                          #
#  data.go.th is GEOBLOCKED from every foreign IP. This puller MUST be run     #
#  from Kaustav's Thai / residential network (his laptop). See                 #
#  docs/TONIGHT_CHECKLIST.md and docs/CKAN_SOURCES.md.                          #
################################################################################

WHY THIS EXISTS
  The owner asked for "vehicle brands by province." We confirmed a MEASURED brand×province cross is
  NOT reachable from the cloud: DLT stat_1_1_01 carries brand only NATIONALLY, dataset_1_1_04 crosses
  province with type/fuel (no brand), and the one place a brand×province cross might live is the
  data.go.th aggregator — which is geoblocked from the cloud. This stub targets the data.go.th
  `newcar` / `newcarfuel` (new-vehicle registration) datasets from the Thai side and, crucially,
  REPORTS WHETHER THE FILE ACTUALLY CONTAINS A BRAND COLUMN — so a single owner-side run tells us
  whether a measured brand×province is even possible, instead of us guessing.

  If it finds a brand column AND a province column in the same table, that is the unlock: we can then
  write a real build_vehicle_collateral brand×province leg (MEASURED). If it does NOT, we have proven
  the ceiling and can stop asking — the honest answer stays "brand is national only."

WHAT IT DOES (when run from Thailand)
  1. Resolves the `newcar` and `newcarfuel` packages on data.go.th via its CKAN API (a token in
     the DATA_GO_TH_TOKEN env / Vercel is used if present, but the geoblock is by IP, not token).
  2. Downloads the current CSV/XLSX resource(s) into source-data/datagoth/ (gitignored, re-pullable).
  3. Inspects the header and PRINTS a verdict:
        - has_brand_col   : does a ยี่ห้อ / brand / make column exist?
        - has_province_col: does a จังหวัด / province column exist?
        - => "MEASURED brand×province IS possible" only if BOTH are present in one table.
     It does NOT build anything — it is a probe. Once the verdict is known, wire the real build.

  python3 pull_newcar_brandprovince.py            # pull + report the verdict (THAI IP ONLY)
  python3 pull_newcar_brandprovince.py --list     # just resolve the resources, no download
"""
import argparse, csv, io, json, os, re, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "source-data", "datagoth")
BASE = "https://data.go.th/api/3/action/"        # GEOBLOCKED from foreign IPs
DATASETS = ["newcar", "newcarfuel"]              # data.go.th new-vehicle registration datasets
TOKEN = os.environ.get("DATA_GO_TH_TOKEN", "")

# header tokens we probe for (Thai + English variants)
BRAND_TOKENS = ["ยี่ห้อ", "brand", "make", "ยีห้อ", "ตราอักษร"]
PROV_TOKENS = ["จังหวัด", "province", "prov"]


def _headers():
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if TOKEN:
        h["api-key"] = TOKEN
    return h


def _get(url, timeout=90):
    return urllib.request.urlopen(urllib.request.Request(url, headers=_headers()), timeout=timeout).read()


def _hit(header_cells, tokens):
    joined = " | ".join(c.lower() for c in header_cells)
    return [t for t in tokens if t.lower() in joined]


def _probe_csv(raw):
    try:
        text = raw.decode("utf-8-sig", errors="replace")
    except Exception:
        return None
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if row and any(c.strip() for c in row):
            return row      # first non-empty row = header
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    print("=" * 70)
    print("pull_newcar_brandprovince.py — data.go.th probe (THAI IP ONLY; 403 from cloud)")
    print("token present:", bool(TOKEN))
    print("=" * 70)
    os.makedirs(OUTDIR, exist_ok=True)

    any_measured = False
    for ds in DATASETS:
        print("\n### dataset:", ds)
        try:
            pkg = json.loads(_get(BASE + "package_show?id=" + ds))["result"]
        except Exception as e:
            print("  [ERR] package_show failed: %s" % (str(e)[:120]))
            print("  (if this is a 403/geoblock, you are NOT on a Thai IP — run from the laptop.)")
            continue
        print("  title:", pkg.get("title", ""))
        resources = [r for r in pkg.get("resources", [])
                     if (r.get("format") or "").upper() in ("CSV", "XLSX")]
        for r in resources:
            print("   %-5s %s  %s" % (r.get("format"), r.get("name", ""), r.get("url", "")))
        if args.list:
            continue
        for r in resources:
            fmt = (r.get("format") or "").lower()
            if fmt != "csv":
                print("   [skip] %s is %s — download + inspect manually (probe reads CSV headers only)"
                      % (r.get("name", ""), fmt))
                continue
            try:
                raw = _get(r["url"])
            except Exception as e:
                print("   [ERR] download failed: %s" % (str(e)[:120]))
                continue
            fn = os.path.basename(r["url"].split("?")[0]) or (ds + ".csv")
            open(os.path.join(OUTDIR, fn), "wb").write(raw)
            header = _probe_csv(raw)
            if not header:
                print("   [??] %s: could not read a header row" % fn)
                continue
            b = _hit(header, BRAND_TOKENS)
            p = _hit(header, PROV_TOKENS)
            measured = bool(b) and bool(p)
            any_measured = any_measured or measured
            print("   FILE %s" % fn)
            print("     header:", header)
            print("     has_brand_col:   ", bool(b), (b or ""))
            print("     has_province_col:", bool(p), (p or ""))
            print("     => MEASURED brand×province possible from THIS file:", measured)

    print("\n" + "=" * 70)
    if any_measured:
        print("VERDICT: at least one data.go.th file carries BOTH brand AND province — a MEASURED")
        print("brand×province collateral view IS possible. Next: wire it into build_vehicle_collateral.py")
        print("as a MEASURED per-province brand leg (replacing the national-only brand note).")
    else:
        print("VERDICT: no file with brand AND province in the same table was found (or the pull was")
        print("blocked). If this ran on a Thai IP and still found none, the ceiling is confirmed:")
        print("brand stays NATIONAL ONLY and build_vehicle_collateral.py's national-only note is correct.")
    print("=" * 70)


if __name__ == "__main__":
    main()
