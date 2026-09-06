#!/usr/bin/env python3
"""Pull the NSO 2023 Agricultural Census (สำมะโนการเกษตร 2566) agri income/debt tables.

Objective #1 (portfolio risk) + objective #2 (competitive risk): the MEASURED, all-77-province
read of how many farm-holders carry debt and — critically — WHICH lender they borrow from. Agri
borrowers who rely on informal, high-cost credit (moneylenders / middlemen / private shops) are
both a distress signal (portfolio) and the competitive space a licensed non-bank title lender
occupies (competition) — a risk lens on the borrower base of the network we already run, NOT a
where-to-open signal.

Source: NSO catalog dataset `income-debt` (376a7d03-42c9-48d3-bd19-07aa82ff6b16), org กองสถิติ
เศรษฐกิจ (สศ.). The clean machine-readable path is the NSO datastore JSON API at
`catalogapi.nso.go.th/api/index?table=<code>&format=json&div=1` — it needs a browser User-Agent
(bare curl/urllib gets HTTP 418). Reachable from CI (any IP). Each row is
`{<dim>, PROVINCE, VALUE, UNIT, SOURCE}`; PROVINCE is a canonical Thai province name (matches
lib.regionmap.REGION exactly, 77/77 — asserted in build_nso_agri_debt.py).

Tables pulled (all "รายจังหวัด" = by province):
  AGC_0506_11_1301  holders reporting agri income, by income band  (→ agri-holder base / denominator)
  AGC_0506_11_1303  holders reporting having debt                  (→ debt incidence)
  AGC_0506_11_1305  holders with agri debt, by SOURCE of loan      (→ lender-source mix)

This is a NETWORK puller — NOT in the determinism gate. It writes a committed, small (~0.4MB) raw
snapshot to source-data/nso/agri_debt_2566.json; the deterministic, --check-gated projection into
platform/data/nso_agri_debt.json is build_nso_agri_debt.py, which reads that committed snapshot with
no network. Re-run this only to refresh the snapshot when NSO publishes a newer census vintage.

    python3 pull_nso_agri_debt.py                 # refresh source-data/nso/agri_debt_2566.json
"""
import argparse
import datetime
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "source-data", "nso", "agri_debt_2566.json")

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
API = "https://catalogapi.nso.go.th/api/index?table={code}&format=json&div=1"

DATASET_ID = "376a7d03-42c9-48d3-bd19-07aa82ff6b16"
DATASET_NAME = "income-debt"
# table code -> (short key, human label)
TABLES = {
    "AGC_0506_11_1301": ("income", "ผู้ถือครองที่รายงานรายได้ทางการเกษตร จำแนกตามช่วงรายได้ รายจังหวัด"),
    "AGC_0506_11_1303": ("debt_incidence", "ผู้ถือครองที่รายงานการมีหนี้สิน รายจังหวัด"),
    "AGC_0506_11_1305": ("loan_source", "ผู้ถือครองที่มีหนี้สินเพื่อการเกษตร จำแนกตามแหล่งเงินกู้ รายจังหวัด"),
}


def _fetch(url, timeout=90):
    safe = urllib.parse.quote(url, safe=":/?&=%#@+,;~")
    req = urllib.request.Request(safe, headers={
        "User-Agent": BROWSER_UA,
        "Accept": "application/json",
        "Referer": "https://catalog.nso.go.th/",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def main():
    ap = argparse.ArgumentParser(description="Pull NSO 2566 agri income/debt tables → committed raw snapshot.")
    ap.add_argument("--out", default=OUT, help="output path (default source-data/nso/agri_debt_2566.json)")
    args = ap.parse_args()

    tables, failed = {}, []
    for code, (key, label) in TABLES.items():
        url = API.format(code=code)
        try:
            st, body = _fetch(url)
            rows = json.loads(body) if st == 200 else None
            if st == 200 and isinstance(rows, list) and rows:
                tables[key] = {"table": code, "label": label, "rows": rows}
                print(f"  ok  {code} ({key}): {len(rows)} rows")
            else:
                failed.append((code, f"HTTP {st}, {len(body or b'')}B, not a row list"))
                print(f"  FAIL {code}: HTTP {st}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
            failed.append((code, str(e)))
            print(f"  FAIL {code}: {e}")
        time.sleep(0.4)

    if failed:
        # Never overwrite the committed snapshot with a partial pull — a block must not be laundered
        # into a shrunken layer. Leave the existing snapshot untouched and report.
        print(f"\nABORT: {len(failed)} table(s) failed; committed snapshot left untouched.")
        for c, e in failed:
            print(f"    {c}: {e}")
        return 1

    snapshot = {
        "meta": {
            "source": "NSO Agricultural Census 2566 (2023)",
            "source_th": "สำมะโนการเกษตร พ.ศ. 2566 — สำนักงานสถิติแห่งชาติ",
            "dataset": DATASET_NAME,
            "dataset_id": DATASET_ID,
            "catalog": "https://catalog.nso.go.th/dataset/" + DATASET_ID,
            "api": "catalogapi.nso.go.th/api/index (datastore JSON, browser-UA)",
            "provenance": "MEASURED — full-count agricultural census, by province.",
            "unit": "ราย (agricultural holders)",
            "pulled_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
            "tables": {v[0]: k for k, v in TABLES.items()},
        },
        "tables": tables,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"\nwrote {os.path.relpath(args.out, ROOT)} ({os.path.getsize(args.out)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
