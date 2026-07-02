# Remote ops — run the data pulls from your phone

**The answer first:** you no longer need your laptop to pull Overture buildings.
Open the repo in the **GitHub mobile app** (or github.com in your phone browser) →
**Actions** tab → pick a workflow → **Run workflow** → fill 1–3 boxes → tap the green
button. GitHub's servers do the download, and either open a **draft PR** for you to
merge (province buildings) or leave a **file to download** (national tiles).

This works because GitHub's runners have normal, unrestricted internet — so Overture
Maps (which the cloud sandbox can't reach) downloads fine from there.

---

## Workflow 1 — "Data — Overture province catchments"

**What it does:** pulls the real 3D buildings for provinces you pick, so their
`rayong-catchment.html?city=<slug>` scene lights up (same as Rayong/Bangkok today).

**How to run it (phone):**
1. GitHub app → this repo → **Actions** → **Data — Overture province catchments**.
2. Tap **Run workflow**.
3. Boxes:
   - **provinces** — comma-separated slugs, e.g. `chiang-mai,khon-kaen,songkhla`
     (default `chon-buri,phuket`). Slugs are the same as the province URLs on the site.
   - **max_buildings** — leave at `60000` (keeps each file web-sized, ~12 MB).
   - **all** — tick it to pull **every** province that doesn't have buildings yet
     (long run, up to ~5 h; if one province fails the rest still finish).
4. Tap the green **Run workflow** button.

**What you get:** a **DRAFT pull request** titled `data: Overture catchments (run …)`.
It never touches your working branch directly, so nothing can be overwritten.

**To merge it from your phone:** GitHub app → **Pull requests** → open the draft →
check the file list looks right (one `<slug>_catchment.json` per province, each ~5–15 MB)
→ **Ready for review** → **Merge**. Then redeploy on Vercel when you're next at the laptop
(or if Vercel auto-deploys the branch, it's already live).

**Time & size:** ~2–5 min per province; a couple of provinces ≈ 10 min. `all` = hours.
Each province file ≈ 5–15 MB at the default cap.

## Workflow 2 — "Data — national building tiles (PMTiles)"

**What it does:** builds the single nationwide `buildings.pmtiles` archive — the
streaming building layer that covers 10 km around every branch and competitor
(see `docs/BUILDING_TILES.md`).

**How to run it (phone):**
1. Actions → **Data — national building tiles (PMTiles)** → **Run workflow**.
2. One optional box, **bbox_override**:
   - **Leave it empty** for the full national build.
   - Or paste a small test area first (recommended for the first run), e.g. Bangkok
     metro: `100.3,13.5,100.9,14.0` (order is W,S,E,N).
3. Tap **Run workflow**. Expect **1–5 hours** for national; ~15–30 min for a test area.

**What you get:** NOT a PR — the file is too big for git. When the run finishes,
open the run page → scroll to **Artifacts** → download **buildings-pmtiles**
(kept for 7 days). Then, from any computer:
1. Upload `buildings.pmtiles` to **Vercel Blob** or **Cloudflare R2**.
2. Paste its public URL into `platform/data/tiles_config.json` → `buildings.pmtilesUrl`.
3. Deploy. The 3D map starts streaming national buildings immediately.

**Honest limit:** the FULL national build can exceed the runner's disk or its 6-hour
cap — if that happens the run **fails visibly** (red X) and nothing is half-done.
That's the signal to run it region-by-region with `bbox_override`, or on the laptop
per `docs/BUILDING_TILES.md`.

## Workflow 3 — "Site health — nightly live check"

**What it does:** every night at **05:30 Bangkok** (22:30 UTC) GitHub probes the
**live Vercel site**: the 4 entry pages must serve with the AutoX wordmark, and the
7 critical data files (`branches.json`, `meta.json`, `amphoe.json`, `amphoe_geo.json`,
`crop_stress.json`, `branch_labor.json`, `opportunity_score.json`) must download,
parse, and have the shapes the app expects (2,015 branches, 928 districts, ...).

**Where alerts land:** if the site is broken you get a **GitHub issue** titled
`🚨 Site health check failed <date>` — it shows up in the GitHub app on your phone.
The full pass/fail report is in the issue body. Repeat failures **comment on the
same issue** (no duplicate spam), and the issue **closes itself automatically**
the first night the site is healthy again. The Actions run also goes red.

**Run it manually (phone):** Actions → **Site health — nightly live check** →
**Run workflow**. One box, **base_url** — leave the default (the stable branch
alias) or paste the production domain once one exists.

**Run it locally (laptop):** the same checker validates the repo's own files
offline — `python3 pipeline/check_site_health.py --local platform` — or probes any
deployment: `python3 pipeline/check_site_health.py --base-url https://<app>.vercel.app`.
Exit 0 = healthy, 1 = broken; `--json out.json` writes a machine-readable report.

**Honest limit:** this checks that the site *serves sane files* — it does not run
the JavaScript, so a rendering bug with intact data won't trip it (that's what the
QA workflow's render phase and your own eyes are for).

## Watching a run / if something fails

- Actions tab → tap the running workflow → live log. A red step tells you exactly
  which province or command failed.
- Province failures in workflow 1 are **non-fatal** — the PR still contains every
  province that succeeded; just re-run later with the failed slugs.
- Re-running is always safe: workflow 1 skips provinces that already have buildings
  (unless you pick them explicitly after a merge), and workflow 2 just rebuilds the file.

## What CANNOT run from GitHub (the honest list)

- **data.go.th / DLT / NSO gov pulls** — geo-blocked to Thai IPs; GitHub's servers are
  foreign too. These still need your Thai laptop: `cd pipeline && python3 autox_dgt_ingest.py`
  (see `docs/TONIGHT_CHECKLIST.md`).
- **The real loan tape** — needs a manual internal export (no API); see
  `pipeline/loan_tape_schema.md`. Until then the platform runs on the labelled SYNTHETIC tape.
- **Vercel deploy** — merging a data PR updates the repo; the site updates when Vercel
  next deploys (automatic if the Git integration is on, otherwise `npx vercel --prod`
  from the laptop).
