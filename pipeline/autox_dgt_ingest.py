#!/usr/bin/env python3
"""
AutoX · data.go.th ingestion  (run from a Thai / non-datacenter network)
------------------------------------------------------------------------
data.go.th Cloudflare-blocks datacenter IPs, so this must run somewhere it allows:
your laptop in TH, a Thai VPS, or behind a TH proxy. Vercel/AWS egress will likely 403.

USAGE
    export DATA_GO_TH_TOKEN=xxxxxxxx        # do NOT hardcode / commit
    python3 autox_dgt_ingest.py            # writes CSVs to ./dgt_out/
    # then upload everything in ./dgt_out/ back to Claude

It self-discovers the right datasets via CKAN package_search, pulls every
datastore-backed resource, paginates, and saves raw CSVs + a manifest.
"""
import os, sys, csv, json, time, urllib.request, urllib.parse, pathlib

KEY = os.environ.get("DATA_GO_TH_TOKEN", "").strip()
if not KEY:
    sys.exit("Set DATA_GO_TH_TOKEN first:  export DATA_GO_TH_TOKEN=...")

BASE = "https://data.go.th/api/3/action"        # CKAN action API
HDR  = {"User-Agent": "Mozilla/5.0", "api-key": KEY}
OUT  = pathlib.Path("dgt_out"); OUT.mkdir(exist_ok=True)
NAT_CAP  = 120        # datasets to scan in the national/aggregate pass per query
PROV_CAP = 12         # datasets to scan per (topic × province) search

# 77 canonical Thai provinces — sweeping each by name guarantees we hit every
# provincial dataset (DLT vehicles / OAE crops / NSO employment are per-province).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from regionmap import REGION
    PROVINCES = sorted(REGION.keys())
except Exception:
    PROVINCES = []

# Each topic: (label, [national queries], province-sweep term). We pull every
# datastore-backed resource we find across BOTH passes, deduped + resumable.
TOPICS = [
    ("factories_diw",  ["โรงงาน กรมโรงงานอุตสาหกรรม", "จำนวนโรงงาน จังหวัด"],          "โรงงาน"),
    ("vehicles_dlt",   ["รถจดทะเบียน กรมการขนส่งทางบก", "จำนวนรถจดทะเบียน จังหวัด"],   "รถจดทะเบียน"),
    ("crop_area_oae",  ["เนื้อที่เพาะปลูก สำนักงานเศรษฐกิจการเกษตร", "เนื้อที่เพาะปลูก จังหวัด"], "เนื้อที่เพาะปลูก"),
    ("crop_price_oae", ["ราคาที่เกษตรกรขายได้", "ราคาผลผลิตเกษตร จังหวัด"],            "ราคาที่เกษตรกรขายได้"),
    ("employment",     ["ภาวะการทำงานของประชากร", "ผู้มีงานทำ จังหวัด",
                        "ผู้ประกันตน ประกันสังคม", "กำลังแรงงาน จังหวัด"],              "ผู้มีงานทำ"),
    ("estates_ieat",   ["นิคมอุตสาหกรรม การนิคมอุตสาหกรรม"],                          None),
]

def api(action, **params):
    url = f"{BASE}/{action}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def datastore_all(resource_id, page=10000, cap=1000000):
    """Pull every row of a datastore resource, paginating."""
    rows, off = [], 0
    while off < cap:
        d = api("datastore_search", resource_id=resource_id, limit=page, offset=off)
        recs = d["result"]["records"]
        if not recs: break
        rows += recs
        if len(recs) < page: break
        off += page
        time.sleep(0.3)
    return rows

def save_csv(name, rows):
    if not rows: return 0
    keys = list({k for r in rows for k in r.keys()})
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for r in rows: w.writerow(r)
    return len(rows)

PROV_KEYS = ("จังหวัด", "province", "provance", "prov", "changwat")
def province_count(rows):
    """How many distinct provinces a resource covers — lets us spot national tables.
    Robust to numeric/None cell values (coerce to str) and never raises."""
    if not rows: return 0
    try:
        key = next((k for k in rows[0].keys() if (k or "").strip() in PROV_KEYS), None)
        if not key: return 0
        return len({str(r.get(key) or "").strip() for r in rows if str(r.get(key) or "").strip()})
    except Exception:
        return 0

def search_results(q, cap):
    """Yield packages for a query, paging through up to `cap` datasets."""
    start = 0
    while start < cap:
        try:
            res = api("package_search", q=q, rows=min(50, cap - start), start=start)["result"]
        except Exception as e:
            print(f"   search '{q[:24]}…' failed: {e}"); return
        results = res.get("results", [])
        if not results:
            return
        for pkg in results:
            yield pkg
        start += len(results)
        if start >= res.get("count", 0):
            return


def pull_pkg(label, pkg, manifest, seen):
    """Pull every datastore resource of a package (resume-safe, deduped)."""
    n = 0
    for r in pkg.get("resources", []):
        if not r.get("datastore_active"):
            continue
        rid = r["id"]
        if rid in seen:
            continue
        seen.add(rid)
        fname = f"{label}__{pkg['name'][:30]}__{rid[:8]}"
        fpath = OUT / (fname + ".csv")
        if fpath.exists():                      # resume: already downloaded a prior run
            n += 1; continue
        try:
            rows = datastore_all(rid)
            if rows:
                cnt = save_csv(fname, rows)
                pc = province_count(rows)
                flag = "  ★" if pc >= 20 else ""
                print(f"   ✓ {cnt:6d} rows · {pc:2d} prov → {fname}.csv{flag}")
                manifest.append({"label": label, "dataset": pkg.get("title", ""),
                                 "package": pkg["name"], "resource_id": rid,
                                 "rows": cnt, "provinces": pc, "file": fname + ".csv"})
                n += 1
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"   ! {rid[:8]} skipped: {e}")
    return n


def main():
    try:
        api("package_search", q="test", rows=1)
        print("✓ data.go.th reachable + key accepted")
        print(f"  exhaustive mode: national pass + {len(PROVINCES)}-province sweep per topic, "
              f"resume-safe (Ctrl-C anytime)\n")
    except Exception as e:
        sys.exit(f"✗ Cannot reach data.go.th from this network ({e}).\n"
                 f"  You're likely on a blocked IP — run from a Thai network/proxy.")

    manifest, seen = [], set()
    for label, queries, prov_term in TOPICS:
        print(f"── {label}")
        got = 0
        # (1) national / aggregate pass
        for q in queries:
            for pkg in search_results(q, NAT_CAP):
                got += pull_pkg(label, pkg, manifest, seen)
        # (2) province sweep — guarantees per-province coverage
        if prov_term and PROVINCES:
            print(f"   province sweep ({len(PROVINCES)} provinces)…")
            for prov in PROVINCES:
                for pkg in search_results(f"{prov_term} {prov}", PROV_CAP):
                    got += pull_pkg(label, pkg, manifest, seen)
        covered = sorted({m["file"] for m in manifest if m["label"] == label})
        maxprov = max([m.get("provinces", 0) for m in manifest if m["label"] == label] or [0])
        print(f"   → {label}: {len(covered)} files, best single-file coverage {maxprov} provinces")
        with open(OUT / "manifest.json", "w", encoding="utf-8") as f:   # checkpoint after each topic
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    nat = sum(1 for m in manifest if m.get("provinces", 0) >= 20)
    print(f"\nDone. {len(manifest)} files in ./dgt_out/  ({nat} with broad ★ coverage). "
          f"Commit the folder and tell Claude.")

if __name__ == "__main__":
    main()
