# R2 migration — move the heavy 3D catchments off git/Vercel

## Why
The per-province 3D building catchments (`platform/data/*_catchment.json`, ~12 MB each) are the
biggest served assets. The national Overture pull generates up to ~77 of them (~0.5–0.9 GB). Keeping
those in git + bundling them into every Vercel deploy bloats the repo, slows builds, and pushes toward
Vercel's file/deploy-size limits. **Cloudflare R2** (S3-compatible object storage, free egress to
Cloudflare's CDN) is the right home. Everything else (branches.json, amphoe layers, the small province
deep-dives) stays where it is — only the big catchments move.

## What moves to R2
- **Primary:** `platform/data/*_catchment.json` + `platform/data/province_bbox.json`
- **Optional archive (re-pullable, not served):** the raw `source-data/datagoth/*` pulls (44 MB DIW
  factory CSV, etc.) and the Overture tile cache — durable backup, not on the hot path.

## Steps

### 1. Create the bucket + credentials (you)
- Cloudflare dashboard → R2 → create bucket, e.g. `autox-catchments`.
- Enable a **public** access URL (r2.dev subdomain) or attach a custom domain (e.g. `cdn.autox…`).
- Create an **R2 API token** (Object Read & Write) → note Access Key ID + Secret + your Account ID.

### 2. Upload (script is ready: `pipeline/upload_r2.py`)
```bash
export R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_BUCKET=autox-catchments
pip install boto3
python3 pipeline/upload_r2.py --also-bbox            # uploads every *_catchment.json + province_bbox
python3 pipeline/upload_r2.py --dry-run              # preview first
```
Idempotent (skips objects whose size already matches). Sets `Cache-Control: public, max-age=86400`.

### 3. Point the app at R2 (one of two ways)
- **A — Vercel rewrite (zero JS change):** in `platform/vercel.json`, add
  ```json
  { "rewrites": [ { "source": "/data/(.*_catchment.json)", "destination": "https://<r2-public-host>/data/$1" } ] }
  ```
  Simple, but catchment bytes proxy through Vercel (counts against Vercel egress).
- **B — Direct R2 fetch (recommended):** set a `CATCHMENT_BASE` in the 3D pages
  (`rayong-catchment.html`, `branch-explorer.html`) and fetch `${CATCHMENT_BASE}/<slug>_catchment.json`
  from R2 directly (client → Cloudflare CDN, no Vercel egress). Guard the existing "not pulled yet"
  fallback on a failed fetch, exactly as today.

### 4. Stop committing catchments to git
- Add `platform/data/*_catchment.json` to `.gitignore`.
- Change `.github/workflows/data-overture.yml`'s final step to run `pipeline/upload_r2.py` (with R2
  secrets added to the repo) instead of committing the files + opening a PR. The national 3D pull then
  lands straight in R2, and neither git nor Vercel ever carries the bulk.

## What I need from you to execute
The **bucket name + public host + the three R2 env vars** (or add them as repo secrets
`R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET`). Then I run the upload,
switch the app to option B, and convert the Overture workflow. Until then, catchments keep working
from git as they do today — this migration is additive and safe to land ahead of the cutover.
