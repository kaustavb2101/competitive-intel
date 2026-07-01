# STANDING LOOP — keep the platform improving without babysitting

> Goal: a **server-side, devices-off** loop that wakes on a schedule, picks the next highest-value
> improvement from `docs/IMPROVEMENT_BACKLOG.md`, builds it, runs the gate, and pushes — exactly like
> the concurrent loops we run by hand today, but automatic. You close your laptop; it keeps going.

## The one thing to know
The **brain already exists**: `docs/IMPROVEMENT_BACKLOG.md`. Its header IS the loop. Any fresh session
that reads it knows what to do. All that's missing is a **scheduler** to start those sessions for you.

## How to turn it on (Claude Code on the web — recommended, truly devices-off)
1. Open this repo in **Claude Code on the web** (claude.ai/code).
2. Use the **Schedule / recurring session** feature on the repo.
3. Set the cadence (suggest **every 4–6 hours**, off-the-hour e.g. `:17`, to spread load).
4. Paste this as the scheduled prompt:

```
Read docs/IMPROVEMENT_BACKLOG.md. Pick the SINGLE highest-value UNBLOCKED, sandbox-safe item.
Build it small and graceful (degrade cleanly when any pulled data is absent). Run
`bash tests/run.sh check` and get it to 0 failed — if you can't, revert ONLY the files you
changed and pick a smaller item. Commit + push to claude/new-session-wto26j (open/refresh the
draft PR). Then check the item off in the backlog and add 1–3 new ideas. ONE substantive
improvement per cycle. ABSOLUTE: no fabricated/hallucinated data — every number traces to a real
source or is labelled an estimate with its method. Never run git clean -fd / checkout -- . /
reset --hard (shared tree). Only push claude/new-session-wto26j.
```

Each firing spawns a clean server-side session, advances the backlog by one item, and pushes — with
the QA gate (now 20 checks) as the safety rail and the no-fabrication provenance gate enforced in CI.

## ⚠️ If a scheduled run fails with "no repository checked out / wrong GitHub token"
Symptom (seen 2026-07-01): the scheduled session reports the container was **empty**
(`/home/user` not a git repo), it **couldn't find this repo**, the **GitHub token belonged to an
unrelated personal account**, and it gave up after a wrong-name clone guess (`autox-calibration`) was
rejected. That is a **provisioning/config problem in the schedule itself**, not a code problem — the
loop never got the repo or the right credentials, so it correctly refused to guess further.

Fix (all in **claude.ai/code**, ~2 min — nothing to change in this repo):
1. **Delete the broken schedule** ("Standing improvement loop").
2. **Open `kaustavb2101/competitive-intel` FIRST** in Claude Code on the web, then create the schedule
   **from inside the repo view** — this is what binds the recurring session to *this* repo. A schedule
   created from the global/home view has no repo attached and lands in an empty container.
3. Confirm the **GitHub connection** is the account that owns `kaustavb2101/competitive-intel`
   (the failure shows a *different* account's token was attached — re-authorize the Claude Code GitHub
   App for this repo/account if the picker doesn't list it).
4. Set the **base branch** to `claude/new-session-wto26j` (or `main`) and re-paste the scheduled prompt
   below. Save, then use "Run now" once to verify it clones the repo and the gate passes before trusting
   the cadence.

If the web Schedule feature still won't attach the repo, the loop can't run devices-off yet — there is
no in-session substitute (see below). Ping me and we treat the backlog by hand each session instead.

## Why not the in-session scheduler
`CronCreate` (the only scheduler exposed inside a chat session) fires into the *current* session and
dies when that session ends — it is **not** devices-off. Use it only as a same-session stopgap; the
web Schedule feature above is the real standing loop.

## Guardrails the loop runs under (already in place)
- **QA gate** (`bash tests/run.sh check`, 20 checks): pipeline `--check` byte-exactness + `node --check`
  on every page + `validate_data.py` (60+ integrity checks incl. the provenance/no-fabrication gate).
- **CI** (`.github/workflows/qa.yml`, pinned Python 3.11) re-runs the gate on every push; a red gate
  blocks the change.
- **Backlog rules** (top of `IMPROVEMENT_BACKLOG.md`): sandbox-only, graceful-degrade, no fabrication,
  shared-tree safety, honest provenance, serve the two objectives (portfolio risk · where to expand).

## Desktop-only items the loop CANNOT do (kept out on purpose)
Anything needing a Thai-IP / desktop pull lives in `docs/TONIGHT_CHECKLIST.md` and must be run by
Kaustav (the cloud loop has a foreign IP): the competitor store-locator census
(`pull_competitor_branches.py`), Overture building tiles (`build_building_tiles.py`), DLT vehicle
registrations, OAE farm-gate prices, NSO census. The loop consumes that data gracefully once it lands.
