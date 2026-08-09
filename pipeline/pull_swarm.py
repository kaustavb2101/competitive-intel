#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_swarm.py — parallel orchestrator for the "real-time market pulse" pullers.
=================================================================================

THE PROBLEM THIS EXISTS FOR
----------------------------
Every live feed in this repo (fuel, ThaiWater, NABC, OAE, macro, Trends, app/Apple reviews, rival
YouTube/ads, SET peers, ...) grew its OWN `data-*.yml` workflow, one at a time, over months. That
now means ~17 separate scheduled jobs, each checking out the repo, pulling ONE thing, and rebuilding
`platform/data/provenance.json` on its own branch. `provenance.json` globs every data file in the
repo, so any two of those jobs landing near each other collide on it — a merge-queue pile-up that
has nothing to do with the data itself, purely an artifact of one-workflow-per-feed.

THE FIX: ONE SWARM, ONE PROVENANCE REGEN
-----------------------------------------
`pull_swarm.py` runs a REGISTRY of pullers CONCURRENTLY (ThreadPoolExecutor — each puller is its own
`subprocess.run`, so the GIL is irrelevant), isolates every failure so one crashing/timing-out feed
never takes down the rest, appends the day's readings to the accumulated history, and calls
`rederive_drift.py` EXACTLY ONCE at the end to re-derive whatever went stale and regenerate
`provenance.json`. One workflow, one branch, one provenance regen, no collisions. It does not
hand-maintain a dependency chain — see `rederive_drift.py`'s own docstring for why that always goes
stale; this script leans on it rather than re-inventing it.

FAILURE ISOLATION IS THE WHOLE POINT
-------------------------------------
A puller can crash, hang, or exit non-zero and it must never abort the swarm — a partial swarm is a
SUCCESS. Each feed gets its own timeout (default 900s, overridable per-feed in FEEDS), its own
captured stdout/stderr tail, and its own before/after sha256 of its declared output file so
"succeeded but wrote nothing new" is distinguishable from "succeeded and changed something". The
repo-wide convention (`RC_ABSENT = 3`, see build_*.py and rederive_drift.py) is honoured here too:
an exit code of 3 is a SKIP, not a failure — an upstream that says "nothing to do" is not broken.

THAI-IP-ONLY FEEDS ARE OPT-IN, NEVER DEFAULT
----------------------------------------------
Some pullers (rival_promos, pantip, datagoth, nso_wages, competitor_branches) reach corporate/gov
sites that are Cloudflare-geoblocked from any datacenter IP — their OWN docstrings say so, verified
per-script, not guessed. They stay OUT of the default swarm and only run with `--include-thai`, which
is meaningless from a CI runner and exists for Kaustav's Thai laptop.

WHAT IT DOES NOT DO
--------------------
It does not decide WHAT downstream needs rebuilding (that's `rederive_drift.py`'s fixed-point loop)
and it does not open a PR (that's the calling workflow's job, same as every other data-*.yml here).

USAGE
-----
    python3 pull_swarm.py --list                    # print the full registry, touch nothing
    python3 pull_swarm.py --dry-run                 # print the run plan, touch nothing
    python3 pull_swarm.py                            # run every any-IP feed, then derive + provenance
    python3 pull_swarm.py --only fuel_prices,macro   # just these
    python3 pull_swarm.py --exclude set_peers        # everything except these
    python3 pull_swarm.py --include-thai             # also run the Thai-IP-only feeds (Thai IP only)
    python3 pull_swarm.py --jobs 3                   # fewer concurrent workers
    python3 pull_swarm.py --no-derive                # pull only; skip append_history + rederive_drift

EXIT CODE: 0 if AT LEAST ONE feed succeeded (a partial swarm is a success); 1 only if EVERY selected
feed failed. `--list` and `--dry-run` always exit 0.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))          # pipeline/
ROOT = os.path.dirname(HERE)                                # repo root

RUNS_OUT = os.path.join(ROOT, "source-data", "swarm_runs.json")
MAX_RUNS = 60                # cap the audit trail at the last N swarm runs
DEFAULT_JOBS = 6
DEFAULT_TIMEOUT = 900        # seconds, per feed, unless overridden in the registry below

# Today's date in UTC, embedded verbatim into every feed's --stamp — matches the convention every
# data-*.yml workflow already uses ($(date -u +%F)), so a swarm run and a standalone workflow run on
# the same day produce byte-identical `pulled` stamps.
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


# =================================================================================================
# THE REGISTRY
# =================================================================================================
# One dict per puller. `ip` is "any" (cloud/CI-reachable — verified from the SCRIPT'S OWN docstring,
# never assumed) or "thai" (geoblocked from any datacenter IP per the script's own docstring — Thai
# residential connection only). `out` is the file this feed's SUCCESS is measured against: read
# straight from each script's own `OUT`/`OUT_NATIONAL` constant, not guessed. `group` is an
# editorial bucket (macro / social / competitive / gov) for the --list / --dry-run tables only — it
# drives no logic.
FEEDS = [
    # ---------------------------------------------------------------------------- ANY-IP (default)
    dict(key="fuel_prices", script="pull_fuel_prices.py", args=["--stamp", STAMP],
         label="Bangchak retail fuel prices (diesel/gasohol)", cadence="daily", ip="any",
         group="macro", out="source-data/fuel_prices.json"),

    dict(key="thaiwater_flood", script="pull_thaiwater_flood.py", args=["--stamp", STAMP],
         label="ThaiWater river/reservoir water-level flood pulse", cadence="4x/day", ip="any",
         group="macro", out="platform/data/thaiwater_flood.json"),

    dict(key="thaiwater_rain", script="pull_thaiwater_rain.py", args=["--stamp", STAMP],
         label="ThaiWater 24h rainfall pulse", cadence="4x/day", ip="any",
         group="macro", out="platform/data/thaiwater_rain.json"),

    dict(key="nabc_prices", script="pull_nabc_prices.py", args=["--stamp", STAMP],
         label="NABC daily agri prices (crop/livestock/fishery)", cadence="4x/day", ip="any",
         group="macro", out="source-data/nabc_prices.json"),

    # Unscheduled until 2026-08-08 and quietly ageing: no workflow ran it, so source-data/
    # nabc_agri.json sat 34 days old while build_branch_agri.py and build_crop_farmer_income.py
    # (both objective-#1 layers) kept reproducing from it. A puller nobody runs is a feed that
    # goes stale in silence — the registry is what stops that happening again.
    dict(key="nabc_agri", script="pull_nabc_agri.py", args=["--stamp", STAMP],
         label="NABC per-province agri production (feeds branch_agri + crop_farmer_income)",
         cadence="weekly", ip="any", group="macro", out="source-data/nabc_agri.json"),

    dict(key="oae_prices", script="pull_oae_prices.py", args=["--stamp", STAMP],
         label="OAE weekly farm-gate prices (measured, replaces the World Bank proxy)",
         cadence="weekly", ip="any", group="macro", out="source-data/oae_farmgate_prices.json",
         timeout=1200),   # CKAN package search + resource download can be slow

    dict(key="macro", script="pull_macro.py", args=["--stamp", STAMP],
         label="BIS household debt/policy rate + World Bank CPI/lending-rate/FX", cadence="weekly",
         ip="any", group="macro", out="platform/data/macro_indicators.json"),

    dict(key="google_trends", script="pull_google_trends.py", args=[],
         label="Google Trends demand + brand share-of-search (ESTIMATED)", cadence="monthly",
         ip="any", group="competitive", out="source-data/google_trends.json", timeout=1200),

    dict(key="app_reviews", script="pull_app_reviews.py", args=[],
         label="Google Play ratings + newest reviews, 10 lender apps incl. our own", cadence="weekly",
         ip="any", group="social", out="source-data/app_reviews.json"),

    dict(key="apple_reviews", script="pull_apple_reviews.py", args=[],
         label="Apple TH storefront ratings + reviews, title + digital cohort", cadence="weekly",
         ip="any", group="social", out="source-data/apple_reviews.json", timeout=1200),

    dict(key="rival_youtube", script="pull_rival_youtube.py", args=[],
         label="Rival + own YouTube channel stats and video metadata (needs YOUTUBE_API_KEY)",
         cadence="weekly", ip="any", group="competitive", out="source-data/rival_youtube_raw.json"),

    dict(key="google_ads", script="pull_google_ads.py", args=[],
         label="Rival Google Ads Transparency Center creatives + copy", cadence="weekly", ip="any",
         group="competitive", out="source-data/google_ads_raw.json", timeout=2400),  # ~17 advertisers, paced

    # needs_browser: these two drive a real headless Chromium (set.or.th 403s external requests;
    # only a same-origin fetch from inside a loaded SET page gets through). CI runners that have not
    # run `playwright install chromium` must skip them — use --skip-browser, NOT a hand-kept
    # --exclude list, so a third browser feed added later is skipped there automatically instead of
    # failing the first time nobody remembers to edit the workflow.
    dict(key="set_peers", script="pull_set_peers.py", args=[], needs_browser=True,
         label="SET-listed peer market + financial data (MTC/TIDLOR/SAWAD/TURBO)", cadence="daily",
         ip="any", group="competitive", out="source-data/set_peers.json"),

    # The NOTES to the financial statements are where the rivals' real credit picture lives: the
    # IFRS-9 Stage 1/2/3 ECL tables, the allowance roll-forward and the receivables-by-collateral
    # split. The MD&A (same script, kind=mda) is only management's narrative — SAWAD, for one,
    # publishes no NPL ratio there at all while disclosing both of its components in the notes.
    # Quarterly because that is how often SET filings appear; the run is cheap and idempotent
    # (attachments are immutable once filed, so a re-run re-downloads nothing).
    dict(key="set_filings", script="pull_set_filings.py", args=["--kind", "both"], needs_browser=True,
         label="SET filings: MD&A narrative + Financial Statements/NOTES (ECL staging, collateral mix)",
         cadence="quarterly", ip="any", group="competitive",
         out="source-data/set_filings/index.json", timeout=1800),

    # ------------------------------------------------------------------- THAI-IP-ONLY (opt-in only)
    dict(key="rival_promos", script="pull_rival_promos.py", args=[],
         label="Rival promo/campaign listings from their own sites (Tidlor/MTC/Sawad)",
         cadence="daily", ip="thai", group="competitive", out="source-data/rival_promos.json"),

    dict(key="pantip", script="pull_pantip.py", args=[],
         label="Pantip forum threads mentioning each lender (unprompted voice-of-customer)",
         cadence="weekly", ip="thai", group="social", out="source-data/pantip_threads.json",
         timeout=1200),

    dict(key="datagoth", script="pull_datagoth.py", args=[],
         label="data.go.th + department CKANs + NSO open-data sweep", cadence="weekly", ip="thai",
         group="gov", out="source-data/datagoth/manifest.json", timeout=1800),

    dict(key="nso_wages", script="pull_nso_wages.py", args=["--stamp", STAMP],
         label="NSO Labour Force Survey wages by region x industry x quarter", cadence="quarterly",
         ip="thai", group="macro", out="source-data/nso_wages.json"),

    dict(key="competitor_branches", script="pull_competitor_branches.py", args=["--pull", "--merge"],
         label="Complete competitor branch census from rivals' own store locators", cadence="monthly",
         ip="thai", group="competitive", out="platform/data/competitors_national.json", timeout=1800),
]

FEEDS_BY_KEY = {f["key"]: f for f in FEEDS}


# =================================================================================================
# HELPERS
# =================================================================================================
def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path):
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _size(path):
    return os.path.getsize(path) if path and os.path.exists(path) else 0


def select_feeds(args):
    """The pool this run will touch: any-IP by default, +thai only with --include-thai, then
    --only / --exclude narrow it. Unknown --only keys are a hard error (a typo should not silently
    run "everything"); a --only key that exists but is thai-and-not-included is reported, not run."""
    pool = [f for f in FEEDS if f["ip"] == "any" or args.include_thai]
    if args.skip_browser:
        dropped = [f["key"] for f in pool if f.get("needs_browser")]
        if dropped:
            print("--skip-browser: dropping %s (needs headless Chromium)" % ", ".join(sorted(dropped)),
                  file=sys.stderr)
        pool = [f for f in pool if not f.get("needs_browser")]
    if args.only:
        wanted = {k.strip() for k in args.only.split(",") if k.strip()}
        unknown = wanted - set(FEEDS_BY_KEY)
        if unknown:
            sys.exit("pull_swarm.py: unknown --only key(s): %s" % ", ".join(sorted(unknown)))
        blocked = wanted - {f["key"] for f in pool}
        if blocked:
            print("NOTE: %s require --include-thai -- not selected this run."
                  % ", ".join(sorted(blocked)), file=sys.stderr)
        pool = [f for f in pool if f["key"] in wanted]
    if args.exclude:
        excl = {k.strip() for k in args.exclude.split(",") if k.strip()}
        unknown = excl - set(FEEDS_BY_KEY)
        if unknown:
            print("NOTE: --exclude key(s) not in the registry (ignored): %s"
                  % ", ".join(sorted(unknown)), file=sys.stderr)
        pool = [f for f in pool if f["key"] not in excl]
    return pool


def run_one(feed):
    """Pull one feed in isolation. Never raises -- any failure mode (bad exit, timeout, a decode
    error from Thai text hitting a non-UTF8 console codepage) is caught and reported as a result
    dict, never propagated, because one feed's failure must never take down the swarm."""
    script = os.path.join(HERE, feed["script"])
    out_path = os.path.join(ROOT, feed["out"]) if feed.get("out") else None
    before_hash, before_size = _sha256(out_path), _size(out_path)
    timeout = feed.get("timeout", DEFAULT_TIMEOUT)

    t0 = time.time()
    rc, tail, timed_out = None, "", False
    try:
        proc = subprocess.run(
            [sys.executable, script] + list(feed.get("args") or []),
            cwd=HERE, capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace",   # never let a Thai-text decode kill the swarm
        )
        rc = proc.returncode
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-2000:]
    except subprocess.TimeoutExpired:
        timed_out = True
        tail = "TIMEOUT after %ds" % timeout
    except Exception as e:                              # noqa: BLE001 -- isolation is the point
        tail = "EXCEPTION: %s: %s" % (type(e).__name__, e)
    seconds = round(time.time() - t0, 1)

    after_hash, after_size = _sha256(out_path), _size(out_path)
    changed = (not timed_out) and (rc == 0) and (before_hash != after_hash)

    if timed_out:
        status = "timeout"
    elif rc == 0:
        status = "changed" if changed else "ok"
    elif rc == 3:
        status = "skipped"                              # the repo-wide RC_ABSENT convention
    else:
        status = "failed"

    return {
        "key": feed["key"], "rc": rc, "status": status, "seconds": seconds,
        "bytes_before": before_size, "bytes_after": after_size, "out_tail": tail,
    }


def run_swarm(feeds, jobs):
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        futures = {ex.submit(run_one, f): f["key"] for f in feeds}
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
    order = {f["key"]: i for i, f in enumerate(feeds)}
    results.sort(key=lambda r: order[r["key"]])
    return results


def run_step(script_name):
    """Run one of the two fixed post-pull steps (append_history.py, rederive_drift.py), streaming
    its own output straight to the console -- these are not isolated the way feeds are: they run
    exactly once, sequentially, and their rc is recorded but never suppressed."""
    print("\n>> %s" % script_name)
    proc = subprocess.run([sys.executable, script_name], cwd=HERE)
    return proc.returncode


# =================================================================================================
# OUTPUT
# =================================================================================================
def print_registry():
    print("%-22s %-4s %-11s %-9s %-28s %s" % ("KEY", "IP", "GROUP", "CADENCE", "SCRIPT", "OUT"))
    print("-" * 110)
    for f in FEEDS:
        print("%-22s %-4s %-11s %-9s %-28s %s" % (f["key"], f["ip"], f["group"], f["cadence"],
                                                    f["script"], f["out"]))
    print("-" * 110)
    n_any = sum(1 for f in FEEDS if f["ip"] == "any")
    n_thai = sum(1 for f in FEEDS if f["ip"] == "thai")
    print("%d feed(s) total: %d any-IP (default swarm), %d Thai-IP-only (--include-thai)"
          % (len(FEEDS), n_any, n_thai))


def print_plan(feeds, args):
    print("DRY RUN -- plan only. Nothing pulled, nothing written, no derive step runs.\n")
    print("%-22s %-4s %-11s %-28s %s" % ("KEY", "IP", "GROUP", "SCRIPT", "ARGS"))
    print("-" * 100)
    for f in feeds:
        print("%-22s %-4s %-11s %-28s %s" % (f["key"], f["ip"], f["group"], f["script"],
                                              " ".join(f.get("args") or []) or "(none)"))
    print("-" * 100)
    print("%d feed(s) selected -- jobs=%d, include_thai=%s" % (len(feeds), args.jobs, args.include_thai))
    if args.no_derive:
        print("--no-derive set: would skip append_history.py and rederive_drift.py")
    else:
        print("would then run once, sequentially: append_history.py, then rederive_drift.py")


def print_table(results):
    print()
    print("%-22s %-9s %8s  %s" % ("FEED", "STATUS", "SECONDS", "CHANGED"))
    print("-" * 52)
    for r in results:
        print("%-22s %-9s %8.1f  %s" % (r["key"], r["status"], r["seconds"],
                                        "yes" if r["status"] == "changed" else "no"))
    print("-" * 52)


def summary_line(n_ok, n_changed, n_failed, n_skipped, n_timeout, total):
    return ("%d/%d succeeded (%d changed, %d unchanged), %d failed, %d timed out, %d skipped"
            % (n_ok, total, n_changed, n_ok - n_changed, n_failed, n_timeout, n_skipped))


def save_run(record):
    store = {"meta": {}, "runs": []}
    if os.path.exists(RUNS_OUT):
        try:
            with open(RUNS_OUT, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict) and isinstance(loaded.get("runs"), list):
                store = loaded
        except (OSError, ValueError):
            pass    # a corrupt file must not stop this run from recording its own result

    runs = store.get("runs") or []
    runs.append(record)
    if len(runs) > MAX_RUNS:
        runs = runs[-MAX_RUNS:]
    store["runs"] = runs
    store["meta"] = {
        "title": "pull_swarm.py run history -- the swarm's own audit trail",
        "generated_by": "pipeline/pull_swarm.py",
        "label": "Each row is one swarm run: which feeds were pulled concurrently, whether each one "
                 "succeeded / changed its declared output file / failed / timed out / was skipped "
                 "(exit 3, the repo-wide SKIP convention), plus the rc of the append_history.py and "
                 "rederive_drift.py steps that followed. This file makes the pulse observable.",
        "max_runs": MAX_RUNS,
        "n_runs": len(runs),
    }
    os.makedirs(os.path.dirname(RUNS_OUT), exist_ok=True)
    with open(RUNS_OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(store, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


# =================================================================================================
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", metavar="k1,k2", help="comma-separated feed keys to run (default: all any-IP feeds)")
    ap.add_argument("--exclude", metavar="k1,k2", help="comma-separated feed keys to skip")
    ap.add_argument("--include-thai", action="store_true",
                     help="also run the Thai-IP-only feeds (only useful from a Thai residential IP)")
    ap.add_argument("--skip-browser", action="store_true",
                     help="skip every feed that needs a headless Chromium (for runners without "
                          "`playwright install chromium`)")
    ap.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="parallel workers (default %d)" % DEFAULT_JOBS)
    ap.add_argument("--dry-run", action="store_true", help="print the plan, touch nothing")
    ap.add_argument("--no-derive", action="store_true",
                     help="pull only -- skip append_history.py and rederive_drift.py")
    ap.add_argument("--list", action="store_true", help="print the full FEEDS registry and exit")
    args = ap.parse_args()

    if args.list:
        print_registry()
        return 0

    feeds = select_feeds(args)
    if not feeds:
        print("No feeds selected -- nothing to do.")
        return 1

    if args.dry_run:
        print_plan(feeds, args)
        return 0

    started = _now_iso()
    print("pull_swarm.py: pulling %d feed(s) with %d worker(s)..." % (len(feeds), args.jobs))
    results = run_swarm(feeds, args.jobs)
    finished = _now_iso()
    print_table(results)

    n_ok = sum(1 for r in results if r["status"] in ("ok", "changed"))
    n_changed = sum(1 for r in results if r["status"] == "changed")
    n_failed = sum(1 for r in results if r["status"] == "failed")
    n_timeout = sum(1 for r in results if r["status"] == "timeout")
    n_skipped = sum(1 for r in results if r["status"] == "skipped")

    for r in results:
        if r["status"] in ("failed", "timeout") and r["out_tail"]:
            print("\n-- %s (%s) tail --\n%s" % (r["key"], r["status"], r["out_tail"][-800:]))

    append_rc, derive_rc = None, None
    if not args.no_derive:
        append_rc = run_step("append_history.py")
        derive_rc = run_step("rederive_drift.py")

    record = {
        "started": started, "finished": finished,
        "n_ok": n_ok, "n_changed": n_changed, "n_failed": n_failed,
        "n_timeout": n_timeout, "n_skipped": n_skipped,
        "jobs": args.jobs, "include_thai": args.include_thai,
        "append_history_rc": append_rc, "rederive_drift_rc": derive_rc,
        "feeds": [{"key": r["key"], "rc": r["rc"], "status": r["status"], "seconds": r["seconds"],
                   "bytes_before": r["bytes_before"], "bytes_after": r["bytes_after"]}
                  for r in results],
    }
    save_run(record)

    print("\n" + summary_line(n_ok, n_changed, n_failed, n_skipped, n_timeout, len(results)))
    if not args.no_derive:
        print("append_history.py rc=%s, rederive_drift.py rc=%s" % (append_rc, derive_rc))
    print("logged to source-data/swarm_runs.json")

    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
