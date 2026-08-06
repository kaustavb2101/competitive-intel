#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_youtube_comments.py — what the PUBLIC says under the rivals' videos (objective #2).

WHY THIS SOURCE. `pull_rival_youtube.py` gives us what each lender BROADCASTS: cadence, reach,
which campaigns they push. It cannot tell us how any of it lands. The comment threads under those
same videos are the cheapest honest read on reception we can get in Thailand — the app-store
ladders (Play + Apple) only capture people who installed an app, which skews to the digital-first
lenders and misses the walk-in title-loan customer almost entirely. Comments do not.

  in : YOUTUBE_API_KEY in the environment or in .env (NEVER committed; .env is gitignored)
       source-data/rival_youtube_raw.json  (the video list — run pull_rival_youtube.py first)
  out: source-data/youtube_comments.json   (accumulating; dedup by comment id)

  python3 pull_youtube_comments.py                 # newest N videos per channel that have comments
  python3 pull_youtube_comments.py --brand TIDLOR  # one operator
  python3 pull_youtube_comments.py --all           # every video with comments (costs far more quota)

PDPA / PRIVACY — read before changing this file.
`pull_rival_youtube.py` deliberately drew a line in its docstring: "We read BRAND channels only …
we never touch commenters, subscribers, or any individual." This file crosses that line, because
reception cannot be measured without reading what people wrote. So it crosses it as narrowly as
possible:

  * We store the comment TEXT and nothing about who wrote it. No display name, no channel id, no
    channel URL, no avatar, no profile link — the API returns all of them and we drop every one at
    parse time, so they never reach disk. Dedup uses the comment id, which identifies the COMMENT,
    not the person.
  * We never call `commenterChannelId`-based endpoints, never build a per-author history, and never
    join comments to any other dataset. There is no way to reassemble an individual from this file.
  * Downstream (`build_rival_pulse.py`) publishes only aggregates plus short unattributed quotes —
    the same contract the app-review ladders already ship under.

That is the whole justification: aggregate reception of a COMPANY's public marketing. If a future
change needs author identity, it needs a fresh privacy decision first — do not quietly add it.

QUOTA. 10,000 units/day free. `commentThreads.list` is 1 unit per call and returns up to 100
comments, so the default run (<=MAX_VIDEOS newest commented videos per channel, <=MAX_PAGES pages
each) costs a few hundred units. `--all` can cost thousands; it is opt-in for that reason. Quota
exhaustion raises loudly and writes nothing, so a truncated pull can never be mistaken for
"the rivals' audiences went quiet".
"""
import argparse
import datetime
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source-data", "rival_youtube_raw.json")
OUT = os.path.join(ROOT, "source-data", "youtube_comments.json")
API = "https://www.googleapis.com/youtube/v3/"

MAX_VIDEOS = 40      # newest commented videos per channel per run (default mode)
MAX_PAGES = 2        # <=100 comments per page, so <=200 comments per video
CAP_PER_BRAND = 6000  # keep the accumulating store bounded


def load_key():
    """Same resolution order as pull_rival_youtube.py — env first, then a gitignored .env."""
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


class CommentsOff(Exception):
    """The uploader disabled comments. A fact about the video, not a failure of the run."""


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
        if reason in ("quotaExceeded", "dailyLimitExceeded"):
            raise RuntimeError("YouTube quota exhausted — re-run tomorrow. Nothing written.")
        # a video with comments turned off, or made private since the video list was pulled
        if reason in ("commentsDisabled", "videoNotFound", "forbidden"):
            raise CommentsOff(reason)
        raise RuntimeError("%s HTTP %s %s: %s" % (path, e.code, reason,
                                                  err.get("message", body[:160])))


def strip_author(item):
    """Take the comment, drop every field that identifies who wrote it.

    The API hands us authorDisplayName, authorChannelId, authorChannelUrl and
    authorProfileImageUrl on every single comment. None of them are read here, so none of them
    reach disk. See the PDPA note at the top of this file before adding any of them back.
    """
    top = (((item.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {})
    text = (top.get("textOriginal") or top.get("textDisplay") or "").strip()
    if not text:
        return None
    return {
        "id": item.get("id"),                                   # identifies the COMMENT, not a person
        "text": text,
        "published": top.get("publishedAt"),
        "likes": int(top.get("likeCount") or 0),
        "replies": int((item.get("snippet") or {}).get("totalReplyCount") or 0),
    }


def comments_of(key, video_id, pages=MAX_PAGES):
    """Top-level comment threads for one video. Replies are counted, not fetched."""
    out, token = [], None
    for _ in range(pages):
        params = dict(part="snippet", videoId=video_id, maxResults=100,
                      order="relevance", textFormat="plainText")
        if token:
            params["pageToken"] = token
        d = api(key, "commentThreads", **params)
        for item in d.get("items") or []:
            c = strip_author(item)
            if c:
                out.append(c)
        token = d.get("nextPageToken")
        if not token:
            break
    return out


def load_store():
    if not os.path.exists(OUT):
        return {"brands": {}, "meta": {}}
    d = json.load(io.open(OUT, encoding="utf-8"))
    d.setdefault("brands", {})
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", help="one operator key (e.g. TIDLOR); default = all")
    ap.add_argument("--all", action="store_true",
                    help="every video that has comments, not just the newest %d" % MAX_VIDEOS)
    ap.add_argument("--pages", type=int, default=MAX_PAGES,
                    help="comment pages per video (100 each); default %d" % MAX_PAGES)
    a = ap.parse_args()

    key = load_key()
    if not key:
        print("YOUTUBE_API_KEY not set (env or .env). Nothing written.", file=sys.stderr)
        return 2
    if not os.path.exists(SRC):
        print("missing %s — run pull_rival_youtube.py first. Nothing written." % SRC,
              file=sys.stderr)
        return 2

    raw = json.load(io.open(SRC, encoding="utf-8"))
    channels = raw.get("channels") or {}
    if a.brand:
        channels = {k: v for k, v in channels.items() if k == a.brand.upper()}
        if not channels:
            print("unknown brand %r — known: %s"
                  % (a.brand, ", ".join(sorted(raw.get("channels") or {}))), file=sys.stderr)
            return 2

    store = load_store()
    calls = 0
    off = []

    for bkey in sorted(channels):
        ch = channels[bkey]
        # newest first; only videos the API will actually have threads for
        vids = [v for v in (ch.get("videos") or []) if int(v.get("comments") or 0) > 0]
        vids.sort(key=lambda v: v.get("published") or "", reverse=True)
        if not a.all:
            vids = vids[:MAX_VIDEOS]

        rec = store["brands"].setdefault(bkey, {
            "key": bkey, "name_th": ch.get("name_th"), "name_en": ch.get("name_en"),
            "channel_title": ch.get("channel_title"), "comments": [],
        })
        seen = set(c["id"] for c in rec["comments"])
        added = 0

        for v in vids:
            try:
                got = comments_of(key, v["id"], pages=a.pages)
                calls += a.pages
            except CommentsOff:
                off.append((bkey, v["id"]))
                continue
            for c in got:
                if c["id"] in seen:
                    continue
                seen.add(c["id"])
                c["video"] = v["id"]
                c["video_title"] = v.get("title")
                c["video_published"] = v.get("published")
                rec["comments"].append(c)
                added += 1

        # newest-first, bounded — the store accumulates across runs and must not grow forever
        rec["comments"].sort(key=lambda c: c.get("published") or "", reverse=True)
        if len(rec["comments"]) > CAP_PER_BRAND:
            rec["comments"] = rec["comments"][:CAP_PER_BRAND]
        print("  %-13s %4d videos scanned, %4d new comments, %5d stored"
              % (bkey, len(vids), added, len(rec["comments"])))

    total = sum(len(r["comments"]) for r in store["brands"].values())
    store["meta"] = {
        "source": "YouTube Data API v3 · commentThreads.list (public comments on brand-channel videos)",
        "pulled": datetime.datetime.now(datetime.timezone.utc)
                          .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "brands": len(store["brands"]),
        "comments": total,
        "mode": "all" if a.all else "newest %d commented videos per channel" % MAX_VIDEOS,
        "pages_per_video": a.pages,
        "api_calls_this_run": calls,
        "comments_disabled_videos": len(off),
        "privacy": ("Comment TEXT only. Author display name, channel id, channel URL and profile "
                    "image are dropped at parse time and never written to disk; dedup uses the "
                    "comment id, which identifies the comment and not the person. No per-author "
                    "history is built and comments are never joined to another dataset."),
        "measured": True,
    }
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(store, ensure_ascii=False, indent=1, sort_keys=True))
    print("\nwrote %s — %d brands / %d comments (%d API units this run, %d videos had comments off)"
          % (os.path.relpath(OUT, ROOT), len(store["brands"]), total, calls, len(off)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
