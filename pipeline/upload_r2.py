#!/usr/bin/env python3
"""Upload the heavy served assets (3D building catchments) to Cloudflare R2.

WHY
    The per-province 3D catchments (platform/data/*_catchment.json, ~12 MB each) are the biggest,
    fastest-growing served files. The national Overture pull generates up to ~77 of them (~0.5-0.9 GB).
    Committing that to git + bundling it into every Vercel deploy bloats the repo and slows/limits
    deploys. R2 (S3-compatible object storage, free egress to Cloudflare's CDN) is the right home:
    the app fetches catchments straight from R2, and git/Vercel stay lean.

CREDENTIALS (env, never commit — set these before running):
    R2_ACCOUNT_ID         Cloudflare account id
    R2_ACCESS_KEY_ID      R2 API token access key
    R2_SECRET_ACCESS_KEY  R2 API token secret
    R2_BUCKET             target bucket name (e.g. "autox-catchments")
    R2_PREFIX             optional key prefix (default "data/")

    python3 upload_r2.py                 # upload every platform/data/*_catchment.json (+ province_bbox)
    python3 upload_r2.py --glob '*.json' --dir ../source-data/datagoth   # archive raw pulls too
    python3 upload_r2.py --dry-run       # list what WOULD upload, no network

Needs boto3:  pip install boto3
Idempotent:   skips objects whose size already matches R2 (cheap HEAD); --force re-uploads all.
"""
import os, sys, glob, argparse, hashlib

def _client():
    try:
        import boto3  # noqa
    except ImportError:
        sys.exit("boto3 not installed — run: pip install boto3")
    import boto3
    acct = os.environ.get("R2_ACCOUNT_ID")
    key  = os.environ.get("R2_ACCESS_KEY_ID")
    sec  = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not all((acct, key, sec)):
        sys.exit("Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY (and R2_BUCKET).")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{acct}.r2.cloudflarestorage.com",
        aws_access_key_id=key, aws_secret_access_key=sec,
        region_name="auto",
    )

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    here = os.path.dirname(os.path.abspath(__file__))
    default_dir = os.path.join(here, "..", "platform", "data")
    ap.add_argument("--dir", default=default_dir, help="source directory")
    ap.add_argument("--glob", default="*_catchment.json", help="filename glob (default 3D catchments)")
    ap.add_argument("--also-bbox", action="store_true", help="also upload province_bbox.json")
    ap.add_argument("--force", action="store_true", help="re-upload even if size matches")
    ap.add_argument("--dry-run", action="store_true", help="list only, no upload")
    args = ap.parse_args()

    bucket = os.environ.get("R2_BUCKET")
    prefix = os.environ.get("R2_PREFIX", "data/")
    if not bucket and not args.dry_run:
        sys.exit("Set R2_BUCKET.")

    files = sorted(glob.glob(os.path.join(args.dir, args.glob)))
    if args.also_bbox:
        bb = os.path.join(args.dir, "province_bbox.json")
        if os.path.exists(bb):
            files.append(bb)
    if not files:
        print(f"No files match {args.glob} in {args.dir}")
        return 0

    total_mb = sum(os.path.getsize(f) for f in files) / 1e6
    print(f"{len(files)} file(s), {total_mb:.1f} MB total → r2://{bucket or '<bucket>'}/{prefix}")
    if args.dry_run:
        for f in files:
            print(f"  would upload {os.path.basename(f)}  ({os.path.getsize(f)/1e6:.1f} MB) -> {prefix}{os.path.basename(f)}")
        return 0

    s3 = _client()
    up, skip = 0, 0
    for f in files:
        name = os.path.basename(f)
        key = f"{prefix}{name}"
        size = os.path.getsize(f)
        if not args.force:
            try:
                head = s3.head_object(Bucket=bucket, Key=key)
                if head.get("ContentLength") == size:
                    print(f"  skip {name} (already {size/1e6:.1f} MB)"); skip += 1; continue
            except Exception:
                pass
        s3.upload_file(f, bucket, key, ExtraArgs={
            "ContentType": "application/json",
            "CacheControl": "public, max-age=86400",
        })
        print(f"  up   {name}  ({size/1e6:.1f} MB) -> {key}")
        up += 1
    print(f"\n=== uploaded {up}, skipped {skip} → r2://{bucket}/{prefix} ===")
    print("Next: point the app at the R2 public URL (see docs/R2_MIGRATION.md).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
