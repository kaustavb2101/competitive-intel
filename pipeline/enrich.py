import json,time,urllib.request,urllib.parse,collections,os,sys
sample=json.load(open('sample.json'))
done={}
if os.path.exists('enriched.json'):
    for x in json.load(open('enriched.json')):
        if x.get('counts'): done[x['code']]=x
EP=["https://overpass.kumi.systems/api/interpreter","https://overpass-api.de/api/interpreter"]
def q(lat,lng):
 return f"""[out:json][timeout:40];
(node(around:10000,{lat},{lng})["amenity"="fuel"];)->.fuel;
(node(around:10000,{lat},{lng})["shop"~"^(motorcycle|motorcycle_repair|car|car_repair|car_parts|tyres|motorcycle_parts)$"];)->.veh;
(node(around:10000,{lat},{lng})["amenity"="marketplace"];node(around:10000,{lat},{lng})["shop"~"^(supermarket|convenience|mall)$"];)->.mkt;
(node(around:10000,{lat},{lng})["shop"~"^(agrarian|farm|hardware|trade|doityourself)$"];)->.agri;
(node(around:10000,{lat},{lng})["amenity"~"^(townhall|school|hospital|clinic|police)$"];)->.civic;
(node(around:10000,{lat},{lng})["amenity"="bank"];)->.bank;
(nwr(around:10000,{lat},{lng})["name"~"ศรีสวัสดิ์|เงินติดล้อ|เมืองไทย ลิ|เฮงลิส|เงินไชโย|srisawad|tidlor",i];)->.comp;
.fuel out count;.veh out count;.mkt out count;.agri out count;.civic out count;.bank out count;.comp out count;
.comp out center 25;"""
def call(query,tmo=55):
 d=urllib.parse.urlencode({'data':query}).encode()
 for ep in EP:
  try:
   return json.load(urllib.request.urlopen(urllib.request.Request(ep,data=d,headers={'User-Agent':'acq/1'}),timeout=tmo))
  except Exception as e: last=str(e)[:60]
 return None
CATS=['fuel','veh','mkt','agri','civic','bank','comp']
todo=[b for b in sample if b['code'] not in done]
N=int(sys.argv[1]) if len(sys.argv)>1 else 6
for b in todo[:N]:
 r=call(q(b['lat'],b['lng']))
 if not r: print("fail",b['prov']); continue
 c={};ci=0;comp=[]
 for el in r['elements']:
  if el['type']=='count': c[CATS[ci]]=int(el.get('tags',{}).get('total',0));ci+=1
  else:
   la=el.get('lat') or el.get('center',{}).get('lat');lo=el.get('lon') or el.get('center',{}).get('lon')
   if la is not None and len(comp)<25: comp.append({'lat':round(la,5),'lng':round(lo,5),'n':el.get('tags',{}).get('name','')[:28]})
 done[b['code']]={**b,'counts':c,'comp':comp}
 print(b['prov'][:12],c)
 time.sleep(1)
json.dump(list(done.values()),open('enriched.json','w'),ensure_ascii=False)
print("saved total:",len(done))
