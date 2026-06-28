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
SEARCH_ROWS = 120     # how many datasets to consider per topic (was 5 — too shallow, missed national tables)
MAX_RES     = 120     # cap resources pulled per topic (set high for "maximum data"; Ctrl-C anytime, files save as they go)

# What we want — each entry is (label, search terms). Tune the queries if a
# better dataset shows up in the manifest.
TARGETS = [
    ("factories_diw",  "โรงงาน กรมโรงงานอุตสาหกรรม จังหวัด"),
    ("vehicles_dlt",   "รถจดทะเบียน กรมการขนส่งทางบก จังหวัด"),
    ("crop_area_oae",  "เนื้อที่เพาะปลูก สำนักงานเศรษฐกิจการเกษตร"),
    ("crop_price_oae", "ราคา ผลผลิต เกษตร จังหวัด"),
    ("estates_ieat",   "นิคมอุตสาหกรรม การนิคมอุตสาหกรรม"),
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

def main():
    # sanity check the key/network first
    try:
        api("package_search", q="test", rows=1)
        print("✓ data.go.th reachable + key accepted\n")
    except Exception as e:
        sys.exit(f"✗ Cannot reach data.go.th from this network ({e}).\n"
                 f"  You're likely on a blocked IP — run from a Thai network/proxy.")

    manifest = []
    seen = set()                       # dedup resources across topics
    for label, query in TARGETS:
        print(f"── {label}: searching '{query}'")
        try:
            res = api("package_search", q=query, rows=SEARCH_ROWS)["result"]
        except Exception as e:
            print(f"   search failed: {e}"); continue
        print(f"   {res['count']} datasets matched; scanning up to {min(SEARCH_ROWS,len(res['results']))} "
              f"(cap {MAX_RES} resources)")
        got = 0
        for pkg in res["results"]:
            if got >= MAX_RES: break
            for r in pkg.get("resources", []):
                if got >= MAX_RES: break
                if not r.get("datastore_active"): continue
                rid = r["id"]
                if rid in seen: continue
                seen.add(rid)
                try:
                    rows = datastore_all(rid)
                    if rows:
                        fname = f"{label}__{pkg['name'][:30]}__{rid[:8]}"
                        n = save_csv(fname, rows)
                        pc = province_count(rows)
                        flag = "  ★ broad coverage" if pc >= 20 else ""
                        print(f"   ✓ {n:6d} rows · {pc:2d} provinces → {fname}.csv{flag}")
                        manifest.append({"label": label, "dataset": pkg["title"],
                                         "package": pkg["name"], "resource_id": rid,
                                         "rows": n, "provinces": pc, "file": fname + ".csv"})
                        got += 1
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(f"   ! {rid[:8]} skipped: {e}"); continue
        if not got:
            print("   (no datastore-backed resources — may be file downloads; check manifest)")
    with open(OUT / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    nat = sum(1 for m in manifest if m.get("provinces", 0) >= 20)
    print(f"\nDone. {len(manifest)} files in ./dgt_out/  ({nat} with broad ★ coverage). "
          f"Commit the folder and tell Claude.")

if __name__ == "__main__":
    main()
