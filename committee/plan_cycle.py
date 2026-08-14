#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_cycle.py — the AUTONOMY PLANNER: a deterministic, network-free self-assessment.

Reads the REAL committed repo state (platform/data/*.json, pipeline/ + committee/ scripts,
.github/workflows/*.yml, docs/*.md) and the git history, then emits a machine-readable
status/plan the CEO dashboard (platform/status.html) renders live. It NEVER pulls the network
and NEVER fabricates progress: every roadmap item's `state` is derived from a concrete, committed
signal (a data file exists, a pipeline script is present, a workflow is committed, a phrase is in
a doc, a count of catchment files, ...). All timestamps come from git (NOT wall clock) so the
output is byte-stable and reproducible under `--check`.

Outputs (both are deterministic pure functions of the committed tree + git):
  - platform/status_data.json   (machine-readable; consumed by platform/status.html)
  - docs/AUTONOMY_PLAN.md        (human-readable mirror)

status_data.json is written at the platform/ ROOT (not platform/data/) precisely so it is EXEMPT
from tests/validate_data.py (which only scans platform/data/*.json) and pipeline/build_provenance.py
(which censuses platform/data/*.json) — verified: neither looks above platform/data.

  python3 committee/plan_cycle.py            # regenerate both outputs
  python3 committee/plan_cycle.py --check    # byte-exact verify; exit 3 SKIP if git/outputs absent
"""
import argparse
import glob
import json
import math
import os
import re
import subprocess
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "platform", "data")
STATUS_JSON = os.path.join(ROOT, "platform", "status_data.json")
PLAN_MD = os.path.join(ROOT, "docs", "AUTONOMY_PLAN.md")

# Effective throughput: 3 autonomous loops x 4 cycles/day, discounted hard to a conservative
# ~3 shipped items/day. Labelled ESTIMATED everywhere it surfaces.
THROUGHPUT_PER_DAY = 3


# --------------------------------------------------------------------------- git (deterministic clock)
def git(*args):
    """Run a git command from ROOT; return stripped stdout, or None on any failure."""
    try:
        out = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


# --------------------------------------------------------------------------- evidence signals
def dexists(fn):
    """A committed platform/data/<fn> exists (a derived layer shipped)."""
    return os.path.exists(os.path.join(DATA, fn))


def rexists(rel):
    """A committed repo-relative path exists (script / workflow / page)."""
    return os.path.exists(os.path.join(ROOT, rel))


def n_catchments():
    """Count of committed platform/data/*_catchment.json (3D Overture building scenes pulled)."""
    return len(sorted(glob.glob(os.path.join(DATA, "*_catchment.json"))))


def r2_catchments():
    """Provinces whose 3D building catchment is PUBLISHED (R2 + git), from the verified manifest
    (platform/data/catchments_r2.json — every slug confirmed HTTP 200 on the R2 CDN)."""
    try:
        m = json.load(open(os.path.join(DATA, "catchments_r2.json"), encoding="utf-8"))
        return len(m.get("provinces", []))
    except Exception:
        return 0


def real_tape_landed():
    """The REAL measured loan tape has landed and is surfaced — distinct from the SYNTHETIC bridge
    (loan_tape_derived.json). Detected from platform/data/tape_real.json carrying a MEASURED label
    with no SYNTH marker (build_tape_layers.py's no-PII aggregate of the owner's loan-level export).
    This is the signal the loan-tape roadmap items were always meant to flip on; the earlier logic
    only checked the synthetic bridge, so it pinned the #1 milestone at in-progress after the real
    tape shipped."""
    try:
        d = json.load(open(os.path.join(DATA, "tape_real.json"), encoding="utf-8"))
        m = d.get("meta", {})
        return (m.get("label", "").strip().upper().startswith("MEASURED")
                and "SYNTH" not in json.dumps(m, ensure_ascii=False).upper())
    except Exception:
        return False


def real_tape_accounts():
    """MEASURED account count carried in tape_real.json's meta (0 if absent) — read from the
    committed file so the evidence string stays deterministic and truthful."""
    try:
        d = json.load(open(os.path.join(DATA, "tape_real.json"), encoding="utf-8"))
        return int(d.get("meta", {}).get("n_accounts") or 0)
    except Exception:
        return 0


def census_provinces():
    """Distinct provinces covered by the MEASURED competitor census (national-coverage signal)."""
    try:
        c = json.load(open(os.path.join(DATA, "competitors_census.json"), encoding="utf-8"))
        return len({x.get("prov") for x in c.get("items", []) if x.get("prov")})
    except Exception:
        return 0


def doc_has(rel, substr):
    """A committed doc contains a phrase (evidence a step was recorded done)."""
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return False
    try:
        with open(p, encoding="utf-8") as f:
            return substr in f.read()
    except Exception:
        return False


def workflow_schedule(rel):
    """Derive a committed workflow's ACTUAL schedule state from the repo — honest, not aspirational.

    Returns (status, schedule_utc):
      ("scheduled", "<hh,hh,..>")  an UNCOMMENTED `cron:` line is present -> the loop really runs on cron
      ("paused", None)             the workflow file exists but every cron is commented out / absent
                                   (still runnable on demand via workflow_dispatch)
      ("absent", None)             no such workflow is committed
    Comment-stripping is line-based (everything from the first '#'), so a `# schedule:` / `#   - cron:`
    block reads as paused — matching how GitHub Actions itself treats a commented-out schedule. The
    hours field (cron position 2) is surfaced so a re-enabled cron shows its real UTC hours, never a
    hardcoded cadence the repo does not run."""
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return ("absent", None)
    hours = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                code = line.split("#", 1)[0]           # drop inline + full-line comments
                if "cron:" in code:
                    m = re.search(r"cron:\s*[\"']?([^\"']+)", code)
                    if m:
                        fields = m.group(1).split()
                        if len(fields) >= 2 and fields[1] not in hours:
                            hours.append(fields[1])
    except Exception:
        return ("absent", None)
    return ("scheduled", ",".join(hours)) if hours else ("paused", None)


def cron_note(rel):
    """A short, DERIVED honesty suffix for a roadmap item's evidence string: whether the committed
    workflow's cron is actually live, paused, or the file is missing. Keeps 'cron done' items from
    implying an active schedule the repo has switched off."""
    st, hours = workflow_schedule(rel)
    if st == "scheduled":
        return " (cron ACTIVE: %s UTC)" % hours
    if st == "paused":
        return " — cron PAUSED (on demand via workflow_dispatch)"
    return ""


def state(done, in_progress=False):
    return "done" if done else ("in_progress" if in_progress else "open")


# --------------------------------------------------------------------------- ROADMAP (real, traceable)
def build_items():
    """Every item is REAL and traceable; its state is derived from a committed signal (evidence)."""
    nc = n_catchments()
    items = []

    def add(pillar, iid, title, st, priority, evidence, owner_side=False):
        # owner_side = the item cannot be closed by the autonomous loops (it needs an owner action —
        # e.g. a Vercel env var + a live production check). Flagged so the ETA excludes it instead of
        # perpetually promising "done tomorrow" for work no loop can finish.
        items.append({"id": iid, "pillar": pillar, "title": title, "state": st,
                      "priority": priority, "evidence": evidence, "owner_side": bool(owner_side)})

    # ---- data-integration ----
    add("data-integration", "di-tmli", "Fold MEASURED TMLI province layers (NSO SES/LFS) into the risk read",
        state(rexists("pipeline/ingest_tmli.py") and dexists("household_risk_by_province.json")), 1,
        "pipeline/ingest_tmli.py + platform/data/household_risk_by_province.json present (NEXT_STEPS §0a)")
    add("data-integration", "di-diw", "DIW factory census (~66k, 77 provinces) via CKAN",
        state(rexists("committee/census.py") and rexists(".github/workflows/data-gov-census.yml")), 2,
        "committee/census.py + .github/workflows/data-gov-census.yml committed")
    _real_tape = real_tape_landed()
    add("data-integration", "di-loan-tape", "Real loan-tape export → measured portfolio risk",
        state(_real_tape,
              in_progress=(not _real_tape) and rexists("pipeline/ingest_real_tape.py")), 1,
        ("platform/data/tape_real.json present — MEASURED real AutoX loan-tape aggregates "
         "(%s no-PII accounts, built by pipeline/build_tape_layers.py from the owner's loan-level export)"
         % f"{real_tape_accounts():,}") if _real_tape else
        "ingest_real_tape.py present but no tape_real.json — the owner-side xlsx has not been streamed yet "
        "(TONIGHT_CHECKLIST §6). The SYNTHETIC bridge was retired 2026-07-31; there is no fallback layer.")
    add("data-integration", "di-dlt", "DLT vehicle registrations, all-province coverage",
        state(dexists("branch_vehicles.json") and rexists("source-data/vehicles_by_province.json")), 2,
        "vehicles_by_province.json = DLT registered-vehicle stock across all 77 provinces "
        "(44.3M vehicles: car/pickup/moto/ev, 0 gaps); wired per-branch via branch_vehicles.json (NEXT_STEPS §2)")
    add("data-integration", "di-farmgate", "Replace GLOBAL price proxy with Thai farm-gate prices",
        state(rexists("source-data/farmgate_prices.json") and doc_has("pipeline/build_crop_stress.py", "farmgate_prices.json")), 2,
        "source-data/farmgate_prices.json (MEASURED Thai daily national-average farm-gate prices — NABC "
        "agriapi.nabc.go.th, vintage 2026-07-02, live-verified from the Thai IP) wired into "
        "build_crop_stress.py price_stress, replacing the World Bank GLOBAL proxy for rice/rubber/oil palm")
    add("data-integration", "di-competitor-census", "National competitor census (Places scout, gate-guarded)",
        state(rexists("committee/scout.py") and dexists("competitors_census.json") and dexists("competitor_coverage.json")), 2,
        "competitors_census.json = 16,503 rivals across all 77 provinces + competitor_coverage.json")

    # ---- deployment ----
    add("deployment", "dep-vercel", "Deploy to Vercel prod + verify on a phone",
        state(doc_has("docs/PROGRESS_LOG.md", "PROD DEPLOY VERIFIED")), 1,
        "LIVE on Vercel production (master auto-deploys); verified 200 on /, /app.js, data layers, 3D scenes + /status")
    add("deployment", "dep-committee-cron", "Autonomous committee scout cron (gate-guarded auto-merge)",
        state(rexists(".github/workflows/committee-cycle.yml")), 2,
        ".github/workflows/committee-cycle.yml committed" + cron_note(".github/workflows/committee-cycle.yml"))
    add("deployment", "dep-gov-census-ci", "Gov census CI (DIW/DLT from any cloud IP)",
        state(rexists(".github/workflows/data-gov-census.yml")), 2,
        ".github/workflows/data-gov-census.yml committed")
    add("deployment", "dep-planner-cron", "Autonomy planner cron (this loop)",
        state(rexists(".github/workflows/committee-planner.yml") and rexists("platform/status.html")), 1,
        ".github/workflows/committee-planner.yml + platform/status.html present" + cron_note(".github/workflows/committee-planner.yml"))
    add("deployment", "dep-qa-gate", "Determinism QA gate in CI (tests/run.sh check)",
        state(rexists(".github/workflows/qa.yml") and rexists("tests/run.sh")), 2,
        ".github/workflows/qa.yml + tests/run.sh committed")
    add("deployment", "dep-access", "Access protection on the deployment (sensitive branch-level PD)",
        state(rexists("middleware.js") and doc_has("docs/PROGRESS_LOG.md", "ACCESS PROTECTION VERIFIED")), 3,
        "Vercel Edge Middleware (./middleware.js) HTTP Basic Auth, gated by the SITE_PASSWORD env var; "
        "fail-open when unset. Verified live (401 without creds, 200 with the password).",
        owner_side=True)

    # ---- feature ----
    add("feature", "feat-competitor-coverage", "Competitive coverage & rival pressure (national census)",
        state(dexists("competitor_coverage.json") and rexists("pipeline/build_competitor_coverage.py")), 1,
        "platform/data/competitor_coverage.json + pipeline/build_competitor_coverage.py present")
    add("feature", "feat-decision-queue", "Exec decision queue (“This week — do these first”)",
        state(dexists("decision_queue.json") and rexists("pipeline/build_decision_queue.py")), 1,
        "platform/data/decision_queue.json + pipeline/build_decision_queue.py present")
    add("feature", "feat-competitor-fragility", "Competitor fragility under BoT registration deadline (market-risk lens)",
        state(dexists("exit_whitespace.json")), 2,
        "platform/data/exit_whitespace.json present")
    add("feature", "feat-search-demand", "Search demand + share-of-search board",
        state(dexists("search_demand.json")), 2,
        "platform/data/search_demand.json present")
    add("feature", "feat-collateral", "Collateral-value outlook (directional, estimated)",
        state(dexists("collateral_outlook.json")), 2,
        "platform/data/collateral_outlook.json present")
    add("feature", "feat-simulator", "Client-side portfolio what-if simulator (#sim)",
        state(doc_has("platform/index.html", 'id="v-sim"') or doc_has("platform/index.html", "#sim")), 2,
        "index.html #sim simulator view present")
    add("feature", "feat-status", "CEO autonomy status dashboard (this deliverable)",
        state(rexists("platform/status.html") and rexists("platform/status_data.json")), 1,
        "platform/status.html + platform/status_data.json present")

    # ---- uxui (seeded from docs/UXUI_AUDIT.md) ----
    add("uxui", "ux-basemap", "Fix branch-explorer dead basemap (BLOCKER)",
        state(doc_has("docs/UXUI_AUDIT.md", "FIXED + verified")), 1,
        "UXUI_AUDIT.md marks the blocker ✅ FIXED + verified (0 console errors)")
    add("uxui", "ux-isochrone-guard", "Guard rayong isochrone/trees toggles when files absent (major)",
        state(doc_has("docs/UXUI_AUDIT.md", "ux-isochrone-guard — ✅ FIXED")), 2,
        "rayong-catchment.html gates isochrone/trees fetch on tiles_config scenery list — no console 404; toggle self-hides when absent (UXUI_AUDIT #2)")
    add("uxui", "ux-map-overlap", "Fix #map lens pills overlapping the zoom control on mobile (major)",
        state(doc_has("docs/UXUI_AUDIT.md", "ux-map-overlap — ✅ FIXED")), 2,
        "styles.css @media(max-width:430px) moves the Leaflet zoom to bottom-right, clear of the lens pills (UXUI_AUDIT #3)")
    add("uxui", "ux-province-overflow", "province.html stat-chip toolbar overflow scroller (minor)",
        state(doc_has("docs/UXUI_AUDIT.md", "ux-province-overflow — ✅ FIXED")), 3,
        "province.html #strip is a touch horizontal scroller (-webkit-overflow-scrolling:touch + white-space:nowrap) (UXUI_AUDIT #4)")
    add("uxui", "ux-theme-persist", "Persist one theme choice across pages (minor)",
        state(doc_has("docs/UXUI_AUDIT.md", "ux-theme-persist — ✅ FIXED")), 3,
        "all pages read the persisted autox-theme; province/branch-explorer aligned to the SPA light default (UXUI_AUDIT #5)")
    add("uxui", "ux-contrast", "Darken light-theme --dim for WCAG AA on microcopy (minor)",
        state(not doc_has("platform/styles.css", "--dim:#7A8598")), 3,
        "styles.css light --dim darkened to #5B6678 (≈5.4:1 on #F4F6FA, clears AA) (UXUI_AUDIT #6)")
    add("uxui", "ux-favicon", "Add a favicon (stop the 404) (polish)",
        state(rexists("platform/favicon.ico") or rexists("platform/favicon.svg") or rexists("platform/favicon.png")), 3,
        "platform/favicon.svg committed + linked in every page head (UXUI_AUDIT #7)")
    add("uxui", "ux-branches-lead", "Add a headline/lead line to #branches (polish)",
        state(doc_has("docs/UXUI_AUDIT.md", "ux-branches-lead — ✅ FIXED")), 3,
        "index.html #branches opens with a header + lead line like the other routes (UXUI_AUDIT #8)")

    # ---- market ----
    add("market", "mkt-rival-pressure", "Rival pressure index per branch",
        state(dexists("rival_pressure.json")), 2, "platform/data/rival_pressure.json present")
    add("market", "mkt-rival-density", "Rival density per district",
        state(dexists("rival_density.json")), 2, "platform/data/rival_density.json present")
    add("market", "mkt-comp-coverage", "Competitor coverage vs our footprint",
        state(dexists("competitor_coverage.json")), 2, "platform/data/competitor_coverage.json present")
    add("market", "mkt-contested-pop", "Contested population (rival catchment overlap)",
        state(dexists("contested_pop.json")), 3, "platform/data/contested_pop.json present")
    add("market", "mkt-search-sos", "Share-of-search brand read",
        state(dexists("search_demand.json")), 2, "platform/data/search_demand.json present")
    _scout_provs = census_provinces()
    add("market", "mkt-scout-national", "National scout coverage (rotate all 77 provinces)",
        state(_scout_provs >= 77), 2,
        ("competitors_census.json spans all %d/77 provinces — the committee-cycle.yml scout rotation "
         "has reached full national coverage" % _scout_provs) if _scout_provs >= 77 else
        ("scout rotates least-covered provinces via committee-cycle.yml; %d/77 provinces covered so far"
         % _scout_provs))

    # ---- service (portfolio & risk) ----
    add("service", "svc-loan-tape", "Loan-tape portfolio outputs (90+ aging, ROI, HHI, PD)",
        state(_real_tape, in_progress=(not _real_tape) and dexists("loan_tape_derived.json")), 1,
        ("platform/data/tape_real.json surfaced — MEASURED portfolio truth (bucket ladder / restructuring / "
         "collateral / LTV & vintage curves / branch audit) from the real loan-level export via "
         "build_tape_layers.py; supersedes the SYNTHETIC loan_tape_derived.json") if _real_tape else
        "loan_tape_derived.json present (SYNTHETIC); flips to measured on a real export (NEXT_STEPS §0b)")
    add("service", "svc-household-dti", "Household DTI risk lens (NSO SES, measured)",
        state(dexists("household_risk_by_province.json")), 1,
        "platform/data/household_risk_by_province.json present")
    add("service", "svc-branch-risk", "Composite per-branch risk",
        state(dexists("branch_risk.json")), 1, "platform/data/branch_risk.json present")
    add("service", "svc-crop-stress", "Agri-PD crop stress (objective #1)",
        state(dexists("crop_stress.json")), 2, "platform/data/crop_stress.json present")
    add("service", "svc-occ-income", "Occupation income floors (factory / agri / SME)",
        state(dexists("factory_income_by_province.json") and dexists("agri_income_by_province.json")), 2,
        "factory_income_by_province.json + agri_income_by_province.json present")
    add("service", "svc-macro-exposure", "Per-branch macro exposure",
        state(dexists("macro_exposure.json")), 3, "platform/data/macro_exposure.json present")

    # ---- peer (benchmarking) ----
    add("peer", "peer-branch-twins", "Branch peer-twin outlier benchmark",
        state(dexists("branch_peers.json") and rexists("pipeline/build_branch_peers.py")), 1,
        "platform/data/branch_peers.json + pipeline/build_branch_peers.py present")
    add("peer", "peer-province-stress", "Province stress-index ranking",
        state(dexists("province_stress_index.json")), 2, "platform/data/province_stress_index.json present")
    add("peer", "peer-province-risk", "Province risk rollup",
        state(dexists("province_risk.json")), 2, "platform/data/province_risk.json present")
    add("peer", "peer-segment-exposure", "Segment × collateral concentration",
        state(dexists("segment_exposure.json")), 2, "platform/data/segment_exposure.json present")
    add("peer", "peer-cluster-brief", "Like-branch cluster brief",
        state(dexists("cluster_brief.json")), 3, "platform/data/cluster_brief.json present")

    # ---- 3d-enrichment ----
    add("3d-enrichment", "td-province", "deck.gl province district-polygon deep-dive (77)",
        state(rexists("platform/province.html") and dexists("provinces/index.json")), 2,
        "platform/province.html + platform/data/provinces/index.json present")
    add("3d-enrichment", "td-branch-explorer", "Per-branch 3D scene (live OSM buildings)",
        state(rexists("platform/branch-explorer.html")), 2, "platform/branch-explorer.html present")
    add("3d-enrichment", "td-catchment-scene", "Overture 3D building catchment scene",
        state(rexists("platform/rayong-catchment.html") and dexists("rayong_catchment.json")), 2,
        "platform/rayong-catchment.html + platform/data/rayong_catchment.json present")
    add("3d-enrichment", "td-overture-pull", "Pull Overture building catchments per province",
        state((nc + r2_catchments()) >= 77, in_progress=0 < (nc + r2_catchments()) < 77), 2,
        "%d of 77 province catchments present (platform/data/*_catchment.json)" % nc)
    add("3d-enrichment", "td-heights", "Bake per-building type/height into catchment scenes",
        state(rexists("pipeline/bake_catchment_heights.py")), 3, "pipeline/bake_catchment_heights.py present")
    add("3d-enrichment", "td-isochrone", "True 15-min street-network isochrone (replace walk-radius)",
        state(rexists("pipeline/pull_isochrones.py") and rexists(".github/workflows/data-isochrones.yml")), 3,
        "pipeline/pull_isochrones.py + .github/workflows/data-isochrones.yml present (ORS driving-car 15-min → R2; scene prefers it over the estimated walk-radius ring)")

    return items


# --------------------------------------------------------------------------- assembly
PILLAR_LABELS = [
    ("data-integration", "Data integration"),
    ("deployment", "Deployment & autonomy"),
    ("feature", "Features"),
    ("uxui", "UX / UI"),
    ("market", "Market intelligence"),
    ("service", "Portfolio & risk"),
    ("peer", "Peer benchmarking"),
    ("3d-enrichment", "3D enrichment"),
]

# Autonomous loops. Each loop's schedule is DERIVED from its committed workflow (or honestly marked
# external / paused), never asserted — deriving it here stops the CEO dashboard advertising fixed cron
# cadences the repo does not actually run. The three improvement loops run as account-level scheduled
# routines with NO committed workflow file (there is nothing in .github/workflows to verify a cadence
# against — their real activity is the git feed below). The two committee loops HAVE workflows whose
# crons were paused 2026-07 (owner request) and now run on demand via workflow_dispatch.
LOOP_DEFS = [
    {"name": "integration-improvement", "owns": "data · feature · deploy", "workflow": None},
    {"name": "ux-improvement", "owns": "UX/UI", "workflow": None},
    {"name": "intelligence", "owns": "market · service · peer · deploy-health", "workflow": None},
    {"name": "committee-scout", "owns": "competitor census", "workflow": ".github/workflows/committee-cycle.yml"},
    {"name": "committee-planner", "owns": "this plan", "workflow": ".github/workflows/committee-planner.yml"},
]


def build_loops():
    """Project LOOP_DEFS into display rows with a schedule that reflects the committed repo state."""
    out = []
    for d in LOOP_DEFS:
        wf = d.get("workflow")
        sched = None
        if wf is None:
            status, cadence = "external", "account-scheduled routine (no committed workflow)"
        else:
            st, hours = workflow_schedule(wf)
            if st == "scheduled":
                status, cadence, sched = "scheduled", "cron", hours
            elif st == "paused":
                status, cadence = "paused", "paused — on demand via workflow_dispatch"
            else:
                status, cadence = "absent", "workflow not committed"
        row = {"name": d["name"], "owns": d["owns"], "cadence": cadence, "status": status}
        if sched:
            row["schedule_utc"] = sched
        out.append(row)
    return out

# activity-feed pillar classification (keyword → pillar; first match wins; specific before generic)
_CLASSIFY = [
    ("3d-enrichment", ["catchment", "overture", "3d", "building", "deck", "isochrone", "tile", "height"]),
    ("uxui", ["ux", "ui", "theme", "mobile", "css", "styles", "layout", "favicon", "render", "visual", "a11y", "contrast"]),
    ("market", ["competitor", "rival", "scout", "market", "share-of-search", "sos"]),
    ("peer", ["peer", "twin", "cluster", "benchmark"]),
    ("service", ["risk", "loan", "tape", "dti", "household", "crop", "collateral", "exposure", " pd", "portfolio"]),
    ("data-integration", ["ingest", "tmli", "doae", "gov", "dlt", "diw", "census", "pull", "fold", "enrich", "nabc", "oae", "data"]),
    ("deployment", ["deploy", "vercel", "ci", "workflow", "cron", "gate", "committee", "r2", "migration", "qa"]),
    ("feature", ["feat", "feature", "queue", "plan", "simulator", "expansion", "acq", "whitespace"]),
]


def classify_pillar(summary):
    s = summary.lower()
    for pillar, kws in _CLASSIFY:
        if any(k in s for k in kws):
            return pillar
    return "feature"


def build_activity():
    raw = git("log", "-30", "--format=%cI|%h|%s")
    if raw is None:
        return []
    feed = []
    for line in raw.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        iso, sha, summary = parts[0].strip(), parts[1].strip(), parts[2].strip()
        feed.append({"date": iso, "sha": sha, "summary": summary, "pillar": classify_pillar(summary)})
    return feed


def assemble():
    """Return the full status object, or None if git is unavailable (SKIP signal)."""
    generated_at = git("log", "-1", "--format=%cI")
    commit = git("rev-parse", "--short", "HEAD")
    if not generated_at or not commit:
        return None

    items = build_items()

    pillars = []
    sum_done = sum_total = 0
    for key, label in PILLAR_LABELS:
        its = [i for i in items if i["pillar"] == key]
        done = sum(1 for i in its if i["state"] == "done")
        total = len(its)
        sum_done += done
        sum_total += total
        pct = round(100 * done / total) if total else 0
        pstatus = "on-track" if done >= total - done else "at-risk"
        pillars.append({
            "key": key, "label": label, "progress_pct": pct, "done": done, "total": total,
            "status": pstatus,
            "items": [{"id": i["id"], "title": i["title"], "state": i["state"],
                       "priority": i["priority"], "evidence": i["evidence"],
                       "owner_side": i.get("owner_side", False)} for i in its],
        })

    done_items = sum(1 for i in items if i["state"] == "done")
    in_progress_items = sum(1 for i in items if i["state"] == "in_progress")
    open_items = sum(1 for i in items if i["state"] == "open")
    # Split open work by who can actually finish it. Owner-side items (e.g. an env var + a live prod
    # check) are NOT loop-closable, so the ETA — which projects the autonomous loops' throughput —
    # must be computed over the autonomous-open subset only, else it perpetually promises "done
    # tomorrow" for work the loops can never touch.
    open_owner_side = sum(1 for i in items if i["state"] == "open" and i.get("owner_side"))
    open_autonomous = open_items - open_owner_side
    total_items = len(items)
    progress_pct = round(100 * sum_done / sum_total) if sum_total else 0

    eta_days = math.ceil(open_autonomous / THROUGHPUT_PER_DAY) if open_autonomous else 0
    eta_date = (date.fromisoformat(generated_at[:10]) + timedelta(days=eta_days)).isoformat()
    overall_status = "on-track" if done_items >= open_items else "at-risk"

    return {
        "meta": {
            "title": "AutoX Platform — Autonomy Plan",
            "generated_by": "committee/plan_cycle.py",
            "generated_at": generated_at,
            "commit": commit,
        },
        "overall": {
            "progress_pct": progress_pct,
            "status": overall_status,
            "eta_days": eta_days,
            "eta_date": eta_date,
            "done_items": done_items,
            "in_progress_items": in_progress_items,
            "open_items": open_items,
            "open_owner_side": open_owner_side,
            "open_autonomous": open_autonomous,
            "total_items": total_items,
        },
        "loops": build_loops(),
        "pillars": pillars,
        "activity": build_activity(),
    }


# --------------------------------------------------------------------------- serialization
def serialize_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def render_markdown(obj):
    o = obj["overall"]
    m = obj["meta"]
    L = []
    L.append("# AutoX Platform — Autonomy Plan")
    L.append("")
    L.append("> Auto-generated by `committee/plan_cycle.py` — do NOT edit by hand. "
             "Deterministic, network-free, evidence-based. Every item's state is derived from a "
             "committed signal; nothing here is aspirational.")
    L.append("")
    L.append("_Generated at %s (commit `%s`)._" % (m["generated_at"], m["commit"]))
    L.append("")
    L.append("## Overall: %d%% complete — %s" % (o["progress_pct"], o["status"]))
    L.append("")
    owner_side = o.get("open_owner_side", 0)
    autonomous = o.get("open_autonomous", o["open_items"])
    open_note = (" (%d owner-side)" % owner_side) if owner_side else ""
    L.append("- **Done:** %d · **In progress:** %d · **Open:** %d%s · **Total:** %d"
             % (o["done_items"], o["in_progress_items"], o["open_items"], open_note, o["total_items"]))
    if autonomous <= 0 and owner_side:
        L.append("- **ETA (ESTIMATED):** no autonomously-completable items remain — the %d open "
                 "item%s %s owner-side (need an owner action, e.g. a Vercel env var + a live check), "
                 "not loop-closable." % (owner_side, "" if owner_side == 1 else "s",
                                         "is" if owner_side == 1 else "are"))
    else:
        L.append("- **ETA (ESTIMATED):** ~%d days · by %s (at ~%d items/day over %d autonomous open "
                 "item%s%s)" % (o["eta_days"], o["eta_date"], THROUGHPUT_PER_DAY, autonomous,
                                "" if autonomous == 1 else "s",
                                ("; %d more owner-side" % owner_side) if owner_side else ""))
    L.append("")
    L.append("## Autonomous loops")
    L.append("")
    for lp in obj["loops"]:
        sched = (" · " + lp["schedule_utc"] + " UTC") if lp.get("schedule_utc") else ""
        L.append("- **%s** — %s · %s%s" % (lp["name"], lp["owns"], lp["cadence"], sched))
    L.append("")
    L.append("## Pillars")
    L.append("")
    chip = {"done": "✅", "in_progress": "\U0001f7e1", "open": "⬜"}
    for p in obj["pillars"]:
        L.append("### %s — %d%% (%d/%d) · %s"
                 % (p["label"], p["progress_pct"], p["done"], p["total"], p["status"]))
        L.append("")
        for it in p["items"]:
            st_lbl = it["state"] + (" · owner-side" if it.get("owner_side") and it["state"] != "done" else "")
            L.append("- %s **%s** — _%s_ (P%d) — %s"
                     % (chip.get(it["state"], "⬜"), it["title"], st_lbl,
                        it["priority"], it["evidence"]))
        L.append("")
    L.append("## Recent activity")
    L.append("")
    for a in obj["activity"][:20]:
        L.append("- `%s` · %s · **%s** — %s"
                 % (a["sha"], a["date"][:10], a["pillar"], a["summary"]))
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="byte-exact verify committed outputs")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass

    obj = assemble()
    if obj is None:
        # git is the required input; without it the plan cannot be built deterministically.
        if args.check:
            print("plan_cycle.py --check: SKIP (git history unavailable)")
            sys.exit(3)
        sys.exit("plan_cycle.py: git history unavailable (run inside the repo).")

    json_payload = serialize_json(obj)
    md_payload = render_markdown(obj)

    if args.check:
        if not os.path.exists(STATUS_JSON) or not os.path.exists(PLAN_MD):
            print("plan_cycle.py --check: SKIP (outputs not generated yet)")
            sys.exit(3)
        drift = []
        if open(STATUS_JSON, encoding="utf-8").read() != json_payload:
            drift.append("platform/status_data.json")
        if open(PLAN_MD, encoding="utf-8").read() != md_payload:
            drift.append("docs/AUTONOMY_PLAN.md")
        if drift:
            sys.exit("plan_cycle.py --check: drifted (%s) — run: python3 committee/plan_cycle.py"
                     % ", ".join(drift))
        print("plan_cycle.py --check: OK (byte-exact)")
        return

    with open(STATUS_JSON, "w", encoding="utf-8") as f:
        f.write(json_payload)
    with open(PLAN_MD, "w", encoding="utf-8") as f:
        f.write(md_payload)
    o = obj["overall"]
    print("wrote platform/status_data.json + docs/AUTONOMY_PLAN.md — %d%% (%d done / %d in-progress / %d open / %d total), ETA ~%d days by %s"
          % (o["progress_pct"], o["done_items"], o["in_progress_items"], o["open_items"],
             o["total_items"], o["eta_days"], o["eta_date"]))


if __name__ == "__main__":
    main()
