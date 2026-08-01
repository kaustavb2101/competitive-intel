"""
build_impact_cards.py — the Region → Province → Branch impact-card layer (owner sign-off 2026-07-25)

Projects committed measured layers into ONE drill file the card component renders:
platform/data/impact_cards.json. Big picture first: 5 region cards, each province a row under
its region, each tape-visible branch a row under its province. Humanized fields by design
(owner: "numbers people understand") — months-of-income instead of a DTI ratio, 1-per-N-vehicles
instead of an index, plain rival ratios instead of HL/LL codes.

Metric set per the 2026-07-25 sign-off: NO profit-per-account; ADD financed-vs-fleet split by
pickup/moto, commodity price direction per region, and book-occupation-mix vs the workforce.

  in : platform/data/tape_real.json            MEASURED — tape rollups + occ/vehicle × geo-region
       platform/data/rival_threat_region.json  MEASURED — rivals vs AutoX per region
       platform/data/rival_density.json        MEASURED — per-district rival census (province rollup)
       platform/data/household_risk_by_province.json  MEASURED — NSO SES debt/income
       platform/data/occupation_income_individual.json MEASURED SES + ESTIMATED individual split
       platform/data/province_lfs.json         MEASURED — NSO LFS 2026Q1
       platform/data/deltas.json               MEASURED vintage deltas (2025M12 → 2026M06)
       source-data/employment_by_province.json MEASURED — NSO formal/informal workers
       source-data/vehicles_by_province.json   MEASURED — DLT registered fleet
       source-data/commodity_board.json        MEASURED — commodity YoY board w/ region tags
       source-data/branches_final.json         branch → province/region join
  out: platform/data/impact_cards.json         (--check: byte-exact reproduce)

All cells inherit the tape's no-PII floor (n>=30). Occupation/vehicle splits exist at region
level (the tape crosses); province rows carry totals only. Branch rows exist only for the tape's
top-400 booking branches — smaller branches are suppressed by the floor, stated in meta.
"""
import json
import os
import re
import sys

from lib.regionmap import REGION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "platform", "data")
S = os.path.join(ROOT, "source-data")
OUT = os.path.join(P, "impact_cards.json")

REGIONS = ["Isan", "Central&BKK", "South", "East", "North"]
TH = {"Isan": "อีสาน", "North": "เหนือ", "South": "ใต้", "East": "ตะวันออก",
      "Central&BKK": "กลาง+กทม"}
# commodity_board 'reg' display tags → region keys ('S·E coast' → South+East; 'coast' ignored)
CTOK = {"Isan": "Isan", "NE": "Isan", "N": "North", "North": "North", "C": "Central&BKK",
        "S": "South", "South": "South", "E": "East", "East": "East"}


def load(*path):
    return json.load(open(os.path.join(*path), encoding="utf-8"))


# The join key lives in ONE place now (pipeline/branchkey.py). It used to be copy-pasted here, in
# ingest_real_tape.py and in make_call_lists.py, kept in sync by a comment — three chances for a
# silent join to drift apart.
from branchkey import norm_branch, master_index, join_report  # noqa: E402


def wmean(pairs):
    """weight-mean over (value, weight); None values are skipped."""
    num = den = 0.0
    for v, w in pairs:
        if v is None or not w:
            continue
        num += v * w
        den += w
    return num / den if den else None


def current_pct(c):
    """Whole-book Current-bucket (0 dpd) share = 100 − X-days(pre-30) − 30+(dpd30p).
    Current + early_pct + dpd30p_pct partition the whole book, so this is exact (clamped ≥0).
    None when a tape cell lacks the buckets."""
    e, d = c.get("early_pct"), c.get("dpd30p_pct")
    if e is None or d is None:
        return None
    return round(max(0.0, 100.0 - e - d), 2)


def build():
    tape = load(P, "tape_real.json")
    threat = {r["region"]: r for r in load(P, "rival_threat_region.json")["regions"]}
    density = load(P, "rival_density.json")["records"]
    hrisk = {r["province"]: r for r in load(P, "household_risk_by_province.json")["provinces"]}
    occinc = load(P, "occupation_income_individual.json")["provinces"]
    lfs = {r["name_th"]: r for r in load(P, "province_lfs.json")["provinces"]}
    deltas = load(P, "deltas.json")
    emp = load(S, "employment_by_province.json")["provinces"]
    fleet = load(S, "vehicles_by_province.json")["provinces"]
    board = load(S, "commodity_board.json")
    crop_stress = {p["th"]: p for p in load(P, "crop_stress.json")["provinces"]}
    master = load(S, "branches_final.json")
    mrows = master if isinstance(master, list) else master.get("branches", [])

    # per-crop price direction from the SAME commodity board the region chips use (World Bank Pink
    # Sheet YoY). crop_stress crop-mix labels → board labels (measured SPAM province mix carries only
    # Rice / Rubber / Oil palm; the board also tracks Sugar/Maize, surfaced at region level).
    BOARD_BY = {it["lab"]: it for it in board}
    CROP2BOARD = {"Rice": "Rice", "Rubber": "Rubber", "Oil palm": "Palm oil",
                  "Sugarcane": "Sugar", "Maize": "Maize"}

    def province_crops(pv):
        """[{crop, share, yoy, cls}] for a province's measured crop mix, each crop tagged with its
        Pink Sheet YoY/direction. Plus rain-%-of-normal (drought proxy). None-safe → empty list."""
        cs = crop_stress.get(pv)
        if not cs:
            return [], None
        out = []
        for c in (cs.get("crop_mix") or []):
            b = BOARD_BY.get(CROP2BOARD.get(c["crop"], c["crop"]))
            out.append({"crop": c["crop"], "share": round(c.get("share") or 0.0, 3),
                        "yoy": (b or {}).get("yoy"), "cls": (b or {}).get("cls")})
        rain = (cs.get("components") or {}).get("rain_pct_of_normal")
        return out, (round(rain, 1) if rain is not None else None)

    geo = tape["geo"]
    treg, tprov = geo["regions"], geo["provinces"]
    occ_x, veh_x = geo["occ_x_region"], geo["vehicle_x_region"]
    dreg = {d["r"]: d for d in deltas.get("region", [])}

    # ── per-province rollups of the shared inputs ────────────────────────────────
    prov_region = dict(REGION)
    rivals_prov = {}
    for d in density:
        pv = d.get("province_th")
        if pv not in prov_region:
            continue
        c = rivals_prov.setdefault(pv, {"ours": 0, "rivals": 0, "brands": {}})
        c["ours"] += d.get("autox") or 0
        c["rivals"] += d.get("rivals") or 0
        for b, n in (d.get("by_brand") or {}).items():
            c["brands"][b] = c["brands"].get(b, 0) + n
    branches_prov = {}
    for m in mrows:
        pv = m.get("prov")
        if pv in prov_region:
            branches_prov[pv] = branches_prov.get(pv, 0) + 1
    inc_prov = {}     # ESTIMATED individual income, mean over the 5 SES occupations
    for pv, occs in occinc.items():
        vals = [o.get("individual_est") for o in occs.values()
                if isinstance(o, dict) and o.get("individual_est")]
        if vals and pv in prov_region:
            inc_prov[pv] = sum(vals) / len(vals)
    # province trend: mean measured agri-risk delta over that province's branches in the
    # movers file (top-80 network movers only — absent provinces carry the region trend).
    dprov = {}
    for b in deltas.get("branches", []):
        pv = b.get("v")
        if pv in prov_region and b.get("d_a") is not None:
            dprov.setdefault(pv, []).append(b["d_a"])
    dprov = {pv: round(sum(v) / len(v), 1) for pv, v in dprov.items()}

    # ── branch rows under their province (joined via the master) ────────────────
    # The miss is now COUNTED. It used to `continue` with no counter and no note, so a branch that
    # failed to join simply was not in the drill — indistinguishable from a branch that does not
    # exist. Everything the join drops is named in meta.branch_name_join.
    bname, bcoll = master_index(mrows, lambda m: m.get("prov"))
    bjoin = join_report(bname, geo["branches"].keys())
    bjoin["master_key_collisions"] = bcoll
    branch_rows = {}
    for name, c in geo["branches"].items():
        pv = bname.get(norm_branch(name))
        if pv not in prov_region:
            continue
        branch_rows.setdefault(pv, []).append({
            "name": name, "n": c["n"], "os_m": round(c["os_sum"] / 1e6, 1),
            "npl_live_pct": c["npl_live_pct"], "roll_pct": c["roll_pct"],
            "early_pct": c["early_pct"],
            "dpd30p_pct": c.get("dpd30p_pct"), "late180_pct": c.get("late180_pct"),
            "current_pct": current_pct(c)})
    for pv in branch_rows:
        branch_rows[pv].sort(key=lambda b: (-b["npl_live_pct"], -b["n"]))

    # ── commodity board per region ───────────────────────────────────────────────
    commod = {r: [] for r in REGIONS}
    for it in board:
        toks = [CTOK.get(t) for t in re.split(r"[·\s]+", str(it.get("reg") or ""))]
        for r in {t for t in toks if t}:
            commod[r].append({"lab": it["lab"], "yoy": it["yoy"], "cls": it["cls"],
                              "note": it["note"]})
    for r in commod:   # stressed (falling income) first, then biggest movers
        commod[r].sort(key=lambda c: (c["cls"] != "stress", -abs(c["yoy"])))

    # ── province rows ────────────────────────────────────────────────────────────
    provinces = {}
    for pv, c in tprov.items():
        if pv not in prov_region:
            continue
        r = prov_region[pv]
        hr, lf = hrisk.get(pv), lfs.get(pv)
        rv = rivals_prov.get(pv)
        fl = (fleet.get(pv) or {}).get("total")
        lead = max(rv["brands"].items(), key=lambda kv: (kv[1], kv[0]))[0] \
            if rv and rv["brands"] else None
        provinces[pv] = {
            "region": r,
            "branches": branches_prov.get(pv, 0),
            "accounts": c["n"], "os_m": round(c["os_sum"] / 1e6, 1),
            "npl_live_pct": c["npl_live_pct"], "roll_pct": c["roll_pct"],
            "early_pct": c["early_pct"],
            "dpd30p_pct": c.get("dpd30p_pct"), "late180_pct": c.get("late180_pct"),
            "current_pct": current_pct(c),
            "debt_months": round(hr["debt"] / hr["income"] * 12, 1) if hr else None,
            "income_ind": round(inc_prov[pv]) if pv in inc_prov else None,
            "unemp_pct": lf.get("unemployment_rate_pct") if lf else None,
            "rivals": ({"ours": rv["ours"], "rivals": rv["rivals"],
                        "ratio": round(rv["rivals"] / rv["ours"], 1) if rv["ours"] else None,
                        "lead": lead} if rv else None),
            "fleet": fl,
            "per_vehicle": round(fl / c["n"]) if fl else None,
            "d_agri": dprov.get(pv),
        }
        crops, rain = province_crops(pv)
        provinces[pv]["crops"] = crops
        provinces[pv]["rain_pct"] = rain

    # ── region cards ─────────────────────────────────────────────────────────────
    regions = []
    for r in REGIONS:
        c = treg[r]
        provs = [pv for pv, reg in prov_region.items() if reg == r]
        emp_k = [(lfs[pv]["employed_k"], pv) for pv in provs if pv in lfs]
        workers = sum(k for k, _ in emp_k) * 1000.0
        informal = wmean([((e := emp.get(pv)) and e["informal"] * 100.0
                          / (e["formal"] + e["informal"]), lfs[pv]["employed_k"])
                         for pv in provs if pv in lfs and emp.get(pv)])
        fl = {"total": 0, "pickup": 0, "moto": 0}
        for pv in provs:
            f = fleet.get(pv)
            if f:
                for k in fl:
                    fl[k] += f.get(k) or 0
        fin_pu = veh_x.get("PU|" + r, {}).get("n", 0)
        fin_mc = veh_x.get("MC|" + r, {}).get("n", 0)
        occ_rows = sorted(((k.split("|")[0], v) for k, v in occ_x.items()
                           if k.endswith("|" + r) and not k.startswith("(blank)")),
                          key=lambda kv: -kv[1]["n"])
        d = dreg.get(r, {})
        regions.append({
            "key": r, "name_th": TH[r],
            "branches": sum(branches_prov.get(pv, 0) for pv in provs),
            "accounts": c["n"], "os_bn": round(c["os_sum"] / 1e9, 2),
            "npl_live_pct": c["npl_live_pct"], "npl_live_os_pct": c["npl_live_os_pct"],
            "roll_pct": c["roll_pct"], "early_pct": c["early_pct"],
            "dpd30p_pct": c.get("dpd30p_pct"), "late180_pct": c.get("late180_pct"),
            "current_pct": current_pct(c),
            "trend": {"agri_now": d.get("agri"), "d_agri": d.get("d_agri")},
            "people": {
                "income_ind": round(wmean([(inc_prov.get(pv), lfs[pv]["employed_k"])
                                           for pv in provs if pv in lfs])),
                "debt_months": round(wmean(
                    [((h := hrisk.get(pv)) and h["debt"] / h["income"] * 12,
                      lfs[pv]["employed_k"]) for pv in provs if pv in lfs]), 1),
                "unemp_pct": round(wmean([(lfs[pv]["unemployment_rate_pct"],
                                           lfs[pv]["employed_k"])
                                          for pv in provs if pv in lfs]), 2),
                "workers_m": round(workers / 1e6, 2),
                "informal_pct": round(informal, 1),
            },
            "vehicles": {
                "fleet_m": round(fl["total"] / 1e6, 2),
                "fleet_pu_m": round(fl["pickup"] / 1e6, 2),
                "fleet_mc_m": round(fl["moto"] / 1e6, 2),
                "fin": c["n"], "fin_pu": fin_pu, "fin_mc": fin_mc,
                "per_all": round(fl["total"] / c["n"]) if c["n"] else None,
                "per_pu": round(fl["pickup"] / fin_pu) if fin_pu else None,
                "per_mc": round(fl["moto"] / fin_mc) if fin_mc else None,
            },
            "occupations": {
                "book": [{"occ": o, "n": v["n"],
                          "pct": round(v["n"] * 100.0 / c["n"], 1),
                          "npl_live_pct": v["npl_live_pct"]} for o, v in occ_rows[:6]],
                # penetration as "1 account per N employed persons" (LFS employed) — same
                # intuitive 1-per-N framing as the vehicle line, not an analyst per-1,000 rate.
                "workers_per_acc": round(workers / c["n"]) if c["n"] else None,
            },
            "rivals": {"ours": threat[r]["autox"], "rivals": threat[r]["rivals"],
                       "ratio": threat[r]["rivals_vs_autox"],
                       "pct_districts_outnumbered": threat[r]["pct_districts_outnumbered"]},
            "commodities": commod[r][:5],
            "provinces": sorted((pv for pv in provs if pv in provinces),
                                key=lambda pv: -provinces[pv]["npl_live_pct"]),
        })
    regions.sort(key=lambda g: -g["accounts"])
    # plain-language flag per card, one each (rank-based, deterministic): worst NPL leads.
    flags = {}
    flags[max(regions, key=lambda g: g["npl_live_pct"])["key"]] = "assist-first"
    flags.setdefault(min(regions, key=lambda g: g["npl_live_pct"])["key"], "cleanest-book")
    left = [g for g in regions if g["key"] not in flags]
    flags[max(left, key=lambda g: g["vehicles"]["per_all"] or 0)["key"]] = "thinnest-foothold"
    left = [g for g in regions if g["key"] not in flags]
    flags[max(left, key=lambda g: g["rivals"]["ratio"])["key"]] = "watch-rivals"
    for g in regions:
        g["flag"] = flags.get(g["key"], "hold-course")

    tmeta = tape["meta"]
    return {
        "meta": {
            "title": "Impact cards — Region → Province → Branch drill (both objectives)",
            "generated_by": "pipeline/build_impact_cards.py",
            "label": "MEASURED throughout except: individual income (ESTIMATED split of the "
                     "measured NSO SES household figure) and the trend chips' agri-risk score "
                     "(model over measured inputs). Humanized fields by owner sign-off "
                     "2026-07-25: months-of-income (SES debt ÷ monthly income), 1-per-N "
                     "vehicles (DLT fleet ÷ tape financed), plain rival ratios.",
            "tape": {"source": tmeta.get("source"), "n_accounts": tmeta.get("n_accounts"),
                     "mob_anchor": tmeta.get("mob_anchor"), "min_cell": tmeta.get("min_cell")},
            "trend_window": {"from": deltas.get("from"), "to": deltas.get("to"),
                             "note": "trend chips = agri-risk deltas between committed "
                                     "vintages; tape-NPL deltas begin at the second monthly "
                                     "tape vintage (current tape is the first)."},
            "branch_note": "branch rows cover EVERY booking branch clearing the no-PII floor "
                           "(n>=30 accounts), so they reconcile to their province total. Until "
                           "2026-07-31 this read a top-400-by-size tab as well as the floor, "
                           "which silently dropped ~1,570 branches that cleared the floor and "
                           "left the rows summing to ~36% of their own province totals; the note "
                           "then blamed the floor for what was actually the cap. Branches still "
                           "absent are those under 30 accounts, which stay suppressed, plus the "
                           "handful named in branch_name_join.unmatched_names whose tape spelling "
                           "cannot be matched to a master branch.",
            "branch_name_join": bjoin,
            "occ_note": "occupation split is the BOOK mix per geo region (tape cross); the "
                        "workforce side is NSO LFS employed + informal share — NSO publishes "
                        "no per-region occupation census we can join yet.",
        },
        "regions": regions,
        "provinces": provinces,
        "branches": branch_rows,
    }


def main():
    if not os.path.exists(os.path.join(P, "tape_real.json")):
        # exit 3 = the gate's SKIP contract (ingest wave absent, not data drift)
        print("build_impact_cards.py: SKIP (tape_real.json absent — run the tape ingest first)")
        sys.exit(3)
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if "--check" in sys.argv[1:]:
        if not os.path.exists(OUT):
            sys.exit("build_impact_cards.py --check: output missing — run the builder.")
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_impact_cards.py --check: drifted — re-run the builder.")
        print("build_impact_cards.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    print("wrote %s — %d regions, %d provinces, %d provinces w/ branch rows"
          % (OUT, len(obj["regions"]), len(obj["provinces"]), len(obj["branches"])))


if __name__ == "__main__":
    main()
