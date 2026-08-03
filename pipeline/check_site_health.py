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


def _shape_sfi_credit(d):
    # The MEASURED state-bank (SFI) system NPL backdrop on Overview (#overview),
    # obj #1 — renderSfi's macro credit-quality card (the closest public read on
    # the household + farm repayment stress AutoX's borrowers sit inside). The
    # render HIDES the whole block on `!SFI || !meta.latest || latest.npl_ratio
    # == null`, and the quarter table maps .series[] (period / npl_ratio /
    # npl_gross). It was the last eager Overview macro card with no deploy probe:
    # a truncated CDN deploy that emptied/truncated sfi_credit.json would silently
    # blank the NPL backdrop on a default nav route with no phone alert. Asserts
    # shape (a non-empty series + a latest quarter carrying a numeric npl_ratio),
    # not counts/values — robust to a future FPO quarter being appended.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    series = d.get("series")
    if not isinstance(series, list) or not series:
        return "missing/empty 'series' list (NPL quarter-table render read)"
    s0 = series[0]
    if not isinstance(s0, dict):
        return "first series row is not an object"
    if not (isinstance(s0.get("period"), str) and s0["period"].strip()):
        return "first series row missing/empty 'period'"
    if not isinstance(s0.get("npl_ratio"), (int, float)):
        return "first series row missing numeric 'npl_ratio' (quarter-table render read)"
    meta = d.get("meta")
    if not isinstance(meta, dict):
        return "missing 'meta' object"
    latest = meta.get("latest")
    if not isinstance(latest, dict):
        return "missing 'meta.latest' object (card hide-gate read)"
    if not isinstance(latest.get("npl_ratio"), (int, float)):
        return "meta.latest missing numeric 'npl_ratio' (card headline hide-gate read)"
    if not (isinstance(latest.get("period"), str) and latest["period"].strip()):
        return "meta.latest missing/empty 'period' (card headline read)"
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


def _shape_rival_threat_region(d):
    # The per-region density x service JOIN (rival_threat_region.json, obj #2) —
    # the ONE competitive read that renders on the exec FRONT DOOR (renderHomeDefend
    # draws the command-center "Where the network is hardest to defend" card off
    # RIVTHREATREG.regions) AND on the Competition tab (drawRivThreatRegion renders
    # the full per-region table + reads RIVTHREATREG.headline for the readout). Both
    # gate on `RIVTHREATREG.regions` being a non-empty array and degrade SILENTLY
    # when the file is missing/truncated — the front-door card just never un-hides
    # (wrap.style.display stays hidden) and the tab drops to its "not yet computed"
    # placeholder, with no phone alert. It was the last surfaced front-door
    # competitive read (and its non-region sibling rival_threat) with no deploy
    # probe — a truncated CDN deploy that guts it silently blanks the hardest-to-
    # defend card on the exec's first screen, the same "broken demo" blind spot the
    # peer_province / province_pressure / competitor_coverage probes closed for the
    # sibling competitive reads. Asserts render shape (the regions gate + the density/
    # service/class axes each row renders + the headline the readout reads), not
    # values — robust to a future census/rating vintage shifting the ratios.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    regs = d.get("regions")
    if not isinstance(regs, list) or len(regs) < 3:
        return "missing/short 'regions' list (expected the 5 AutoX regions)"
    r0 = regs[0]
    if not isinstance(r0, dict) or not r0.get("region"):
        return "first region missing 'region' name (row render read)"
    if "rivals_vs_autox" not in r0:
        return "first region missing 'rivals_vs_autox' (density axis / outgunned-x render)"
    if "rating_wavg" not in r0:
        return "first region missing 'rating_wavg' (service axis render)"
    if not r0.get("threat_class"):
        return "first region missing 'threat_class' (defensibility class render + #home sort key)"
    if not isinstance(d.get("headline"), str) or not d["headline"].strip():
        return "missing/blank 'headline' (Competition readout gate)"
    return None


def _shape_province_pressure(d):
    # The cross-objective SYNTHESIS layer (province_pressure.json) — the
    # deterministic JOIN of portfolio risk (province_stress_index composite,
    # obj #1) x competitive risk (peer_province rival:AutoX ratio, obj #2), the
    # one read that fuses BOTH standing objectives. It powers the command-center
    # thesis' sharpest cross-objective clause (renderHomeThesis reads
    # meta.n_double_pressure to gate the "N provinces both stressed and
    # outgunned" line and meta.worst_province.province_th for its tail). Its two
    # parents (peer_province + the stress index) are probed, but the join that
    # actually renders on the exec front door was not — a truncated deploy that
    # guts meta.n_double_pressure silently drops the front-door intersection
    # clause with no phone alert, the same "broken demo" blind spot the peer /
    # coverage / flow-card probes closed. Asserts render shape (the meta gate +
    # the province rows carrying the joined axes), not values — robust to a
    # future SES/census vintage shifting the counts.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    provs = d.get("provinces")
    if not isinstance(provs, list) or len(provs) < 70:
        return "missing/short 'provinces' list (expected ~77)"
    p0 = provs[0]
    if not isinstance(p0, dict) or not (isinstance(p0.get("province_th"), str) and p0["province_th"].strip()):
        return "first province missing 'province_th'"
    for k in ("stress_pctile", "contest_pctile"):
        if not isinstance(p0.get(k), (int, float)):
            return "first province missing numeric '%s' (joined axis, board read)" % k
    if "double_pressure" not in p0:
        return "first province missing 'double_pressure' flag (quadrant join read)"
    meta = d.get("meta")
    if not isinstance(meta, dict):
        return "missing 'meta' object"
    if not isinstance(meta.get("n_double_pressure"), int):
        return "meta.n_double_pressure missing/not int (front-door thesis clause hide-gate)"
    w = meta.get("worst_province")
    if not isinstance(w, dict) or not (isinstance(w.get("province_th"), str) and w["province_th"].strip()):
        return "meta.worst_province missing 'province_th' (thesis clause tail read)"
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
    meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
    totals = meta.get("totals")
    if not isinstance(totals, dict) or not isinstance(totals.get("found"), int):
        return "meta.totals.found missing (national census headline)"
    # meta.national_standing powers the exec headline peer claim ("Nationally,
    # AutoX runs the Nth-largest title-loan branch network …"). drawCompCoverage
    # gates the whole readout on `ns && ns.autox_rank && Array.isArray(ns.ranking)`
    # and maps each ranking row's .operator + .branches — so a truncated deploy
    # that drops this block silently vanishes the single most exec-visible
    # peer-comparison line with no phone alert, the exact blind spot this probe
    # closes for the sibling reads. Mirror the render's own reads exactly; robust
    # to roster changes (assert shape + the AutoX row is present, not counts).
    ns = meta.get("national_standing")
    if not isinstance(ns, dict):
        return "meta.national_standing missing (exec network-scale peer headline)"
    if not isinstance(ns.get("autox_rank"), int) or ns["autox_rank"] < 1:
        return "national_standing.autox_rank missing (drawCompCoverage gates the readout on it)"
    if not isinstance(ns.get("n_ranked"), int) or ns["n_ranked"] < 1:
        return "national_standing.n_ranked missing ('of the N big operators …' is rendered directly)"
    ranking = ns.get("ranking")
    if not isinstance(ranking, list) or not ranking:
        return "national_standing.ranking empty (the branch-network-size peer chain)"
    # drawCompCoverage maps EVERY ranking row (o.operator + o.branches), not just
    # the first — so validate every row. A partial truncation like a valid first
    # peer plus a bare {"operator":"AutoX"} would pass a first-row-only check yet
    # render "AutoX 0", missing exactly the own-network anchor this probe guards.
    for o in ranking:
        if not isinstance(o, dict) or not o.get("operator") or not isinstance(o.get("branches"), (int, float)):
            return "national_standing.ranking has a row missing 'operator'/numeric 'branches'"
    if not any(o.get("operator") == "AutoX" for o in ranking):
        return "national_standing.ranking has no AutoX row (own network-scale anchor)"
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


def _shape_scenarios(d):
    # The LIVE / stress scenario engine (#sim, a whole default-reachable nav
    # route). renderScenarios live-fetches it (tmliFetch('scenarios')) and, when
    # `.scenarios` is a non-empty array, renders one card per scenario reading
    # s.kind (badge), s.title + s.headline (card body) and s.vintage. If the
    # array is missing/empty the whole engine falls back to its "not yet
    # computed" placeholder, so a truncated deploy that empties scenarios.json
    # silently blanks the simulator's scenario board with no phone alert — the
    # same "broken demo" blind spot the Competition (peer_province /
    # competitor_coverage / pico_district) and obj-#1 flow-card probes closed for
    # their routes. This is the last default-reachable nav route left unprobed.
    # Robust to a future scenario-count change (asserts non-empty, not ==6).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    scns = d.get("scenarios")
    if not isinstance(scns, list) or not scns:
        return "missing/empty 'scenarios' list (engine render read)"
    s0 = scns[0]
    if not isinstance(s0, dict):
        return "first scenario is not an object"
    for k in ("kind", "title", "headline"):
        if not (isinstance(s0.get(k), str) and s0[k].strip()):
            return "first scenario missing/empty '%s' (card render read)" % k
    return None


def _shape_rival_pulse(d):
    # The always-on rival sentiment watch on Competition (#acq): drawRivalPulse
    # live-fetches it and renders the app-store sentiment ladder from .sentiment
    # (per-brand score / detractor share / 90-day trend) plus the promo feed from
    # .promos. If BOTH are empty it drops to a "not yet pulled" placeholder, so a
    # truncated deploy that guts the file silently blanks the rival sentiment +
    # promo board with no phone alert — the same blind spot the peer_province /
    # competitor_coverage / pico_district probes closed for the other #acq reads.
    # Robust to roster growth (asserts shape, not brand counts).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    sent = d.get("sentiment")
    if not isinstance(sent, list) or not sent:
        return "missing/empty 'sentiment' list (sentiment-ladder render read)"
    s0 = sent[0]
    if not isinstance(s0, dict):
        return "first sentiment row is not an object"
    if not (isinstance(s0.get("brand"), str) and s0["brand"].strip()):
        return "first sentiment row missing/empty 'brand'"
    if not isinstance(s0.get("score"), (int, float)):
        return "first sentiment row missing numeric 'score' (ladder render read)"
    if not isinstance(d.get("promos"), list):
        return "missing 'promos' list (promo-feed render read)"
    return None


def _shape_rival_ads(d):
    # The rival paid-media pulse on Competition (#acq): drawRivalAds live-fetches
    # it and renders the per-operator Google-ad creative table from .brands
    # (n_creatives / n_live / share-of-volume / cadence). Empty .brands drops it
    # to a "not yet run" placeholder, so a truncated deploy that guts the file
    # blanks the paid-media board with no phone alert. Robust to roster growth.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    brands = d.get("brands")
    if not isinstance(brands, list) or not brands:
        return "missing/empty 'brands' list (ad-table render read)"
    b0 = brands[0]
    if not isinstance(b0, dict):
        return "first brand row is not an object"
    if not (isinstance(b0.get("brand"), str) and b0["brand"].strip()):
        return "first brand row missing/empty 'brand'"
    if not isinstance(b0.get("n_creatives"), (int, float)):
        return "first brand row missing numeric 'n_creatives' (ad-table render read)"
    return None


def _shape_rival_youtube(d):
    # The rival video pulse on Competition (#acq): drawRivalVideo live-fetches it
    # and renders the per-operator YouTube table from .channels (subscribers /
    # upload cadence / median views / engagement). Empty .channels drops it to a
    # "not yet pulled" placeholder, so a truncated deploy that guts the file
    # blanks the video board with no phone alert. Robust to roster growth; the
    # render tolerates a null subscribers cell (bought-placement flag), so the
    # probe asserts the key exists rather than a numeric value.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    ch = d.get("channels")
    if not isinstance(ch, list) or not ch:
        return "missing/empty 'channels' list (video-table render read)"
    c0 = ch[0]
    if not isinstance(c0, dict):
        return "first channel row is not an object"
    if not (isinstance(c0.get("brand"), str) and c0["brand"].strip()):
        return "first channel row missing/empty 'brand'"
    if "subscribers" not in c0:
        return "first channel row missing 'subscribers' key (video-table render read)"
    return None


def _shape_rival_density(d):
    # The district-outnumbered board on Competition (#acq, obj #2): drawRivalDensity
    # live-fetches it (renderRivalDensity) and ranks the districts where the big-4
    # rival field most out-stations AutoX — reading .records and, per row, .autox +
    # .rivals (the raw branch deficit the table sorts on) + .by_brand (the "who holds
    # it" single-brand-dominance read). It is the district-grain competitive read the
    # province peer board is built on the same census as, one grain finer. It renders
    # on a default-reachable nav route but was the last #acq board with no deploy
    # probe: an empty/truncated .records drops the whole board to its "not yet
    # computed" placeholder with NO phone alert — the same "broken demo" blind spot
    # the peer_province / competitor_coverage / pico_district probes closed for the
    # other Competition reads. Asserts render shape, not values (robust to a future
    # census refresh shifting counts / district totals).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    recs = d.get("records")
    if not isinstance(recs, list) or not recs:
        return "missing/empty 'records' list (board render read)"
    r0 = recs[0]
    if not isinstance(r0, dict):
        return "first record is not an object"
    for k in ("autox", "rivals"):
        if not isinstance(r0.get(k), (int, float)):
            return "first record missing numeric '%s' (branch-deficit ranking read)" % k
    if not isinstance(r0.get("by_brand"), dict):
        return "first record missing 'by_brand' per-rival split ('who holds it' read)"
    if not (isinstance(r0.get("province_th"), str) and r0["province_th"].strip()):
        return "first record missing 'province_th' (board column read)"
    return None


def _shape_search_demand(d):
    # The share-of-search board on Competition (#acq, obj #2, ESTIMATED): drawSearchDemand
    # builds SDEMAND_LIST from .provinces filtered on .demand and, per row, reads
    # .th + .demand + .autox_share + .best_rival{brand,share} + .autox_sos_rank to
    # render the "brand vs rival search" board and its answer-first verdict clause.
    # It is a default-reachable #acq read that live-degrades to a calm "not yet
    # computed" notice (and the map lens hides itself) when the file is missing —
    # graceful, but silent, so a truncated CDN deploy that guts it drops the board
    # with no phone alert. The builder can also write an HONEST meta.absent state
    # (Google-Trends source genuinely unavailable) that the app treats as a valid
    # empty shape; mirror that here (absent -> OK, not an alert) so the probe fires
    # only on a real truncation. Asserts render shape, not values.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    meta = d.get("meta")
    if isinstance(meta, dict) and meta.get("absent"):
        return None  # builder's honest source-absent guard — a valid empty shape, not a truncation
    provs = d.get("provinces")
    if not isinstance(provs, list) or len(provs) < 70:
        return "missing/short 'provinces' list (expected ~77)"
    demand_rows = [p for p in provs if isinstance(p, dict) and p.get("demand") is not None]
    if not demand_rows:
        return "no province carries a numeric 'demand' (board is built from demand-bearing rows)"
    p0 = demand_rows[0]
    if not (isinstance(p0.get("th"), str) and p0["th"].strip()):
        return "first demand-bearing province missing 'th' name (board column read)"
    if not isinstance(p0.get("demand"), (int, float)):
        return "first demand-bearing province missing numeric 'demand' (board column read)"
    return None


def _shape_household_risk(d):
    # The household debt-to-income lens (obj #1 portfolio risk, MEASURED — NSO SES
    # 2566): loadHhRisk builds HHRISK/HHRISK_LIST from .provinces filtered on
    # .debt_to_income and, per row, reads .province + .debt_to_income (the National-map
    # hhdti hero lens' brightness read, hhriskVal) + .stress_index. It is a MEASURED
    # obj-#1 read that live-degrades to a hidden lens when absent — graceful but
    # silent, so a truncated deploy that guts it drops the DTI lens with no phone
    # alert, the same blind spot the obj-#1 flow-card / province_pressure probes
    # closed. The builder can write an HONEST meta.absent state that the app treats
    # as a valid empty shape; mirror it (absent -> OK). Asserts render shape, not
    # values (robust to a future SES vintage shifting the ratios).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    meta = d.get("meta")
    if isinstance(meta, dict) and meta.get("absent"):
        return None  # builder's honest source-absent guard — a valid empty shape, not a truncation
    provs = d.get("provinces")
    if not isinstance(provs, list) or len(provs) < 70:
        return "missing/short 'provinces' list (expected ~77)"
    dti_rows = [p for p in provs if isinstance(p, dict) and p.get("debt_to_income") is not None]
    if not dti_rows:
        return "no province carries a numeric 'debt_to_income' (the hhdti lens' brightness read)"
    p0 = dti_rows[0]
    if not (isinstance(p0.get("province"), str) and p0["province"].strip()):
        return "first DTI-bearing province missing 'province' name (HHRISK map key)"
    if not isinstance(p0.get("debt_to_income"), (int, float)):
        return "first DTI-bearing province missing numeric 'debt_to_income' (hhriskVal read)"
    return None


def _shape_provenance(d):
    # The Command-center (#home) DATA ROOM card — the exec's core measured /
    # estimated / UNLABELLED honesty census (the "shame board"), the surface the
    # whole project's measured-vs-estimated mandate is judged on. renderHomeDataRoom
    # eager-loads data/provenance.json on the front door (renderHome -> line ~8562)
    # and is NULL-SAFE: when the file is missing/truncated its guard
    # (!PROVEN || !Array.isArray(PROVEN.layers) || !PROVEN.counts) collapses the
    # whole card to a calm "not yet computed" placeholder with NO phone alert — a
    # truncated CDN deploy that drops the provenance census would silently blank the
    # exec's honesty surface, exactly the "broken demo" blind spot this probe exists
    # to catch. It was the last front-door eager read with no deploy probe. The
    # render contract: .counts (the three-way headline split) + a non-empty .layers
    # table (each row reads .file + .cls) + .files.total (the per-file shame note).
    # Asserts render SHAPE, not values — robust to the census growing (it only ever
    # gains layers); a floor guards against a truncated/emptied file.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    counts = d.get("counts")
    if not isinstance(counts, dict):
        return "missing 'counts' (the card's guard drops the whole Data Room without it)"
    for k in ("layers", "measured", "estimated", "unlabelled"):
        if not isinstance(counts.get(k), int):
            return "counts.%s missing/non-int (the measured/estimated/unlabelled headline split)" % k
    layers = d.get("layers")
    if not isinstance(layers, list) or len(layers) < 50:
        return "missing/short 'layers' table (expected the full ~120-layer census)"
    L0 = layers[0]
    if not isinstance(L0, dict) or not (isinstance(L0.get("file"), str) and L0["file"].strip()):
        return "first layer row missing 'file' name (Data Room table render read)"
    if not (isinstance(L0.get("cls"), str) and L0["cls"] in ("measured", "estimated", "unlabelled")):
        return "first layer row missing a valid 'cls' provenance chip (measured/estimated/unlabelled)"
    files = d.get("files")
    if not isinstance(files, dict) or not isinstance(files.get("total"), int):
        return "files.total missing (the per-file shame note read)"
    return None


def _shape_contested_pop(d):
    # The command-center (#home) "MOST CONTESTED GROUND" front-door read (obj #2):
    # renderHomeWhitespace gates its lead competitive-pressure line on
    # `CPOP && Array.isArray(CPOP.top) && CPOP.top.length` and renders top[0]'s
    # .name/.prov/.region + .cpop/.pop (catchment pop within 2km of a rival) +
    # .pct. The National-map contested lens ALSO reads the index-aligned .rows[i]
    # = [pop10, contested_pop] (one row per branch). It is a MEASURED WorldPop ×
    # rival-census overlay that live-degrades SILENTLY — a missing/truncated file
    # just omits the front-door clause and hides the lens, with no phone alert —
    # the same "broken demo" blind spot the peer_province / competitor_coverage /
    # obj-#1 flow-card probes closed for the other exec reads. Asserts the .top
    # leaderboard shape AND the exact index-aligned .rows length (a wrong length
    # silently misaligns every branch's contested-pop lens value), not values;
    # robust to a future census refresh shifting the pop counts.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    top = d.get("top")
    if not isinstance(top, list) or not top:
        return "missing/empty 'top' list (front-door 'most contested ground' render read)"
    t0 = top[0]
    if not isinstance(t0, dict) or not (isinstance(t0.get("name"), str) and t0["name"].strip()):
        return "top[0] missing 'name' (contested-ground headline read)"
    for k in ("pop", "cpop", "pct"):
        if not isinstance(t0.get(k), (int, float)):
            return "top[0] missing numeric '%s' (contested-ground headline read)" % k
    rows = d.get("rows")
    if not isinstance(rows, list) or len(rows) != 2015:
        return "expected 2015 index-aligned 'rows' (one per branch), got %s" % (
            len(rows) if isinstance(rows, list) else type(rows).__name__)
    return None


def _shape_exit_whitespace(d):
    # The Competition (#acq) rival-fragility board (obj #2, ESTIMATED): drawExitWhitespace
    # reads .districts and, per row, .exit_capture_score (the leaderboard sort key) +
    # .name/.province/.region + .branches + .components{sub_scale_proxy, whitespace,
    # big4_competitors}, plus the answer-first readout from meta.competitor_census +
    # meta.regulatory_citation.deadline. An empty/missing .districts drops the whole
    # board to its "Rival-fragility cue not yet computed" placeholder with NO phone
    # alert — the same silent-degrade blind spot the other #acq probes (peer_province /
    # competitor_coverage / pico_district / rival_density / search_demand) closed. It
    # was the last surfaced #acq competitive read with no deploy probe. Asserts render
    # shape (a non-empty district table carrying the sort key + component split, and the
    # meta census block the readout headline reads), not values — robust to a future
    # census/registry refresh. Floor guards a truncated build (928 amphoe expected).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    dists = d.get("districts")
    if not isinstance(dists, list) or len(dists) < 500:
        return "missing/short 'districts' list (expected the ~928-amphoe board)"
    r0 = dists[0]
    if not isinstance(r0, dict):
        return "first district row is not an object"
    if not isinstance(r0.get("exit_capture_score"), (int, float)):
        return "first district missing numeric 'exit_capture_score' (leaderboard sort key)"
    if not (isinstance(r0.get("name"), str) and r0["name"].strip()):
        return "first district missing 'name' (board column read)"
    comps = r0.get("components")
    if not isinstance(comps, dict):
        return "first district missing 'components' split (board cell render read)"
    for k in ("sub_scale_proxy", "whitespace"):
        if not isinstance(comps.get(k), (int, float)):
            return "components.%s missing/non-numeric (board cell render read)" % k
    meta = d.get("meta")
    if not isinstance(meta, dict) or not isinstance(meta.get("competitor_census"), dict):
        return "meta.competitor_census missing (readout headline census-provenance read)"
    return None


def _shape_collateral_book(d):
    # The Overview/Macro tab's SECTION-LEADING collateral read (obj #1) — the
    # "Collateral value — what the titles are worth, and what we hold against
    # them" block. renderCollateralBook GATES the whole section on `j.national
    # && j.types` (else host.style.display='none') and its load-bearing verdict
    # sentence reads N.os / N.core_share_pct / N.ltv_proxy_pct / N.ticket /
    # N.eval_avg, then renders the 8-row collateral-type table (each .type/.tier/
    # .os_share_pct/.dpd90p_pct) plus the fleet-class, resale-flow and brand-book
    # sub-tables. It is MEASURED (real loan tape × DLT registrations) and
    # live-degrades SILENTLY — a missing/truncated file just hides the section
    # with no phone alert — the same "broken demo" blind spot the collateral_flow
    # / truck_flow / tape_real obj-#1 probes closed for their siblings, and it was
    # the last unprobed read from the #258/#261 macro/collateral wave. Asserts the
    # gate + headline render shape (national KPI keys + the type-table rows), not
    # values — robust to a future tape/DLT vintage refresh moving the numbers.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    nat = d.get("national")
    if not isinstance(nat, dict):
        return "missing 'national' object (renderCollateralBook display gate)"
    for k in ("os", "ltv_proxy_pct", "ticket", "eval_avg", "core_share_pct"):
        if not isinstance(nat.get(k), (int, float)):
            return "national.%s missing/non-numeric (collateral-value verdict render read)" % k
    types = d.get("types")
    if not isinstance(types, list) or not types:
        return "missing/empty 'types' list (collateral-type table + display gate)"
    t0 = types[0]
    if not isinstance(t0, dict):
        return "first type row is not an object"
    if not (isinstance(t0.get("type"), str) and t0["type"].strip()):
        return "first type row missing 'type' (type-table row key)"
    for k in ("tier", "os_share_pct"):
        if k not in t0:
            return "first type row missing '%s' (type-table cell render read)" % k
    return None


def _shape_macro_book(d):
    # The Overview/Macro tab's "CONDITIONS AT OUR GRAIN" geo drill (obj #1/#2) —
    # the one drill that replaced five macro sections (labour / fleet / hazard /
    # business-formation / household-debt). renderMacroBook GATES the whole block
    # on `j.national && j.provinces` (else host.style.display='none'), then reads
    # the per-lens note verdicts off national KPIs (unemployment_pct,
    # electrified_pct, diesel_share_pct, flood_high/flood_stations, n_dry/
    # n_districts, new_biz_n, ...), the 77-province drill table off j.provinces,
    # and the header NPL sparkline off j.npl. It is the sibling of collateral_book
    # from the #258/#261 macro wave and was the last unprobed read from it — the
    # audit's own "next probe targets" note. It live-degrades SILENTLY: a missing
    # or truncated file just hides the primary conditions-at-our-grain screen with
    # no phone alert, the exact "broken demo" blind spot the collateral_book /
    # collateral_flow / tape_real obj-#1 probes closed for their siblings. Asserts
    # the gate + headline render shape (national KPI keys the notes read + the
    # 77-province drill + the npl header), not values — robust to a future tape/
    # DLT/ThaiWater vintage refresh moving the numbers.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    nat = d.get("national")
    if not isinstance(nat, dict):
        return "missing 'national' object (renderMacroBook display gate)"
    for k in ("unemployment_pct", "electrified_pct", "diesel_share_pct",
              "flood_high", "flood_stations", "n_dry", "n_districts", "new_biz_n"):
        if not isinstance(nat.get(k), (int, float)):
            return "national.%s missing/non-numeric (per-lens note verdict render read)" % k
    provs = d.get("provinces")
    if not isinstance(provs, dict) or not provs:
        return "missing/empty 'provinces' object (renderMacroBook display gate + drill table)"
    p0 = next(iter(provs.values()))
    if not isinstance(p0, dict) or "region" not in p0 or "os" not in p0:
        return "first province row missing region/os (drill-table cell render read)"
    npl = d.get("npl")
    if not isinstance(npl, dict) or not isinstance(npl.get("series"), list) or not npl["series"]:
        return "missing 'npl.series' (header NPL sparkline render read)"
    return None


def _shape_farm_book(d):
    # The Overview tab's "Farm book — where the crop mix meets our money" section
    # (obj #1) — the load-bearing crop-to-portfolio read. renderFarmBook GATES the
    # whole block on `j.national && j.provinces` (else host.style.display='none'),
    # then its verdict sentence reads N.farm_os / N.farm_weighted_mix_pct /
    # N.neg_provinces / N.neg_farm_os / N.neg_share_of_os_pct / N.neg_farm_n /
    # N.neg_current / N.book_weighted_mix_pct, and the "the crop that MOVED the book
    # is not the crop that IS the book" commentary line reads j.crops (each .en /
    # .os_share_pct / .pp_of_book / .farm_os_alloc / .yoy). It is MEASURED (real
    # loan tape × OAE crop mix × farm-gate prices) and live-degrades SILENTLY — a
    # missing/truncated file just hides the primary obj-#1 farm read with no phone
    # alert, the same "broken demo" blind spot the collateral_book / macro_book /
    # tape_real obj-#1 probes closed for their siblings, and it was the sibling the
    # audit's own "next probe targets" note flagged after macro_book. Asserts the
    # gate + headline render shape (national KPI keys + non-empty province dict +
    # the crops commentary rows), not values — robust to a future tape/crop/price
    # vintage refresh moving the numbers.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    nat = d.get("national")
    if not isinstance(nat, dict):
        return "missing 'national' object (renderFarmBook display gate)"
    for k in ("farm_os", "farm_weighted_mix_pct", "neg_provinces", "neg_farm_os",
              "neg_share_of_os_pct", "neg_farm_n", "neg_current", "book_weighted_mix_pct"):
        if not isinstance(nat.get(k), (int, float)):
            return "national.%s missing/non-numeric (farm-book verdict render read)" % k
    provs = d.get("provinces")
    if not isinstance(provs, dict) or not provs:
        return "missing/empty 'provinces' object (renderFarmBook display gate)"
    crops = d.get("crops")
    if not isinstance(crops, list) or not crops:
        return "missing/empty 'crops' list (crop-mix commentary render read)"
    c0 = crops[0]
    if not isinstance(c0, dict):
        return "first crop row is not an object"
    if not (isinstance(c0.get("en"), str) and c0["en"].strip()):
        return "first crop row missing 'en' (crop-name commentary render read)"
    for k in ("os_share_pct", "pp_of_book", "farm_os_alloc", "yoy"):
        if not isinstance(c0.get(k), (int, float)):
            return "first crop row %s missing/non-numeric (crop-mix commentary render read)" % k
    return None


def _shape_flood_hazard(d):
    # The Exposure (#exposure) tab's "Portfolio flood-hazard exposure" read (obj #1)
    # — the MEASURED GISTDA Repeated-Flooding 2005-2016 census projected to a per-
    # branch structural-hazard flag. loadFloodHazard sets FLOODHZ = j.branches (the
    # 0-12 MAX-flood-frequency array, INDEX-ALIGNED to branches.json) and floodhzMeta
    # = j.meta; renderFloodExposure gates the whole panel on `FLOODHZ && FLOODHZ.length`
    # (else host.innerHTML='' — renders nothing) and reads FLOODHZ[i] per branch to
    # tally the region/province chronic-flood tables + the frequency-band ladder, plus
    # floodhzMeta.source / .data_vintage for the header citation. It live-degrades
    # SILENTLY — a missing/truncated CDN deploy just blanks the primary obj-#1 flood-
    # exposure screen with no phone alert, the same "broken demo" blind spot the
    # collateral_book / macro_book / farm_book obj-#1 probes closed for their siblings,
    # and it was the audit's own flagged "next probe target" after farm_book. Asserts
    # the render contract — a full-length 2015-branch index-aligned 0-12 array + the
    # meta header keys — as SHAPE not values, robust to a future GISTDA-vintage refresh
    # moving the frequencies.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    recs = d.get("branches")
    if not isinstance(recs, list) or not recs:
        return "missing/empty 'branches' array (renderFloodExposure display gate)"
    if len(recs) != 2015:
        return "expected 2015 branch frequencies (index-aligned to branches.json), got %d" % len(recs)
    ints = [f for f in recs if isinstance(f, int) and not isinstance(f, bool)]
    if not ints:
        return "no branch carries a numeric flood frequency (FLOODHZ[i] band-tally read)"
    if min(ints) < 0 or max(ints) > 12:
        return "flood frequency out of the 0-12 census range (min %d, max %d)" % (min(ints), max(ints))
    meta = d.get("meta")
    if not isinstance(meta, dict):
        return "missing 'meta' object (header citation render read)"
    for k in ("source", "data_vintage"):
        if not (isinstance(meta.get(k), str) and meta[k].strip()):
            return "meta.%s missing/blank (flood-exposure header citation render read)" % k
    return None


def _shape_deltas(d):
    # The TIME dimension (deltas.json, obj #1 — which segments/branches are getting
    # riskier between vintages). It renders on the exec FRONT DOOR (renderHomeMovers
    # draws the command-center "Movers" card off DELTAS.region + DELTAS.branches) AND
    # is the whole payload of the Risk-trend tab (#trend reads DELTAS.board YoY
    # re-ratings + the region/branch mover rows). Both degrade to a CALM empty state
    # when the file is missing/truncated — and that is exactly the trap: a fetch
    # failure or a gutted CDN deploy silently renders "Baseline captured — trends
    # appear after the next data refresh", MASQUERADING a broken file as the normal
    # single-vintage baseline, with no phone alert, hiding real obj-#1 risk movement.
    # It was the last surfaced front-door read with no deploy probe. Asserts the
    # render shape both surfaces read, NOT values — and stays healthy in a legitimate
    # baseline vintage (baseline===true, movers genuinely absent), so it won't false-
    # alarm if the snapshot history is ever reset to one vintage.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    if "baseline" not in d:
        return "missing 'baseline' flag (renderHomeMovers/#trend gate read)"
    if not (isinstance(d.get("to"), str) and d["to"].strip()):
        return "missing/blank 'to' vintage label (empty-state + header render read)"
    if d.get("baseline"):
        return None  # legitimate single-vintage baseline — movers absent by design, healthy
    # Populated diff: assert the mover shapes both surfaces render off.
    brs = d.get("branches")
    if not isinstance(brs, list) or not brs:
        return "non-baseline deltas with missing/empty 'branches' movers (#home + #trend branch-mover render)"
    b0 = brs[0]
    if not isinstance(b0, dict) or not b0.get("n") or "comp" not in b0:
        return "first branch mover missing 'n'/'comp' (branch-mover row render read)"
    reg = d.get("region")
    if not isinstance(reg, list) or not reg:
        return "non-baseline deltas with missing/empty 'region' movers (#home region-mover render)"
    r0 = reg[0]
    if not isinstance(r0, dict) or not r0.get("r") or "d_agri" not in r0:
        return "first region mover missing 'r'/'d_agri' (region-mover row render read)"
    if not isinstance(d.get("board"), list):
        return "missing 'board' commodity-YoY list (#trend board re-rating render read)"
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
    # The last eager Overview macro card left unprobed (renderSfi, loaded on the
    # default #overview route): the MEASURED state-bank (SFI) system NPL backdrop,
    # obj #1's closest public read on household + farm repayment stress. The other
    # Overview flow/backdrop cards (collateral_flow / truck_flow / region_debt) are
    # already probed; this closes the matching macro-NPL blind spot so a truncated
    # deploy that guts the FPO NPL series fires a phone alert instead of silently
    # hiding the backdrop card.
    ("data/sfi_credit.json", _shape_sfi_credit, ".series[] (FPO quarterly) + meta.latest.npl_ratio (Overview NPL backdrop)"),
    # The competition pillar's flagship exec layer (obj #2) — the per-province
    # peer board (AutoX next to each big-4 rival, per province) that powers the
    # Competition surface + the command-center thesis clause. Every default-route
    # obj-#1 flow card is now probed; this closes the matching obj-#2 blind spot
    # so a truncated deploy that guts the competitive board triggers a phone alert.
    ("data/peer_province.json", _shape_peer_province, ".provinces (~77) with .by_brand per-rival split + meta.total_autox"),
    # The cross-objective SYNTHESIS the exec front door leads with: province_pressure
    # is the deterministic JOIN of portfolio risk (obj #1) x competitive risk (obj
    # #2). Both parents are probed above (peer_province + province_risk/stress); the
    # join that actually renders the command-center "N provinces both stressed and
    # outgunned" thesis clause (renderHomeThesis reads meta.n_double_pressure +
    # meta.worst_province) was the last front-door read with no deploy probe. A
    # truncated deploy that guts it silently drops the intersection clause with no
    # phone alert — closes that blind spot.
    ("data/province_pressure.json", _shape_province_pressure, ".provinces (~77) joined axes + meta.n_double_pressure/worst_province (front-door thesis)"),
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
    # The LIVE/stress scenario engine (#sim) — the last default-reachable nav
    # route with no probe. renderScenarios reads .scenarios[] (kind/title/
    # headline per card); an empty/truncated build drops the whole engine to its
    # "not yet computed" placeholder with no phone alert. Closes the #sim gap the
    # 2026-07-30 board_vintage provenance run flagged as the next probe target.
    ("data/scenarios.json", _shape_scenarios, ".scenarios[] with kind/title/headline (#sim engine)"),
    # The always-on rival-pulse trio on Competition (#acq, shipped #217): the
    # app-store sentiment ladder (rival_pulse), the Google paid-media board
    # (rival_ads) and the YouTube video board (rival_youtube). All three are
    # live-fetched into the Competition surface but were the last #acq reads with
    # no deploy probe — a truncated CDN deploy that emptied any one silently
    # blanked its board and dropped it to a "not yet pulled" placeholder with no
    # phone alert. Adding them closes the Competition surface's remaining
    # deploy-health blind spot (flagged as the next probe target by the
    # 2026-07-30 scenarios/ad-copy-wrap runs). Robust to roster growth.
    ("data/rival_pulse.json", _shape_rival_pulse, ".sentiment ladder + .promos feed (#acq rival watch)"),
    ("data/rival_ads.json", _shape_rival_ads, ".brands ad-creative board (#acq paid-media pulse)"),
    ("data/rival_youtube.json", _shape_rival_youtube, ".channels video board (#acq video pulse)"),
    # The three exec-facing reads flagged as the next probe targets by the 2026-08-01
    # province_pressure run — each renders on a default-reachable route and
    # live-degrades SILENTLY when its file is missing, so a truncated CDN deploy
    # blanks it with no phone alert:
    #  - rival_density: the #acq district-outnumbered board (obj #2), the district-grain
    #    sibling of the already-probed peer_province province board;
    #  - search_demand: the #acq share-of-search board (obj #2, ESTIMATED);
    #  - household_risk_by_province: the obj-#1 household DTI hero map lens (MEASURED).
    # rival_density has no absent-state (it's a straight census rollup); the other two
    # carry the builder's honest meta.absent guard, which their probes treat as a
    # valid empty shape (see the shape fns). Closes the last three surfaced-but-unprobed
    # exec reads across both standing objectives.
    ("data/rival_density.json", _shape_rival_density, ".records (928 districts) with autox/rivals/by_brand (#acq district-outnumbered board)"),
    ("data/search_demand.json", _shape_search_demand, ".provinces (~77) with demand/autox_share/best_rival (#acq share-of-search)"),
    ("data/household_risk_by_province.json", _shape_household_risk, ".provinces (~77) with debt_to_income (obj #1 DTI map lens)"),
    # The Command-center DATA ROOM honesty census — the exec front door's core
    # measured / estimated / UNLABELLED provenance table (renderHomeDataRoom eager-
    # loads data/provenance.json on #home). It is the surface the project's whole
    # measured-vs-estimated mandate is judged on and is NULL-SAFE (silently collapses
    # to a "not yet computed" placeholder when the file is missing/truncated), so a
    # truncated CDN deploy that guts it blanks the honesty board with no phone alert.
    # It was the last front-door eager read still unprobed; this closes that blind
    # spot. Asserts render shape (counts split + layers table + files.total), not
    # values — robust to the census growing.
    ("data/provenance.json", _shape_provenance, ".counts split + .layers (~120) census table + .files.total (Data Room honesty card)"),
    # The two remaining surfaced-but-unprobed competitive reads (obj #2), each on a
    # default-reachable route and each live-degrading SILENTLY when its file is
    # missing/truncated (no phone alert) — the same "broken demo" blind spot the
    # prior peer_province / competitor_coverage / pico_district / rival trio /
    # rival_density / search_demand probes closed for their siblings:
    #  - contested_pop: the command-center (#home) "MOST CONTESTED GROUND" front-door
    #    lead (renderHomeWhitespace reads CPOP.top) + the National-map contested lens
    #    (index-aligned .rows[i]=[pop10, contested_pop]);
    #  - exit_whitespace: the Competition (#acq) rival-fragility board under the
    #    Q1-2026 BoT registration deadline (drawExitWhitespace reads .districts +
    #    meta.competitor_census) — the last unprobed #acq competitive read.
    # Closes the Competition surface's + front-door's remaining obj-#2 deploy-health gap.
    ("data/contested_pop.json", _shape_contested_pop, ".top contested-ground leaderboard + 2015 index-aligned .rows (#home lead + map lens)"),
    ("data/exit_whitespace.json", _shape_exit_whitespace, ".districts (~928) fragility board + meta.competitor_census (#acq rival-fragility)"),
    # The Overview/Macro tab's section-leading collateral read (obj #1), shipped in
    # the #258/#261 macro/collateral wave with no deploy probe. renderCollateralBook
    # gates the whole "Collateral value" section on `j.national && j.types`, so a
    # truncated CDN deploy that drops either silently hides the primary obj-#1
    # collateral-value screen (real loan tape × DLT) with no phone alert — the same
    # blind spot the collateral_flow / truck_flow / tape_real probes closed for the
    # sibling obj-#1 reads. Asserts the gate + verdict render shape, not values.
    ("data/collateral_book.json", _shape_collateral_book, ".national KPI block + .types collateral-type table (Overview collateral section)"),
    # The sibling from the same #258/#261 macro wave, and the audit's own flagged
    # "next probe target". renderMacroBook gates the whole "CONDITIONS AT OUR
    # GRAIN" geo drill (the one that replaced five macro sections) on `j.national
    # && j.provinces`, so a truncated CDN deploy that drops either silently hides
    # the primary conditions screen with no phone alert. Asserts the gate +
    # per-lens verdict render shape (national KPIs + 77-province drill + npl
    # header), not values.
    ("data/macro_book.json", _shape_macro_book, ".national KPI block + 77-province drill + .npl header (Overview conditions-at-our-grain drill)"),
    # The obj-#1 sibling from the crop/tape line, and the audit's own next flagged
    # "next probe target" after macro_book. renderFarmBook gates the whole "Farm
    # book — where the crop mix meets our money" section on `j.national &&
    # j.provinces`, so a truncated CDN deploy that drops either silently hides the
    # primary crop-to-portfolio read with no phone alert. Asserts the gate +
    # verdict/commentary render shape (national KPIs + province dict + crops rows),
    # not values.
    ("data/farm_book.json", _shape_farm_book, ".national KPI block + province drill + .crops commentary (Overview farm-book section)"),
    # The Exposure (#exposure) tab's flagship obj-#1 flood read, and the audit's own
    # flagged "next probe target" after farm_book. renderFloodExposure gates the whole
    # "Portfolio flood-hazard exposure" panel on `FLOODHZ && FLOODHZ.length` (the
    # per-branch 0-12 MAX-flood-frequency array, index-aligned to branches.json), so a
    # truncated CDN deploy that drops or empties it silently blanks the primary
    # structural-hazard screen (MEASURED GISTDA 50k census) with no phone alert — the
    # same blind spot the collateral_book / macro_book / farm_book probes closed for
    # the sibling obj-#1 reads. Asserts the index-aligned array shape + the meta header
    # citation keys, not values.
    ("data/flood_hazard.json", _shape_flood_hazard, ".branches 0-12 array of 2015 (index-aligned) + meta.source/data_vintage (Exposure flood-hazard panel)"),
    # The per-region density x service JOIN (rival_threat_region.json, obj #2) — the
    # last surfaced FRONT-DOOR competitive read with no deploy probe. It renders on
    # the command-center "Where the network is hardest to defend" card (renderHomeDefend)
    # AND the Competition per-region table (drawRivThreatRegion), both gated on a
    # non-empty .regions array, both degrading SILENTLY (the #home card never un-hides;
    # the tab drops to "not yet computed") with no phone alert when a truncated CDN
    # deploy guts it — the same "broken demo" blind spot the peer_province /
    # province_pressure / competitor_coverage probes closed for the sibling competitive
    # reads. Asserts the render shape (regions gate + density/service/class axes + the
    # headline the readout reads), not values.
    ("data/rival_threat_region.json", _shape_rival_threat_region, ".regions (5) density×service axes + threat_class + .headline (#home hardest-to-defend card + #acq table)"),
    # The TIME dimension (deltas.json, obj #1) — the last surfaced FRONT-DOOR read with
    # no deploy probe. Renders the command-center "Movers" card (renderHomeMovers off
    # .region + .branches) AND is the whole Risk-trend tab payload (.board YoY re-ratings
    # + mover rows). A truncated/404 file degrades to a CALM "Baseline captured" state on
    # BOTH surfaces — masquerading a broken deploy as the normal single-vintage baseline,
    # with no phone alert, silently hiding real obj-#1 risk movement. Asserts the mover
    # render shape (baseline gate + branch/region mover fields + the #trend board list),
    # shape not values, and stays green in a legitimate baseline vintage.
    ("data/deltas.json", _shape_deltas, ".baseline gate + .branches/.region movers + .board YoY (#home Movers card + #trend tab)"),
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
