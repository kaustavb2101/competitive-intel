# DESKTOP AUTOPILOT — the Thai-IP pulls, unattended

**The answer first — run this once from the repo root on the home desktop (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File pipeline\desktop_autopilot.ps1
```

That single command does the whole Thai-IP session by itself: pulls the geo-blocked gov data,
folds it in, refreshes the competitor census, re-derives every app layer, runs the QA gate,
commits, and pushes to `claude/new-session-wto26j`. You don't have to watch it. Schedule it
(below) and the desktop keeps the platform's Thai-only data fresh without you at the keyboard.

One-time prerequisites (you likely already have all of these):
- Git for Windows (gives you `git` **and** Git Bash — the QA gate uses bash if it's on PATH).
- Python 3 on PATH as `python` (the script also falls back to the `py` launcher), plus
  `pip install shapely openlocationcode openpyxl pdfplumber requests`.
- `DATA_GO_TH_TOKEN` in `pipeline/.env` (see `docs/TONIGHT_CHECKLIST.md` §0 — and rotate it,
  the old one was exposed). Without it the gov sweep is skipped with a warning; everything
  else still runs.
- Git credentials that can push to the repo (if you've ever pushed from this machine, you're set).

---

## What it runs, in order (and roughly how long)

| # | Step | What it gets | Typical time |
|---|------|--------------|--------------|
| 1 | `git pull --rebase` of `claude/new-session-wto26j` | latest code + data from Claude sessions | seconds |
| 2 | `autox_dgt_ingest.py` | data.go.th sweep: DIW factories, DLT vehicles, NSO employment, OAE crops (**Thai-IP only**) | 20–60 min first run; minutes after (it resumes, skips downloaded CSVs) |
| 3 | `ingest_gov.py` | folds the raw CSVs into clean `source-data/` layers (measured, not proxy) | ~1 min |
| 4 | `pull_competitor_branches.py --pull --merge` | competitor branch census from the brands' own store-locators (**Thai-IP only**) → `competitors_national.json` | 5–15 min |
| 5 | `pull_all_provinces.py --max-buildings 60000` | Overture 3D building catchments for all 77 provinces — **OFF by default**, enable with `-Provinces` | HOURS (resumable; skips provinces already done) |
| 6 | Derive chain: `derive` → `build_amphoe` → `build_province` → `build_crop_stress` → `build_occupations`* → `build_amphoe_occupations`* → `build_opportunity_score` | re-projects everything into `platform/data/` and `--check`s each byte-exact (*optional-source builders skip quietly) | ~2–5 min |
| 7 | `bash tests/run.sh check` | the determinism + integrity gate — **skipped with a note if bash isn't installed** | ~1–2 min |
| 8 | `git add source-data platform/data` → commit → push (with pull-rebase retry) | your refreshed data lands on the branch for the next Claude session | seconds |

Steps 2–5 are "continue on failure": a dead site or missing token logs a **WARN** and the run
carries on. Steps 6–7 are the honesty gate: if the derive chain or QA gate fails, the run **stops
before committing** so broken data never lands on the branch (the pulled raw files stay on disk).

Flags:
- `-Provinces` — also run the long Overture 3D-buildings batch (step 5). Do this occasionally,
  e.g. overnight on a weekend; it resumes, so interrupting it is fine.
- `-NoPush` — commit locally but don't push (for a dry look before it leaves the machine).

## Schedule it (Windows Task Scheduler) — set-and-forget

1. Start → type **Task Scheduler** → **Create Task…** (not "Basic" — you want the settings tab).
2. **General**: name it `AutoX Thai-IP autopilot`. Check **"Run only when user is logged on"**
   (simplest; the pulls don't need admin).
3. **Triggers** → New…: either
   - **At log on** (runs every time you sit down at the desktop), or
   - **On a schedule → Daily** at e.g. 02:00 (nightly-if-on; add **"Run task as soon as possible
     after a scheduled start is missed"** under Settings so a powered-off night just catches up).
4. **Actions** → New…:
   - Program/script: `powershell`
   - Arguments: `-ExecutionPolicy Bypass -File pipeline\desktop_autopilot.ps1`
   - **Start in**: the repo root, e.g. `C:\Users\you\competitive-intel` (quotes not needed here
     even with spaces; the script also self-locates from its own path).
5. **Settings**: check "Stop the task if it runs longer than" → 4 hours (safety), and
   "Do not start a new instance" if the previous one is still running.

That's it. The desktop now does the Thai-IP session on its own whenever it's on.

## Reading the log

Everything (every command, every output line, per-step timings) is appended to
**`pipeline/autopilot_log.txt`** (gitignored — never leaves the machine, delete it any time).

Jump to the end of the file. Each run ends with a block like:

```
[2026-07-02 02:14:09] ---------------- SESSION SUMMARY ----------------
[2026-07-02 02:14:09]   [OK  ] git sync  (4.1s)
[2026-07-02 02:14:09]   [OK  ] data.go.th sweep  (1834.2s)
[2026-07-02 02:14:09]   [OK  ] gov fold-in  (42.7s)
[2026-07-02 02:14:09]   [WARN] competitor census  (61.3s)
[2026-07-02 02:14:09]   [SKIP] Overture province batch  (0s)
[2026-07-02 02:14:09]   [OK  ] derive (master -> branches/meta)  (55.0s)
...
[2026-07-02 02:14:09] AUTOPILOT DONE — refreshed data committed and pushed to origin/claude/new-session-wto26j.
```

- **OK** — worked. **SKIP** — deliberately not run (optional source absent, or `-Provinces` off).
- **WARN** — a pull failed but the run continued with the previously committed data (honest
  degradation; the data on the branch simply doesn't get fresher for that layer).
- **ABORT: …** — the run stopped on purpose (conflict, derive drift, or QA-gate failure) and
  tells you exactly what to do. Paste the tail of the log into Claude Code and it can take over.

## Safety notes (what it will NEVER do)

- **It never destroys local work.** No `git clean`, no `git reset --hard`, ever. On a pull/rebase
  conflict it aborts the rebase, leaves your tree exactly as it was, logs clear instructions, and
  exits. Uncommitted local changes ride through the pull via `--autostash`.
- **It never commits broken data.** The derive chain is `--check`-gated byte-exact and the QA gate
  runs before `git commit`; any failure stops the run pre-commit. Raw pulled files stay on disk
  either way (they're resume-safe inputs).
- **It never commits secrets or bulk raw inputs.** It only `git add`s `source-data/` and
  `platform/data/`; `.gitignore` already excludes `.env`, `pipeline/dgt_out/`, the Overture tile
  cache, the synthetic loan tape, and this autopilot's own log.
- Re-running is always safe: every pull resumes/skips what's done, every builder is deterministic.

## Alternative considered: a GitHub self-hosted runner on the desktop

You could instead register the desktop as a **GitHub Actions self-hosted runner** and put these
same steps in a workflow. Honest comparison:

| | Scheduled script (this) | Self-hosted runner |
|---|---|---|
| Setup | one Task Scheduler entry | install + register the runner service, write a workflow, keep the runner agent updated |
| Trigger from your **phone** | no — runs on its schedule | **yes** — `workflow_dispatch` from the GitHub app anywhere, and the job executes on the desktop's **Thai IP** |
| Logs/visibility | local `autopilot_log.txt` | GitHub Actions UI, notifications on failure |
| Security surface | none new | a machine that executes whatever lands in the repo's workflows — keep the repo private and runner scoped to this one repo only |
| When desktop is off | run is missed (catch-up option in Task Scheduler) | job queues until the runner is back |

**Recommendation: use the scheduled script.** It's one command, zero new attack surface, and the
desktop refreshes data whenever it's on — which is what you actually need. If you later want
phone-triggered Thai-IP pulls, the upgrade path is straightforward: repo → Settings → Actions →
Runners → "New self-hosted runner" (follow the Windows steps, install it as a service), then add a
workflow with `on: workflow_dispatch` + `runs-on: self-hosted` whose single step is
`powershell -ExecutionPolicy Bypass -File pipeline\desktop_autopilot.ps1`. The script is the same
either way — that's the point.
