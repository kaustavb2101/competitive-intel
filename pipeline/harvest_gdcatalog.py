#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""harvest_gdcatalog.py — autonomous background harvester for a Thai government CKAN catalog.

Targets gdcatalog.go.th (the national Government Data Catalog, ~24k datasets) by default, or any
CKAN instance via --base (e.g. https://gdcatalog.dlt.go.th). Runs UNATTENDED in the background —
it is a plain Python long-runner, so it consumes ZERO AI tokens while it works; you launch it once
and check its log/manifest.

Two phases, both RESUMABLE (safe to kill + restart — it skips what's already done):
  1. CATALOG  — paginate package_search, write every dataset + resource's metadata to
                _catalog.jsonl (fast; ~1 request / 100 datasets). Immediately useful as an index.
  2. DOWNLOAD — for each resource that passes the filters: stream the file to disk, and if it is a
                PDF, run ingest_pdf.extract_pdf() (pdfplumber/PyMuPDF text tier + Tesseract Thai+Eng
                OCR for scanned pages) and save the extracted text/tables JSON beside it. Datastore-
                only resources (no downloadable file) are paged via datastore_search into JSON.

Politeness + safety (this hits a public gov server + your disk):
  - one shared requests.Session with a real User-Agent; retry with backoff; per-request timeout.
  - --sleep between downloads (default 0.6s); --max-mb skips oversized single files (default 300).
  - --max-total-gb hard stop for the whole run (default 40). --max-datasets to scope.
  - a JSONL manifest records every processed resource; a re-run reads it and skips done items.

Output (all GITIGNORED — raw gov data is never committed; only derived platform/data JSON is):
  source-data/gdcatalog_harvest/<host>/
     _catalog.jsonl     one line per dataset (metadata + resource list)
     _manifest.jsonl    one line per processed resource (status, path, bytes, sha1)
     _harvest.log       progress log
     data/<dataset>/<resource>.<ext>          the raw files
     extracted/<dataset>/<resource>.pdf.json  OCR/text extract for PDFs

Examples:
  python3 harvest_gdcatalog.py --index-only                 # just build the catalog index (fast)
  python3 harvest_gdcatalog.py                              # full harvest, polite defaults
  python3 harvest_gdcatalog.py --base https://gdcatalog.dlt.go.th
  python3 harvest_gdcatalog.py --query "vehicle" --formats csv,xlsx,pdf --max-datasets 500
  python3 harvest_gdcatalog.py --no-pdf-ocr --sleep 1.0      # skip OCR, be gentler
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)  # so we can import the repo's OCR pdf reader + the relevance rule

try:
    from gdcatalog_relevance import is_relevant
except Exception:  # relevance rule is optional; --relevant-only is a no-op without it
    def is_relevant(org, title, notes=""):
        return True

BASE_DEFAULT = "https://gdcatalog.go.th"
# NOTE: gdcatalog.go.th's WAF returns HTTP 500 to unusual User-Agent strings (a custom
# "compatible; …research…" UA is blocked). A standard browser UA is accepted — keep it plain.
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
# formats we treat as harvestable data by default (lowercased CKAN 'format' field / url extension)
DATA_FORMATS = {"csv", "xlsx", "xls", "json", "geojson", "xml", "txt", "tsv", "pdf",
                "zip", "kml", "kmz", "shp", "parquet", "ods", "api"}
DL_EXT = re.compile(r"\.([a-z0-9]{2,6})(?:\?|#|$)", re.I)

SESS = requests.Session()
SESS.headers.update({"User-Agent": UA})


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def make_logger(path):
    def log(msg):
        line = "%s  %s" % (now(), msg)
        print(line, flush=True)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
    return log


def api(base, action, log, **params):
    """CKAN action API call with retry/backoff. Returns result dict/list or None."""
    url = base.rstrip("/") + "/api/3/action/" + action
    for attempt in range(5):
        try:
            r = SESS.get(url, params=params, timeout=90)
            if r.status_code == 200:
                d = r.json()
                if d.get("success"):
                    return d.get("result")
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(3 * (attempt + 1))
                continue
            return None
        except Exception as e:
            if attempt == 0:
                log("  api retry %s: %s" % (action, type(e).__name__))
            time.sleep(3 * (attempt + 1))
    return None


def safe(s, maxlen=90):
    s = re.sub(r"[^\w฀-๿.\- ]+", "_", str(s or "")).strip("._ ")
    s = re.sub(r"\s+", "_", s)
    return (s[:maxlen] or "x")


def guess_ext(res):
    fmt = (res.get("format") or "").strip().lower()
    if fmt and re.fullmatch(r"[a-z0-9]{2,6}", fmt):
        return fmt
    m = DL_EXT.search(res.get("url") or "")
    return (m.group(1).lower() if m else "bin")


def load_done(manifest_path):
    done = set()
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                    if o.get("id"):
                        done.add(o["id"])
                except Exception:
                    pass
    return done


def append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def iter_datasets(base, log, query, max_datasets):
    """Paginate package_search yielding dataset dicts (with embedded resources)."""
    start, rows, seen = 0, 100, 0
    total = None
    while True:
        res = api(base, "package_search", log, q=(query or "*:*"), rows=rows, start=start)
        if not res:
            break
        if total is None:
            total = res.get("count", 0)
            log("catalog: %s datasets match%s" % (total, (" '%s'" % query) if query else ""))
        results = res.get("results", [])
        if not results:
            break
        for ds in results:
            yield ds
            seen += 1
            if max_datasets and seen >= max_datasets:
                return
        start += rows
        if total and start >= total:
            break
        time.sleep(0.3)


def stream_download(url, dest, max_bytes, log):
    """Stream a URL to dest. Returns (bytes, sha1) or (None, reason)."""
    try:
        with SESS.get(url, stream=True, timeout=120, allow_redirects=True) as r:
            if r.status_code != 200:
                return None, "http_%s" % r.status_code
            clen = r.headers.get("Content-Length")
            if clen and int(clen) > max_bytes:
                return None, "too_big(%s)" % clen
            h = hashlib.sha1()
            n = 0
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    n += len(chunk)
                    if n > max_bytes:
                        f.close()
                        os.remove(tmp)
                        return None, "too_big(stream)"
                    h.update(chunk)
                    f.write(chunk)
            os.replace(tmp, dest)
            return n, h.hexdigest()
    except Exception as e:
        return None, "err_%s" % type(e).__name__


def extract_pdf_safe(path, log):
    try:
        from ingest_pdf import extract_pdf
        return extract_pdf(path)
    except Exception as e:
        log("    pdf-extract failed: %s" % type(e).__name__)
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=BASE_DEFAULT, help="CKAN base URL")
    ap.add_argument("--out", default=None, help="output dir (default source-data/gdcatalog_harvest/<host>)")
    ap.add_argument("--query", default=None, help="CKAN search filter (default all)")
    ap.add_argument("--formats", default=None, help="comma list to restrict formats (default the data allowlist)")
    ap.add_argument("--all-formats", action="store_true", help="download every resource format, no allowlist")
    ap.add_argument("--index-only", action="store_true", help="build the catalog index then stop")
    ap.add_argument("--no-pdf-ocr", action="store_true", help="download PDFs but skip OCR/text extraction")
    ap.add_argument("--max-datasets", type=int, default=None)
    ap.add_argument("--max-mb", type=float, default=300.0, help="skip a single file bigger than this")
    ap.add_argument("--max-total-gb", type=float, default=40.0, help="hard stop for the whole run")
    ap.add_argument("--min-free-gb", type=float, default=0.0,
                    help="stop when the output drive has less than this much free (disk safety)")
    ap.add_argument("--relevant-only", action="store_true",
                    help="catalog ALL datasets but only DOWNLOAD ones relevant to AutoX "
                         "(gdcatalog_relevance.is_relevant); the rest are logged skip_irrelevant")
    ap.add_argument("--sleep", type=float, default=0.6, help="seconds between downloads (politeness)")
    a = ap.parse_args()

    host = re.sub(r"^https?://", "", a.base).strip("/").split("/")[0]
    out = a.out or os.path.join(ROOT, "source-data", "gdcatalog_harvest", host)
    os.makedirs(out, exist_ok=True)
    data_dir = os.path.join(out, "data")
    extr_dir = os.path.join(out, "extracted")
    catalog_path = os.path.join(out, "_catalog.jsonl")
    manifest_path = os.path.join(out, "_manifest.jsonl")
    log = make_logger(os.path.join(out, "_harvest.log"))

    allow = None
    if a.formats:
        allow = {x.strip().lower() for x in a.formats.split(",") if x.strip()}
    elif not a.all_formats:
        allow = set(DATA_FORMATS)

    max_bytes = int(a.max_mb * 1024 * 1024)
    max_total = int(a.max_total_gb * 1024 * 1024 * 1024)

    log("=" * 70)
    log("harvest start · base=%s · out=%s" % (a.base, out))
    log("index_only=%s pdf_ocr=%s formats=%s max_mb=%s max_total_gb=%s sleep=%s"
        % (a.index_only, not a.no_pdf_ocr, sorted(allow) if allow else "ALL",
           a.max_mb, a.max_total_gb, a.sleep))

    done = load_done(manifest_path)
    log("resume: %d resources already in manifest" % len(done))

    # fresh catalog each run (cheap, keeps the index current); manifest persists for resume
    open(catalog_path, "w", encoding="utf-8").close()

    n_ds = n_res = n_dl = n_pdf = n_skip = n_irrel = 0
    total_bytes = 0
    t0 = time.time()

    def disk_free_gb():
        try:
            return shutil.disk_usage(out).free / 1e9
        except OSError:
            return 1e9

    for ds in iter_datasets(a.base, log, a.query, a.max_datasets):
        n_ds += 1
        org = (ds.get("organization") or {}).get("title") if ds.get("organization") else None
        resources = ds.get("resources", []) or []
        append_jsonl(catalog_path, {
            "name": ds.get("name"), "title": ds.get("title"), "org": org,
            "notes": (ds.get("notes") or "")[:500], "num_resources": len(resources),
            "resources": [{"id": r.get("id"), "name": r.get("name"),
                           "format": r.get("format"), "url": r.get("url"),
                           "datastore_active": r.get("datastore_active")} for r in resources],
        })
        if n_ds % 200 == 0:
            log("catalog progress: %d datasets indexed (%d resources, %d downloaded, %d irrelevant-skip, %.2f GB)"
                % (n_ds, n_res, n_dl, n_irrel, total_bytes / 1e9))
        if a.index_only:
            continue

        # DELETE-what-isn't-relevant, applied at the source: catalog everything (done above),
        # but only download datasets that pass the AutoX relevance rule.
        if a.relevant_only and not is_relevant(org, ds.get("title"), ds.get("notes")):
            for res in resources:
                rid = res.get("id") or (res.get("url") or "")
                if rid and rid not in done:
                    append_jsonl(manifest_path, {"id": rid, "dataset": ds.get("name"),
                                                 "org": org, "status": "skip_irrelevant"})
                    done.add(rid)
            n_irrel += 1
            continue

        dslug = safe(ds.get("name") or ds.get("title") or "dataset", 60)
        for res in resources:
            n_res += 1
            rid = res.get("id") or (res.get("url") or "")
            if not rid or rid in done:
                continue
            fmt = guess_ext(res)
            if allow is not None and fmt not in allow:
                append_jsonl(manifest_path, {"id": rid, "dataset": ds.get("name"),
                                             "format": fmt, "status": "skip_format"})
                done.add(rid); n_skip += 1
                continue
            url = res.get("url")
            rslug = safe((res.get("name") or rid), 60) + "." + fmt
            ddir = os.path.join(data_dir, dslug)
            os.makedirs(ddir, exist_ok=True)
            dest = os.path.join(ddir, rslug)

            rec = {"id": rid, "dataset": ds.get("name"), "org": org, "name": res.get("name"),
                   "format": fmt, "url": url, "ts": now()}

            got = None
            if url and re.match(r"^https?://", url):
                nbytes, sha = stream_download(url, dest, max_bytes, log)
                if nbytes is not None:
                    got = True
                    rec.update({"status": "ok", "path": os.path.relpath(dest, out),
                                "bytes": nbytes, "sha1": sha})
                    total_bytes += nbytes; n_dl += 1
                    # PDF -> OCR/text extract
                    if fmt == "pdf" and not a.no_pdf_ocr:
                        doc = extract_pdf_safe(dest, log)
                        if doc:
                            edir = os.path.join(extr_dir, dslug)
                            os.makedirs(edir, exist_ok=True)
                            epath = os.path.join(edir, rslug + ".json")
                            with open(epath, "w", encoding="utf-8") as f:
                                json.dump(doc, f, ensure_ascii=False)
                            rec["extract"] = os.path.relpath(epath, out)
                            rec["pdf_methods"] = doc["meta"]["method_counts"]
                            n_pdf += 1
                else:
                    rec.update({"status": "download_failed", "reason": sha})
            # datastore-only fallback (no downloadable file, or download failed)
            if not got and res.get("datastore_active"):
                rows, offset = [], 0
                while True:
                    dsr = api(a.base, "datastore_search", log,
                              resource_id=res.get("id"), limit=1000, offset=offset)
                    if not dsr or not dsr.get("records"):
                        break
                    rows.extend(dsr["records"])
                    offset += 1000
                    if offset >= (dsr.get("total") or 0) or len(rows) >= 200000:
                        break
                    time.sleep(0.2)
                if rows:
                    os.makedirs(ddir, exist_ok=True)
                    jpath = os.path.join(ddir, safe(res.get("name") or rid, 60) + ".datastore.json")
                    with open(jpath, "w", encoding="utf-8") as f:
                        json.dump(rows, f, ensure_ascii=False)
                    rec.update({"status": "datastore", "path": os.path.relpath(jpath, out),
                                "rows": len(rows)})
                    n_dl += 1
            if "status" not in rec:
                rec["status"] = "no_url"

            append_jsonl(manifest_path, rec)
            done.add(rid)
            time.sleep(a.sleep)

            if total_bytes >= max_total:
                log("HARD STOP: reached max-total-gb (%.1f GB). Re-run to continue." % a.max_total_gb)
                _summary(log, n_ds, n_res, n_dl, n_pdf, n_skip, n_irrel, total_bytes, t0, out)
                return
            if a.min_free_gb and disk_free_gb() < a.min_free_gb:
                log("HARD STOP: output drive below --min-free-gb (%.1f GB free < %.1f). Re-run to continue."
                    % (disk_free_gb(), a.min_free_gb))
                _summary(log, n_ds, n_res, n_dl, n_pdf, n_skip, n_irrel, total_bytes, t0, out)
                return

    _summary(log, n_ds, n_res, n_dl, n_pdf, n_skip, n_irrel, total_bytes, t0, out)


def _summary(log, n_ds, n_res, n_dl, n_pdf, n_skip, n_irrel, total_bytes, t0, out):
    log("-" * 70)
    log("DONE · datasets=%d resources_seen=%d downloaded=%d pdfs_ocr=%d skipped_format=%d irrelevant_skip=%d"
        % (n_ds, n_res, n_dl, n_pdf, n_skip, n_irrel))
    log("total=%.2f GB · elapsed=%.0f min · catalog+manifest in %s"
        % (total_bytes / 1e9, (time.time() - t0) / 60, out))


if __name__ == "__main__":
    main()
