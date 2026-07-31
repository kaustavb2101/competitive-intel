#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_pantip.py — what Thai borrowers say about the lenders UNPROMPTED (objective #2).

WHY THIS SOURCE. Every reception channel we already have is anchored to something the brand did.
App reviews need the person to have installed an app (skews digital-first, misses the walk-in
title-loan customer). YouTube comments sit under an ad the brand paid to put there. Pantip is the
first channel where the customer starts the conversation: someone asks "is ไชโย/เงินให้ใจ actually
จำนำทะเบียน?" and strangers answer. That is the closest thing to overhearing the market.

  in : nothing — no key, no token, no login (see REACHABILITY below)
  out: source-data/pantip_threads.json   (accumulating; dedup by topic id and comment id)

  python3 pull_pantip.py                  # every brand + the category terms
  python3 pull_pantip.py --brand AUTOX    # one operator
  python3 pull_pantip.py --no-op          # skip the original-post fetch (1 request/thread cheaper)

REACHABILITY (probed 2026-07-31 from a Thai residential IP).
Two plain-HTTP endpoints, no auth, no cookies, no JS:
  * `pantip.com/search?q=<term>` — Next.js page whose `__NEXT_DATA__` carries the result rows.
  * `pantip.com/forum/topic/render_comments?tid=<id>&param=&type=3` — full comment JSON. Requires
    the header `X-Requested-With: XMLHttpRequest`; without it the server 302s. That is a client-side
    formality, not a bot-block — no WAF or Cloudflare challenge appeared anywhere.
Behaviour from a foreign/CI IP is UNVERIFIED. Do not schedule this in GitHub Actions until someone
has confirmed it answers from that IP — treat a sudden empty pull as "blocked", not "market quiet".

THE HARD CAP — read this before trusting any total.
Search reports big totals (254 threads for เงินไชโย, 4,634 for ศรีสวัสดิ์) but **serves only the
first 10**. `?page=2..4` return the same ten rows with `last_page: true`, and the POST search API
(`/api/search-service/search/query`) rejects `limit` above 10. So we cannot walk a brand's history;
we get the ten most-relevant threads per TERM. Breadth therefore comes from asking more questions,
not deeper pages — hence several query terms per brand plus the category terms. The store
accumulates across runs, so re-running as Pantip's relevance ordering drifts does widen coverage
over time. `meta.coverage` states this in the file so no downstream reader mistakes 10 for all.

PDPA / PRIVACY — same contract as pull_youtube_comments.py, read before changing.
These are individual people writing in public, not brand channels. So:
  * We store post and comment TEXT and nothing about who wrote it. The API hands us `user.mid`,
    `user.name`, `user.link`, `user.avatar` and `author_name`/`author_url` on every row; all of them
    are dropped at parse time and never reach disk. Dedup uses topic/comment ids, which identify the
    POST, not the person.
  * ONE non-identifying attribute is kept: `org: true` when Pantip's own badge marks the writer as a
    verified organisation (`user_meta.icon.type == "organization"`). That distinguishes "a lender's
    official account answered" from "a member of the public answered" — a fact about a COMPANY's
    conduct, which is the thing we are allowed to study. It is a category, not an identity.
  * We never fetch profile pages, never build a per-author history, never join to another dataset.
  * Downstream publishes aggregates plus short unattributed quotes, like every other pulse source.
"""
import argparse
import datetime
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "pantip_threads.json")

SEARCH = "https://pantip.com/search?q=%s"
COMMENTS = "https://pantip.com/forum/topic/render_comments?tid=%s&param=&type=3"
TOPIC = "https://pantip.com/topic/%s"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SERVER_CAP = 10        # threads Pantip will serve per term, whatever the reported total
CAP_PER_BRAND = 400    # threads kept per brand in the store (newest first)
SLEEP = 0.7            # polite delay between requests

# Query terms per brand. Several per brand because each term is capped at SERVER_CAP threads —
# more questions is the only way to widen coverage. Keys match the other social sources so
# build_social_themes.py folds them into the same brand buckets.
BRANDS = {
    "AUTOX":       ["เงินไชโย", "ออโต้ เอกซ์"],
    "TIDLOR":      ["เงินติดล้อ", "ติดล้อ จำนำทะเบียน"],
    "SAWAD":       ["ศรีสวัสดิ์", "ศรีสวัสดิ์ เงินสดทันใจ"],
    "MTC":         ["เมืองไทยแคปปิตอล", "เมืองไทย แคปปิตอล"],
    "SOMWANG":     ["สมหวัง เงินสั่งได้", "สมหวัง ทิสโก้"],
    "TURBO":       ["เงินเทอร์โบ"],
    "HENG":        ["เฮงลิสซิ่ง"],
    "SAK":         ["ศักดิ์สยามลิสซิ่ง"],
    "CAR4CASH":    ["คาร์ ฟอร์ แคช", "car4cash"],
    "NGERNHAIJAI": ["เงินให้ใจ"],
    "KTC_PBERM":   ["KTC พี่เบิ้ม"],
    "MICRO":       ["ไมโครลิสซิ่ง"],
    "GSB_MONEYDD": ["เงินดีดี GSB"],
    "KRUNGSRI_GO": ["GO by Krungsri"],
}

# Category terms — the conversation that is not about any one brand. Filed under _CATEGORY so a
# brand's own share is never inflated by generic product chatter.
CATEGORY = ["จำนำทะเบียน", "จำนำทะเบียนรถ", "รถแลกเงิน", "สินเชื่อทะเบียนรถ"]

TAG_RE = re.compile(r"<[^>]+>")
# Identity can also arrive INSIDE the words, not just in the metadata we drop at parse time:
# support accounts routinely open with "คุณสมาชิกหมายเลข 4339341" (Pantip's pseudonymous member
# number) and members @-mention each other. Stripping only the user object would leave those on
# disk and quietly break the promise this file makes, so scrub the text as well.
IDENT_RES = [
    (re.compile(r"(สมาชิกหมายเลข)\s*\d+"), r"\1 [ตัดออก]"),
    (re.compile(r"(?:คุณ)?สมาชิกหมายเลข\s*\d+"), "สมาชิกหมายเลข [ตัดออก]"),
    (re.compile(r"/profile/\d+"), "/profile/[redacted]"),
    (re.compile(r"@[A-Za-z0-9_.]{3,}"), "@[redacted]"),
]
STORY_RE = re.compile(r'<div class="display-post-story"[^>]*>(.*?)</div>', re.S)
OG_RE = re.compile(r'<meta property="og:description" content="(.*?)"', re.S)
NEXT_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


class Blocked(Exception):
    """Pantip answered, but not with what it answers from a Thai IP. Never treat as 'no data'."""


def get(url, headers=None):
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def detag(s):
    """Pantip stores post bodies as HTML. We want the words, not the markup — and not the people:
    every identifier a writer typed into the body is scrubbed here, at the same boundary where the
    author metadata is dropped."""
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = html.unescape(TAG_RE.sub("", s)).strip()
    for rx, repl in IDENT_RES:
        s = rx.sub(repl, s)
    return s


def search(term):
    """The ten most-relevant threads for one term. Author fields dropped here, at the boundary."""
    body = get(SEARCH % urllib.parse.quote(term))
    m = NEXT_RE.search(body)
    if not m:
        raise Blocked("no __NEXT_DATA__ for %r — the search page did not render" % term)
    data = json.loads(m.group(1))
    try:
        rl = data["props"]["initialProps"]["pageProps"]["resultList"]
    except (KeyError, TypeError):
        raise Blocked("unexpected search payload shape for %r" % term)
    out = []
    for it in (rl.get("data") or []):
        out.append({
            "id": str(it.get("id")),
            "title": detag(it.get("title")),
            "snippet": detag(it.get("detail")),
            "created": it.get("created_time"),
            "n_comment": int(it.get("total_comment") or 0),
            "rooms": [r.get("name_en") or r.get("slug") or r.get("name")
                      for r in (it.get("rooms") or []) if isinstance(r, dict)],
            "tags": [t.get("name") if isinstance(t, dict) else t for t in (it.get("tags") or [])],
            # author_name / author_url deliberately not read — see PDPA note.
        })
    return out, rl.get("total")


def original_post(tid):
    """Full opening post. The search row carries only a truncated snippet, and the OP is where the
    customer's actual question lives, so it is worth the extra request."""
    body = get(TOPIC % tid)
    m = STORY_RE.search(body)
    if m:
        txt = detag(m.group(1))
        if txt:
            return txt
    m = OG_RE.search(body)
    return html.unescape(m.group(1)).strip() if m else ""


def comments_of(tid):
    """Every comment on a thread. Identity dropped at parse time; only the org badge survives."""
    raw = get(COMMENTS % tid, {"X-Requested-With": "XMLHttpRequest",
                               "Referer": TOPIC % tid})
    raw = raw.lstrip("﻿").strip()
    if not raw or raw[0] not in "{[":
        raise Blocked("comments for %s returned non-JSON (%d bytes) — redirected or blocked"
                      % (tid, len(raw)))
    d = json.loads(raw)
    out = []
    for c in (d.get("comments") or []):
        text = detag(c.get("message"))
        if not text:
            continue
        meta = ((c.get("user") or {}).get("user_meta") or {})
        out.append({
            "id": "%s-%s" % (tid, c.get("comment_no")),
            "no": c.get("comment_no"),
            "text": text,
            "created": c.get("created_time"),
            "points": int(c.get("point") or 0),
            "replies": int(c.get("reply_count") or 0),
            "org": ((meta.get("icon") or {}).get("type") == "organization"),
        })
    return out


def load_store():
    if os.path.exists(OUT):
        try:
            d = json.load(io.open(OUT, encoding="utf-8"))
            if isinstance(d.get("brands"), dict):
                return d
        except (ValueError, IOError):
            pass
    return {"meta": {}, "brands": {}}


def harvest(store, bkey, terms, want_op, stats):
    rec = store["brands"].setdefault(bkey, {"key": bkey, "threads": []})
    by_id = {t["id"]: t for t in rec["threads"]}
    new_threads = new_comments = 0

    for term in terms:
        rows, total = search(term)
        stats["reported"][term] = total
        time.sleep(SLEEP)
        for row in rows:
            tid = row["id"]
            fresh = tid not in by_id
            t = by_id.get(tid) or dict(row, comments=[], terms=[])
            if term not in t["terms"]:
                t["terms"].append(term)
            if fresh:
                if want_op:
                    t["post"] = original_post(tid)
                    time.sleep(SLEEP)
                by_id[tid] = t
                new_threads += 1
            seen = set(c["id"] for c in t["comments"])
            try:
                for c in comments_of(tid):
                    if c["id"] not in seen:
                        seen.add(c["id"])
                        t["comments"].append(c)
                        new_comments += 1
            except Blocked:
                raise
            except (urllib.error.URLError, ValueError) as e:
                stats["skipped"].append((tid, str(e)[:80]))
            time.sleep(SLEEP)

    threads = sorted(by_id.values(), key=lambda t: t.get("created") or "", reverse=True)
    rec["threads"] = threads[:CAP_PER_BRAND]
    return new_threads, new_comments, len(rec["threads"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", help="one brand key (e.g. AUTOX); default = all + category")
    ap.add_argument("--no-op", action="store_true",
                    help="skip the full original-post fetch (saves one request per new thread)")
    a = ap.parse_args()

    targets = dict(BRANDS)
    targets["_CATEGORY"] = CATEGORY
    if a.brand:
        k = a.brand.upper()
        if k not in targets:
            print("unknown brand %r — known: %s" % (a.brand, ", ".join(sorted(targets))),
                  file=sys.stderr)
            return 2
        targets = {k: targets[k]}

    store = load_store()
    stats = {"reported": {}, "skipped": []}
    tot_t = tot_c = 0

    for bkey in sorted(targets):
        try:
            nt, nc, held = harvest(store, bkey, targets[bkey], not a.no_op, stats)
        except Blocked as e:
            # A block must never be written out as a quiet market.
            print("BLOCKED: %s" % e, file=sys.stderr)
            print("Nothing written — Pantip did not answer the way it does from a Thai IP.",
                  file=sys.stderr)
            return 3
        tot_t += nt
        tot_c += nc
        print("  %-12s %3d new threads, %5d new comments, %4d threads stored"
              % (bkey, nt, nc, held))

    n_threads = sum(len(v["threads"]) for v in store["brands"].values())
    n_comments = sum(len(t["comments"]) for v in store["brands"].values() for t in v["threads"])
    store["meta"] = {
        "title": "Pantip — unprompted Thai discussion of the title lenders",
        "generated": datetime.datetime.now(datetime.timezone.utc)
                             .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "pantip.com public search + comment endpoints (no auth, no login)",
        "measured": "Thread and comment COUNTS and TEXT are measured — read verbatim from Pantip.",
        "coverage": ("SEARCH IS CAPPED AT %d THREADS PER TERM by Pantip itself — ?page=2+ repeats "
                     "page 1 with last_page:true and the POST search API refuses limit>10. The "
                     "reported totals in meta.reported_totals are what Pantip CLAIMS exists, not "
                     "what is retrievable. Coverage widens only by adding query terms and by "
                     "re-running as relevance ordering drifts, never by paging."
                     % SERVER_CAP),
        "privacy": ("Text only. No author name, member id, profile link or avatar is read or "
                    "stored at any stage. The single retained attribute is org:true, Pantip's own "
                    "verified-organisation badge, which marks a company account rather than a "
                    "person — a category, not an identity."),
        "reported_totals": stats["reported"],
        "brands": sorted(store["brands"]),
        "n_threads": n_threads,
        "n_comments": n_comments,
    }
    if stats["skipped"]:
        store["meta"]["skipped"] = ["%s: %s" % s for s in stats["skipped"][:40]]

    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(store, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote %s - %d threads / %d comments (%d new threads, %d new comments this run)"
          % (os.path.relpath(OUT, ROOT), n_threads, n_comments, tot_t, tot_c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
