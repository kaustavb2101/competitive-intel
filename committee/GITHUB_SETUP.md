# Running the committee in GitHub Actions

The workflow `.github/workflows/committee.yml` runs the **key-based** committee members in CI,
commits the improved data back to the repo, and (if Vercel is Git-connected) auto-redeploys.

## What can and cannot run in GitHub Actions
| Member | Runs in GitHub Actions? | Why |
|---|---|---|
| **Geocoder** (Google Maps API) | ✅ yes | API key, works from any IP |
| **Competitor Scout** (Google Maps API) | ✅ yes (once `scout.py` is built) | API key, any IP |
| **Industry Census** (DLT / DIW / data.go.th) | ❌ no | geo-blocked to **Thai IPs**; GitHub runners are in Azure datacenters. Run locally or on a Thai self-hosted runner |

## One-time setup (5 minutes)
1. **Push this repo to GitHub** (private recommended — it contains branch data).
2. **Add the API key as a secret:**
   GitHub → your repo → *Settings* → *Secrets and variables* → *Actions* → *New repository secret*
   - Name: `GOOGLE_MAPS_API_KEY`
   - Value: your Google Maps Platform key (enable **Places API**). Restrict the key to Places API.
3. **(Optional) Connect Vercel to the repo** with Root Directory = `platform`. Then every commit the
   bot makes to `platform/data/` auto-deploys. If you'd rather deploy manually, skip this.

## Running it
- **On demand:** repo → *Actions* → *committee-loop* → *Run workflow* → set `batch` (e.g. 100) and `loop`.
- **Scheduled:** it already runs every Monday 02:00 UTC, chipping away 10 cycles × batch.
- The bot commits `source-data/branches_final.json`, `committee/SCORECARD.json`,
  `committee/ITERATION_LOG.md`, and regenerated `platform/data/` with message
  `committee: automated data-quality cycle [skip ci]`.

## Cost & safety
- Google **Places Text Search ≈ $32 / 1,000 requests**. The ~1,505 imprecise branches ≈ **$48 one-time**
  to fully backfill. The weekly schedule is gentle; use a manual run with a big batch if you want it done fast.
- The key lives only in GitHub Secrets (never in code). Restrict it to the Places API + your repo.
- The Validator gate still applies in CI — bad matches are rejected and logged, never merged.
- Keep the repo **private**; it carries branch locations and (after enrichment) phone numbers.

## The Thai-IP members
For Industry Census (DLT vehicles, DIW factories), either:
- run `python3 committee/run_cycle.py --member census …` locally on your Thai connection, **or**
- register a **self-hosted GitHub runner** on a Thai network and label the census job to use it.
Everything else (Geocoder, Scout) is happy in the cloud.
