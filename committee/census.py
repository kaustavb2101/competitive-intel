"""Industry Census member — authoritative factory data from DIW.

THE UNBLOCK: data.go.th is geo-blocked to Thai IPs, but DIW's OWN CKAN portal
(diw-dataset.diw.go.th) is reachable from ANY IP — including GitHub Actions and any cloud host.
So the factory census needs no Thai connection.

Pulls factory registries, aggregates by province+district (name, capital, workers, horsepower),
joins to the master by district, and writes:
  - source-data/factory_census_national.json   (per province|district rollup)
  - factory_diw / workers_diw / capital_diw on each branch record

    python3 census.py --in ../source-data/branches_final.json

Datasets (DIW CKAN):
  factype3       national category-3 factories (>50HP / >50 workers) — 67k records, all 77 provinces
  fac-eec-class3 EEC detail (Chonburi/Rayong/Chachoengsao)
"""
import os, csv, io, json, argparse, urllib.request, collections

CKAN = "https://diw-dataset.diw.go.th/api/3/action/package_show?id="
DATASETS = ["factype3"]           # add "factype2", "fac-eec-class3" for more depth
P, D, C, W, H = "จังหวัด", "อำเภอ", "เงินทุนรวม(ล้านบาท)", "คนงานรวม", "แรงม้า"

def num(x):
    try: return float(str(x).replace(",", ""))
    except: return 0.0

def resource_url(dsid):
    with urllib.request.urlopen(CKAN + dsid, timeout=40) as r:
        d = json.load(r)
    return d["result"]["resources"][0]["url"]

def fetch_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "autox-census/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(raw)))

def build_census(datasets=DATASETS):
    cen = collections.defaultdict(lambda: {"factories": 0, "workers": 0.0, "capital": 0.0, "hp": 0.0})
    for ds in datasets:
        rows = fetch_csv(resource_url(ds))
        print(f"  {ds}: {len(rows)} records")
        for r in rows:
            if P not in r: continue
            k = (r[P].strip(), r[D].strip())
            cen[k]["factories"] += 1
            cen[k]["workers"]   += num(r.get(W))
            cen[k]["capital"]   += num(r.get(C))
            cen[k]["hp"]        += num(r.get(H))
    return {f"{p}|{d}": {"factories": v["factories"], "workers": int(v["workers"]),
                         "capital_Mbaht": int(v["capital"]), "horsepower": int(v["hp"])}
            for (p, d), v in cen.items()}


# --- DLT vehicle census (cumulative registered vehicles by province + type) ---
DLT_CKAN = "https://gdcatalog.dlt.go.th/api/3/action/package_show?id="
DLT_DATASET = "dataset_1_1_04"     # รถจดทะเบียนสะสม — reachable from any IP (NOT data.go.th)
VP, VT, VN = "จังหวัด", "ประเภทรถ", "จำนวนรถ"

def _vcls(t):
    if "จักรยานยนต์" in t: return "motorcycle"
    if "บรรทุกส่วนบุคคล" in t: return "pickup"
    if "นั่งส่วนบุคคล" in t or "นั่งไม่เกิน" in t: return "car"
    if "บรรทุก" in t or "ลากจูง" in t: return "truck"
    return "other"

def build_vehicle_census():
    # resource URLs rotate monthly; pick the newest CSV resource on the dataset
    with urllib.request.urlopen(DLT_CKAN + DLT_DATASET, timeout=40) as r:
        d = json.load(r)
    res = [x for x in d["result"]["resources"] if (x.get("format") or "").upper() == "CSV"]
    if not res: raise RuntimeError("no CSV resource on DLT dataset")
    res.sort(key=lambda x: x.get("last_modified") or x.get("created") or "", reverse=True)
    rows = None; err = None
    for cand in res[:3]:                      # try newest first, fall back
        try:
            rows = fetch_csv(cand["url"]); break
        except Exception as e: err = e
    if rows is None: raise RuntimeError(f"all DLT resources failed: {err}")
    prov = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        if VP not in r: continue
        prov[r[VP].strip()][_vcls(r[VT])] += num(r.get(VN))
    out = {}
    for p, c in prov.items():
        tot = sum(c.values())
        out[p] = {"total": tot, "motorcycle": c["motorcycle"], "car": c["car"],
                  "pickup": c["pickup"], "moto_share": round(100*c["motorcycle"]/tot) if tot else 0}
    return out

def norm(s): return (s or "").replace("อ.", "").replace("เขต", "").strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--census-out", default=None)
    args = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    census_out = args.census_out or os.path.join(here, "..", "source-data", "factory_census_national.json")

    print("Industry Census — pulling DIW (reachable from any IP)…")
    census = build_census()
    json.dump(census, open(census_out, "w"), ensure_ascii=False)
    print(f"  districts with authoritative factory data: {len(census)}")

    branches = json.load(open(args.inp))
    joined = 0
    for b in branches:
        c = census.get(f"{b['prov'].strip()}|{norm(b.get('district',''))}")
        if c:
            b["factory_diw"], b["workers_diw"], b["capital_diw"] = c["factories"], c["workers"], c["capital_Mbaht"]
            joined += 1
        else:
            b.setdefault("factory_diw", None)
    # vehicles (DLT, reachable from any IP)
    try:
        vc = build_vehicle_census()
        json.dump(vc, open(os.path.join(here, "..", "source-data", "vehicle_census_province.json"), "w"), ensure_ascii=False)
        vj = 0
        for b in branches:
            v = vc.get(b["prov"].strip())
            if v:
                b["veh_total_dlt"], b["veh_moto_dlt"], b["moto_share"] = v["total"], v["motorcycle"], v["moto_share"]
                vj += 1
        print(f"  DLT vehicles: {len(vc)} provinces, joined to {vj} branches")
    except Exception as e:
        print(f"  (vehicle census skipped: {e})")
    json.dump(branches, open(args.inp, "w"), ensure_ascii=False)
    pct = 100 * joined // len(branches)
    print(f"  joined {joined}/{len(branches)} branches ({pct}%) to authoritative factory data")
    return {"member": "census", "districts": len(census), "joined": joined, "join_pct": pct}

if __name__ == "__main__":
    main()
