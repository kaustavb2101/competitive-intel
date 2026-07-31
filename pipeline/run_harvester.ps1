# run_harvester.ps1 — disk-safe detached runner for the gov-catalog harvester.
# Operational helper (NOT committed; harvest output is gitignored). Invoked by the
# "AutoX-GovHarvester" Scheduled Task at logon + hourly, so the harvest survives a
# Claude session ending, a shell close, and a reboot. The task uses MultipleInstances
# = IgnoreNew, so this never runs two at once (safe for the append-only manifest).
#
# Two guards keep it from filling the laptop (only ~78 GB free):
#   1. skip entirely if free disk < 40 GB
#   2. cap each run's downloads at 15 GB (the harvester resumes next trigger)
$ErrorActionPreference = 'Continue'
$root    = 'C:\Users\Kaustav Bagchi\competitive-intel\competitive-intel'
$hostdir = Join-Path $root 'source-data\gdcatalog_harvest\gdcatalog.go.th'
$out     = Join-Path $hostdir '_harvest_stdout.log'
$err     = Join-Path $hostdir '_harvest_stderr.log'
$ts      = Get-Date -Format o
$freeGB  = [math]::Round((Get-PSDrive C).Free / 1GB, 1)

if ($freeGB -lt 40) {
    Add-Content -Path $out -Value "$ts  SKIP: low disk ($freeGB GB free < 40 GB floor) — not harvesting"
    exit 0
}
Add-Content -Path $out -Value "$ts  LAUNCH: $freeGB GB free — harvesting (cap 15 GB this run)"
Set-Location (Join-Path $root 'pipeline')
& python harvest_gdcatalog.py --max-total-gb 15 --sleep 0.6 1>> $out 2>> $err
$ts2 = Get-Date -Format o
Add-Content -Path $out -Value "$ts2  RUN EXITED (code $LASTEXITCODE)"
