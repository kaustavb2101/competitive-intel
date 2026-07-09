"""Geocoder member — raises location accuracy: tambon/zip centroid -> precise.
Runnable in Claude Code. Uses Google Places Text Search (needs GOOGLE_MAPS_API_KEY);
swap in Nominatim/OSM if you prefer no key. Emits a candidate delta file; it does NOT
touch the master — the Validator gate + Orchestrator do the merge.

Usage:
    export GOOGLE_MAPS_API_KEY=...
    python3 geocoder.py --in ../source-data/branches_final.json --batch 50 --out candidates.json
"""
import os, json, time, argparse, urllib.parse, urllib.request

PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

def distinctive_token(name):
    """Pull the branch's distinctive token (drops the เงินไชโย/สาขา boilerplate)."""
    t = name.replace("เงินไชโย", "").replace("สาขา", "").strip()
    return t.split("(")[0].strip()[:20]

def query_places(name, subdistrict, prov, key):
    q = f"{name} {subdistrict} {prov}"
    url = PLACES_URL + "?" + urllib.parse.urlencode({"query": q, "language": "th", "key": key})
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.load(r)
    if d.get("status") != "OK" or not d.get("results"):
        return None
    top = d["results"][0]
    loc = top["geometry"]["location"]
    return {"name": top.get("name", ""), "lat": loc["lat"], "lng": loc["lng"],
            "token": distinctive_token(name),
            "phone": None, "rating": top.get("rating"),
            "place_id": top.get("place_id")}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", default="candidates.json")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--only-imprecise", action="store_true", default=True,
                    help="only branches not already 'places'/'building' precise")
    args = ap.parse_args()
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        raise SystemExit("Set GOOGLE_MAPS_API_KEY (or edit query_places to use Nominatim).")

    branches = json.load(open(args.inp))
    todo = [b for b in branches if b.get("prec") not in ("places", "building")] if args.only_imprecise else branches
    todo = todo[:args.batch]
    cands = {}
    for i, b in enumerate(todo):
        try:
            c = query_places(b["name"], b.get("subdistrict", ""), b["prov"], key)
            if c: cands[b["code"]] = c
            print(f"[{i+1}/{len(todo)}] {b['code']} {b['name'][:24]} -> {'hit' if c else 'miss'}")
        except Exception as e:
            print(f"[{i+1}/{len(todo)}] {b['code']} ERROR {e}")
        time.sleep(0.2)  # be polite to the API
    json.dump(cands, open(args.out, "w"), ensure_ascii=False, indent=1)
    print(f"wrote {len(cands)} candidates -> {args.out}")

if __name__ == "__main__":
    main()
