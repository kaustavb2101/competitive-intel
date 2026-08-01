#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
branchkey.py — the ONE definition of how a loan-tape branch name is matched to the master.

WHY THIS FILE EXISTS. `norm_branch()` was copy-pasted into three scripts (ingest_real_tape.py,
build_impact_cards.py, make_call_lists.py) and kept in sync by a comment. Three copies of a join key
is three chances to drift, and the join is silent when it fails, so drift would not announce itself.
One definition, imported.

WHAT WAS WRONG WITH THE OLD RULE. It was:

    re.sub(r"เงินไชโย|สาขา|\\s+", "", name)

— strip the brand word, the word "branch", and whitespace, in a single left-to-right pass. That left
95 of the tape's 1,974 distinct branch names (4.8%) unmatched, and the failures were almost all
FORMATTING, not real absence:

    79  the master parenthesises the disambiguator, the tape spaces it
        master 'เงินไชโยสาขาชุมพร(วังไผ่)'  vs  tape 'สาขาชุมพร วังไผ่'
     5  '/' vs '_' in an address number, or '_' used between words
        master '...ถนนเพชรเกษม 50/1'        vs  tape '...ถนนเพชรเกษม 50_1'
     1  a zero-width space (U+200B) hiding at the end of a master name
     1  a literal typo in the master — a space injected INSIDE the word สาขา ('ส าขา'), which
        defeats the single-pass regex: at 'ส' the alternation cannot match 'สาขา' because the next
        character is a space, so the token survives into the key while the tape's clean 'สาขา' is
        stripped. Two passes fix this for free (whitespace first, then the words).

The remaining ~9 are NOT normalisation problems and are deliberately left unmatched:
    ~4  genuine spelling divergence between the two systems (บึงสามัคคี vs บึงสามัคคึ,
        สรรพาวุธ vs สรรพวุธ) — a rule that "fixed" these would be fuzzy matching, and fuzzy
        matching a branch means silently booking accounts to the wrong province.
    ~4  a disambiguating suffix on one side only ('นิคม' vs 'นิคม 304', 'พยัคฆภูมิพิสัย' vs
        'พยัคฆภูมิพิสัย 2') — could be the same branch, could be a genuine second branch. Needs the
        owner to say which, not a guess.
     1  'ฝ่ายบริหารความสัมพันธ์กับธุรกิจ' — a head-office booking bucket, not a branch at all.
        Correctly absent from the master.

THE REAL FIX IS UPSTREAM. `loan_tape_schema.md` already specifies a `branch_id` column equal to the
master's `code` (e.g. '@chaiyo30415'). The 2026-07-21 export carried only the free-text name, which is
the whole reason this normalisation exists. Ask for the code column on the next export and this file
becomes a compatibility shim for old vintages rather than load-bearing.

COLLISIONS ARE NOT FREE. Broadening what gets stripped makes keys less specific, so two master rows
can collapse onto one key. The old rule was accidentally masking one such pair:
'เงินไชโยสาขาบ้านกลาง (เพชรบูรณ์)' and 'เงินไชโย สาขาบ้านกลาง เพชรบูรณ์' — almost certainly the same
branch entered twice. master_index() therefore REPORTS every collision instead of letting one row
quietly overwrite another, and flags the dangerous case (colliding rows that disagree on province or
region) separately from the harmless one.
"""
import re
import unicodedata

# Zero-width and bidi formatting characters. These are invisible, survive copy-paste between systems,
# and make two identical-looking names unequal. Stripped before anything else.
_INVISIBLE = re.compile(r"[​-‏‪-‮⁠﻿]")

# Punctuation and separators that the two systems use interchangeably around the same name:
# parentheses (master) vs a space (tape); '/' vs '_' inside address numbers; hyphens and dots.
_PUNCT = re.compile(r"[()\[\]{}_/\\.,\-–—·•]")

# Stripped only AFTER whitespace and punctuation are gone, so a master-side typo like 'ส าขา'
# normalises to the same key as the tape's 'สาขา'.
_WORDS = re.compile(r"เงินไชโย|สาขา")


def norm_branch(s):
    """Normalise a branch name to its join key. Same key => same branch."""
    s = unicodedata.normalize("NFC", str(s or ""))
    s = _INVISIBLE.sub("", s)
    s = _PUNCT.sub("", s)
    s = re.sub(r"\s+", "", s)
    return _WORDS.sub("", s)


def master_index(mrows, value):
    """Build {key: value(row)} over the master branch list, reporting collisions rather than hiding them.

    `value` is a callable taking a master row and returning whatever the caller wants to look up
    (a province string, a tuple, ...). Returns (index, collisions) where collisions is a list of
    {"key", "names", "values", "conflicting"} — one entry per key claimed by more than one DISTINCT
    master name. `conflicting` is True when those rows disagree on the value, i.e. when picking one
    would actually change the answer; False when they agree and the collision is cosmetic.

    First writer wins, and the master is iterated in its committed order, so the result is
    deterministic — the same key always resolves to the same row.
    """
    idx, seen = {}, {}
    for m in mrows:
        name = m.get("name")
        k = norm_branch(name)
        if not k:
            continue
        v = value(m)
        if k in idx:
            if name != seen[k][0]["name"]:      # identical raw names are a master duplicate, not a collision
                seen[k].append({"name": name, "value": v})
            continue
        idx[k] = v
        seen[k] = [{"name": name, "value": v}]
    collisions = []
    for k, rows in seen.items():
        if len(rows) < 2:
            continue
        vals = [r["value"] for r in rows]
        collisions.append({
            "key": k,
            "names": [r["name"] for r in rows],
            "values": vals,
            "conflicting": len({repr(v) for v in vals}) > 1,
        })
    collisions.sort(key=lambda c: c["key"])
    return idx, collisions


def join_report(idx, names):
    """Summarise a name->master join so the miss is reported instead of swallowed.

    `names` is the iterable of tape-side branch names being joined. Returns a dict fit to drop
    straight into a builder's `meta`, matching the convention build_amphoe_crops.py and
    build_province_geo.py already use for their own unjoined rows.
    """
    names = list(names)
    unmatched = sorted({str(n) for n in names if norm_branch(n) not in idx})
    n = len(set(str(x) for x in names))
    return {
        "n_tape_names": n,
        "n_matched": n - len(unmatched),
        "n_unmatched": len(unmatched),
        "pct_matched": round(100.0 * (n - len(unmatched)) / n, 2) if n else None,
        "unmatched_names": unmatched,
        "note": ("Branch names are joined by normalised name (pipeline/branchkey.py) because the tape "
                 "export carries no branch code. Names listed here booked accounts that could not be "
                 "placed on the master; see branchkey.py for why each residual class is deliberately "
                 "NOT auto-matched. loan_tape_schema.md's branch_id column removes this join entirely."),
    }
