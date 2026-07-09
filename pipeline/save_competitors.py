import json

# Live competitors pulled from Google Places (Rayong), deduplicated + tagged by brand
raw = [
 # Srisawad
 ("Srisawad","ศรีสวัสดิ์ Noen Phra",12.683758,101.232661),
 ("Srisawad","ศรีสวัสดิ์ Phloen Chai 5",12.698656,101.217385),
 ("Srisawad","ศรีสวัสดิ์ Talat Mo Dit (Thapma)",12.691449,101.239729),
 ("Srisawad","ศรีสวัสดิ์ Rayong 2 (Tha Pradu)",12.681888,101.271848),
 ("Srisawad","ศรีสวัสดิ์ Map Ta Phut",12.712949,101.168668),
 ("Srisawad","ศรีสวัสดิ์ Khot Hin",12.700086,101.199414),
 ("Srisawad","ศรีสวัสดิ์ Yaek Noen Samli",12.702397,101.186630),
 ("Srisawad","ศรีสวัสดิ์ Nong Mahat",12.695656,101.252328),
 ("Srisawad","ศรีสวัสดิ์ Talat Lao (Choeng Noen)",12.684993,101.299947),
 ("Srisawad","ศรีสวัสดิ์ Ta Khan (Ban Khai)",12.718595,101.308116),
 # Muangthai Capital
 ("Muangthai","เมืองไทย Ban Laeng",12.680959,101.283646),
 ("Muangthai","เมืองไทย Phloen Chai 4 (Thapma)",12.698806,101.219009),
 ("Muangthai","เมืองไทย Choeng Noen",12.682675,101.266026),
 ("Muangthai","เมืองไทย Noen Phra",12.683606,101.232489),
 ("Muangthai","เมืองไทย Map Ta Phut",12.711012,101.172024),
 ("Muangthai","เมืองไทย Map Ya (Map Ta Phut)",12.731258,101.160408),
 ("Muangthai","เมืองไทย Choeng Noen 2",12.692955,101.288405),
 ("Muangthai","เมืองไทย Leasing Choeng Noen",12.682677,101.266031),
 ("Muangthai","เมืองไทย 3139 (Choeng Noen)",12.686657,101.301851),
 ("Muangthai","เมืองไทย Map Ta Phut 2",12.719793,101.171434),
 # Ngern Tid Lor
 ("Tidlor","เงินติดล้อ Choeng Noen",12.682154,101.267467),
 ("Tidlor","เงินติดล้อ Thapma",12.698420,101.218540),
 ("Tidlor","เงินติดล้อ Map Ta Phut",12.686592,101.165371),
 ("Tidlor","เงินติดล้อ Talat Star",12.685185,101.271813),
 ("Tidlor","เงินติดล้อ Bangkok Hospital Rayong",12.675890,101.219399),
 ("Tidlor","เงินติดล้อ Ban Phe",12.625681,101.433872),
 ("Tidlor","เงินติดล้อ Taphong",12.649402,101.343635),
 ("Tidlor","เงินติดล้อ Prasae (Klaeng)",12.783584,101.732127),
 ("Tidlor","เงินติดล้อ Nikhom Phatthana Soi 13",12.887416,101.099225),
 # Krungsri Auto
 ("Krungsri","กรุงศรี ออโต้ Thapma",12.697196,101.215440),
]
comps=[{"brand":b,"name":n,"lat":la,"lng":ln} for (b,n,la,ln) in raw]
json.dump(comps, open("rayong_competitors.json","w"), ensure_ascii=False, indent=0)
from collections import Counter
print("saved", len(comps), "competitor branches")
print(dict(Counter(c["brand"] for c in comps)))
