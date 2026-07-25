#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prune_gdcatalog_harvest.py — delete already-downloaded harvest files that are NOT relevant to
AutoX, using the SAME rule the harvester uses (gdcatalog_relevance.is_relevant).

Directive: "delete what isn't relevant." This reclaims disk from the blind full-catalog sweep while
keeping the catalog INDEX intact (100% coverage) — so every deletion is reversible: the URL of each
removed file is written to _pruned.jsonl, and the dataset still exists in _catalog.jsonl.

  python3 prune_gdcatalog_harvest.py                 # DRY RUN — report what would be deleted
  python3 prune_gdcatalog_harvest.py --apply         # actually delete + log to _pruned.jsonl
  python3 prune_gdcatalog_harvest.py --host gdcatalog.go.th --apply
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from gdcatalog_relevance import is_relevant


def load_catalog_meta(base):
    """dataset name -> (org, title, notes) from the retained index."""
    meta = {}
    p = os.path.join(base, "_catalog.jsonl")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                meta[d.get("name")] = (d.get("org"), d.get("title"), d.get("notes"))
    return meta


def gb(b):
    return "%.2f GB" % (b / 1e9) if b >= 1e9 else "%.0f MB" % (b / 1e6)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="gdcatalog.go.th")
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    a = ap.parse_args()

    base = os.path.join(ROOT, "source-data", "gdcatalog_harvest", a.host)
    if not os.path.isdir(base):
        print("no harvest dir:", base)
        return
    meta = load_catalog_meta(base)
    manifest = os.path.join(base, "_manifest.jsonl")
    pruned_log = os.path.join(base, "_pruned.jsonl")

    del_files = del_bytes = keep_files = keep_bytes = missing = 0
    to_delete = []  # (abspath, rec)
    with open(manifest, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            rel = r.get("path")
            if not rel:
                continue  # skipped/failed — nothing on disk
            dsname = r.get("dataset")
            if dsname in meta:
                org, title, notes = meta[dsname]
            else:
                org, title, notes = r.get("org"), r.get("name"), ""
            if is_relevant(org, title, notes):
                keep_files += 1
                keep_bytes += r.get("bytes") or 0
                continue
            ap_ = os.path.join(base, rel)
            b = r.get("bytes") or 0
            del_files += 1
            del_bytes += b
            to_delete.append((ap_, r))
            # also the PDF extract sidecar, if any
            if r.get("extract"):
                to_delete.append((os.path.join(base, r["extract"]), None))

    print("harvest:", base)
    print("KEEP: %d files %s" % (keep_files, gb(keep_bytes)))
    print("DROP: %d files %s  (irrelevant)" % (del_files, gb(del_bytes)))
    if not a.apply:
        print("\nDRY RUN — nothing deleted. Re-run with --apply to reclaim %s." % gb(del_bytes))
        return

    plog = open(pruned_log, "a", encoding="utf-8")
    freed = 0
    for path, rec in to_delete:
        try:
            if os.path.exists(path):
                sz = os.path.getsize(path)
                os.remove(path)
                freed += sz
            if rec is not None:
                plog.write(json.dumps({"path": rec.get("path"), "url": rec.get("url"),
                                       "dataset": rec.get("dataset"), "org": rec.get("org"),
                                       "bytes": rec.get("bytes")}, ensure_ascii=False) + "\n")
        except OSError:
            missing += 1
    plog.close()

    # remove now-empty dataset dirs
    removed_dirs = 0
    for sub in ("data", "extracted"):
        d = os.path.join(base, sub)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if os.path.isdir(p) and not os.listdir(p):
                try:
                    os.rmdir(p)
                    removed_dirs += 1
                except OSError:
                    pass
    print("\nAPPLIED: freed %s · %d empty dirs removed · log -> _pruned.jsonl (reversible)"
          % (gb(freed), removed_dirs))


if __name__ == "__main__":
    main()
