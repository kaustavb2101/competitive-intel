# tape_portal_watch.ps1 — the loan-tape portal sync (schtasks AutoXTapePortal, daily)
# ---------------------------------------------------------------------------------
# PORTAL: %USERPROFILE%\OneDrive\AutoX-DataRoom\loan-tape\tape_YYYY-MM.xlsx
#   The risk team drops the monthly no-PII-contract export there (same 60 columns).
#   OneDrive syncs it to this laptop; this script notices the new file and runs the
#   full chain: ingest (owner-side, raw never committed) -> deterministic builder ->
#   commit aggregates -> push -> PR. State stamp = .processed_<name> marker files, so
#   every drop is ingested exactly once; re-drops (same name, newer mtime) re-process.
# SAFETY: only source-data/staging + platform/data aggregates are committed. The raw
#   xlsx stays in OneDrive. Never widen the git add list here.
$ErrorActionPreference = "Stop"
$portal = Join-Path $env:USERPROFILE "OneDrive\AutoX-DataRoom\loan-tape"
$repo = Join-Path $env:USERPROFILE "competitive-intel\competitive-intel"
$log = Join-Path $portal "_sync.log"

function Log($m) { "$((Get-Date).ToString('s'))  $m" | Add-Content -Encoding utf8 $log }

if (-not (Test-Path $portal)) { exit 0 }
$files = Get-ChildItem $portal -Filter "tape_*.xlsx" | Sort-Object LastWriteTime
if (-not $files) { exit 0 }

foreach ($f in $files) {
    $stamp = Join-Path $portal (".processed_" + $f.Name)
    if ((Test-Path $stamp) -and ((Get-Item $stamp).LastWriteTime -ge $f.LastWriteTime)) { continue }
    Log "NEW DROP: $($f.Name) ($([math]::Round($f.Length/1MB,1)) MB) — ingesting"
    try {
        Set-Location (Join-Path $repo "pipeline")
        $env:PYTHONUTF8 = "1"
        git -C $repo fetch origin 2>&1 | Out-Null
        git -C $repo pull --ff-only origin master 2>&1 | Out-Null
        python ingest_real_tape.py --src $f.FullName 2>&1 | Add-Content -Encoding utf8 $log
        python build_tape_layers.py 2>&1 | Add-Content -Encoding utf8 $log
        python build_tape_layers.py --check 2>&1 | Add-Content -Encoding utf8 $log
        if ($LASTEXITCODE -ne 0) { throw "build_tape_layers --check failed" }
        $branch = "data/tape-" + $f.BaseName
        git -C $repo checkout -B $branch 2>&1 | Out-Null
        git -C $repo add source-data/staging/real_tape_aggregates.json platform/data/tape_real.json
        git -C $repo commit -m "data(tape): portal drop $($f.Name) — refresh no-PII aggregates + tape layers" 2>&1 | Add-Content -Encoding utf8 $log
        git -C $repo push -u origin $branch 2>&1 | Add-Content -Encoding utf8 $log
        gh pr create -R kaustavb2101/competitive-intel --title "data(tape): portal drop $($f.Name)" --body "Automated portal sync: new loan-tape drop ingested to no-PII aggregates (raw stays in OneDrive). Provenance regen + merge handled by the usual gate flow." 2>&1 | Add-Content -Encoding utf8 $log
        git -C $repo checkout master 2>&1 | Out-Null
        New-Item -ItemType File -Path $stamp -Force | Out-Null
        Log "DONE: $($f.Name) -> PR opened"
    } catch {
        Log "FAILED: $($f.Name) — $($_.Exception.Message)"
    }
}
