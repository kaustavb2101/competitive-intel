#!/usr/bin/env python3
"""
build_decision_queue.py — EXEC DECISION QUEUE for the Command Center (#home)
=============================================================================
Synthesizes ~8 concrete recommended actions — "This week — do these first" —
from EXISTING committed layers ONLY. Nothing is measured or estimated here that
was not already measured or estimated upstream; this script only SELECTS and
PHRASES, and every number in every sentence is copied verbatim (or rounded,
stated below) from the named source file.

Inputs (all under platform/data/, all committed, all optional — a missing layer
just contributes no items):
  rival_pressure.json    -> DEFEND  : the most besieged branches (MEASURED geometry)
  branch_peers.json      -> AUDIT   : branches out of line vs statistical twins (ESTIMATED)
  macro_sensitivity.json -> TIGHTEN : the worst macro-headwind province (ESTIMATED proxy)
  crop_stress.json       -> TIGHTEN : the worst crop-household-stress province (ESTIMATED)
  opportunity_score.json -> EXPAND  : the top expansion district (ESTIMATED composite)
  exit_whitespace.json   -> EXPAND  : the top competitor-exit capture district (ESTIMATED PROXY)

Output: platform/data/decision_queue.json
  { meta: {... full provenance + the ranking rule below ...},
    items: [{rank, type, act, basis, source, go, go_label, name, prov, priority} x ~8] }

DETERMINISTIC RANKING (no wall clock, no randomness — documented here and in meta):
  priority = TYPE_BASE[type] + 10 * intensity          (rounded to 2 dp)
  TYPE_BASE — an EDITORIAL precedence, stated openly: defending and auditing the
  existing book outranks growth actions in a weekly queue:
      defend = 40   audit = 30   tighten = 20   expand = 10
  intensity in [0, 1] — the layer's own native magnitude, normalized WITHIN its layer
  (cross-layer scores are not commensurable, so we never pretend they are):
      defend  : n2 / max(n2 over the shipped besieged list)     (measured rival count <=2 km)
      audit   : dev / max(dev over the shipped outlier list)    (risk-proxy points above twins)
      tighten : macro   -> hits / n  (share of the province's branches led by the headwind)
                crop    -> agri_stress (already 0..1)
      expand  : opportunity -> score / 100 ; exit -> exit_capture_score / 100
  Sort: priority desc, then type asc, then name asc (total order — byte-stable).
  Candidate picks are deterministic too: each source list is used in its committed
  sort order; DEFEND picks the top 2 besieged branches in DISTINCT districts and
  AUDIT the top 2 outliers in DISTINCT provinces (so the queue is not two rows of
  the same market); the EXIT pick skips a district already taken by the
  opportunity pick (no duplicate recommendation).

Deterministic + network-free. Pure stdlib.
    python3 build_decision_queue.py            # write the JSON
    python3 build_decision_queue.py --check    # verify byte-for-byte reproduce
"""
import argparse, json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
OUT  = os.path.join(DATA, "decision_queue.json")

TYPE_BASE = {"defend": 40.0, "audit": 30.0, "tighten": 20.0, "expand": 10.0}
GO_LABEL  = {"trend": "Risk trend →", "overview": "Overview →", "acq": "Acquisition →"}
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
    opp   = _load("opportunity_score.json")
    exitw = _load("exit_whitespace.json")

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
            detail = " (global price %s%s%% YoY, measured proxy)" % ("+" if yoy > 0 else "", _num(yoy))
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

    # ---- EXPAND (ESTIMATED) — top opportunity district ---------------------------------
    odist = (opp or {}).get("districts") or []
    opick = odist[0] if odist else None          # committed order: score desc
    if opick:
        c = opick.get("components", {}) or {}
        rival_bit = ""
        if c.get("_competitors") is not None:
            rival_bit = " vs %d big-4 rival branches in-district (measured)" % c["_competitors"]
        items.append({
            "type": "expand",
            # NOT "Open next" — that verdict belongs to the sequenced Road-to-3,000 plan
            # (committee finding #2, 2026-07-10). This is the composite LENS's top district.
            "act": ("Scout %s (%s) — highest composite opportunity %s/100: white-space %s, %d AutoX "
                    "branch%s today%s. Placement ORDER comes from the sequenced plan."
                    % (opick.get("name"), opick.get("province"), _num(opick.get("score")),
                       _num(c.get("whitespace")), opick.get("branches", 0),
                       "" if opick.get("branches") == 1 else "es", rival_bit)),
            "basis": "estimated",
            "source": "opportunity_score.json",
            "go": "acq",
            "name": opick.get("name"), "prov": opick.get("province"),
            "priority": round(TYPE_BASE["expand"] + 10.0 * (opick.get("score") or 0) / 100.0, 2),
        })
        used.append("opportunity_score.json — ESTIMATED composite (measured white-space + rival "
                    "density blended with estimated crop stress)")

    # ---- EXPAND/SCOUT (ESTIMATED PROXY) — top exit-capture district (no duplicate) -----
    edist = (exitw or {}).get("districts") or []
    epick = next((e for e in edist if not (opick and e.get("id") == opick.get("id"))), None)
    if epick:
        c = epick.get("components", {}) or {}
        big4 = c.get("big4_competitors")
        items.append({
            "type": "expand",
            "act": ("Scout %s (%s) — exit-capture %s/100 if sub-scale lenders exit at the "
                    "Q1-2026 BoT registration deadline%s. Inferred cue, not a census — "
                    "verify on the ground."
                    % (epick.get("name"), epick.get("province"),
                       _num(epick.get("exit_capture_score")),
                       (" (%d big-4 rivals present today, measured)" % big4)
                       if big4 is not None else "")),
            "basis": "estimated",
            "source": "exit_whitespace.json",
            "go": "acq",
            "name": epick.get("name"), "prov": epick.get("province"),
            "priority": round(TYPE_BASE["expand"]
                              + 10.0 * (epick.get("exit_capture_score") or 0) / 100.0, 2),
        })
        used.append("exit_whitespace.json — ESTIMATED PROXY (big-4 scarcity × demand; sub-scale "
                    "operators are NOT censused)")

    # ---- rank: priority desc, type asc, name asc (total, byte-stable order) ------------
    items.sort(key=lambda it: (-it["priority"], it["type"], it.get("name") or ""))
    for r, it in enumerate(items, 1):
        it["rank"] = r
        it["go_label"] = GO_LABEL[it["go"]]

    meta = {
        "generated_with": "pipeline/build_decision_queue.py",
        "label": ("EXEC DECISION QUEUE — ~8 ranked weekly actions SYNTHESIZED from existing "
                  "committed layers; every inline number is copied from the named source file. "
                  "Items are individually tagged measured/estimated (defend rows are MEASURED "
                  "geometry; audit/tighten/expand rows are ESTIMATED screens). The ordering "
                  "itself is an editorial rule, stated in meta.ranking — not a measured urgency."),
        "objective": "Both objectives on one list: #1 defend/audit/tighten the existing book, "
                     "#2 expand/scout where the ground is open.",
        "ranking": {
            "rule": "priority = TYPE_BASE[type] + 10 x intensity (2 dp); sort priority desc, "
                    "type asc, name asc.",
            "type_base": {"defend": 40, "audit": 30, "tighten": 20, "expand": 10},
            "type_base_note": "EDITORIAL precedence, stated openly: defending and auditing the "
                              "existing book outranks growth actions in a weekly queue.",
            "intensity": {
                "defend": "n2 / max(n2) over the shipped besieged list (measured rivals <=2 km)",
                "audit": "dev / max(dev) over the shipped outlier list (risk-proxy points above twins)",
                "tighten": "macro: hits/n (share of province branches led by the headwind); "
                           "crop: agri_stress (already 0..1)",
                "expand": "opportunity: score/100; exit: exit_capture_score/100",
            },
            "dedupe": "defend: distinct districts; audit: distinct provinces; crop-watch skips a "
                      "province already queued; exit pick skips the opportunity district.",
            "deterministic": "no wall clock, no randomness — same inputs give the same bytes.",
        },
        "inputs_used": used,
        "types": {"defend": "hold share where rivals crowd our door",
                  "audit": "branch out of line vs its statistical twins",
                  "tighten": "risk headwind — tighten LTV / watch the segment",
                  "expand": "open or scout new ground"},
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
