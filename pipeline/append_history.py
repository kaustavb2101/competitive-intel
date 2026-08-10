#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""append_history.py — turn the overwrite-on-pull feeds into real time series.

THE PROBLEM. Most live feeds publish only "now". Bangchak returns today's pump price, ThaiWater
returns the current gauge readings, the Ads Transparency Center returns what is running today.
Each pull OVERWRITES the last, so the platform could show a current value and never a direction.
The live board makes this explicit — 16 of 20 feeds carry no history — and this is the fix.

  in : the feed files themselves (source-data/ or platform/data/, per the registry below)
  out: source-data/feed_history.json   — one dated row per feed per day, accumulating

  python3 append_history.py                    # append today's values (idempotent)
  python3 append_history.py --from-git         # BACKFILL from git history, then append
  python3 append_history.py --show             # print what is on file, change nothing

IDEMPOTENT BY THE FEED'S OWN STAMP, NOT BY WALL CLOCK. A row is keyed on the date the SOURCE says
it is current for (meta.pulled), so running this twice in a day is a no-op, re-running after a
failed workflow is safe, and a feed that did not refresh does not get a duplicate row at a new
date. This is the same discipline as the loan tape's mob_anchor: never let the clock on the machine
decide what a data point is dated.

THE BACKFILL IS THE REASON THIS SHIPS WITH REAL LINES. Every daily pull has been committed since
2026-07-05, so the past values were never actually lost — they were in git, just not queryable
from a browser. --from-git walks `git log` for each registered path and replays every committed
vintage through the same extractors used for a live append. That is 12 real diesel observations and
10 ThaiWater vintages on day one, instead of a chart that starts empty and is useless for a month.
Re-running it is safe: same stamp, same row, no duplicate.

HONESTY. `meta.first_seen` per series records where the history actually begins, so a four-point
line is never mistaken for a long record. Nothing is interpolated and no gap is filled: if a pull
was missed, the series simply has no row for that day, and the chart draws straight between the
observations that exist rather than inventing the ones that do not.

NOT IN THE DETERMINISM GATE. This script WRITES source-data from other files and (with --from-git)
shells out to git, so it is a pull-side action like the pulls themselves. The deterministic,
--check-gated half is build_feed_history.py, which projects this file into platform/data.
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "feed_history.json")

MAX_POINTS = 800        # ~2 years of daily rows; oldest are dropped first


def dig(o, path):
    cur = o
    for seg in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(seg)
    return cur


def _sum(doc, group, field):
    """Total a per-province field. ThaiWater publishes per-province station aggregates; the national
    number we want is their sum, and a province that dropped out of the pull contributes 0 rather
    than breaking the row."""
    d = (doc or {}).get(group) or {}
    if not isinstance(d, dict):
        return None
    tot = 0
    for p in d.values():
        v = (p or {}).get(field)
        if isinstance(v, (int, float)):
            tot += v
    return tot


def _max(doc, group, field):
    d = (doc or {}).get(group) or {}
    if not isinstance(d, dict):
        return None
    vals = [(p or {}).get(field) for p in d.values()]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return max(vals) if vals else None


def _peer_field(doc, symbol, field):
    """One SET-listed peer's field by ticker symbol, or None when that peer is absent from the pull."""
    for p in (doc or {}).get("peers") or []:
        if isinstance(p, dict) and p.get("symbol") == symbol:
            v = p.get(field)
            return v if isinstance(v, (int, float)) else None
    return None


def _peer_mcap_bn(doc, symbol):
    """set_peers.json reports marketCap in raw THB; the board reads peers in billions (peer_scoreboard.json
    already does this same /1e9 conversion), so match that unit here rather than publish a raw-THB series."""
    v = _peer_field(doc, symbol, "marketCap")
    return v / 1e9 if isinstance(v, (int, float)) else None


def _brand_share_pct(doc, brand):
    """National share-of-search for one brand: its Trends value summed over every province, divided by
    the same sum for all five brands. Brand values share one Trends payload axis (per pull_google_trends.py),
    so this cross-brand ratio is meaningful even though the underlying numbers are a relative 0-100 index,
    not query volume. None when the payload is empty or sums to zero (no share is fabricated)."""
    total, target, seen = 0.0, 0.0, False
    for b, provs in ((doc or {}).get("brands") or {}).items():
        if not isinstance(provs, dict):
            continue
        for v in provs.values():
            if isinstance(v, (int, float)):
                total += v
                seen = True
                if b == brand:
                    target += v
    return (target / total * 100.0) if seen and total > 0 else None


def _app_score(doc, key):
    v = dig(doc, "apps.%s.stats.score" % key)
    return v if isinstance(v, (int, float)) else None


def _app_1star_pct(doc, key):
    """Google Play's histogram is [1-star, 2-star, 3-star, 4-star, 5-star] counts; share of the worst
    bucket is the sentiment-deterioration signal, not the average score alone."""
    hist = dig(doc, "apps.%s.stats.histogram" % key)
    if not isinstance(hist, list) or len(hist) != 5:
        return None
    vals = [v for v in hist if isinstance(v, (int, float))]
    if len(vals) != 5:
        return None
    total = sum(vals)
    return (hist[0] / total * 100.0) if total > 0 else None


def _promo_live_count(doc, brand):
    """A promo/news item's last_seen is bumped forward every time a re-pull still finds it on the rival's
    site; counting items whose last_seen equals THIS pull's own stamp is 'still live now', the same
    still-running idea as rival_ads_live's n_live, just for the rival-site promo/news feed instead of the
    Ads Transparency Center."""
    pulled = dig(doc, "meta.pulled_at")
    if not isinstance(pulled, str):
        return None
    items = (doc or {}).get("items") or []
    return sum(1 for it in items if isinstance(it, dict)
               and it.get("brand") == brand and it.get("last_seen") == pulled)


def _social_corpus_docs(doc):
    """Total voice-of-customer demand documents behind social_themes.json — the sum of every
    app-store review, YouTube comment and Pantip thread in the corpus the #acq themes board renders
    (meta.demand_docs, which equals the sum of meta.demand_by_source[*].n). This is the frozen-value
    canary for the aggregate social-listening feed. Reviews and comments ACCUMULATE across pulls (the
    Play/Apple/YouTube stores dedup-and-append, Pantip adds threads), so this count ticks UP on every
    genuine rebuild — verified 11,137 → 11,146 → 11,149 → 11,154 across the 2026-08-07 → 08-09
    vintages. It goes flat ONLY if every upstream social source stops delivering new documents — the
    exact expired-key / dead-puller shape TEST B exists for, on the one #acq-rendered feed whose own
    reads had no frozen canary (TEST-A stale-stamp coverage already exists via live_board's
    social_themes row, but TEST A is blind to a refreshed stamp over a frozen corpus). Falls back to
    summing demand_by_source when demand_docs is absent in an older vintage, so the --from-git
    backfill reads every committed shape rather than dropping the ones that predate the scalar."""
    m = (doc or {}).get("meta") or {}
    v = m.get("demand_docs")
    if isinstance(v, (int, float)):
        return v
    dbs = m.get("demand_by_source")
    if isinstance(dbs, dict):
        tot, seen = 0, False
        for src in dbs.values():
            n = (src or {}).get("n") if isinstance(src, dict) else None
            if isinstance(n, (int, float)):
                tot += n
                seen = True
        return tot if seen else None
    return None


def _youtube_views_total(doc):
    """Total lifetime view count across every tracked rival brand channel (13 in the current pull).
    This is the frozen-value canary for the YouTube feed. Views accrue continuously on any live
    channel, so this large integer ticks UP on every genuine pull (verified: 915.9M → 920.0M across
    the 2026-07-30 → 2026-08-09 pulls). It goes flat ONLY if the YouTube Data API stops returning
    fresh channel statistics — the exact expired-key failure mode this whole history mechanism was
    built to catch (youtube_comments.json sat frozen for 9 days behind a dead key while the puller
    exited 0 daily). TEST-A stale-stamp coverage already exists via live_board; this closes the
    TEST-B (frozen value) blind spot the sibling ad/promo/app feeds all have and this one lacked."""
    chans = (doc or {}).get("channels")
    if not isinstance(chans, list) or not chans:
        return None
    tot = 0
    seen = False
    for c in chans:
        v = (c or {}).get("views_total") if isinstance(c, dict) else None
        if isinstance(v, (int, float)):
            tot += v
            seen = True
    return tot if seen else None


# ---------------------------------------------------------------- registry
# `path` is the file to read, relative to the repo root — this is also the path walked by --from-git,
# so a feed can only be backfilled if its history was actually committed under that name.
# `stamp` lists the meta fields that could date the observation, MOST AUTHORITATIVE FIRST. Prefer the
# source's own observation time over our fetch time: ThaiWater's nightly pull runs at 22:40 UTC, which
# is already the next morning in Bangkok, so `pulled` files those readings a day EARLY while
# `observed_to` is what the gauges actually say. `pick` turns a loaded document into a number.
REGISTRY = [
    dict(key="fuel_diesel", path="source-data/fuel_prices.json", stamp=("pulled",),
         label="Diesel · retail pump", unit="฿/L", cadence="daily",
         source="Bangchak retail oil-price API",
         pick=lambda d: dig(d, "headline.diesel")),
    dict(key="fuel_gasohol95", path="source-data/fuel_prices.json", stamp=("pulled",),
         label="Gasohol 95 · retail pump", unit="฿/L", cadence="daily",
         source="Bangchak retail oil-price API",
         pick=lambda d: dig(d, "headline.gasohol95")),
    dict(key="flood_high", path="platform/data/thaiwater_flood.json", stamp=("observed_to", "pulled"),
         label="River stations above their high mark", unit="stations", cadence="daily",
         source="ThaiWater live river/reservoir telemetry",
         pick=lambda d: _sum(d, "provinces", "n_high")),
    dict(key="rain_max_mm", path="platform/data/thaiwater_rain.json", stamp=("observed_to", "pulled"),
         label="Heaviest 24h rainfall, any gauge", unit="mm", cadence="daily",
         source="ThaiWater rain-gauge telemetry",
         pick=lambda d: _max(d, "provinces", "max_mm")),
    dict(key="rain_heavy_pct", path="platform/data/thaiwater_rain.json", stamp=("observed_to", "pulled"),
         label="Provinces with heavy rain somewhere", unit="provinces", cadence="daily",
         source="ThaiWater rain-gauge telemetry",
         pick=lambda d: sum(1 for p in (d.get("provinces") or {}).values()
                            if isinstance((p or {}).get("pct_heavy"), (int, float)) and p["pct_heavy"] > 0)),
    # Brand COUNT would be a flat line (the same five advertise every week); live CREATIVES is the
    # number that actually moves when a rival opens or closes a campaign.
    dict(key="rival_ads_live", path="platform/data/rival_ads.json", stamp=("pulled",),
         label="Rival ad creatives running now", unit="creatives", cadence="weekly",
         source="Google Ads Transparency Center",
         pick=lambda d: sum(b.get("n_live") or 0 for b in (d.get("brands") or [])) or None),

    # ---- SET-listed peers — genuine daily market data, currently pure snapshot ----------------
    # price_asof is the source's own vintage stamp (a price DATE, not a pull timestamp); using it
    # keeps two same-day re-pulls from creating two rows even though set_peers.json has been
    # committed twice for the same 2026-07-17 price date.
    dict(key="set_mtc_mcap", path="source-data/set_peers.json", stamp=("price_asof",),
         label="MTC · market cap", unit="฿bn", cadence="daily",
         source="Stock Exchange of Thailand (set.or.th)",
         pick=lambda d: _peer_mcap_bn(d, "MTC")),
    dict(key="set_mtc_pbv", path="source-data/set_peers.json", stamp=("price_asof",),
         label="MTC · price/book", unit="x", cadence="daily",
         source="Stock Exchange of Thailand (set.or.th)",
         pick=lambda d: _peer_field(d, "MTC", "pbRatio")),
    dict(key="set_tidlor_mcap", path="source-data/set_peers.json", stamp=("price_asof",),
         label="TIDLOR · market cap", unit="฿bn", cadence="daily",
         source="Stock Exchange of Thailand (set.or.th)",
         pick=lambda d: _peer_mcap_bn(d, "TIDLOR")),
    dict(key="set_tidlor_pbv", path="source-data/set_peers.json", stamp=("price_asof",),
         label="TIDLOR · price/book", unit="x", cadence="daily",
         source="Stock Exchange of Thailand (set.or.th)",
         pick=lambda d: _peer_field(d, "TIDLOR", "pbRatio")),
    dict(key="set_sawad_mcap", path="source-data/set_peers.json", stamp=("price_asof",),
         label="SAWAD · market cap", unit="฿bn", cadence="daily",
         source="Stock Exchange of Thailand (set.or.th)",
         pick=lambda d: _peer_mcap_bn(d, "SAWAD")),
    dict(key="set_sawad_pbv", path="source-data/set_peers.json", stamp=("price_asof",),
         label="SAWAD · price/book", unit="x", cadence="daily",
         source="Stock Exchange of Thailand (set.or.th)",
         pick=lambda d: _peer_field(d, "SAWAD", "pbRatio")),

    # ---- search demand — AutoX's own share-of-search vs the same four rivals ------------------
    dict(key="search_share_autox", path="source-data/google_trends.json", stamp=("pulled_at_utc",),
         label="AutoX share of brand search (national)", unit="%", cadence="weekly",
         source="Google Trends (geo=TH) — AutoX vs rival brand terms",
         pick=lambda d: _brand_share_pct(d, "AutoX")),

    # ---- app-store sentiment — score + 1-star share, AutoX's own app and its three closest ----
    # SET-listed rivals. Google Play overwrites the histogram on every pull; this is the fix.
    dict(key="app_autox_score", path="source-data/app_reviews.json", stamp=("pulled_at",),
         label="AutoX app (Ngern Chaiyo) - Play Store rating", unit="stars", cadence="weekly",
         source="Google Play (th.co.autox.chaiyo)",
         pick=lambda d: _app_score(d, "AUTOX")),
    dict(key="app_autox_1star_pct", path="source-data/app_reviews.json", stamp=("pulled_at",),
         label="AutoX app · 1-star share", unit="%", cadence="weekly",
         source="Google Play (th.co.autox.chaiyo)",
         pick=lambda d: _app_1star_pct(d, "AUTOX")),
    dict(key="app_tidlor_score", path="source-data/app_reviews.json", stamp=("pulled_at",),
         label="Tidlor app · Play Store rating", unit="stars", cadence="weekly",
         source="Google Play (com.ntl.cxm_mobile)",
         pick=lambda d: _app_score(d, "TIDLOR")),
    dict(key="app_tidlor_1star_pct", path="source-data/app_reviews.json", stamp=("pulled_at",),
         label="Tidlor app · 1-star share", unit="%", cadence="weekly",
         source="Google Play (com.ntl.cxm_mobile)",
         pick=lambda d: _app_1star_pct(d, "TIDLOR")),
    dict(key="app_mtc_score", path="source-data/app_reviews.json", stamp=("pulled_at",),
         label="MTC app · Play Store rating", unit="stars", cadence="weekly",
         source="Google Play (co.th.muangthaileasing.mtls)",
         pick=lambda d: _app_score(d, "MTC")),
    dict(key="app_mtc_1star_pct", path="source-data/app_reviews.json", stamp=("pulled_at",),
         label="MTC app · 1-star share", unit="%", cadence="weekly",
         source="Google Play (co.th.muangthaileasing.mtls)",
         pick=lambda d: _app_1star_pct(d, "MTC")),
    dict(key="app_sawad_score", path="source-data/app_reviews.json", stamp=("pulled_at",),
         label="SAWAD app · Play Store rating", unit="stars", cadence="weekly",
         source="Google Play (com.srisawad.mobileApplications)",
         pick=lambda d: _app_score(d, "SAWAD")),
    dict(key="app_sawad_1star_pct", path="source-data/app_reviews.json", stamp=("pulled_at",),
         label="SAWAD app · 1-star share", unit="%", cadence="weekly",
         source="Google Play (com.srisawad.mobileApplications)",
         pick=lambda d: _app_1star_pct(d, "SAWAD")),

    # ---- NABC farm-gate — the two crops with the longest, most consistent daily read -----------
    # (all five crop_yoy categories are consistently present across every committed vintage; rice
    # and rubber are picked as the two headline reads. latest_date tracks 'pulled' within a day or
    # two across every vintage checked, the same ThaiWater-style lag already handled elsewhere.)
    # Registry `label` strings are printed to a cp1252 console by --show, so these stay
    # transliterated (Hom Mali rice / RSS3 rubber) even though the dict keys they dig for are the
    # Thai category names NABC actually publishes (that lookup never touches the console).
    dict(key="nabc_rice_price", path="source-data/nabc_prices.json", stamp=("pulled",),
         label="Rice (Hom Mali) - NABC farm-gate", unit="THB/tonne", cadence="daily",
         source="NABC Agricultural Data Service",
         pick=lambda d: dig(d, "categories.ข้าวหอมมะลิ.price")),
    dict(key="nabc_rubber_price", path="source-data/nabc_prices.json", stamp=("pulled",),
         label="Rubber (raw sheet) - NABC farm-gate", unit="THB/kg", cadence="daily",
         source="NABC Agricultural Data Service",
         pick=lambda d: dig(d, "categories.ยางพารา.price")),

    # ---- rival promo/news count — live items per brand on the rival's OWN site -----------------
    dict(key="rival_promo_live_mtc", path="source-data/rival_promos.json", stamp=("pulled_at",),
         label="MTC · live promo/news items", unit="items", cadence="weekly",
         source="muangthaicap.com (own-site pull)",
         pick=lambda d: _promo_live_count(d, "MTC")),
    dict(key="rival_promo_live_sawad", path="source-data/rival_promos.json", stamp=("pulled_at",),
         label="SAWAD · live promo/news items", unit="items", cadence="weekly",
         source="sawad.co.th (own-site pull)",
         pick=lambda d: _promo_live_count(d, "SAWAD")),
    dict(key="rival_promo_live_tidlor", path="source-data/rival_promos.json", stamp=("pulled_at",),
         label="TIDLOR · live promo/news items", unit="items", cadence="weekly",
         source="tidlor.com (own-site pull)",
         pick=lambda d: _promo_live_count(d, "TIDLOR")),

    # YouTube — the frozen-value canary for the rival brand-channel feed. Summed lifetime views
    # across all tracked channels; live pulls tick it up, an expired API key freezes it. `pulled`
    # is the only stamp this feed carries. Weekly cadence matches its ~10-day refresh so a run of
    # identical values across 4+ pulls (never legitimate for accruing view counts) trips TEST B.
    dict(key="rival_youtube_views", path="platform/data/rival_youtube.json", stamp=("pulled",),
         label="Rival YouTube brand channels · total views", unit="views", cadence="weekly",
         source="YouTube Data API v3 (official) — public brand-channel statistics",
         pick=_youtube_views_total),

    # ---- social-listening corpus — the aggregate voice-of-customer feed behind #acq --------------
    # social_themes.json's own reads (theme shares, per-brand demand) had no frozen-value canary;
    # total demand documents is the number that accumulates on every live rebuild and freezes only if
    # the whole social corpus goes dark. `as_of` is build_social_themes.py's newest-doc-in-data stamp
    # (never wall clock); weekly cadence matches the data-social-listening.yml Tuesday cron and the
    # live-board classification of this same feed.
    dict(key="social_corpus_docs", path="platform/data/social_themes.json", stamp=("as_of",),
         label="Social-listening corpus · total demand documents", unit="documents", cadence="weekly",
         source="app-store reviews + YouTube comments + Pantip threads (build_social_themes.py)",
         pick=_social_corpus_docs),
]


def load(obj_text):
    """Every JSON document in one blob of text, as a list.

    Normally that is a list of one. But a botched merge in July concatenated two nightly ThaiWater
    pulls into a single committed file, and a plain json.loads() rejects the whole thing — throwing
    away two perfectly good observations, one of which (2026-07-28) survives nowhere else. So parse
    document-by-document and keep what parses. Corrupt tail, readable head: keep the head."""
    dec = json.JSONDecoder()
    docs, i, n = [], 0, len(obj_text)
    while i < n:
        while i < n and obj_text[i].isspace():
            i += 1
        if i >= n:
            break
        try:
            doc, i = dec.raw_decode(obj_text, i)
        except ValueError:
            break
        docs.append(doc)
    return docs


def observe(spec, doc):
    """(date, value) for one feed from one loaded document, or None when either is missing.
    A feed with no stamp is SKIPPED rather than dated with today: an undated observation filed
    under today's date is a fabricated data point."""
    if not isinstance(doc, dict):
        return None
    meta = doc.get("meta") or {}
    stamp = next((meta[k] for k in spec["stamp"]
                  if isinstance(meta.get(k), str) and len(meta[k]) >= 10), None)
    if stamp is None:
        return None
    try:
        val = spec["pick"](doc)
    except Exception:
        return None
    if not isinstance(val, (int, float)):
        return None
    return stamp[:10], round(float(val), 4)


def read_store():
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as fh:
            return json.load(fh)
    return {"meta": {}, "series": {}}


def put(store, spec, date, value):
    """Insert one observation, keeping the series sorted by date and free of duplicates.
    Returns True when the store actually changed."""
    s = store["series"].setdefault(spec["key"], {
        "label": spec["label"], "unit": spec["unit"], "cadence": spec["cadence"],
        "source": spec["source"], "path": spec["path"], "dates": [], "values": [],
    })
    # keep the descriptive fields current if the registry was edited
    for k in ("label", "unit", "cadence", "source", "path"):
        s[k] = spec[k]
    if date in s["dates"]:
        i = s["dates"].index(date)
        if s["values"][i] == value:
            return False
        s["values"][i] = value          # same day re-pulled with a corrected number
        return True
    pairs = sorted(zip(s["dates"] + [date], s["values"] + [value]))
    if len(pairs) > MAX_POINTS:
        pairs = pairs[-MAX_POINTS:]
    s["dates"] = [d for d, _ in pairs]
    s["values"] = [v for _, v in pairs]
    return True


def git_vintages(path):
    """Every committed version of one file, oldest first. Returns [(sha, text)].

    Bytes in, explicit UTF-8 out — never subprocess(text=True). That decodes with the machine's
    locale, which on this Windows laptop is cp1252, and every one of these files carries Thai
    province names. The decode raises inside subprocess's own reader thread, so the call still
    returns success with empty output and the vintage is dropped WITHOUT an error — the failure
    mode is a silently short history, which is exactly the thing this script exists to prevent."""
    try:
        shas = subprocess.run(["git", "log", "--format=%H", "--", path],
                              cwd=ROOT, capture_output=True, check=True
                              ).stdout.decode("ascii").split()
    except Exception:
        return []
    out = []
    for sha in reversed(shas):
        try:
            raw = subprocess.run(["git", "show", "%s:%s" % (sha, path)],
                                 cwd=ROOT, capture_output=True, check=True).stdout
        except Exception:
            continue
        out.append((sha, raw.decode("utf-8", "replace")))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-git", action="store_true",
                    help="replay every committed vintage of each feed before appending today's")
    ap.add_argument("--show", action="store_true", help="print the store and exit")
    a = ap.parse_args()

    store = read_store()
    if a.show:
        for k, s in sorted(store.get("series", {}).items()):
            n = len(s.get("dates") or [])
            span = ("%s → %s" % (s["dates"][0], s["dates"][-1])) if n else "empty"
            print("  %-18s %3d pts  %-25s %s" % (k, n, span, s.get("label", "")))
        return 0

    changed = 0
    if a.from_git:
        # One git walk per distinct path, not per series — several series can share a file.
        by_path = {}
        for spec in REGISTRY:
            by_path.setdefault(spec["path"], []).append(spec)
        for path, specs in by_path.items():
            vintages = git_vintages(path)
            unreadable = 0
            for _sha, txt in vintages:
                docs = load(txt)
                if not docs:
                    unreadable += 1
                    continue
                for doc in docs:
                    for spec in specs:
                        obs = observe(spec, doc)
                        if obs and put(store, spec, *obs):
                            changed += 1
            # Say when a vintage could not be read. A silently short series is the failure this
            # whole script exists to prevent, so it must never be silent here either.
            print("  %-40s %d committed vintage(s)%s"
                  % (path, len(vintages),
                     "  [%d UNREADABLE — history for those dates is missing]" % unreadable
                     if unreadable else ""))

    # ...then today's working-tree state, which may be newer than anything committed.
    for spec in REGISTRY:
        p = os.path.join(ROOT, spec["path"])
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            for doc in load(fh.read()):
                obs = observe(spec, doc)
                if obs and put(store, spec, *obs):
                    changed += 1

    for key, s in store["series"].items():
        s["first_seen"] = s["dates"][0] if s["dates"] else None
        s["n"] = len(s["dates"])
    store["meta"] = {
        "title": "Accumulated history for the feeds whose API only publishes 'now'",
        "generated_by": "pipeline/append_history.py",
        "label": "MEASURED — each row is a value the source itself published, dated by the source's "
                 "own stamp (meta.pulled), never by this machine's clock.",
        "note": "Nothing is interpolated. A missed pull leaves a GAP, not a filled-in value, so a "
                "line drawn from this joins the observations that exist and invents none. "
                "meta.first_seen on each series says where the record actually begins — a short "
                "series is a short record, not a short trend.",
        "backfill": "Values before this file existed were recovered from git: every daily pull was "
                    "committed, so the history was never lost, only unqueryable from a browser.",
        "max_points": MAX_POINTS,
        "n_series": len(store["series"]),
        "n_points": sum(s["n"] for s in store["series"].values()),
    }
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(store, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print("feed_history.json — %d series, %d points (%d row(s) changed this run)"
          % (store["meta"]["n_series"], store["meta"]["n_points"], changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
