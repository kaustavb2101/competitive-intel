#!/usr/bin/env python3
"""
build_farm_book.py — the farm book, ranked by BAHT, at four grains: national, region, province, branch.

WHY THIS EXISTS
---------------
The Macro tab carried FOUR separate farm tables (crop mix, crop-household stress, farmer margin,
district crop x drought) plus an `agri_stress` 0-100 composite, and the owner's read was blunt:
"agri stress is an estimated measure that has been made up. Difficult to relate." He is right, and
the composite hid something worse.

Ranking by an index -- or by ACCOUNT COUNTS -- manufactured an alarm that ranking by money dissolves:

  * `crop_mix.accounts` is EVERY book account in a province (it is the weighting basis for the
    book-weighted crop shock), not the farm ones. Read as "farm accounts" it said 17,287 accounts
    were exposed to a falling crop mix.
  * The farm-specific exposure -- the tape's real เกษตร occupation cell -- is 1,826 accounts and
    ~THB213m, about 3% of the ~THB7.17bn farm book.
  * And the two provinces with the catastrophic crop moves carry almost NO farm lending:
    สมุทรสงคราม (-66.4%) has zero measured farm accounts, สมุทรสาคร (-61.9%) has 48.

So the honest headline inverts: ~97% of the farm book sits in provinces whose crop mix is RISING,
and the dramatic collapse is not a portfolio event. That finding is only visible in baht, which is
why this layer exists and why nothing here is scored.

WHAT IT DOES
------------
A pure join. Every number is carried from a source layer; this script computes no index and invents
no weighting. The one derived quantity is a sum.

  tape_geo_occ.json   MEASURED  farm (เกษตร) accounts, outstanding, and bucket counts per province
                                AND per branch -- the exposure, and the Current subset that is the
                                pre-emptive contact list
  crop_mix.json       MEASURED  the province's crop mix over all eight priced crops, each crop's
                                farm-gate YoY, and its contribution in pp to the province move
  crop_stress.json    MIXED     drought (MODELLED OAE SPEI) + rainfall % of normal (MEASURED)
  income_impact.json  MEASURED  the NSO/LFS-anchored farm income level (THB/month) for context --
                      + MODEL   asked for directly: "the table should also show the nso/lfs farm
                                income for context"
  crop_margin.json    MEASURED  farm-gate price vs OAE production cost per crop -- the margin table
                      + DERIVED the owner liked ("expand to cover what we have on data AND consolidate
                                with above tables"), folded in as the BY-CROP lens rather than left
                                standing alone
  napprang.json       MEASURED  OAE dry-season (irrigated SECOND) rice area -- the one measured column
                                the retired crop-stress table carried that nothing else does

THE CROP-DRIVER FIX
-------------------
The old "what is driving it" column named the biggest DRAG, under a heading promising the biggest
DRIVER. For ร้อยเอ็ด that printed "Sugarcane 5% of land, -17.9%" while rice -- 91.7% of the land at
+12.4% -- supplied +11.37pp of the province's +11.8% move. Same defect class as the agri-stress
sentence: right arithmetic, wrong sentence. `drivers` here is the ranked mix by |contribution|, so
the crop that actually moved the province is always first, and `drag` names the largest negative
separately instead of impersonating the driver.

Deterministic + network-free + --check, per the house rule.
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "..", "platform", "data")
OUT = os.path.join(P, "farm_book.json")

AGRI_OCC = "เกษตร"          # the tape's agriculture occupation label
BUCKETS = ("n_current", "n_watch_xdays", "n_rolling_3089", "n_at_risk_90p")


def _load(name):
    p = os.path.join(P, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _farm_cell(cells):
    """The เกษตร cell out of a list of occupation cells, or None."""
    for c in cells or []:
        if c.get("occupation") == AGRI_OCC:
            return c
    return None


def _zero():
    d = {"n": 0, "os": 0.0}
    d.update({b: 0 for b in BUCKETS})
    return d


def _add(acc, cell):
    acc["n"] += int(cell.get("n") or 0)
    acc["os"] += float(cell.get("os_sum") or 0.0)
    for b in BUCKETS:
        acc[b] += int(cell.get(b) or 0)


def _pack(acc):
    """Rounded, JSON-ready. Outstanding is carried in whole baht — no float tails in the payload."""
    return {"farm_n": acc["n"], "farm_os": int(round(acc["os"])),
            "current": acc["n_current"], "watch_x": acc["n_watch_xdays"],
            "roll_3089": acc["n_rolling_3089"], "at_risk_90p": acc["n_at_risk_90p"]}


FIELDS = ("farm_os", "farm_n", "current", "watch_x", "roll_3089", "at_risk_90p")


def _largest_remainder(weights, target, names):
    """Split `target` (an integer) across `weights` so the parts sum EXACTLY to it.

    Proportional rounding alone leaves a residue of a few units; largest-remainder assigns it to the
    rows with the biggest fractional parts. Ties break on name so the output is deterministic
    regardless of dict ordering — this file is --check-gated byte-for-byte.
    """
    tw = sum(weights)
    if tw <= 0 or target <= 0:
        return [0] * len(weights)
    raw = [target * w / tw for w in weights]
    base = [int(x) for x in raw]
    short = target - sum(base)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - base[i]), names[i]))
    for i in range(short):
        base[order[i % len(order)]] += 1
    return base


def _reconcile(rows, target):
    """Make the branch rows sum EXACTLY to the province's measured cell.

    WHY THIS IS HERE. tape_geo_occ carries branch x occupation cells that are MEASURED only where the
    cell clears the 30-account floor; each branch's thin residual is allocated over its province
    occupation mix and is ESTIMATED. Those allocations do not tie back: summed nationally the branch
    rows came to THB7.442bn against a measured province total of THB7.171bn — 3.8% over, with 62 of 75
    provinces off by more than 2%. A drill whose children do not sum to their parent is the exact
    defect the owner already caught once on the rice belt, so it is fixed at source rather than
    explained away in a footnote.

    MEASURED cells are never touched. The ESTIMATED residual flexes to close the gap, which is what
    an allocation is for. Only if the measured cells alone already exceed the province total does
    everything scale proportionally — and that case is recorded in the province's `recon` block so it
    is visible rather than silent.
    """
    if not rows:
        return None
    names = [r["name"] for r in rows]
    meas = [i for i, r in enumerate(rows) if r.get("basis") == "measured"]
    est = [i for i, r in enumerate(rows) if r.get("basis") != "measured"]
    mode = "estimated-residual"
    for f in FIELDS:
        tgt = int(target.get(f) or 0)
        sm = sum(int(rows[i][f] or 0) for i in meas)
        se = sum(int(rows[i][f] or 0) for i in est)
        if sm <= tgt and est and se > 0:
            parts = _largest_remainder([int(rows[i][f] or 0) for i in est], tgt - sm,
                                       [names[i] for i in est])
            for k, i in enumerate(est):
                rows[i][f] = parts[k]
        else:
            # measured alone already meets or exceeds the target (or there is nothing to flex):
            # scale every row so the level still ties, and say so.
            mode = "proportional" if sm > tgt else mode
            parts = _largest_remainder([int(r[f] or 0) for r in rows], tgt, names)
            for i, r in enumerate(rows):
                r[f] = parts[i]
    return {"mode": mode, "n_branches": len(rows), "n_measured": len(meas)}


def _margin_rows(margin):
    """One representative margin row per crop, chosen deterministically.

    OAE reports rice three ways (a compendium average plus two measured field practices), so the raw
    file has 7 rows for 5 crops. Preference: a DIRECTLY MEASURED cost beats one back-computed from
    cost/ton; among equals take the LOWEST margin, so the row shown is the conservative one rather
    than the flattering one. `alts` keeps the count so the spread is disclosed, not hidden.
    """
    by = {}
    for r in (margin.get("crops") or []):
        by.setdefault(r.get("crop"), []).append(r)
    out = {}
    for crop, rows in by.items():
        direct = [r for r in rows if r.get("cost_method") == "measured_direct"]
        pool = direct or rows
        pick = min(pool, key=lambda r: (r.get("margin_per_rai") or 0.0, r.get("crop_en") or ""))
        out[crop] = {
            "price_kg": pick.get("price_kg"), "cost_kg": pick.get("cost_kg"),
            "margin_per_rai": pick.get("margin_per_rai"),
            "margin_pct": pick.get("margin_pct_of_price"),
            "cost_method": pick.get("cost_method"), "cost_year": pick.get("cost_year"),
            "basis_en": pick.get("crop_en"), "alts": len(rows),
        }
    return out


def build():
    geo = _load("tape_geo_occ.json") or {}
    mix = _load("crop_mix.json") or {}
    stress = _load("crop_stress.json") or {}
    income = _load("income_impact.json") or {}
    margin = _load("crop_margin.json") or {}
    nap = _load("napprang.json") or {}

    mix_pv = (mix.get("provinces") or {})
    inc_pv = (income.get("provinces") or {})
    st_pv = {r.get("th"): r for r in (stress.get("provinces") or []) if r.get("th")}
    nap_pv = (nap.get("by_province") or {})
    marg = _margin_rows(margin)

    # region key per province: income_impact and crop_stress both carry one; prefer the tape's own.
    def region_of(th, fallback=None):
        r = (inc_pv.get(th) or {}).get("region") or (st_pv.get(th) or {}).get("region")
        return r or fallback

    provinces, regions, branches, prov_crops = {}, {}, {}, {}
    nat = _zero()

    for th, cells in sorted((geo.get("provinces") or {}).items()):
        cell = _farm_cell(cells)
        if not cell:
            continue                      # no measured farm cell in this province — omit, never zero-fill
        acc = _zero()
        _add(acc, cell)
        _add(nat, cell)

        m = mix_pv.get(th) or {}
        crops = [c for c in (m.get("crops") or []) if c.get("share")]
        # ranked by ABSOLUTE contribution: the crop that actually moved the province leads, whichever
        # way it moved. This is the column that used to name a 5%-of-land drag as "what is driving it".
        drivers = sorted(crops, key=lambda c: -abs(c.get("pp") or 0.0))[:3]
        drags = [c for c in crops if (c.get("pp") or 0.0) < 0]
        drag = min(drags, key=lambda c: c.get("pp") or 0.0) if drags else None

        st = st_pv.get(th) or {}
        comp = st.get("components") or {}
        agri_inc = ((inc_pv.get(th) or {}).get("occ") or {}).get("Agriculture") or {}

        np_ = nap_pv.get(th) or {}
        rec = _pack(acc)
        rec.update({
            "region": region_of(th),
            "mix_pct": m.get("shock_pct"),
            "mix_income_thb_month": m.get("income_thb_month"),
            "drivers": [{"crop": c.get("crop"), "share": round(100.0 * (c.get("share") or 0.0), 1),
                         "yoy": c.get("yoy"), "pp": c.get("pp")} for c in drivers],
            "drag": ({"crop": drag.get("crop"), "share": round(100.0 * (drag.get("share") or 0.0), 1),
                      "yoy": drag.get("yoy"), "pp": drag.get("pp")} if drag else None),
            "farm_income_thb_month": agri_inc.get("income"),
            "rain_pct_of_normal": comp.get("rain_pct_of_normal"),
            "drought": st.get("drought"),
            # the irrigated SECOND rice crop (OAE, MEASURED). The income cushion behind a dry reading:
            # a large area is a buffer today AND the income most at risk if water cuts skip it.
            "napprang_rai": np_.get("planted_rai"),
            "dpd90p_pct": cell.get("dpd90p_pct"),
            "basis": cell.get("basis"),
        })
        provinces[th] = rec
        # keep the full mix for the by-crop rollup below (never emitted per province — the drivers
        # list is what the province row shows; carrying all 8 for 75 provinces would triple the file)
        prov_crops[th] = crops

        r = rec["region"]
        if r:
            ra = regions.setdefault(r, _zero())
            _add(ra, cell)

    # branch grain — only branches that actually have a farm cell, so a branch with no farm book is
    # absent rather than shown as a zero row it would be read as a gap.
    for b in (geo.get("branches") or []):
        cell = _farm_cell(b.get("occs"))
        if not cell:
            continue
        th = b.get("prov")
        if th not in provinces:
            continue
        acc = _zero()
        _add(acc, cell)
        row = _pack(acc)
        row.update({"name": b.get("branch"), "dpd90p_pct": cell.get("dpd90p_pct"),
                    "basis": cell.get("basis")})
        branches.setdefault(th, []).append(row)
    # Tie every province's branch rows to its measured cell BEFORE sorting, then sort on the
    # reconciled figure so the ordering reflects what is actually displayed.
    for th in branches:
        branches[th].sort(key=lambda r: r["name"])          # stable input order for the split
        rec = _reconcile(branches[th], provinces[th])
        if rec:
            provinces[th]["recon"] = rec
        branches[th].sort(key=lambda r: (-r["farm_os"], r["name"]))

    # national: how much of the farm book sits under a FALLING mix. The whole point of the layer.
    neg = _zero()
    neg_names = []
    for th, rec in provinces.items():
        if rec.get("mix_pct") is not None and rec["mix_pct"] < 0:
            neg_names.append(th)
            neg["n"] += rec["farm_n"]
            neg["os"] += rec["farm_os"]
            neg["n_current"] += rec["current"]
    neg_names.sort()

    reg_out = {}
    for r, acc in sorted(regions.items()):
        p_in_r = [p for p in provinces.values() if p.get("region") == r]
        rec = _pack(acc)
        # region mix move, weighted by the region's own farm OUTSTANDING (not by area, not by
        # account count) — the money is what the region's exposure actually is.
        wsum = sum(p["farm_os"] for p in p_in_r if p.get("mix_pct") is not None)
        rec["mix_pct"] = (round(sum(p["farm_os"] * p["mix_pct"] for p in p_in_r
                                    if p.get("mix_pct") is not None) / wsum, 1) if wsum else None)
        rec["provinces"] = len(p_in_r)
        rec["neg_provinces"] = sum(1 for p in p_in_r
                                   if p.get("mix_pct") is not None and p["mix_pct"] < 0)
        reg_out[r] = rec

    # ---- BY-CROP LENS -------------------------------------------------------------------------
    # The same farm book, cut by crop instead of by geography. Two quantities per crop:
    #   farm_os_alloc  the farm book ALLOCATED over planted-area share. An allocation, not a
    #                  measurement -- the tape records an occupation, never which crop a borrower
    #                  grows -- and labelled as such wherever it renders.
    #   pp_of_book     the crop's contribution, in percentage points, to the farm-baht-weighted move
    #                  of the whole book. THIS one is the answer to "what is actually moving us":
    #                  it is measured price YoY x measured area share, weighted by measured baht.
    # They disagree on purpose. Coconut is 0.4% of the book but drags it; rice is most of both.
    crop_en = {}
    crop_alloc, crop_pp, crop_area, crop_dom = {}, {}, {}, {}
    area_tot = 0.0
    for th, rec in provinces.items():
        os_ = rec["farm_os"]
        cs = prov_crops.get(th) or []
        a = (mix_pv.get(th) or {}).get("area_rai") or 0
        area_tot += a
        dom = max(cs, key=lambda c: c.get("share") or 0.0) if cs else None
        if dom:
            crop_dom[dom["crop"]] = crop_dom.get(dom["crop"], 0) + 1
        for c in cs:
            k = c.get("crop")
            crop_en[k] = c.get("en") or k
            crop_alloc[k] = crop_alloc.get(k, 0.0) + os_ * (c.get("share") or 0.0)
            crop_pp[k] = crop_pp.get(k, 0.0) + os_ * (c.get("pp") or 0.0)
            crop_area[k] = crop_area.get(k, 0.0) + a * (c.get("share") or 0.0)
    os_tot = float(nat["os"]) or 1.0
    crops_out = []
    for k in sorted(crop_alloc, key=lambda k: (-crop_alloc[k], k)):
        row = {
            "crop": k, "en": crop_en.get(k, k),
            "farm_os_alloc": int(round(crop_alloc[k])),
            "os_share_pct": round(100.0 * crop_alloc[k] / os_tot, 1),
            "area_share_pct": (round(100.0 * crop_area[k] / area_tot, 1) if area_tot else None),
            "yoy": ((mix.get("meta") or {}).get("crop_yoy_pct") or {}).get(k),
            "pp_of_book": round(crop_pp[k] / os_tot, 2),
            "dominant_in": crop_dom.get(k, 0),
        }
        row.update(marg.get(k) or {})
        crops_out.append(row)
    # the farm book's OWN weighted move: every region row is farm-baht-weighted, so the national
    # banner must be too. crop_mix's headline number weights by ALL book accounts, not farm ones,
    # and reading it as the farm book's move is the same unit error this layer exists to kill.
    wsum_n = sum(p["farm_os"] for p in provinces.values() if p.get("mix_pct") is not None)
    farm_w_mix = (round(sum(p["farm_os"] * p["mix_pct"] for p in provinces.values()
                            if p.get("mix_pct") is not None) / wsum_n, 1) if wsum_n else None)

    nat_rec = _pack(nat)
    nat_rec.update({
        "provinces": len(provinces),
        "farm_weighted_mix_pct": farm_w_mix,
        "book_weighted_mix_pct": ((mix.get("national") or {}).get("book_weighted_shock_pct")),
        "neg_provinces": len(neg_names),
        "neg_province_names": neg_names,
        "neg_farm_n": neg["n"],
        "neg_farm_os": int(round(neg["os"])),
        "neg_current": neg["n_current"],
        "neg_share_of_os_pct": (round(100.0 * neg["os"] / nat["os"], 1) if nat["os"] else None),
    })

    return {
        "meta": {
            "title": "Farm book by baht — national, region, province, branch",
            "generated_by": "pipeline/build_farm_book.py",
            "deterministic": True,
            "network_free": True,
            "label": (
                "MEASURED exposure — farm (เกษตร) accounts, outstanding and bucket counts come from the "
                "real loan tape via tape_geo_occ.json (>=30-account cell floor; per-cell basis carried). "
                "Crop mix and each crop's farm-gate YoY are MEASURED (crop_mix.json). Rainfall % of "
                "normal is MEASURED; drought is MODELLED (OAE SPEI). Farm income level is the NSO/LFS-"
                "anchored estimate from income_impact.json, shown for CONTEXT only — it is not used to "
                "rank anything. No composite index is computed here: the ranking quantity is baht."
            ),
            "ranking": "farm_os (outstanding baht) — replaces the retired agri_stress 0-100 composite",
            "occupation_key": AGRI_OCC,
            "crop_lens_label": (
                "ALLOCATED — the tape records a borrower's occupation, never which crop they grow. "
                "`farm_os_alloc` spreads each province's MEASURED farm book over its MEASURED planted-"
                "area mix, so it is an allocation and reads as an order of magnitude, not a balance. "
                "`pp_of_book` is firmer: measured farm-gate YoY × measured area share, weighted by "
                "measured baht — it is the crop's actual contribution to the book's move. Price, cost "
                "and margin per rai are MEASURED OAE/NABC inputs with DERIVED margin arithmetic; where "
                "OAE reports several field practices the CONSERVATIVE (lowest-margin) measured row is "
                "shown and `alts` counts the others."
            ),
            "sources": ["tape_geo_occ.json", "crop_mix.json", "crop_stress.json", "income_impact.json",
                        "crop_margin.json", "napprang.json"],
            "n_provinces": len(provinces),
            "n_branches": sum(len(v) for v in branches.values()),
        },
        "national": nat_rec,
        "regions": reg_out,
        "provinces": provinces,
        "branches": branches,
        "crops": crops_out,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the committed file reproduces byte-for-byte")
    args = ap.parse_args()

    for need in ("tape_geo_occ.json", "crop_mix.json"):
        if not os.path.exists(os.path.join(P, need)):
            print("build_farm_book.py: SKIP (%s absent)" % need)
            return 0

    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            print("DRIFT: platform/data/farm_book.json missing — run build_farm_book.py")
            return 1
        with open(OUT, encoding="utf-8") as f:
            if f.read() != payload:
                print("DRIFT: platform/data/farm_book.json differs from a fresh build")
                return 1
        n = json.loads(payload)["national"]
        print("OK: farm_book.json reproduces (%d provinces, THB%.2fbn farm book, %.1f%% under a falling mix)"
              % (n["provinces"], n["farm_os"] / 1e9, n["neg_share_of_os_pct"] or 0))
        return 0

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    doc = json.loads(payload)          # read back from the payload, never re-run build()
    n = doc["national"]
    print("wrote %s — %d provinces, %d branches, THB%.2fbn farm book; %d provinces under a falling "
          "mix hold THB%.0fm (%.1f%%), %s accounts, %s still Current"
          % (OUT, n["provinces"], doc["meta"]["n_branches"],
             n["farm_os"] / 1e9, n["neg_provinces"], n["neg_farm_os"] / 1e6,
             n["neg_share_of_os_pct"] or 0, f"{n['neg_farm_n']:,}", f"{n['neg_current']:,}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
