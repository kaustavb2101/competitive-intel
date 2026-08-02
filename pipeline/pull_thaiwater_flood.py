#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_thaiwater_flood.py — LIVE measured river/reservoir WATER-LEVEL flood pulse per province.

Source: api-v3.thaiwater.net /public/waterlevel_load — ~780 live water-level stations (RID/DWR…),
each with a situation_level (1 critical-low → 4 high-water → 5 bank-overflow), diff-to-bank and
storage_percent, plus a geocode carrying the province. Keyless, cloud-reachable.

Why (objective #1): the rain pulse (pull_thaiwater_rain.py) is water ARRIVING; this is water ON THE
GROUND — high river levels / bank overflow are the immediate flood event that stalls borrower income
and blocks collections in a province, days before it shows in any monthly series. The twin signal to
the rain pulse, on the same Overview strip.

situation_level (ThaiWater convention): 1 = critical low, 2 = low, 3 = normal, 4 = high water,
5 = bank overflow (flood). We count stations at level ≥ 4 (high / flood) per province.

Writes the compact per-province aggregate → platform/data/thaiwater_flood.json (served directly).
Network puller (live telemetry snapshot) — NOT in the determinism gate, same class as the rain pull.

  python3 pull_thaiwater_flood.py
  python3 pull_thaiwater_flood.py --stamp 2026-07-11
"""
import argparse, json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.regionmap import REGION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "platform", "data", "thaiwater_flood.json")
URL = "https://api-v3.thaiwater.net/api/v1/thaiwater30/public/waterlevel_load"
UA = {"User-Agent": "autox-credit-intel/1.0"}
HIGH_LEVEL = 4   # situation_level >= 4 = high water / flood watch


def _get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default="")
    args = ap.parse_args()
    payload = _get(URL).get("waterlevel_data") or {}
    rows = payload.get("data") or []
    if len(rows) < 300:
        sys.exit("pull_thaiwater_flood.py: only %d stations — likely truncated; not writing." % len(rows))
    prov = {}
    foreign = {}
    latest_dt = ""
    for r in rows:
        g = r.get("geocode") or {}
        p = ((g.get("province_name") or {}).get("th") or "").strip()
        lvl = r.get("situation_level")
        if not p or not isinstance(lvl, int):
            continue
        # ThaiWater's network reaches upstream onto the shared Salween/Mekong systems, so a handful
        # of stations geocode to a NEIGHBOURING COUNTRY, not a Thai province. They arrived filed
        # under "สาธารณรัฐแห่งสหภาพเมียนมา" and every consumer treated that string as a province:
        # the Overview card ranked it 2nd on the 24h-rainfall table, and it padded the "N provinces
        # at high water" count by one. Gate on the canonical 77-province registry — an unknown key
        # is counted out loud in meta.foreign_dropped rather than silently discarded, because a
        # Thai province that ever failed this test would otherwise vanish without a trace.
        if p not in REGION:
            foreign[p] = foreign.get(p, 0) + 1
            continue
        latest_dt = max(latest_dt, r.get("waterlevel_datetime") or "")
        e = prov.setdefault(p, {"n": 0, "high": 0, "max_level": 0})
        e["n"] += 1
        e["max_level"] = max(e["max_level"], lvl)
        if lvl >= HIGH_LEVEL:
            e["high"] += 1
    out = {}
    for p, e in prov.items():
        out[p] = {
            "n_stations": e["n"],
            "n_high": e["high"],                                    # stations at level ≥ 4
            "pct_high": round(100.0 * e["high"] / e["n"], 1),
            "max_level": e["max_level"],                            # worst situation_level in province
        }
    doc = {
        "meta": {
            "source": "ThaiWater (api-v3.thaiwater.net /public/waterlevel_load) — live river/reservoir "
                      "water-level telemetry (RID/DWR networks). Keyless, cloud-reachable.",
            "label": "MEASURED — live water-level flood pulse per province (station aggregate). "
                     "n_high = stations at situation_level ≥ 4 (high water / bank overflow); "
                     "max_level = worst level in the province (5 = overflow flood).",
            "generated_by": "pipeline/pull_thaiwater_flood.py",
            "pulled": args.stamp,
            "observed_to": latest_dt,
            "n_stations": sum(v["n_stations"] for v in out.values()),
            "n_provinces": len(out),
            # Stations the feed geocoded outside Thailand, kept visible so the drop is auditable.
            "foreign_dropped": {k: foreign[k] for k in sorted(foreign)},
            "levels": {"1": "critical low", "2": "low", "3": "normal", "4": "high water", "5": "bank overflow (flood)"},
        },
        "provinces": {k: out[k] for k in sorted(out)},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    worst = sorted(out.items(), key=lambda x: (-x[1]["max_level"], -x[1]["pct_high"]))[:5]
    print("wrote %s — %d stations, %d provinces (obs to %s)" % (
        OUT, doc["meta"]["n_stations"], len(out), latest_dt))
    for p, v in worst:
        print("   %-16s level %d · %d/%d stations high (%.0f%%)" % (
            p, v["max_level"], v["n_high"], v["n_stations"], v["pct_high"]))


if __name__ == "__main__":
    main()
