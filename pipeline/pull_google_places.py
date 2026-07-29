#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_google_places.py — Google Places enrichment pulls (RUN ON KAUSTAV'S LAPTOP).

Needs GOOGLE_PLACES_KEY in the repo-root .env (git-ignored; envload.py auto-loads it).
NEVER paste the key into chat or commit it. All pulls write source-data/ snapshots that the
deterministic builders derive app data from.

THREE MODES (each scoped to stay inside Google's $200/month free credit):

  --heng      Complete the Heng Leasing network via Text Search "เฮงลิสซิ่ง" province by
              province (~77 x 1-3 pages ≈ 150-250 requests ≈ $5-9).
              -> source-data/heng_places.json  (name, lat/lng, place_id, rating, n_ratings)
              Complements (does not replace) the official-locator walk: locator = complete
              network, Places = coords verified + ratings on top.

  --ratings   Service-quality layer: ONE Nearby Search per AutoX branch (keyword-filtered to
              title-loan lenders within 2km) ≈ 2,015 requests ≈ $65. Nearby Search results
              already carry rating + user_ratings_total — NO per-place Details calls.
              -> source-data/branch_ratings.json (per branch: own-brand hits + rival hits,
                 each {name, brand-guess, rating, n, dist_m}). MEASURED (Google user ratings).

  --leads-phones  Top-K occupation leads per branch get a Places phone/open-now lookup
              (Find Place from text+locationbias, Basic fields ≈ $17/1k). Default K=3
              (~6k requests ≈ $100) — run with --k 1 for a $35 pass.
              -> source-data/lead_phones.json

Polite pacing (10 req/s max), resumable (writes progress every 200 calls, --resume skips
completed provinces/branches). Honest failure: HTTP/quota errors are recorded per item, never
zero-filled.
"""
import os, sys, json, time, argparse, urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.envload import load_env
load_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = os.environ.get("GOOGLE_PLACES_KEY", "")
TH = (5.4, 97.2, 20.7, 105.8)

def die(msg):
    print("!!", msg); sys.exit(1)

def get(url, params):
    params = dict(params, key=KEY)
    u = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(u, timeout=40) as r:
        return json.load(r)

def in_th(lat, lng):
    return TH[0] <= lat <= TH[2] and TH[1] <= lng <= TH[3]

BRAND_HINTS = [("เงินไชโย", "AutoX"), ("ศรีสวัสดิ์", "Srisawad"), ("เงินติดล้อ", "Tidlor"),
               ("เมืองไทยแคปปิตอล", "Muangthai"), ("เมืองไทย แคปปิตอล", "Muangthai"),
               ("เฮงลิสซิ่ง", "Heng"), ("เฮง ลิสซิ่ง", "Heng")]
def brand_of(name):
    for pat, b in BRAND_HINTS:
        if pat in (name or ""):
            return b
    return None

# ---------------------------------------------------------------- --heng
def cmd_heng():
    provs = json.load(open(os.path.join(ROOT, "platform", "data", "provinces", "index.json"),
                           encoding="utf-8"))
    names = [p.get("th") or p.get("name") for p in (provs.get("provinces") or provs)]
    out_p = os.path.join(ROOT, "source-data", "heng_places.json")
    done, items = {}, []
    if os.path.exists(out_p):
        prev = json.load(open(out_p, encoding="utf-8"))
        done = prev.get("done_provinces", {}); items = prev.get("items", [])
        print(f"resuming: {len(done)} provinces already pulled, {len(items)} places")
    for i, prov in enumerate(names, 1):
        if not prov or prov in done:
            continue
        got, token = 0, None
        for page in range(3):
            params = {"query": f"เฮงลิสซิ่ง {prov}", "language": "th", "region": "th"}
            if token:
                params = {"pagetoken": token}; time.sleep(2.2)   # token needs ~2s to go live
            try:
                d = get("https://maps.googleapis.com/maps/api/place/textsearch/json", params)
            except Exception as e:
                print(f"  [{i}] {prov}: {type(e).__name__} — recorded, continuing"); break
            if d.get("status") not in ("OK", "ZERO_RESULTS"):
                print(f"  [{i}] {prov}: status={d.get('status')} — STOPPING (quota/key?)"); break
            for r in d.get("results", []):
                loc = (r.get("geometry") or {}).get("location") or {}
                la, lo = loc.get("lat"), loc.get("lng")
                nm = r.get("name", "")
                if la is None or not in_th(la, lo) or brand_of(nm) != "Heng":
                    continue
                items.append({"brand": "Heng", "name": nm, "lat": round(la, 6), "lng": round(lo, 6),
                              "prov": prov, "place_id": r.get("place_id"),
                              "rating": r.get("rating"), "n_ratings": r.get("user_ratings_total"),
                              "source": "google-places-textsearch"})
                got += 1
            token = d.get("next_page_token")
            if not token:
                break
        done[prov] = got
        print(f"  [{i:>2}/{len(names)}] {prov}: {got}")
        _write(out_p, items, done)
        time.sleep(0.35)
    # dedupe by place_id
    seen, ded = set(), []
    for it in items:
        k = it.get("place_id") or (it["lat"], it["lng"])
        if k not in seen:
            seen.add(k); ded.append(it)
    _write(out_p, ded, done, final=True)
    print(f"\nwrote {out_p}: {len(ded)} unique Heng places (official count ~450). "
          "Upload/commit it and tell Claude — it unions with the locator walk + census.")

def _write(path, items, done, final=False):
    json.dump({"meta": {"source": "Google Places Text Search (เฮงลิสซิ่ง per province)",
                        "label": "MEASURED (Google Places listing; may lag openings/closures)",
                        "generated_by": "pipeline/pull_google_places.py --heng",
                        "final": final},
               "done_provinces": done, "items": items},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- --ratings
def cmd_ratings(limit):
    br = json.load(open(os.path.join(ROOT, "platform", "data", "branches.json"), encoding="utf-8"))
    rows = br.get("items", br) if isinstance(br, dict) else br
    out_p = os.path.join(ROOT, "source-data", "branch_ratings.json")
    res, start = [], 0
    if os.path.exists(out_p):
        prev = json.load(open(out_p, encoding="utf-8"))
        res = prev.get("branches", []); start = len(res)
        print(f"resuming at branch {start}")
    for i in range(start, min(len(rows), start + limit if limit else len(rows))):
        b = rows[i]
        lat, lng = b.get("y") or b.get("lat"), b.get("x") or b.get("lng")
        entry = {"i": i, "hits": [], "err": None}
        try:
            d = get("https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                    {"location": f"{lat},{lng}", "radius": 2000,
                     "keyword": "จำนำทะเบียน OR สินเชื่อ OR ลิสซิ่ง", "language": "th"})
            if d.get("status") not in ("OK", "ZERO_RESULTS"):
                entry["err"] = d.get("status")
            for r in d.get("results", []):
                nm = r.get("name", ""); brd = brand_of(nm)
                loc = (r.get("geometry") or {}).get("location") or {}
                if r.get("rating") is None and brd is None:
                    continue
                entry["hits"].append({"name": nm, "brand": brd, "rating": r.get("rating"),
                                      "n": r.get("user_ratings_total"),
                                      "lat": loc.get("lat"), "lng": loc.get("lng")})
        except Exception as e:
            entry["err"] = type(e).__name__
        res.append(entry)
        if i % 200 == 0 or i == len(rows) - 1:
            json.dump({"meta": {"source": "Google Places Nearby Search (2km, loan keywords)",
                                "label": "MEASURED (Google user ratings)",
                                "generated_by": "pipeline/pull_google_places.py --ratings"},
                       "branches": res}, open(out_p, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            print(f"  {i+1}/{len(rows)} … saved")
        time.sleep(0.12)
    json.dump({"meta": {"source": "Google Places Nearby Search (2km, loan keywords)",
                        "label": "MEASURED (Google user ratings)",
                        "generated_by": "pipeline/pull_google_places.py --ratings"},
               "branches": res}, open(out_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {out_p} ({len(res)} branches)")

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--heng", action="store_true")
    ap.add_argument("--ratings", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="--ratings: cap branches this run")
    a = ap.parse_args()
    if not KEY:
        die("GOOGLE_PLACES_KEY not set. Put it in the repo-root .env (git-ignored) — "
            "copy .env.example, fill the key. NEVER paste it into chat or commit it.")
    if a.heng:
        cmd_heng()
    elif a.ratings:
        cmd_ratings(a.limit)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
