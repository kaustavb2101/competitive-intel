#!/usr/bin/env python3
"""
build_assist_branch_radar.py — take the price-pressure assistance radar from PROVINCE to BRANCH
=============================================================================================
`assist_price_radar.json` answers "which provinces have farm borrowers in a crop whose price is
falling". That is the right question, but it lands on a province — and nobody works a province. A
branch manager needs to know whether THEIR book is the exposed one.

WHAT THIS ADDS
--------------
For each TRIPPED province, the branches inside it ranked by how much of their own catchment
cropland sits in the crop that is actually falling. So the readout goes from

    "Bueng Kan has 1,471 farm accounts in the Current/X-days window and cane is down 17.9%"

to that PLUS which of its branches carry the cane exposure and which barely do.

WHAT IS MEASURED AND WHAT IS NOT — read this before quoting a number
-------------------------------------------------------------------
  MEASURED  the price move. Farm-gate prices are NABC daily market averages, except SUGARCANE,
            which is the OCSB ANNOUNCED price — administered nationally, one price per season. That
            makes cane's -17.9% stronger evidence than a market wobble, not weaker: it is certain,
            already announced, dated, and every cane household takes it. It is also season-over-
            season, NOT a daily move, and this file says so per crop.
  MEASURED  the account counts and balances, from the real no-PII tape. Province totals always;
            per-branch ONLY where that branch's farm cell cleared MIN_CELL in the tape aggregation
            (250 of 618 branches in tripped provinces, ~40%). Everywhere else the per-branch count
            is null with a stated reason — NOT a province figure divided down, which would look
            like a measurement and be a model.
  ESTIMATED the branch's crop exposure. branch_agri.json's crop mix is a SPAM spatial model over a
            10km catchment, not a survey of what this branch's borrowers grow. It is the right
            shape for RANKING branches against each other and the wrong thing to quote as a fact
            about any single one.

COVERAGE, STATED PLAINLY
------------------------
branch_agri carries five crops (rice, cassava, maize, oil palm, sugarcane). 21 of the 22 tripped
provinces trip on sugarcane, which is covered. One trips on coconut, which is not — that province
is emitted with branches:[] and a note naming the gap rather than being silently dropped or ranked
on a crop it is not stressed about.

  in : platform/data/assist_price_radar.json   tripped provinces + MEASURED tape counts
       platform/data/branch_agri.json          per-branch crop mix (ESTIMATED, index-aligned)
       platform/data/branches.json             the branch master (name, province, coords)
       platform/data/tape_geo_occ.json         per-branch farm cells (MEASURED where flagged)
  out: platform/data/assist_branch_radar.json

Usage:
  python3 build_assist_branch_radar.py
  python3 build_assist_branch_radar.py --check
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from branchkey import norm_branch  # noqa: E402

DATA = os.path.join(ROOT, "platform", "data")
IN_RADAR = os.path.join(DATA, "assist_price_radar.json")
IN_AGRI = os.path.join(DATA, "branch_agri.json")
IN_BRANCHES = os.path.join(DATA, "branches.json")
IN_GEO_OCC = os.path.join(DATA, "tape_geo_occ.json")
OUT = os.path.join(DATA, "assist_branch_radar.json")

FARM_OCC = "เกษตร"          # the tape's agriculture occupation label
RC_ABSENT = 3


def _load(p):
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def build():
    radar, agri, branches, geo = (_load(IN_RADAR), _load(IN_AGRI),
                                  _load(IN_BRANCHES), _load(IN_GEO_OCC))
    if radar is None or agri is None or branches is None:
        return None

    rows = branches["branches"] if isinstance(branches, dict) else branches
    agri_rows = agri["branches"]
    if len(rows) != len(agri_rows):
        # branch_agri is INDEX-aligned to branches.json; a length mismatch means one was rebuilt
        # without the other and every join below would be silently off by some branches.
        raise SystemExit("branches.json has %d rows but branch_agri.json has %d — refusing to "
                         "join by index across a mismatch" % (len(rows), len(agri_rows)))

    crop_keys = [c["key"] for c in agri["meta"]["crops"]]

    # MEASURED per-branch farm cells, keyed by the normalised branch name. Only cells the tape
    # itself flagged `measured` are carried; an `estimated` cell is a province rate allocated down
    # and must not be presented as this branch's number.
    tape = {}
    if geo:
        for b in geo.get("branches") or []:
            for cell in b.get("occs") or []:
                if cell.get("occupation") == FARM_OCC and cell.get("basis") != "estimated":
                    tape[norm_branch(b.get("branch") or "")] = {
                        "n_farm": cell.get("n"),
                        "os_farm_thb": cell.get("os_sum"),
                        "early_pct": cell.get("early_pct"),
                        "dpd90p_pct": cell.get("dpd90p_pct"),
                    }

    out_provs = []
    n_ranked = n_measured = 0
    for prov in radar.get("provinces") or []:
        if not prov.get("tripped"):
            continue
        falling = [c for c in prov.get("crops") or []
                   if c.get("depended_on") and c.get("direction") == "down"]
        if not falling:
            continue

        # Which of the falling crops this branch layer can actually see.
        layer_crops = [c for c in falling if c["key"] in crop_keys]
        uncovered = [c["crop"] for c in falling if c["key"] not in crop_keys]

        rec = {
            "th": prov.get("th"),
            "region": prov.get("region"),
            # the province-level MEASURED figures, carried through so the branch list is always
            # read next to the number that is actually solid
            "n_farm_accounts": prov.get("n_farm_accounts"),
            "n_current_x": prov.get("n_current_x"),
            "os_thb": prov.get("os_thb"),
            "dpd90p_pct": prov.get("dpd90p_pct"),
            "falling": [{"crop": c["crop"], "key": c["key"], "yoy": c["yoy"],
                         "province_share": c.get("share"),
                         "administered": c["key"] == "sugarcane",
                         "basis": ("OCSB announced season price — administered nationally, "
                                   "season-over-season, not a daily market move")
                                  if c["key"] == "sugarcane" else
                                  "NABC daily market average, year-over-year"}
                        for c in falling],
            "branch_layer_crops": [c["key"] for c in layer_crops],
            "branches": [],
        }
        if uncovered:
            rec["coverage_note"] = (
                "No per-branch crop layer for %s — branch_agri models five crops (%s), so this "
                "province's branches cannot be ranked on the crop it is actually stressed about. "
                "The province totals above are still MEASURED."
                % (", ".join(uncovered), ", ".join(crop_keys)))

        if layer_crops:
            keys = [c["key"] for c in layer_crops]
            idxs = [crop_keys.index(k) for k in keys]
            for i, r in enumerate(rows):
                if r.get("v") != prov.get("th"):
                    continue
                a = agri_rows[i]
                sh = a.get("sh") or []
                ha = a.get("ha") or []
                exposure = round(sum(sh[j] for j in idxs if j < len(sh)), 4)
                crop_ha = sum(ha[j] for j in idxs if j < len(ha))
                cell = tape.get(norm_branch(r.get("n") or ""))
                b = {
                    "name": r.get("n"),
                    "x": r.get("x"), "y": r.get("y"),
                    "exposure_share": exposure,
                    "exposed_crop_ha": int(round(crop_ha)),
                    "catchment_crop_ha": a.get("crop_ha"),
                    "price_stress": a.get("price_stress"),
                }
                if cell:
                    b.update(cell)
                    b["accounts_basis"] = "measured"
                    n_measured += 1
                else:
                    b["n_farm"] = None
                    b["accounts_basis"] = "not_published"
                    b["accounts_note"] = ("this branch's farm cell did not clear the tape's "
                                          "MIN_CELL floor, so no per-branch count is published; "
                                          "use the province total")
                rec["branches"].append(b)
                n_ranked += 1
            # Rank by ABSOLUTE exposed hectares, not share. Share alone is actively misleading
            # here: the first build put a branch with 48% cane and SEVEN hectares of it above one
            # with 27% and 1,155 — 48% of almost no cropland is not a bigger book at risk, it is a
            # branch with almost no farmland. What is actionable is the size of the falling-crop
            # farm economy around the branch. Share stays on the record as concentration.
            # Ties break on share then name so the order is total and the file is byte-stable.
            rec["branches"].sort(key=lambda b: (-b["exposed_crop_ha"], -b["exposure_share"],
                                                b["name"] or ""))
        out_provs.append(rec)

    out_provs.sort(key=lambda p: (-(p.get("n_current_x") or 0), p.get("th") or ""))

    return {
        "meta": {
            "title": "Which BRANCHES carry the falling-crop exposure in a stressed province",
            "generated_by": "pipeline/build_assist_branch_radar.py",
            "label": (
                "MIXED, labelled per field. Price moves and the account counts are MEASURED; the "
                "per-branch crop exposure used to RANK branches is ESTIMATED (SPAM spatial model "
                "over a 10km catchment). Per-branch account counts appear only where the tape's "
                "own cell was measured — %d of %d branches here; the rest are null with a reason, "
                "never a province figure divided down."
                % (n_measured, n_ranked)),
            "source": (
                "provinces + accounts: platform/data/assist_price_radar.json (real no-PII tape x "
                "MEASURED planted-area shares x MEASURED farm-gate prices); per-branch crop mix: "
                "platform/data/branch_agri.json (SPAM 2010, 10km catchment, ESTIMATED); "
                "per-branch farm cells: platform/data/tape_geo_occ.json (measured cells only); "
                "branch master: platform/data/branches.json."),
            "how_to_read": (
                "Branches are ranked by exposed_crop_ha — the modelled hectares of the FALLING "
                "crop around the branch, i.e. the size of the farm economy taking the price cut. "
                "exposure_share is that as a share of the branch's catchment cropland, and is "
                "concentration, not size: 48% of seven hectares is not a big exposure. Both are "
                "ESTIMATED and both compare branches to each other — neither is a claim about "
                "what any individual borrower grows."),
            "action": (
                "These are Current and X-days borrowers — not yet delinquent — whose crop income "
                "is falling on a price that is already known. The window for contact is now, "
                "before the roll. Work the province total; start at the top of its branch list."),
            "n_provinces": len(out_provs),
            "n_branches_ranked": n_ranked,
            "n_branches_with_measured_accounts": n_measured,
            "farm_occupation": FARM_OCC,
        },
        "provinces": out_provs,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="re-run and byte-compare (exit 3 / SKIP when an input is absent)")
    args = ap.parse_args()

    data = build()
    if data is None:
        msg = "an input layer is absent — assist_branch_radar not buildable here"
        print(("CHECK SKIP: " if args.check else "SKIP: ") + msg, file=sys.stderr)
        sys.exit(RC_ABSENT)

    text = dumps(data)
    if args.check:
        if not os.path.exists(OUT):
            print("CHECK FAIL: %s does not exist" % OUT)
            sys.exit(1)
        with open(OUT, encoding="utf-8") as fh:
            if fh.read() == text:
                print("CHECK OK: %s reproduces byte-for-byte (%d provinces, %d branches)"
                      % (OUT, data["meta"]["n_provinces"], data["meta"]["n_branches_ranked"]))
                sys.exit(0)
        print("CHECK FAIL: %s differs from a fresh build" % OUT)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    m = data["meta"]
    print("wrote %s (%d tripped provinces, %d branches ranked, %d with MEASURED farm accounts)"
          % (OUT, m["n_provinces"], m["n_branches_ranked"], m["n_branches_with_measured_accounts"]))


if __name__ == "__main__":
    main()
