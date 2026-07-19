# rival_pulse_refresh.ps1 — the ALWAYS-ON rival watch (objective #2).
# Runs daily via Windows Task Scheduler on Kaustav's laptop (the Thai-IP requirement lives here:
# tidlor.com / sawad.co.th / muangthaicap.com are geoblocked from foreign/cloud IPs, so this is the
# ONE machine that can watch rival promos). Google Play would work from any IP but rides along.
#
# Design: works in a DEDICATED clone under %LOCALAPPDATA% so it never touches the main working
# copy. Refreshes the two network pulls + the deterministic builder, and if anything changed,
# force-pushes branch data/rival-pulse-auto and upserts a PR — Kaustav merges from his phone.
# first_seen promo tracking persists through the COMMITTED source files, so merge the PRs to keep
# the "NEW" flags honest.
#
#   register (once):  schtasks /Create /TN AutoXRivalPulse /TR "pwsh -NoProfile -File <this file>" /SC DAILY /ST 08:57
#   remove:           schtasks /Delete /TN AutoXRivalPulse /F
#   run now (test):   pwsh -NoProfile -File pipeline\rival_pulse_refresh.ps1

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$Repo   = 'https://github.com/kaustavb2101/competitive-intel.git'
$Work   = Join-Path $env:LOCALAPPDATA 'autox-rival-pulse\repo'
$Branch = 'data/rival-pulse-auto'
$Log    = Join-Path $env:LOCALAPPDATA 'autox-rival-pulse\refresh.log'
New-Item -ItemType Directory -Force (Split-Path $Log) | Out-Null
Start-Transcript -Path $Log -Append | Out-Null
try {
  if (-not (Test-Path (Join-Path $Work '.git'))) {
    git clone --depth 50 $Repo $Work
  }
  Set-Location $Work
  git fetch origin master
  git checkout -B $Branch origin/master

  # the two network pulls + the deterministic projection
  python pipeline/pull_rival_promos.py
  python pipeline/pull_app_reviews.py
  python pipeline/build_rival_pulse.py

  $changed = git status --porcelain -- source-data/rival_promos.json source-data/app_reviews.json platform/data/rival_pulse.json
  if (-not $changed) { Write-Output 'rival-pulse: no changes today.'; Stop-Transcript | Out-Null; exit 0 }

  git add source-data/rival_promos.json source-data/app_reviews.json platform/data/rival_pulse.json
  $stamp = Get-Date -Format 'yyyy-MM-dd'
  git -c user.name='AutoX Rival Pulse' -c user.email='kb210183@gmail.com' commit -m "data(rival-pulse): daily refresh $stamp — promos + app sentiment (auto, Thai-IP laptop)"
  git push -f origin $Branch

  # upsert the PR (create if none open for the branch)
  $open = gh pr list --head $Branch --state open --json number --jq 'length'
  if ($open -eq '0') {
    gh pr create --head $Branch --title "data(rival-pulse): daily auto-refresh" --body "Automated daily rival-pulse refresh from the Thai-IP laptop (rival_pulse_refresh.ps1): rival promos (first_seen-tracked) + Google Play sentiment for the 5 apps incl. our own. Merge to publish; the branch is force-updated each day until merged."
  } else {
    Write-Output "rival-pulse: PR already open for $Branch — branch updated in place."
  }
} finally {
  Stop-Transcript | Out-Null
}
