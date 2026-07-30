#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rival_youtube.py — the rivals' VIDEO marketing pulse (objective #2).

Turns `source-data/rival_youtube_raw.json` (pull_rival_youtube.py, official YouTube Data API)
into `platform/data/rival_youtube.json` for the Competition tab.

WHAT IT MEASURES, per operator — including our own เงินไชโย channel as the control:
  * REACH     — subscribers, lifetime views, median views per recent video
  * ACTIVITY  — uploads in the last 30 / 90 / 365 days, monthly cadence, days since last upload
  * ENGAGEMENT— likes + comments per 1,000 views on recent videos
  * MESSAGE   — what the video titles push, using the SAME Thai lexicon as the ad-copy read, so
                video messaging and paid-ad messaging are directly comparable (ESTIMATED)

HONEST COMPARISON LIMITS.
  * Subscriber counts are rounded by YouTube itself at scale (101,000 not 101,437) — treat them
    as bands, not exact counts. They are reported as published.
  * Only the newest N uploads per channel are pulled, so lifetime medians are computed over
    that recent window and labelled as such; `video_count` is the channel's true total.
  * CAR4CASH maps to Krungsri Auto's PARENT channel, which markets all auto finance rather than
    title loans alone. It carries `is_parent_channel` and must never be read as a like-for-like
    title-loan audience — the UI is required to mark it.

Deterministic: all windows anchor on the pull's own `meta.pulled` stamp, never the wall clock,
so a given input reproduces byte-for-byte. `--check` byte-compares; exits 3 (SKIP) when the
network pull has not been run, matching the other network-fed builders.

  python3 build_rival_youtube.py
  python3 build_rival_youtube.py --check
"""
import argparse
import collections
import datetime
import io
import json
import os
import sys

from build_google_ads import THEMES          # one lexicon for ad copy AND video titles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "source-data", "rival_youtube_raw.json")
OUT = os.path.join(ROOT, "platform", "data", "rival_youtube.json")

MONTHS = 24
TOP_VIDEOS = 8
OWN = "AUTOX"


def d(s):
    return datetime.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))


def months_back(anchor, n):
    y, m = int(anchor[0:4]), int(anchor[5:7])
    keys = []
    for _ in range(n):
        keys.append("%04d-%02d" % (y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(keys))


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) // 2


def pct(a, b):
    return round(100.0 * a / b, 1) if b else 0.0


def build():
    raw = json.load(io.open(IN, encoding="utf-8"))
    pulled = raw["meta"]["pulled"]
    anchor = d(pulled)
    cadence_keys = months_back(pulled, MONTHS)
    theme_label = {k: lbl for k, lbl, _ in THEMES}

    rows = []
    for key in sorted(raw.get("channels") or {}):
        c = raw["channels"][key]
        vids = [v for v in (c.get("videos") or []) if v.get("published")]
        vids.sort(key=lambda v: (v["published"], v["id"]), reverse=True)
        cad = collections.Counter()
        u30 = u90 = u365 = 0
        views, engage = [], []
        theme_n = collections.Counter()
        for v in vids:
            age = (anchor - d(v["published"])).days
            cad[v["published"][0:7]] += 1
            if age <= 30:
                u30 += 1
            if age <= 90:
                u90 += 1
            if age <= 365:
                u365 += 1
                if v.get("views"):
                    views.append(v["views"])
                    inter = (v.get("likes") or 0) + (v.get("comments") or 0)
                    engage.append(round(1000.0 * inter / v["views"], 2))
            title = v.get("title") or ""
            for tkey, _lbl, words in THEMES:
                if any(w in title for w in words):
                    theme_n[tkey] += 1
        last = vids[0]["published"] if vids else None
        top = sorted((v for v in vids if v.get("views")),
                     key=lambda v: (-v["views"], v["id"]))[:TOP_VIDEOS]
        rows.append({
            "key": key,
            "brand": c.get("name_en") or key,
            "name_th": c.get("name_th"),
            "tier": c.get("tier"),
            "is_us": key == OWN,
            "is_parent_channel": bool(c.get("is_parent_channel")),
            "channel_id": c.get("channel_id"),
            "channel_title": c.get("channel_title"),
            "channel_note": c.get("channel_note"),
            "started": c.get("started"),
            "subscribers": c.get("subscribers"),
            "views_total": c.get("views_total"),
            "video_count": c.get("video_count"),
            "n_sampled": len(vids),
            "uploads_30d": u30,
            "uploads_90d": u90,
            "uploads_365d": u365,
            "last_upload": last,
            "days_since_upload": (anchor - d(last)).days if last else None,
            "median_views_365d": median(views),
            "engagement_per_1k_365d": (round(sum(engage) / len(engage), 2) if engage else None),
            "cadence": [cad.get(k, 0) for k in cadence_keys],
            "themes": [{"key": k, "label": theme_label[k], "n": n, "pct": pct(n, len(vids))}
                       for k, n in sorted(theme_n.items(), key=lambda kv: (-kv[1], kv[0]))],
            "top_videos": [{"title": v.get("title"), "published": v.get("published"),
                            "views": v.get("views"), "id": v.get("id")} for v in top],
        })

    # share of voice over the operators that are actually comparable — the parent channel is
    # excluded from the denominator rather than silently inflating it.
    comparable = [r for r in rows if not r["is_parent_channel"]]
    subs_tot = sum(r["subscribers"] or 0 for r in comparable)
    up_tot = sum(r["uploads_365d"] or 0 for r in comparable)
    for r in rows:
        if r["is_parent_channel"]:
            r["share_of_subs_pct"] = None
            r["share_of_uploads_pct"] = None
        else:
            r["share_of_subs_pct"] = pct(r["subscribers"] or 0, subs_tot)
            r["share_of_uploads_pct"] = pct(r["uploads_365d"] or 0, up_tot)
    rows.sort(key=lambda r: -(r["subscribers"] or 0))

    return {
        "meta": {
            "source": "YouTube Data API v3 (official)",
            "provenance": "MEASURED — public channel statistics and public video metadata for "
                          "BRAND channels only. No commenters, no subscribers, no individuals.",
            "pulled": pulled,
            "cadence_months": cadence_keys,
            "theme_label": theme_label,
            "own_key": OWN,
            "no_channel_found": sorted((raw.get("meta") or {}).get("no_channel", [])),
            "parent_channels": sorted((raw.get("meta") or {}).get("parent_channels", [])),
            "limits": "Subscriber counts are rounded by YouTube at scale — read them as bands. "
                      "Medians and engagement are computed over the newest %d uploads per "
                      "channel (video_count is the channel's true total). Title themes are an "
                      "ESTIMATED keyword read, the same lexicon used for ad copy. A PARENT "
                      "channel (Krungsri Auto for Car4Cash) markets more than title loans and "
                      "is excluded from share-of-voice."
                      % (raw.get("meta") or {}).get("max_videos_per_channel", 200),
            "n_channels": len(rows),
            "n_videos": sum(r["n_sampled"] for r in rows),
        },
        "channels": rows,
    }


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(IN):
        if args.check:
            print("build_rival_youtube.py --check: SKIP (no rival_youtube_raw — network pull)")
            sys.exit(3)
        sys.exit("build_rival_youtube.py: run pull_rival_youtube.py first")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_rival_youtube.py --check: output missing — run the builder.")
        if io.open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_rival_youtube.py --check: drifted — re-run the builder.")
        print("build_rival_youtube.py --check: OK (byte-exact)")
        return
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d channel(s), %d video(s)"
          % (OUT, obj["meta"]["n_channels"], obj["meta"]["n_videos"]))
    for r in obj["channels"]:
        print("  %-12s subs %-8s  up30 %-3s up365 %-4s  med views %-8s  eng/1k %-6s  %s%s"
              % (r["key"], r["subscribers"], r["uploads_30d"], r["uploads_365d"],
                 r["median_views_365d"], r["engagement_per_1k_365d"],
                 (r["themes"][0]["label"] if r["themes"] else ""),
                 "  [PARENT]" if r["is_parent_channel"] else ("  [US]" if r["is_us"] else "")))


if __name__ == "__main__":
    main()
