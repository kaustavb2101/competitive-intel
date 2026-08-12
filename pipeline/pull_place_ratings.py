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
fetch place_ids missing or past their refresh age, so a partial run costs nothing to finish.

COST — read this before changing the cache path or the limit (2026-08-12). This script is the most
expensive thing in the repo: it calls billed Place Details once per competitor place_id, and there
are 1,740 of them. It was written to be nearly free on re-runs, and it was not, for one reason: the
cache lived at `source-data/.place_ratings_cache.json`, which is GITIGNORED. A CI runner checks the
repo out fresh, so the cache was empty on arrival EVERY time and every scheduled run re-bought all
1,740 ratings at full price. Combined with `pull_swarm.py` ignoring its own `cadence` field (fixed
the same day), this feed billed daily rather than weekly and is the bulk of a USD 300 Places bill.

Three things keep it cheap now, and removing any one of them re-opens the leak:
  1. the cache is COMMITTED (see CACHE below), so a CI run starts warm rather than empty;
  2. entries carry `fetched` and are only re-bought once they pass REFRESH_DAYS;
  3. --limit defaults to a non-zero ceiling, so no single run can spend more than that many calls
     even if the cache is somehow lost.
Ratings move slowly; a 90-day refresh on 1,740 ids is ~19 calls/day of real churn.

Key: GOOGLE_PLACES_KEY from the environment or ./.env (never committed).

  python3 pull_place_ratings.py                 # refresh what is missing/stale, up to --limit
  python3 pull_place_ratings.py --limit 50      # smaller batch
  python3 pull_place_ratings.py --limit 0       # NO ceiling -- can cost 1,740 calls, use knowingly
"""
import argparse
import datetime
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
# COMMITTED, not gitignored scratch -- see the COST note in the module docstring. This file is what
# makes a CI run cost ~nothing instead of ~1,740 billed calls. It holds public business ratings only
# (name, rating, review count, open/closed) -- no personal data, nothing under the tape PII floor.
CACHE = os.path.join(SRC, "place_ratings_cache.json")
DETAILS_URL = "https://places.googleapis.com/v1/places/%s"
FIELDS = "displayName,rating,userRatingCount,businessStatus"
REFRESH_DAYS = 90        # re-buy an id only once it is this stale
DEFAULT_LIMIT = 300      # hard per-run ceiling; --limit 0 removes it deliberately
LEGACY_CACHE = os.path.join(SRC, ".place_ratings_cache.json")   # pre-2026-08-12 gitignored path


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


def _is_stale(entry, now, refresh_days):
    """True if this cached id is worth re-buying.

    An entry with no `fetched` stamp predates the committed cache and is treated as CURRENT, not
    stale -- the whole point of adopting the old cache is to avoid paying for those 1,740 ids
    again. It gets a stamp on its first write and ages normally from there.
    An `error` entry retries, because a transient 500 should not poison an id forever."""
    if not isinstance(entry, dict):
        return True
    if entry.get("error"):
        return True
    stamp = entry.get("fetched")
    if not stamp:
        return False
    try:
        when = datetime.datetime.strptime(stamp, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return False
    return (now - when).days >= refresh_days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help="max place_ids to fetch this run (default %d; 0 = NO ceiling, up to 1,740 "
                         "billed calls)" % DEFAULT_LIMIT)
    ap.add_argument("--refresh-days", type=int, default=REFRESH_DAYS,
                    help="re-fetch a cached id once it is this many days old (default %d)" % REFRESH_DAYS)
    ap.add_argument("--sleep", type=float, default=0.12, help="seconds between calls")
    args = ap.parse_args()

    key = _load_key()
    scout = _load_json(SCOUT, [])
    cache = _load_json(CACHE, {})
    # One-time adoption of the old gitignored cache, so the move to a committed path does not
    # itself trigger a full 1,740-call re-buy on whichever machine still has the old file.
    if not cache:
        legacy = _load_json(LEGACY_CACHE, {})
        if legacy:
            cache = legacy
            print("adopted %d entries from the legacy gitignored cache" % len(legacy))

    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.strftime("%Y-%m-%d")
    missing = [r for r in scout if r.get("place_id") and r["place_id"] not in cache]
    stale = [r for r in scout if r.get("place_id") and r["place_id"] in cache
             and _is_stale(cache[r["place_id"]], now, args.refresh_days)]
    todo = missing + stale                    # never-seen ids first, then the oldest work
    capped = len(todo)
    if args.limit:
        todo = todo[:args.limit]
    print("scout=%d cached=%d missing=%d stale=%d to-fetch=%d%s"
          % (len(scout), len(cache), len(missing), len(stale), len(todo),
             (" (capped from %d by --limit %d)" % (capped, args.limit))
             if capped > len(todo) else ""))
    if capped > len(todo):
        # Say what was deferred rather than letting a silent cap read as "fully refreshed".
        print("NOTE: %d id(s) deferred to a later run by the cost ceiling." % (capped - len(todo)))

    ok = err = 0
    for i, r in enumerate(todo, 1):
        pid = r["place_id"]
        try:
            d = _fetch(pid, key)
            cache[pid] = {"rating": d.get("rating"), "n": d.get("userRatingCount"),
                          "name": (d.get("displayName") or {}).get("text"),
                          "status": d.get("businessStatus"), "fetched": today}
            ok += 1
        except Exception as e:  # noqa: BLE001 — one bad id must not abort the run
            cache[pid] = {"error": str(e)[:120], "fetched": today}
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
