"""Orchestrator (Chair) — runs ONE gated committee cycle and updates the scorecard + log.
Recursive by design: call with --loop to keep going while the accept-rate stays healthy.

    python3 run_cycle.py --member geocoder --batch 50
    python3 run_cycle.py --member geocoder --batch 50 --loop --max-cycles 20

Flow: member produces candidates -> validator gates -> accepted patches merged into master
-> SCORECARD.json updated (no-regression enforced) -> ITERATION_LOG.md appended.
"""
import os, json, argparse, subprocess, datetime, math
import validator as V

HERE = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(HERE, "..", "source-data", "branches_final.json")
SCORECARD = os.path.join(HERE, "SCORECARD.json")
LOG = os.path.join(HERE, "ITERATION_LOG.md")

def load(p): return json.load(open(p))
def save(p, o): json.dump(o, open(p, "w"), ensure_ascii=False, indent=1)

def compute_scorecard(branches):
    n = len(branches)
    precise = sum(1 for b in branches if b.get("prec") in ("places", "building"))
    return {"branches": n, "precise": precise,
            "precise_pct": round(100*precise/n, 1),
            "with_phone": sum(1 for b in branches if b.get("phone")),
            "updated": datetime.date.today().isoformat()}

def run_member(member, batch):
    """Runs the member script, returns dict of candidates by code."""
    out = os.path.join(HERE, f"_cand_{member}.json")
    subprocess.run(["python3", os.path.join(HERE, f"{member}.py"),
                    "--in", MASTER, "--batch", str(batch), "--out", out], check=True)
    return load(out)

def one_cycle(member, batch, cyc_id):
    branches = load(MASTER)
    by_code = {b["code"]: b for b in branches}
    before = compute_scorecard(branches)

    candidates = run_member(member, batch)
    accepted, rejected = V.run_batch_gate(by_code, candidates)

    # merge accepted patches into master (append/merge, never blind-overwrite)
    for p in accepted:
        b = by_code[p["code"]]
        b["lat"], b["lng"], b["prec"] = p["lat"], p["lng"], p["prec"]
        if p.get("phone"): b["phone"] = p["phone"]
        if p.get("rating") is not None: b["rating"] = p["rating"]
        b["geo_source"] = p["source"]
    after = compute_scorecard(branches)

    ok, offending = V.no_regression(before, after)
    if not ok:
        print(f"!! regression on {offending}; discarding cycle {cyc_id}")
        return before, 0, len(candidates)

    save(MASTER, branches)
    save(SCORECARD, after)
    append_log(cyc_id, member, before, after, accepted, rejected)
    print(f"cycle {cyc_id}: +{after['precise']-before['precise']} precise "
          f"({after['precise_pct']}%), {len(rejected)} rejected")
    return after, len(accepted), len(candidates)

def append_log(cyc_id, member, before, after, accepted, rejected):
    lines = [f"\n## Iteration {cyc_id} — {member} — {datetime.date.today().isoformat()}",
             f"- precise: {before['precise']} → {after['precise']} "
             f"({before['precise_pct']}% → {after['precise_pct']}%)",
             f"- accepted: {len(accepted)}  rejected: {len(rejected)}"]
    if rejected:
        lines.append("- rejected (manual-review queue):")
        for code, why in rejected[:10]:
            lines.append(f"    - {code}: {why}")
    open(LOG, "a").write("\n".join(lines) + "\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--member", default="geocoder")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--max-cycles", type=int, default=20)
    ap.add_argument("--min-accept-rate", type=float, default=0.3)
    args = ap.parse_args()

    # next iteration id = 1 + highest "## Iteration N" already in the log
    start = 1
    try:
        import re
        nums = [int(m) for m in re.findall(r"## Iteration (\d+)", open(LOG).read())]
        start = (max(nums) + 1) if nums else 1
    except FileNotFoundError:
        pass
    cyc = start
    while True:
        sc, acc, tried = one_cycle(args.member, args.batch, cyc)
        cyc += 1
        if not args.loop: break
        if cyc - start >= args.max_cycles: break
        if tried == 0 or acc / max(1, tried) < args.min_accept_rate:
            print("accept-rate below floor or nothing left; stopping."); break

if __name__ == "__main__":
    main()
