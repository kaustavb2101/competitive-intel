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
    (province_cropland.json says so in its own provenance line). The only sugarcane area in the repo
    is SPAM 2010, a MODELLED 5-arcmin disaggregation now 16 years old, so the sugar belt is labelled
    MODELLED and dated. There is also no CURRENT Thai cane price here: source-data/crop_prices.json
    carries อ้อยโรงงาน but it is an OAE 2561/2562 BE (2018/2019 CE) snapshot, so it is deliberately
    NOT wired as a farm-gate. Closing both needs an OCSB (สำนักงานคณะกรรมการอ้อยและน้ำตาลทราย) pull.
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
                 "Sugar": ("spam", "sugarcane")}

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
    "spam": {
        "provenance": "MODELLED",
        "source": "IFPRI/MapSPAM 2010 v2.0 (platform/data/crop_landuse.json)",
        "note": "MODELLED spatial disaggregation on a 2010 base — 16 years old. It is the only "
                "sugarcane area held anywhere in this repo, because cane growers register with the "
                "OCSB rather than DOAE. Read the belt as where cane grows, not as current area.",
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

    return {"census": census, "doae": doae, "spam": spam}


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

    nabc = load(S, "nabc_prices.json")
    nkept, ndropped = nabc_locals(nabc)
    extra = [dict(spec, _nabc=cat) for cat, spec in NABC_ROWS if cat in nkept]

    items = []
    for it in list(board) + LOCAL_ONLY + extra:
        lab = it["lab"]
        ncat = it.get("_nabc") or BOARD_TO_NABC.get(lab)
        fgkey = BOARD_TO_FARMGATE.get(lab)
        # farmgate_prices is the curated raw-crop layer; NABC covers everything else it drops.
        local = (fgc.get(fgkey) if fgkey else None) or (nkept.get(ncat) if ncat else None)
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
            "local_source": ("NABC daily market" if (local and ncat and not fgkey)
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
            row["exposure"] = {
                "book_accounts": book_in_belt,
                "belt_provinces": len(belt),
                "national_area_rai": round(national),
                "top": [{"prov": pv, "area_rai": round(a), "accounts": acc.get(pv, 0)}
                        for pv, a in belt[:6]],
                "area_provenance": src["provenance"],
                "area_source": src["source"],
                "area_note": src["note"],
                "basis": "book accounts in the crop's core belt (provinces = ~80%% of national "
                         "planted area, %s); belt identifies the real growing region."
                         % src["provenance"],
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
                     "Each exposure carries its own area_provenance — MEASURED for rice/rubber/"
                     "oilpalm (census) and cassava/maize (DOAE registry), MODELLED for sugarcane "
                     "(SPAM 2010, the only cane area held here). Rows with neither price series "
                     "nor province area carry their global price alone, with a region tag.",
            "nabc_excluded": ndropped,
            "nabc_note": "Thai livestock / fishery / orchard prices come from the NABC daily market "
                         "feed. build_farmgate_prices.py keeps raw CROP farm-gate forms only, so "
                         "before this these series never reached the board and six FALLING measured "
                         "Thai prices were invisible behind a board whose only faller was a world "
                         "sugar price. Some NABC series are quoted by a single market — every row "
                         "carries its own n_markets so a thin series is visible as thin.",
            "sugarcane_gap": "Sugarcane has a MODELLED 2010 belt and NO current Thai farm-gate "
                             "price. Cane growers register with the OCSB rather than DOAE, and the "
                             "only Thai cane price in the repo (source-data/crop_prices.json, "
                             "อ้อยโรงงาน) is an OAE 2561/2562 BE = 2018/2019 CE snapshot, so it is "
                             "deliberately not wired. Sugar is currently the board's only falling "
                             "world price, so this is the gap worth closing: it needs an OCSB pull.",
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
