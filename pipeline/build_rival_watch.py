#!/usr/bin/env python3
"""
build_rival_watch.py — give the Competition tab (#acq) a TIME dimension: what changed in the
rival field since last time
============================================================================================
Every rival layer on #acq today (rival_pulse.json, rival_ads.json, search_demand.json) is a
point-in-time read: promos live right now, ads live right now, search share right now. None of
them answer "what's new since I last looked". This file is that diff, built ONLY from real dated
fields already sitting in those layers — it never fabricates a "since last time" by comparing a
file to itself with wall-clock time, and it never invents a prior vintage that was not actually
recorded.

WHAT IS MEASURED, WHAT IS ESTIMATED, AND WHAT THIS DELIBERATELY DOES NOT CLAIM
-------------------------------------------------------------------------------
  MEASURED   promos.new — rival_pulse.json's promo items each carry a real `first_seen` date
             (set by pipeline/pull_rival_promos.py the first time that URL was seen). A promo is
             "new" when first_seen equals meta.promos_pulled_at, the newest promo-pull date IN
             THE DATA. As of this build there is exactly ONE recorded promo pull
             (2026-07-19) — every promo's first_seen equals that date, so this run's "new" list
             is the FULL baseline, not yet a week-over-week delta. Said plainly in meta so it is
             never read as "22 promos appeared this week".
  ABSENT     promos.disappeared — pull_rival_promos.py's own staging file
             (source-data/rival_promos.json) tracks last_seen per item, but
             build_rival_pulse.py's projection into platform/data/rival_pulse.json drops that
             field before it reaches this script's declared inputs. Since a promo can only be
             flagged "disappeared" by comparing its last_seen to the newest pull date, and that
             field is not present in the input this script is allowed to read, the section is
             emitted EMPTY with the reason recorded — not silently, not estimated from something
             else.
  MEASURED   ads.appeared — rival_ads.json's n_new_30d per brand is a real count of ad creatives
             whose own first_shown date falls within meta.new_window_days of meta.pulled. That is
             a genuine dated measurement even from a single pull (first_shown is per-creative and
             already in the data); it is not a delta between two pulls.
  ABSENT     ads.disappeared — rival_ads.json's brand rows are aggregates (cadence-by-month,
             live/new counts); there is no per-creative last_shown, so a creative going dark
             cannot be identified. The one candidate that COULD carry this — feed_history.json's
             `rival_ads_live` series, a dated total-live-creatives count — currently holds a
             single observation (n=1, 2026-07-30). A "disappeared" read needs at least two points
             to fall from; with one, the honest output is empty, not a manufactured drop from 0.
  EXCLUDED   search_demand.json in full. Its per-province `sos` (share-of-search) block is a
             single Google Trends snapshot (meta.pulled_at_utc: one timestamp, no prior vintage
             recorded anywhere this script is allowed to read) — the file's own `national_ts` is
             a national query-volume series, not a per-brand share-of-search series, so it cannot
             stand in. Emitting a brand movement number here would mean inventing a "before" that
             was never measured. Nothing is emitted for it beyond the meta note explaining why.

  in : platform/data/rival_pulse.json     rival promos (first_seen per item) + app sentiment
       platform/data/rival_ads.json       Google Ads Transparency per-brand ad aggregates
       platform/data/search_demand.json   brand share-of-search per province (single snapshot)
       source-data/feed_history.json      dated accumulator series, incl. rival_ads_live
  out: platform/data/rival_watch.json

Usage:
  python3 build_rival_watch.py
  python3 build_rival_watch.py --check
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DATA = os.path.join(ROOT, "platform", "data")
SRC = os.path.join(ROOT, "source-data")
IN_PULSE = os.path.join(DATA, "rival_pulse.json")
IN_ADS = os.path.join(DATA, "rival_ads.json")
IN_SEARCH = os.path.join(DATA, "search_demand.json")
IN_FEED_HISTORY = os.path.join(SRC, "feed_history.json")
OUT = os.path.join(DATA, "rival_watch.json")

RC_ABSENT = 3
RIVAL_ADS_LIVE_SERIES = "rival_ads_live"


def _load(p):
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _s(v):
    """None-safe string coercion for sort keys, so every list has an explicit total order."""
    return v if isinstance(v, str) else ""


def build_promos(pulse):
    """NEW promos (first_seen == the newest recorded promo-pull date). DISAPPEARED cannot be
    computed: rival_pulse.json's promo items do not carry last_seen (see module docstring)."""
    section = {
        "as_of": None,
        "label": None,
        "new": [],
        "disappeared": [],
        "n_new": 0,
        "n_disappeared": 0,
        "note": None,
    }
    if pulse is None:
        section["note"] = "platform/data/rival_pulse.json is absent — no promo layer to watch."
        return section, None

    promos = pulse.get("promos") or []
    pulled = pulse.get("meta", {}).get("promos_pulled_at")
    has_last_seen = any("last_seen" in p for p in promos)

    new_items = []
    for p in promos:
        if pulled is not None and p.get("first_seen") == pulled:
            new_items.append({
                "brand": p.get("brand"),
                "kind": p.get("kind"),
                "title": p.get("title"),
                "date": p.get("date"),
                "url": p.get("url"),
                "first_seen": p.get("first_seen"),
                "product": (p.get("cls") or {}).get("product"),
                "promo_type": (p.get("cls") or {}).get("promo_type"),
            })
    # explicit total order: brand, then first_seen, then own date, then title, then url
    new_items.sort(key=lambda p: (_s(p["brand"]), _s(p["first_seen"]), _s(p["date"]),
                                   _s(p["title"]), _s(p["url"])))

    disappeared_items = []
    if has_last_seen and pulled is not None:
        for p in promos:
            ls = p.get("last_seen")
            if ls is not None and ls < pulled:
                disappeared_items.append({
                    "brand": p.get("brand"), "kind": p.get("kind"), "title": p.get("title"),
                    "url": p.get("url"), "last_seen": ls,
                })
        disappeared_items.sort(key=lambda p: (_s(p["brand"]), _s(p["last_seen"]),
                                               _s(p["title"]), _s(p["url"])))

    n_pulls_note = ("this is the only promo pull recorded so far, so every item's first_seen "
                     "equals the pull date — 'new' here is the baseline list, not yet a "
                     "week-over-week arrival; it will start showing genuine arrivals from the "
                     "next pull onward."
                     if pulled is not None and all(p.get("first_seen") == pulled for p in promos)
                     else "first_seen values span more than one pull; 'new' reflects arrivals "
                          "since the previous pull.")
    last_seen_note = ("" if has_last_seen else
                       " 'disappeared' is empty because rival_pulse.json's promo items do not "
                       "carry last_seen — pipeline/build_rival_pulse.py does not project that "
                       "field from source-data/rival_promos.json through to this input, so a "
                       "promo going quiet cannot be detected from the input this script reads.")

    section["as_of"] = pulled
    section["label"] = "MEASURED — dated by each promo's own first_seen (set by pull_rival_promos.py)."
    section["new"] = new_items
    section["disappeared"] = disappeared_items
    section["n_new"] = len(new_items)
    section["n_disappeared"] = len(disappeared_items)
    section["note"] = n_pulls_note + last_seen_note
    return section, pulled


def build_ads(ads, feed_history):
    """Ads that APPEARED: brands' n_new_30d, a genuine dated read (first_shown within
    new_window_days of the pull) even from a single pull. Ads that DISAPPEARED: not computable —
    no per-creative last_shown, and feed_history's rival_ads_live total-live series (the one
    candidate proxy) has only one recorded observation so far."""
    section = {
        "as_of": None,
        "label": None,
        "appeared": [],
        "disappeared": [],
        "n_appeared_brands": 0,
        "n_disappeared_brands": 0,
        "note": None,
        "live_total_series": None,
    }
    if ads is None:
        section["note"] = "platform/data/rival_ads.json is absent — no ad layer to watch."
        return section, None

    meta = ads.get("meta") or {}
    pulled = meta.get("pulled")
    window_days = meta.get("new_window_days")

    appeared = []
    for b in ads.get("brands") or []:
        n_new = b.get("n_new_30d") or 0
        if n_new > 0:
            appeared.append({
                "brand": b.get("brand"), "key": b.get("key"), "n_new_30d": n_new,
                "n_live": b.get("n_live"), "live_pct": b.get("live_pct"),
                "share_of_volume_pct": b.get("share_of_volume_pct"),
            })
    appeared.sort(key=lambda b: (-(b["n_new_30d"] or 0), _s(b["key"])))

    live_series = None
    live_note = ("feed_history.json carries no rival_ads_live series — a total-live-creatives "
                 "delta is not available.")
    if feed_history is not None:
        s = (feed_history.get("series") or {}).get(RIVAL_ADS_LIVE_SERIES)
        if s:
            n = s.get("n") or len(s.get("dates") or [])
            live_series = {
                "n_observations": n,
                "first_seen": s.get("first_seen"),
                "latest_date": (s.get("dates") or [None])[-1],
                "latest_value": (s.get("values") or [None])[-1],
            }
            if n >= 2:
                dates = s.get("dates") or []
                values = s.get("values") or []
                live_series["delta_vs_prior_pull"] = round(values[-1] - values[-2], 4)
                live_series["prior_date"] = dates[-2]
                live_note = None
            else:
                live_note = ("feed_history.json's rival_ads_live series has only %d "
                              "observation(s) (first_seen %s) — a delta needs at least two "
                              "pulls; none is computed here rather than diffed against an "
                              "invented zero." % (n, s.get("first_seen")))

    disappeared_note = ("ads.disappeared is empty: rival_ads.json's brand rows are monthly "
                         "aggregates with no per-creative last_shown, so a specific creative "
                         "going dark cannot be identified from this input. " + (live_note or ""))

    section["as_of"] = pulled
    section["label"] = ("MEASURED — n_new_30d is Google Ads Transparency's own per-creative "
                         "first_shown date, counted within %s days of the pull date."
                         % window_days if window_days is not None else "MEASURED")
    section["appeared"] = appeared
    section["disappeared"] = []
    section["n_appeared_brands"] = len(appeared)
    section["n_disappeared_brands"] = 0
    section["note"] = disappeared_note.strip()
    section["live_total_series"] = live_series
    return section, pulled


def build_search_demand(search):
    section = {
        "as_of": None,
        "label": None,
        "movement": [],
        "n_brands_moved": 0,
        "note": None,
    }
    if search is None:
        section["note"] = ("platform/data/search_demand.json is absent — no share-of-search "
                            "layer to watch.")
        return section

    pulled = (search.get("meta") or {}).get("pulled_at_utc")
    section["as_of"] = pulled
    section["note"] = (
        "EXCLUDED: search_demand.json's per-province brand share-of-search (`sos`) is a single "
        "Google Trends snapshot (pulled_at_utc %s) with no prior vintage recorded anywhere this "
        "script reads. Its own national_ts field is a national query-VOLUME series, not a "
        "per-brand share-of-search series, so it cannot substitute. Emitting a movement number "
        "here would mean inventing a 'before' that was never measured, so nothing is emitted." % pulled
    )
    return section


def build():
    pulse = _load(IN_PULSE)
    ads = _load(IN_ADS)
    search = _load(IN_SEARCH)
    feed_history = _load(IN_FEED_HISTORY)

    # The only two inputs that can ever populate a real section are rival_pulse (promos) and
    # rival_ads (ads). If BOTH are absent there is nothing this file can honestly say, so this
    # is the "required input absent" case that must SKIP, not emit an all-empty file.
    if pulse is None and ads is None:
        return None

    promos_section, promos_date = build_promos(pulse)
    ads_section, ads_date = build_ads(ads, feed_history)
    search_section = build_search_demand(search)

    dates = [d for d in (promos_date, ads_date) if d]
    newest_observation_date = max(dates) if dates else None

    inputs_meta = {
        "rival_pulse.json": {
            "usable": pulse is not None,
            "reason": ("promos carry first_seen (usable for NEW); no last_seen (DISAPPEARED "
                       "not computable)") if pulse is not None else "file absent",
        },
        "rival_ads.json": {
            "usable": ads is not None,
            "reason": ("per-brand n_new_30d is a genuine dated count (usable for APPEARED); no "
                       "per-creative last_shown (DISAPPEARED not computable)")
                      if ads is not None else "file absent",
        },
        "search_demand.json": {
            "usable": False,
            "reason": "single Google Trends snapshot — no prior vintage exists to diff against"
                      if search is not None else "file absent",
        },
        "source-data/feed_history.json": {
            "usable": bool(feed_history and (feed_history.get("series") or {})
                           .get(RIVAL_ADS_LIVE_SERIES, {}).get("n", 0) >= 2),
            "reason": (
                "rival_ads_live series has only 1 observation so far — needs 2+ for a delta"
                if feed_history and (feed_history.get("series") or {}).get(RIVAL_ADS_LIVE_SERIES)
                else "no rival_ads_live series in this file"
            ) if feed_history is not None else "file absent",
        },
    }

    return {
        "meta": {
            "title": "Rival watch — what changed in the rival field since last time (obj #2)",
            "generated_by": "pipeline/build_rival_watch.py",
            "label": (
                "MIXED, labelled per section. promos.new and ads.appeared are MEASURED from "
                "real per-item/per-creative first_seen/first_shown dates already in the source "
                "files. promos.disappeared, ads.disappeared and search_demand movement are all "
                "empty by design — none of this pipeline's inputs currently carry the second "
                "data point (last_seen, per-creative last_shown, or a prior share-of-search "
                "vintage) that an honest 'disappeared' or 'movement' figure requires."),
            "how_to_read": (
                "This is a diff layer, not a new census: it never re-counts what rival_pulse.json "
                "or rival_ads.json already show as 'live now', it only surfaces what is NEW or "
                "GONE relative to a dated field already in those files. An empty section here "
                "means no usable time signal existed for that category at this build, not that "
                "nothing happened."),
            "does_not_claim": [
                "does not claim any promo or ad 'disappeared' without a measured last_seen / "
                "last_shown date to prove it stopped running",
                "does not claim a share-of-search trend from a single Google Trends snapshot",
                "does not treat the very first promo pull's full list as a week-over-week arrival",
                "never uses wall-clock time — every date in this file is copied from a field the "
                "source data itself stamped",
            ],
            "newest_observation_date": newest_observation_date,
            "inputs": inputs_meta,
        },
        "promos": promos_section,
        "ads": ads_section,
        "search_demand": search_section,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare (exit 3 / SKIP when both rival_pulse.json and "
                         "rival_ads.json are absent)")
    args = ap.parse_args()

    data = build()
    if data is None:
        msg = ("both platform/data/rival_pulse.json and platform/data/rival_ads.json are "
               "absent — rival_watch not buildable here")
        print(("CHECK SKIP: " if args.check else "SKIP: ") + msg, file=sys.stderr)
        sys.exit(RC_ABSENT)

    text = dumps(data)
    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as fh:
            if fh.read() == text:
                print("CHECK OK: %s reproduces byte-for-byte (%d new promos, %d disappeared "
                      "promos, %d brands with new ads, %d brands with disappeared ads)"
                      % (OUT, data["promos"]["n_new"], data["promos"]["n_disappeared"],
                         data["ads"]["n_appeared_brands"], data["ads"]["n_disappeared_brands"]))
                sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("wrote %s (%d new promos, %d disappeared promos, %d brands with new ads, "
          "%d brands with disappeared ads, search_demand: %s)"
          % (OUT, data["promos"]["n_new"], data["promos"]["n_disappeared"],
             data["ads"]["n_appeared_brands"], data["ads"]["n_disappeared_brands"],
             "excluded (single snapshot)"))


if __name__ == "__main__":
    main()
