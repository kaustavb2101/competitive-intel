"""
build_commodities.py — the commodities board upgrade (TMLI-convergence move 4, owner ask 2026-07-25)

TMLI's commodities page was concise and readable; CI has richer data but scattered. This unifies it
into ONE board layer with a "who's exposed" drill:
  · GLOBAL price move  — World Bank Pink Sheet YoY (commodity_board.json)
  · LOCAL price move    — Thai farm-gate YoY (farmgate_prices.json) — the domestic cross-check
  · DIVERGENCE          — local − global (where the Thai farmer's reality parts from the world price)
  · WHO'S EXPOSED       — provinces growing the crop (planted area) and the AutoX book accounts
                          sitting in them, weighted by crop share → press a commodity, see the book.

  in : source-data/commodity_board.json    MEASURED — Pink Sheet YoY (global)
       source-data/farmgate_prices.json    MEASURED — Thai farm-gate daily price + YoY (local)
       platform/data/fuel_prices.json      MEASURED — retail diesel (the cost line)
       source-data/crop_prov_area.json      MEASURED — rice/rubber/oilpalm planted area per province
       platform/data/province_cropland.json MEASURED — DOAE farmer registry, adds cassava + maize
       platform/data/crop_landuse.json      MODELLED  — SPAM 2010, the only sugarcane area we hold
       platform/data/impact_cards.json      book accounts per province
       platform/data/income_impact.json     per-province crop mix (area shares)
  out: platform/data/commodities.json       (--check: byte-exact reproduce)

Deterministic + network-free. Exposure is book-FOOTPRINT weighted by crop area (an ESTIMATE of which
accounts sit under each crop — labelled).

AREA SOURCES ARE NOT INTERCHANGEABLE — this is why the registry below pins one source per crop
rather than preferring the newest everywhere:
  · crop_prov_area.json (rice/rubber/oilpalm) is a planted-area census.
  · province_cropland.json is the DOAE farmer REGISTRY. Against the census it reads rice 1.10x but
    rubber 0.46x and oilpalm 0.58x, because most rubber smallholders register with RAOT and most
    palm growers with their mill, not DOAE. So it is used ONLY for cassava and maize, where nothing
    else carries province area at all. Its absolute hectares are not comparable across crops; what
    we take from it is the BELT RANKING (which provinces grow it), which survives partial
    registration as long as under-registration is not regionally biased.
  · Sugarcane is absent from DOAE by construction — cane growers register with the OCSB, not DOAE
    (province_cropland.json says so in its own provenance line). Until 2026-08-01 the only cane area
    held anywhere here was SPAM 2010, a MODELLED 5-arcmin raster, and there was no current Thai cane
    price at all, so Sugar was the one board row with a falling WORLD price and no way to name who
    in Thailand carries it. The OCSB pull (pipeline/ingest_ocsb_cane.py) closes BOTH: source-data/
    ocsb_cane.json now carries MEASURED per-province cane area for production year 2565/66 and the
    announced cane price series 2020..2025. The modelled raster it replaces understated the national
    belt by ~1.7x (1.06m ha vs the 1.82m ha OCSB measures), which is why the sugar belt looked thin.
    SPAM stays in AREA_SOURCES as the documented fallback but no board row points at it any more.
"""
import json
import os
import sys
from datetime import date

from lib.regionmap import REGION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "platform", "data")
S = os.path.join(ROOT, "source-data")
OUT = os.path.join(P, "commodities.json")

HA_TO_RAI = 6.25          # DOAE and SPAM publish hectares; the board reports rai, the Thai unit.

# board label → farm-gate key (Thai local price cross-check)
BOARD_TO_FARMGATE = {"Rice": "rice", "Rubber": "rubber", "Palm oil": "oilpalm",
                     "Maize": "maize", "Cassava": "cassava"}

# board label → (area source id, key inside that source). Pinned per crop on purpose; see the
# module docstring for why the newest source is NOT preferred everywhere.
BOARD_TO_AREA = {"Rice": ("census", "rice"), "Rubber": ("census", "rubber"),
                 "Palm oil": ("census", "oilpalm"),
                 "Cassava": ("doae", "cassava"), "Maize": ("doae", "maize"),
                 # Coconut and pineapple are the two steepest FALLING Thai prices on the board.
                 # ingest_doae.py now maps all 19 registry crops instead of 5, so they finally have
                 # a belt — a falling price you can put provinces and accounts behind.
                 "Coconut": ("doae", "coconut"), "Pineapple": ("doae", "pineapple"),
                 # Sugar moved off the SPAM-2010 raster onto OCSB's own measured returns on
                 # 2026-08-01. Cane is the ONE crop where the pinned source is not a choice between
                 # census and registry — OCSB is the register of record for every cane grower.
                 "Sugar": ("ocsb", "sugarcane"),
                 # Lime, added 2026-08-02. Not in the DOAE farmer registry (18 crops, no มะนาว) or
                 # any other province source held here — the only belt that exists for it anywhere
                 # is DOAE's own 2019 "รต." crop-situation PDF series (ingest_doae_fruit.py). Old
                 # vintage, but the alternative was no belt at all for a row that already prices.
                 "Lime": ("doae_rt", "lime"),
                 # NON-CROP ROWS, added 2026-08-02 (owner: "i want the 'book exposed' data for all
                 # the commods meaning you need to find out where the belts of these commods are").
                 # A belt does not have to be planted area — it has to be the measured geography of
                 # the livelihood the price reaches. Each of these pins a different measure and the
                 # row says which, rather than calling everything "planted area".
                 "White shrimp": ("dof", "shrimp_marine"),
                 "Fishmeal": ("dof", "fishmeal"),
                 # Both timber rows point at the SAME belt on purpose: the plantation register is
                 # where trees are legally grown for harvest, and logs and sawnwood are the same
                 # standing timber at two points of the same chain. Reserve forest (ป่าสงวนแห่งชาติ)
                 # was rejected as the source — protected area is where logging does NOT happen, so
                 # it would have inverted the signal.
                 "Logs": ("rfd", "plantation"),
                 "Sawnwood": ("rfd", "plantation"),
                 # Livestock, added 2026-08-02. DLD runs its own CKAN (dld.gdcatalog.go.th) which is
                 # NOT geoblocked — the same pattern as DIW and DLT — so these are structured CSV
                 # exports at 77/77 provinces, not OCR'd PDFs. Belt measure is herd/flock size.
                 "Pork": ("dld", "pig"),
                 "Chicken": ("dld", "chicken_all"),
                 "Beef": ("dld", "cattle_beef"),
                 # EGGS rides the SAME combined chicken flock as Chicken, on the owner's call
                 # ("for eggs, chicken or whatever group is fine for a belt"). DLD's national
                 # release reports จำนวนไก่ as ALL chicken types combined — no layer-vs-broiler
                 # split at province grain — so this belt says "where chickens are", not "where
                 # LAYING chickens are". The two overlap heavily (ลพบุรี/ชลบุรี/นครนายก run both)
                 # but they are not identical, and the caveat is carried on the row.
                 "Eggs": ("dld", "chicken_all")}

AREA_SOURCES = {
    "census": {
        "provenance": "MEASURED",
        "source": "province planted-area census (source-data/crop_prov_area.json)",
        "note": "Planted-area census — the fullest province count held for these three crops.",
    },
    "doae": {
        "provenance": "MEASURED",
        "source": "DOAE farmer registry 2568/2025 (platform/data/province_cropland.json)",
        "note": "Farmer-REGISTRATION area, not a full census: against the census it reads rubber "
                "0.46x and oilpalm 0.58x, so absolute area is not comparable across crops. What is "
                "used here is the belt RANKING, which survives partial registration.",
    },
    "ocsb": {
        "provenance": "MEASURED",
        "source": "OCSB cane area, production year 2565/66 (source-data/ocsb_cane.json)",
        "note": "Office of the Cane and Sugar Board administrative returns — mills report every "
                "delivery, so this is a near-complete count rather than a survey or a registry "
                "sample. It is the register of record for Thai cane: growers register with OCSB, "
                "not DOAE, which is why cane is absent from the farmer registry entirely.",
    },
    "doae_rt": {
        "provenance": "MEASURED",
        "source": "DOAE annual crop-situation ('รต.') report, year 2562 BE / 2019 CE "
                  "(source-data/doae_fruit_area.json)",
        "measure": {"lime": "planted area"},
        "unit": {"lime": "rai"},
        "note": "2019 vintage — seven years old, prominently so. Used anyway because it is the "
                "ONLY province-grain lime source that exists anywhere: absent from the DOAE "
                "farmer registry, the planted-area census, SPAM 2010 and OCSB alike, confirmed "
                "across four independent searches. The DOAE site's own รต. series stops at this "
                "year — year64/65/67 404, and later years carry an unrelated document set or sit "
                "behind a login. An old belt names the same growing region a fresh one would; it "
                "is the account count next to it that would go stale first, and there is no newer "
                "figure to replace it with.",
    },
    # --- non-crop belts (2026-08-02) ---------------------------------------------------------
    # These two do NOT measure planted area, so each carries its own `measure` + `unit`, and the
    # exposure block quotes them instead of hardcoding "planted area". Calling a shrimp pond or a
    # tonne of fishmeal "planted area" would be a mislabel, and every number on this site has to
    # say what it actually is.
    "dof": {
        "provenance": "MEASURED",
        "source": "Department of Fisheries aquaculture + fishmeal releases, newest year in the "
                  "data (source-data/livelihood_area.json)",
        "measure": {"shrimp_marine": "marine-shrimp farm area",
                    "fishmeal": "fishmeal output"},
        "unit": {"shrimp_marine": "rai", "fishmeal": "tonnes"},
        "note": "DOF publishes farms, area, volume and value per province per year. Marine shrimp "
                "uses FARM AREA, the direct analogue of planted area. Fishmeal has no farm area to "
                "report — it is a processing industry — so its belt is built on OUTPUT VOLUME, and "
                "the borrower behind a fishmeal price is the operator and the boats supplying it, "
                "not a grower.",
    },
    "rfd": {
        "provenance": "MEASURED",
        "source": "Royal Forest Department register of commercial forest plantations under the "
                  "Forest Plantation Act B.E. 2535 (source-data/livelihood_area.json)",
        "measure": {"plantation": "registered plantation area"},
        "unit": {"plantation": "rai"},
        "note": "Land registered for commercial timber growing — where trees are legally grown to "
                "be harvested, across all 77 provinces. Deliberately NOT the reserve-forest layer "
                "(ป่าสงวนแห่งชาติ, 66 provinces): protected forest is where logging does not "
                "happen, so ranking provinces by it would have inverted the signal.",
    },
    "dld": {
        "provenance": "MEASURED",
        "source": "Department of Livestock Development province census, CE 2025 "
                  "(source-data/livestock_province.json, via dld.gdcatalog.go.th)",
        "measure": {"pig": "pig keepers", "chicken_all": "chicken keepers",
                    "cattle_beef": "beef-cattle keepers"},
        "unit": {"pig": "farms", "chicken_all": "farms", "cattle_beef": "farms"},
        "note": "Counted per province by the provincial livestock offices, all 77 covered. "
                "Structured CSV from DLD's own catalog — no OCR, so no digit-transcription risk. "
                "The belt ranks on KEEPERS, not on animals: DLD publishes both, and for a lender "
                "the keeper count is the borrower population. Head counts point at the industrial "
                "provinces — ลพบุรี holds 58.7m chickens across 18,916 keepers, 3,106 birds each, "
                "which is contract production, not a customer base — so a head-ranked belt would "
                "aim at exactly the provinces that do not borrow. Head is carried in the source "
                "file for reference: nationally 12.2m pigs, 517m chickens, 9.5m beef cattle. "
                "CAVEAT on eggs: DLD reports จำนวนไก่ as ALL chicken types combined, so the egg row "
                "and the chicken row share one belt — it locates where chicken keepers are, not "
                "where LAYER keepers are. The layer-vs-broiler split exists only in nine "
                "regional-office publications on unstable subsites.",
    },
    "spam": {
        "provenance": "MODELLED",
        "source": "IFPRI/MapSPAM 2010 v2.0 (platform/data/crop_landuse.json)",
        "note": "MODELLED spatial disaggregation on a 2010 base — 16 years old. RETIRED as a board "
                "source on 2026-08-01 when the OCSB pull landed: it was carrying sugarcane, and "
                "against OCSB's measured returns it understated the national cane belt by ~1.7x. "
                "Kept here as documentation of what the sugar belt used to be built on.",
    },
}

# Thai crops carrying no World Bank Pink Sheet series, so they can never reach the board from
# commodity_board.json. Cassava is Thailand's largest crop export book and its farm-gate is the
# biggest move this pipeline measures; leaving it off the board hid that move completely.
LOCAL_ONLY = [
    {"lab": "Cassava", "seg": "Crops", "reg": "Isan·N·E",
     "note": "no World Bank series — Thai farm-gate only"},
]

# NABC categories the Pink Sheet cannot cover and build_farmgate_prices.py deliberately drops.
# That script keeps RAW CROP farm-gate forms only (paddy, fresh root, whole bunch, raw sheet), which
# is right for what it is, but it meant the board carried five Thai prices out of the thirteen NABC
# publishes — and every one of the eight it dropped that still has a live YoY is a livestock,
# fishery or orchard series. Six of them are FALLING, so a board whose only faller was a world sugar
# price was reading "everything is up" while measured Thai livestock and fishery prices were down.
NABC_ROWS = [
    ("มะพร้าว", {"lab": "Coconut", "seg": "Crops", "reg": "S·E"}),
    ("สับปะรดโรงงาน", {"lab": "Pineapple", "seg": "Crops", "reg": "E·W·N"}),
    ("มะนาว", {"lab": "Lime", "seg": "Crops", "reg": "C·W"}),
    ("สุกร", {"lab": "Pork", "seg": "Livestock", "reg": "C·W·E"}),
    ("ไข่ไก่", {"lab": "Eggs", "seg": "Livestock", "reg": "C·E"}),
    ("กุ้งขาว", {"lab": "White shrimp", "seg": "Fisheries", "reg": "S·E coast"}),
]
# Pink Sheet rows that gain a Thai cross-check from NABC rather than from farmgate_prices.
BOARD_TO_NABC = {"Chicken": "ไก่"}

# A NABC series is dropped when it carries no YoY, or when its last price is this far behind the
# newest price in the same feed. Longan is the live case: it last priced 2025-09-05 with a null YoY,
# and showing it as a current signal would be wrong.
NABC_STALE_DAYS = 120


def load(*path):
    return json.load(open(os.path.join(*path), encoding="utf-8"))


def nabc_locals(nabc):
    """category_th → price dict, dropping any series with no YoY or a stale last price.

    The staleness anchor is the NEWEST latest_date IN THE FEED, never the wall clock, so the build
    reproduces byte-for-byte from the committed file alone however long after the pull it is run.
    Returns (kept, dropped_reasons) — the drops are published in meta rather than swallowed, so an
    absent commodity reads as "we dropped it and here is why", not as "the market went quiet".
    """
    cats = nabc.get("categories") or {}
    dates = [c.get("latest_date") for c in cats.values() if c.get("latest_date")]
    anchor = max(dates) if dates else None
    kept, dropped = {}, []
    for k in sorted(cats):                       # sorted: no dependence on dict insertion order
        c = cats[k]
        d, y = c.get("latest_date"), c.get("yoy")
        if y is None:
            dropped.append("%s — no year-ago comparison in the feed" % k)
            continue
        if anchor and d:
            lag = (date.fromisoformat(anchor) - date.fromisoformat(d)).days
            if lag > NABC_STALE_DAYS:
                dropped.append("%s — last priced %s, %d days behind the feed" % (k, d, lag))
                continue
        kept[k] = c
    return kept, dropped


def area_tables(area_census):
    """Province → rai, per area-source id. Thai province names throughout (the book's join key)."""
    census = {crop: {pv: a for pv, a in tbl.items() if pv in REGION}
              for crop, tbl in area_census.items()}

    doae = {}
    for pv in load(P, "province_cropland.json")["provinces"].values():
        th = pv.get("th")
        if th not in REGION:
            continue
        for crop, ha in (pv.get("crops") or {}).items():
            if isinstance(ha, (int, float)) and ha > 0:
                doae.setdefault(crop, {})[th] = ha * HA_TO_RAI

    spam = {}
    for pv in load(P, "crop_landuse.json")["provinces"]:
        th = pv.get("province_th")
        if th not in REGION:
            continue
        for crop, ha in (pv.get("crop_area_ha") or {}).items():
            if isinstance(ha, (int, float)) and ha > 0:
                spam.setdefault(crop, {})[th] = ha * HA_TO_RAI

    # OCSB is already per-province rai in Thai province names, so unlike the other three it needs
    # no ha→rai conversion — only the same canonical-province filter.
    cane = {pv: rec["area_rai"] for pv, rec in load(S, "ocsb_cane.json")["provinces"].items()
            if pv in REGION and rec.get("area_rai", 0) > 0}

    # Fisheries + forestry (livelihood_area.json, written by the owner-side ingest). Absent file =
    # those board rows keep the empty belt they have today, rather than the build failing — the
    # ingest reads a gitignored harvest, so a fresh clone legitimately will not have it yet.
    dof, rfd = {}, {}
    try:
        liv = load(S, "livelihood_area.json")
    except (FileNotFoundError, ValueError):
        liv = {}
    for grp, dest in (("fisheries", dof), ("forestry", rfd)):
        for key, lay in (liv.get(grp) or {}).items():
            tbl = {pv: v for pv, v in (lay.get("provinces") or {}).items()
                   if pv in REGION and isinstance(v, (int, float)) and v > 0}
            if tbl:
                dest[key] = tbl

    # Livestock (livestock_province.json). Same absent-file contract as above. Shape differs from
    # livelihood_area.json: one flat {"species": {key: {provinces: ..., farms: ...}}} block.
    #
    # The belt ranks on FARMS, not on head, and that is a deliberate reversal of what the other
    # sources do. Everywhere else the area measure and the borrower population move together — a
    # province with more rai of rubber has more rubber farmers. Livestock breaks that: ลพบุรี runs
    # 58.7m chickens across 18,916 keepers (3,106 birds each — contract complexes), while
    # นครราชสีมา runs 24.7m across 155,188 keepers (159 each — backyard flocks). Ranking on head
    # would point the belt at the industrial provinces, which are precisely the ones that do not
    # borrow from us. Only 15 provinces are common to both belts for chicken, so the choice is
    # material rather than cosmetic. Beef is nearly indifferent (5-8 head per keeper nationwide).
    dld = {}
    try:
        lv = load(S, "livestock_province.json")
    except (FileNotFoundError, ValueError):
        lv = {}
    for key, lay in (lv.get("species") or {}).items():
        tbl = {pv: v for pv, v in (lay.get("farms") or {}).items()
               if pv in REGION and isinstance(v, (int, float)) and v > 0}
        if tbl:
            dld[key] = tbl

    # DOAE รต. crop-situation series (doae_fruit_area.json, owner-side ingest_doae_fruit.py). Same
    # absent-file contract as dof/rfd/dld above — a fresh clone without the file just keeps Lime's
    # belt empty rather than failing the build.
    doae_rt = {}
    try:
        frt = load(S, "doae_fruit_area.json")
    except (FileNotFoundError, ValueError):
        frt = {}
    for key, lay in (frt.get("crops") or {}).items():
        tbl = {pv: v for pv, v in (lay.get("provinces") or {}).items()
               if pv in REGION and isinstance(v, (int, float)) and v > 0}
        if tbl:
            doae_rt[key] = tbl

    return {"census": census, "doae": doae, "spam": spam, "ocsb": {"sugarcane": cane},
            "dof": dof, "rfd": rfd, "dld": dld, "doae_rt": doae_rt}


def ocsb_price():
    """The announced cane price, shaped like a farm-gate record so the board row reads it uniformly.

    It is NOT a market quote: OCSB announces one national price per season, so n_markets is left
    absent rather than faked as 1 — the UI's thin-quote caveat would misdescribe an administered
    price. Sugarcane reaches the board through neither farmgate_prices.json (raw-crop forms only)
    nor NABC (daily market survey), which is why it needs its own small adapter.
    """
    p = load(S, "ocsb_cane.json").get("price")
    if not p or p.get("yoy") is None:
        return None
    return {"price": p["latest_price"], "unit": p["unit"], "yoy": p["yoy"],
            "latest_date": str(p["latest_year_ce"]), "n_markets": None,
            "product": "อ้อยโรงงาน — announced cane price (~10 CCS)"}


def build():
    board = load(S, "commodity_board.json")
    fg = load(S, "farmgate_prices.json")
    fgc = fg.get("commodities", {})
    fuel = load(P, "fuel_prices.json")
    area = load(S, "crop_prov_area.json")
    cards = load(P, "impact_cards.json")
    income = load(P, "income_impact.json")

    acc = {pv: p["accounts"] for pv, p in cards["provinces"].items()}
    cmix = {pv: p["crop_mix"] for pv, p in income["provinces"].items()}
    areas = area_tables(area)
    # Per-province MEASURED farm income base (NSO SES, ฿/month for the Agriculture occupation) and
    # the SAME crop sensitivity the income engine uses, so a crop-specific number computed here can
    # never disagree with income_impact.json's own arithmetic.
    agri_base = {pv: ((p.get("occ") or {}).get("Agriculture") or {}).get("income")
                 for pv, p in income["provinces"].items()}
    crop_sens = (((income.get("meta") or {}).get("sensitivity") or {})
                 .get("Agriculture") or {}).get("crop")

    ocsb = ocsb_price()
    nabc = load(S, "nabc_prices.json")
    nkept, ndropped = nabc_locals(nabc)
    extra = [dict(spec, _nabc=cat) for cat, spec in NABC_ROWS if cat in nkept]

    items = []
    for it in list(board) + LOCAL_ONLY + extra:
        lab = it["lab"]
        ncat = it.get("_nabc") or BOARD_TO_NABC.get(lab)
        fgkey = BOARD_TO_FARMGATE.get(lab)
        # farmgate_prices is the curated raw-crop layer; NABC covers everything else it drops; OCSB
        # covers sugarcane, which neither of them can see (administered price, own regulator).
        local = ((fgc.get(fgkey) if fgkey else None) or (nkept.get(ncat) if ncat else None)
                 or (ocsb if lab == "Sugar" else None))
        local_yoy = local.get("yoy") if local else None
        # LOCAL_ONLY rows have no Pink Sheet series at all, so global_yoy is genuinely absent
        # (rendered "n/a") rather than zero, and their up/stress class comes off the Thai move.
        global_yoy = it.get("yoy")
        cls = it.get("cls")
        if cls is None:
            cls = "stress" if (local_yoy is not None and local_yoy < 0) else "up"
        row = {
            "lab": lab, "seg": it.get("seg"), "reg": it.get("reg"),
            "global_yoy": global_yoy, "cls": cls, "note": it.get("note"),
            "global_vintage": it.get("stale"),
            "local_yoy": local_yoy,
            "local_price": (("%.2f %s" % (local["price"], local.get("unit", "")))
                            if local else None),
            "local_date": local.get("latest_date") if local else None,
            # n_markets is the honesty column: some NABC series are quoted by a single market, so
            # the YoY is measured but thin. The UI shows it rather than averaging the caveat away.
            "local_markets": local.get("n_markets") if local else None,
            "local_product": (local.get("product") or local.get("product_th")) if local else None,
            "local_source": ("OCSB announced price" if (local and local is ocsb)
                             else "NABC daily market" if (local and ncat and not fgkey)
                             else ("Thai farm-gate" if local else None)),
            "divergence": (round(local_yoy - global_yoy, 1)
                           if (local_yoy is not None and global_yoy is not None) else None),
        }
        # who's exposed — rank provinces by MEASURED planted area (the real crop belt, not
        # within-province share, which wrongly floats urban high-account provinces to the top),
        # take the core belt (provinces making up ~80% of national area), and report the book
        # accounts sitting in it.
        src_id, akey = BOARD_TO_AREA.get(lab, (None, None))
        # canonical provinces only — crop_prov_area carries an empty-key national-total row that
        # would otherwise dominate the belt and inflate the national area. area_tables() has
        # already dropped it for every source.
        ar = areas.get(src_id, {}).get(akey, {}) if src_id else {}
        if ar:
            ranked = sorted(((pv, a) for pv, a in ar.items() if a > 0), key=lambda x: -x[1])
            national = sum(a for _, a in ranked) or 1
            belt, cum = [], 0
            for pv, a in ranked:
                belt.append((pv, a))
                cum += a
                if cum >= 0.80 * national:
                    break
            book_in_belt = sum(acc.get(pv, 0) for pv, _ in belt)
            src = AREA_SOURCES[src_id]
            # Most belts are planted area in rai; the fisheries and forestry ones are not (see the
            # `measure`/`unit` keys on those AREA_SOURCES entries). Resolve per source+key so the
            # row states its own measure instead of every belt claiming to be planted area.
            measure = (src.get("measure") or {}).get(akey, "planted area")
            unit = (src.get("unit") or {}).get(akey, "rai")
            row["exposure"] = {
                "book_accounts": book_in_belt,
                "belt_provinces": len(belt),
                "national_area_rai": round(national),
                # What the belt is actually ranked on. The UI column header reads these, so a shrimp
                # belt says "Farm area (rai)" and fishmeal says "Output (tonnes)" instead of both
                # claiming planted area.
                "belt_measure": measure,
                "belt_unit": unit,
                "belt_measure_label": "%s%s" % (measure[:1].upper() + measure[1:],
                                                " (%s)" % unit if unit else ""),
                # THE WHOLE BELT, not a top-6 slice (changed 2026-08-01, owner ask). The drill quotes
                # book_accounts for the entire belt above the table, so emitting only 6 rows made the
                # accounts column visibly fail to add up to its own headline — for rice, the 6 shown
                # provinces held 50,742 of 138,184 and the missing 63% was nowhere on the page. The
                # rows now sum exactly to book_accounts and the area column sums to the belt's area.
                #
                # crop_income_pct / crop_income_baht are THIS CROP's effect (owner ask 2026-08-02).
                # The drill previously borrowed income_impact.json's `agri_price_shock_pct`, which is
                # the province's ALL-CROP shock and is area-weighted over rice/rubber/oilpalm ONLY.
                # In the coconut belt that read +26.84% while coconut itself was -70.9%, because
                # ประจวบคีรีขันธ์'s crop_mix is 61% rubber / 34% palm / 5% rice and contains no
                # coconut at all — the column was answering a different question than the drill asks,
                # and answering it with the opposite sign. This is conditional on the household's
                # MAIN crop being this one (stated in the UI); it deliberately does NOT weight by the
                # crop's area share, because belt areas come from different registries (DOAE farmer
                # registration vs the planted-area census) and a share computed across them would be
                # a false precision — see area_note.
                "crop_sens": crop_sens,
                "top": [{"prov": pv, "area_rai": round(a), "accounts": acc.get(pv, 0),
                         "crop_income_pct": (round(crop_sens * local_yoy, 1)
                                             if (crop_sens is not None and local_yoy is not None)
                                             else None),
                         "crop_income_baht": (round(agri_base[pv] * crop_sens * local_yoy / 100.0)
                                              if (crop_sens is not None and local_yoy is not None
                                                  and agri_base.get(pv)) else None)}
                        for pv, a in belt],
                "area_provenance": src["provenance"],
                "area_source": src["source"],
                "area_note": src["note"],
                "basis": "book accounts in the core belt (provinces = ~80%% of national %s, %s); "
                         "belt identifies the real producing region."
                         % (measure, src["provenance"]),
                "income_basis": (
                    "ESTIMATED, and conditional: the income columns are this crop's OWN effect on a "
                    "farm household in that province whose MAIN crop is this one — "
                    "sensitivity %s x the crop's Thai YoY, applied to the province's MEASURED NSO SES "
                    "farm-income base. Same sensitivity the income engine uses. It is deliberately "
                    "NOT weighted by the crop's share of local area: belt areas come from different "
                    "registries and a cross-source share would be false precision."
                    % crop_sens) if crop_sens is not None else None,
            }
        else:
            row["exposure"] = None
        items.append(row)

    # Stressed (falling) first, then biggest movers — same ordering the cards use, but ranked on
    # the move the BORROWER feels (Thai farm-gate where a local series exists, world price
    # otherwise) rather than always the world price. `lab` is the final tiebreak so equal moves
    # can never order on dict/set iteration and break the byte-exact --check.
    def felt(r):
        return r["local_yoy"] if r["local_yoy"] is not None else r["global_yoy"]

    items.sort(key=lambda r: (r["cls"] != "stress", -abs(felt(r) or 0), r["lab"]))

    diesel = (fuel.get("headline") or {}).get("diesel")
    return {
        "meta": {
            "title": "Commodities board — global Pink Sheet × Thai farm-gate × book exposure",
            "generated_by": "pipeline/build_commodities.py",
            "label": "MEASURED prices (World Bank Pink Sheet global YoY + Thai farm-gate local YoY). "
                     "Divergence = local − global. WHO'S EXPOSED is an ESTIMATED book-footprint "
                     "read: accounts in a crop's growing provinces weighted by planted-area share. "
                     "Each exposure carries its own area_provenance — every belt on this board is "
                     "now MEASURED: rice/rubber/oilpalm from the planted-area census, cassava/"
                     "maize/coconut/pineapple from the DOAE farmer registry, sugarcane from OCSB's "
                     "own returns. Rows with neither price series nor province area carry their "
                     "global price alone, with a region tag.",
            "nabc_excluded": ndropped,
            "nabc_note": "Thai livestock / fishery / orchard prices come from the NABC daily market "
                         "feed. build_farmgate_prices.py keeps raw CROP farm-gate forms only, so "
                         "before this these series never reached the board and six FALLING measured "
                         "Thai prices were invisible behind a board whose only faller was a world "
                         "sugar price. Some NABC series are quoted by a single market — every row "
                         "carries its own n_markets so a thin series is visible as thin.",
            "sugarcane_note": "CLOSED 2026-08-01 (pipeline/ingest_ocsb_cane.py). Sugar was the "
                              "board's one row with a falling WORLD price, a MODELLED 2010 belt "
                              "and no Thai price at all — a move nobody could be named against. "
                              "OCSB's own returns now give it a MEASURED 47-province belt "
                              "(production year 2565/66) and the announced cane price falls with "
                              "the world price rather than diverging from it. The retired SPAM "
                              "2010 raster understated the national cane belt by ~1.7x. The cane "
                              "price is ADMINISTERED — one announced national price per season on "
                              "a ~10-CCS basis — so it is not a market quote and carries no "
                              "n_markets; the OAE 2561/2562 BE snapshot stays unwired.",
            "farmgate_vintage": (fg.get("meta") or {}).get("pulled")
                                or next((v.get("latest_date") for v in fgc.values()), None),
            "divergence_note": "A large local−global gap flags where the Thai farmer's cash reality "
                               "parts from the world index (FX, export policy, local supply).",
        },
        "fuel": {"diesel_thb_l": diesel,
                 "name": (fuel.get("headline") or {}).get("diesel_name"),
                 "note": "Diesel is a cost line for pickup/haulage borrowers, not a crop revenue."},
        "board": items,
    }


def main():
    if not os.path.exists(os.path.join(P, "income_impact.json")):
        print("build_commodities.py: SKIP (income_impact.json absent — run the tape/income wave)")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if "--check" in sys.argv[1:]:
        if not os.path.exists(OUT):
            sys.exit("build_commodities.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_commodities.py --check: drifted — re-run the builder.")
        print("build_commodities.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d commodities, %d with exposure"
          % (OUT, len(obj["board"]), sum(1 for r in obj["board"] if r["exposure"])))


if __name__ == "__main__":
    main()
