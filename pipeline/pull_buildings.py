import urllib.request,json,time

MIRROR="https://maps.mail.ru/osm/tools/overpass/api/interpreter"

def overpass(q,timeout=120):
    data=urllib.parse.urlencode({'data':q}).encode()
    req=urllib.request.Request(MIRROR,data=data,headers={'User-Agent':'autox-catchment/1.0'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.load(r)

# Two focused catchments in Rayong:
# A) Mueang Rayong urban core (contested - competitors cluster here)
# B) Pluak Daeng factory zone (white space, factory core)
catchments={
 "mueang":{"name":"Mueang Rayong core","lat":12.681,"lng":101.276,"r":0.018},  # ~2km box
 "pluak":{"name":"Pluak Daeng factory zone","lat":12.880,"lng":101.180,"r":0.022},
}

for key,c in catchments.items():
    s,w=c['lat']-c['r'],c['lng']-c['r']*1.1
    n,e=c['lat']+c['r'],c['lng']+c['r']*1.1
    bbox=f"{s},{w},{n},{e}"
    q=f"""[out:json][timeout:120];
(way["building"]({bbox});
 relation["building"]["type"="multipolygon"]({bbox}););
out body geom;"""
    try:
        t=time.time()
        d=overpass(q)
        els=d.get('elements',[])
        print(f"{key}: {len(els)} buildings in {time.time()-t:.1f}s")
        json.dump(d,open(f'bldg_{key}.json','w'))
    except Exception as ex:
        print(f"{key}: ERROR {ex}")
