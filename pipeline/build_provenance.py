#!/usr/bin/env python3
"""
build_provenance.py — the DATA ROOM ledger (a provenance census of platform/data)
=================================================================================
Scans every committed `platform/data/*.json` (plus `provinces/index.json`) and
records, for each, whether it carries a provenance stamp (meta.label / meta.source /
meta.provenance / meta.generated_by), what that stamp says, its byte size, and its
top-level count. Emits `platform/data/provenance.json` — a deterministic listing that
powers the "Data room" card on the Command center (#home).

Three verdicts per layer:
  - MEASURED    — carries a stamp with no ESTIMATED/PROXY/SYNTH/EDITORIAL marker.
  - ESTIMATED   — carries a stamp that labels itself an estimate/proxy/synthetic/editorial.
  - UNLABELLED  — no readable meta stamp at all. This is the SHAME BOARD: files that
                  ship a numeric layer with no provenance. Named explicitly so they get fixed.

Top-level JSON arrays (branches.json, provinces/index.json) structurally cannot carry an inline
`meta` block. Their provenance comes from a hand-authored SIDECAR manifest (provenance_sidecar.json,
keyed by relpath); it supplies the same label/source/provenance a real meta block would, so those
layers leave the shame board with no breaking {meta,data} restructure. The sidecar carries only
provenance TEXT (no data), and a `vintage_from` key lets an array layer inherit the live vintage of
the file it ships with (branches.json ← meta.json). Nothing is fabricated — a file is upgraded only
when an honest, committed sidecar entry names it.

The per-province geometry basemaps (`<slug>_roads/_water/_landuse/_rail/_places/_catchment.json`)
are COLLAPSED into one "family" layer each (77 road files -> one "roads" row) so the exec card
stays readable — but any family member lacking a stamp is still counted in the per-FILE shame
tally (`files.unlabelled`) and named in `unlabelled_files`, so collapsing never hides a gap.

HONESTY RULES (sacred):
  - The verdict is read from the file's OWN meta text — nothing is invented. A file with no
    stamp is called UNLABELLED, never silently upgraded. We do NOT fabricate a source for the
    basemap geometry files that lack one; the shame board is the point.
  - Sizes/counts are read from the committed bytes on disk; --check is byte-exact.
  - provenance.json excludes itself from the scan (no self-reference).

    python3 build_provenance.py           # rebuild platform/data/provenance.json
    python3 build_provenance.py --check   # verify the committed file reproduces byte-exact

Deterministic + network-free. Pure function of the committed platform/data tree.
"""
import os, re, json, glob, fnmatch, argparse
from collections import Counter
from datetime import date

# Strict ISO-vintage parser for the freshness readout. Matches ONLY YYYY-MM-DD or YYYY-MM at the
# start of a vintage string (20xx, so a Buddhist-Era year like "2568 (BE)" or a coarse "2026 Q1" /
# "2026M06" label is deliberately NOT parsed — it stays UNDATED rather than mis-aged). A YYYY-MM
# vintage resolves to the 1st of the month (a conservative, oldest-in-period read that never
# understates age). Nothing is invented: only clean, machine-readable dates get an age.
ISO_VINTAGE_RE = re.compile(r"^(20\d\d)-(\d\d)(?:-(\d\d))?(?=$|[^\d])")
STALE_DAYS = 180   # a dated layer this many days behind the freshest layer is flagged stale.

# Layers whose committed vintage is CAPPED by an external source that publishes nothing newer —
# they cannot be made fresher, so counting them in the "stale by neglect" alarm is a false positive
# (a checker that cries wolf is worth less than no checker). They are still shown as the OLDEST dated
# layer (transparent — it IS the oldest data we hold) and listed under freshness.upstream_capped WITH
# the reason, so the exec sees "old because the source stops here", not "old because we forgot to pull".
# Keyed on (file, EXACT vintage): the exemption applies ONLY while the committed vintage still equals
# the known upstream-max, so the day a newer pull lands (the vintage string changes) the key no longer
# matches and normal staleness re-arms automatically. NOT a blanket exempt — it self-corrects.
# See docs/NEXT_STEPS.md §2 (settled 2026-08-04) + pipeline/pull_dlt_fuel.py for the recheck trigger.
UPSTREAM_CAPPED = {
    # DLT dataset_1_1_04 serves a single CSV — stt_car_fuel_at_25690228.csv = 28 Feb 2569 (2026-02-28),
    # the newest COMPLETE fuel-type registered-stock file DLT publishes (verified via the gdcatalog
    # CKAN, HTTP 200 from any IP). Re-pulling is byte-identical until a stt_car_fuel_at_2569MMDD.csv
    # dated after 2569-02-28 lands. Both layers derive from that one file, so both cap on the same date.
    ("vehicle_collateral.json", "2026-02-28"): "DLT dataset_1_1_04 newest complete vintage (28 Feb 2569); no newer CSV published upstream",
    ("ev_penetration.json", "2026-02-28"): "DLT dataset_1_1_04 newest complete vintage (28 Feb 2569); no newer CSV published upstream",
    # vehicle_mix.json takes its STOCK shares from the same dataset_1_1_04 file (28 Feb 2569) as the two
    # above, and its new-registration shares from stat_1_1_01/dataset_stat, which top out at Feb 2569 —
    # the 2569_02 monthly new-reg file is a permanent ~6-row stub, which the builder already excludes
    # (its meta.excluded_stub_months = ["2026-02"]). So its 2026-02-28 vintage is the newest COMPLETE data
    # upstream, capped for the same reason as its two siblings — not stale by neglect (NEXT_STEPS §2).
    ("vehicle_mix.json", "2026-02-28"): "DLT dataset_1_1_04 stock (28 Feb 2569) + stat_1_1_01 new-reg capped at Feb 2569 (2569_02 is a permanent ~6-row stub, excluded); no newer complete CSV published upstream",
    # vehicle_models.json is built from stat_1_1_01_first_regis_vehicles_car; its 2569_02 (Feb) monthly
    # file is a permanent ~6-row stub (1KB vs Jan's 151KB/~1,421 rows, re-verified still-a-stub 4 months
    # after its 2026-03-17 last-modified), so latest_month 2026-01 is the newest REAL month, not a laggard.
    # Re-arms the day a >20-row 2569_03+ file lands (vintage string changes → key no longer matches).
    ("vehicle_models.json", "2026-01"): "DLT stat_1_1_01_first_regis_vehicles_car newest complete monthly vintage (Jan 2569); the 2569_02 file is a permanent ~6-row stub (1KB vs Jan's ~1,421 rows), so 2026-01 is the newest real month upstream",
    # collateral_flow.json is built from DLT dataset_stat_1_008 (car-law registration actions →
    # source-data/vehicle_flow_by_province.json → build_collateral_flow.py). Its newest monthly
    # release is sttt_car_tax_mm_2569_02.csv = Feb 2569 (2026-02); every 2569 file is last-modified
    # 2026-03-17 and there is NO 2569_03+ release (verified live via the gdcatalog CKAN, HTTP 200
    # from this cloud IP, 2026-08-18). So its trailing-12-month window END (2026-02, newly surfaced
    # by the _vintage_of window-array read) is the newest COMPLETE monthly vintage upstream — capped
    # for the same reason as its DLT siblings, not stale by neglect. Re-arms the day a >stub 2569_03+
    # monthly file lands (the window end advances → this key no longer matches, staleness re-arms).
    ("collateral_flow.json", "2026-02"): "DLT dataset_stat_1_008 newest complete monthly release (sttt_car_tax_mm_2569_02 = Feb 2569 = 2026-02); no 2569_03+ file published upstream (verified via gdcatalog CKAN, HTTP 200 any-IP, 2026-08-18)",
}


def _parse_vintage(v):
    """Parse a strict ISO vintage string -> datetime.date, or None if not cleanly ISO."""
    if not isinstance(v, str):
        return None
    m = ISO_VINTAGE_RE.match(v.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    if not (1 <= mo <= 12) or not (1 <= d <= 31):
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
OUT_PATH = os.path.join(DATA, "provenance.json")
INDEX_REL = "provinces/index.json"
SELF = "provenance.json"
# Sidecar provenance manifest. Some layers cannot practically carry an inline `meta` block:
# top-level JSON arrays (branches.json, provinces/index.json) structurally cannot, and the large
# network-pulled geometry families (every <slug>_catchment.json, an object-shaped {buildings,center}
# blob re-pulled from the desktop) would need the puller + app changed to inject one. This companion
# supplies their stamp so they leave the shame board without a breaking restructure. A stamp key is
# either an exact relpath OR a glob pattern (e.g. "*_catchment.json") that stamps a whole family at
# once — see _sidecar_stamp_for. Consumed here only — never fabricates a stamp for a file that has
# no honest, hand-authored entry.
SIDECAR = "provenance_sidecar.json"

# meta keys that count as a provenance stamp (exactly the four named in the mandate).
PROV_KEYS = ("label", "source", "provenance", "generated_by")
# keys whose text we scan to decide MEASURED vs ESTIMATED.
VERDICT_KEYS = ("label", "source", "provenance", "objective", "title", "note",
                "honesty_caveat", "generated_with")
# markers that flip a stamped layer to ESTIMATED (uppercased substring match).
# NOTE: the synthetic-data family is handled separately (see _affirmative_synthetic below),
# NOT as a blunt "SYNTH" substring here. The fragment "SYNTH" false-matched the honest
# MEASURED disclaimers several genuinely-measured layers carry ("no synthesis", "no
# synthetic value is introduced"), mislabelling e.g. the MEASURED competitor census and the
# MEASURED FPO SFI-credit series as ESTIMATED on the Data-room honesty card. Synthetic data
# is still caught — but only when the layer AFFIRMATIVELY declares it (not when it declares
# the opposite). Every genuinely-estimated layer also carries a strong marker below, so real
# coverage is unchanged (verified: only self-declared-MEASURED layers reclassify).
EST_MARKERS = ("ESTIMATED", "PROXY", "INFERRED", "EDITORIAL", "SIMULAT")

# synthetic-data marker, negation-aware. "SYNTHETIC" / "SYNTHESIS" / "SYNTHESIZED" flip a
# layer to ESTIMATED only when AFFIRMATIVE — i.e. the clause it sits in is not a measured
# disclaimer negating it ("no synthesis", "no ... synthetic value", "without synthesis") and
# does not itself assert MEASURED. Clause = a comma/semicolon/sentence-bounded fragment.
_SYNTH_RE = re.compile(r"SYNTHE(?:TIC|SI[SZ]E?D?|SIS)")
_NEG_CUES = ("NO ", "NO-", "NON-", "NON ", "NOT ", "NEVER ", "WITHOUT ")

# per-province geometry basemap families (collapsed to one row each in the card).
FAMILY_KINDS = ("catchment", "roads", "water", "places", "landuse", "rail")
KIND_LABEL = {
    "roads":     "Road-network geometry (basemap)",
    "water":     "Water-polygon geometry (basemap)",
    "landuse":   "Land-use polygon geometry (basemap)",
    "rail":      "Rail-line geometry (basemap)",
    "places":    "Named-place points",
    "catchment": "Building-footprint catchment",
}
CLS_RANK = {"unlabelled": 0, "estimated": 1, "measured": 2}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _nonempty(v):
    """A usable provenance value: a non-blank string, or a container holding one."""
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple)):
        return any(_nonempty(x) for x in v)
    if isinstance(v, dict):
        return any(_nonempty(x) for x in v.values())
    return False


def _trunc(s, n):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _stamp_meta(d):
    """Return the meta dict iff it carries a real provenance stamp, else None."""
    if not isinstance(d, dict):
        return None
    m = d.get("meta")
    if not isinstance(m, dict):
        return None
    if any(_nonempty(m.get(k)) for k in PROV_KEYS):
        return m
    return None


def _affirmative_synthetic(hay):
    """True iff the (uppercased) text AFFIRMATIVELY declares synthetic data — i.e. a
    'synthetic/synthesis/synthesized' occurrence in a clause that is not negating it and
    does not assert MEASURED. Splits on sentence/semicolon/comma boundaries so a nearby
    'no'/'without' that scopes the synthetic word is seen. This is what keeps the honest
    disclaimer 'every point is a real coordinate; no synthesis' from reading as an estimate."""
    for clause in re.split(r"[.;,]", hay):
        if _SYNTH_RE.search(clause):
            if "MEASURED" in clause:
                continue
            if any(cue in clause for cue in _NEG_CUES):
                continue
            return True
    return False


def _verdict_from_meta(m):
    """MEASURED / ESTIMATED from a stamped meta dict (repo convention: estimates are tagged)."""
    parts = []
    for k in VERDICT_KEYS:
        v = m.get(k)
        if v is not None:
            parts.append(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    hay = " ".join(parts).upper()
    if any(mk in hay for mk in EST_MARKERS):
        return "estimated"
    if _affirmative_synthetic(hay):
        return "estimated"
    return "measured"


def _label_of(m):
    """Best human label for the chip's description column."""
    for k in ("label", "source", "provenance", "generated_with", "generated_by", "title"):
        v = m.get(k)
        if isinstance(v, str) and v.strip():
            return _trunc(v, 160)
        if _nonempty(v):
            return _trunc(json.dumps(v, ensure_ascii=False), 160)
    return ""


def _source_of(m):
    for k in ("source", "provenance", "generated_by", "generated_with"):
        v = m.get(k)
        if isinstance(v, str) and v.strip():
            return _trunc(v, 140)
        if _nonempty(v):
            return _trunc(json.dumps(v, ensure_ascii=False), 140)
    return ""


def _vintage_of(m):
    # Priority: an explicit "as-of/updated" stamp first, then a data-observation
    # window end, then a price/registry vintage, then a pull timestamp. These are all
    # real freshness fields the repo's layers actually carry — nothing is invented; a
    # layer with none of them stays vintage-blank (the honest ABSENT state).
    # pico_vintage (pico_competitors), vintage_individual (occupation_income_individual)
    # and promos_pulled_at (rival_pulse — the live rival promo/sentiment watch) were
    # each dropping a real date from the Data-room card because they stamp freshness
    # under a layer-specific key; added below so their vintage surfaces like the rest.
    # snapshot (drought_district — the MODELLED OAE SPEI district-drought layer) is the
    # SPEI reference month (e.g. 2026-06); it is a data-vintage, so it sits with the
    # other observation-window keys, ahead of any pull timestamp.
    # price_asof (peer_scoreboard — the MEASURED SET listed-peer market scoreboard) is the
    # market-price observation date (e.g. 2026-07-17); it is a data-observation vintage
    # like observed_to / price_vintage, so it sits with them, ahead of any pull timestamp
    # (the layer cannot auto-refresh — SET is Akamai/bot-blocked from CI — so surfacing its
    # own observation date is exactly how the exec sees how current the scoreboard is).
    # farmgate_vintage (commodities — the global Pink Sheet × Thai farm-gate × book-exposure
    # board) is the Thai farm-gate price observation date (e.g. 2026-07-24); it is a MEASURED
    # data-observation vintage exactly like price_vintage / price_asof, so it sits with them,
    # ahead of any pull timestamp. The layer carries only this price date + a divergence note,
    # so without it the commodities board showed blank in the Data-room card despite a fresh
    # measured farm-gate vintage.
    # board_vintage (scenarios — the LIVE/stress scenario engine) is the commodity/macro board
    # month (e.g. 2026M06) that its LIVE scenarios draw their MEASURED current driver values
    # from ("Each card shows its vintage"); it is a data-observation vintage exactly like
    # price_vintage / farmgate_vintage, so it sits with them, ahead of any pull timestamp. The
    # layer stamps freshness only under this key, so without it the scenario engine showed
    # blank in the Data-room card despite carrying a real measured board vintage.
    # sentiment_anchor (rival_pulse — the always-on rival app-review + promo watch) is the newest
    # review date IN the pulled data (e.g. 2026-08-03), the MEASURED observation vintage of the
    # sentiment ladder — the layer's fresher half. It sits with the other data-observation keys,
    # AHEAD of promos_pulled_at (the Thai-IP promo-pull timestamp, the layer's staler half): the
    # Data-room card should show when the competitive sentiment was actually observed, not a pull
    # timestamp for the other sub-layer. Only rival_pulse carries this key, so no other layer moves.
    # latest_year_ce (debt_source — NSO household debt-by-source; vehicle_fleet — DLT registered-
    # vehicle stock) is the newest SURVEY/registry year those MEASURED layers report, an INTEGER
    # calendar year (e.g. 2023 / 2025) — their native data-vintage, exactly like vintage_individual's
    # NSO year, just stored as an int. span (farm_household — OAE farm-household cash P&L survey) is
    # the crop-year observation window (e.g. "2562/63..2566/67"), the survey's own BE data-vintage.
    # All three stamp freshness ONLY under these keys, so without them the layers showed blank in the
    # Data-room card despite carrying a real measured vintage. They sit LAST (coarse, non-ISO labels):
    # a proper ISO/observation key always wins, and _parse_vintage leaves each age-blank (a bare year
    # or BE label is never coerced into a false age), matching the vintage_individual precedent.
    # asof_card (rate_board — the MEASURED published rate-card observation date; preferred over the
    # layer's advertised-half asof_ads), anchor_date (collateral_census — the newest auction date the
    # vehicle-age read is measured against), stock_asof (vehicle_mix — the DLT registered-stock snapshot
    # date), latest_month (vehicle_models — the newest DLT first-registration month IN the series),
    # mob_anchor (tape_real / tape_geo_occ / collateral_book — the months-on-book anchor = newest
    # disbursement month IN the real loan tape), and newest_observation_date (rival_watch — the newest
    # promo/ad observation date) are all MEASURED data-observation dates each layer stamps ONLY under
    # its own key, so every one showed BLANK in the Data-room card despite a real fresh vintage. They
    # are strict ISO/month strings, so they sit with the other data-observation keys (AHEAD of any pull
    # timestamp) and _parse_vintage gives each an honest freshness age. vintage_ce (oae_agstats — the
    # OAE crop-year, a bare CE calendar year like 2024) is the latest_year_ce precedent under a second
    # key name; it sits LAST with the other coarse int-year labels (int→str coerced, age-blank, never a
    # false age) and — verified — leaves nso_wage_anchor / vehicle_registry unchanged, since each of
    # those already resolves via an earlier scanned key. Purely additive: no populated layer carries any
    # of these keys under an earlier priority, so only the previously-blank layers gain a vintage.
    # search_vintage (contested_mindshare — the newest share-of-search observation datetime IN the pulled
    # data, e.g. 2026-08-26T04:13Z) is a MEASURED data-observation vintage exactly like
    # newest_observation_date, so it sits with the observation keys (ahead of any pull timestamp);
    # pulled_at (rival_rate_observed — the rate-card read timestamp, e.g. 2026-08-31) is a pull
    # timestamp exactly like pulled_at_utc / pulled, so it sits with them. Each is carried by ONLY its
    # one layer and neither layer has an earlier-priority key, so both were BLANK/undated in the
    # freshness pulse despite a strict-ISO vintage; adding them is purely additive — verified no other
    # populated layer carries either key, so exactly those two layers gain an honest age.
    # retrieved (amphoe_crops / region_debt — OAE amphoe crop-area + NSO region household-debt pulls),
    # cost_ingested (crop_margin — the OAE cost-of-production ingest) and verified (rival_universe — the
    # rival-brand registry cross-check date) are all PULL/INGEST-side timestamps — the moment the source
    # was fetched or last checked, NOT an observation window IN the data. Each of those four layers stamps
    # freshness ONLY under one of these keys and carries NO data-observation vintage, so each showed BLANK
    # in the Data-room card despite a real strict-ISO pull date. They are placed DEAD LAST (after every
    # data-observation key, incl. the coarse int-year / span data-vintages) so any true data vintage
    # always wins over a pull timestamp: this keeps the three OTHER layers carrying `retrieved` untouched
    # — province_lfs (→ `vintage`), drought_district (→ `snapshot`) and, critically, oae_agstats, whose
    # crop-year data-vintage `vintage_ce`=2024 must keep winning (surfacing its recent PULL date would
    # falsely imply the 2024 crop-year data is days-fresh). Purely additive — exactly the four
    # previously-blank pull-only layers gain an honest freshness age; no already-dated layer moves.
    for k in ("updated", "vintage", "as_of", "updated_to",
              "observed_to", "price_vintage", "price_asof", "farmgate_vintage", "board_vintage",
              "asof_card", "anchor_date", "stock_asof", "latest_month", "mob_anchor",
              "newest_observation_date", "search_vintage",
              "sentiment_anchor", "snapshot", "pico_vintage", "vintage_individual", "pulled_at_utc",
              "pulled_at", "pulled", "promos_pulled_at", "latest_year_ce", "vintage_ce", "span",
              "retrieved", "cost_ingested", "verified"):
        v = m.get(k)
        if isinstance(v, str) and v.strip():
            return _trunc(v, 24)
        if isinstance(v, int) and k in ("latest_year_ce", "vintage_ce"):
            return str(v)
    # window (collateral_flow — the DLT car-law registration-flow / used-collateral pulse): this
    # layer stamps its data-observation vintage ONLY as a two-element [start, end] month array
    # (meta.window, e.g. ["2025-03","2026-02"]), never a scalar key, so the scan above never saw it
    # and the layer showed BLANK in the Data-room card despite carrying a real MEASURED observation
    # vintage. The trailing-12-month window END is the freshness date (the newest month IN the
    # series) — a strict ISO month that reads like observed_to. Placed last so any scalar/ISO key
    # above always wins; verified only collateral_flow carries a window array with no scalar vintage
    # key, so this is purely additive — no populated layer moves.
    w = m.get("window")
    if isinstance(w, (list, tuple)) and len(w) >= 2 and isinstance(w[-1], str) and w[-1].strip():
        return _trunc(w[-1], 24)
    return ""


def _top_count(d):
    """(count, count_of): the longest top-level list, or the root list length."""
    if isinstance(d, list):
        return len(d), "rows"
    if isinstance(d, dict):
        best_k, best_n = "", -1
        for k, v in d.items():
            if k in ("meta", "_meta"):
                continue
            if isinstance(v, list) and len(v) > best_n:
                best_k, best_n = k, len(v)
        if best_n >= 0:
            return best_n, best_k
    return 0, ""


def _load_sidecar():
    """Sidecar provenance stamps for array-shaped layers: {rel -> stamp dict}. Empty if absent."""
    path = os.path.join(DATA, SIDECAR)
    if not os.path.exists(path):
        return {}
    try:
        d = _load(path)
    except Exception:
        return {}
    stamps = d.get("stamps")
    return stamps if isinstance(stamps, dict) else {}


def _resolve_sidecar_stamp(stamp):
    """Prepare a sidecar stamp for scanning. If it carries `vintage_from`, resolve the referenced
    file's live vintage so an array layer inherits the exact freshness of the file it ships with
    (e.g. branches.json shares meta.json's vintage — both projected in one derive.py run). Reads
    committed bytes only; never invents a date."""
    if not isinstance(stamp, dict):
        return None
    ref = stamp.get("vintage_from")
    if isinstance(ref, str) and ref.strip():
        try:
            rm = _load(os.path.join(DATA, ref.replace("/", os.sep))).get("meta")
        except Exception:
            rm = None
        v = _vintage_of(rm) if isinstance(rm, dict) else ""
        if v:
            stamp = {**stamp, "vintage": v}
    return stamp


def _sidecar_stamp_for(rel, sidecar):
    """The sidecar stamp that applies to `rel`, or None. An exact relpath key wins; otherwise the
    first glob-pattern key (one containing '*', matched with fnmatch, sorted for determinism) that
    matches. This lets a whole geometry family share ONE stamp (e.g. "*_catchment.json" covers all
    77 <slug>_catchment.json files) instead of 77 per-file entries. Only a stamp that carries a real
    PROV_KEY is honoured — an empty entry never upgrades a file."""
    def _ok(s):
        return isinstance(s, dict) and any(_nonempty(s.get(k)) for k in PROV_KEYS)
    if rel in sidecar and _ok(sidecar[rel]):
        return sidecar[rel]
    for pat in sorted(k for k in sidecar if "*" in k):
        if fnmatch.fnmatch(rel, pat) and _ok(sidecar[pat]):
            return sidecar[pat]
    return None


def _scan_file(rel, sidecar=None):
    """Read one file -> (verdict, meta_or_None, bytes, count, count_of).

    A layer that cannot practically carry an inline meta block (a top-level JSON array, or a large
    network-pulled geometry blob like <slug>_catchment.json) falls back to a hand-authored sidecar
    stamp — matched by exact relpath or by a family glob (see _sidecar_stamp_for) — so it leaves the
    shame board without a breaking restructure. Only an honest, committed sidecar entry upgrades a
    file — nothing is fabricated."""
    path = os.path.join(DATA, rel.replace("/", os.sep))
    size = os.path.getsize(path)
    try:
        d = _load(path)
    except Exception:
        return "unlabelled", None, size, 0, ""
    m = _stamp_meta(d)
    count, count_of = _top_count(d)
    if m is None and sidecar:
        stamp = _sidecar_stamp_for(rel, sidecar)
        if stamp is not None:
            m = _resolve_sidecar_stamp(stamp)
    if m is None:
        return "unlabelled", None, size, count, count_of
    return _verdict_from_meta(m), m, size, count, count_of


def build():
    slugs = set(p.get("slug") for p in _load(os.path.join(DATA, INDEX_REL)))
    sidecar = _load_sidecar()   # hand-authored stamps for array-shaped layers (branches / index)

    # ---- partition top-level *.json into standalone files vs geometry families ----
    fam_re = re.compile(r"^(?P<slug>.+)_(?P<kind>%s)$" % "|".join(FAMILY_KINDS))
    standalone = []          # rel paths
    families = {}            # kind -> [rel, ...]
    for path in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        rel = os.path.basename(path)
        if rel == SELF:
            continue
        stem = rel[:-5]
        mm = fam_re.match(stem)
        if mm and mm.group("slug") in slugs:
            families.setdefault(mm.group("kind"), []).append(rel)
        else:
            standalone.append(rel)
    standalone.append(INDEX_REL)   # scan the province index too (mandate)

    layers = []
    unlabelled_files = []

    # ---- standalone layers (one file = one layer) ----
    for rel in standalone:
        cls, m, size, count, count_of = _scan_file(rel, sidecar)
        if cls == "unlabelled":
            unlabelled_files.append(rel)
        layers.append({
            "file": rel, "family": False, "cls": cls,
            "label": _label_of(m) if m else "",
            "source": _source_of(m) if m else "",
            "vintage": _vintage_of(m) if m else "",
            "bytes": size, "count": count, "count_of": count_of,
            "n_files": 1, "n_unlabelled": 0 if cls != "unlabelled" else 1,
        })

    # ---- geometry families (many files = one collapsed layer) ----
    for kind in sorted(families):
        members = sorted(families[kind])
        tot_bytes = 0
        tot_count = 0
        n_unlab = 0
        member_cls = []
        srcs = Counter()
        vints = Counter()
        for rel in members:
            cls, m, size, count, count_of = _scan_file(rel, sidecar)
            tot_bytes += size
            tot_count += count
            member_cls.append(cls)
            if cls == "unlabelled":
                n_unlab += 1
                unlabelled_files.append(rel)
            else:
                s = _source_of(m)
                if s:
                    srcs[s] += 1
                v = _vintage_of(m)
                if v:
                    vints[v] += 1
        labelled = [c for c in member_cls if c != "unlabelled"]
        if not labelled:
            fam_cls = "unlabelled"
        elif "estimated" in labelled:
            fam_cls = "estimated"
        else:
            fam_cls = "measured"
        # source/vintage: the most common member value (deterministic tie-break: alphabetical).
        src = sorted(srcs.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if srcs else ""
        vint = sorted(vints.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if vints else ""
        layers.append({
            "file": kind, "family": True, "cls": fam_cls,
            "label": KIND_LABEL.get(kind, kind),
            "source": src, "vintage": vint,
            "bytes": tot_bytes, "count": tot_count, "count_of": "features",
            "n_files": len(members), "n_unlabelled": n_unlab,
        })

    # shame board leads (unlabelled), then estimated, then measured; stable by file within.
    layers.sort(key=lambda L: (CLS_RANK[L["cls"]], L["file"]))
    unlabelled_files = sorted(unlabelled_files)

    # ---- FRESHNESS readout (deterministic, no wall-clock) ------------------------------------
    # Each layer's age is measured against the FRESHEST dated layer in the tree — a purely internal
    # reference (the newest committed vintage), so the number never depends on when the build runs.
    # It answers the exec question "how far behind our newest data is this layer?" Only layers that
    # carry a clean ISO vintage (YYYY-MM / YYYY-MM-DD) get an age; the rest stay age_days=null (the
    # honest UNDATED state — a coarse or Buddhist-Era label is never coerced into a false age).
    dated = []
    for L in layers:
        dt = _parse_vintage(L.get("vintage", ""))
        L["age_days"] = None
        if dt is not None:
            dated.append((dt, L))
    freshness = None
    if dated:
        ref = max(dt for dt, _ in dated)
        for dt, L in dated:
            L["age_days"] = (ref - dt).days
        entries = sorted(
            ({"file": L["file"], "vintage": L["vintage"], "age_days": (ref - dt).days}
             for dt, L in dated),
            key=lambda e: (e["age_days"], e["file"]))
        # A layer pinned to its source's newest-available vintage cannot be refreshed, so it must not
        # trip the neglect alarm — exclude it from `stale` (keyed on the exact committed vintage, so a
        # newer pull re-arms it). It stays eligible as `oldest` and is named in `upstream_capped`.
        capped = [e for e in entries if (e["file"], e["vintage"]) in UPSTREAM_CAPPED]
        stale = [e for e in entries
                 if e["age_days"] > STALE_DAYS and (e["file"], e["vintage"]) not in UPSTREAM_CAPPED]
        freshness = {
            "reference_date": ref.isoformat(),
            "reference_note": ("age = days behind the freshest dated layer in the committed tree "
                               "(deterministic; no wall-clock read). The freshest vintage can be a "
                               "forward-looking observation window — e.g. collateral_census's "
                               "anchor_date is the newest auction date IN the data, which may be a "
                               "scheduled future auction — so a positive age means 'behind our newest "
                               "data', not necessarily 'behind today'. null age = no machine-readable "
                               "ISO vintage — the honest undated state, never a coerced date."),
            "stale_over_days": STALE_DAYS,
            "n_dated": len(entries),
            "n_undated": len(layers) - len(entries),
            "freshest": entries[0],
            "oldest": entries[-1],
            "stale": sorted(stale, key=lambda e: (-e["age_days"], e["file"])),
            # Old because the upstream source stops here, NOT because a pull was missed. Excluded from
            # `stale` above; surfaced here (with the reason) so the age is honest, not laundered away.
            "upstream_capped": sorted(
                ({**e, "reason": UPSTREAM_CAPPED[(e["file"], e["vintage"])]} for e in capped),
                key=lambda e: (-e["age_days"], e["file"])),
        }

    n_files = sum(L["n_files"] for L in layers)
    n_files_unlab = len(unlabelled_files)
    counts = {
        "layers": len(layers),
        "measured": sum(1 for L in layers if L["cls"] == "measured"),
        "estimated": sum(1 for L in layers if L["cls"] == "estimated"),
        "unlabelled": sum(1 for L in layers if L["cls"] == "unlabelled"),
    }
    meta = {
        "generated_by": "pipeline/build_provenance.py (deterministic, network-free, --check)",
        "source": ("Provenance census of platform/data/*.json (+ provinces/index.json). For each "
                   "layer it reads the file's OWN meta stamp (label/source/provenance/generated_by), "
                   "byte size and top-level count. Nothing is invented."),
        "provenance": "measured (a listing of committed files); the per-layer verdict is read from each file's own meta text",
        "provenance_note": ("MEASURED / ESTIMATED are read from each layer's self-declared meta. "
                            "UNLABELLED = no readable meta stamp at all — the shame board; those files "
                            "ship a numeric layer with no provenance and should get a meta block. "
                            "Per-province geometry basemaps are collapsed into one 'family' row each, "
                            "but any unstamped member is still counted in files.unlabelled and named in "
                            "unlabelled_files, so collapsing hides no gap. Top-level JSON arrays "
                            "(branches.json, provinces/index.json) cannot carry an inline meta block; "
                            "their stamp comes from the hand-authored provenance_sidecar.json manifest "
                            "(provenance text only, no data) — honest by mechanism, not un-sourced."),
    }
    return {
        "meta": meta,
        "counts": counts,
        "files": {"total": n_files, "unlabelled": n_files_unlab,
                  "labelled": n_files - n_files_unlab},
        "freshness": freshness,
        "unlabelled_files": unlabelled_files,
        "layers": layers,
    }


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def run(check=False):
    text = canonical(build())
    if check:
        if not os.path.exists(OUT_PATH):
            print("DRIFT: platform/data/provenance.json missing — run build_provenance.py")
            return 1
        with open(OUT_PATH, encoding="utf-8") as f:
            if f.read() != text:
                print("DRIFT: platform/data/provenance.json differs from a fresh build")
                return 1
        print("OK: provenance.json reproduces exactly")
        return 0
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    d = json.loads(text)
    c = d["counts"]
    print("provenance.json written — %d layers (%d measured / %d estimated / %d unlabelled) · "
          "%d files, %d without a meta stamp"
          % (c["layers"], c["measured"], c["estimated"], c["unlabelled"],
             d["files"]["total"], d["files"]["unlabelled"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Data-room provenance census for #home")
    ap.add_argument("--check", action="store_true",
                    help="verify committed provenance.json reproduces exactly; exit 1 on drift")
    raise SystemExit(run(check=ap.parse_args().check))
