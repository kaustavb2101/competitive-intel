import urllib.request,urllib.parse,json,time
MIRROR="https://maps.mail.ru/osm/tools/overpass/api/interpreter"
def overpass(q,t=180):
    data=urllib.parse.urlencode({'data':q}).encode()
    req=urllib.request.Request(MIRROR,data=data,headers={'User-Agent':'autox/1.0'})
    with urllib.request.urlopen(req,timeout=t) as r: return json.load(r)
# Wider Mueang Rayong urban area incl Thapma(101.21) + Choeng Noen(101.29) + Map Ta Phut edge
bbox="12.655,101.155,12.725,101.310"
q=f"""[out:json][timeout:180];
(way["building"]({bbox}););
out body geom;"""
t=time.time();d=overpass(q);n=len(d['elements'])
print(f"{n} buildings in {time.time()-t:.1f}s")
json.dump(d,open('bldg_wide.json','w'))
