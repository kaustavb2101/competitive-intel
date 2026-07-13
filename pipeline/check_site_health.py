#!/usr/bin/env python3
# AutoX credit-intelligence — LIVE-SITE health check (nightly CI probe).
#
# WHY: the owner should find out from a GitHub issue on his phone when the LIVE
# Vercel deployment breaks — not from a broken demo. The committed QA suite
# (tests/run.sh + tests/validate_data.py) validates the REPO; this script
# validates the DEPLOYMENT: pages actually serve, the critical data files
# actually download and parse, and their top-level shapes are what app.js /
# the deck.gl pages expect.
#
# It is deliberately SHALLOW compared to tests/validate_data.py — the point is
# "is the live site up and serving sane files", not a full data audit. Deep
# integrity checks stay in the repo gate where they belong.
#
# Properties:
#   - pure stdlib (urllib, json, argparse) — runs anywhere, incl. GitHub runners
#   - same validation code path for --base-url (HTTP) and --local (filesystem),
#     so the checker logic itself is testable offline against platform/
#   - exit 0 = all checks pass, exit 1 = at least one failure
#   - --json out.json writes a machine-readable report for the CI workflow
#
# Usage:
#   python3 pipeline/check_site_health.py --base-url https://<deployment>      # CI / live
#   python3 pipeline/check_site_health.py --local platform                     # offline test
#   python3 pipeline/check_site_health.py --local platform --json /tmp/h.json
#   SITE_PASSWORD=... python3 pipeline/check_site_health.py --base-url ...      # auth-gated site
#
# ACCESS-PROTECTED DEPLOYMENTS: the production alias runs middleware.js HTTP
# Basic Auth (any username, password = SITE_PASSWORD). Supply the same password
# via --site-password or the SITE_PASSWORD env var and the probe authenticates
# and runs the full deep checks. WITHOUT a password, a 401 from the live site is
# treated as HEALTHY ("up and correctly access-protected") rather than a
# breakage — the deep page/data checks are reported as SKIPPED, not FAILED, so
# the nightly probe never fires a false alarm just because it lacks the secret.

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

# Sanity cap: no single served asset should exceed this. The largest committed
# file today is rayong_catchment.json (~26 MB); 100 MB means "something is
# badly wrong" (runaway generator, wrong file at the route), not normal growth.
MAX_BYTES = 100 * 1024 * 1024  # 100 MB
HTTP_TIMEOUT = 60  # seconds per fetch
USER_AGENT = "autox-site-health/1.0 (+github-actions nightly probe)"

# The four user-facing entry pages; each must serve 200 and carry the wordmark.
PAGES = [
    "index.html",
    "rayong-catchment.html",
    "province.html",
    "branch-explorer.html",
]
WORDMARK = "AutoX"


# ---------------------------------------------------------------------------
class AuthGated(RuntimeError):
    """The live deployment returned 401 and no credential was supplied. The site
    is UP and correctly access-protected (middleware.js) — this is a healthy
    state, not a breakage; the deep checks simply need the SITE_PASSWORD secret."""


# Fetchers — one code path for validation, two transports.
class HttpFetcher:
    def __init__(self, base_url, password=None):
        self.base = base_url.rstrip("/")
        self.target = self.base
        self.password = (password or "").strip()

    def _headers(self):
        h = {"User-Agent": USER_AGENT}
        if self.password:
            # middleware.js accepts any username; only the password is checked.
            token = base64.b64encode(
                ("health:" + self.password).encode("utf-8")).decode("ascii")
            h["Authorization"] = "Basic " + token
        return h

    def fetch(self, rel):
        """Return (bytes, detail) or raise RuntimeError with a plain reason."""
        url = self.base + "/" + rel
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                status = resp.getcode()
                body = resp.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as e:
            if e.code == 401 and not self.password:
                # Up + correctly protected, but we hold no credential -> gated.
                raise AuthGated(
                    "HTTP 401 — live site is up and access-protected; "
                    "no SITE_PASSWORD supplied to the probe")
            raise RuntimeError("HTTP %d %s" % (e.code, e.reason))
        except urllib.error.URLError as e:
            raise RuntimeError("unreachable: %s" % e.reason)
        except Exception as e:  # timeout, TLS, protocol
            raise RuntimeError("fetch error: %r" % e)
        # urllib follows redirects (Vercel cleanUrls 308s *.html -> clean route),
        # so a 200 here means the final response was OK.
        if status != 200:
            raise RuntimeError("HTTP status %d (expected 200)" % status)
        return body


class LocalFetcher:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.target = "local:" + self.root

    def fetch(self, rel):
        path = os.path.join(self.root, rel)
        if not os.path.exists(path):
            raise RuntimeError("file missing: %s" % path)
        with open(path, "rb") as f:
            return f.read(MAX_BYTES + 1)


# ---------------------------------------------------------------------------
# Per-file JSON shape validators. Each takes the parsed object and returns an
# error string (None = sane). Shapes mirror what the frontend actually reads —
# see tests/validate_data.py for the deep versions of these invariants.
def _shape_branches(d):
    if not isinstance(d, list):
        return "expected a list, got %s" % type(d).__name__
    if len(d) != 2015:
        return "expected 2015 branches, got %d" % len(d)
    r0 = d[0]
    if not isinstance(r0, dict) or "x" not in r0 or "y" not in r0:
        return "first record missing x/y coordinates"
    return None


def _shape_meta(d):
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    if not (isinstance(d.get("updated"), str) and d["updated"].strip()):
        return "missing/empty 'updated' vintage stamp"
    return None


def _shape_amphoe(d):
    recs = d.get("amphoe") if isinstance(d, dict) else None
    if not isinstance(recs, list):
        return "missing 'amphoe' record list"
    if len(recs) != 928:
        return "expected 928 amphoe, got %d" % len(recs)
    return None


def _shape_amphoe_geo(d):
    if not isinstance(d, dict) or d.get("type") != "FeatureCollection":
        return "not a FeatureCollection"
    feats = d.get("features")
    if not isinstance(feats, list):
        return "missing features[]"
    if len(feats) != 928:
        return "expected 928 features, got %d" % len(feats)
    return None


def _shape_crop_stress(d):
    provs = d.get("provinces") if isinstance(d, dict) else None
    if not isinstance(provs, list) or not provs:
        return "missing/empty 'provinces' list"
    if len(provs) < 70:  # 76-77 provinces expected; well below = truncated build
        return "only %d provinces (expected ~76)" % len(provs)
    return None


def _shape_branch_labor(d):
    recs = d.get("branches") if isinstance(d, dict) else None
    if not isinstance(recs, list):
        return "missing 'branches' list"
    if len(recs) != 2015:
        return "expected 2015 branch records (index-aligned), got %d" % len(recs)
    return None


def _shape_opportunity_score(d):
    recs = d.get("districts") if isinstance(d, dict) else None
    if not isinstance(recs, list) or not recs:
        return "missing/empty 'districts' list"
    return None


DATA_FILES = [
    ("data/branches.json", _shape_branches, "array of 2015 branches with x/y"),
    ("data/meta.json", _shape_meta, "object with 'updated' vintage"),
    ("data/amphoe.json", _shape_amphoe, ".amphoe list of 928 districts"),
    ("data/amphoe_geo.json", _shape_amphoe_geo, "FeatureCollection, 928 features"),
    ("data/crop_stress.json", _shape_crop_stress, ".provinces list (~76)"),
    ("data/branch_labor.json", _shape_branch_labor, ".branches list of 2015 (index-aligned)"),
    ("data/opportunity_score.json", _shape_opportunity_score, ".districts list (non-empty)"),
]


# ---------------------------------------------------------------------------
def run_checks(fetcher):
    """Run every check through the given fetcher. Returns a list of dicts:
    {name, ok, detail}. Same code path for HTTP and local."""
    results = []

    def record(name, ok, detail=""):
        results.append({"name": name, "ok": bool(ok), "detail": detail})

    # Pre-flight: distinguish "site up + correctly access-protected (401)" from a
    # real breakage. A protected production alias returning 401 to a
    # credential-less probe is HEALTHY — report it and skip the deep checks
    # rather than firing a false alarm. (LocalFetcher never raises AuthGated;
    # supplying SITE_PASSWORD authenticates past this and runs the full suite.)
    try:
        fetcher.fetch(PAGES[0])
    except AuthGated as e:
        record("live site is up and access-protected (401)", True, str(e))
        record("deep page/data checks", True,
               "SKIPPED — set the SITE_PASSWORD secret so the nightly probe can "
               "authenticate and validate pages + data against the protected alias")
        return results
    except RuntimeError:
        pass  # a genuine fetch failure is reported in detail by the loops below.

    def fetch_common(rel):
        """Fetch + the checks every asset shares (non-empty, under size cap).
        Returns bytes or None (failure already recorded)."""
        try:
            body = fetcher.fetch(rel)
        except RuntimeError as e:
            record("%s fetches" % rel, False, str(e))
            return None
        if len(body) == 0:
            record("%s fetches" % rel, False, "empty response (0 bytes)")
            return None
        if len(body) > MAX_BYTES:
            record("%s fetches" % rel, False,
                   "over %d MB sanity cap" % (MAX_BYTES // (1024 * 1024)))
            return None
        record("%s fetches" % rel, True, "%d bytes" % len(body))
        return body

    # --- pages: 200 + wordmark ---
    for page in PAGES:
        body = fetch_common(page)
        if body is None:
            continue
        try:
            text = body.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        if WORDMARK in text:
            record("%s carries the %s wordmark" % (page, WORDMARK), True)
        else:
            record("%s carries the %s wordmark" % (page, WORDMARK), False,
                   "marker %r not found — wrong content served?" % WORDMARK)

    # --- data files: parse + shape ---
    for rel, validator, expect in DATA_FILES:
        body = fetch_common(rel)
        if body is None:
            continue
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception as e:
            record("%s parses as JSON" % rel, False, "parse error: %r" % e)
            continue
        record("%s parses as JSON" % rel, True)
        err = validator(parsed)
        if err:
            record("%s shape sane (%s)" % (rel, expect), False, err)
        else:
            record("%s shape sane (%s)" % (rel, expect), True)

    return results


def print_report(results, target):
    print("AutoX site-health check — %s" % target)
    print("-" * 72)
    for r in results:
        mark = "[PASS]" if r["ok"] else "[FAIL]"
        line = "%s %s" % (mark, r["name"])
        if r["detail"]:
            line += " — " + r["detail"]
        print(line)
    n_fail = sum(1 for r in results if not r["ok"])
    n_pass = len(results) - n_fail
    print("-" * 72)
    if n_fail == 0:
        print("HEALTHY: %d/%d checks passed." % (n_pass, len(results)))
    else:
        print("BROKEN: %d check(s) FAILED (%d passed)." % (n_fail, n_pass))
        print("Failed:")
        for r in results:
            if not r["ok"]:
                print("  - %s: %s" % (r["name"], r["detail"] or "failed"))
    return n_fail


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Health-check the live AutoX platform (or the local platform/ dir).")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--base-url", help="deployment root, e.g. https://<app>.vercel.app")
    src.add_argument("--local", metavar="DIR",
                     help="validate a local directory (e.g. 'platform') instead of HTTP — "
                          "same validation code path, for offline testing")
    ap.add_argument("--site-password", default=os.environ.get("SITE_PASSWORD"),
                    help="HTTP Basic Auth password for an access-protected deployment "
                         "(any username; matches middleware.js SITE_PASSWORD). Falls "
                         "back to the SITE_PASSWORD env var. Omit for a public site — a "
                         "401 is then reported as healthy-but-gated, not a failure.")
    ap.add_argument("--json", metavar="OUT",
                    help="also write a machine-readable report to this path")
    args = ap.parse_args(argv)

    if args.base_url:
        fetcher = HttpFetcher(args.base_url, password=args.site_password)
    else:
        fetcher = LocalFetcher(args.local)
    results = run_checks(fetcher)
    n_fail = print_report(results, fetcher.target)

    if args.json:
        report = {
            "target": fetcher.target,
            "checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "passed": sum(1 for r in results if r["ok"]),
            "failed": n_fail,
            "ok": n_fail == 0,
            "checks": results,
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, ensure_ascii=False)
            f.write("\n")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
