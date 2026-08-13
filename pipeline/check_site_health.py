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
import calendar
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


def _shape_tape_occ(d):
    # The MEASURED real loan-tape occupation cut (obj #1) — the #exposure
    # occupation panel + drill (renderAssistOccMacro / renderAssistOcc). Both
    # GATE their render on `geo.regions` and degrade SILENTLY to a "not yet
    # computed" note when it is missing, with NO phone alert; and unlike its
    # probed sibling tape_real, this layer CANNOT self-heal (owner-side tape,
    # no CI job re-pulls it), so a truncated/404 CDN deploy blanks a primary
    # portfolio screen unnoticed — the exact "broken demo" this probe catches.
    # Assert SHAPE not values (robust to a future tape vintage): the regions
    # dict the macro panel aggregates (aodAgg reads each region's cell list for
    # `occupation` + `n`) and the branches list the drill navigates (`branch`
    # /`prov`/`region`).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    regs = d.get("regions")
    if not isinstance(regs, dict) or not regs:
        return "missing/empty 'regions' dict (occupation panel render gate)"
    cells = next(iter(regs.values()))
    if not isinstance(cells, list) or not cells:
        return "a 'regions' entry is not a non-empty cell list"
    c0 = cells[0]
    if not isinstance(c0, dict) or "occupation" not in c0 or "n" not in c0:
        return "region cell missing 'occupation'/'n' (aodAgg reads)"
    brs = d.get("branches")
    if not isinstance(brs, list) or not brs:
        return "missing/empty 'branches' list (occupation drill)"
    b0 = brs[0]
    if not isinstance(b0, dict) or not all(k in b0 for k in ("branch", "prov", "region")):
        return "branch row missing 'branch'/'prov'/'region' (drill navigation)"
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


def _shape_vehicle_registry(d):
    # The MEASURED collateral base card on Overview (#overview), obj #1 — the
    # eager `loadVehReg().then(renderVehReg)` on the default nav route. The render
    # HIDES the whole block on `!VEHREG || !VEHREG.latest`, then paints four
    # collateral-class cards from `latest.groups[motorcycle|car|pickup|agri]` and a
    # note headline from `latest.title_base` / `latest.all_vehicles` / `meta.vintage`.
    # A truncated/404 CDN deploy that emptied or short-served it would silently blank
    # the "≈half the book is motorcycle title" collateral read on the exec Overview
    # with NO phone alert — the exact broken-demo this check exists to catch. Asserts
    # the render contract (shape, not counts) so a future DLT vintage bump still passes.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    latest = d.get("latest")
    if not isinstance(latest, dict):
        return "missing 'latest' object (renderVehReg hide-gate: !VEHREG.latest)"
    groups = latest.get("groups")
    if not isinstance(groups, dict) or not groups:
        return "missing/empty latest.groups (the four collateral-class card render reads)"
    if not isinstance(groups.get("motorcycle"), (int, float)):
        return "latest.groups.motorcycle not numeric (the small-ticket title core card, ~half the book)"
    if not isinstance(latest.get("title_base"), (int, float)):
        return "latest.title_base not numeric (the note 'NM registered ...' headline read)"
    if not isinstance(latest.get("all_vehicles"), (int, float)):
        return "latest.all_vehicles not numeric (the note 'of NM vehicles' read)"
    meta = d.get("meta")
    if not isinstance(meta, dict):
        return "missing 'meta' object"
    if not (isinstance(meta.get("vintage"), str) and meta["vintage"].strip()):
        return "meta.vintage missing/empty (the note vintage read)"
    return None


def _shape_drought_district(d):
    # The MODELLED district-grain drought read on Overview (#overview), obj #1 —
    # eager `loadDroughtDistrict().then(renderDroughtDistrict)` on the default nav
    # route, sharpening the coarser province crop-stress verdict to the district.
    # The render HIDES the block on an empty `.districts` list, tallies the
    # verdict line from `meta.counts` (extreme/severe/moderate), and the
    # driest-districts table renders only rows carrying a numeric `spei` + a `cls`.
    # A truncated deploy that emptied it would silently drop the district drought
    # card with no phone alert. Asserts shape (a non-empty districts list, one
    # render-eligible row, meta.counts), not values — robust to a future SPEI snapshot.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    ds = d.get("districts")
    if not isinstance(ds, list) or not ds:
        return "missing/empty 'districts' list (renderDroughtDistrict hide-gate + table render)"
    rec = next(
        (x for x in ds if isinstance(x, dict) and isinstance(x.get("spei"), (int, float)) and x.get("cls")),
        None,
    )
    if rec is None:
        return "no district row with numeric 'spei' + 'cls' (the driest-districts table render reads none)"
    meta = d.get("meta")
    if not isinstance(meta, dict):
        return "missing 'meta' object"
    if not isinstance(meta.get("counts"), dict):
        return "missing 'meta.counts' object (the extreme/severe/moderate verdict-line reads)"
    return None


def _shape_amphoe_crops(d):
    # The crop x drought exposure card on Overview (#overview), obj #1 — eager
    # `loadAmphoeCrops().then(renderAmphoeCrops)` on the default nav route (which
    # slice of the agri-PD book sits under the driest ground). The render HIDES the
    # block unless `.hotspots` has a row with BOTH `planted_rai != null` and
    # `spei != null` (its own filter), then the largest-exposure verdict + the
    # exposure table read that row's province_th / amphoe_th / crop / planted_rai /
    # spei / drought. A truncated deploy that emptied it silently drops the exposure
    # card with no phone alert. Asserts the render contract (a filter-surviving
    # hotspot carrying the join keys), not values — robust to a future OAE vintage.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    hs = d.get("hotspots")
    if not isinstance(hs, list) or not hs:
        return "missing/empty 'hotspots' list (renderAmphoeCrops hide-gate + table render)"
    rec = next(
        (
            h
            for h in hs
            if isinstance(h, dict)
            and h.get("planted_rai") is not None
            and h.get("spei") is not None
            and h.get("province_th")
            and h.get("amphoe_th")
            and h.get("drought")
        ),
        None,
    )
    if rec is None:
        return "no hotspot with planted_rai+spei+province_th+amphoe_th+drought (the exposure table render reads none)"
    meta = d.get("meta")
    if not isinstance(meta, dict):
        return "missing 'meta' object"
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


def _shape_rival_threat(d):
    # The brand-level density x service matrix (rival_threat.json, obj #2) — the
    # per-BRAND sibling of rival_threat_region (whose probe comment already named
    # this file as its one unprobed twin). It renders the Competition (#acq)
    # "rival threat matrix" (drawRivThreat): each big-4 rival's national footprint
    # ×AutoX (ESTIMATED company-IR headline, MEASURED census in the sub-line) next
    # to its MEASURED Google service rating, so the strongest COMBINED threat reads
    # at a glance. The render gates the whole board on a non-empty .brands array
    # and, per row, reads .brand (name), .footprint_vs_autox (the ×AutoX ratio —
    # the board's primary quantitative column) and .threat_class (the Threat column
    # + its risk-colour), plus .headline for the readout. It degrades SILENTLY — a
    # missing/truncated file drops the board to its "Rival threat matrix not yet
    # computed" placeholder with NO phone alert — the same "broken demo" blind spot
    # the peer_province / competitor_coverage / rival_threat_region probes closed
    # for the sibling competitive reads. Asserts render shape (the brands gate, the
    # brand/threat_class columns each row renders, at least one numeric ×AutoX
    # ratio, and the headline the readout reads), not values — robust to a future
    # census/rating vintage shifting the ratios.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    brands = d.get("brands")
    if not isinstance(brands, list) or len(brands) < 3:
        return "missing/short 'brands' list (expected the big-4 rivals)"
    b0 = brands[0]
    if not isinstance(b0, dict):
        return "first brand row is not an object"
    if not (isinstance(b0.get("brand"), str) and b0["brand"].strip()):
        return "first brand row missing/empty 'brand' (matrix row name render)"
    if not (isinstance(b0.get("threat_class"), str) and b0["threat_class"].strip()):
        return "first brand row missing/empty 'threat_class' (Threat column render + colour key)"
    if not any(isinstance(b, dict) and isinstance(b.get("footprint_vs_autox"), (int, float)) for b in brands):
        return "no brand carries a numeric 'footprint_vs_autox' (the ×AutoX ratio column)"
    if not (isinstance(d.get("headline"), str) and d["headline"].strip()):
        return "missing/blank 'headline' (Competition readout render read)"
    return None


def _shape_regional_outlook(d):
    # The Overview (#overview) LEAD narrative (regional_outlook.json) — a pure
    # deterministic rollup of the SAME per-branch recs the map shows, and the very
    # first thing the Overview tab renders: renderNationalOutlook draws the "Bottom
    # line" insight straight off OUTLOOK.national.headline, and the region rows carry
    # the per-province .metrics that provDetailHTML reveals in the risk-drill
    # (region -> province -> branch). The whole #outlook block is null-guarded to
    # render NOTHING when the file is absent (loadOutlook swallows a non-200), so a
    # truncated CDN deploy that drops or empties it silently blanks the Overview's
    # lead answer with NO phone alert — the same "broken demo" blind spot the
    # collateral_book / macro_book / farm_book / rival_threat_region probes closed
    # for the sibling front-door reads. Asserts the render shape (the national.headline
    # the lead insight reads, the 5 macro-region rows carrying per-province drills, and
    # a ~77-province total across regions), not values — robust to a future vintage
    # reshuffling the narrative or the recommendations.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    nat = d.get("national")
    if not isinstance(nat, dict):
        return "missing 'national' block (Overview lead render read)"
    if not (isinstance(nat.get("headline"), str) and nat["headline"].strip()):
        return "national.headline missing/blank (the 'Bottom line' insight render)"
    regs = d.get("regions")
    if not isinstance(regs, list) or len(regs) != 5:
        return "expected 5 macro-region rows, got %s" % (
            len(regs) if isinstance(regs, list) else type(regs).__name__)
    r0 = regs[0]
    if not isinstance(r0, dict) or not isinstance(r0.get("provinces"), list):
        return "first region missing 'provinces' drill list"
    tot = sum(len(r.get("provinces", [])) for r in regs if isinstance(r, dict))
    if tot < 70:
        return "only %d provinces across regions (expected ~77 — truncated build)" % tot
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


def _shape_rival_reputation(d):
    # The rival SERVICE-REPUTATION board (rival_reputation.json, obj #2, MEASURED
    # sample) — the QUALITY layer on top of rival density: review-count-weighted
    # Google rating by brand. It is the shared PARENT of the two already-probed
    # threat layers (rival_threat + rival_threat_region both consume its ratings),
    # yet the file has its OWN render board and was itself unprobed — a truncated
    # CDN deploy that guts it silently blanks the "rival service reputation" board
    # (drawRivRep) while the pre-built, committed threat siblings keep rendering,
    # masking the breakage with no phone alert. drawRivRep GATES the whole board on
    # a non-empty .by_brand array and, per row, reads .brand (name) + .rating_wavg
    # (the review-weighted rating — the board's primary quantitative column, and the
    # colour scale), and the readout reads .headline + meta.n_rated/.reviews. It
    # degrades SILENTLY to a "Rival reputation not yet computed" placeholder — the
    # same "broken demo" blind spot the peer_province / competitor_coverage /
    # rival_threat probes closed for the sibling competitive reads. Asserts render
    # shape (the by_brand gate, the brand name each row renders, at least one numeric
    # rating_wavg, and the headline the readout reads), not values — robust to a
    # future rating-vintage refresh shifting the scores.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    brands = d.get("by_brand")
    if not isinstance(brands, list) or len(brands) < 3:
        return "missing/short 'by_brand' list (expected the rated rival brands)"
    b0 = brands[0]
    if not isinstance(b0, dict):
        return "first by_brand row is not an object"
    if not (isinstance(b0.get("brand"), str) and b0["brand"].strip()):
        return "first by_brand row missing/empty 'brand' (board row name render)"
    if not any(isinstance(b, dict) and isinstance(b.get("rating_wavg"), (int, float)) for b in brands):
        return "no brand carries a numeric 'rating_wavg' (the weighted-rating column + colour scale)"
    if not (isinstance(d.get("headline"), str) and d["headline"].strip()):
        return "missing/blank 'headline' (rival-reputation readout render read)"
    return None


def _shape_peer_scoreboard(d):
    # The listed-peer MARKET scoreboard (peer_scoreboard.json, obj #2, MEASURED) —
    # SET market cap / valuation / ROE / net profit for the 3-4 listed title-lenders,
    # with AutoX's 25% ROE TARGET as the reference line. The code itself calls it
    # "the sharpest external benchmark we have", yet it was the last unprobed obj-#2
    # peer read on the Competition surface. drawPeerScore GATES the whole board on a
    # non-empty .peers array (else it silently drops to a calm "Listed-peer scoreboard
    # not available" placeholder with NO phone alert), and per row renders p.name/
    # p.symbol + p.market_cap_bn (the bold "Mkt cap" column) + p.roe (the ROE column,
    # its bar, AND the readout's benchmark clause vs the 25% target). The readout leads
    # with .headline and hangs its "would sit above / below" clause on .autox_roe_target.
    # SET is Akamai-blocked from CI (owner-side refresh only), so this file cannot self-
    # heal — a truncated/404 CDN deploy that guts it is exactly the "broken demo" blind
    # spot the peer_province / competitor_coverage / rival_reputation probes close for
    # the sibling competitive reads. Asserts render shape (the peers gate, the row name/
    # symbol, a numeric market-cap column, a numeric ROE, the non-blank headline, and the
    # numeric ROE reference line), not values — robust to a future SET price/quarter pull.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    peers = d.get("peers")
    if not isinstance(peers, list) or len(peers) < 3:
        return "missing/short 'peers' list (expected the listed title-lender rows)"
    p0 = peers[0]
    if not isinstance(p0, dict):
        return "first peers row is not an object"
    if not ((isinstance(p0.get("name"), str) and p0["name"].strip())
            or (isinstance(p0.get("symbol"), str) and p0["symbol"].strip())):
        return "first peers row missing 'name'/'symbol' (scoreboard row label render)"
    if not any(isinstance(p, dict) and isinstance(p.get("market_cap_bn"), (int, float)) for p in peers):
        return "no peer carries a numeric 'market_cap_bn' (the 'Mkt cap' column)"
    if not any(isinstance(p, dict) and isinstance(p.get("roe"), (int, float)) for p in peers):
        return "no peer carries a numeric 'roe' (the ROE column + bar + benchmark clause)"
    if not (isinstance(d.get("headline"), str) and d["headline"].strip()):
        return "missing/blank 'headline' (peer-scoreboard readout render read)"
    if not isinstance(d.get("autox_roe_target"), (int, float)):
        return "missing/non-numeric 'autox_roe_target' (the ROE reference line the readout benchmarks against)"
    return None


def _shape_peer_npl(d):
    # The peer LOAN-QUALITY benchmark (peer_npl.json, obj #1 + #2) — the listed
    # title-lenders' OWN reported NPL ratios (docs/RESEARCH_DIGEST.md §B, FY2025 /
    # 2025 IR) shown next to AutoX's MEASURED own-book NPL from the real loan tape.
    # The last surfaced obj-#2 peer read on the Competition surface with no deploy
    # probe. Like peer_scoreboard it CANNOT self-heal — its peer figures come from
    # an off-repo research doc and the AutoX anchor from the owner-side tape, neither
    # of which any CI job re-pulls — so a truncated/404 CDN deploy that guts it has no
    # job to restore it. drawPeerNpl GATES the whole board on a non-empty .peers array
    # (else it silently drops to the calm "Peer NPL benchmark not available" placeholder
    # with NO phone alert), and per row renders p.name/p.ticker + p.npl (numeric — the
    # bar, the colour band, the label, AND the readout's best/worst spread clause) +
    # p.collateral + p.source. The distinct MEASURED AutoX row renders .autox.name +
    # .npl_live_os_pct (numeric, .toFixed(2) — bar + readout) + .npl_90plus_os_pct
    # (numeric, .toFixed(1)). Asserts render shape (the peers gate + row label + a
    # numeric npl column + the AutoX anchor's two numeric NPL fields), not values —
    # robust to a future RESEARCH_DIGEST / tape-vintage refresh moving the ratios.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    peers = d.get("peers")
    if not isinstance(peers, list) or len(peers) < 2:
        return "missing/short 'peers' list (expected the reported title-lender NPL rows)"
    p0 = peers[0]
    if not isinstance(p0, dict):
        return "first peers row is not an object"
    if not ((isinstance(p0.get("name"), str) and p0["name"].strip())
            or (isinstance(p0.get("ticker"), str) and p0["ticker"].strip())):
        return "first peers row missing 'name'/'ticker' (peer-NPL row label render)"
    if not any(isinstance(p, dict) and isinstance(p.get("npl"), (int, float)) for p in peers):
        return "no peer carries a numeric 'npl' (the reported-NPL bar + colour band + spread clause)"
    ax = d.get("autox")
    if not isinstance(ax, dict):
        return "missing 'autox' MEASURED self-anchor block (the distinct own-tape row)"
    if not (isinstance(ax.get("name"), str) and ax["name"].strip()):
        return "autox anchor missing 'name' (the MEASURED own-book row label)"
    if not isinstance(ax.get("npl_live_os_pct"), (int, float)):
        return "autox anchor missing/non-numeric 'npl_live_os_pct' (the measured NPL-live bar + readout)"
    if not isinstance(ax.get("npl_90plus_os_pct"), (int, float)):
        return "autox anchor missing/non-numeric 'npl_90plus_os_pct' (the strict-90+ readout figure)"
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


def _shape_pico_competitors(d):
    # The PROVINCE-grain sibling of pico_district (obj #2): "where do sub-scale
    # rivals most outnumber our own footprint?" app.js live-fetches it
    # (loadPicoCompetitors -> PICOCOMP) and drawPicoCompetitors renders the
    # #acq "sub-scale rivals per province vs our footprint" leaderboard off
    # PICOCOMP.provinces, each row read for .outnumber (sort key + the pressure
    # column), .pico_total, .autox_branches and .th (the row name). Both counts
    # are MEASURED tallies (FPO PICO licence registry vs the AutoX branch book).
    # pico_district (the district grain) is already probed; this closes the same
    # "a truncated deploy silently blanks the Competition surface with no phone
    # alert" blind spot for the province grain it renders alongside. The render
    # empties gracefully to a "not yet computed" note on an absent/empty file,
    # so a probe is exactly how a broken deploy would otherwise stay invisible.
    # Robust to registry growth (asserts render shape, not exact counts).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    provs = d.get("provinces")
    if not isinstance(provs, list) or not provs:
        return "missing/empty 'provinces' list (leaderboard render read)"
    r0 = provs[0]
    if not isinstance(r0, dict):
        return "provinces[0] not an object"
    for k in ("outnumber", "pico_total", "autox_branches"):
        if not isinstance(r0.get(k), (int, float)):
            return "provinces[0].%s missing/not numeric (leaderboard render read)" % k
    if not r0.get("th"):
        return "provinces[0].th missing (row name render read)"
    if not isinstance(d.get("meta"), dict):
        return "missing 'meta' object (provenance/momentum block the readout reads)"
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


def _shape_province_stress_index(d):
    # The combined province STRUCTURAL-STRESS index (province_stress_index.json,
    # obj #1, MEASURED legs) — the pure borrower-leverage read (household DTI +
    # unemployment, both NSO measured; the two percentiles + composite_stress an
    # ESTIMATED equal-weighted blend). It renders on the exec FRONT DOOR (the #home
    # "Structurally riskiest · household DTI + unemployment" card reads PSTRESS_LIST[0]
    # — .province/.region/.debt_to_income/.unemployment_rate/.composite_stress) AND
    # drives a #map lens, and it is the parent whose composite the already-probed
    # province_pressure join consumes. loadProvinceStress builds PSTRESS_LIST by
    # filtering .provinces on `composite_stress != null` and GATES every render on that
    # list being non-empty — so a truncated/404 CDN deploy that guts the file silently
    # drops the front-door structural-leverage card and hides the map lens with NO phone
    # alert, the same "broken demo" blind spot the household_risk / province_pressure /
    # obj-#1 flow-card probes closed for the sibling reads. It CANNOT self-heal (the DTI
    # + unemployment legs come from NSO SES/LFS folded by a pipeline build, not a CI
    # pull). The builder can also write an HONEST meta.absent state that the app treats
    # as a valid empty shape (PSTRESS stays empty, lens hides, no error); mirror that
    # here (absent -> OK, not an alert) so the probe fires only on a real truncation.
    # Asserts render shape (the composite-bearing rows the PSTRESS_LIST gate is built
    # from + the province name each row renders), not values — robust to a future
    # SES/LFS vintage shifting the ratios.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    meta = d.get("meta")
    if isinstance(meta, dict) and meta.get("absent"):
        return None  # builder's honest source-absent guard — a valid empty shape, not a truncation
    provs = d.get("provinces")
    if not isinstance(provs, list) or len(provs) < 70:
        return "missing/short 'provinces' list (expected ~77)"
    stress_rows = [p for p in provs if isinstance(p, dict) and p.get("composite_stress") is not None]
    if not stress_rows:
        return "no province carries a numeric 'composite_stress' (the PSTRESS_LIST render gate)"
    p0 = stress_rows[0]
    if not (isinstance(p0.get("province"), str) and p0["province"].strip()):
        return "first stress-bearing province missing 'province' name (PSTRESS map key + card label)"
    if not isinstance(p0.get("composite_stress"), (int, float)):
        return "first stress-bearing province missing numeric 'composite_stress' (#home card + lens read)"
    return None


def _shape_segment_exposure(d):
    # The Exposure tab's LEAD read (obj #1 portfolio concentration): renderConcentration
    # + renderExpoVerdict build the whole board ONLY from segment_exposure.json. The tab
    # opens with a colored LEAD-WITH-THE-VERDICT card (the most-concentrated region — its
    # .region/.hhi/.dominant_segment/.n_branches) and a "Portfolio concentration by region"
    # panel that maps EVERY .regions row (.region + .n_branches + .dominant_segment +
    # .segment_mix{agri,merchant,collateral} + .hhi), then a national HHI legend line
    # (.national.hhi/.dominant_segment). renderConcentration GATES the whole board on a
    # non-empty .regions array — if the file 404s or truncates, host.innerHTML='' and the
    # verdict card hides, silently blanking the top of the Exposure tab with NO phone alert.
    # It CANNOT self-heal: the mix/HHI are derived from the ESTIMATED segment proxy scores
    # off the master by build_segment_exposure.py — a pipeline rebuild, not a CI pull — so a
    # bad CDN deploy stays broken until someone notices. The last unprobed obj-#1 read on the
    # Exposure surface; closes the same "broken demo" blind spot the province_risk /
    # branch_risk / tape_real probes closed. Mirror the render's reads; validate EVERY region
    # row (a partial truncation must not pass a first-row-only check). Robust to a future
    # region-count change (asserts >=1, not ==5) and to the estimated scores shifting.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    regions = d.get("regions")
    if not isinstance(regions, list) or not regions:
        return "missing/empty 'regions' list (renderConcentration gates the whole board on it)"
    for r in regions:
        if not isinstance(r, dict):
            return "a 'regions' row is not an object"
        if not (isinstance(r.get("region"), str) and r["region"].strip()):
            return "a 'regions' row missing 'region' name (the row/verdict label)"
        if not isinstance(r.get("hhi"), (int, float)) or isinstance(r.get("hhi"), bool):
            return "region '%s' missing numeric 'hhi' (the concentration bar/verdict)" % r.get("region")
        if not (isinstance(r.get("dominant_segment"), str) and r["dominant_segment"].strip()):
            return "region '%s' missing 'dominant_segment' (the dominant-segment read)" % r.get("region")
        mix = r.get("segment_mix")
        if not isinstance(mix, dict) or not all(isinstance(mix.get(k), (int, float)) for k in ("agri", "merchant", "collateral")):
            return "region '%s' missing 'segment_mix' agri/merchant/collateral shares (the stacked mix bar)" % r.get("region")
        if not isinstance(r.get("n_branches"), (int, float)) or isinstance(r.get("n_branches"), bool):
            return "region '%s' missing numeric 'n_branches' (rendered in the row + verdict)" % r.get("region")
    nat = d.get("national")
    if not isinstance(nat, dict):
        return "missing 'national' object (the national-HHI legend line)"
    if not isinstance(nat.get("hhi"), (int, float)) or isinstance(nat.get("hhi"), bool):
        return "national.hhi missing/non-numeric (the 'national HHI …' legend read)"
    if not (isinstance(nat.get("dominant_segment"), str) and nat["dominant_segment"].strip()):
        return "national.dominant_segment missing (the 'dominant …' legend read)"
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


def _shape_collateral_outlook(d):
    # The Overview (#overview) collateral board's national recovery-value read
    # AND the command-center collateral clause (obj #1). renderCollatOutlook +
    # the command-center read both key off `COLLO.national`: the MEASURED used-
    # car/pickup resale card gates on `national.used_veh_yoy_blended != null`
    # (reading used_veh_yoy_car/pickup/price_period), and the "recovery outlook —
    # firming vs softening" card + the command-center row both gate on
    # `national.exposure_weighted_outlook != null` (reading n_firming/n_provinces/
    # most_at_risk_province). It is a composite of MEASURED gold + MEASURED BoT
    # UVPI used-vehicle prices + a structural moto proxy, and it live-degrades
    # SILENTLY — absent/truncated COLLO just falls back to an editorial card with
    # no phone alert, the same "broken demo" blind spot the collateral_book /
    # macro_book / farm_book obj-#1 probes closed for their Overview siblings, and
    # it was the sibling the last audit's own "next probe targets" note flagged
    # alongside macro_sensitivity. Asserts the two national gate keys + render
    # reads and the 77-province backbone, not values — robust to a future BoT
    # UVPI / Pink Sheet vintage moving the numbers.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    nat = d.get("national")
    if not isinstance(nat, dict):
        return "missing 'national' object (renderCollatOutlook gate)"
    for k in ("used_veh_yoy_blended", "exposure_weighted_outlook", "n_firming", "n_provinces"):
        if not isinstance(nat.get(k), (int, float)):
            return "national.%s missing/non-numeric (collateral-outlook card gate/render read)" % k
    if not (isinstance(nat.get("most_at_risk_province"), str) and nat["most_at_risk_province"].strip()):
        return "national.most_at_risk_province missing/blank (recovery-outlook card render read)"
    provs = d.get("provinces")
    if not isinstance(provs, list) or not provs:
        return "missing/empty 'provinces' list (per-province outlook backbone)"
    return None


def _shape_collateral_census(d):
    # The Overview (#overview) collateral section's MEASURED book-appraisal-vs-market-
    # recovery card (obj #1) — renderCollatBookCheck reads `j.book_check`, filters to
    # priced pools (`eval_vs_auction` set, `market_auction` set, n_accounts>=200),
    # sorts by the book-to-auction gap, and renders per-pool `collateral_class` /
    # `age_band` / `n_accounts` / `eval_avg` (our book) / `market_auction` (MEASURED) /
    # `eval_vs_auction` (the gap) / `dpd30p_pct` (delinquency). It is MEASURED auction/
    # retail listings x MEASURED eval_avg from the real loan tape, and it live-degrades
    # SILENTLY — the render gate hides the whole block when `book_check` is absent/empty
    # or no pool survives the priced-pool filter, so a truncated/404 CDN deploy would
    # blank this newly-wired front-door read with NO phone alert, the same "broken demo"
    # blind spot the collateral_book / collateral_outlook obj-#1 probes closed for their
    # Overview siblings. This layer folds off owner-side inputs (the real loan tape +
    # a Thai-IP price census) with no CI cron, so the probe is the only deploy safeguard.
    # Asserts the render gate + a well-formed priced-pool row, shape not values — robust
    # to a future auction/tape vintage moving the prices.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    bc = d.get("book_check")
    if not isinstance(bc, list) or not bc:
        return "missing/empty 'book_check' list (renderCollatBookCheck gate)"
    priced = [r for r in bc if isinstance(r, dict)
              and isinstance(r.get("eval_vs_auction"), (int, float)) and not isinstance(r.get("eval_vs_auction"), bool)
              and isinstance(r.get("market_auction"), (int, float)) and not isinstance(r.get("market_auction"), bool)
              and isinstance(r.get("n_accounts"), (int, float)) and not isinstance(r.get("n_accounts"), bool)
              and r.get("n_accounts", 0) >= 200]
    if not priced:
        return "no priced pool survives the renderCollatBookCheck filter (eval_vs_auction+market_auction+n_accounts>=200)"
    r = priced[0]
    for k in ("collateral_class", "age_band"):
        if not (isinstance(r.get(k), str) and r[k].strip()):
            return "priced pool missing/blank '%s' (table render read)" % k
    if not isinstance(r.get("eval_avg"), (int, float)) or isinstance(r.get("eval_avg"), bool):
        return "priced pool 'eval_avg' missing/non-numeric (our-book column render read)"
    return None


def _shape_macro_sensitivity(d):
    # The per-branch "What moves this branch" popup read (obj #1) — msensRec picks
    # MSENS[idxOf(branch)] from `j.branches`, so the list MUST stay index-aligned
    # to branches.json (2015), and msensPhrase renders each driver against
    # `meta.drivers[key]` (reading .label + .yoy_pct). It is an ESTIMATED PROXY
    # over MEASURED inputs (Pink Sheet price YoY x OAE crop shares / rainfall) and
    # is fully null-guarded — absent/truncated file just omits the branch-drill
    # driver line with no phone alert, the same "broken demo" blind spot the
    # obj-#1 book probes closed for their siblings, and the read the last audit's
    # own "next probe targets" note flagged alongside collateral_outlook. Asserts
    # the index-aligned branches list + a well-formed driver tuple + the
    # meta.drivers phrase-render table + the province watchlist, not values —
    # robust to a future price vintage reshuffling which lever leads.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    branches = d.get("branches")
    if not isinstance(branches, list):
        return "missing 'branches' list (MSENS index-aligned branch drill read)"
    if len(branches) < 2000:
        return "branches has %d entries, expected ~2015 (index-aligned to branches.json)" % len(branches)
    # entries may be empty (branch with no dominant driver); a non-empty one must
    # be a [key, score, dir, ctx] tuple of >=4 (msensPhrase reads t[0]/t[2]/t[3]).
    for rec in branches:
        if not isinstance(rec, list):
            return "a branch entry is not a list (msensRec expects an array of driver tuples)"
        if rec:
            t0 = rec[0]
            if not isinstance(t0, list) or len(t0) < 4:
                return "a driver tuple is not a >=4-element [key,score,dir,ctx] (msensPhrase render read)"
            break
    meta = d.get("meta")
    if not isinstance(meta, dict):
        return "missing 'meta' object (msensPhrase driver-label lookup)"
    drivers = meta.get("drivers")
    if not isinstance(drivers, dict) or not drivers:
        return "missing/empty 'meta.drivers' (msensPhrase label/yoy_pct render read)"
    dv0 = next(iter(drivers.values()))
    if not isinstance(dv0, dict) or not (isinstance(dv0.get("label"), str) and dv0["label"].strip()):
        return "a meta.drivers entry missing 'label' (msensPhrase render read)"
    provs = d.get("provinces")
    if not isinstance(provs, list) or not provs:
        return "missing/empty 'provinces' list (Overview province macro watchlist)"
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


def _shape_vehicle_models(d):
    # The Macro tab's nameplate wave (#275/#276, obj #1 collateral context) — the
    # newest surfaced data layer and the last one from that wave with no deploy
    # probe. It is load-bearing on TWO render paths, both MEASURED (DLT registry
    # at nameplate grain): (1) the "which models, and which are growing" nameplate
    # panel (`cb-nameplates`) GATES on `V.plates_last12` (else display='none'),
    # then rowsOf('pickup')/rowsOf('ppv') render each group's `.top[]` rows
    # (plate/units/share_pct/yoy_pct); (2) the collateral pickup-definition verdict
    # (renderYearTable) takes this layer as the AUTHORITATIVE pickup count on
    # AutoX's own nameplate rule, falling back to the registrar's รย.3 class only
    # when it is absent. The client loader itself sets VMODELS=null unless
    # `Array.isArray(v.annual)`, so a truncated/gutted CDN deploy silently reverts
    # both surfaces to their fallback with no phone alert — the same "broken demo"
    # blind spot the collateral_book / macro_book / deltas obj-#1 probes closed for
    # their siblings. Asserts the render contract both paths read — the `annual`
    # array gate + the pickup/ppv nameplate boards — as SHAPE not values, robust to
    # a future DLT-vintage refresh moving the registration counts.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    annual = d.get("annual")
    if not isinstance(annual, list) or not annual:
        return "missing/empty 'annual' array (client VMODELS gate: Array.isArray(v.annual))"
    if not isinstance(annual[0], dict):
        return "first 'annual' row is not an object (year-table reconciliation render read)"
    pl = d.get("plates_last12")
    if not isinstance(pl, dict) or not pl:
        return "missing/empty 'plates_last12' object (nameplate-panel display gate)"
    for grp in ("pickup", "ppv"):
        g = pl.get(grp)
        if not isinstance(g, dict):
            return "plates_last12.%s missing (nameplate-board group render read)" % grp
        top = g.get("top")
        if not isinstance(top, list) or not top:
            return "plates_last12.%s.top missing/empty (nameplate-board row render read)" % grp
        r0 = top[0]
        if not isinstance(r0, dict):
            return "plates_last12.%s.top[0] is not an object" % grp
        if not (isinstance(r0.get("plate"), str) and r0["plate"].strip()):
            return "plates_last12.%s.top[0] missing 'plate' (nameplate-row label render read)" % grp
        for k in ("units", "share_pct"):
            if not isinstance(r0.get(k), (int, float)) or isinstance(r0.get(k), bool):
                return "plates_last12.%s.top[0].%s missing/non-numeric (nameplate-row cell render read)" % (grp, k)
    return None


def _shape_rival_pressure(d):
    # The per-branch rival-pressure layer (rival_pressure.json, obj #2, MEASURED
    # geometry over the merged competitor census — pipeline/build_rival_pressure.py).
    # It is load-bearing on TWO render paths and was the last surfaced obj-#2
    # competitive read still with no deploy probe: (1) the Risk-trend (#trend) "Most
    # besieged branches" board — drawSiegeTable renders RIVP.besieged.slice(0,10)
    # (the branches with >=3 rivals within 2 km) and, when it is missing/empty, drops
    # the whole board to a "Rival pressure not yet computed." placeholder; (2) the
    # per-branch popup line (rivalPressureLineHTML reads RIVP.branches[i], INDEX-
    # ALIGNED to branches.json — nearest-rival km per brand in .d aligned to .brands,
    # plus the 2 km / 5 km counts n2/n5). The client loader itself sets RIVP=null
    # unless BOTH .branches and .brands are arrays, so a truncated/gutted CDN deploy
    # silently reverts both surfaces to their fallback with NO phone alert — the same
    # "broken demo" blind spot the rival_density / rival_threat / rival_threat_region
    # probes closed for the sibling obj-#2 competitive reads. Asserts the render
    # contract (the client .branches/.brands gate + the 2015-branch index-aligned
    # popup array + the .besieged board rows) as SHAPE not values, robust to a future
    # competitor-census refresh moving the counts.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    brands = d.get("brands")
    if not isinstance(brands, list) or not brands:
        return "missing/empty 'brands' array (client RIVP gate: Array.isArray(j.brands))"
    recs = d.get("branches")
    if not isinstance(recs, list) or not recs:
        return "missing/empty 'branches' array (client RIVP gate + popup RIVP.branches[i] read)"
    if len(recs) != 2015:
        return "expected 2015 branch records (index-aligned to branches.json), got %d" % len(recs)
    r0 = recs[0]
    if not isinstance(r0, dict):
        return "first 'branches' record is not an object"
    for k in ("n2", "n5"):
        if not isinstance(r0.get(k), (int, float)) or isinstance(r0.get(k), bool):
            return "first branch record missing numeric '%s' (popup 2/5 km-count render read)" % k
    if not isinstance(r0.get("d"), list):
        return "first branch record missing 'd' list (per-brand nearest-rival km, aligned to .brands)"
    bes = d.get("besieged")
    if not isinstance(bes, list) or not bes:
        return "missing/empty 'besieged' list (#trend Most-besieged board render read)"
    b0 = bes[0]
    if not isinstance(b0, dict):
        return "first 'besieged' row is not an object"
    if not isinstance(b0.get("i"), int) or isinstance(b0.get("i"), bool):
        return "first besieged row missing integer 'i' (branch index the board row keys on)"
    if not (isinstance(b0.get("name"), str) and b0["name"].strip()):
        return "first besieged row missing 'name' (board branch-label render read)"
    if not isinstance(b0.get("n2"), (int, float)) or isinstance(b0.get("n2"), bool):
        return "first besieged row missing numeric 'n2' (board rivals-<=2km column render read)"
    return None


def _shape_branch_cropland(d):
    # The per-branch crop-AREA layer (branch_cropland.json, obj #1 — SPAM-2010
    # spatial pattern rescaled per province to the DOAE farmer-registry MEASURED
    # 2025 planted area, pipeline/build_branch_cropland.py). It is the only
    # per-branch absolute crop-hectares read the app carries, index-aligned to
    # branches.json, and it renders the MEASURED-CORRECTED "crop area within 10km"
    # block in every branch popup (croplandPopupHTML reads croplandRec(d)=CROPLAND[i]
    # -> .crop_ha gate + the per-crop .ha[] magnitudes, labelled off croplandMeta.crops).
    # The client loader sets CROPLAND=null on any fetch/parse failure and the popup
    # helper returns '' whenever the record is missing, so a truncated/404 CDN deploy
    # silently drops the crop-area block from every popup with NO phone alert — the
    # same "broken demo" blind spot the flood_hazard / farm_book / branch_labor obj-#1
    # probes closed for their siblings, and this layer (backlog item #2's shipped
    # integration) was the last surfaced per-branch obj-#1 read with no deploy probe.
    # Asserts the render contract (the meta.crops label list + the 2015-branch
    # index-aligned array + the .crop_ha gate and .ha[] magnitudes the popup reads)
    # as SHAPE not values, robust to a future DOAE-vintage / SPAM refresh moving areas.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    crops = d.get("meta", {}).get("crops") if isinstance(d.get("meta"), dict) else None
    if not isinstance(crops, list) or not crops:
        return "missing/empty meta.crops label list (popup per-crop row labels)"
    recs = d.get("branches")
    if not isinstance(recs, list) or not recs:
        return "missing/empty 'branches' array (client CROPLAND gate + popup CROPLAND[i] read)"
    if len(recs) != 2015:
        return "expected 2015 branch records (index-aligned to branches.json), got %d" % len(recs)
    r0 = recs[0]
    if not isinstance(r0, dict):
        return "first 'branches' record is not an object"
    if not isinstance(r0.get("ha"), list):
        return "first branch record missing 'ha' list (per-crop hectares, popup .ha[j] render read)"
    if not isinstance(r0.get("crop_ha"), (int, float)) or isinstance(r0.get("crop_ha"), bool):
        return "first branch record missing numeric 'crop_ha' (popup crop-area gate/total render read)"
    return None


def _shape_branch_pico(d):
    # The per-branch LICENSED-PICO rival count (branch_pico.json, obj #2 — the FPO
    # พิโกไฟแนนซ์ registry counted in each branch's OWN district, a DISTINCT small-ticket
    # rival class the big-4 census (rival_pressure.json) is blind to; pipeline/
    # build_branch_pico.py). It is index-aligned to branches.json and renders the
    # MEASURED "PICO rivals in อำเภอ" block in every branch popup (picoBrHTML reads
    # picoBrRec(d)=PICOBR[i] and GATES the line on `typeof e.pico!=='number'`, then
    # renders e.pico + the e.head/e.branch/e.recent split). The client loader sets
    # PICOBR=null on any fetch/parse failure, so a truncated/404 CDN deploy silently
    # drops the PICO competitive-pressure block from every popup with NO phone alert —
    # the same "broken demo" blind spot the branch_cropland / tape_geo_occ / flood_hazard
    # probes closed for their siblings. Its DISTRICT-grain twins (pico_district,
    # pico_competitors) are already probed; this per-branch layer (backlog item #1's
    # shipped per-branch integration, obj #2's #1 competitive gap) was the unprobed one.
    # Asserts the render contract (the 2015-branch index-aligned array + the numeric
    # .pico gate and the .head/.branch/.recent split the popup reads) as SHAPE not
    # values, robust to a future FPO registry vintage moving the counts.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    recs = d.get("branches")
    if not isinstance(recs, list) or not recs:
        return "missing/empty 'branches' array (client PICOBR gate + popup PICOBR[i] read)"
    if len(recs) != 2015:
        return "expected 2015 branch records (index-aligned to branches.json), got %d" % len(recs)
    r0 = recs[0]
    if not isinstance(r0, dict):
        return "first 'branches' record is not an object"
    for k in ("pico", "head", "branch", "recent"):
        v = r0.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return "first branch record missing numeric '%s' (popup .%s render read)" % (k, k)
    return None


def _shape_branch_occupations(d):
    # The per-branch MEASURED establishment-by-occupation rollup (branch_occupations.json,
    # pipeline/build_occupations.py — Overture POI points within 10km bucketed into 14
    # occupation classes). It is load-bearing on TWO surfaces: the #map "estab" lens
    # (estabCount(d)=OCCDATA.branches[i].t, so the array MUST stay index-aligned to
    # branches.json) AND the branch popup's occupation-mix block (reads .buckets labels +
    # per-branch .o[] counts). The client loader sets OCCDATA=null on any fetch/parse
    # failure and every reader returns 0/'' when the record is missing, so a truncated/404
    # CDN deploy silently zeroes the estab lens and drops the popup block with NO phone
    # alert — the same "broken demo" blind spot the branch_cropland / branch_pico probes
    # closed for their per-branch siblings. Asserts the render contract (the .buckets label
    # list + the 2015-branch index-aligned array + the numeric .t lens read and .o[] counts
    # the popup reads) as SHAPE not values, robust to a future Overture-vintage refresh.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    buckets = d.get("buckets")
    if not isinstance(buckets, list) or not buckets:
        return "missing/empty 'buckets' label list (popup occupation-row labels + map lens)"
    recs = d.get("branches")
    if not isinstance(recs, list) or not recs:
        return "missing/empty 'branches' array (client OCCDATA gate + estabCount OCCDATA[i] read)"
    if len(recs) != 2015:
        return "expected 2015 branch records (index-aligned to branches.json), got %d" % len(recs)
    r0 = recs[0]
    if not isinstance(r0, dict):
        return "first 'branches' record is not an object"
    if not isinstance(r0.get("o"), list):
        return "first branch record missing 'o' list (per-bucket establishment counts, popup .o[j] read)"
    if not isinstance(r0.get("t"), (int, float)) or isinstance(r0.get("t"), bool):
        return "first branch record missing numeric 't' (total ≤10km — the #map estab lens val())"
    return None


def _shape_branch_workforce(d):
    # The per-branch ESTIMATED WORKFORCE-mix layer (branch_workforce.json,
    # pipeline/build_branch_workforce.py — people-by-occupation within 10km, each bucket
    # from the source that measures it: farmers SPAM×OAE anchored to NSO, factory DIW, the
    # storefront classes Overture×headcount). Unlike branch_occupations (which counts
    # BUSINESSES and buries farmers), this is the lead-by-occupation "who WORKS here" read.
    # It renders the "Workforce mix" block in every branch popup (workforcePopupHTML reads
    # WFDATA.branches[i], GATES on e.t>0, then the .buckets labels + per-branch .w[]/.mix[]
    # bars). The client loader sets WFDATA=null on any fetch/parse failure and the helper
    # returns '' when the record is missing, so a truncated/404 CDN deploy silently drops
    # the block from every popup with NO phone alert. Asserts the render contract (the
    # .buckets label list + the 2015-branch index-aligned array + the numeric .t gate and
    # the .w[]/.mix[] bars) as SHAPE not values, robust to a future vintage refresh.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    buckets = d.get("buckets")
    if not isinstance(buckets, list) or not buckets:
        return "missing/empty 'buckets' label list (popup workforce-row labels)"
    recs = d.get("branches")
    if not isinstance(recs, list) or not recs:
        return "missing/empty 'branches' array (client WFDATA gate + popup WFDATA[i] read)"
    if len(recs) != 2015:
        return "expected 2015 branch records (index-aligned to branches.json), got %d" % len(recs)
    r0 = recs[0]
    if not isinstance(r0, dict):
        return "first 'branches' record is not an object"
    for k in ("w", "mix"):
        if not isinstance(r0.get(k), list):
            return "first branch record missing '%s' list (per-bucket people/pct, popup bar render read)" % k
    if not isinstance(r0.get("t"), (int, float)) or isinstance(r0.get("t"), bool):
        return "first branch record missing numeric 't' (total workers ≤10km — popup render gate)"
    return None


def _shape_branch_agri(d):
    # The per-branch AGRICULTURE profile (branch_agri.json, obj #1 —
    # pipeline/build_branch_agri.py): crop exposure (SPAM) + REAL OAE farm-gate price
    # stress + per-branch drought + est farm income. It renders the "Agriculture — crop
    # exposure & stress" block in every branch popup (agriPopupHTML reads AGRIDATA.branches[i],
    # GATES on e.crop_ha>0, then the meta.crops labels + per-crop .ha[]/.sh[] bars +
    # .price_yoy / .agri_pressure / .rain_anom / .income_est lines). It is DISTINCT from
    # branch_cropland (absolute AREA, already probed): this carries the price/drought/income
    # STRESS reads. The client loader sets AGRIDATA=null on any fetch/parse failure and the
    # helper returns '' when the record is missing, so a truncated/404 CDN deploy silently
    # drops the obj-#1 agri-stress block from every popup with NO phone alert. Asserts the
    # render contract (meta.crops label list + the 2015-branch index-aligned array + the
    # .crop_ha gate and .ha[]/.sh[] bars) as SHAPE not values, robust to a future
    # OAE-farm-gate / SPAM vintage moving the numbers.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    crops = d.get("meta", {}).get("crops") if isinstance(d.get("meta"), dict) else None
    if not isinstance(crops, list) or not crops:
        return "missing/empty meta.crops label list (popup per-crop row labels)"
    recs = d.get("branches")
    if not isinstance(recs, list) or not recs:
        return "missing/empty 'branches' array (client AGRIDATA gate + popup AGRIDATA[i] read)"
    if len(recs) != 2015:
        return "expected 2015 branch records (index-aligned to branches.json), got %d" % len(recs)
    r0 = recs[0]
    if not isinstance(r0, dict):
        return "first 'branches' record is not an object"
    for k in ("ha", "sh"):
        if not isinstance(r0.get(k), list):
            return "first branch record missing '%s' list (per-crop hectares/share, popup bar render read)" % k
    if not isinstance(r0.get("crop_ha"), (int, float)) or isinstance(r0.get("crop_ha"), bool):
        return "first branch record missing numeric 'crop_ha' (popup crop-area gate render read)"
    return None


def _shape_macro_exposure(d):
    # The per-branch MACRO-EXPOSURE profile (macro_exposure.json, obj #1 —
    # pipeline/build_macro_exposure.py: MEASURED occupation shares × ESTIMATED sensitivity
    # weights × MEASURED macro signals → a share-diluted per-factor exposure). It is
    # load-bearing on TWO surfaces: the #map "macx" macro-headwind lens (macxHeadwindVal /
    # macxDomTally read macxVec[i] AND MACX[i] TOGETHER — so BOTH the .vector and .branches
    # arrays must stay index-aligned to branches.json at 2015, or the lens paints the wrong
    # branches) AND the branch popup (macxRec(d)=MACX[i] → .t3[] dominant-factor chips,
    # labelled off meta.factors/meta.factor_keys). The client loader sets MACX/macxVec=null
    # on any fetch/parse failure and every reader returns 0/null when a record is missing,
    # so a truncated/404 CDN deploy silently zeroes the macx lens and drops the popup chips
    # with NO phone alert. Asserts the render contract (meta.factors + meta.factor_keys label
    # tables + the 2015-branch index-aligned .branches with a .t3 tuple list + the 2015-entry
    # index-aligned .vector the lens reads) as SHAPE not values, robust to a future vintage.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    meta = d.get("meta")
    if not isinstance(meta, dict):
        return "missing 'meta' object (factor label tables)"
    if not isinstance(meta.get("factors"), list) or not meta.get("factors"):
        return "missing/empty meta.factors (popup chip factor labels — macxFactor lookup)"
    if not isinstance(meta.get("factor_keys"), list) or not meta.get("factor_keys"):
        return "missing/empty meta.factor_keys (map-lens macxDomTally dominant-factor key list)"
    recs = d.get("branches")
    if not isinstance(recs, list) or not recs:
        return "missing/empty 'branches' array (client MACX gate + popup/lens MACX[i] read)"
    if len(recs) != 2015:
        return "expected 2015 branch records (index-aligned to branches.json), got %d" % len(recs)
    r0 = recs[0]
    if not isinstance(r0, dict) or not isinstance(r0.get("t3"), list):
        return "first 'branches' record missing 't3' tuple list (popup dominant-factor chips)"
    vec = d.get("vector")
    if not isinstance(vec, list) or not vec:
        return "missing/empty 'vector' array (the #map macx lens macxVec[i] read)"
    if len(vec) != 2015:
        return "expected 2015 vector entries (index-aligned to branches.json + MACX), got %d" % len(vec)
    if not isinstance(vec[0], list):
        return "first 'vector' entry is not a [dominant-idx, score] list (macx lens read)"
    return None


def _shape_vehicle_mix(d):
    # The collateral board's fleet-mix panel (`cb-mix`, obj #1 — vehicle titles are
    # ~75% of the book, so the stock-vs-new-registration gap by DLT class is a direct
    # read on the collateral pool AutoX lends against and recovers into). MEASURED
    # throughout (DLT gdcatalog dataset_1_1_04 stock + red-plate new registrations).
    # The client (`tmliFetch('vehicle_mix')`) GATES the whole panel on
    # `!NAT.stock || !NAT.new || !TY.length` and otherwise `display='none'` with NO
    # phone alert, so a truncated/404 CDN deploy silently drops the fleet-mix read to
    # nothing — the same "broken demo" blind spot the vehicle_models / collateral_book
    # probes closed for their siblings. And like them it CANNOT self-heal from CI: the
    # DLT stock file is an annual off-cadence pull, so no daily cron re-publishes it —
    # the probe is the only deploy safeguard. Asserts the render contract the panel
    # reads — the national stock/new maps + the `types` class list — as SHAPE not
    # values, robust to a future DLT-vintage refresh moving the registration counts.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    nat = d.get("national")
    if not isinstance(nat, dict):
        return "missing 'national' object (cb-mix panel display gate: !NAT.stock||!NAT.new)"
    for k in ("stock", "new"):
        m = nat.get(k)
        if not isinstance(m, dict) or not m:
            return "national.%s missing/empty (cb-mix display gate reads NAT.%s)" % (k, k)
        r0 = next(iter(m.values()))
        if not isinstance(r0, dict) or not isinstance(r0.get("share_pct"), (int, float)) or isinstance(r0.get("share_pct"), bool):
            return "national.%s first row missing numeric 'share_pct' (cb-mix share cell render read)" % k
    types = d.get("types")
    if not isinstance(types, list) or not types:
        return "missing/empty 'types' array (cb-mix display gate: !TY.length)"
    t0 = types[0]
    if not isinstance(t0, dict):
        return "types[0] is not an object (cb-mix class-row render read)"
    if not (isinstance(t0.get("id"), str) and t0["id"].strip()):
        return "types[0] missing 'id' (cb-mix class-row keys NAT.stock[t.id])"
    if not (isinstance(t0.get("label"), str) and t0["label"].strip()):
        return "types[0] missing 'label' (cb-mix class-row DLT-label render read)"
    if not isinstance(t0.get("has_stock"), bool):
        return "types[0] missing boolean 'has_stock' (cb-mix stock-bearing vs LTA divider read)"
    return None


def _shape_vehicle_brands(d):
    # The collateral board's new-nameplate panel (`cb-vbrands`, obj #1 — what the
    # country is registering NEW becomes the collateral offered next year; pickup is a
    # two-brand market so pickup residual value is not a diversified exposure). The
    # NATIONAL brand mix is MEASURED (DLT stat_1_1_01); the province split is ESTIMATED
    # and labelled so in the UI. The client (`tmliFetch('vehicle_brands')`) GATES the
    # panel on `!NB.ry3 || !NB.ry1` (NB = national.by_type) and otherwise
    # `display='none'` with NO phone alert, so a truncated/404 deploy silently drops
    # it — and, like its vehicle_mix sibling, it CANNOT self-heal from CI (annual DLT
    # pull, no daily cron), so the probe is the only deploy safeguard. Asserts the gate
    # both render paths read — the ry3/ry1 by_type groups and their brand rows — as
    # SHAPE not values, robust to a future DLT-vintage refresh moving the counts.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    nat = d.get("national")
    if not isinstance(nat, dict):
        return "missing 'national' object (cb-vbrands gate reads national.by_type)"
    by_type = nat.get("by_type")
    if not isinstance(by_type, dict):
        return "missing 'national.by_type' object (cb-vbrands display gate: !NB.ry3||!NB.ry1)"
    for grp in ("ry3", "ry1"):
        g = by_type.get(grp)
        if not isinstance(g, dict):
            return "national.by_type.%s missing (cb-vbrands display gate)" % grp
        brands = g.get("brands")
        if not isinstance(brands, list) or not brands:
            return "national.by_type.%s.brands missing/empty (cb-vbrands brand-row render read)" % grp
        b0 = brands[0]
        if not isinstance(b0, dict):
            return "national.by_type.%s.brands[0] is not an object" % grp
        if not (isinstance(b0.get("brand"), str) and b0["brand"].strip()):
            return "national.by_type.%s.brands[0] missing 'brand' (cb-vbrands row label render read)" % grp
        for k in ("count", "share_pct"):
            if not isinstance(b0.get(k), (int, float)) or isinstance(b0.get(k), bool):
                return "national.by_type.%s.brands[0].%s missing/non-numeric (cb-vbrands cell render read)" % (grp, k)
    if not isinstance(d.get("provinces"), dict):
        return "missing 'provinces' object (cb-vbrands ESTIMATED province-split render read)"
    return None


def _shape_assist_price_radar(d):
    # The proactive-assistance PRICE LENS (assist_price_radar.json, obj #1) — the
    # healthy farm book crossed with MEASURED Thai farm-gate price direction: which
    # provinces hold Current/X-bucket farm accounts riding on a crop whose price is
    # falling, "the slice to call before collections turn". renderAssistPriceLens
    # GATES the whole lens on a non-empty .crops array (else it silently drops to the
    # calm "The price lens needs data/assist_price_radar.json — not built for this
    # vintage" placeholder with NO phone alert). It is MEASURED (real-tape counts x
    # planted-area shares x NABC farm-gate YoY) but does NOT self-heal from a broken
    # deploy: build_assist_radar_price.py has no cron, so a truncated/404 CDN copy
    # has no CI job to restore it. Per crop it renders .crop + .yoy/.direction +
    # .n_current_x (the "healthy accounts riding on it" column) + .n_farm_accounts;
    # per province .th + .tripped + .n_current_x; the readout reads meta.trigger
    # (.dominant_share/.rule) and the .tripped list. Asserts render shape (the crops
    # gate + a crop label + a numeric exposed-account column + the provinces list +
    # the trigger block + the tripped list), not values — robust to a future
    # tape / farm-gate vintage refresh moving the counts, and it stays green in the
    # legitimate "nothing tripped" state (tripped may be an empty list).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    crops = d.get("crops")
    if not isinstance(crops, list) or not crops:
        return "missing/empty 'crops' list (renderAssistPriceLens gates the lens on it)"
    c0 = crops[0]
    if not isinstance(c0, dict):
        return "first crops row is not an object"
    if not (isinstance(c0.get("crop"), str) and c0["crop"].strip()):
        return "first crops row missing 'crop' (the crop-row label render)"
    if not any(isinstance(c, dict) and isinstance(c.get("n_current_x"), (int, float))
               and not isinstance(c.get("n_current_x"), bool) for c in crops):
        return "no crop carries a numeric 'n_current_x' (the healthy-accounts-riding-on-it column)"
    provs = d.get("provinces")
    if not isinstance(provs, list) or not provs:
        return "missing/empty 'provinces' list (the by-province call table + the lead read)"
    if not (isinstance(provs[0], dict) and isinstance(provs[0].get("th"), str) and provs[0]["th"].strip()):
        return "first provinces row missing 'th' (the province-row label render)"
    trig = (d.get("meta") or {}).get("trigger")
    if not isinstance(trig, dict):
        return "missing meta.trigger block (the readout reads trigger.dominant_share/.rule)"
    if not isinstance(d.get("tripped"), list):
        return "missing 'tripped' list (the lead branches on tripped.length; empty is a valid no-distress state)"
    return None


def _shape_assist_branch_radar(d):
    # The proactive-assistance BRANCH DRILL (assist_branch_radar.json, obj #1) — the
    # newest surfaced obj-#1 read (the falling-crop radar taken from province down to
    # BRANCH: "a call list, not a map"). renderAssistBranchLens GATES the whole drill
    # on a non-empty .provinces array (else it silently drops to the calm "The branch
    # drill needs data/assist_branch_radar.json — not built for this vintage"
    # placeholder with NO phone alert), then flattens every province's .branches[] into
    # the ranked call list. Like its price-lens parent it is MEASURED-where-shown /
    # ESTIMATED-ranking but does NOT self-heal from a broken deploy (no cron for
    # build_assist_radar_branch.py), so a truncated/404 CDN copy has no CI job to
    # restore it. Per branch it renders .name + .exposed_crop_ha (the ranking column,
    # nullable) + .exposure_share + .n_farm (MEASURED, nullable under the >=30 floor) +
    # .early_pct; the lead reads meta.n_branches_ranked + meta.n_provinces. Asserts
    # render shape (the provinces gate + a province label + >=1 branch row carrying a
    # name + the two numeric meta counts the lead renders), not values — robust to a
    # future tape / crop-area vintage refresh, and it does NOT require exposed_crop_ha /
    # n_farm to be numeric (both are legitimately null when a cell falls under the
    # tape's >=30 floor).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    provs = d.get("provinces")
    if not isinstance(provs, list) or not provs:
        return "missing/empty 'provinces' list (renderAssistBranchLens gates the drill on it)"
    p0 = provs[0]
    if not isinstance(p0, dict):
        return "first provinces row is not an object"
    if not (isinstance(p0.get("th"), str) and p0["th"].strip()):
        return "first provinces row missing 'th' (the province-column label render)"
    branch = None
    for p in provs:
        if isinstance(p, dict) and isinstance(p.get("branches"), list) and p["branches"]:
            branch = p["branches"][0]
            break
    if branch is None:
        return "no province carries a non-empty 'branches' list (the ranked call list would be empty)"
    if not isinstance(branch, dict):
        return "first branches row is not an object"
    if not (isinstance(branch.get("name"), str) and branch["name"].strip()):
        return "first branches row missing 'name' (the branch-row label render)"
    meta = d.get("meta") or {}
    for k in ("n_branches_ranked", "n_provinces"):
        if not isinstance(meta.get(k), (int, float)) or isinstance(meta.get(k), bool):
            return "meta.%s missing/non-numeric (the lead sentence renders it)" % k
    return None


def _shape_rival_book_impact(d):
    # The Competition (#acq) book-cost read (obj #1 + #2, shipped #319) — the one
    # layer that joins MEASURED per-district rival counts to the MEASURED real loan
    # tape and asks "what does the rival field actually cost the book?".
    # renderRivalBookImpact live-fetches it (tmliFetch('rival_book_impact')) and
    # GATES the whole board on `j.within_province` — if the file 404s/truncates it
    # drops to a calm "not built for this vintage" note with NO phone alert. It
    # CANNOT self-heal: the join is a pipeline rebuild off the owner-side tape
    # (build_rival_book_impact.py, no CI cron), so a bad CDN deploy stays broken
    # until someone notices. The within-province table reads .more_contested /
    # .less_contested (each .n_branches/.n_accounts/.rivals_avg/.dpd90p_pct/
    # .early_pct/.avg_balance_thb) and the three .gap_* deltas; validate both sides
    # so a partial truncation cannot pass a one-side check. Asserts render shape,
    # not values — robust to a future tape/rival-density vintage refresh.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    wp = d.get("within_province")
    if not isinstance(wp, dict):
        return "missing 'within_province' object (renderRivalBookImpact gates the whole board on it)"
    for side in ("more_contested", "less_contested"):
        s = wp.get(side)
        if not isinstance(s, dict):
            return "within_province.%s missing/not an object (a table row render read)" % side
        for k in ("n_branches", "n_accounts", "rivals_avg", "dpd90p_pct", "early_pct", "avg_balance_thb"):
            if not isinstance(s.get(k), (int, float)) or isinstance(s.get(k), bool):
                return "within_province.%s.%s missing/non-numeric (the contested-split table render read)" % (side, k)
    for k in ("gap_dpd90p_pp", "gap_early_pp", "gap_avg_balance_thb"):
        if not isinstance(wp.get(k), (int, float)) or isinstance(wp.get(k), bool):
            return "within_province.%s missing/non-numeric (the Gap row render read)" % k
    return None


def _shape_rival_watch(d):
    # The Competition (#acq) change-diff read (obj #2, shipped #319) — the only
    # panel on the tab that answers "and what MOVED since the last pull?" instead of
    # a right-now snapshot. renderRivalWatch live-fetches it (tmliFetch('rival_watch'))
    # into the "What changed since the last pull" panel at the top of the Rival-pulse
    # section, off .promos (n_new/n_disappeared + new[]/disappeared[]) and .ads
    # (n_appeared_brands + appeared[]). The render is deliberately null-safe on every
    # sub-object (it degrades to a "not built yet" note only when the WHOLE file is
    # missing), so the deploy risk it guards is a truncated/gutted file — a 200 that
    # parses but has lost .promos/.ads would silently blank the change panel with no
    # phone alert, and it CANNOT self-heal (build_rival_watch.py diffs off the
    # Thai-IP promo pull, no CI cron). Assert the two load-bearing sub-objects carry
    # their render-read count fields; shape not values, robust to a quiet vintage
    # (n_new / n_appeared_brands legitimately 0).
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    promos = d.get("promos")
    if not isinstance(promos, dict):
        return "missing 'promos' object (the 'Rivals' own sites' change block render read)"
    if not isinstance(promos.get("n_new"), (int, float)) or isinstance(promos.get("n_new"), bool):
        return "promos.n_new missing/non-numeric (the new-promo count render read)"
    if not isinstance(promos.get("n_disappeared"), (int, float)) or isinstance(promos.get("n_disappeared"), bool):
        return "promos.n_disappeared missing/non-numeric (the no-longer-listed count render read)"
    ads = d.get("ads")
    if not isinstance(ads, dict):
        return "missing 'ads' object (the 'Google Ads Transparency' change block render read)"
    if not isinstance(ads.get("n_appeared_brands"), (int, float)) or isinstance(ads.get("n_appeared_brands"), bool):
        return "ads.n_appeared_brands missing/non-numeric (the new-creative brand-count render read)"
    return None


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _shape_debt_source(d):
    # MEASURED NSO household debt inside-vs-outside the formal system (obj #1). The
    # Competition/#acq tab's renderDebtSource GATES the whole informal-debt board on
    # `Array.isArray(j.by_class)`, then reads per-class .cls_en/.total/.informal_pct/
    # .consumption_debt rows and the .national series ([0] + last) for the lead. A
    # truncated/404 CDN deploy that drops or guts it degrades SILENTLY to a "not built
    # for this vintage" note with NO phone alert, and it CANNOT self-heal (NSO SES is a
    # laptop/owner-side fold, no CI cron) — the same "broken demo" blind spot the
    # farm_book / macro_book obj-#1 probes closed for their siblings. Asserts the
    # by_class gate + a real (non-total) class row's render fields + the national
    # series; shape not values, robust to a future SES wave.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    bc = d.get("by_class")
    if not isinstance(bc, list) or not bc:
        return "missing/empty 'by_class' list (the informal-debt board render gate)"
    rows = [r for r in bc if isinstance(r, dict) and r.get("cls") != "รวม"]
    if not rows:
        return "no non-total 'by_class' row (every row is the รวม total)"
    r0 = rows[0]
    if not (isinstance(r0.get("cls_en"), str) and r0["cls_en"].strip()):
        return "first class row missing 'cls_en' label (the household-type render read)"
    if not _num(r0.get("informal_pct")):
        return "first class row missing numeric 'informal_pct' (the share-outside render read)"
    if not _num(r0.get("total")):
        return "first class row missing numeric 'total' (the debt/household render read)"
    nat = d.get("national")
    if not isinstance(nat, list) or not nat:
        return "missing/empty 'national' series (the lead informal-share trend read)"
    if not _num(nat[-1].get("informal_pct")):
        return "national[-1].informal_pct missing/non-numeric (the lead headline read)"
    return None


def _shape_income_impact(d):
    # ESTIMATED first-order income-impact engine (obj #1). renderIncome GATES its whole
    # region table on `Array.isArray(j.regions)`, then reads per-region .key +
    # .income_pressure_pct + .book_mix (+ best_occ/worst_occ/nso_wage_ref). Fully
    # null-guarded -> a truncated CDN deploy that drops or guts it silently blanks the
    # income-impact panel with NO phone alert, and it CANNOT self-heal (a pipeline
    # rebuild off NSO SES + tape, no CI cron) — the same blind spot the crop_stress /
    # farm_book obj-#1 probes closed. Asserts the regions gate + a region row's render
    # fields; shape not values, robust to a future vintage reshuffling the pass-through.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    regs = d.get("regions")
    if not isinstance(regs, list) or not regs:
        return "missing/empty 'regions' list (the income-impact table render gate)"
    r0 = regs[0]
    if not isinstance(r0, dict):
        return "first region row is not an object"
    if not (isinstance(r0.get("key"), str) and r0["key"].strip()):
        return "first region missing 'key' name (the region-row render read)"
    if not _num(r0.get("income_pressure_pct")):
        return "first region missing numeric 'income_pressure_pct' (the book-pressure render read)"
    if not isinstance(r0.get("book_mix"), dict):
        return "first region missing 'book_mix' object (the top-occupations render read)"
    return None


def _shape_credit_anchor(d):
    # MEASURED BoT credit anchor (obj #1) — the real-world scale the estimated branch-
    # risk score is read against, on the Competition/#acq method surface. drawCreditAnchor
    # GATES on `Array.isArray(CREDITANCHOR.metrics)` (non-empty), then reads per-metric
    # .key/.label/.display/.scope/.source/.vintage and looks up by('system_npl') for the
    # headline. Fully null-guarded -> a truncated CDN deploy that drops or empties it
    # silently swaps the measured scale for a "not available" note with NO phone alert,
    # and it CANNOT self-heal (pull_bot_credit.py off BoT FSR text, no CI cron). Asserts
    # the metrics gate + a metric's render fields + the presence of the system_npl
    # headline metric; shape not values, robust to a future BoT-FSR vintage.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    metrics = d.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        return "missing/empty 'metrics' list (the credit-anchor render gate)"
    m0 = metrics[0]
    if not isinstance(m0, dict):
        return "first metric is not an object"
    for f in ("key", "label", "display"):
        if not (isinstance(m0.get(f), str) and m0[f].strip()):
            return "first metric missing '%s' (a metric-card render read)" % f
    if not any(isinstance(m, dict) and m.get("key") == "system_npl" for m in metrics):
        return "no 'system_npl' metric (the answer-first headline read)"
    return None


def _shape_rival_universe(d):
    # The MEASURED/ESTIMATED operator census (obj #2) — every material title-lender,
    # us + rivals + banks + brokers — on the Competition/#acq rival-pulse surface.
    # drawRivalUniverse GATES on `Array.isArray(RIVUNI.operators)` (non-empty), then
    # reads per-operator .tier/.name_th/.name_en/.owner/.model/.footprint(/.app), with
    # the tier=='us' (AutoX) row highlighted. Fully null-guarded -> a truncated CDN
    # deploy that drops or empties it silently swaps the census for a "not available"
    # note with NO phone alert, and it CANNOT self-heal (build_rival_universe.py has no
    # CI cron) — the same blind spot the rival_reputation / rival_threat obj-#2 probes
    # closed. Asserts the operators gate + an operator's render fields + the presence of
    # the tier=='us' AutoX self-row; shape not values, robust to a future roster edit.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    ops = d.get("operators")
    if not isinstance(ops, list) or not ops:
        return "missing/empty 'operators' list (the operator-census render gate)"
    o0 = ops[0]
    if not isinstance(o0, dict):
        return "first operator is not an object"
    if not (isinstance(o0.get("name_th"), str) and o0["name_th"].strip()):
        return "first operator missing 'name_th' (the operator-row render read)"
    if not (isinstance(o0.get("tier"), str) and o0["tier"].strip()):
        return "first operator missing 'tier' (the US/NON-BANK/BANK badge render read)"
    if not any(isinstance(o, dict) and o.get("tier") == "us" for o in ops):
        return "no tier=='us' operator (the AutoX self-row the board highlights)"
    return None


def _shape_farm_household(d):
    # MEASURED farm-household cash P&L (obj #1) — the ground under every crop-price
    # claim, on the Proactive-assist/#assist surface. Its render GATES on `j.latest`,
    # then reads .latest.income/.expense (objects) + .net_cash_monthly +
    # .farm_share_of_income_pct + .nonfarm_share_of_income_pct (+ .household), and a
    # non-empty .years trend. Fully null-guarded -> a truncated CDN deploy that drops or
    # guts it silently blanks the household backdrop with NO phone alert, and it CANNOT
    # self-heal (OAE farm-household survey fold, no CI cron) — the same blind spot the
    # farm_book / crop_stress obj-#1 probes closed. Asserts the latest gate + its
    # income/expense/net-cash render reads + the years trend; shape not values, robust
    # to a future crop-year vintage.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    L = d.get("latest")
    if not isinstance(L, dict):
        return "missing 'latest' object (the household-P&L render gate)"
    if not isinstance(L.get("income"), dict):
        return "latest.income missing/not-an-object (the farm-cash render read)"
    if not isinstance(L.get("expense"), dict):
        return "latest.expense missing/not-an-object (the cash-expense render read)"
    if not _num(L.get("net_cash_monthly")):
        return "latest.net_cash_monthly missing/non-numeric (the /month lead render read)"
    if not _num(L.get("farm_share_of_income_pct")):
        return "latest.farm_share_of_income_pct missing/non-numeric (the split-bar render read)"
    yrs = d.get("years")
    if not isinstance(yrs, list) or not yrs:
        return "missing/empty 'years' list (the trend-table render read)"
    return None


def _shape_branch_peers(d):
    # The peer-twin outlier benchmark (branch_peers.json, obj #1 PEER pillar,
    # ESTIMATED) — the Risk-trend (#trend) audit-first "risky vs its market twins"
    # list AND the #map peer-deviation lens. TWO render paths, both silently
    # degrading with NO phone alert: peerHasData() gates the lens on a non-empty
    # `.branches` array indexed by branch position (peerRec reads .branches[i].dev),
    # so a truncated file that drops rows misaligns every branch's lens value; and
    # drawPeerOutliers gates the audit table on a non-empty `.outliers` array, each
    # row reading .name/.prov/.risk/.peer_median/.dev/.top_driver + a .twins[] list
    # (.name/.risk per twin). The client sets PEERS=null on any fetch failure, so a
    # truncated/404 CDN deploy blanks the audit list (to "not yet computed") and
    # zeroes the lens with no alert — the same "broken demo" blind spot the
    # branch_risk / peer_province probes closed for their siblings. Asserts the
    # index-aligned branches shape + the outlier row render reads; shape not values.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    brs = d.get("branches")
    if not isinstance(brs, list):
        return "missing 'branches' list (the #map peer-deviation lens read)"
    if len(brs) != 2015:
        return "expected 2015 branch records (index-aligned), got %d" % len(brs)
    if not (isinstance(brs[0], dict) and "dev" in brs[0]):
        return "first branch record missing 'dev' (peerDevVal lens read)"
    outs = d.get("outliers")
    if not isinstance(outs, list) or not outs:
        return "missing/empty 'outliers' list (the #trend audit-table render gate)"
    o0 = outs[0]
    need = ("name", "prov", "risk", "peer_median", "dev", "top_driver", "twins")
    if not isinstance(o0, dict) or not all(k in o0 for k in need):
        return "outlier row missing render keys (name/prov/risk/peer_median/dev/top_driver/twins)"
    if not isinstance(o0.get("twins"), list):
        return "outlier 'twins' is not a list (the closest-twins column render read)"
    return None


def _shape_branch_density(d):
    # Per-branch building density (branch_density.json, MEASURED Overture footprint
    # count ≤10km, projected from source-data/perimeter_counts.json). Consumed in the
    # branch popup via bldgDensityRec(d) = BLDGDEN[idxOf(d)] — the store is set to
    # j.branches and indexed by BRANCH POSITION, so a truncated/misaligned file paints
    # the WRONG branch's building count with NO error (the client sets BLDGDEN=null on a
    # non-200 and omits the block, but a short-but-200 CDN body silently misaligns every
    # row after the cut). Asserts the 2015-record index-aligned .branches shape + the
    # buildings_10km render read on the first record; shape not values.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    brs = d.get("branches")
    if not isinstance(brs, list):
        return "missing 'branches' list (bldgDensityRec index read)"
    if len(brs) != 2015:
        return "expected 2015 branch records (index-aligned), got %d" % len(brs)
    if not (isinstance(brs[0], dict) and "buildings_10km" in brs[0]):
        return "first branch record missing 'buildings_10km' (popup density read)"
    return None


def _shape_branch_fuel(d):
    # Per-branch fuel-station count (branch_fuel.json, MEASURED OSM ≤10km, a lower-bound
    # FLOOR). Consumed in the branch popup via fuelStnRec(d) = FUELSTN[idxOf(d)] — the
    # store is set to j.branches and indexed by BRANCH POSITION, so a truncated file
    # misaligns every branch's fuel-station read with NO error (FUELSTN=null on non-200
    # omits the block; a short-but-200 body silently misaligns). Asserts the 2015-record
    # index-aligned .branches shape + the n10 render read; shape not values.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    brs = d.get("branches")
    if not isinstance(brs, list):
        return "missing 'branches' list (fuelStnRec index read)"
    if len(brs) != 2015:
        return "expected 2015 branch records (index-aligned), got %d" % len(brs)
    if not (isinstance(brs[0], dict) and "n10" in brs[0]):
        return "first branch record missing 'n10' (popup fuel-station read)"
    return None


def _shape_branch_vehicles(d):
    # Per-branch vehicle-collateral base (branch_vehicles.json, MEASURED DLT province
    # stock allocated ESTIMATED by population). Consumed in vehiclePopupHTML via
    # VEHDATA.branches[idxOf(d)], gated on e.n_est>0, rendering the fleet mix off
    # VEHDATA.meta.labels — indexed by BRANCH POSITION, so a truncated file paints the
    # WRONG branch's vehicle mix with NO error (VEHDATA=null on non-200 omits the block;
    # a short-but-200 body silently misaligns). Asserts the .meta.labels render table,
    # the 2015-record index-aligned .branches shape + the fleet/n_est reads on the first
    # record with a catchment; shape not values.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    labels = (d.get("meta") or {}).get("labels")
    if not isinstance(labels, dict) or not labels:
        return "missing 'meta.labels' (the fleet-row label table the popup reads)"
    brs = d.get("branches")
    if not isinstance(brs, list):
        return "missing 'branches' list (VEHDATA.branches index read)"
    if len(brs) != 2015:
        return "expected 2015 branch records (index-aligned), got %d" % len(brs)
    rec = next((b for b in brs if isinstance(b, dict) and b.get("n_est", 0) > 0), None)
    if rec is None:
        return "no branch record with n_est>0 (the popup render gate reads none)"
    if not (isinstance(rec.get("fleet"), dict) and "n_est" in rec and "pickup_share" in rec):
        return "branch record missing fleet/n_est/pickup_share (popup vehicle-mix reads)"
    return None


def _shape_branch_population(d):
    # Per-branch ~10km area-weighted population (branch_population.json, ESTIMATED —
    # the defensive fallback when the MEASURED WorldPop count in contested_pop.json is
    # absent). Consumed via BPOP[i] where the store is set to j.values and indexed by
    # BRANCH POSITION, so a truncated file misaligns every branch's fallback population
    # with NO error (BPOP=null on non-200; a short-but-200 body silently misaligns).
    # Asserts the 2015-entry index-aligned .values list of numbers; shape not values.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    vals = d.get("values")
    if not isinstance(vals, list):
        return "missing 'values' list (the BPOP index-aligned population read)"
    if len(vals) != 2015:
        return "expected 2015 population entries (index-aligned), got %d" % len(vals)
    if not any(isinstance(v, (int, float)) for v in vals):
        return "no numeric population entries (the BPOP fallback read is unusable)"
    return None


def _shape_branch_leads(d):
    # Per-branch WHO-TO-ACQUIRE lead board (branch_leads.json, obj #2). Consumed in the
    # branch popup via leadsRec(d) = LEADS[idxOf(d)] where the store is set to j.branches
    # and indexed by BRANCH POSITION, so a truncated file paints the WRONG branch's lead
    # board with NO error (LEADS=null on non-200 omits the block; a short-but-200 CDN body
    # silently misaligns every row after the cut). The render also joins each lead's .k to
    # the top-level .buckets lookup (leadsBK), so both the index-aligned .branches list and
    # the .buckets table are render dependencies. Asserts the .buckets lookup, the 2015-
    # record index-aligned .branches shape + the leads[].k render read on the first record
    # that carries leads; shape not values.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    buckets = d.get("buckets")
    if not isinstance(buckets, list) or not buckets:
        return "missing 'buckets' list (the leadsBK lookup the popup joins each lead to)"
    if not (isinstance(buckets[0], dict) and "k" in buckets[0]):
        return "first bucket missing 'k' (the leadsBK key the render looks up)"
    brs = d.get("branches")
    if not isinstance(brs, list):
        return "missing 'branches' list (leadsRec index read)"
    if len(brs) != 2015:
        return "expected 2015 branch records (index-aligned), got %d" % len(brs)
    rec = next((b for b in brs if isinstance(b, dict) and b.get("leads")), None)
    if rec is None:
        return "no branch record with a non-empty 'leads' list (the popup render reads none)"
    if not (isinstance(rec["leads"][0], dict) and "k" in rec["leads"][0]):
        return "first lead missing 'k' (the bucket-key the popup joins to leadsBK)"
    return None


def _shape_branch_recommendations(d):
    # Per-branch ACTION recommendations (branch_recommendations.json) — the "what to do
    # here" triage read at the top of the branch panel. Consumed in recsPopupHTML via
    # RECDATA.branches[idxOf(d)], indexed by BRANCH POSITION, so a truncated file paints
    # the WRONG branch's recommendations with NO error (RECDATA=null on non-200 omits the
    # block; a short-but-200 body silently misaligns every row after the cut). Asserts the
    # 2015-record index-aligned .branches shape + the recs[].t/.tone render reads on the
    # first record that carries recs; shape not values.
    if not isinstance(d, dict):
        return "expected an object, got %s" % type(d).__name__
    brs = d.get("branches")
    if not isinstance(brs, list):
        return "missing 'branches' list (RECDATA.branches index read)"
    if len(brs) != 2015:
        return "expected 2015 branch records (index-aligned), got %d" % len(brs)
    rec = next((b for b in brs if isinstance(b, dict) and b.get("recs")), None)
    if rec is None:
        return "no branch record with a non-empty 'recs' list (the popup render reads none)"
    r0 = rec["recs"][0]
    if not (isinstance(r0, dict) and "t" in r0 and "tone" in r0):
        return "first rec missing 't'/'tone' (the popup recommendation text + tone reads)"
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
    # Sibling of tape_real on the SAME MEASURED, un-refreshable owner-side loan
    # tape: the #exposure occupation panel + drill (renderAssistOccMacro /
    # renderAssistOcc) gate on geo.regions and blank SILENTLY when it is missing.
    # tape_real was probed; this cut was the unprobed twin — a truncated deploy
    # would gut the occupation screen with no alert. Closes that blind spot.
    ("data/tape_geo_occ.json", _shape_tape_occ, ".regions occupation cells + .branches drill (MEASURED tape occupation cut, obj #1)"),
    # The Exposure tab's LEAD read (obj #1): segment_exposure.json drives BOTH the
    # colored most-concentrated-region verdict card and the "Portfolio concentration
    # by region" board (renderConcentration/renderExpoVerdict). It gates the whole
    # board on a non-empty .regions array and CANNOT self-heal (mix/HHI derived from
    # the estimated segment scores off the master — a pipeline rebuild, not a CI pull),
    # so a truncated/404 deploy silently blanks the top of #exposure with no phone
    # alert. Was the last unprobed obj-#1 read on the Exposure surface; closes it.
    ("data/segment_exposure.json", _shape_segment_exposure, ".regions (mix/HHI per region) + .national HHI (#exposure concentration board)"),
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
    # The three remaining eager Overview (#overview) backdrop cards that the
    # collateral_flow/truck_flow/region_debt/sfi_credit probes above left
    # uncovered — each loaded on the DEFAULT nav route and each self-hiding when
    # its layer is missing, so a truncated/404 CDN deploy silently blanks it with
    # NO phone alert:
    #  - vehicle_registry (renderVehReg): the MEASURED MOT collateral base, obj #1's
    #    primary class (moto ~half the book);
    #  - drought_district (renderDroughtDistrict): the MODELLED OAE-SPEI district
    #    drought read behind the province crop-stress verdict;
    #  - amphoe_crops (renderAmphoeCrops): MEASURED OAE planted area x that drought,
    #    naming the agri-PD exposure under the driest ground.
    # (dbd_formation is deliberately NOT probed here: its data flows server-side
    # into macro_book — surfaced as national.new_biz_n, which _shape_macro_book
    # already asserts — and its orphaned client loader/renderer were fully removed
    # from app.js 2026-08-11, so the page no longer fetches it. Its siblings
    # region_debt/sfi_credit remain probed above as committed macro_book INPUTS,
    # not as live Overview reads — their client renderers were removed in the same
    # sweep, but the committed files must still serve intact for the next
    # build_macro_book rebuild.)
    ("data/vehicle_registry.json", _shape_vehicle_registry, "latest.groups (4 classes) + latest.title_base/all_vehicles (Overview collateral base, obj #1)"),
    ("data/drought_district.json", _shape_drought_district, ".districts (~928) with spei/cls + meta.counts (Overview district drought, obj #1)"),
    ("data/amphoe_crops.json", _shape_amphoe_crops, ".hotspots (crop x drought exposure w/ planted_rai+spei) (Overview agri-PD exposure, obj #1)"),
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
    # The listed-peer MARKET scoreboard (peer_scoreboard.json, obj #2, MEASURED) —
    # SET market cap / valuation / ROE for the listed title-lenders with AutoX's 25%
    # ROE target as the reference line, the code's own "sharpest external benchmark we
    # have" and the last unprobed obj-#2 peer read on the Competition surface. Unlike
    # its census siblings it CANNOT self-heal (SET is Akamai-blocked from CI, owner-side
    # refresh only), so a truncated/404 CDN deploy that guts it silently drops the board
    # to a calm "not available" placeholder with no phone alert. drawPeerScore gates on
    # a non-empty .peers array, per row reading .name/.symbol + .market_cap_bn + .roe,
    # and the readout leads with .headline and benchmarks against .autox_roe_target.
    # Asserts render shape (the peers gate + row label + numeric mkt-cap/ROE columns +
    # headline + the ROE reference line), not values — robust to a future SET pull.
    ("data/peer_scoreboard.json", _shape_peer_scoreboard, ".peers (listed title-lenders) with market_cap_bn/roe + .headline + .autox_roe_target (#acq listed-peer scoreboard)"),
    # The peer LOAN-QUALITY benchmark (peer_npl.json, obj #1 + #2) — the listed
    # title-lenders' OWN reported NPL ratios next to AutoX's MEASURED own-book NPL
    # from the real loan tape. The last surfaced obj-#2 peer read on the Competition
    # surface with no deploy probe, and like peer_scoreboard it CANNOT self-heal (peer
    # figures from off-repo RESEARCH_DIGEST §B, the AutoX anchor from the owner-side
    # tape — no CI job re-pulls either), so a truncated/404 CDN deploy that guts it
    # silently drops the board to the calm "Peer NPL benchmark not available"
    # placeholder with no phone alert. drawPeerNpl gates on a non-empty .peers array,
    # per row reading .name/.ticker + .npl (the bar/colour/spread), plus the distinct
    # MEASURED .autox row (.name + .npl_live_os_pct + .npl_90plus_os_pct). Asserts
    # render shape, not values — robust to a future RESEARCH_DIGEST / tape refresh.
    ("data/peer_npl.json", _shape_peer_npl, ".peers reported-NPL rows (name/ticker + npl) + .autox MEASURED anchor (npl_live_os_pct/npl_90plus_os_pct) (#acq peer loan-quality board)"),
    # The district-grain competitive layer (obj #2) that sharpens the Competition
    # surface below province level: the "Top go-live districts (recent/total)"
    # go-live leaderboard + the provincial-capital clustering clause both render
    # from it. peer_province + competitor_coverage now cover the province-grain
    # competitive reads; this closes the matching district-grain blind spot so a
    # truncated deploy that guts the recently-shipped go-live leaderboard fires a
    # phone alert instead of silently blanking the อำเภอ reads.
    ("data/pico_district.json", _shape_pico_district, ".top_districts + meta.operating_momentum.top_recent (go-live leaderboard)"),
    ("data/pico_competitors.json", _shape_pico_competitors, ".provinces leaderboard rows (outnumber/pico_total/autox_branches/th) — #acq province-grain sub-scale-rival board"),
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
    # The combined structural-stress index (household DTI + unemployment, MEASURED
    # NSO legs) — parent of the already-probed province_pressure join, and itself the
    # #home "Structurally riskiest" front-door card + a #map lens. Carries the same
    # honest meta.absent guard as household_risk/search_demand (probe treats it as a
    # valid empty shape). It was the last surfaced obj-#1 province read with no deploy
    # probe: a truncated CDN deploy silently drops the front-door leverage card + hides
    # the lens with no phone alert. Closes that blind spot alongside its DTI sibling.
    ("data/province_stress_index.json", _shape_province_stress_index, ".provinces (~77) with composite_stress + province (obj #1 #home structural-leverage card + map lens)"),
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
    # The Overview collateral board's national recovery-value read + the command-
    # center collateral clause (obj #1), and one of the two reads the last audit's
    # "next probe targets" note flagged. renderCollatOutlook + the command-center
    # read both gate off `COLLO.national` (used_veh_yoy_blended for the MEASURED
    # BoT-UVPI resale card; exposure_weighted_outlook/n_firming/most_at_risk for
    # the firming-vs-softening card), and it live-degrades SILENTLY to an editorial
    # fallback — a truncated CDN deploy would drop the measured recovery read with
    # no phone alert. Asserts the two national gate keys + the 77-province backbone.
    ("data/collateral_outlook.json", _shape_collateral_outlook, ".national recovery-value KPIs (used_veh_yoy_blended + exposure_weighted_outlook) + 77-province backbone (Overview collateral board)"),
    ("data/collateral_census.json", _shape_collateral_census, ".book_check priced pools (eval_avg vs measured market_auction, eval_vs_auction gap, dpd30p_pct) — Overview book-vs-recovery card"),
    # The per-branch "What moves this branch" drill (obj #1), and the second read
    # the last audit flagged. msensRec picks MSENS[idxOf(branch)] off `.branches`
    # so it MUST stay index-aligned to branches.json, and msensPhrase renders each
    # driver against `meta.drivers[key]`. Fully null-guarded -> a truncated deploy
    # silently omits the branch driver line with no phone alert. Asserts the index-
    # aligned branch list + a well-formed driver tuple + the meta.drivers table.
    ("data/macro_sensitivity.json", _shape_macro_sensitivity, ".branches index-aligned (2015) driver tuples + meta.drivers label table (branch 'what moves this' drill)"),
    # The Overview (#overview) LEAD narrative (regional_outlook.json) — the very
    # first thing the tab renders (renderNationalOutlook draws the "Bottom line"
    # insight off .national.headline) and the source of the per-province .metrics
    # the risk-drill reveals. The #outlook block is fully null-guarded (absent file
    # -> renders nothing), so a truncated CDN deploy that drops it silently blanks
    # the Overview's lead answer with no phone alert — the same blind spot the
    # collateral_book / macro_book / farm_book probes closed for the sibling Overview
    # reads. Asserts the national.headline gate + the 5 macro-region drill rows.
    ("data/regional_outlook.json", _shape_regional_outlook, ".national.headline lead insight + 5 macro-region drill rows (~77 provinces) (Overview lead narrative)"),
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
    # The brand-level density x service matrix (rival_threat.json, obj #2) — the
    # per-BRAND sibling of rival_threat_region (whose own probe comment named this
    # file as its one unprobed twin). Renders the Competition (#acq) "rival threat
    # matrix" (drawRivThreat), gated on a non-empty .brands array, each row reading
    # .brand + .footprint_vs_autox (×AutoX ratio) + .threat_class; it degrades
    # SILENTLY to a "not yet computed" placeholder with no phone alert when a
    # truncated CDN deploy guts it — the same blind spot the peer_province /
    # competitor_coverage / rival_threat_region probes closed. Asserts render shape
    # (brands gate + brand/threat_class columns + a numeric ×AutoX ratio + the
    # readout headline), not values.
    ("data/rival_threat.json", _shape_rival_threat, ".brands (big-4) density×service matrix + threat_class + .headline (#acq rival threat matrix)"),
    # The rival SERVICE-REPUTATION board (rival_reputation.json, obj #2, MEASURED
    # sample) — the review-count-weighted Google rating by brand, and the shared
    # PARENT of the two already-probed threat layers (rival_threat +
    # rival_threat_region both consume its ratings) that was itself unprobed. It
    # renders the Competition (#acq) "rival service reputation" board (drawRivRep),
    # gated on a non-empty .by_brand array, each row reading .brand + .rating_wavg;
    # a truncated CDN deploy that guts it silently blanks the board (with NO phone
    # alert) while the pre-built committed threat siblings keep rendering, masking
    # the breakage — the same "broken demo" blind spot the peer_province /
    # competitor_coverage / rival_threat probes closed. Asserts render shape (the
    # by_brand gate + brand column + a numeric weighted rating + the readout
    # headline), not values.
    ("data/rival_reputation.json", _shape_rival_reputation, ".by_brand rated-rival ratings + .headline (#acq rival service reputation board)"),
    # The TIME dimension (deltas.json, obj #1) — the last surfaced FRONT-DOOR read with
    # no deploy probe. Renders the command-center "Movers" card (renderHomeMovers off
    # .region + .branches) AND is the whole Risk-trend tab payload (.board YoY re-ratings
    # + mover rows). A truncated/404 file degrades to a CALM "Baseline captured" state on
    # BOTH surfaces — masquerading a broken deploy as the normal single-vintage baseline,
    # with no phone alert, silently hiding real obj-#1 risk movement. Asserts the mover
    # render shape (baseline gate + branch/region mover fields + the #trend board list),
    # shape not values, and stays green in a legitimate baseline vintage.
    ("data/deltas.json", _shape_deltas, ".baseline gate + .branches/.region movers + .board YoY (#home Movers card + #trend tab)"),
    # The Macro tab's nameplate wave (vehicle_models.json, #275/#276, obj #1) — the
    # newest surfaced layer and the last from that wave with no deploy probe. It is
    # load-bearing on two MEASURED render paths: the "which models, and which are
    # growing" nameplate panel (gates on .plates_last12, renders the pickup/ppv
    # .top[] boards) AND the collateral pickup-definition verdict (takes this layer
    # as the AUTHORITATIVE pickup count on AutoX's nameplate rule). The client sets
    # VMODELS=null unless .annual is an array, so a truncated/gutted CDN deploy
    # silently reverts BOTH surfaces to their fallback with no phone alert — the
    # same "broken demo" blind spot the collateral_book / macro_book / deltas obj-#1
    # probes closed for their siblings. Asserts the .annual gate + the pickup/ppv
    # nameplate-board shape, not values — robust to a future DLT-vintage refresh.
    ("data/vehicle_models.json", _shape_vehicle_models, ".annual year table + .plates_last12 pickup/ppv boards (Macro nameplate panel + collateral pickup verdict)"),
    # The per-branch rival-pressure layer (rival_pressure.json, obj #2, MEASURED) —
    # the last surfaced obj-#2 competitive read with no deploy probe. It drives the
    # Risk-trend (#trend) "Most besieged branches" board (drawSiegeTable reads
    # .besieged) AND the per-branch popup line (rivalPressureLineHTML reads the
    # .branches index-aligned array). The client sets RIVP=null unless BOTH .branches
    # and .brands are arrays, so a truncated CDN deploy silently reverts both surfaces
    # to their fallback with no phone alert — the same blind spot the rival_density /
    # rival_threat / rival_threat_region probes closed for their obj-#2 siblings.
    ("data/rival_pressure.json", _shape_rival_pressure, ".brands + 2015-branch index-aligned .branches + .besieged board rows (#trend Most-besieged board + per-branch popup)"),
    # The per-branch crop-AREA layer (branch_cropland.json, obj #1) — the last
    # surfaced per-branch read with no deploy probe. It renders the MEASURED-
    # corrected "crop area within 10km" block in every branch popup
    # (croplandPopupHTML, index-aligned to branches.json), and the client sets
    # CROPLAND=null on any fetch failure so a truncated/404 CDN deploy silently
    # drops the block from every popup with no phone alert — the same blind spot
    # the flood_hazard / branch_labor obj-#1 probes closed for their siblings.
    ("data/branch_cropland.json", _shape_branch_cropland, ".meta.crops + 2015-branch index-aligned .branches with ha[]/crop_ha (per-branch crop-area popup block)"),
    ("data/branch_pico.json", _shape_branch_pico, "2015-branch index-aligned .branches with numeric pico/head/branch/recent (per-branch PICO-rival popup block, obj #2)"),
    ("data/branch_occupations.json", _shape_branch_occupations, ".buckets labels + 2015-branch index-aligned .branches with t/o[] (per-branch occupation-mix popup + #map estab lens, MEASURED)"),
    ("data/branch_workforce.json", _shape_branch_workforce, ".buckets labels + 2015-branch index-aligned .branches with t/w[]/mix[] (per-branch workforce-mix popup, lead-by-occupation, ESTIMATED)"),
    ("data/branch_agri.json", _shape_branch_agri, ".meta.crops + 2015-branch index-aligned .branches with crop_ha/ha[]/sh[] (per-branch agri crop-exposure+stress popup, obj #1)"),
    ("data/branch_density.json", _shape_branch_density, "2015-branch index-aligned .branches with buildings_10km (per-branch building-density popup, MEASURED Overture ≤10km)"),
    ("data/branch_fuel.json", _shape_branch_fuel, "2015-branch index-aligned .branches with n10 (per-branch fuel-station popup, MEASURED OSM ≤10km floor)"),
    ("data/branch_vehicles.json", _shape_branch_vehicles, ".meta.labels + 2015-branch index-aligned .branches with fleet/n_est/pickup_share (per-branch vehicle-collateral popup, DLT stock)"),
    ("data/branch_population.json", _shape_branch_population, "2015-entry index-aligned .values list (per-branch fallback ~10km population, ESTIMATED)"),
    ("data/branch_leads.json", _shape_branch_leads, ".buckets lookup + 2015-branch index-aligned .branches with leads[].k (per-branch who-to-acquire lead-board popup, obj #2)"),
    ("data/branch_recommendations.json", _shape_branch_recommendations, "2015-branch index-aligned .branches with recs[].t/.tone (per-branch action-recommendation popup)"),
    ("data/macro_exposure.json", _shape_macro_exposure, ".meta.factors/factor_keys + 2015-branch index-aligned .branches (t3[]) + 2015-entry .vector (per-branch macro-headwind popup + #map macx lens, obj #1)"),
    # The two collateral-board fleet reads from the same DLT wave, both surfaced via
    # tmliFetch and both self-hiding (display='none') on a truncated/404 deploy with no
    # phone alert — annual off-cadence pulls, so neither self-heals from CI (probe = the
    # only deploy safeguard). vehicle_mix is MEASURED; vehicle_brands' national mix is
    # MEASURED, its province split ESTIMATED and labelled so in the UI.
    ("data/vehicle_mix.json", _shape_vehicle_mix, ".national stock/new maps + .types class list (collateral fleet-mix panel cb-mix, MEASURED)"),
    ("data/vehicle_brands.json", _shape_vehicle_brands, ".national.by_type ry3/ry1 brand boards (collateral new-nameplate panel cb-vbrands; national MEASURED, province split ESTIMATED)"),
    # The proactive-assistance radar PAIR (obj #1) — the two newest surfaced exec reads,
    # both live-fetched into the Proactive-assist (#assist) surface and both unprobed.
    # Each GATES its section on a non-empty array (.crops / .provinces) and silently
    # drops to a calm "not built for this vintage" placeholder with NO phone alert when
    # its file is missing/truncated, and NEITHER self-heals from CI (build_assist_radar_
    # price.py / build_assist_radar_branch.py have no cron), so a truncated/404 CDN
    # deploy that guts either has no job to restore it — exactly the "broken demo" blind
    # spot the crop_stress / branch_cropland / flood_hazard obj-#1 probes closed for
    # their siblings. The branch drill is the "falling-crop radar goes to BRANCH — a
    # call list" ship. Both assert render shape (the gate + a row label + the load-
    # bearing counts the lead/columns render), not values — robust to a future tape /
    # farm-gate vintage refresh, and green in the legitimate "nothing tripped" state.
    ("data/assist_price_radar.json", _shape_assist_price_radar, ".crops falling-price rows (crop/yoy/n_current_x) + .provinces call table + meta.trigger + .tripped (#assist price lens, obj #1)"),
    ("data/assist_branch_radar.json", _shape_assist_branch_radar, ".provinces[].branches ranked call list (name/exposed_crop_ha/n_farm) + meta.n_branches_ranked/n_provinces (#assist branch drill, obj #1)"),
    # The two newest Competition (#acq) reads, shipped together in the #319
    # rival-field wave and both live-fetched (tmliFetch) into the surface with no
    # deploy probe — the last unprobed reads on that tab:
    #  - rival_book_impact: the MEASURED rival-density x real-loan-tape join (obj #1
    #    + #2), whose whole board GATES on .within_province and cannot self-heal (a
    #    pipeline rebuild off the owner-side tape, no CI cron);
    #  - rival_watch: the change-diff panel (obj #2) that answers "what MOVED since
    #    the last pull", off .promos/.ads — a truncated file that parses but drops a
    #    sub-object silently blanks the panel, and it cannot self-heal (diffs off the
    #    Thai-IP promo pull, no CI cron).
    # Each degrades SILENTLY (a calm "not built for this vintage" note) on a
    # truncated/404 CDN deploy with no phone alert — the same "broken demo" blind
    # spot the rival_pulse / rival_ads / peer_province probes closed for their #acq
    # siblings. Both assert render shape, not values.
    ("data/rival_book_impact.json", _shape_rival_book_impact, ".within_province more/less-contested split + gap deltas (#acq rival-density x loan-tape book-cost board)"),
    ("data/rival_watch.json", _shape_rival_watch, ".promos + .ads change-diff counts (#acq 'what changed since the last pull' panel)"),
    # A coherent batch of the remaining surfaced-but-unprobed obj-#1/#2 FRONT-DOOR
    # reads the last three intelligence runs' "next recommended" note enumerated —
    # each live-fetched (tmliFetch / direct fetch) into a default-reachable route, each
    # GATING its section on a specific structural key, and each degrading SILENTLY (a
    # calm "not built for this vintage" / "not available" note) on a truncated/404 CDN
    # deploy with NO phone alert. None self-heals from CI (all fold off owner-side /
    # Thai-IP sources — NSO SES, OAE farm survey, BoT FSR text, the operator roster —
    # with no cron), so the probe is the ONLY deploy safeguard, exactly like the
    # branch_pico / assist-radar siblings. Each asserts render shape, not values:
    #  - debt_source: the #acq informal-debt board (obj #1, MEASURED NSO SES);
    #  - income_impact: the #assist income-impact engine (obj #1, ESTIMATED first-order);
    #  - credit_anchor: the #acq BoT credit-scale anchor (obj #1, MEASURED BoT FSR);
    #  - farm_household: the #assist farm-household cash-P&L backdrop (obj #1, MEASURED OAE);
    #  - rival_universe: the #acq operator census (obj #2).
    ("data/debt_source.json", _shape_debt_source, ".by_class informal-debt board + .national trend series (#acq informal-debt read, obj #1)"),
    ("data/income_impact.json", _shape_income_impact, ".regions income-pressure table with key/income_pressure_pct/book_mix (#assist income-impact engine, obj #1)"),
    ("data/credit_anchor.json", _shape_credit_anchor, ".metrics scale cards + system_npl headline (#acq BoT credit anchor, obj #1)"),
    ("data/farm_household.json", _shape_farm_household, ".latest income/expense/net_cash_monthly + .years trend (#assist farm-household P&L, obj #1)"),
    ("data/rival_universe.json", _shape_rival_universe, ".operators census with tier/name_th + the tier=='us' AutoX row (#acq operator census, obj #2)"),
    # The peer-twin outlier benchmark (branch_peers.json, obj #1 PEER pillar) — the
    # last surfaced peer-comparison read with no deploy probe. It is load-bearing on
    # TWO #trend/#map surfaces (the audit-first "risky vs its market twins" table and
    # the per-branch peer-deviation map lens), both null-guarded so a truncated/404
    # CDN deploy silently blanks the table and zeroes the lens with NO phone alert —
    # the same "broken demo" blind spot the branch_risk / peer_province probes closed
    # for their siblings. Asserts the 2015-index-aligned .branches shape + the outlier
    # row render reads, not values — robust to a future risk-vintage refresh.
    ("data/branch_peers.json", _shape_branch_peers, ".branches index-aligned (2015) with dev + .outliers audit rows (name/prov/risk/peer_median/dev/top_driver/twins) (#trend peer-twin benchmark + #map lens, obj #1)"),
]


# ---------------------------------------------------------------------------
# DATA FRESHNESS — the one class of breakage the ~40 shape validators above
# CANNOT catch. Every check_site_health probe asserts a file's SHAPE; none
# asserts its VINTAGE. So if a data-refresh cron silently freezes (upstream
# API drops, a workflow secret rotates, a pull script starts erroring), the
# last-good file keeps serving, still passes every shape probe, and ships
# green forever — the deploy looks healthy while the numbers quietly rot,
# with no phone alert. This closes that blind spot for the DAILY,
# CI-REFRESHED, CI-REACHABLE price/weather layers, where a lagging vintage is
# an unambiguous "the cron broke" signal (not an owner-side / Thai-IP data gap).
#
# WHY LIVE-ONLY (HttpFetcher, never --local): freshness is inherently a
# function of wall-clock "now", so it CANNOT be part of the deterministic repo
# gate (tests/run.sh runs --local and must reproduce byte-for-byte on any
# date). The nightly probe is exactly where it belongs — it already runs
# against the real deployment with a real clock. The --local path skips this
# block entirely, so the gate's output is unchanged.
#
# FALSE-ALARM-PROOF: a layer is FAILED only when its vintage parses cleanly AND
# is older than a generous per-layer TTL (14 days — ~2 weeks of missed daily
# runs, well past any weekend/holiday upstream gap; only a genuinely stuck cron
# reaches it). Any fetch / parse / missing-key case is recorded as a non-fatal
# "not evaluated" note, never a failure — the fetch + shape probes already own
# "does the file serve and parse". EXCLUDED by design: owner-side / Thai-IP /
# monthly-or-slower layers (rival_pulse promos, search_demand, dbd_formation,
# the annual DLT vehicle stock), whose lag is a known constraint, not a break.
FRESHNESS_LAYERS = [
    # (rel_path, meta_key, max_age_days, cron/source note)
    ("data/commodities.json", "farmgate_vintage", 14,
     "NABC farm-gate, daily CI (data-nabc-prices.yml)"),
    ("data/fuel_prices.json", "pulled", 14,
     "Bangchak retail fuel prices, daily CI (data-fuel-prices.yml) — a DISTINCT "
     "upstream from the NABC farm-gate that commodities.json keys on, so its own "
     "cron can freeze while farmgate stays fresh; .pulled advances every daily "
     "reproject (cadence well under the TTL), so a lag here means the Bangchak pull stuck"),
    ("data/thai_price_history.json", "vintage", 14,
     "Thai daily price history (rebuilt with the daily price pulls)"),
    ("data/thaiwater_flood.json", "pulled", 14,
     "ThaiWater flood pulse, daily CI (data-thaiwater.yml)"),
    ("data/thaiwater_rain.json", "pulled", 14,
     "ThaiWater rain pulse, daily CI (data-thaiwater.yml)"),
    ("data/macro_indicators.json", "pulled", 21,
     "Thai macro-risk indicators (household debt-to-GDP · policy/lending rate · CPI · "
     "USD/THB) — obj#1 borrower-leverage backdrop, live-fetch()'d, refreshed by the "
     "WEEKLY data-macro.yml cron (Mondays) from a DISTINCT keyless cloud upstream "
     "(BIS + World Bank + ECB/Frankfurter FX) that none of the price/weather layers "
     "above touch, so its own pull can freeze while they stay fresh. The pull stamps "
     "meta.pulled every run and the USD/THB leg moves daily, so the folded file "
     "genuinely changes (→ commits) every weekly run — a >21-day lag (3 missed "
     "Mondays) is an unambiguous 'the macro pull stuck' signal, not a flat week"),
    ("data/peer_scoreboard.json", "price_asof", 12,
     "Listed-peer SET market scoreboard (market cap / valuation / ROE for the big-4 "
     "listed title-lenders — obj#2 peer benchmark) — live-fetch()'d (app.js), refreshed "
     "by the WEEKDAY data-set-peers.yml cron (Mon-Fri) via an autonomous SET in-browser "
     "pull that CANNOT self-heal: a broken Playwright/SET-API pull leaves a structurally "
     "valid (shape-probe-green) but frozen scoreboard shipping forever. meta.price_asof "
     "is the SET trading date, so it advances every business day the pull succeeds; a "
     ">12-day lag is ~7 missed trading-day pulls (well past any weekend + Thai market "
     "holiday cluster) — an unambiguous 'the SET pull stuck' signal, not a market lull"),
    ("data/search_demand.json", "pulled_at_utc", 35,
     "Brand share-of-search board (Google Trends interest for AutoX vs the big-4 rivals "
     "per province — obj#2 competitive-demand read) — live-fetch()'d into #acq, refreshed "
     "by BOTH the 4x/day data-swarm.yml google_trends feed AND the monthly dedicated "
     "data-search-demand.yml backstop cron; build_search_demand.py carries pull_google_trends.py's "
     "meta.pulled_at_utc, which is stamped fresh on every SUCCESSFUL Trends pull, so it "
     "advances several times a day when the pull works (observed 3 advances in 18h). It "
     "CANNOT self-heal: both refresh paths call the same rate-limited pull_google_trends.py "
     "from the same CI IP range, so a Google-Trends block freezes them together, leaving a "
     "structurally valid (shape-probe-green) but frozen board shipping forever. A >35-day lag "
     "is past both the monthly backstop cadence AND any Google rate-limit cluster (which "
     "resolves in days) — an unambiguous 'the Trends pull is dead' signal, not a slow week"),
]


def _parse_iso_day(s):
    """Parse a 'YYYY-MM-DD' (optionally with a trailing time) vintage to an
    epoch (UTC midnight). Returns None if it does not start with an ISO day."""
    if not isinstance(s, str):
        return None
    head = s.strip()[:10]
    try:
        t = time.strptime(head, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    return calendar.timegm(t)


def _freshness_result(vintage_str, max_age_days, now_epoch):
    """PURE + deterministic given its inputs (unit-testable offline). Returns
    (ok, detail). ok is False ONLY for a cleanly-parsed vintage older than the
    TTL; an unparseable/absent vintage yields ok=True with a 'not evaluated'
    note so freshness never fires a false alarm."""
    epoch = _parse_iso_day(vintage_str)
    if epoch is None:
        return True, "vintage %r not an ISO day — freshness not evaluated" % (vintage_str,)
    age_days = (now_epoch - epoch) / 86400.0
    if age_days > max_age_days:
        return False, ("vintage %s is %.0f days old (> %d-day TTL) — the refresh "
                       "cron may be stuck" % (str(vintage_str)[:10], age_days, max_age_days))
    return True, "vintage %s, %.0f days old (TTL %d)" % (str(vintage_str)[:10], age_days, max_age_days)


def run_freshness_checks(fetcher, now_epoch, record):
    """Live-only vintage-lag guard over FRESHNESS_LAYERS. Records via `record`."""
    for rel, key, max_age, note in FRESHNESS_LAYERS:
        try:
            body = fetcher.fetch(rel)
            parsed = json.loads(body.decode("utf-8"))
            vintage = parsed.get("meta", {}).get(key)
        except Exception as e:
            record("%s fresh (%s)" % (rel, note), True,
                   "freshness not evaluated (%r)" % e)
            continue
        ok, detail = _freshness_result(vintage, max_age, now_epoch)
        record("%s fresh (%s)" % (rel, note), ok, detail)


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

    # --- data freshness (LIVE ONLY) ---
    # Runs against the real deployment with a real clock; the deterministic
    # --local gate path (LocalFetcher) skips it so the repo gate is unaffected.
    if isinstance(fetcher, HttpFetcher):
        run_freshness_checks(fetcher, time.time(), record)

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
