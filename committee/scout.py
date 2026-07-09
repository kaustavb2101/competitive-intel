"""Competitor Scout member — maps rival title-lenders province by province.

Uses Google Places Text Search (needs GOOGLE_MAPS_API_KEY), so it runs from any IP incl. CI.
Pulls the main rivals (Srisawad, Muangthai Capital, Ngern Tid Lor, Krungsri Auto) per province,
classifies by brand, dedups by place_id, and writes a competitor census (province -> rival count)
plus point locations. Joins the count to branches as `competitors_prov`.

    export GOOGLE_MAPS_API_KEY=...
    python3 scout.py --in ../source-data/branches_final.json --provinces ระยอง ชลบุรี เชียงใหม่
"""
import os, json, time, argparse, urllib.parse, urllib.request, collections

PLACES = "https://maps.googleapis.com/maps/api/place/textsearch/json"
BRANDS = {  # query term -> canonical brand
    "ศรีสวัสดิ์ เงินสดทันใจ": "Srisawad",
    "เมืองไทย แคปปิตอล": "Muangthai",
    "เงินติดล้อ": "Tidlor",
    "กรุงศรี ออโต้ สินเชื่อรถ": "Krungsri",
}
def classify(name):
    if "ศรีสวัสดิ์" in name: return "Srisawad"
    if "เมืองไทย" in name: return "Muangthai"
    if "ติดล้อ" in name: return "Tidlor"
    if "กรุงศรี" in name: return "Krungsri"
    return None

def query(term, prov, key, rows=10):
    url = PLACES + "?" + urllib.parse.urlencode({"query": f"{term} {prov}", "language": "th", "key": key})
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.load(r)
    out = []
    for res in (d.get("results") or [])[:rows]:
        b = classify(res.get("name", ""))
        if not b: continue
        loc = res["geometry"]["location"]
        out.append({"brand": b, "prov": prov, "lat": loc["lat"], "lng": loc["lng"],
                    "place_id": res.get("place_id")})
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--provinces", nargs="+", required=True)
    args = ap.parse_args()
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key: raise SystemExit("Set GOOGLE_MAPS_API_KEY.")
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, "..", "source-data")

    seen, points = set(), []
    for prov in args.provinces:
        for term in BRANDS:
            for p in query(term, prov, key):
                if p["place_id"] in seen: continue
                seen.add(p["place_id"]); points.append(p)
            time.sleep(0.2)
        print(f"  {prov}: cumulative {len(points)} rival branches")

    # merge with any existing scouted points, rebuild census
    path = os.path.join(src, "competitors_scout.json")
    existing = json.load(open(path)) if os.path.exists(path) else []
    ex_ids = {p.get("place_id") for p in existing if p.get("place_id")}
    existing += [p for p in points if p["place_id"] not in ex_ids]
    json.dump(existing, open(path, "w"), ensure_ascii=False, indent=1)
    census = dict(collections.Counter(p["prov"] for p in existing))
    json.dump(census, open(os.path.join(src, "competitor_census.json"), "w"), ensure_ascii=False, indent=1)

    branches = json.load(open(args.inp)); j = 0
    for b in branches:
        n = census.get(b["prov"].strip())
        if n is not None: b["competitors_prov"] = n; j += 1
    json.dump(branches, open(args.inp, "w"), ensure_ascii=False)
    print(f"competitor census: {census} · joined to {j} branches")
    return {"member": "scout", "provinces_measured": len(census), "rival_branches": len(existing)}

if __name__ == "__main__":
    main()
