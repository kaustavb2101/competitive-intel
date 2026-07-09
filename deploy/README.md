# Running the committee continuously

The daemon (`committee/daemon.py`) loops forever: census (authoritative factories) → geocoder
(accuracy backfill) → derive (refresh app) → sleep → repeat. Because DIW's portal is reachable from
any IP, this runs on **any** host — no Thai connection needed for factories.

## Pick a host
- **Docker (anywhere):** `docker build -t autox-committee -f deploy/Dockerfile . && docker run -d --restart=always -e GOOGLE_MAPS_API_KEY=... autox-committee`
- **A small VPS / your laptop (systemd):** edit `deploy/committee.service` (set the key + path), then
  `sudo cp deploy/committee.service /etc/systemd/system/ && sudo systemctl enable --now committee`
- **Render / Railway / Fly.io:** deploy as a **background worker** using `deploy/Procfile`.
- **Quick & dirty:** `nohup python3 committee/daemon.py > daemon.out 2>&1 &`

## Tuning (env vars)
- `CYCLE_SLEEP_SEC` — seconds between cycles (default 900 = 15 min)
- `CENSUS_EVERY_N` — run the factory census every N cycles (default 24; it changes slowly)
- `GEOCODE_BATCH` — branches per geocode cycle (default 50)
- `GOOGLE_MAPS_API_KEY` — needed for geocoder; census runs without it

## What still needs a Thai IP
Only **DLT vehicle registrations** remain geo-blocked (DLT hosts are down/blocked from abroad).
Factories (DIW) are solved and run anywhere. For DLT, run the daemon on a Thai VPS or self-hosted
runner, or find a reachable mirror (open thread).

## Committing results (if running on a host with the repo)
The daemon updates `source-data/branches_final.json`, `platform/data/`, `committee/SCORECARD.json`,
and `committee/ITERATION_LOG.md`. To publish, either let the GitHub Actions workflow run (it commits),
or add a `git commit && git push` step to your host's crontab.
