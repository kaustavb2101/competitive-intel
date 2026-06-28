#!/usr/bin/env python3
"""
AutoX · เงินไชโย — Recursive Enrichment Loop
=============================================
One re-runnable pipeline that refreshes every reachable data source, recomputes
per-branch features, re-scores both borrower segments, and logs each iteration.

Run once:        python3 autox_enrich_loop.py
Run on a loop:   python3 autox_enrich_loop.py --watch --interval 86400   # daily
Force refresh:   python3 autox_enrich_loop.py --force

Each source has a freshness TTL; the loop only re-pulls what's stale, so repeated
runs are cheap and the dataset keeps "refining itself." Outputs:
  branches_final.json · autox-branch-features.csv · deck_payload.json · iteration_log.json

NOTE on blocked sources: data.go.th (DIW factories, DLT vehicles) Cloudflare-blocks
datacenter IPs. Run THIS script from a Thai/residential network and set
DATA_GO_TH_TOKEN to also pull those (hooks included, off by default).
"""
import os, json, time, math, csv, argparse, datetime, urllib.request, urllib.parse, collections

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
CACHE = os.path.join(ROOT, "cache"); os.makedirs(CACHE, exist_ok=True)
# the canonical master lives in source-data/ (everything in platform/data is derived from it)
MASTER = os.path.join(REPO, "source-data", "branches_final.json")
UA = {"User-Agent": "Mozilla/5.0"}
OVERPASS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]

# ── SOURCE REGISTRY ───────────────────────────────────────────────────────────
# OSM POI layers: name -> (overpass selector, TTL days)
OSM_LAYERS = {
 "industrial":      ('way(area.th)["landuse"="industrial"];relation(area.th)["landuse"="industrial"];nwr(area.th)["man_made"="works"];', 30),
 "bank":            ('node(area.th)["amenity"="bank"];', 30),
 "atm":             ('node(area.th)["amenity"="atm"];', 30),
 "convenience":     ('node(area.th)["shop"="convenience"];', 30),
 "hotel":           ('node(area.th)["tourism"="hotel"];', 30),
 "fresh_market":    ('nwr(area.th)["amenity"="marketplace"];', 30),
 "restaurant":      ('node(area.th)["amenity"="restaurant"];', 30),
 "supermarket":     ('nwr(area.th)["shop"="supermarket"];', 30),
 "pharmacy":        ('node(area.th)["amenity"="pharmacy"];', 30),
 "gold":            ('nwr(area.th)["shop"~"^(jewelry|gold)$"];', 30),
 "vehicle_commerce":('nwr(area.th)["shop"~"^(car|motorcycle|car_repair)$"];', 30),
 "school":          ('nwr(area.th)["amenity"="school"];', 30),
 "civic":           ('nwr(area.th)["office"="government"];node(area.th)["amenity"="townhall"];node(area.th)["amenity"~"^(hospital|clinic)$"];nwr(area.th)["amenity"~"^(university|college)$"];', 30),
}
# OAE crop production (national trend) CKAN package ids
OAE_CROPS = {"rice":"dataoae1104","rubber":"dataoae1404","maize":"dataoae1204",
             "cassava":"ปริมาณการผลิตมันสำปะหลัง","oilpalm":"ปริมาณการผลิตปาล์มน้ำมัน"}
# World Bank Pink Sheet (all commodities incl. livestock/fisheries/forestry/gold)
PINKSHEET = "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/related/CMO-Historical-Data-Monthly.xlsx"
WB_COMMODITIES = {  # column name -> (label, crop/segment region weights N/I/C/S, stress sign)
 "Rice, Thai 5%":"rice","Rubber, RSS3":"rubber","Palm oil":"palm","Sugar, world":"sugar","Maize":"maize",
 "Beef **":"beef","Chicken **":"chicken","Fishmeal":"fishmeal","Shrimps, Mexican":"shrimp",
 "Logs, Cameroon":"logs","Sawnwood, Malaysian":"sawnwood","Gold":"gold"}
# HDX feeds (resource ids)
HDX_POP = "a5d0b682-1644-4a2d-a9d7-90f1a0fdc959"      # UNFPA district population
HDX_RAIN = "76a5bb85-9a55-4cda-afcb-6cb4fa2739cc"     # WFP subnational rainfall

# ── helpers ───────────────────────────────────────────────────────────────────
def fresh(path, ttl_days):
    return os.path.exists(path) and (time.time()-os.path.getmtime(path)) < ttl_days*86400

def get(url, tmo=90):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=tmo).read()

def overpass(sel, tmo=230):
    q = f'[out:json][timeout:220];area["ISO3166-1"="TH"][admin_level=2]->.th;({sel})->.s;.s out center;'
    data = urllib.parse.urlencode({"data": q}).encode()
    for ep in OVERPASS:
        try:
            r = urllib.request.urlopen(urllib.request.Request(ep, data=data, headers=UA), timeout=tmo)
            els = json.loads(r.read())["elements"]; pts=[]
            for e in els:
                la=e.get("lat") or e.get("center",{}).get("lat"); lo=e.get("lon") or e.get("center",{}).get("lon")
                if la is not None: pts.append([round(lo,5),round(la,5)])
            return pts
        except Exception: continue
    return None

def hav(a,b,c,d):
    R=6371;p=math.pi/180;x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2
    return 2*R*math.asin(math.sqrt(x))

def bucket(pts):
    g=collections.defaultdict(list)
    for lo,la in pts: g[(round(la*10),round(lo*10))].append((la,lo))
    return g

def count_within(la,lo,g,r=10):
    c=0;kla=round(la*10);klo=round(lo*10)
    for dla in(-1,0,1):
        for dlo in(-1,0,1):
            for pla,plo in g.get((kla+dla,klo+dlo),[]):
                if hav(la,lo,pla,plo)<=r: c+=1
    return c

# ── stages ────────────────────────────────────────────────────────────────────
def stage_osm(force, log):
    layers={}
    for name,(sel,ttl) in OSM_LAYERS.items():
        path=os.path.join(CACHE,f"osm_{name}.json")
        if not force and fresh(path,ttl):
            layers[name]=json.load(open(path)); log[name]="cached"; continue
        pts=overpass(sel)
        if pts is not None:
            json.dump(pts,open(path,"w")); layers[name]=pts; log[name]=f"pulled {len(pts)}"
        elif os.path.exists(path):
            layers[name]=json.load(open(path)); log[name]="stale-kept"
    return layers

def stage_commodities(force, log):
    path=os.path.join(CACHE,"pinksheet.xlsx")
    if force or not fresh(path,15):
        try: open(path,"wb").write(get(PINKSHEET,120)); log["pinksheet"]="pulled"
        except Exception as e: log["pinksheet"]=f"err {e}"
    try:
        import openpyxl
        ws=openpyxl.load_workbook(path,read_only=True,data_only=True)["Monthly Prices"]
        rows=[list(r) for r in ws.iter_rows(values_only=True)]; hdr=rows[4]; data=rows[6:]
        out={}
        for j,n in enumerate(hdr):
            nm=str(n).strip() if n else ""
            if nm in WB_COMMODITIES:
                lab=WB_COMMODITIES[nm]
                s=[ (lambda x: (float(x) if str(x).replace('.','',1).replace('-','').isdigit() else None))(r[j]) for r in data]
                li=max(i for i in range(len(s)) if s[i] is not None)
                yi=li-12; yoy=100*(s[li]-s[yi])/s[yi] if yi>=0 and s[yi] else None
                out[lab]={"latest":round(s[li],3),"date":str(data[li][0]),"yoy":round(yoy,1) if yoy is not None else None}
        json.dump(out,open(os.path.join(CACHE,"commodities.json"),"w"))
        log["commodities"]=f"{len(out)} priced"
        return out
    except Exception as e:
        log["commodities"]=f"parse-skip {e}"; return json.load(open(os.path.join(CACHE,"commodities.json")))

def stage_features(branches, layers, log):
    B={k:bucket(v) for k,v in layers.items()}
    keymap={"industrial":"ind10","bank":"bank10","atm":"atm10","convenience":"cvs10","hotel":"hotel10",
            "fresh_market":"fmkt10","restaurant":"rest10","supermarket":"super10","pharmacy":"pharm10",
            "gold":"gold10","vehicle_commerce":"veh10","school":"sch10","civic":"civic10"}
    for b in branches:
        for cat,g in B.items():
            b[keymap.get(cat,cat+"10")]=count_within(b["lat"],b["lng"],g)
    log["features"]=f"{len(branches)} branches × {len(B)} layers"
    return branches

def stage_score(branches, com, log):
    def pct(xs): s=sorted(xs); return lambda v:100*sum(1 for x in s if x<=v)/len(s)
    fm=pct([b.get("fmkt10",0) for b in branches]); rs=pct([b.get("rest10",0) for b in branches])
    sm=pct([b.get("super10",0) for b in branches]); wa=pct([b.get("dist_workingage") or 0 for b in branches])
    ve=pct([b.get("veh10",0) for b in branches]); gd=pct([b.get("gold10",0) for b in branches])
    # crop price stress (rice/rubber/palm drive it); livestock buffer where protein prices firm
    cs={"rice":max(0,-(com.get("rice",{}).get("yoy") or 0))/100,
        "rubber":max(0,-(com.get("rubber",{}).get("yoy") or 0))/100,
        "palm":max(0,-(com.get("palm",{}).get("yoy") or 0))/100}
    LIVE_BUF={"Isan":0.10,"Central&BKK":0.06,"East":0.06,"North":0.05,"South":0.04}
    CROPREG={"Isan":"Isan","North":"North","South":"South","Central&BKK":"Central","East":"Central"}
    import statistics as st
    dmed=st.median([b.get("demand",0) for b in branches])
    for b in branches:
        # agri price stress by region crop-mix (rice-heavy Isan/North/Central, rubber/palm South)
        reg=CROPREG.get(b["region"],"Central")
        mix={"Isan":(.85,.10,.05),"North":(.75,.05,.20),"Central":(.80,.05,.15),"South":(.05,.55,.40)}[reg]
        ps=mix[0]*cs["rice"]+mix[1]*cs["rubber"]+mix[2]*cs["palm"]
        dr=b.get("rain_3mo_anom"); drs=max(0,(100-dr)/100) if dr is not None else 0
        urban=0.30 if (b.get("demand",0)>dmed*1.6 or b.get("bank10",0)>25) else (0.6 if b.get("demand",0)>dmed else 1.0)
        agri=100*(0.65*ps+0.35*drs)*urban*1.6
        b["agri_pd"]=round(min(100,agri)*(1-LIVE_BUF.get(b["region"],0.05)))
        b["merchant_demand"]=round(0.24*fm(b.get("fmkt10",0))+0.20*rs(b.get("rest10",0))+0.10*sm(b.get("super10",0))
                                   +0.24*wa(b.get("dist_workingage") or 0)+0.22*b.get("tourism_score",0))
        b["collateral_density"]=round(0.60*ve(b.get("veh10",0))+0.40*gd(b.get("gold10",0)))
    log["score"]="agri_pd · merchant_demand · collateral_density"
    return branches

def write_outputs(branches, com, log):
    json.dump(branches, open(MASTER,"w"), ensure_ascii=False)
    cols=["store_code","name","province","region","lat","lng","agri_pd","merchant_demand",
          "collateral_density","merchant_pd","tourism_score","veh10","gold10","fmkt10","rest10",
          "dist_workingage","rain_3mo_anom","own10","opportunity"]
    with open(os.path.join(ROOT,"autox-branch-features.csv"),"w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(cols)
        for b in branches:
            w.writerow([b.get(k.replace("store_code","code").replace("province","prov"),"") for k in cols])
    log["written"]=["branches_final.json","autox-branch-features.csv"]

def iterate(force=False, derive_only=False):
    import derive  # projection master → platform/data (same dir)
    t0=time.time(); log={"ts":datetime.datetime.now().isoformat(timespec="seconds")}
    branches=json.load(open(MASTER, encoding="utf-8"))
    if derive_only:
        log["mode"]="derive-only (no network; re-project master → platform/data)"
    else:
        layers=stage_osm(force, log)
        com=stage_commodities(force, log)
        branches=stage_features(branches, layers, log)
        branches=stage_score(branches, com, log)
        write_outputs(branches, com, log)
    # close the loop: push the refreshed master into the deployable app data
    derive.run()
    log["derived"]=["platform/data/branches.json","platform/data/meta.json"]
    log["seconds"]=round(time.time()-t0,1)
    hist_path=os.path.join(ROOT,"iteration_log.json")
    hist=json.load(open(hist_path)) if os.path.exists(hist_path) else []
    hist.append(log); json.dump(hist, open(hist_path,"w"), ensure_ascii=False, indent=2)
    print(f"[{log['ts']}] iteration done in {log['seconds']}s — "
          f"{sum(1 for v in log.values() if 'pulled' in str(v))} sources refreshed")
    return log

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--watch",action="store_true",help="run forever on an interval")
    ap.add_argument("--interval",type=int,default=86400,help="seconds between iterations")
    ap.add_argument("--force",action="store_true",help="ignore cache TTL, refresh all")
    ap.add_argument("--derive-only",action="store_true",
                    help="skip all network pulls; just re-project the master into platform/data + log it")
    a=ap.parse_args()
    if a.watch:
        print(f"recursive loop · every {a.interval}s · Ctrl-C to stop")
        while True:
            try: iterate(a.force, a.derive_only)
            except Exception as e: print("iteration error:",e)
            time.sleep(a.interval)
    else:
        iterate(a.force, a.derive_only)
