#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_oae_napprang.py — OAE dry-season (SECOND) rice-crop production per province (objective #1).

Pulls ปริมาณการผลิตข้าวนาปรัง (dry-season / irrigated SECOND rice crop) per province from the OAE
CKAN catalog (catalog.oae.go.th, dataset slug `dataoae1104`) → source-data/oae_napprang.json.

WHY (committee Area-2 finding, 2026-07-10): the Central/West drought pocket looks income-cushioned
because the rice-price tailwind hides a 56%-of-normal rainfall reading. The committee said the risk
"crystallizes IF the irrigated second rice crop is cut." This is the MEASURED read of exactly that:
  - napprang PLANTED area per province = how much farm income depends on the dry-season second crop.
  - harvested < planted = the second crop that was planted but NOT brought in this season
    (abandonment) — a measured "the second crop got cut" signal, per province, this year.

Pairs with the crop_stress drought_watch flag (rice-share + rain deficit): the flag says WHERE the
water deficit sits; this layer says HOW MUCH second-crop income is exposed there and how much was
already lost this year. Nothing modelled — real OAE area/production numbers only.

FLOW (network — run from a host that can reach catalog.oae.go.th; CI runners can):
  1. package_show?id=dataoae1104  (stable slug, never a rotating resource id).
  2. Pick the newest per-province napprang CSV (name carries ปี <BE year>, has province_name column).
  3. Parse per-province planted / harvested / production; compute abandonment = 1 - harvested/planted.
  4. Write with full provenance meta; vintage read FROM THE DATA (the BE year in the resource).

DETERMINISM: `pulled` comes only from --stamp; a re-run with the same upstream + same --stamp is
byte-identical. Fails loudly and writes nothing if <50 provinces parse (never demote with junk).

  python3 pull_oae_napprang.py --stamp 2026-07-11     # real pull + write
  python3 pull_oae_napprang.py --dry-run              # resolve + list candidate CSVs only
"""
import argparse, csv, io, json, os, ssl, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPE)
from regionmap import canonical, REGION

OUT = os.path.join(ROOT, "source-data", "oae_napprang.json")
PKG = "https://catalog.oae.go.th/api/3/action/package_show?id=dataoae1104"
CA = "/root/.ccr/ca-bundle.crt"
MIN_PROV = 50

# OAE attribute (Thai) -> our field
ATTR = {"เนื้อที่เพาะปลูก": "planted_rai", "เนื้อที่เก็บเกี่ยว": "harvested_rai", "ผลผลิต": "production_tons"}


def _ctx():
    return ssl.create_default_context(cafile=CA) if os.path.exists(CA) else None


def _get(url):
    return urllib.request.urlopen(url, timeout=60, context=_ctx()).read()


def _resolve_csv():
    """Newest per-province napprang CSV: (url, be_year, name). Never a hardcoded resource id."""
    meta = json.loads(_get(PKG))
    cands = []
    for r in meta["result"].get("resources", []):
        nm = r.get("name", "")
        if (r.get("format", "").upper() == "CSV" and "นาปรัง" in nm and "ระดับประเทศ" not in nm):
            # name looks like "…ข้าวนาปรัง ปี 2568" — pull the BE year
            be = "".join(ch for ch in nm.split("ปี")[-1] if ch.isdigit())[:4]
            if be:
                cands.append((int(be), r["url"], nm))
    cands.sort(reverse=True)  # newest BE year first
    return cands


def build(stamp):
    cands = _resolve_csv()
    if not cands:
        sys.exit("pull_oae_napprang.py: no per-province napprang CSV in dataoae1104 — abort (wrote nothing).")
    be, url, name = cands[0]
    ce = be - 543
    raw = _get(url).decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(raw)))
    hdr = rows[0]
    ix = {h: i for i, h in enumerate(hdr)}
    need = ("province_name", "attribute", "amount")
    if not all(k in ix for k in need):
        sys.exit("pull_oae_napprang.py: unexpected header %s — abort." % hdr)
    prov = {}
    for r in rows[1:]:
        if len(r) <= max(ix.values()):
            continue
        pname = r[ix["province_name"]].strip()
        if pname in ("ประเทศไทย", "", "รวม"):   # skip national/aggregate rows
            continue
        c = canonical(pname)
        if not c:
            continue
        attr = ATTR.get(r[ix["attribute"]].strip())
        if not attr:
            continue
        try:
            v = float(str(r[ix["amount"]]).replace(",", "").strip() or 0)
        except ValueError:
            continue
        prov.setdefault(c, {"th": c, "region": REGION.get(c)})[attr] = v
    out = []
    for c, e in prov.items():
        pl, hv = e.get("planted_rai"), e.get("harvested_rai")
        e["abandon_pct"] = round(100.0 * (1 - hv / pl), 1) if (pl and hv is not None and pl > 0) else None
        out.append(e)
    if len(out) < MIN_PROV:
        sys.exit("pull_oae_napprang.py: only %d provinces parsed (<%d) — abort (wrote nothing)." % (len(out), MIN_PROV))
    out.sort(key=lambda r: (-(r.get("planted_rai") or 0), r["th"]))
    nat = {k: round(sum(r.get(k) or 0 for r in out)) for k in ("planted_rai", "harvested_rai", "production_tons")}
    nat["abandon_pct"] = round(100.0 * (1 - nat["harvested_rai"] / nat["planted_rai"]), 1) if nat["planted_rai"] else None
    return {
        "meta": {
            "title": "OAE dry-season (second) rice-crop production per province — measured",
            "generated_by": "pipeline/pull_oae_napprang.py",
            "label": "MEASURED — OAE ข้าวนาปรัง (dry-season/irrigated SECOND rice crop) planted + "
                     "harvested area (rai) and production (tons) per province. abandon_pct = "
                     "1 - harvested/planted (the second crop planted but not brought in this season).",
            "source": "catalog.oae.go.th dataset dataoae1104 — %s" % name,
            "resource_url": url,
            "vintage": "%d (BE %d)" % (ce, be),
            "pulled": stamp,
            "n_provinces": len(out),
            "national": nat,
            "why": "committee Area-2 (2026-07-10): the drought-watch provinces' income cushion "
                   "'disappears if the irrigated second crop is cut' — this is the measured "
                   "second-crop exposure + this-season abandonment behind that flag.",
        },
        "provinces": out,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", help="YYYY-MM-DD pull date embedded in meta.pulled (required to write)")
    ap.add_argument("--dry-run", action="store_true", help="resolve + list candidate CSVs only")
    args = ap.parse_args()
    if args.dry_run:
        for be, url, nm in _resolve_csv():
            print("BE %d  %s" % (be, nm))
        return
    if not args.stamp:
        sys.exit("pull_oae_napprang.py: --stamp YYYY-MM-DD required for a real write.")
    data = build(args.stamp)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    n = data["meta"]["national"]
    print("wrote %s — %s, %d provinces, national planted %s rai, abandonment %.1f%%" % (
        OUT, data["meta"]["vintage"], data["meta"]["n_provinces"],
        format(n["planted_rai"], ","), n["abandon_pct"]))
    for r in data["provinces"][:5]:
        print("   %-16s planted %s rai · abandon %s%%" % (
            r["th"], format(int(r.get("planted_rai") or 0), ","), r.get("abandon_pct")))


if __name__ == "__main__":
    main()
