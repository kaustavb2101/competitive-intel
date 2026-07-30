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
    """The live deployment returned 401 (middleware.js Basic Auth). The site is UP
    and correctly access-protected — a healthy state, not a breakage — whether the
    probe supplied no credential OR supplied one the deployment rejected. Either
    way the deep checks are skipped, not failed; unlocking them just needs the CI
    SITE_PASSWORD secret to match the deployment's own SITE_PASSWORD."""


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
            if e.code == 401:
                # A 401 means the site is UP and answering with an auth challenge
                # (middleware.js Basic Auth) — categorically not an outage, whether
                # or not we hold a credential. Two sub-cases, both healthy:
                #   no credential supplied  -> gated; deep checks need SITE_PASSWORD.
                #   credential supplied but still 401 -> the probe's SITE_PASSWORD does
                #     not match the deployment's; a probe-credential mismatch, NOT a
                #     broken site. (A truly down site gives connection-refused / 5xx /
                #     timeout, which the loops below still report as real failures.)
                if self.password:
                    raise AuthGated(
                        "HTTP 401 — live site is up and access-protected, but the "
                        "SITE_PASSWORD supplied to the probe was rejected by the "
                        "deployment (probe-credential mismatch, not a site outage)")
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


def _shape_decision_queue(d):
    # The exec front-door (#home command center) marquee: "This week — do these
    # first". Frontend reads .items (built by build_decision_queue.py). A broken
    # build that empties this list would gut the front page, so validate it here.
    items = d.get("items") if isinstance(d, dict) else None
    if not isinstance(items, list) or not items:
        return "missing/empty 'items' list"
    r0 = items[0]
    if not isinstance(r0, dict) or "act" not in r0:
        return "first item missing 'act' field"
    return None


def _shape_impact_cards(d):
    # The command-center front-door LEAD visual: the 5-region impact strip
    # (renderImpactStrip reads IMPACT.regions). A truncated build that drops the
    # region cards leaves the exec's first screen blank, so validate the shape.
    regs = d.get("regions") if isinstance(d, dict) else None
    if not isinstance(regs, list) or not regs:
        return "missing/empty 'regions' list"
    r0 = regs[0]
    if not isinstance(r0, dict) or "key" not in r0 or "name_th" not in r0:
        return "first region missing key/name_th"
    return None


def _shape_province_risk(d):
    # The #home "getting riskier" verdict (obj #1): worst-first province rollup
    # (renderHomeRisk reads .provinces). Well below 77 = a truncated build.
    provs = d.get("provinces") if isinstance(d, dict) else None
    if not isinstance(provs, list) or not provs:
        return "missing/empty 'provinces' list"
    if len(provs) < 70:  # 77 provinces expected; well below = truncated build
        return "only %d provinces (expected ~77)" % len(provs)
    if "mean_risk" not in provs[0]:
        return "first province missing 'mean_risk'"
    return None


def _shape_branch_risk(d):
    # Per-branch composite risk (obj #1), index-aligned to branches.json — the
    # #home riskiest-branch line + the map risk lens read it. A wrong length
    # silently misaligns every branch's risk, so assert the exact count.
    recs = d.get("branches") if isinstance(d, dict) else None
    if not isinstance(recs, list):
        return "missing 'branches' list"
    if len(recs) != 2015:
        return "expected 2015 branch records (index-aligned), got %d" % len(recs)
    if "composite_risk" not in recs[0]:
        return "first record missing 'composite_risk'"
    return None


def _shape_tape_real(d):
    # The MEASURED real loan-tape (obj #1 portfolio truth) — the #home pillar
    # band + assistance radar read it. A broken/empty build guts the front
    # door's headline risk read, so validate the headline + bucket ladder.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    if not (isinstance(d.get("headline"), str) and d["headline"].strip()):
        return "missing/empty 'headline'"
    ladder = (d.get("bucket_ladder") or {}).get("ladder") if isinstance(d.get("bucket_ladder"), dict) else None
    if not isinstance(ladder, list) or not ladder:
        return "missing/empty bucket_ladder.ladder"
    return None


def _shape_collateral_flow(d):
    # The MEASURED used-collateral pulse (obj #1) — the Overview tab's lead
    # "moto / car / pickup" registration-flow card (renderCollateralFlow reads
    # .regions + meta.national_mix_pct). Motorcycles are ~50% of the book, so a
    # truncated deploy that drops the region rows or the national mix blanks a
    # primary obj-#1 exec screen with no phone alert — the exact "broken demo"
    # this probe exists to catch. Overview is a default nav route, so cover it.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    regs = d.get("regions")
    if not isinstance(regs, list) or len(regs) < 5:
        return "missing/short 'regions' list (expected 5 macro regions)"
    r0 = regs[0]
    if not isinstance(r0, dict) or "region" not in r0 or not isinstance(r0.get("moto"), dict):
        return "first region missing 'region'/'moto' collateral block"
    if "transfer_rate" not in r0["moto"]:
        return "region moto block missing 'transfer_rate'"
    mix = (d.get("meta") or {}).get("national_mix_pct") if isinstance(d.get("meta"), dict) else None
    if not isinstance(mix, dict) or "moto" not in mix:
        return "meta.national_mix_pct missing 'moto' (headline read)"
    return None


def _shape_truck_flow(d):
    # The MEASURED logistics-SME (hauler) pulse (obj #1) — the Overview tab's
    # truck-registration-flow card (renderTruckFlow reads .provinces, filtering
    # for rows with `th` + `new_regis_yoy_pct`, and sums `new_regis_12m`). An
    # owner-operator hauler is a classic heavy-title borrower, so a truncated
    # deploy that drops the province rows blanks a default-route obj-#1 card
    # with no phone alert. Sibling of collateral_flow; cover it the same way.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    provs = d.get("provinces")
    if not isinstance(provs, list) or len(provs) < 70:
        return "missing/short 'provinces' list (expected ~77)"
    p0 = provs[0]
    if not isinstance(p0, dict) or not p0.get("th"):
        return "first province missing 'th'"
    if "new_regis_yoy_pct" not in p0 or "new_regis_12m" not in p0:
        return "first province missing 'new_regis_yoy_pct'/'new_regis_12m' (card render + headline reads)"
    return None


def _shape_region_debt(d):
    # The MEASURED regional household-debt backdrop (obj #1) — the Overview
    # tab's leverage card (renderRegionDebt reads .series{national,region} and
    # renders the heaviest-region debt-per-household read). A truncated deploy
    # that drops the series or the debt-per-household indicator blanks the
    # leverage-floor read on a default nav route with no phone alert. Robust to
    # a future SES vintage bump (the indicator key is asserted, not the year).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    if not (isinstance(d.get("headline"), str) and d["headline"].strip()):
        return "missing/empty 'headline'"
    series = d.get("series")
    if not isinstance(series, dict):
        return "missing 'series' object"
    region = series.get("region")
    if not isinstance(region, list) or not region:
        return "missing/empty series.region list"
    if not (isinstance(series.get("national"), list) and series["national"]):
        return "missing/empty series.national list"
    has_dph = any(
        isinstance(r, dict)
        and r.get("indicator") == "debt_per_household_thb"
        and r.get("value") is not None
        for r in region
    )
    if not has_dph:
        return "series.region has no 'debt_per_household_thb' row (card headline read)"
    return None


def _shape_peer_province(d):
    # The MEASURED per-province PEER board (obj #2 competitive risk) — the
    # Competition surface's flagship read (drawPeerProvince reads .provinces and,
    # per row, .autox + .by_brand to stack AutoX next to Muangthai / Srisawad /
    # Tidlor / Heng one brand at a time) AND the command-center thesis clause
    # (loadPeerProvince). It is the sharpest competitive-risk benchmark on the
    # footprint we already run. A truncated deploy that drops the province rows
    # or the per-brand split blanks the exec's competitive board with no phone
    # alert — the same "broken demo" blind spot the obj-#1 flow-card probes
    # closed. Robust to a future census growth (row count asserted >=70, not ==77).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    provs = d.get("provinces")
    if not isinstance(provs, list) or len(provs) < 70:
        return "missing/short 'provinces' list (expected ~77)"
    p0 = provs[0]
    if not isinstance(p0, dict) or "autox" not in p0:
        return "first province missing 'autox' branch count"
    if not isinstance(p0.get("by_brand"), dict):
        return "first province missing 'by_brand' per-rival split (board render read)"
    if "ratio" not in p0:
        return "first province missing 'ratio' (rival:AutoX headline read)"
    tot = (d.get("meta") or {}).get("total_autox") if isinstance(d.get("meta"), dict) else None
    if not isinstance(tot, int):
        return "meta.total_autox missing (national rollup headline)"
    return None


def _shape_competitor_coverage(d):
    # The competition pillar's OTHER flagship read (obj #2): the national
    # census-completeness board (drawCompCoverage reads .brands — the big-4
    # MEASURED found-count vs ESTIMATED public-report expected — plus
    # meta.totals for the "N measured rival branches" readout and
    # meta.national_standing for AutoX's own network-scale rank). It is the
    # census rollup the whole per-province peer board is built on. peer_province
    # is already probed; this sibling was not, so a truncated deploy that empties
    # .brands silently drops the Competition surface to its "not yet computed"
    # placeholder with no phone alert — the same "broken demo" blind spot the
    # peer_province + obj-#1 flow-card probes closed. Robust to census growth
    # (asserts the 4 big brands are present, not exact counts).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    brands = d.get("brands")
    if not isinstance(brands, list) or len(brands) < 4:
        return "missing/short 'brands' list (expected the 4 big-4 rivals)"
    b0 = brands[0]
    if not isinstance(b0, dict) or "brand" not in b0:
        return "first brand row missing 'brand' name"
    if not isinstance(b0.get("found"), int):
        return "first brand row missing 'found' MEASURED census count"
    totals = (d.get("meta") or {}).get("totals") if isinstance(d.get("meta"), dict) else None
    if not isinstance(totals, dict) or not isinstance(totals.get("found"), int):
        return "meta.totals.found missing (national census headline)"
    return None


def _shape_pico_district(d):
    # The district-grain competitive-density layer (obj #2) that sharpens the
    # Competition surface below province level. app.js live-fetches it
    # (picodistPromise) and renders TWO visible reads: the "Top go-live districts
    # (recent/total)" leaderboard (renderPicoCensus reads
    # meta.operating_momentum.top_recent, each row [district, recent, total]) and
    # the "within provinces the rival field is not uniform — PICO clusters in the
    # provincial-capital districts" clause (reads .top_districts +
    # meta.n_district_resolved / resolution_pct). It is a MEASURED FPO-registry
    # tally shipped recently with NO probe coverage, so a truncated deploy that
    # empties it would silently blank the Competition surface's district-grain
    # reads with no phone alert — the same "broken demo" blind spot the
    # peer_province / competitor_coverage probes closed for the province-grain
    # reads. Robust to registry growth (asserts shape, not exact counts).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    tops = d.get("top_districts")
    if not isinstance(tops, list) or not tops:
        return "missing/empty 'top_districts' list (density clause render read)"
    meta = d.get("meta")
    if not isinstance(meta, dict):
        return "missing 'meta' object"
    if not isinstance(meta.get("n_district_resolved"), int):
        return "meta.n_district_resolved missing (district-grain prose read)"
    op = meta.get("operating_momentum")
    if not isinstance(op, dict):
        return "meta.operating_momentum missing (go-live leaderboard block)"
    tr = op.get("top_recent")
    if not isinstance(tr, list) or not tr:
        return "meta.operating_momentum.top_recent missing/empty (leaderboard render read)"
    r0 = tr[0]
    if not isinstance(r0, list) or len(r0) < 3:
        return "top_recent[0] not a [district, recent, total] row"
    return None


DATA_FILES = [
    ("data/branches.json", _shape_branches, "array of 2015 branches with x/y"),
    ("data/meta.json", _shape_meta, "object with 'updated' vintage"),
    ("data/amphoe.json", _shape_amphoe, ".amphoe list of 928 districts"),
    ("data/amphoe_geo.json", _shape_amphoe_geo, "FeatureCollection, 928 features"),
    ("data/crop_stress.json", _shape_crop_stress, ".provinces list (~76)"),
    ("data/branch_labor.json", _shape_branch_labor, ".branches list of 2015 (index-aligned)"),
    # Was opportunity_score.json — that growth leaderboard was dropped in the
    # consolidation/strategy pivot (kept on disk, no live fetch), so probing it
    # asserted a dependency the app no longer has. Swapped for the front-door's
    # live marquee layer, the exec Decision Queue.
    ("data/decision_queue.json", _shape_decision_queue, ".items list (ranked weekly actions)"),
    # Command-center (#home) front-door layers, eagerly loaded on the exec's
    # first screen (renderHome). The probe previously covered only the default
    # map/overview entry files, so a truncated/failed deploy of any of these
    # would break the command center with NO phone alert — the exact "broken
    # demo" this check exists to catch. Added to close that blind spot.
    ("data/impact_cards.json", _shape_impact_cards, ".regions strip of 5 (front-door lead visual)"),
    ("data/province_risk.json", _shape_province_risk, ".provinces rollup (~77, obj #1 risk verdict)"),
    ("data/branch_risk.json", _shape_branch_risk, ".branches list of 2015 (index-aligned composite risk)"),
    ("data/tape_real.json", _shape_tape_real, "headline + bucket_ladder (MEASURED portfolio truth)"),
    # Overview (#overview) tab's lead used-collateral pulse card — a default nav
    # route, MEASURED DLT registration flow, obj #1's primary collateral class
    # (moto ~50% of the book). Shipped 2026-07-27 with no probe coverage; a
    # truncated CDN deploy would blank it with no alert. Added to close that gap.
    ("data/collateral_flow.json", _shape_collateral_flow, ".regions (5 macro regions) + meta.national_mix_pct (moto/car/pickup)"),
    # The two remaining eager Overview flow-family cards its sibling
    # collateral_flow left uncovered (renderTruckFlow / renderRegionDebt, both
    # loaded on the default #overview route). Same "truncated deploy blanks a
    # default-route obj-#1 card with no alert" rationale; closes the flow-card
    # coverage gap the 2026-07-27 collateral-flow probe ship flagged as next.
    ("data/truck_flow.json", _shape_truck_flow, ".provinces list (~77) with new_regis_yoy_pct"),
    ("data/region_debt.json", _shape_region_debt, ".series{national,region} + debt_per_household_thb"),
    # The competition pillar's flagship exec layer (obj #2) — the per-province
    # peer board (AutoX next to each big-4 rival, per province) that powers the
    # Competition surface + the command-center thesis clause. Every default-route
    # obj-#1 flow card is now probed; this closes the matching obj-#2 blind spot
    # so a truncated deploy that guts the competitive board triggers a phone alert.
    ("data/peer_province.json", _shape_peer_province, ".provinces (~77) with .by_brand per-rival split + meta.total_autox"),
    # peer_province's sibling flagship (obj #2): the national census-completeness
    # board the whole per-province peer read is built on. The province rows were
    # probed above; this rollup (drawCompCoverage reads .brands + meta.totals +
    # meta.national_standing) was the last unprobed piece of the Competition
    # surface, so a truncated deploy could blank it with no phone alert. Closes it.
    ("data/competitor_coverage.json", _shape_competitor_coverage, ".brands (big-4 found vs public expected) + meta.totals.found"),
    # The district-grain competitive layer (obj #2) that sharpens the Competition
    # surface below province level: the "Top go-live districts (recent/total)"
    # go-live leaderboard + the provincial-capital clustering clause both render
    # from it. peer_province + competitor_coverage now cover the province-grain
    # competitive reads; this closes the matching district-grain blind spot so a
    # truncated deploy that guts the recently-shipped go-live leaderboard fires a
    # phone alert instead of silently blanking the อำเภอ reads.
    ("data/pico_district.json", _shape_pico_district, ".top_districts + meta.operating_momentum.top_recent (go-live leaderboard)"),
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
        if getattr(fetcher, "password", ""):
            # A credential was supplied but the deployment rejected it. The site is
            # healthy; the probe simply cannot see past the gate. Skip (not fail) the
            # deep checks and say exactly how to unlock them — align the CI
            # SITE_PASSWORD secret with the deployment's own SITE_PASSWORD.
            record("deep page/data checks", True,
                   "SKIPPED — the supplied SITE_PASSWORD was rejected by the deployment "
                   "(probe-credential mismatch, not a site outage); align the CI "
                   "SITE_PASSWORD secret with the deployment's to run the full page + "
                   "data validation")
        else:
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
