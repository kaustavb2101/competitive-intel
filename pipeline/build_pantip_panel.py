#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_pantip_panel.py — what borrowers say about each lender, in their own words (objective #2).

  in : source-data/pantip_threads.json   208 threads / 2,649 comments across 14 brands (pull_pantip.py)
  out: platform/data/pantip_panel.json   per-brand volume, themes, reply rate and short quotes

WHY THIS LAYER EXISTS. Pantip already fed the Competition tab, but only blended into the aggregate
theme mix — the brand split, the thread volumes and every quote were averaged away. Pantip is the
one place Thai borrowers discuss lenders UNPROMPTED, at length, without a review form asking them
to rate anything. That is the closest thing we have to overhearing the market talk about us.

THREE HONEST DIFFICULTIES, EACH HANDLED RATHER THAN HIDDEN
------------------------------------------------------------------------------------------------
1. THE SAMPLE IS CAPPED, THE VOLUME IS NOT. Pantip's search returns at most 10 threads per term and
   refuses to page further, so our retrieved thread counts are a CEILING we hit, not a measurement
   of how much each brand is discussed. Ranking brands by threads-we-pulled would rank them by how
   many search terms we happened to configure. Volume therefore comes from `reported_totals` —
   the total Pantip itself claims for each term — and the retrieved threads are used only for what
   they genuinely are: a readable sample of the text.

2. SEVERAL BRAND NAMES ARE ORDINARY THAI. `สมหวัง` ("wish fulfilled") and `ศรีสวัสดิ์` (also a
   district of Kanchanaburi, and a common personal name) match far more than the lender. So the
   reported total is an upper bound, and we MEASURE how loose it is: `precision` is the share of
   the threads Pantip returned for that brand whose opening post actually contains the brand's
   name. It runs 6% for สมหวัง against 100% for เงินติดล้อ — a 16x difference in how much the raw
   number can be trusted, which is far too large to leave unstated. `est_threads` applies it, and
   is labelled ESTIMATED because it is exactly that: a claim multiplied by a sampled rate.

3. THE SAMPLE IS SMALL. Ten to twenty threads per brand cannot carry a percentage to the decimal.
   Rates are published as counts alongside their denominator so a reader can see 3-of-10 for what
   it is, and no brand under MIN_THREADS gets a rate at all.

PDPA. Pantip threads are individual people's writing. No author name, member id, handle, profile
link or avatar is read at any stage, and pull_pantip.py additionally scrubs identifiers out of the
body text (members address each other by pseudonymous member number). This builder re-scrubs
defensively before publishing any quote — a second pass costs nothing and the failure mode of
missing one is a real person's identifier on a public site. Published quotes are short, verbatim
and unattributed. The single retained attribute is `org` — Pantip's own verified-organisation
badge, which marks a company account rather than a person, and is a category, not an identity.

Deterministic + network-free. `--check` byte-compares. Exits 3 (SKIP) if the pull is absent.

  python3 build_pantip_panel.py
  python3 build_pantip_panel.py --check
"""
import argparse
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "pipeline")
IN = os.path.join(ROOT, "source-data", "pantip_threads.json")
IN_UNI = os.path.join(ROOT, "source-data", "rival_universe.json")
OUT = os.path.join(ROOT, "platform", "data", "pantip_panel.json")

MIN_THREADS = 8      # below this, publish the text but never a rate
MAX_QUOTES = 3       # per brand
QUOTE_CHARS = 150    # published length
QUOTE_MIN = 40       # shorter than this is "up" / "same here", not a view
QUOTE_MAX_DOC = 700  # longer than this is a news digest or a blog repost, not a borrower talking
MIN_THEME_HITS = 2   # a theme needs this many hits in a brand's own text to be listed


def _load_module(path, name):
    """Import a sibling pipeline script as a module so its lexicon/brand map has ONE definition.
    Re-typing either here would let them drift apart silently, and a theme lexicon that disagrees
    with the one used on the rest of the Competition tab is worse than no themes at all."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(PIPE, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Pantip's search-result markup, and a defensive second pass over the identifiers pull_pantip.py
# already strips. Belt and braces: this is the last step before the text is published.
EM = re.compile(r"\{\{/?e?em\}\}")
IDENT = [
    re.compile(r"สมาชิกหมายเลข\s*\d+"),     # Pantip's pseudonymous member number
    re.compile(r"@[A-Za-z0-9_.\-]{2,}"),      # @-mentions
    re.compile(r"https?://\S+"),              # profile links
    re.compile(r"\b0\d{1,2}[-\s]?\d{3}[-\s]?\d{3,4}\b"),   # Thai phone numbers
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),             # e-mail
    re.compile(r"\bid\s*line\s*[:：]?\s*\S+", re.I),        # LINE ids
]


def clean(s):
    t = EM.sub("", s or "")
    for rx in IDENT:
        t = rx.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


def quote_of(text):
    t = clean(text)
    return (t[:QUOTE_CHARS].rstrip() + "…") if len(t) > QUOTE_CHARS else t


def reported_n(v):
    """Pantip reports a total as Thai text — 'พบ 1,263 กระทู้'. Pull the number out; a term it
    reported nothing for returns None rather than 0, because 'not reported' and 'zero threads'
    are different claims."""
    if not isinstance(v, str):
        return None
    digits = re.sub(r"[^\d]", "", v)
    return int(digits) if digits else None


def build():
    doc = json.load(open(IN, encoding="utf-8"))
    pull = _load_module("pull_pantip.py", "pull_pantip")
    themes_mod = _load_module("build_social_themes.py", "build_social_themes")
    DEMAND = themes_mod.DEMAND
    BRANDS, CATEGORY = pull.BRANDS, pull.CATEGORY

    labels, tiers = {}, {}
    if os.path.exists(IN_UNI):
        for o in json.load(open(IN_UNI, encoding="utf-8")).get("operators", []):
            labels[o["key"]] = o.get("name_th") or o.get("brand") or o["key"]
            tiers[o["key"]] = o.get("tier")

    reported = (doc.get("meta") or {}).get("reported_totals") or {}
    rows = []
    for key, rec in (doc.get("brands") or {}).items():
        threads = rec.get("threads") or []
        if not threads:
            continue
        is_cat = key == "_CATEGORY"
        terms = CATEGORY if is_cat else BRANDS.get(key, [])

        n_comments, matched, with_org, org_msgs = 0, 0, 0, 0
        borrower_text, quotes = [], []
        for t in threads:
            head = clean((t.get("title") or "") + " " + (t.get("post") or t.get("snippet") or ""))
            if terms and any(x.lower() in head.lower() for x in terms):
                matched += 1
            comments = t.get("comments") or []
            n_comments += len(comments)
            org_here = [c for c in comments if c.get("org")]
            org_msgs += len(org_here)
            if org_here:
                with_org += 1
            if head:
                borrower_text.append((head, (t.get("created") or "")[:10]))
            for c in comments:
                if c.get("org"):        # a lender replying is not a borrower speaking
                    continue
                txt = clean(c.get("text") or "")
                if txt:
                    borrower_text.append((txt, (c.get("created") or "")[:10]))

        # Themes over this brand's borrower-side text only, using the SAME lexicon as the rest of
        # the Competition tab so the two readouts can never disagree about what a theme means.
        blob = [themes_mod.norm(x) for x, _ in borrower_text]
        theme_rows = []
        for tkey, tlabel, kind, kws in DEMAND:
            hit_docs = [i for i, b in enumerate(blob) if themes_mod.hits(b, kws)]
            if len(hit_docs) >= MIN_THEME_HITS:
                theme_rows.append({"key": tkey, "label": tlabel, "kind": kind,
                                   "n": len(hit_docs),
                                   "pct": round(100.0 * len(hit_docs) / len(blob), 1) if blob else None})
        theme_rows.sort(key=lambda r: (-r["n"], r["key"]))

        # Quotes must MENTION THE BRAND and carry a theme, and must not be enormous. Selecting the
        # longest themed document instead surfaced stock-news roundups and blog reposts — Pantip
        # search returns them, they are long, and at 70% precision some were not about us at all.
        # A borrower asking about their loan writes a paragraph, not a newspaper digest, so an
        # upper length bound is a better filter for real customer voice than any keyword blocklist.
        # First theme to claim a document wins it, and the ordering key is TOTAL — length, then
        # document index, then label. A set of (index, label) sorted on length alone leaves ties
        # to set iteration order, which Python randomises per process via PYTHONHASHSEED: the
        # build then emits different quotes on consecutive runs and --check fails intermittently.
        kw_by_theme = dict((d[0], d[3]) for d in DEMAND)
        themed, claimed = [], set()
        for r in theme_rows[:4]:
            for i, b in enumerate(blob):
                if i not in claimed and themes_mod.hits(b, kw_by_theme[r["key"]]):
                    claimed.add(i)
                    themed.append((i, r["label"]))
        seen = set()
        for i, tl in sorted(themed, key=lambda p: (-len(borrower_text[p[0]][0]), p[0], p[1])):
            txt, date = borrower_text[i]
            if not (QUOTE_MIN <= len(txt) <= QUOTE_MAX_DOC) or i in seen:
                continue
            if terms and not any(x.lower() in txt.lower() for x in terms):
                continue
            seen.add(i)
            quotes.append({"text": quote_of(txt), "theme": tl, "date": date})
            if len(quotes) >= MAX_QUOTES:
                break

        # Volume: Pantip's own claim for this brand's BROADEST term. Summing a brand's terms would
        # double-count — "ศรีสวัสดิ์ เงินสดทันใจ" is a subset of "ศรีสวัสดิ์" — so take the max and
        # name the term it came from, rather than quietly adding overlapping searches together.
        per_term = [{"term": tm, "reported": reported_n(reported.get(tm))} for tm in terms]
        have = [r for r in per_term if r["reported"] is not None]
        top = max(have, key=lambda r: r["reported"]) if have else None
        precision = round(matched / len(threads), 3) if terms else None

        # Label from the rival census where the brand is in it; otherwise fall back to the brand's
        # own broadest search term, which is a real string from the data. Never the raw key — a
        # reader should not have to decode KRUNGSRI_GO, and inventing a display name would be
        # guessing at a competitor's Thai branding.
        label = labels.get(key) or (terms[0] if terms else key)
        row = {
            "key": key,
            "label": label if not is_cat else "The category itself (no brand named)",
            "tier": tiers.get(key) if not is_cat else "category",
            "is_us": key == "AUTOX",
            "n_threads_sampled": len(threads),
            "n_comments_sampled": n_comments,
            "reported_total": top["reported"] if top else None,
            "reported_term": top["term"] if top else None,
            "per_term": per_term,
            "precision": precision,
            "est_threads": (int(round(top["reported"] * precision))
                            if top and precision is not None else None),
            "org_reply_threads": with_org,
            "org_reply_msgs": org_msgs,
            # A rate on 10 threads is noise dressed as a number; publish the fraction, and only
            # once there are enough threads for the fraction to mean anything at all.
            "reply_rate": (round(100.0 * with_org / len(threads), 0)
                           if len(threads) >= MIN_THREADS else None),
            "themes": theme_rows[:6],
            "quotes": quotes,
        }
        rows.append(row)

    # Rank by what Pantip claims, corrected by measured precision — the honest best estimate of who
    # is actually being talked about. Brands with no reported total sort last rather than as zero.
    rows.sort(key=lambda r: (r["key"] == "_CATEGORY", -(r["est_threads"] or -1), r["key"]))

    brands = [r for r in rows if r["key"] != "_CATEGORY"]
    us = next((r for r in brands if r["is_us"]), None)
    ranked = [r for r in brands if r["est_threads"] is not None]
    loud = ranked[0] if ranked else None
    us_rank = (ranked.index(us) + 1) if (us and us in ranked) else None

    # Lead with the RANK, not the multiple. The rank survives the precision bias described in
    # meta.precision_bias; the multiple does not, and quoting "36x" as the headline would put the
    # weight of the finding on its least defensible number.
    headline = None
    if us and loud and us.get("est_threads") is not None and loud is not us:
        headline = ("We are the %d%s most-discussed of %d title lenders on Pantip — %s leads, with "
                    "roughly %s threads against our %s (ESTIMATED: Pantip's own reported totals "
                    "scaled by how often the brand name really appears in the thread, which leans "
                    "high for everyone). The ranking is the finding; the multiple is indicative. "
                    "Share of unprompted conversation is not market share, but where we are absent "
                    "a rival's version of the product is the only one being read."
                    % (us_rank, {1: "st", 2: "nd", 3: "rd"}.get(us_rank if us_rank < 20 else 0, "th"),
                       len(ranked), loud["label"],
                       "{:,}".format(loud["est_threads"]), "{:,}".format(us["est_threads"])))

    answered = [r for r in brands if r["reply_rate"] is not None]
    answered.sort(key=lambda r: -r["reply_rate"])
    reply_line = None
    if us and us.get("reply_rate") is not None and answered:
        better = [r["label"] for r in answered if r["reply_rate"] > us["reply_rate"]]
        reply_line = ("We reply to %d of %d sampled threads (%d%%). %s"
                      % (us["org_reply_threads"], us["n_threads_sampled"], us["reply_rate"],
                         ("Answering more consistently than us: " + ", ".join(better) + ".")
                         if better else "No tracked rival answers more consistently."))

    m = doc.get("meta") or {}
    return {
        "meta": {
            "title": "Pantip — what borrowers say about each lender, unprompted",
            "generated_by": "pipeline/build_pantip_panel.py",
            "source": m.get("source"),
            "pulled": (m.get("generated") or "")[:10] or None,
            "measured": "Thread and comment TEXT, the sampled counts, and the reply counts are "
                        "MEASURED — read verbatim from Pantip. Volume per brand is Pantip's OWN "
                        "reported total for the search term. est_threads is ESTIMATED: that "
                        "reported total multiplied by the measured share of sampled threads whose "
                        "opening post really names the brand.",
            "cap": "Pantip caps search at 10 threads per term and refuses to page further, so the "
                   "sampled thread counts are a ceiling we hit, not a measure of how much each "
                   "brand is discussed. Never rank brands by n_threads_sampled — that ranks them "
                   "by how many search terms were configured. Volume comes from reported_total.",
            "name_collision": "Several brand names are ordinary Thai. สมหวัง means 'wish "
                              "fulfilled'; ศรีสวัสดิ์ is also a district of Kanchanaburi and a "
                              "common personal name. Their reported totals therefore count far "
                              "more than the lender, which is what `precision` measures — it runs "
                              "from 6% to 100% across the brands tracked.",
            "precision_bias": "precision is measured on the threads Pantip ranked MOST relevant, "
                              "which is the friendliest slice of the corpus. The long tail behind "
                              "a reported total will match the brand less often, not more — so "
                              "precision is an upper bound and est_threads leans HIGH. Read the "
                              "ranking, which is robust to this, ahead of the multiple, which is "
                              "not.",
            "small_sample": "Rates come from 8-20 threads per brand. They are published with "
                            "their numerator and denominator so a reader can judge them; no rate "
                            "is shown for a brand below %d sampled threads." % MIN_THREADS,
            "privacy": "PDPA. No author name, member id, handle, profile link or avatar is read "
                       "or stored at any stage, and identifiers are scrubbed from the body text "
                       "too. Quotes are short, verbatim and unattributed. The one retained "
                       "attribute is Pantip's verified-organisation badge, which distinguishes a "
                       "company account from a person — a category, not an identity.",
            "org_note": "Comments from a verified organisation account are a LENDER speaking. They "
                        "are excluded from the borrower text and themes, and counted separately as "
                        "the reply rate.",
            "n_brands": len(brands),
            "n_threads_sampled": sum(r["n_threads_sampled"] for r in rows),
            "n_comments_sampled": sum(r["n_comments_sampled"] for r in rows),
        },
        "headline": headline,
        "reply_line": reply_line,
        "brands": rows,
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
            print("build_pantip_panel.py --check: SKIP (source-data/pantip_threads.json absent)")
            sys.exit(3)
        sys.exit("build_pantip_panel.py: source-data/pantip_threads.json missing — run pull_pantip.py")
    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            sys.exit("build_pantip_panel.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_pantip_panel.py --check: drifted — re-run the builder.")
        print("build_pantip_panel.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    o = json.loads(payload)
    print("wrote %s — %d brands, %d threads / %d comments sampled"
          % (OUT, o["meta"]["n_brands"], o["meta"]["n_threads_sampled"],
             o["meta"]["n_comments_sampled"]))
    if o["headline"]:
        print("headline:", o["headline"])
    if o["reply_line"]:
        print("reply:   ", o["reply_line"])


if __name__ == "__main__":
    main()
