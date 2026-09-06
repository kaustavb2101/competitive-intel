#!/usr/bin/env python3
"""
build_decision_queue.py — EXEC DECISION QUEUE for the Command Center (#home)
=============================================================================
Synthesizes ~6 concrete recommended actions — "This week — do these first" —
from EXISTING committed layers ONLY. Nothing is measured or estimated here that
was not already measured or estimated upstream; this script only SELECTS and
PHRASES, and every number in every sentence is copied verbatim (or rounded,
stated below) from the named source file.

STRATEGY SCOPE (CLAUDE.md objective #2): AutoX is CONSOLIDATING / rationalising
the ~2,015-branch network it already runs — there is no branch-growth target, and
this platform makes NO open / close / where-to-open recommendation. The queue is a
RISK-and-DEFENCE list on the existing book only: it never emits an "open" or "scout"
action. (The upstream opportunity_score.json / exit_whitespace.json layers stay on
disk — exit_whitespace still surfaces on #acq as a competitive-landscape signal —
but they are NOT read here, so no expansion row can reach the exec front door.)

Inputs (all under platform/data/, all committed, all optional — a missing layer
just contributes no items):
  rival_pressure.json    -> DEFEND  : the most besieged branches (MEASURED geometry)
  branch_risk.json       -> DEFEND+ : DOUBLE JEOPARDY — the besieged branch whose portfolio
                                      composite risk is also top-quartile (index-join of the two
                                      layers; MEASURED siege x ESTIMATED book stress)
  branch_peers.json      -> AUDIT   : branches out of line vs statistical twins (ESTIMATED)
  macro_sensitivity.json -> TIGHTEN : the worst macro-headwind province (ESTIMATED proxy)
  crop_stress.json       -> TIGHTEN : the worst crop-household-stress province (ESTIMATED)

Output: platform/data/decision_queue.json
  { meta: {... full provenance + the ranking rule below ...},
    items: [{rank, type, act, basis, source, go, go_label, name, prov, priority} x ~8] }

DETERMINISTIC RANKING (no wall clock, no randomness — documented here and in meta):
  priority = TYPE_BASE[type] + 10 * intensity          (rounded to 2 dp)
  TYPE_BASE — an EDITORIAL precedence, stated openly: defending and auditing the
  existing book outranks tightening actions in a weekly queue:
      defend = 40   audit = 30   tighten = 20
  intensity in [0, 1] — the layer's own native magnitude, normalized WITHIN its layer
  (cross-layer scores are not commensurable, so we never pretend they are):
      defend  : n2 / max(n2 over the shipped besieged list)     (measured rival count <=2 km)
      audit   : dev / max(dev over the shipped outlier list)    (risk-proxy points above twins)
      tighten : macro   -> hits / n  (share of the province's branches led by the headwind)
                crop    -> agri_stress (already 0..1)
  Sort: priority desc, then type asc, then name asc (total order — byte-stable).
  Candidate picks are deterministic too: each source list is used in its committed
  sort order; DEFEND picks the top 2 besieged branches in DISTINCT districts and
  AUDIT the top 2 outliers in DISTINCT provinces (so the queue is not two rows of
  the same market).

Deterministic + network-free. Pure stdlib.
    python3 build_decision_queue.py            # write the JSON
    python3 build_decision_queue.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
OUT  = os.path.join(DATA, "decision_queue.json")

# CONSOLIDATION SCOPE (CLAUDE.md objective #2): no "expand" tier — the queue never
# recommends opening / scouting new ground; it is a defence/audit/tighten list on the
# existing network only.
TYPE_BASE = {"defend": 40.0, "audit": 30.0, "tighten": 20.0}
# DOUBLE-JEOPARDY precedence (stated openly): a branch that is BOTH besieged by rivals
# (objective #2, MEASURED geometry) AND carries a top-quartile portfolio composite risk
# (objective #1, ESTIMATED) is strictly more urgent than an equally-besieged branch with a
# healthy book — so its base sits ABOVE the plain-defend base (max plain-defend = 40+10 = 50),
# guaranteeing the double-jeopardy row leads the defend group. It renders as a `defend` chip
# (measured rival trigger, same as the other defend rows); the estimated composite is tagged
# inline, so the row-level measured tag and the queue footer stay accurate.
JEOPARDY_BASE = 50.0
GO_LABEL  = {"trend": "Risk trend →", "overview": "Macro →"}  # nav labels the overview route "Macro" (five-pillar re-IA); "Risk trend →" is still #trend's TAB_TITLE.
# plain-language driver names (same map as app.js RISK_DRIVER_LABEL)
DRIVER_LABEL = {"household": "household leverage", "agri": "crop / drought stress",
                "occupation": "occupation concentration", "segment": "segment / collateral mix"}


def _load(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _num(v, nd=1):
    """Fixed-precision display number (str) — deterministic, no trailing .0 noise."""
    if v is None:
        return "—"
    r = round(float(v), nd)
    if r == int(r):
        return str(int(r))
    return str(r)


def build():
    rivp  = _load("rival_pressure.json")
    peers = _load("branch_peers.json")
    msens = _load("macro_sensitivity.json")
    crop  = _load("crop_stress.json")
    brisk = _load("branch_risk.json")

    # branch_risk.branches[] is INDEX-ALIGNED to branches.json, and rival_pressure's
    # besieged[].i is that same branches.json index — so a besieged branch's portfolio
    # composite risk is a pure index lookup (no recompute, no new estimation here). We also
    # precompute the network top-quartile / top-decile composite cuts so the double-jeopardy
    # row can name WHERE the book screens, deterministically, over present values only.
    rk_branches = (brisk or {}).get("branches") or []
    rk_present  = sorted(x["composite_risk"] for x in rk_branches
                         if isinstance(x.get("composite_risk"), (int, float)))
    rk_max = rk_present[-1] if rk_present else 0.0
    rk_p75 = rk_present[int(len(rk_present) * 0.75)] if rk_present else None
    rk_p90 = rk_present[int(len(rk_present) * 0.90)] if rk_present else None

    def _risk_at(i):
        """(composite_risk, top_driver) for branches.json index i, or (None, None)."""
        if isinstance(i, int) and 0 <= i < len(rk_branches):
            r = rk_branches[i]
            cr = r.get("composite_risk")
            if isinstance(cr, (int, float)):
                return cr, r.get("top_driver")
        return None, None

    items, used = [], []

    # ---- DEFEND (MEASURED) — top-2 besieged branches in distinct districts -------------
    besieged = (rivp or {}).get("besieged") or []
    if besieged:
        max_n2 = max(b.get("n2", 0) for b in besieged) or 1
        seen_d, picks = set(), []
        for b in besieged:                       # committed order: n2 desc, n5 desc, nd asc
            key = (b.get("prov"), b.get("district"))
            if key in seen_d:
                continue
            seen_d.add(key)
            picks.append(b)
            if len(picks) == 2:
                break
        picked_i = {b.get("i") for b in picks}
        for b in picks:
            items.append({
                "type": "defend",
                "act": ("Defend %s (%s · %s) — %d rival branches within 2 km of the door "
                        "(%d within 5 km); the nearest is %s at %s km. Review pricing and "
                        "LTV response on this street first."
                        % (b.get("name"), b.get("prov"), b.get("district"),
                           b.get("n2", 0), b.get("n5", 0), b.get("nb"), _num(b.get("nd"), 2))),
                "basis": "measured",
                "source": "rival_pressure.json",
                "go": "trend",
                "name": b.get("name"), "prov": b.get("prov"),
                "priority": round(TYPE_BASE["defend"] + 10.0 * b.get("n2", 0) / max_n2, 2),
            })
        used.append("rival_pressure.json — MEASURED rival counts/distances (merged competitor "
                    "census; Heng a sample, so counts are a lower bound)")

        # ---- DOUBLE JEOPARDY — the besieged branch whose BOOK is also most stressed --------
        # Cross-pillar synthesis (BOTH objectives at once): the pure-besieged rows above rank
        # by rival count alone and are blind to portfolio risk — so the #1 defended branch can
        # have a perfectly healthy book. Here we surface the branch that is besieged AND sits in
        # the network's top-quartile portfolio composite risk: rivals press price/LTV while the
        # book is already stressed. Pure JOIN of two committed labelled layers (rival_pressure
        # MEASURED + branch_risk ESTIMATED) — nothing new is estimated. Deterministic pick:
        # highest composite among the besieged, tie-break by committed besieged order (index asc);
        # skipped if already surfaced above, if no branch clears the top-quartile cut, or if the
        # branch_risk layer is absent.
        if rk_present and rk_p75 is not None:
            jp = None  # (composite, -besieged_index, branch, driver)
            for bi, b in enumerate(besieged):
                if b.get("i") in picked_i:
                    continue
                cr, td = _risk_at(b.get("i"))
                if cr is None or cr < rk_p75:
                    continue
                key = (cr, -bi)
                if jp is None or key > jp[0]:
                    jp = (key, b, cr, td)
            if jp is not None:
                _, b, cr, td = jp
                band = ("top-decile" if (rk_p90 is not None and cr >= rk_p90)
                        else "top-quartile")
                drv = DRIVER_LABEL.get(td, td or "mixed")
                items.append({
                    "type": "defend",
                    "act": ("Defend + watch %s (%s · %s) — DOUBLE JEOPARDY: %d rival branches "
                            "within 2 km of the door (measured; nearest %s at %s km) AND its book "
                            "screens %s for portfolio risk (composite %s/100, estimated; top "
                            "driver %s). Rivals pressure price/LTV while the book is already "
                            "stressed — review both here first."
                            % (b.get("name"), b.get("prov"), b.get("district"),
                               b.get("n2", 0), b.get("nb"), _num(b.get("nd"), 2),
                               band, _num(cr), drv)),
                    "basis": "measured",              # defend TRIGGER = measured rival siege;
                    "source": "rival_pressure.json + branch_risk.json",
                    "go": "trend",
                    "name": b.get("name"), "prov": b.get("prov"),
                    "jeopardy": True, "risk": cr, "top_driver": td,
                    "priority": round(JEOPARDY_BASE + 10.0 * (cr / rk_max if rk_max else 0.0), 2),
                })
                used.append("branch_risk.json — ESTIMATED composite portfolio risk (0-100), joined "
                            "by branch index to flag the besieged branch whose book is also "
                            "top-quartile-stressed (the estimated read is tagged inline, not "
                            "folded into the measured rival count)")

    # ---- AUDIT (ESTIMATED) — top-2 twin outliers in distinct provinces -----------------
    outliers = (peers or {}).get("outliers") or []
    if outliers:
        max_dev = max((o.get("dev") or 0) for o in outliers) or 1
        seen_p, picks = set(), []
        for o in outliers:                       # committed order: rz desc
            if o.get("prov") in seen_p:
                continue
            seen_p.add(o.get("prov"))
            picks.append(o)
            if len(picks) == 2:
                break
        k = ((peers or {}).get("meta", {}).get("params", {}) or {}).get("k", 15)
        for o in picks:
            items.append({
                "type": "audit",
                "act": ("Audit %s (%s) — risk proxy %s vs %s at its %d statistical twins "
                        "(+%s points, %sσ out of line; top driver: %s). Something local is "
                        "different from its market — send audit first."
                        % (o.get("name"), o.get("prov"), _num(o.get("risk")),
                           _num(o.get("peer_median")), k, _num(o.get("dev")),
                           _num(o.get("rz")), DRIVER_LABEL.get(o.get("top_driver"),
                                                               o.get("top_driver") or "mixed"))),
                "basis": "estimated",
                "source": "branch_peers.json",
                "go": "trend",
                "name": o.get("name"), "prov": o.get("prov"),
                "priority": round(TYPE_BASE["audit"] + 10.0 * (o.get("dev") or 0) / max_dev, 2),
            })
        used.append("branch_peers.json — ESTIMATED deviation of the estimated composite risk vs "
                    "twins matched on MEASURED market features (not a measured default rate)")

    # ---- TIGHTEN (ESTIMATED) — worst macro-headwind province ---------------------------
    mprov = (msens or {}).get("provinces") or []
    drivers = ((msens or {}).get("meta", {}) or {}).get("drivers", {}) or {}
    head = next((p for p in mprov if p.get("dir") == "h"), None)   # builder sorts headwinds first
    if head:
        drv = drivers.get(head.get("driver"), {}) or {}
        dlab = drv.get("label") or head.get("driver")
        detail = ""
        yoy = drv.get("yoy_pct")
        if yoy is not None:
            # macro_sensitivity stamps each price driver's basis: Thai farm-gate (MEASURED, primary)
            # or the World Bank GLOBAL Pink Sheet proxy (fallback). Label it honestly, not always "global".
            pbase = ("Thai farm-gate price" if drv.get("basis") == "farmgate" else "global price")
            pnote = ("measured" if drv.get("basis") == "farmgate" else "measured proxy")
            detail = " (%s %s%s%% YoY, %s)" % (pbase, "+" if yoy > 0 else "", _num(yoy), pnote)
        elif head.get("driver") == "drought" and crop:
            row = next((c for c in (crop.get("provinces") or []) if c.get("th") == head.get("th")), None)
            rain = (row or {}).get("components", {}).get("rain_pct_of_normal")
            if rain is not None:
                detail = " (rain at %s%% of normal, measured proxy)" % _num(rain)
        share = (head.get("hits", 0) / head.get("n")) if head.get("n") else 0.0
        items.append({
            "type": "tighten",
            "act": ("Tighten new-loan LTV in %s (%s) — %s is the top macro headwind for %d of the "
                    "province's %d branches%s."
                    % (head.get("th"), head.get("region"), dlab,
                       head.get("hits", 0), head.get("n", 0), detail)),
            "basis": "estimated",
            "source": "macro_sensitivity.json",
            "go": "overview",
            "name": head.get("th"), "prov": head.get("th"),
            "priority": round(TYPE_BASE["tighten"] + 10.0 * share, 2),
        })
        used.append("macro_sensitivity.json — ESTIMATED proxy over measured inputs (real global "
                    "price YoY × measured crop shares/rain, estimated relevance weights)")

    # ---- TIGHTEN/WATCH (ESTIMATED) — worst crop-household-stress province --------------
    cprov = (crop or {}).get("provinces") or []
    cw = next((c for c in cprov if c.get("th") not in {i.get("prov") for i in items}), None)
    if cw:
        mix = (cw.get("crop_mix") or [{}])[0]
        comps = cw.get("components", {}) or {}
        bits = []
        if comps.get("rain_pct_of_normal") is not None:
            bits.append("rain at %s%% of normal" % _num(comps["rain_pct_of_normal"]))
        if mix.get("crop") and mix.get("share") is not None:
            bits.append("%s is %d%% of planted area" % (mix["crop"], round(mix["share"] * 100)))
        if comps.get("n_branches"):
            bits.append("%d AutoX branches exposed" % comps["n_branches"])
        items.append({
            "type": "tighten",
            "act": ("Watch crop households in %s (%s) — agri-stress %d/100%s."
                    % (cw.get("th"), cw.get("region"),
                       round((cw.get("agri_stress") or 0) * 100),
                       (": " + ", ".join(bits)) if bits else "")),
            "basis": "estimated",
            "source": "crop_stress.json",
            "go": "overview",
            "name": cw.get("th"), "prov": cw.get("th"),
            "priority": round(TYPE_BASE["tighten"] + 10.0 * (cw.get("agri_stress") or 0), 2),
        })
        used.append("crop_stress.json — ESTIMATED stress (measured OAE crop areas + rainfall; "
                    "GLOBAL price direction proxy, not Thai farm-gate)")

    # NOTE — no EXPAND tier. AutoX is consolidating the network it already runs
    # (CLAUDE.md objective #2); the exec queue never recommends opening or scouting new
    # ground. opportunity_score.json / exit_whitespace.json are intentionally NOT read here.

    # ---- rank: priority desc, type asc, name asc (total, byte-stable order) ------------
    items.sort(key=lambda it: (-it["priority"], it["type"], it.get("name") or ""))
    for r, it in enumerate(items, 1):
        it["rank"] = r
        it["go_label"] = GO_LABEL[it["go"]]

    meta = {
        "generated_with": "pipeline/build_decision_queue.py",
        "label": ("EXEC DECISION QUEUE — ~6 ranked weekly actions SYNTHESIZED from existing "
                  "committed layers; every inline number is copied from the named source file. "
                  "Items are individually tagged measured/estimated (defend rows are MEASURED "
                  "geometry; audit/tighten rows are ESTIMATED screens). The ordering "
                  "itself is an editorial rule, stated in meta.ranking — not a measured urgency."),
        "objective": "Objective #2 scope — AutoX is CONSOLIDATING the ~2,015-branch network it "
                     "already runs; this queue is a defend/audit/tighten list on the existing book "
                     "and makes NO open / close / where-to-open recommendation.",
        "ranking": {
            "rule": "priority = BASE[type] + 10 x intensity (2 dp); sort priority desc, "
                    "type asc, name asc.",
            "type_base": {"double_jeopardy": 50, "defend": 40, "audit": 30, "tighten": 20},
            "type_base_note": "EDITORIAL precedence, stated openly: a DOUBLE-JEOPARDY branch "
                              "(besieged AND top-quartile portfolio risk) outranks a plain defend, "
                              "which outranks auditing, which outranks tightening. The "
                              "double-jeopardy row renders as a `defend` chip (its trigger is the "
                              "same measured rival siege) but carries a higher base so it leads the "
                              "group; its estimated portfolio-risk read is tagged inline.",
            "intensity": {
                "double_jeopardy": "composite_risk / max(composite_risk) over branch_risk.json "
                                   "(estimated portfolio risk of the besieged branch)",
                "defend": "n2 / max(n2) over the shipped besieged list (measured rivals <=2 km)",
                "audit": "dev / max(dev) over the shipped outlier list (risk-proxy points above twins)",
                "tighten": "macro: hits/n (share of province branches led by the headwind); "
                           "crop: agri_stress (already 0..1)",
            },
            "double_jeopardy": "The single besieged branch (rival_pressure.json, MEASURED) whose "
                               "portfolio composite risk (branch_risk.json, ESTIMATED) is highest "
                               "and clears the network top-quartile cut — the intersection of the "
                               "two objectives. Pure index-join of two committed labelled layers; "
                               "nothing new is estimated. Emitted only when a distinct such branch "
                               "exists and branch_risk.json is present.",
            "dedupe": "defend: distinct districts; audit: distinct provinces; crop-watch skips a "
                      "province already queued; double-jeopardy skips a branch already picked above.",
            "deterministic": "no wall clock, no randomness — same inputs give the same bytes.",
        },
        "inputs_used": used,
        "types": {"defend": "hold share where rivals crowd our door",
                  "double_jeopardy": "a defend row flagged jeopardy=true — besieged AND "
                                     "top-quartile portfolio risk (both objectives at once)",
                  "audit": "branch out of line vs its statistical twins",
                  "tighten": "risk headwind — tighten LTV / watch the segment"},
        "n_items": len(items),
    }
    if not items:
        meta["absent"] = True
        meta["note"] = ("No source layers present — run the build_* scripts listed in "
                        "inputs_used, then rerun build_decision_queue.py.")
    return {"meta": meta, "items": items}


def run(check=False):
    obj = build()
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if check:
        if not os.path.exists(OUT) or open(OUT, encoding="utf-8").read() != text:
            print(f"DRIFT: {os.path.relpath(OUT, REPO)}")
            return 1
        print(f"OK: decision_queue.json reproduces ({obj['meta']['n_items']} items)")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {obj['meta']['n_items']} actions -> platform/data/decision_queue.json "
          f"({len(text)/1024:.1f} KB)")
    for it in obj["items"]:
        print(f"  {it['rank']}. [{it['type']}] ({it['priority']}) {it['act'][:110]}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="exec decision queue for the Command Center (#home)")
    ap.add_argument("--check", action="store_true")
    raise SystemExit(run(check=ap.parse_args().check))
