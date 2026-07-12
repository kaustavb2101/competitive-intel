#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_dlt_all.py — mirror EVERY dataset on DLT's gdcatalog (gdcatalog.dlt.go.th, the geoblock bypass).

The host is INTERMITTENT, so this puller is RESUMABLE and greedy: it enumerates package_list,
downloads every CSV/XLSX/JSON resource it doesn't already have into source-data/dlt/raw/<dataset>/,
and skips files that already exist — re-run it whenever a window opens and it fills the gaps.
Tiny responses (<200 bytes) are treated as upstream stubs and recorded, not saved.

Writes an inventory → source-data/dlt/raw/INVENTORY.json (dataset → resources, sizes, rows, stubs)
so downstream builders and future sessions know exactly what's mirrored.

  python3 pull_dlt_all.py                # pull everything missing
  python3 pull_dlt_all.py --list         # just enumerate, no downloads
  python3 pull_dlt_all.py --stamp 2026-07-10
"""
import argparse, json, os, re, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "source-data", "dlt", "raw")
BASE = "https://gdcatalog.dlt.go.th/api/3/action/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
FORMATS = {"CSV", "XLSX", "JSON"}
STUB_BYTES = 200          # smaller than this = upstream stub (recorded, not saved)


def _get(url, tries=4, timeout=90):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(4 * (i + 1))
    raise RuntimeError("GET failed after %d tries: %s" % (tries, last))


def _safe(name):
    s = re.sub(r"[^\wก-๙.\- ]+", "_", (name or "resource")).strip().replace(" ", "_")
    return s[:120]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--stamp", default="")
    args = ap.parse_args()
    names = json.loads(_get(BASE + "package_list"))["result"]
    print("DLT catalog: %d datasets" % len(names))
    os.makedirs(RAW, exist_ok=True)
    inv_path = os.path.join(RAW, "INVENTORY.json")
    inv = json.load(open(inv_path)) if os.path.exists(inv_path) else {"meta": {}, "datasets": {}}
    got = skipped = stubs = failed = 0
    for ds in names:
        try:
            pkg = json.loads(_get(BASE + "package_show?id=" + ds))["result"]
        except Exception as e:
            print("  [ERR] %s: %s" % (ds, str(e)[:60])); failed += 1
            continue
        entry = inv["datasets"].setdefault(ds, {"title": pkg.get("title", ""), "resources": {}})
        entry["title"] = pkg.get("title", "")
        ddir = os.path.join(RAW, ds)
        res_list = [r for r in pkg.get("resources", []) if (r.get("format") or "").upper() in FORMATS]
        print("  %s — %s (%d resources)" % (ds, pkg.get("title", "")[:48], len(res_list)))
        if args.list:
            continue
        os.makedirs(ddir, exist_ok=True)
        for r in res_list:
            fmt = (r.get("format") or "").lower()
            fn = _safe(r.get("name", r.get("id", "res"))) + "." + fmt
            path = os.path.join(ddir, fn)
            rec = entry["resources"].get(fn)
            if os.path.exists(path):
                # already mirrored (possibly by a run killed before it wrote the inventory) —
                # make sure the inventory records it from disk.
                if not rec:
                    raw_sz = os.path.getsize(path)
                    rows = open(path, "rb").read().count(b"\n") if fmt == "csv" else None
                    entry["resources"][fn] = {"bytes": raw_sz, "rows": rows, "url": r["url"]}
                skipped += 1
                continue
            if rec and rec.get("stub"):
                skipped += 1
                continue
            try:
                raw = _get(r["url"], tries=3)
            except Exception as e:
                print("     [ERR] %s: %s" % (fn[:50], str(e)[:50])); failed += 1
                continue
            if len(raw) < STUB_BYTES:
                entry["resources"][fn] = {"stub": True, "bytes": len(raw), "url": r["url"]}
                stubs += 1
                continue
            open(path, "wb").write(raw)
            rows = raw.count(b"\n") if fmt == "csv" else None
            entry["resources"][fn] = {"bytes": len(raw), "rows": rows, "url": r["url"]}
            got += 1
    if not args.list:
        inv["meta"] = {
            "source": "gdcatalog.dlt.go.th (DLT's own catalog — bypasses the data.go.th geoblock; INTERMITTENT host)",
            "label": "MEASURED — raw mirror of every CSV/XLSX/JSON resource on the DLT catalog. Resumable; re-run pull_dlt_all.py when a window opens.",
            "generated_by": "pipeline/pull_dlt_all.py",
            "last_pull": args.stamp,
            "n_datasets": len(names),
            "n_files": sum(1 for d in inv["datasets"].values() for k, v in d["resources"].items() if not v.get("stub")),
            "n_stubs": sum(1 for d in inv["datasets"].values() for v in d["resources"].values() if v.get("stub")),
        }
        with open(inv_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(inv, ensure_ascii=False, indent=1))
        total_mb = sum(v.get("bytes", 0) for d in inv["datasets"].values()
                       for v in d["resources"].values() if not v.get("stub")) / 1e6
        print("\ndone: +%d new, %d already had, %d stubs, %d failed · mirror %.1f MB · inventory written" % (
            got, skipped, stubs, failed, total_mb))


if __name__ == "__main__":
    main()
