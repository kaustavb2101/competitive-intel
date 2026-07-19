#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_place_ratings.py — MEASURED Google rating + review count for the rival title-lender
branches we already located (competitive risk, objective #2 · a SERVICE-QUALITY layer on top
of rival density).

Reads source-data/competitors_scout.json (755 rival branches with a Google `place_id`, pulled by
committee/scout.py) and calls the Google Places (New) Place Details endpoint per place_id for its
`rating` + `userRatingCount` + `businessStatus`. Writes source-data/competitor_ratings.json.

WHY place_id, not text search: text search can't reliably find Thai title-lender storefronts
(verified — our own brand and rival brand-name queries both return 0). The scout captured stable
place_ids on a prior Nearby pull, so Place-Details-by-id is the only reliable path — and it is the
one Google endpoint that returns a rating. (Our OWN branches have no captured place_ids and are not
findable by text, so an AutoX-branch reputation is not obtainable this way — stated, not faked.)

NETWORK (Google Places New). Not in the offline determinism gate. Resumable + cached: re-runs only
fetch place_ids missing from the cache, so a partial run costs nothing to finish.

Key: GOOGLE_PLACES_KEY from the environment or ./.env (never committed).

  python3 pull_place_ratings.py                 # fetch all missing, write competitor_ratings.json
  python3 pull_place_ratings.py --limit 50      # bounded first batch (cost control)
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data")
SCOUT = os.path.join(SRC, "competitors_scout.json")
OUT = os.path.join(SRC, "competitor_ratings.json")
CACHE = os.path.join(SRC, ".place_ratings_cache.json")   # gitignored scratch
DETAILS_URL = "https://places.googleapis.com/v1/places/%s"
FIELDS = "displayName,rating,userRatingCount,businessStatus"


def _load_key():
    k = os.environ.get("GOOGLE_PLACES_KEY")
    if k:
        return k.strip()
    envp = os.path.join(ROOT, ".env")
    if os.path.exists(envp):
        for line in open(envp, encoding="utf-8"):
            if line.startswith("GOOGLE_PLACES_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("pull_place_ratings.py: GOOGLE_PLACES_KEY not in env or ./.env")


def _load_json(p, default):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def _fetch(pid, key):
    req = urllib.request.Request(
        DETAILS_URL % urllib.parse.quote(pid),
        headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max NEW place_ids to fetch this run (0 = all)")
    ap.add_argument("--sleep", type=float, default=0.12, help="seconds between calls")
    args = ap.parse_args()

    key = _load_key()
    scout = _load_json(SCOUT, [])
    cache = _load_json(CACHE, {})
    todo = [r for r in scout if r.get("place_id") and r["place_id"] not in cache]
    if args.limit:
        todo = todo[:args.limit]
    print("scout=%d cached=%d to-fetch=%d" % (len(scout), len(cache), len(todo)))

    ok = err = 0
    for i, r in enumerate(todo, 1):
        pid = r["place_id"]
        try:
            d = _fetch(pid, key)
            cache[pid] = {"rating": d.get("rating"), "n": d.get("userRatingCount"),
                          "name": (d.get("displayName") or {}).get("text"),
                          "status": d.get("businessStatus")}
            ok += 1
        except Exception as e:  # noqa: BLE001 — one bad id must not abort the run
            cache[pid] = {"error": str(e)[:120]}
            err += 1
        if i % 50 == 0 or i == len(todo):
            json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
            print("  %d/%d (ok=%d err=%d)" % (i, len(todo), ok, err), flush=True)
        time.sleep(args.sleep)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    # project cache -> committed competitor_ratings.json (join scout brand/prov onto each rated id)
    rows = []
    for r in scout:
        pid = r.get("place_id")
        c = cache.get(pid) if pid else None
        if not c or c.get("rating") is None:
            continue
        rows.append({"place_id": pid, "brand": r.get("brand"), "prov": r.get("prov"),
                     "rating": c["rating"], "n": c.get("n") or 0})
    rows.sort(key=lambda x: (x["brand"] or "", -(x["rating"] or 0)))
    payload = {
        "meta": {
            "title": "Measured Google rating + review count for located rival title-lender branches",
            "generated_by": "pipeline/pull_place_ratings.py",
            "label": "MEASURED — Google Places (New) Place Details rating + userRatingCount, joined onto "
                     "the scout's rival place_ids. A SAMPLE (the located subset), not the full census. "
                     "AutoX-branch reputation is NOT obtainable (our branches have no captured place_ids "
                     "and are not findable by text search) — stated, not inferred.",
            "source": "Google Places API (New) · Place Details",
            "n_rated": len(rows), "n_scout": len(scout),
        },
        "ratings": rows,
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("wrote %s — %d rated of %d scout ids" % (OUT, len(rows), len(scout)))


if __name__ == "__main__":
    main()
