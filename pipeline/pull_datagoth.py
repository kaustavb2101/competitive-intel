#!/usr/bin/env python3
"""Thai open-data puller — data.go.th + department CKANs + NSO (browser-UA).

WHY THIS EXISTS
    data.go.th (the aggregator) is Cloudflare geo-blocked to foreign/datacenter IPs, so it fails from
    GitHub Actions and the Claude cloud sandbox. It is REACHABLE from Kaustav's Thai residential IP.
    This script pulls the verified, province/district-granular datasets a title-loan credit-intelligence
    platform needs, straight from the open CKAN download hosts (no auth token anywhere). Run it from the
    Thai laptop; it caches raw files + a provenance manifest into source-data/datagoth/ for the existing
    ingest/build pipeline to normalize.

    python3 pull_datagoth.py                 # pull every registered source
    python3 pull_datagoth.py --list          # list the registry, pull nothing
    python3 pull_datagoth.py --only fpo_pico diw_factories   # pull just these
    python3 pull_datagoth.py --out ../source-data/datagoth   # override cache dir

PROVENANCE
    Every fetch is MEASURED (government open data, nothing synthesized). The manifest records the exact
    source URL, fetch time, byte size, and HTTP status so downstream layers can cite measured-vs-estimated
    honestly. Per-source failures are NON-FATAL — the script pulls what it can and reports the rest.

ACCESS NOTES (verified 2026-07-12 from a Bangkok IP)
    - catalog.nso.go.th (NSO's own CKAN) needs a browser User-Agent; catalogapi.nso.go.th is WAF-blocked
      (use the CKAN /dataset/.../download/ resources or the data.go.th nso mirror instead).
    - gdcatalog.dlt.go.th (DLT vehicle CSVs) is unreachable from this connection — use office_mot
      (datagov.mot.go.th, cumulative vehicles) or excise vehicle-tax as the vehicle-volume signal.
"""
import os, sys, json, time, argparse, datetime, urllib.request, urllib.error, urllib.parse

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

def _dbd_registration_url(kind="99", part="1"):
    """DBD publishes new-company registrations as a month-stamped CSV. Try the last few months
    (this-month files appear a few days in), newest first. kind 99=new regs, part rotates."""
    today = datetime.date.today()
    urls = []
    y, m = today.year, today.month
    for back in range(0, 4):            # try current month then 3 prior
        mm = m - back
        yy = y
        while mm <= 0:
            mm += 12; yy -= 1
        urls.append(f"https://openapi.dbd.go.th/juristic_person/registration/{kind}_{yy}{mm:02d}_{part}.csv")
    return urls

# id -> {url|urls, ext, ua, theme, gran, desc}. url = single; urls = try-in-order (first 200 wins).
REGISTRY = {
    # ---- ACQUISITION / competitors & demand -------------------------------------------------
    "fpo_pico": {
        "ckan": ("https://catalog.fpo.go.th/api/3/action/package_search?q=พิโกไฟแนนซ์&rows=10", "csv"),
        "ext": "csv", "ua": False, "theme": "acquisition", "gran": "province+address",
        "desc": "FPO licensed PICO-finance operators — DIRECT competitor registry (province + full address)."},
    "dbd_newco": {
        "urls": _dbd_registration_url("99", "1"),
        "ext": "csv", "ua": False, "theme": "acquisition", "gran": "subdistrict(tambon) monthly",
        "desc": "DBD new company registrations (business-formation demand signal), tambon-granular."},
    "smebank_credit": {
        "ckan": ("https://data.go.th/api/3/action/package_show?id=smedbank-outprovince", "csv"),
        "ext": "csv", "ua": False, "theme": "acquisition", "gran": "province monthly",
        "desc": "SME-bank SME credit outstanding by province."},
    "osmep_sme_growth": {
        "url": "https://opendata.sme.go.th/dataset/b64805bb-0000-0000-0000-000000000000/download/growth_newly-est-sme-juristic-y2566-y2568.csv",
        "ckan": ("https://opendata.sme.go.th/api/3/action/package_show?id=number-of-sme", "csv"),
        "ext": "csv", "ua": False, "theme": "acquisition", "gran": "province",
        "desc": "OSMEP MSME counts / growth by province."},
    # ---- RISK / collateral & credit -------------------------------------------------------
    "diw_factories": {
        "ckan": ("https://data.go.th/api/3/action/package_show?id=factype3", "csv"),
        "ext": "csv", "ua": False, "theme": "risk", "gran": "subdistrict",
        "desc": "DIW class-3 factory registry — name/addr/capital/workers/horsepower (industrial demand)."},
    "mot_vehicles": {
        "ckan": ("https://datagov.mot.go.th/api/3/action/package_search?q=รถจดทะเบียนสะสม", "csv"),
        "ext": "csv", "ua": False, "theme": "risk", "gran": "province",
        "desc": "MOT cumulative registered vehicles by province (collateral base)."},
    "excise_moto_tax": {
        "url": "https://catalog.excise.go.th/api/3/action/datastore_search?resource_id=a8d9115a-708d-420d-b796-e96b373ad1b8&limit=2000",
        "ext": "json", "ua": False, "theme": "risk", "gran": "national/monthly",
        "desc": "Excise motorcycle-tax collections (motorcycle-sales proxy = collateral flow)."},
    "excise_car_tax": {
        "url": "https://catalog.excise.go.th/base/catalog/excise/file/03_0301.csv",
        "ext": "csv", "ua": False, "theme": "risk", "gran": "national/monthly",
        "desc": "Excise car-tax collections (car-sales proxy)."},
    "baac_credit": {
        "ckan": ("https://data.go.th/api/3/action/package_show?id=baac02_2567", "xlsx"),
        "ext": "xlsx", "ua": False, "theme": "risk", "gran": "province",
        "desc": "BAAC personal credit outstanding by area (province)."},
    # ---- NSO (browser-UA CKAN) ------------------------------------------------------------
    "nso_household_debt": {
        "ckan": ("https://catalog.nso.go.th/api/3/action/package_search?q=หนี้สินของครัวเรือน&rows=5", "any"),
        "ext": "xlsx", "ua": True, "theme": "risk", "gran": "region",
        "desc": "NSO SES household debt (browser-UA CKAN)."},
    "nso_agri_income_debt": {
        "ckan": ("https://catalog.nso.go.th/api/3/action/package_search?q=หนี้สินทางการเกษตร&rows=5", "any"),
        "ext": "xlsx", "ua": True, "theme": "risk", "gran": "province",
        "desc": "NSO agricultural income & debt by province (browser-UA CKAN)."},
    "nso_unemployment": {
        "ckan": ("https://catalog.nso.go.th/api/3/action/package_search?q=อัตราการว่างงาน&rows=5", "any"),
        "ext": "csv", "ua": True, "theme": "risk", "gran": "region",
        "desc": "NSO unemployment rate (browser-UA CKAN)."},
}

def _fetch(url, ua, timeout=60):
    # CKAN search URLs carry raw Thai query terms; percent-encode non-ASCII while preserving structure.
    safe_url = urllib.parse.quote(url, safe=":/?&=%#@+,;~")
    req = urllib.request.Request(safe_url, headers={"User-Agent": BROWSER_UA if ua else "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()

def _resolve_ckan(api_url, prefer_ext, ua):
    """Given a CKAN package_show/package_search API URL, return the best resource download URL."""
    try:
        st, body = _fetch(api_url, ua)
        d = json.loads(body)
        res = d["result"]
        pkgs = res if isinstance(res, list) else res.get("results", [res])
        pkgs = pkgs if isinstance(pkgs, list) else [pkgs]
        best = None
        for pkg in pkgs:
            for r in pkg.get("resources", []):
                fmt = (r.get("format") or "").lower()
                url = r.get("url")
                if not url:
                    continue
                if prefer_ext in ("any",) or prefer_ext in fmt or url.lower().endswith("." + prefer_ext):
                    return url
                best = best or url
        return best
    except Exception as e:
        print(f"      ckan-resolve failed: {e}")
        return None

def pull_one(sid, spec, outdir):
    ua = spec.get("ua", False)
    candidates = []
    if spec.get("url"):
        candidates.append(spec["url"])
    candidates += spec.get("urls", [])
    # If direct URLs fail (or none given), resolve the newest resource via the CKAN API.
    if spec.get("ckan"):
        api, pref = spec["ckan"]
        resolved = _resolve_ckan(api, pref, ua)
        if resolved:
            candidates.append(resolved)
    last_err = None
    for url in candidates:
        try:
            st, body = _fetch(url, ua)
            if st == 200 and body and not body[:200].lstrip().lower().startswith(b"<!doctype html"):
                path = os.path.join(outdir, f"{sid}.{spec['ext']}")
                with open(path, "wb") as f:
                    f.write(body)
                return {"id": sid, "ok": True, "url": url, "bytes": len(body), "status": st,
                        "path": os.path.relpath(path), "theme": spec["theme"], "gran": spec["gran"],
                        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
                        "desc": spec["desc"]}
            last_err = f"HTTP {st}, {len(body or b'')}B"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = str(e)
        time.sleep(0.3)
    return {"id": sid, "ok": False, "error": last_err, "tried": candidates,
            "theme": spec["theme"], "desc": spec["desc"]}

def main():
    ap = argparse.ArgumentParser(description="Pull Thai open data (data.go.th + dept CKANs + NSO).")
    ap.add_argument("--only", nargs="+", help="pull only these registry ids")
    ap.add_argument("--out", default=None, help="cache dir (default ../source-data/datagoth)")
    ap.add_argument("--list", action="store_true", help="list the registry and exit")
    args = ap.parse_args()

    # Thai text + arrows in the log crash a cp1252 Windows console; force UTF-8 output.
    for stream in (sys.stdout, sys.stderr):
        try: stream.reconfigure(encoding="utf-8")
        except Exception: pass

    if args.list:
        for sid, s in REGISTRY.items():
            print(f"  {sid:22s} [{s['theme']:11s}] {s['gran']:24s} {s['desc']}")
        return

    here = os.path.dirname(os.path.abspath(__file__))
    outdir = args.out or os.path.join(here, "..", "source-data", "datagoth")
    os.makedirs(outdir, exist_ok=True)

    ids = args.only or list(REGISTRY)
    results, ok = [], 0
    for sid in ids:
        if sid not in REGISTRY:
            print(f"[SKIP] {sid} — not in registry"); continue
        print(f"[pull] {sid} …")
        r = pull_one(sid, REGISTRY[sid], outdir)
        results.append(r)
        if r["ok"]:
            ok += 1
            print(f"       OK  {r['bytes']:>9,}B  {r['url'][:90]}")
        else:
            print(f"       FAIL  {r.get('error')}")

    manifest = {"pulled_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "source_ip_note": "run from Thai residential IP (data.go.th geo-blocks foreign IPs)",
                "ok": ok, "total": len(results), "results": results}
    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n=== {ok}/{len(results)} sources pulled → {os.path.relpath(outdir)} (manifest.json) ===")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
