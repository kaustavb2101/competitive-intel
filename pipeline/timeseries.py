#!/usr/bin/env python3
"""
timeseries.py — the time dimension (Phase 3): snapshots + deltas
================================================================
The #1 gap was "which segments / branches are getting RISKIER" — that needs a
second point in time. This script captures a deterministic SNAPSHOT of the key
measured / proxy fields for the current data vintage, then diffs it against the
prior snapshot into the files the app's "Risk trend" tab reads.

It is deliberately built so it WORKS with one vintage today (writes a baseline,
the app says "baseline captured") and LIGHTS UP automatically on the next data
refresh (a second snapshot appears, deltas.json fills in).

    python3 timeseries.py            # capture snapshot for the current vintage + rebuild deltas
    python3 timeseries.py --check    # verify committed snapshot + deltas reproduce exactly

DETERMINISM (sacred):
  - the snapshot LABEL is derived from meta.updated (the data vintage), NEVER the
    wall clock — so re-running --check is byte-exact.
  - a snapshot file is only (re)written if its content changes; an existing label
    is never silently mutated by a new run with the same vintage.
  - snapshots_index.json + deltas.json are pure functions of source-data/snapshots/*.

What a snapshot captures (per vintage):
  meta            label, vintage token, the editorial 'updated' string
  board           commodity-board YoY by item (measured/editorial price direction)
  region          per-region mean agri-PD / merchant / collateral proxies + counts
  branches        per-branch a/m/c proxies, keyed by a stable id (code|name|prov)

deltas.json (vs the immediately-prior snapshot, by index order):
  baseline:true when only one snapshot exists (no movers yet)
  region movers, board YoY movers, and the biggest per-branch risk movers
"""
import os, sys, json, re, argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
SRC  = os.path.join(REPO, "source-data")
SNAPDIR = os.path.join(SRC, "snapshots")
OUT  = os.path.join(REPO, "platform", "data")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def vintage_token(updated):
    """Stable vintage label from meta.updated (NEVER wall-clock). Prefer the price
    vintage token YYYY'M'MM (the commodity-board vintage that drives the trend),
    else the first ISO date, else a slug of the whole string."""
    s = updated or "baseline"
    m = re.search(r"(\d{4})M(\d{2})", s)
    if m:
        return m.group(0)
    d = re.search(r"\d{4}-\d{2}-\d{2}", s)
    if d:
        return d.group(0)
    return re.sub(r"[^0-9A-Za-z]+", "-", s).strip("-").lower() or "baseline"


def branch_key(b):
    """Stable per-branch id. code is not unique (2 dupes in the master), so fold in
    name+prov to disambiguate; this id only has to be stable across vintages."""
    return f"{b.get('code','')}|{b['name']}|{b['prov']}"


def round1(x):
    return round(float(x), 1)


def build_snapshot(master, meta):
    """The deterministic per-vintage snapshot object."""
    label = vintage_token(meta.get("updated"))

    # region rollups — mean of the three proxies + branch count (matches meta.region)
    by_region = {}
    for b in master:
        by_region.setdefault(b["region"], []).append(b)
    region = []
    for r in meta["region"]:           # preserve the meta region order
        rows = by_region.get(r["r"], [])
        n = max(1, len(rows))
        region.append({
            "r": r["r"], "n": len(rows),
            "agri": round1(sum(x["agri_pd"] for x in rows) / n),
            "md":   round1(sum(x["merchant_demand"] for x in rows) / n),
            "col":  round1(sum(x["collateral_density"] for x in rows) / n),
        })

    # commodity board YoY by item (editorial/measured price direction)
    board = [{"lab": b["lab"], "yoy": b.get("yoy"), "seg": b.get("seg"),
              "cls": b.get("cls")} for b in meta.get("board", [])]

    # per-branch proxies, keyed stably; kept compact + sorted by key for determinism
    branches = {}
    for b in master:
        branches[branch_key(b)] = {
            "n": b["name"], "v": b["prov"], "r": b["region"],
            "a": b["agri_pd"], "m": b["merchant_demand"], "c": b["collateral_density"],
        }
    branches = {k: branches[k] for k in sorted(branches)}

    return {"meta": {"label": label, "vintage": label, "updated": meta.get("updated", "")},
            "board": board, "region": region, "branches": branches}


def snapshot_json(snap):
    """Canonical serialization (sorted keys → byte-stable regardless of dict order)."""
    return json.dumps(snap, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def list_snapshots():
    """All committed snapshots, ordered by their meta.label (vintage). Vintage tokens
    sort chronologically as strings (YYYY'M'MM, ISO dates), giving a stable order."""
    if not os.path.isdir(SNAPDIR):
        return []
    snaps = []
    for fn in os.listdir(SNAPDIR):
        if fn.endswith(".json"):
            snaps.append(_load(os.path.join(SNAPDIR, fn)))
    snaps.sort(key=lambda s: s["meta"]["label"])
    return snaps


def build_index(snaps):
    return {"snapshots": [{"label": s["meta"]["label"], "updated": s["meta"].get("updated", "")}
                          for s in snaps],
            "count": len(snaps)}


def build_deltas(snaps):
    """Diff the latest snapshot vs the immediately-prior one. With <2 snapshots this
    is a labelled baseline (the app shows the 'baseline captured' message)."""
    if not snaps:
        return {"baseline": True, "count": 0,
                "from": None, "to": None,
                "region": [], "board": [], "branches": []}
    cur = snaps[-1]
    if len(snaps) < 2:
        return {"baseline": True, "count": 1,
                "from": None, "to": cur["meta"]["label"],
                "updated_to": cur["meta"].get("updated", ""),
                "region": [], "board": [], "branches": []}
    prev = snaps[-2]

    # region movers: delta of each proxy mean, per region
    prev_reg = {r["r"]: r for r in prev["region"]}
    region = []
    for r in cur["region"]:
        p = prev_reg.get(r["r"])
        if not p:
            continue
        region.append({
            "r": r["r"], "n": r["n"],
            "agri": r["agri"], "d_agri": round1(r["agri"] - p["agri"]),
            "md": r["md"],     "d_md":   round1(r["md"]   - p["md"]),
            "col": r["col"],   "d_col":  round1(r["col"]  - p["col"]),
        })

    # board YoY movers: change in the YoY figure itself (a price re-rating)
    prev_board = {b["lab"]: b for b in prev["board"]}
    board = []
    for b in cur["board"]:
        p = prev_board.get(b["lab"])
        cy, py = b.get("yoy"), (p or {}).get("yoy")
        d = round1(cy - py) if (cy is not None and py is not None) else None
        board.append({"lab": b["lab"], "seg": b.get("seg"), "cls": b.get("cls"),
                      "yoy": cy, "prev_yoy": py, "d_yoy": d})

    # per-branch risk movers: change in the composite (worst of a/m/c) + each leg
    prev_br = prev["branches"]
    branches = []
    for k, c in cur["branches"].items():
        p = prev_br.get(k)
        if not p:
            continue
        comp_c = max(c["a"], c["m"], c["c"])
        comp_p = max(p["a"], p["m"], p["c"])
        branches.append({
            "n": c["n"], "v": c["v"], "r": c["r"],
            "comp": comp_c, "d_comp": round1(comp_c - comp_p),
            "d_a": round1(c["a"] - p["a"]),
            "d_m": round1(c["m"] - p["m"]),
            "d_c": round1(c["c"] - p["c"]),
        })
    # biggest absolute movers first; deterministic tiebreak on name
    branches.sort(key=lambda x: (-abs(x["d_comp"]), x["n"]))
    branches = branches[:80]

    return {"baseline": False, "count": len(snaps),
            "from": prev["meta"]["label"], "to": cur["meta"]["label"],
            "updated_from": prev["meta"].get("updated", ""),
            "updated_to": cur["meta"].get("updated", ""),
            "region": region, "board": board, "branches": branches}


# Self-declared provenance stamps so these two derived files leave the provenance "shame board"
# (build_provenance.py reads meta.label/source/provenance/generated_by). Deterministic literals —
# they add no data, only a provenance header, so --check stays byte-exact once regenerated.
INDEX_META = {
    "label": "Index of captured data-vintage snapshots (label + updated) that back the Risk-trend deltas.",
    "generated_by": "pipeline/timeseries.py (build_index) — deterministic, network-free, --check-reproducible",
    "source": "source-data/snapshots/*.json (one per captured vintage).",
    "provenance": "MEASURED — a listing of committed snapshot files; carries no computed risk/market number.",
}
DELTAS_META = {
    "label": ("Time-dimension snapshot diff (Risk-trend tab): region proxy movers, commodity-board YoY "
              "re-ratings, and the top per-branch composite movers between two committed data vintages."),
    "generated_by": "pipeline/timeseries.py (build_deltas) — deterministic, network-free, --check-reproducible",
    "source": "Diff of two committed source-data/snapshots/*.json vintages (by index order).",
    "provenance": ("ESTIMATED — region/branch movers are proxy-score deltas; the commodity board is "
                   "measured/editorial price direction. Not a measured default/loss delta."),
}


def targets():
    """(path, canonical-text) for the two derived platform files, given committed snapshots."""
    snaps = list_snapshots()
    idx = build_index(snaps)
    idx["meta"] = INDEX_META
    deltas = build_deltas(snaps)
    # vintage of the diff = the "to" snapshot's updated stamp (blank on the baseline path)
    deltas["meta"] = {**DELTAS_META, "updated": deltas.get("updated_to", "")}
    return [
        (os.path.join(OUT, "snapshots_index.json"),
         json.dumps(idx, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
        (os.path.join(OUT, "deltas.json"),
         json.dumps(deltas, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
    ]


def run(check=False):
    master = _load(os.path.join(SRC, "branches_final.json"))
    meta = _load(os.path.join(OUT, "meta.json"))
    snap = build_snapshot(master, meta)
    snap_text = snapshot_json(snap)
    snap_path = os.path.join(SNAPDIR, snap["meta"]["label"] + ".json")

    if check:
        drift = False
        # 1) the current-vintage snapshot must already be committed + byte-exact
        if not os.path.exists(snap_path):
            print(f"DRIFT: snapshot for vintage {snap['meta']['label']} is missing "
                  f"({os.path.relpath(snap_path, REPO)}) — run timeseries.py")
            drift = True
        else:
            with open(snap_path, encoding="utf-8") as f:
                if f.read() != snap_text:
                    print(f"DRIFT: {os.path.relpath(snap_path, REPO)} differs from a fresh snapshot")
                    drift = True
        # 2) the derived index + deltas must reproduce from committed snapshots
        for path, text in targets():
            with open(path, encoding="utf-8") as f:
                if f.read() != text:
                    print(f"DRIFT: {os.path.relpath(path, REPO)} differs from a fresh build")
                    drift = True
        if drift:
            return 1
        print("OK: snapshot + snapshots_index.json + deltas.json reproduce exactly")
        return 0

    # write/refresh the current-vintage snapshot (only when content changes)
    os.makedirs(SNAPDIR, exist_ok=True)
    wrote = False
    if not os.path.exists(snap_path) or open(snap_path, encoding="utf-8").read() != snap_text:
        with open(snap_path, "w", encoding="utf-8") as f:
            f.write(snap_text)
        wrote = True
    # rebuild derived files from the full (now updated) snapshot set
    for path, text in targets():
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    n = len(list_snapshots())
    print(f"snapshot vintage {snap['meta']['label']} {'written' if wrote else 'unchanged'}; "
          f"{n} snapshot(s) total → deltas.json {'(baseline)' if n < 2 else '(trends live)'}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="capture data snapshot + build deltas (time dimension)")
    ap.add_argument("--check", action="store_true",
                    help="verify committed snapshot + deltas reproduce exactly; exit 1 on drift")
    raise SystemExit(run(check=ap.parse_args().check))
