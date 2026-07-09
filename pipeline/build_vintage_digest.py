#!/usr/bin/env python3
"""
build_vintage_digest.py — plain-language "what changed since the last data vintage"
====================================================================================
Exec digest for the TOP of the Risk-trend tab (objective #1: what's getting riskier).
Turns the machine-shaped snapshot diff (platform/data/deltas.json, built by
timeseries.py) into ONE headline + 4-8 one-sentence findings in exec language,
each tagged better / worse / neutral, ordered worst-first.

    python3 build_vintage_digest.py           # rebuild platform/data/vintage_digest.json
    python3 build_vintage_digest.py --check   # verify the committed file reproduces byte-exact

HONESTY RULES (sacred):
  - EVERY number in every sentence is read verbatim from deltas.json (which itself
    diffs two committed snapshots). NOTHING is invented — the wording only adds
    direction/magnitude phrasing ("swung", "cooled", "eased") to the deltas.
  - Region/branch proxies are ESTIMATED (OSM/price-based 0-100); the commodity
    board is measured/editorial World Bank price direction. meta says so.
  - Vintage labels come from the snapshot metadata (deltas.from / deltas.to),
    NEVER the wall clock — --check is byte-exact.
  - With 0 or 1 snapshots (deltas.baseline true) the digest is a calm
    "first vintage — no comparison yet" payload, findings = [].

Deterministic + network-free. Pure function of deltas.json + snapshots_index.json.
"""
import os, json, argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
OUT  = os.path.join(REPO, "platform", "data")
DELTAS_PATH = os.path.join(OUT, "deltas.json")
INDEX_PATH  = os.path.join(OUT, "snapshots_index.json")
OUT_PATH    = os.path.join(OUT, "vintage_digest.json")

TONE_RANK = {"worse": 0, "neutral": 1, "better": 2}

# thresholds (stated rules, not data): a board YoY re-rating is a "mover" at ±5 pts;
# a region proxy leg moved at ±1 pt; a branch composite rose at ≥+1 pt.
BOARD_MOVE = 5.0
REGION_MOVE = 1.0
BRANCH_RISE = 1.0
MAX_FINDINGS = 8

# how a commodity segment reads for the borrower book (used in sentences only)
SEG_PHRASE = {
    "Crops":     "crop-borrower price backdrop",
    "Livestock": "livestock-borrower price backdrop",
    "Fisheries": "fisheries-borrower price backdrop",
    "Forestry":  "forestry-borrower price backdrop",
    "Collateral": "gold-collateral price tailwind",
}

LEG_NAME = {"agri": "agri-PD", "md": "merchant-demand", "col": "collateral-density"}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def num(v):
    """Compact deterministic number: 17.9 -> '17.9', -36.0 -> '-36', 0.0 -> '0'."""
    s = "%.1f" % float(v)
    if s.endswith(".0"):
        s = s[:-2]
    if s == "-0":
        s = "0"
    return s


def sgn(v):
    """Signed compact number: +17.9 / -36 / 0."""
    return ("+" if float(v) > 0 else "") + num(v)


def F(tone, metric, mag, text, short):
    return {"tone": tone, "metric": metric, "mag": round(abs(float(mag)), 1),
            "text": text, "short": short}


def board_findings(board):
    """Findings from the commodity-board YoY re-rating (measured/editorial direction)."""
    movers = [b for b in board if b.get("d_yoy") is not None]
    worse, swung_pos, moderating, accelerating = [], [], [], []
    for b in sorted(movers, key=lambda x: (x["d_yoy"], x["lab"])):
        d, yoy, prev, lab = b["d_yoy"], b["yoy"], b["prev_yoy"], b["lab"]
        seg = SEG_PHRASE.get(b.get("seg") or "", "price backdrop for that segment")
        if d <= -BOARD_MOVE:
            if yoy > 0.05:
                txt = (f"{lab} is still up {num(yoy)}% year-on-year, but momentum cooled from "
                       f"{sgn(prev)}% — a {sgn(d)}-point re-rating of the {seg}.")
            elif yoy < -0.05 and prev > 0.05:
                txt = (f"{lab} swung from {sgn(prev)}% to {sgn(yoy)}% year-on-year "
                       f"({sgn(d)} pts) — the {seg} turned negative.")
            else:
                txt = (f"{lab} momentum faded: {sgn(yoy)}% year-on-year vs {sgn(prev)}% "
                       f"last vintage ({sgn(d)} pts).")
            worse.append(F("worse", f"board:{lab}", d, txt,
                           f"{lab} price momentum {sgn(d)} pts YoY"))
        elif d >= BOARD_MOVE:
            if prev < -0.05 and yoy > 0.05:
                swung_pos.append(b)          # fell last vintage, rising now
            elif yoy < -0.05:
                moderating.append(b)         # still falling, but less steeply
            else:
                accelerating.append(b)       # was rising, rising faster
    worse.sort(key=lambda f: (-f["mag"], f["metric"]))

    grouped_better = []
    if swung_pos:
        swung_pos.sort(key=lambda b: (-b["d_yoy"], b["lab"]))
        top = swung_pos[:3]
        parts = [f"{b['lab']} ({sgn(b['d_yoy'])} pts to {sgn(b['yoy'])}% YoY)" for b in top]
        if len(parts) == 1:
            joined = parts[0]
        else:
            joined = ", ".join(parts[:-1]) + " and " + parts[-1]
        labs = ", ".join(b["lab"] for b in top)
        grouped_better.append(F(
            "better", "board:" + "+".join(b["lab"] for b in top), top[0]["d_yoy"],
            f"{joined} swung from falling to rising prices — the income backdrop for "
            f"those borrower segments improved.",
            f"{labs} prices swung positive"))

    neutral = []
    for b in sorted(moderating, key=lambda x: (-x["d_yoy"], x["lab"]))[:1]:
        neutral.append(F(
            "neutral", f"board:{b['lab']}", b["d_yoy"],
            f"{b['lab']} is still down {num(-b['yoy'])}% year-on-year, though the fall "
            f"moderated from {sgn(b['prev_yoy'])}% ({sgn(b['d_yoy'])} pts).",
            f"{b['lab']} still falling, less steeply"))

    accel = []
    for b in sorted(accelerating, key=lambda x: (-x["d_yoy"], x["lab"]))[:1]:
        accel.append(F(
            "better", f"board:{b['lab']}", b["d_yoy"],
            f"{b['lab']} accelerated to {sgn(b['yoy'])}% year-on-year from "
            f"{sgn(b['prev_yoy'])}% ({sgn(b['d_yoy'])} pts).",
            f"{b['lab']} price gains accelerated"))
    return worse, grouped_better, neutral, accel


def region_findings(region):
    """Aggregate per-leg findings over the region proxy deltas (ESTIMATED)."""
    worse, better, flat_legs = [], [], []
    for leg in ("agri", "md", "col"):
        rows = [r for r in region if r.get("d_" + leg) is not None]
        if not rows:
            continue
        name = LEG_NAME[leg]
        risers = [r for r in rows if r["d_" + leg] >= REGION_MOVE]
        easers = [r for r in rows if r["d_" + leg] <= -REGION_MOVE]
        if risers:
            risers.sort(key=lambda r: (-r["d_" + leg], r["r"]))
            w = risers[0]
            worse.append(F(
                "worse", f"region:{leg}", w["d_" + leg],
                f"The estimated {name} proxy rose in {len(risers)} of {len(rows)} regions — "
                f"worst {w['r']}, {sgn(w['d_' + leg])} pts to {num(w[leg])} "
                f"({w['n']} branches).",
                f"{name} proxy up in {len(risers)} region(s)"))
        elif len(easers) == len(rows):
            easers.sort(key=lambda r: (r["d_" + leg], r["r"]))
            a, b = easers[0], easers[1] if len(easers) > 1 else None
            lead = (f"{a['r']} {sgn(a['d_' + leg])} pts to {num(a[leg])}"
                    + (f" and {b['r']} {sgn(b['d_' + leg])} pts to {num(b[leg])}" if b else ""))
            better.append(F(
                "better", f"region:{leg}", a["d_" + leg],
                f"The estimated {name} proxy eased in all {len(rows)} regions, led by "
                f"{lead}.",
                f"{name} proxy down in all {len(rows)} regions"))
        else:
            flat_legs.append((leg, max(abs(r["d_" + leg]) for r in rows)))
    neutral = []
    if flat_legs:
        names = " and ".join(LEG_NAME[l] for l, _ in flat_legs)
        mx = max(m for _, m in flat_legs)
        neutral.append(F(
            "neutral", "region:" + "+".join(l for l, _ in flat_legs), mx,
            f"The estimated {names} prox{'ies were' if len(flat_legs) > 1 else 'y was'} "
            f"flat in every region (largest move {num(mx)} pt).",
            f"{names} flat"))
    return worse, better, neutral


def branch_finding(branches):
    """One finding over the top branch composite movers carried in deltas.json."""
    if not branches:
        return None
    n = len(branches)
    risers = [b for b in branches if b["d_comp"] >= BRANCH_RISE]
    top = branches[0]  # deltas.json is already sorted by |d_comp| desc
    if risers:
        risers.sort(key=lambda b: (-b["d_comp"], b["n"]))
        w = risers[0]
        return F("worse", "branches:top_movers", w["d_comp"],
                 f"{len(risers)} of the {n} biggest branch movers got riskier — worst "
                 f"{w['n']} ({w['v']}), {sgn(w['d_comp'])} pts to a composite of {num(w['comp'])}.",
                 f"{len(risers)} of {n} top branch movers riskier")
    return F("better", "branches:top_movers", top["d_comp"],
             f"None of the {n} biggest branch movers got riskier — every one eased, led by "
             f"{top['n']} ({top['v']}) at {sgn(top['d_comp'])} pts (composite now {num(top['comp'])}).",
             f"all {n} top branch movers eased")


def build_headline(frm, findings, nw, nn, nb):
    worse = [f for f in findings if f["tone"] == "worse"]
    better = [f for f in findings if f["tone"] == "better"]
    if not worse:
        lead = better[0]["short"] if better else "no material movement"
        return (f"Since {frm}: nothing moved toward higher risk — {nb} signal"
                f"{'s' if nb != 1 else ''} improved (led by {lead}), {nn} flat.")
    if not better:
        return (f"Since {frm}: {nw} signal{'s' if nw != 1 else ''} deteriorated, led by "
                f"{worse[0]['short']}; {nn} flat.")
    return (f"Since {frm}: {nb} signal{'s' if nb != 1 else ''} improved and {nw} "
            f"deteriorated — biggest deterioration: {worse[0]['short']}; biggest "
            f"improvement: {better[0]['short']}.")


def build_digest(deltas, index):
    meta = {
        "generated_by": "pipeline/build_vintage_digest.py (deterministic, network-free, --check)",
        "source": ("Digest of platform/data/deltas.json — the diff of two committed data-vintage "
                   "snapshots built by pipeline/timeseries.py. Every figure in every sentence is "
                   "read from deltas.json; the wording adds direction/magnitude phrasing only."),
        "inputs_used": ["platform/data/deltas.json", "platform/data/snapshots_index.json"],
        "provenance_note": ("Region and branch figures are ESTIMATED proxies (OSM/price-based, "
                            "0-100), not measured defaults. The commodity board is "
                            "measured/editorial World Bank price direction. Vintage labels come "
                            "from snapshot metadata, never the wall clock."),
    }
    count = int((index or {}).get("count", deltas.get("count", 0)) or 0)

    if deltas.get("baseline") or count < 2:
        to = deltas.get("to")
        if to:
            headline = (f"First data vintage ({to}) captured — no earlier vintage to compare "
                        f"against yet; this digest lights up at the next data refresh.")
        else:
            headline = ("No data vintage captured yet — run pipeline/timeseries.py to snapshot "
                        "the first one; this digest lights up once two vintages exist.")
        return {"baseline": True, "count": count, "from": None, "to": to,
                "updated_to": deltas.get("updated_to", ""),
                "headline": headline, "findings": [],
                "n_worse": 0, "n_neutral": 0, "n_better": 0, "meta": meta}

    b_worse, b_swung, b_mod, b_accel = board_findings(deltas.get("board", []))
    r_worse, r_better, r_flat = region_findings(deltas.get("region", []))
    br = branch_finding(deltas.get("branches", []))
    br_worse = [br] if br and br["tone"] == "worse" else []
    br_better = [br] if br and br["tone"] == "better" else []

    # priority order (worst themes first), then cap at MAX_FINDINGS
    candidates = (b_worse[:3] + r_worse + br_worse
                  + b_swung + r_better + br_better
                  + b_mod + r_flat + b_accel)
    findings = candidates[:MAX_FINDINGS]
    # display order: worst-first, then biggest magnitude, then stable metric key
    findings.sort(key=lambda f: (TONE_RANK[f["tone"]], -f["mag"], f["metric"]))

    nw = sum(1 for f in findings if f["tone"] == "worse")
    nn = sum(1 for f in findings if f["tone"] == "neutral")
    nb = sum(1 for f in findings if f["tone"] == "better")
    frm, to = deltas["from"], deltas["to"]
    return {"baseline": False, "count": count, "from": frm, "to": to,
            "updated_from": deltas.get("updated_from", ""),
            "updated_to": deltas.get("updated_to", ""),
            "headline": build_headline(frm, findings, nw, nn, nb),
            "findings": findings,
            "n_worse": nw, "n_neutral": nn, "n_better": nb, "meta": meta}


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def run(check=False):
    deltas = _load(DELTAS_PATH) if os.path.exists(DELTAS_PATH) else {"baseline": True, "count": 0}
    index = _load(INDEX_PATH) if os.path.exists(INDEX_PATH) else None
    text = canonical(build_digest(deltas, index))

    if check:
        if not os.path.exists(OUT_PATH):
            print(f"DRIFT: {os.path.relpath(OUT_PATH, REPO)} missing — run build_vintage_digest.py")
            return 1
        with open(OUT_PATH, encoding="utf-8") as f:
            if f.read() != text:
                print(f"DRIFT: {os.path.relpath(OUT_PATH, REPO)} differs from a fresh build")
                return 1
        print("OK: vintage_digest.json reproduces exactly")
        return 0

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    d = json.loads(text)
    print(f"vintage_digest.json written — baseline={d['baseline']} "
          f"{d.get('from')}→{d.get('to')} · {len(d['findings'])} findings "
          f"({d['n_worse']} worse / {d['n_neutral']} neutral / {d['n_better']} better)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="plain-language since-last-vintage digest for #trend")
    ap.add_argument("--check", action="store_true",
                    help="verify committed vintage_digest.json reproduces exactly; exit 1 on drift")
    raise SystemExit(run(check=ap.parse_args().check))
