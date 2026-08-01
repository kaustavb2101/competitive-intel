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


# ── explicit master-name correction (2026-08) ────────────────────────────────────────────────
# One master row is a plain MISSPELLING, not a naming-convention mismatch: 'เงินไชโย
# สาขาพยัคฆภูมิสัย' (code @chaiyo50506, prov มหาสารคาม) — its own `district` field already spells
# the town correctly as 'พยัคฆภูมิพิสัย', so the branch `name` field is simply wrong. The tape's
# 'สาขาพยัคฆภูมิพิสัย' (484 accounts, ops Area มหาสารคาม) is the correctly-spelled name for this
# exact branch and has no other candidate on the master, but norm_branch() cannot join it because
# the two spellings differ. This dict is the ONLY entry: a verified, one-off correction of a single
# master row, not a fuzzy/edit-distance rule (see the module docstring for why that class of change
# is banned for this join — it would silently book accounts to the wrong province).
#
# 'เงินไชโยสาขาพยัคฆภูมิพิสัย 2' (@chaiyo50517) is a SEPARATE, owner-confirmed branch. Its
# norm_branch() key carries the trailing '2' ('...พยัคฆภูมิพิสัย2') so it never collides with the
# corrected key added here, and it is left untouched.
MASTER_KEY_ALIASES = {
    # @chaiyo50506: 'เงินไชโย สาขาพยัคฆภูมิสัย' (typo key) -> 'สาขาพยัคฆภูมิพิสัย' (correct key)
    norm_branch("เงินไชโย สาขาพยัคฆภูมิสัย"): norm_branch("สาขาพยัคฆภูมิพิสัย"),

    # @chaiyo30203: master 'เงินไชโย สาขานิคม' (ปราจีนบุรี) == tape 'สาขานิคม 304' — both rows agree
    # on province (ปราจีนบุรี) and the owner has ruled these are the same branch, written two ways
    # (owner ruling 2026-08-01).
    norm_branch("เงินไชโย สาขานิคม"): norm_branch("สาขานิคม 304"),

    # @chaiyo40627: master 'เงินไชโยห้วยไคร้' (เชียงราย) == tape 'สาขาห้วยไคร้ เชียงราย' — both rows
    # agree on province (เชียงราย) and the owner has ruled these are the same branch, written two ways
    # (owner ruling 2026-08-01).
    norm_branch("เงินไชโยห้วยไคร้"): norm_branch("สาขาห้วยไคร้ เชียงราย"),

    # @chaiyo30125: master 'เงินไชโยหัวไทร(ฉะฯ)' (ฉะเชิงเทรา) == tape 'สาขาหัวไทร ฉะเชิงเทรา' — both
    # rows agree on province (ฉะเชิงเทรา) and the owner has ruled these are the same branch, written
    # two ways (owner ruling 2026-08-01). NOTE: a DIFFERENT, unrelated master row — 'เงินไชโยสาขาหัวไทร'
    # (@chaiyo70524, นครศรีธรรมราช) — also contains the word 'หัวไทร'. That row's own key is 'หัวไทร',
    # which is distinct from this alias's new key ('หัวไทรฉะเชิงเทรา'), so @chaiyo70524 is untouched and
    # still resolves to its own row under its own name — verified via master_index() before this entry
    # was added.
    norm_branch("เงินไชโยหัวไทร(ฉะฯ)"): norm_branch("สาขาหัวไทร ฉะเชิงเทรา"),
}


def master_index(mrows, value):
    """Build {key: value(row)} over the master branch list, reporting collisions rather than hiding them.

    `value` is a callable taking a master row and returning whatever the caller wants to look up
    (a province string, a tuple, ...). Returns (index, collisions) where collisions is a list of
    {"key", "names", "values", "conflicting"} — one entry per key claimed by more than one DISTINCT
    master name. `conflicting` is True when those rows disagree on the value, i.e. when picking one
    would actually change the answer; False when they agree and the collision is cosmetic.

    First writer wins, and the master is iterated in its committed order, so the result is
    deterministic — the same key always resolves to the same row.

    Also applies MASTER_KEY_ALIASES: a small, explicit set of verified one-off corrections to a
    master row's own name (currently just the @chaiyo50506 spelling fix — see that dict's comment).
    Each alias ADDS the corrected key alongside the original typo key; it never removes or
    overwrites an existing entry, so it cannot introduce a real collision.
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
    for typo_key, good_key in MASTER_KEY_ALIASES.items():
        if typo_key in idx and good_key not in idx:
            idx[good_key] = idx[typo_key]
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


# ── ops-Area -> province fallback (2026-08) ──────────────────────────────────────────────────
# The tape's `account_disb_Booking_Branch_Name` join above still leaves 2,126 of 382,735 accounts
# unmatched. Those rows ALSO carry `account_disb_Area` — an ops-management area, populated on every
# real branch row — and 1,908 of the 2,126 (89.7%) resolve straight to a master province once the
# tape's own trailing ordinal is stripped ("อุทัยธานี 2" -> "อุทัยธานี"). This is a FALLBACK, not a
# substitute for the name join: it is coarser (province only — no district, no branch code), so it
# only ever applies to rows the name join already failed on, and the caller must not invent a
# district or branch row to go with it.
#
# Anything left after stripping the ordinal is either a genuine non-province ops area (head office,
# 'DS - ...' direct-sales desks — no province at all, ~218 accounts) or one of the three areas below
# that name a city/district rather than a province. Those three are the ONLY implicit-looking
# resolutions this function performs, and each is an explicit, verified entry — never a fuzzy rule,
# for the same reason MASTER_KEY_ALIASES above is a fixed dict and not an edit-distance match.
_AREA_ORDINAL = re.compile(r"\s*\d+\s*$")  # trailing ordinal: "ฉะเชิงเทรา 1" -> "ฉะเชิงเทรา"

# Verified to exist verbatim in branches_final.json's `prov` values before being relied on here.
_AREA_ALIAS = {
    "พัทยา": "ชลบุรี",             # Pattaya is a city in Chonburi, not its own province
    "ศรีราชา": "ชลบุรี",           # Si Racha is a district of Chonburi
    "อยุธยา": "พระนครศรีอยุธยา",   # short form of the province name
}


def area_province(area, provinces):
    """Resolve the tape's `account_disb_Area` ops string to a master province name, or None.

    `provinces` is the set of valid province strings (branches_final.json's `prov` values). Returns
    None for: empty/blank Area, any 'DS -' direct-sales office, and any Area that still isn't a
    province after its trailing ordinal is stripped and the explicit `_AREA_ALIAS` table is checked.
    The caller is expected to COUNT those Nones rather than drop them silently — they are either a
    head-office / direct-sales booking or a residual this function deliberately declines to resolve.
    """
    s = str(area or "").strip()
    if not s or s.startswith("DS -") or s.startswith("DS-"):
        return None
    base = _AREA_ORDINAL.sub("", s).strip()
    if base == "กรุงเทพ":                 # Bangkok ops areas are numbered ("กรุงเทพ 1", "กรุงเทพ 2", ...)
        return "กรุงเทพมหานคร"
    if base in _AREA_ALIAS:
        return _AREA_ALIAS[base]
    if base in provinces:
        return base
    return None
