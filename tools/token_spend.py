#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
token_spend.py — local Claude Code token-spend report (the honest half of a "savings" tool)

Reads the Claude Code transcripts on THIS machine and reports what they cost, where the
money went, and what the same work would have cost on a cheaper model. Nothing is sent
anywhere: it only reads ~/.claude/projects/<slug>/*.jsonl.

Why this exists: gateway products pitch "compress the context, pay for fewer tokens". On a
cached workload that is the wrong lever. Prompt caching already discounts a re-sent prefix
~10x (Opus: $1.50/M cached read vs $15/M fresh input). A proxy that REWRITES the prefix per
request breaks exact-prefix cache matching, turning $1.50/M reads into $18.75/M writes —
12.5x worse per token, so it must delete >92% of the context just to break even. Measure
first; the levers that actually pay are model tier, session length, and call count.

  python3 tools/token_spend.py                  # this project
  python3 tools/token_spend.py --all            # every project on this machine
  python3 tools/token_spend.py --sessions       # per-session breakdown
  python3 tools/token_spend.py --what-if sonnet # cost if routine work had run on Sonnet

Prices are Anthropic list USD per 1M tokens and are stated in PRICE below — edit if your
plan differs. Dedupes by message id, so resumed/compacted transcripts are not counted twice.
"""
import argparse
import collections
import glob
import json
import os
import sys

# USD per 1M tokens: (fresh input, cache write, cache read, output)
PRICE = {
    "opus":   (15.0, 18.75, 1.50, 75.0),
    "sonnet": (3.0,   3.75, 0.30, 15.0),
    "haiku":  (1.0,   1.25, 0.10,  5.0),
}
HOME = os.path.expanduser("~")
PROJECTS = os.path.join(HOME, ".claude", "projects")


def tier_of(model):
    m = (model or "").lower()
    for k in ("opus", "sonnet", "haiku"):
        if k in m:
            return k
    return None


def cost(tier, fresh, cw, cr, out):
    pi, pw, pr, po = PRICE[tier]
    return (fresh * pi + cw * pw + cr * pr + out * po) / 1e6


def slug_for(path):
    """Claude Code's per-project transcript folder name for a working directory.

    Every path separator, drive colon and space becomes '-', and the leading drive
    letter is lowercased: C:\\Users\\A B\\proj -> c--Users-A-B-proj
    """
    p = os.path.abspath(path)
    for ch in (":", os.sep, "/", " "):
        p = p.replace(ch, "-")
    return p[:1].lower() + p[1:]


def resolve_dir(path):
    """Exact slug, else the closest existing transcript folder (case/format drift)."""
    exact = os.path.join(PROJECTS, slug_for(path))
    if os.path.isdir(exact):
        return exact
    want = slug_for(path).lower().strip("-")
    best = None
    for d in glob.glob(os.path.join(PROJECTS, "*")):
        if not os.path.isdir(d):
            continue
        have = os.path.basename(d).lower().strip("-")
        if have == want or have.endswith(want) or want.endswith(have):
            if best is None or len(os.path.basename(d)) > len(os.path.basename(best)):
                best = d
    return best


def scan(files):
    """-> (per_tier totals, per_session rows, n_calls). Dedupes by message id."""
    per_tier = collections.defaultdict(lambda: [0, 0, 0, 0, 0])   # fresh, cw, cr, out, calls
    sessions = []
    seen = set()
    for f in files:
        s = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
        peak = 0
        try:
            fh = open(f, encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                msg = d.get("message") or {}
                u = msg.get("usage")
                if not u:
                    continue
                t = tier_of(msg.get("model"))
                if not t:
                    continue
                mid = msg.get("id")
                if mid:
                    if mid in seen:
                        continue
                    seen.add(mid)
                cr = u.get("cache_read_input_tokens") or 0
                vals = (u.get("input_tokens") or 0,
                        u.get("cache_creation_input_tokens") or 0,
                        cr,
                        u.get("output_tokens") or 0)
                peak = max(peak, cr)
                for acc in (per_tier[t], s[t]):
                    for i, v in enumerate(vals):
                        acc[i] += v
                    acc[4] += 1
        if s:
            c = sum(cost(t, *a[:4]) for t, a in s.items())
            calls = sum(a[4] for a in s.values())
            reads = sum(a[2] for a in s.values())
            sessions.append({"file": os.path.basename(f), "cost": c, "calls": calls,
                             "reads": reads, "peak": peak,
                             "mb": os.path.getsize(f) / 1e6})
    return per_tier, sessions, len(seen)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="every project, not just this one")
    ap.add_argument("--sessions", action="store_true", help="per-session breakdown")
    ap.add_argument("--what-if", metavar="TIER", choices=sorted(PRICE),
                    help="recost every call at this tier (upper bound on the model lever)")
    ap.add_argument("--project", default=os.getcwd(), help="working dir to report on")
    a = ap.parse_args()

    if not os.path.isdir(PROJECTS):
        sys.exit("no transcripts at %s" % PROJECTS)
    if a.all:
        files = glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
        scope = "ALL projects"
    else:
        d = resolve_dir(a.project)
        if not d:
            sys.exit("no transcripts for %s\n(looked for %s in %s)\ntry --all"
                     % (a.project, slug_for(a.project), PROJECTS))
        files = glob.glob(os.path.join(d, "*.jsonl"))
        scope = os.path.basename(os.path.abspath(a.project))
    files.sort(key=os.path.getmtime)
    if not files:
        sys.exit("no .jsonl transcripts found")

    per_tier, sessions, n = scan(files)
    if not per_tier:
        sys.exit("no usage records found")

    print("Claude Code token spend — %s" % scope)
    print("%d transcripts, %d unique API calls\n" % (len(files), n))
    print("%-7s %8s %13s %14s %11s %10s" %
          ("model", "calls", "fresh-in", "cache-WRITE", "cache-READ", "output"))
    total = 0.0
    for t, x in sorted(per_tier.items(), key=lambda kv: -kv[1][4]):
        total += cost(t, *x[:4])
        print("%-7s %8s %13s %14s %11s %10s" %
              (t, f"{x[4]:,}", f"{x[0]:,}", f"{x[1]:,}", f"{x[2]:,}", f"{x[3]:,}"))
    print()
    for t, x in sorted(per_tier.items(), key=lambda kv: -cost(kv[0], *kv[1][:4])):
        print("  %-7s $%9.2f" % (t, cost(t, *x[:4])))
    print("  %-7s $%9.2f   TOTAL (list price)" % ("", total))

    # where the money goes — the number that decides which lever matters
    buckets = collections.Counter()
    for t, x in per_tier.items():
        pi, pw, pr, po = PRICE[t]
        buckets["cache reads"] += x[2] * pr
        buckets["cache writes"] += x[1] * pw
        buckets["output"] += x[3] * po
        buckets["fresh input"] += x[0] * pi
    s = sum(buckets.values()) or 1
    print("\ncost split")
    for k, v in buckets.most_common():
        print("  %-13s %5.1f%%  $%8.2f" % (k, v * 100 / s, v / 1e6))

    calls = sum(x[4] for x in per_tier.values())
    reads = sum(x[2] for x in per_tier.values())
    print("\naverage cached prefix re-read per call: %s tokens" % f"{reads // max(1, calls):,}")
    print("average cost per call: $%.3f" % (total / max(1, calls)))
    print("\nThe prefix is re-read on EVERY call, so spend scales with")
    print("  (context size) x (number of calls) x (model tier).")
    print("Clearing between unrelated tasks resets the prefix; a cheaper tier")
    print("cuts the read rate 5x (Opus $1.50/M -> Sonnet $0.30/M).")

    if a.what_if:
        w = 0.0
        for t, x in per_tier.items():
            w += cost(a.what_if, *x[:4])
        print("\nwhat-if: every call on %s = $%.2f (vs $%.2f) — saves $%.2f (%.0f%%)"
              % (a.what_if, w, total, total - w,
                 (total - w) * 100 / total if total else 0))
        print("Upper bound only: the hard reasoning that needs the top tier is in here too.")

    if a.sessions:
        print("\nper-session (largest first)")
        print("%-10s %8s %8s %13s %12s %10s" %
              ("session", "MB", "calls", "cache-reads", "peak prefix", "cost USD"))
        for r in sorted(sessions, key=lambda r: -r["cost"]):
            print("%-10s %8.1f %8d %13s %12s  $%8.2f" %
                  (r["file"][:8], r["mb"], r["calls"], f"{r['reads']:,}",
                   f"{r['peak']:,}", r["cost"]))
        print("\nSessions overlap when one is resumed or compacted (the replayed prefix is")
        print("counted once, in whichever transcript held it first), so per-session figures")
        print("are indicative; the deduped TOTAL above is the number to trust.")


if __name__ == "__main__":
    main()
