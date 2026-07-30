#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_rival_youtube.py — the rivals' VIDEO marketing pulse, via the official YouTube Data API.

WHY THIS SOURCE (objective #2). Video is where Thai lenders run campaign messaging before it
reaches display, and YouTube is the only major social platform that exposes it through a free,
official, ToS-clean API — no scraping, no login, no personal data. We read BRAND channels only:
channel-level counts and the public metadata of the videos those brands published. We never
touch commenters, subscribers, or any individual, so there is no Thai PDPA exposure.

  in : YOUTUBE_API_KEY in the environment or in .env (NEVER committed; .env is gitignored)
  out: source-data/rival_youtube_raw.json  (accumulating: channel stats + per-video metadata)

  python3 pull_rival_youtube.py              # curated channels
  python3 pull_rival_youtube.py --discover   # re-vet which channels belong to which operator
  python3 pull_rival_youtube.py --brand TIDLOR

QUOTA: 10,000 units/day free. A channel fetch is 1 unit per 50 channels, an uploads page 1 unit
per 50 videos, a video-stats page 1 unit per 50. A full run of this file costs well under 200
units — but --discover uses search, at 100 units PER QUERY, so it is opt-in and not run daily.

CHANNELS ARE HAND-PINNED, exactly as the Google-ads advertiser ids are, and for the same
reason: YouTube search is fuzzy and Thai brand names collide with personal names and with
individual BRANCH channels. A search for ศรีสวัสดิ์ returns a band and several private people;
เงินไชโย returns dozens of one-video branch accounts. Only the operator's own national channel
belongs in a share-of-voice comparison, so each id below was eyeballed with --discover.
"""
import argparse
import datetime
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "rival_youtube_raw.json")
UNIVERSE = os.path.join(ROOT, "source-data", "rival_universe.json")
API = "https://www.googleapis.com/youtube/v3/"

MAX_VIDEOS = 200          # newest N uploads per channel — enough for 24 months of cadence

# operator key -> (channel id, note). The note records why this channel, not a lookalike.
CHANNELS = {
    "TIDLOR":      ("UCQYxurc9EUHkCmwSjc0bChw", "เงินติดล้อ — national brand channel"),
    "TURBO":       ("UC1suNKLkr10knW39-VE4U9Q", "Ngernturbo — national brand channel"),
    "SOMWANG":     ("UC0CHmVsyRIqU_ZywpWLnu_w", "สมหวัง เงินสั่งได้ — national (not the regional acct)"),
    "SAWAD":       ("UCM6C9702eroZQGYVENTcm_w", "ศรีสวัสดิ์ เงินสดทันใจ — national brand channel"),
    "MTC":         ("UCwKRUhhrs0uzpwtMTjj9v8A", "เมืองไทย แคปปิตอล — national brand channel"),
    "MICRO":       ("UC6NMK1_0nW9zK7ZRwF6Qqkw", "ไมโครลิสซิ่ง ขวัญใจสิบล้อ — brand channel"),
    "HENG":        ("UCwvWhOBVolMcnN2zdjal1eg", "Heng Leasing : เฮงลิสซิ่ง — brand channel"),
    "SAK":         ("UCSkTr6d-9ElKUzjQIRKUxIA", "ศักดิ์สยามลิสซิ่ง — brand channel"),
    "AUTOX":       ("UC37BhUdsBwpOp3ShsUL8BWw", "เงินไชโย — OUR OWN national channel (the control)"),
    "NGERNHAIJAI": ("UCGrHku6BNayHzVkvE_u_NeQ", "เงินให้ใจ — KBank-backed brand channel"),
    "GSB_MEETEE":  ("UCM4ArAibWfe8ta9SaOAw0vQ", "มีที่ มีเงิน — GSB product channel"),
    "GSB_MONEYDD": ("UC09YCRbgvTgnILEPjBWhXpA", "MONEYDD — GSB product channel"),
    # Car4Cash has no channel of its own; Krungsri Auto's channel carries it. Flagged as a
    # PARENT channel so the UI never reads its scale as a title-loan-only audience.
    "CAR4CASH":    ("UCYAUDEaTdDBBFV4twBxWRKQ", "KrungsriAutoTV — PARENT auto-finance channel, "
                                                "not Car4Cash-specific"),
}
PARENT_CHANNEL = {"CAR4CASH"}

# Operators checked with --discover that have no brand channel at all. As with the ad pull,
# an absence is a real finding — but only from a clean run.
NO_CHANNEL = ["AMANAH", "KKP", "KTC_PBERM", "TTB_CYC"]


def load_key():
    for k in ("YOUTUBE_API_KEY", "YT_API_KEY"):
        if os.environ.get(k):
            return os.environ[k]
    for env in (os.path.join(ROOT, ".env"), os.path.join(os.path.dirname(ROOT), ".env")):
        if not os.path.exists(env):
            continue
        for line in io.open(env, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line.startswith(("YOUTUBE_API_KEY=", "YT_API_KEY=")):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def api(key, path, **params):
    params["key"] = key
    url = API + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "autox-rival-pulse/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        err = (json.loads(body).get("error") or {}) if body.startswith("{") else {}
        reason = (err.get("errors") or [{}])[0].get("reason", "")
        # quota exhaustion must stop the run loudly, never look like "this rival posts nothing"
        if reason in ("quotaExceeded", "dailyLimitExceeded"):
            raise RuntimeError("YouTube quota exhausted — re-run tomorrow. Nothing written.")
        raise RuntimeError("%s HTTP %s %s: %s" % (path, e.code, reason,
                                                  err.get("message", body[:160])))


def universe():
    if not os.path.exists(UNIVERSE):
        return {}
    return {o["key"]: o for o in
            json.load(io.open(UNIVERSE, encoding="utf-8")).get("operators", [])}


def uploads_playlist(key, channel_ids):
    """channel id -> (snippet, statistics, uploads-playlist-id)."""
    out = {}
    for i in range(0, len(channel_ids), 50):
        d = api(key, "channels", part="snippet,statistics,contentDetails",
                id=",".join(channel_ids[i:i + 50]), maxResults=50)
        for it in d.get("items", []):
            out[it["id"]] = (it.get("snippet") or {}, it.get("statistics") or {},
                             ((it.get("contentDetails") or {}).get("relatedPlaylists")
                              or {}).get("uploads"))
    return out


def videos_of(key, playlist_id, cap=MAX_VIDEOS):
    """Newest uploads with their public stats. Two cheap calls per 50 videos."""
    ids, token = [], None
    while len(ids) < cap:
        p = dict(part="contentDetails", playlistId=playlist_id, maxResults=50)
        if token:
            p["pageToken"] = token
        d = api(key, "playlistItems", **p)
        for it in d.get("items", []):
            vid = (it.get("contentDetails") or {}).get("videoId")
            if vid:
                ids.append(vid)
        token = d.get("nextPageToken")
        if not token:
            break
        time.sleep(0.2)
    ids = ids[:cap]
    out = []
    for i in range(0, len(ids), 50):
        d = api(key, "videos", part="snippet,statistics,contentDetails",
                id=",".join(ids[i:i + 50]), maxResults=50)
        for it in d.get("items", []):
            sn, st = it.get("snippet") or {}, it.get("statistics") or {}
            out.append({
                "id": it["id"],
                "title": sn.get("title"),
                "published": (sn.get("publishedAt") or "")[:10],
                "duration": (it.get("contentDetails") or {}).get("duration"),
                "views": int(st["viewCount"]) if st.get("viewCount") else None,
                "likes": int(st["likeCount"]) if st.get("likeCount") else None,
                "comments": int(st["commentCount"]) if st.get("commentCount") else None,
            })
        time.sleep(0.2)
    return out


def do_discover(key):
    ops = universe()
    print("Re-vetting brand channels (search costs 100 quota units per query).\n")
    for opkey in sorted(ops):
        o = ops[opkey]
        for q in [o.get("name_th"), o.get("name_en")]:
            if not q:
                continue
            d = api(key, "search", part="snippet", type="channel", q=q,
                    maxResults=5, regionCode="TH")
            for it in d.get("items", []):
                sn = it["snippet"]
                mark = " <-- PINNED" if CHANNELS.get(opkey, ("",))[0] == sn["channelId"] else ""
                print("  %-12s %-36s %s%s" % (opkey, sn["title"][:34], sn["channelId"], mark))
            time.sleep(0.3)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--discover", action="store_true", help="re-vet channels (costly); no write")
    ap.add_argument("--brand", help="pull a single operator key")
    a = ap.parse_args()

    key = load_key()
    if not key:
        print("NO KEY — nothing was called.\n  echo 'YOUTUBE_API_KEY=<key>' >> .env")
        print("  enable YouTube Data API v3 + create a key restricted to it.")
        return 2
    if a.discover:
        do_discover(key)
        return 0

    ops = universe()
    todo = {k: v for k, v in CHANNELS.items() if not a.brand or k.lower() == a.brand.lower()}
    if not todo:
        print("unknown --brand; known: %s" % ", ".join(sorted(CHANNELS)))
        return 2

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    meta = uploads_playlist(key, [cid for cid, _ in todo.values()])
    channels = {}
    for opkey, (cid, note) in sorted(todo.items()):
        sn, st, pl = meta.get(cid, ({}, {}, None))
        if not sn:
            print("  %-12s channel %s not returned by the API — skipped" % (opkey, cid))
            continue
        vids = videos_of(key, pl) if pl else []
        op = ops.get(opkey) or {}
        channels[opkey] = {
            "key": opkey,
            "name_en": op.get("name_en") or opkey,
            "name_th": op.get("name_th"),
            "tier": op.get("tier"),
            "channel_id": cid,
            "channel_title": sn.get("title"),
            "channel_note": note,
            "is_parent_channel": opkey in PARENT_CHANNEL,
            "started": (sn.get("publishedAt") or "")[:10],
            "subscribers": int(st["subscriberCount"]) if st.get("subscriberCount") else None,
            "views_total": int(st["viewCount"]) if st.get("viewCount") else None,
            "video_count": int(st["videoCount"]) if st.get("videoCount") else None,
            "videos": vids,
        }
        print("  %-12s %-32s subs %-9s videos %-6s pulled %d"
              % (opkey, (sn.get("title") or "")[:30],
                 st.get("subscriberCount", "?"), st.get("videoCount", "?"), len(vids)))

    payload = {
        "meta": {
            "source": "YouTube Data API v3 (official)",
            "provenance": "MEASURED — public channel statistics and public video metadata for "
                          "BRAND channels only. No commenters, no subscribers, no individuals: "
                          "advertiser-side marketing output, not personal data.",
            "pulled": today,
            "max_videos_per_channel": MAX_VIDEOS,
            "no_channel": sorted(NO_CHANNEL),
            "parent_channels": sorted(PARENT_CHANNEL),
            "caveat": "Channels are hand-pinned: YouTube search is fuzzy and Thai brand names "
                      "collide with personal names and with individual BRANCH accounts. "
                      "CAR4CASH maps to Krungsri Auto's PARENT channel, so its scale covers "
                      "all auto finance, not title loans alone.",
        },
        "channels": channels,
    }
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, sort_keys=True, indent=1)
    print("\nwrote %s — %d channel(s), %d video(s)"
          % (os.path.relpath(OUT, ROOT), len(channels),
             sum(len(c["videos"]) for c in channels.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
