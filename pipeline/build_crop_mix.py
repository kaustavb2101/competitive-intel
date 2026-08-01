#!/usr/bin/env python3
"""
build_crop_mix.py — the FULL per-province crop mix, and what this year's prices do to farm income.

WHY THIS EXISTS
---------------
`income_impact.json` already models a crop-price shock to farm income, but it weights over
**rice, rubber and oilpalm only** — the three crops that had province-level planted area when it was
written. All three are up double digits right now, so that engine reported farm income RISING in
every one of the 77 provinces (+17.9% to +32.1%). That is an artefact of the three crops it could
see, not a reading of the country: it was blind to the two crops that are falling hardest
(coconut -70.9%, sugarcane -17.9%) and to pineapple (-20.0%).

With coconut, pineapple, cassava and maize now mapped from the DOAE farmer registry and sugarcane
from OCSB, all **eight** priced crops have province-level area, so the mix can be weighted properly.
The answer changes materially: four provinces flip NEGATIVE, two of them severely — the Mae Klong
coconut delta (สมุทรสงคราม -66%, สมุทรสาคร -62%) plus ราชบุรี and ประจวบคีรีขันธ์.

AREA BASIS — the honest part
----------------------------
The three area sources do NOT measure the same thing, and the difference is crop-specific, so there
is no single calibration constant. Measured against the planted-area census, DOAE farmer
REGISTRATION covers rice 1.10x, rubber 0.44x, oilpalm 0.58x (rice growers register for support
schemes; rubber growers register with RAOT, not DOAE). Each crop therefore uses the most complete
source that exists for it:

  rice / rubber / oilpalm            planted-area census   (source-data/crop_prov_area.json)
  cassava / maize / coconut / pineapple  DOAE farmer registry  (platform/data/province_cropland.json)
  sugarcane                          OCSB mill returns     (source-data/ocsb_cane.json)

The known bias: the four DOAE-only crops are probably UNDER-weighted against the three census crops,
which tilts the mix toward rice/rubber/palm — and since those three are all rising, it makes the
shock look too OPTIMISTIC. So this basis is conservative in the direction that matters.

`shock_pct_doae_basis` is the sensitivity: the same calculation with rice/rubber/oilpalm ALSO taken
from DOAE, so every crop sits on one registry. It is reported per province and it does not change
the answer — สมุทรสงคราม -66.4% vs -63.9%, ยะลา +37.4% vs +37.0% — which is the point of carrying it.

INCOME
------
`shock_pct` is an area-weighted price move, not an income change. It becomes income the same way
income_impact.json does it: multiplied by that engine's OWN Agriculture crop sensitivity (read from
its meta, never restated here, so the two layers cannot drift apart) and applied to the province's
MEASURED NSO SES farm-income base. ESTIMATED, first-order: every quantity multiplied is measured;
the sensitivity is a documented assumption.

Deterministic + network-free. `--check` reproduces the committed file byte-for-byte.
"""
import os, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
P = os.path.join(ROOT, "platform", "data")
S = os.path.join(ROOT, "source-data")
OUT = os.path.join(P, "crop_mix.json")

RAI_PER_HA = 6.25
# Order is fixed so the emitted per-crop lists can never reorder on dict iteration and break --check.
CROPS = ["rice", "rubber", "oilpalm", "cassava", "maize", "coconut", "pineapple", "sugarcane"]
CENSUS_CROPS = ("rice", "rubber", "oilpalm")          # planted-area census
OCSB_CROPS = ("sugarcane",)                            # OCSB mill returns
CROP_EN = {"rice": "Rice", "rubber": "Rubber", "oilpalm": "Oil palm", "cassava": "Cassava",
           "maize": "Maize", "coconut": "Coconut", "pineapple": "Pineapple", "sugarcane": "Sugarcane"}


def load(*path):
    with open(os.path.join(*path), encoding="utf-8") as f:
        return json.load(f)


def coverage_ratios(doae_by_th, census):
    """DOAE registered area / census planted area, nationally, for the crops in both.

    This is the number that justifies NOT using one basis for everything — it is reported in meta
    so the reader can see the bias rather than take the mixed basis on trust.
    """
    out = {}
    for crop in CENSUS_CROPS:
        d = c = 0.0
        for th, area_c in census.get(crop, {}).items():
            rec = doae_by_th.get(th)
            if rec is None:
                continue
            d += (rec.get(crop) or 0) * RAI_PER_HA
            c += area_c
        out[crop] = round(d / c, 3) if c else None
    return out


def build():
    cropland = load(P, "province_cropland.json")["provinces"]
    census = load(S, "crop_prov_area.json")
    cane = load(S, "ocsb_cane.json")["provinces"]
    yoy = load(S, "farmgate_prices.json")["crop_yoy"]
    income = load(P, "income_impact.json")
    cards = load(P, "impact_cards.json")["provinces"]

    doae_by_th = {v["th"]: v["crops"] for v in cropland.values()}
    en_by_th = {v["th"]: v.get("en") for v in cropland.values()}
    prov_income = income["provinces"]
    sens = (((income.get("meta") or {}).get("sensitivity") or {}).get("Agriculture") or {}).get("crop")

    def area(th, crop, basis):
        if crop in OCSB_CROPS:
            return float((cane.get(th) or {}).get("area_rai") or 0)
        if basis == "mixed" and crop in CENSUS_CROPS:
            return float(census.get(crop, {}).get(th, 0) or 0)
        return float((doae_by_th.get(th, {}).get(crop) or 0) * RAI_PER_HA)

    def shock(th, basis):
        a = [area(th, c, basis) for c in CROPS]
        tot = sum(a)
        if tot <= 0:
            return None, None, None
        shares = [x / tot for x in a]
        return sum(s * yoy[c] for s, c in zip(shares, CROPS)), shares, tot

    provinces = {}
    for th in sorted(prov_income):
        s_mixed, shares, tot = shock(th, "mixed")
        if s_mixed is None:
            continue
        s_doae, _, _ = shock(th, "doae")
        base = ((prov_income[th].get("occ") or {}).get("Agriculture") or {}).get("income")
        acc = (cards.get(th) or {}).get("accounts", 0)
        # per-crop contribution in PERCENTAGE POINTS of the province shock — this is the column that
        # explains the headline (coconut is 95% of สมุทรสงคราม's land, so it IS the -66%).
        contrib = [{"crop": c, "en": CROP_EN[c], "share": round(sh, 4),
                    "yoy": yoy[c], "pp": round(sh * yoy[c], 2)}
                   for sh, c in zip(shares, CROPS) if sh > 0]
        contrib.sort(key=lambda d: (d["pp"], d["crop"]))
        provinces[th] = {
            "en": en_by_th.get(th),
            "region": prov_income[th].get("region"),
            "shock_pct": round(s_mixed, 1),
            "shock_pct_doae_basis": round(s_doae, 1) if s_doae is not None else None,
            "shock_pct_3crop_prior": prov_income[th].get("agri_price_shock_pct"),
            "area_rai": round(tot),
            "income_base_thb": base,
            "income_pct": round(sens * s_mixed, 1) if sens is not None else None,
            "income_thb_month": (round(base * sens * s_mixed / 100.0)
                                 if (sens is not None and base) else None),
            "accounts": acc,
            "crops": contrib,
        }

    neg = sorted((p for p in provinces.values() if p["shock_pct"] < 0), key=lambda p: p["shock_pct"])
    neg_th = [th for th, p in sorted(provinces.items(), key=lambda kv: kv[1]["shock_pct"])
              if p["shock_pct"] < 0]
    ranked = sorted(provinces.items(), key=lambda kv: kv[1]["shock_pct"])
    tot_acc = sum(p["accounts"] for p in provinces.values()) or 1
    # Book-weighted national shock: what the average AutoX farm borrower's crop mix actually did,
    # rather than the average province's (77 provinces are not 77 equal books).
    nat = sum(p["shock_pct"] * p["accounts"] for p in provinces.values()) / tot_acc

    # Region rollup — the entry level of the drill. Weighted by BOOK ACCOUNTS, not by province count
    # or by land: five regions are not five equal books, and the question is what the borrowers we
    # actually lent to are living through.
    regions = {}
    for th, p in provinces.items():
        r = p.get("region") or "—"
        g = regions.setdefault(r, {"provinces": 0, "accounts": 0, "_w": 0.0, "negative": 0,
                                   "worst_prov": None, "worst_shock": None})
        g["provinces"] += 1
        g["accounts"] += p["accounts"]
        g["_w"] += p["shock_pct"] * p["accounts"]
        if p["shock_pct"] < 0:
            g["negative"] += 1
            g["accounts_negative"] = g.get("accounts_negative", 0) + p["accounts"]
        if g["worst_shock"] is None or p["shock_pct"] < g["worst_shock"]:
            g["worst_shock"], g["worst_prov"] = p["shock_pct"], th
    for r, g in regions.items():
        g["shock_pct"] = round(g["_w"] / g["accounts"], 1) if g["accounts"] else None
        g["accounts_negative"] = g.get("accounts_negative", 0)
        del g["_w"]

    return {
        "meta": {
            "title": "Per-province crop mix and the farm-income effect of this year's prices",
            "generated_by": "pipeline/build_crop_mix.py",
            "provenance": "ESTIMATED (first-order). Every quantity multiplied is MEASURED — province "
                          "crop area, Thai farm-gate YoY, NSO SES farm income. The crop→income "
                          "sensitivity is income_impact.json's own documented assumption, read from "
                          "its meta rather than restated here.",
            "method": "shock_pct = Σ(crop share of province crop area × crop Thai farm-gate YoY) over "
                      "8 priced crops. income_pct = crop sensitivity × shock_pct. "
                      "income_thb_month = province NSO SES farm income × income_pct.",
            "why": "income_impact.json weights over rice/rubber/oilpalm only — all three are up, so it "
                   "reported farm income rising in all 77 provinces. That was an artefact of the three "
                   "crops it could see: it was blind to coconut (-70.9%), sugarcane (-17.9%) and "
                   "pineapple (-20.0%). Weighting all eight flips four provinces negative.",
            "area_basis": {
                "rice/rubber/oilpalm": "planted-area census (source-data/crop_prov_area.json)",
                "cassava/maize/coconut/pineapple": "DOAE farmer registry 2568/2025 "
                                                   "(platform/data/province_cropland.json)",
                "sugarcane": "OCSB mill returns 2565/66 (source-data/ocsb_cane.json)",
            },
            "area_basis_note": "The three sources do not measure the same thing and the gap is "
                               "crop-specific, so no single calibration constant applies. Each crop "
                               "uses the most complete source that exists for it. Known bias: the four "
                               "DOAE-only crops are likely UNDER-weighted against the census crops, "
                               "which tilts the mix toward rice/rubber/palm — and as those three are "
                               "all rising, the shock reads too OPTIMISTIC, not too pessimistic.",
            "doae_coverage_vs_census": coverage_ratios(doae_by_th, census),
            "sensitivity_check": "shock_pct_doae_basis repeats the calculation with every crop on the "
                                 "DOAE registry alone. It does not change the answer (สมุทรสงคราม "
                                 "-66.4 vs -63.9, ยะลา +37.4 vs +37.0), which is why the mixed basis "
                                 "is safe to lead with.",
            "crop_sensitivity": sens,
            "crop_yoy_pct": {c: yoy[c] for c in CROPS},
            "crops": CROPS,
        },
        "national": {
            "provinces": len(provinces),
            "negative_provinces": len(neg),
            "negative_province_names": neg_th,
            "accounts_in_negative": sum(p["accounts"] for p in neg),
            "accounts_total": sum(p["accounts"] for p in provinces.values()),
            "book_weighted_shock_pct": round(nat, 1),
            "median_shock_pct": round(sorted(p["shock_pct"] for p in provinces.values())[len(provinces) // 2], 1),
            "worst": [{"prov": th, "shock_pct": p["shock_pct"], "accounts": p["accounts"],
                       "income_thb_month": p["income_thb_month"],
                       "driver": p["crops"][0]["crop"] if p["crops"] else None}
                      for th, p in ranked[:6]],
            "best": [{"prov": th, "shock_pct": p["shock_pct"], "accounts": p["accounts"],
                      "income_thb_month": p["income_thb_month"]}
                     for th, p in ranked[-4:]],
        },
        "regions": dict(sorted(regions.items())),
        "provinces": provinces,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify the committed file reproduces byte-for-byte")
    args = ap.parse_args()

    for need in ("province_cropland.json", "income_impact.json", "impact_cards.json"):
        if not os.path.exists(os.path.join(P, need)):
            print("build_crop_mix.py: SKIP (%s absent)" % need)
            return 0

    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    if args.check:
        if not os.path.exists(OUT):
            print("DRIFT: platform/data/crop_mix.json missing — run build_crop_mix.py")
            return 1
        with open(OUT, encoding="utf-8") as f:
            if f.read() != payload:
                print("DRIFT: platform/data/crop_mix.json differs from a fresh build")
                return 1
        d = json.loads(payload)["national"]
        print("OK: crop_mix.json reproduces (%d provinces, %d negative, %d accounts exposed)"
              % (d["provinces"], d["negative_provinces"], d["accounts_in_negative"]))
        return 0

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    d = json.loads(payload)["national"]
    print("wrote %s — %d provinces, %d negative (%s), %s accounts exposed, book-weighted %+.1f%%"
          % (OUT, d["provinces"], d["negative_provinces"], ", ".join(d["negative_province_names"]),
             f"{d['accounts_in_negative']:,}", d["book_weighted_shock_pct"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
