#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_thaiwater_rain.py — LIVE measured 24h rainfall per province (ThaiWater telemetry, keyless).

Source: api-v3.thaiwater.net /public/rain_24h — ~4.5k live rain-gauge stations (DWR/TMD/EGAT…),
each with rain_24h (mm), province, amphoe and coordinates. Reachable from any cloud IP.

Why (objective #1): this is the real-time FLOOD/soak pulse to pair with the slower satellite
rainfall-anomaly drought signal — heavy 24h rain over a crop province is an immediate
collections/collateral event (flooded fields, stalled borrower income), not a monthly average.
Thai Met convention: ≥35.1mm/24h = heavy (ฝนตกหนัก), ≥90.1mm = very heavy (หนักมาก).

Writes the compact per-province aggregate → source-data/thaiwater_rain.json:
{meta, provinces: {<th-name>: {n_stations, max_mm, p90_mm, pct_heavy, pct_very_heavy}}}.
Network puller (live telemetry snapshot) — NOT in the determinism gate.

  python3 pull_thaiwater_rain.py
  python3 pull_thaiwater_rain.py --stamp 2026-07-10
"""
import argparse, json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.regionmap import REGION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "platform", "data", "thaiwater_rain.json")   # served directly to the frontend
URL = "https://api-v3.thaiwater.net/api/v1/thaiwater30/public/rain_24h"
UA = {"User-Agent": "autox-credit-intel/1.0"}
HEAVY_MM, VERY_HEAVY_MM = 35.1, 90.1


def _get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stamp", default="")
    args = ap.parse_args()
    rows = _get(URL).get("data") or []
    if len(rows) < 1000:
        sys.exit("pull_thaiwater_rain.py: only %d stations — likely truncated; not writing." % len(rows))
    prov = {}
    foreign = {}
    latest_dt = ""
    for r in rows:
        g = r.get("geocode") or {}
        p = ((g.get("province_name") or {}).get("th") or "").strip()
        mm = r.get("rain_24h")
        if not p or not isinstance(mm, (int, float)):
            continue
        # Same cross-border gauges as the flood pull — see pull_thaiwater_flood.py. On this layer it
        # was worse than a miscount: Myanmar rendered SECOND on the Overview's 24h-rainfall table,
        # above every Thai province but Chiang Mai.
        if p not in REGION:
            foreign[p] = foreign.get(p, 0) + 1
            continue
        latest_dt = max(latest_dt, r.get("rainfall_datetime") or "")
        prov.setdefault(p, []).append(float(mm))
    out = {}
    for p, vals in prov.items():
        vals.sort()
        n = len(vals)
        out[p] = {
            "n_stations": n,
            "max_mm": round(vals[-1], 1),
            "p90_mm": round(vals[int(0.9 * (n - 1))], 1),
            "pct_heavy": round(100.0 * sum(1 for v in vals if v >= HEAVY_MM) / n, 1),
            "pct_very_heavy": round(100.0 * sum(1 for v in vals if v >= VERY_HEAVY_MM) / n, 1),
        }
    doc = {
        "meta": {
            "source": "ThaiWater (api-v3.thaiwater.net /public/rain_24h) — live rain-gauge telemetry "
                      "(DWR/TMD/EGAT networks). Keyless, cloud-reachable.",
            "label": "MEASURED — live 24h rainfall per province (station aggregate). The real-time "
                     "flood/soak pulse; thresholds per Thai Met convention (heavy ≥35.1mm, very heavy ≥90.1mm/24h).",
            "generated_by": "pipeline/pull_thaiwater_rain.py",
            "pulled": args.stamp,
            "observed_to": latest_dt,
            "n_stations": sum(v["n_stations"] for v in out.values()),
            "n_provinces": len(out),
            # Stations the feed geocoded outside Thailand, kept visible so the drop is auditable.
            "foreign_dropped": {k: foreign[k] for k in sorted(foreign)},
        },
        "provinces": {k: out[k] for k in sorted(out)},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    worst = sorted(out.items(), key=lambda x: -x[1]["max_mm"])[:3]
    print("wrote %s — %d stations, %d provinces (obs to %s)" % (
        OUT, doc["meta"]["n_stations"], len(out), latest_dt))
    for p, v in worst:
        print("   wettest: %s max %.0fmm, %s%% stations heavy" % (p, v["max_mm"], v["pct_heavy"]))


if __name__ == "__main__":
    main()
