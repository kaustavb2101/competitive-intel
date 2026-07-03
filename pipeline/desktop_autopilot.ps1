<#
.SYNOPSIS
  desktop_autopilot.ps1 — ONE unattended Thai-IP data session for the AutoX platform.

.DESCRIPTION
  Run this (or schedule it) on the Thai home desktop. It does the whole session by itself:

    1. git pull the working branch (claude/new-session-wto26j) — ABORTS SAFELY on conflict,
       never destroys local work (no git clean, no reset --hard, ever).
    2. python pipeline/autox_dgt_ingest.py     — data.go.th gov sweep (DIW/DLT/NSO/OAE).
                                                 Thai-IP only; on failure logs a warning and continues.
    3. python pipeline/ingest_gov.py           — fold dgt_out CSVs into clean source-data layers.
    4. python pipeline/pull_competitor_branches.py --pull --merge
                                               — competitor store-locator census (Thai-IP only).
    5. (only with -Provinces) python pipeline/pull_all_provinces.py --max-buildings 60000
                                               — Overture 3D building catchments, LONG (hours).
    6. Deterministic derive chain (mirrors pipeline/refresh_all.sh order):
       derive.py -> build_amphoe.py -> build_province.py -> build_crop_stress.py ->
       build_occupations.py -> build_amphoe_occupations.py -> build_opportunity_score.py
       Each is re-run then --check'd byte-exact. A hard failure here BLOCKS the commit.
    7. bash tests/run.sh check (if bash is on PATH, e.g. Git Bash) — skipped with a note otherwise.
    8. git add source-data/ + platform/data/, commit, git push (pull --rebase retry on rejection).

  Everything is appended to pipeline/autopilot_log.txt (gitignored).

.PARAMETER Provinces
  Also run the Overture 3D-buildings batch (pull_all_provinces.py). Off by default — it can run
  for hours. The batch is resumable, so it is safe to enable occasionally.

.PARAMETER NoPush
  Do everything including the local commit, but skip the final git push.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File pipeline\desktop_autopilot.ps1
  powershell -ExecutionPolicy Bypass -File pipeline\desktop_autopilot.ps1 -Provinces

.NOTES
  PowerShell 5.1 compatible (Windows default). Uses `python` (falls back to the `py` launcher).
  Safe to re-run any time: every pull is resume-safe and every builder is deterministic.
#>
[CmdletBinding()]
param(
    [switch]$Provinces,
    [switch]$NoPush
)

# ---------------------------------------------------------------------------
# Setup — paths, log, environment
# ---------------------------------------------------------------------------
$ErrorActionPreference = "Continue"   # native stderr must not kill the run
Set-StrictMode -Off

$Branch    = "claude/new-session-wto26j"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path          # ...\pipeline
$RepoRoot  = (Resolve-Path (Join-Path $ScriptDir "..")).Path          # repo root
$PipeDir   = $ScriptDir
$LogFile   = Join-Path $ScriptDir "autopilot_log.txt"

# Python prints Thai text + unicode glyphs; when stdout is a pipe (as here) Windows falls back to
# a legacy codepage and crashes with UnicodeEncodeError. Force UTF-8 for every child python.
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8       = "1"
# Never hang unattended waiting for a credential prompt — fail fast instead.
$env:GIT_TERMINAL_PROMPT = "0"

$script:StepResults = @()   # summary rows: @{ Name=..; Status=OK|WARN|FAIL|SKIP; Seconds=.. }

function Write-Log {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line  = "[$stamp] $Message"
    Write-Host $line
    try { Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 } catch { }
}

function Add-Result {
    param([string]$Name, [string]$Status, [double]$Seconds)
    $script:StepResults += (New-Object PSObject -Property @{
        Name = $Name; Status = $Status; Seconds = [math]::Round($Seconds, 1)
    })
}

function Write-Summary {
    Write-Log "---------------- SESSION SUMMARY ----------------"
    foreach ($r in $script:StepResults) {
        Write-Log ("  [{0,-4}] {1}  ({2}s)" -f $r.Status, $r.Name, $r.Seconds)
    }
    Write-Log "-------------------------------------------------"
}

function Stop-Autopilot {
    # Hard abort: log why, print the summary, exit non-zero. NEVER cleans/resets the tree.
    param([string]$Reason)
    Write-Log "ABORT: $Reason"
    Write-Summary
    Write-Log "Autopilot stopped. Your working tree was NOT cleaned or reset — local work is intact."
    exit 1
}

# Run one external command, streaming all output into the log. Returns the exit code.
# $Command = @(exe, arg1, arg2, ...). Robust to spaces in paths (PS quotes variables itself).
function Invoke-Step {
    param(
        [string]$Name,
        [string[]]$Command,
        [string]$WorkDir = $null
    )
    Write-Log "=== STEP: $Name"
    Write-Log (">>> " + ($Command -join " "))
    $t0 = Get-Date
    $code = -1
    if ($WorkDir) { Push-Location -LiteralPath $WorkDir }
    try {
        $exe  = $Command[0]
        $rest = @()
        if ($Command.Count -gt 1) { $rest = $Command[1..($Command.Count - 1)] }
        & $exe @rest 2>&1 | ForEach-Object { Write-Log ("  | " + "$_") }
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }   # some PS-native calls leave it unset
    } catch {
        Write-Log ("  ! could not run '" + $Command[0] + "': " + $_.Exception.Message)
        $code = -1
    } finally {
        if ($WorkDir) { Pop-Location }
    }
    $secs = ((Get-Date) - $t0).TotalSeconds
    Write-Log ("=== STEP: $Name -> exit $code  ({0:N1}s)" -f $secs)
    return $code
}

# ---------------------------------------------------------------------------
# 0. Preflight
# ---------------------------------------------------------------------------
Write-Log "================================================================"
Write-Log "AUTOPILOT START  (Provinces=$Provinces  NoPush=$NoPush)"
Write-Log "repo: $RepoRoot"
Set-Location -LiteralPath $RepoRoot

$gitOk = Invoke-Step -Name "git preflight (rev-parse)" -Command @("git", "rev-parse", "--git-dir")
if ($gitOk -ne 0) { Stop-Autopilot "not a git repository (or git not on PATH). Install Git for Windows / run from the repo." }

# Resolve python: prefer `python`, fall back to the Windows `py -3` launcher.
$PyCmd = $null
foreach ($cand in @( @("python"), @("py", "-3") )) {
    try {
        $exe = $cand[0]; $pre = @(); if ($cand.Count -gt 1) { $pre = $cand[1..($cand.Count - 1)] }
        & $exe @pre --version 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { $PyCmd = $cand; break }
    } catch { }
}
if ($null -eq $PyCmd) { Stop-Autopilot "no python found (tried 'python' and 'py -3'). Install Python 3 and re-run." }
Write-Log ("python resolved as: " + ($PyCmd -join " "))

function New-PyCommand {   # build @(python..., script, extra args)
    param([string]$Script, [string[]]$Extra = @())
    $c = @() + $PyCmd + @($Script)
    if ($Extra.Count -gt 0) { $c += $Extra }
    return $c
}

# ---------------------------------------------------------------------------
# 1. Sync the working branch (abort-on-conflict, never destructive)
# ---------------------------------------------------------------------------
$t0 = Get-Date
$cur = (& git rev-parse --abbrev-ref HEAD 2>&1 | Select-Object -First 1)
Write-Log "current branch: $cur (want: $Branch)"

$dirty = @(& git status --porcelain 2>&1)
if ($dirty.Count -gt 0) {
    Write-Log ("NOTE: working tree has {0} uncommitted change(s); pull will use --autostash to keep them." -f $dirty.Count)
}

if ("$cur" -ne $Branch) {
    $code = Invoke-Step -Name "git checkout $Branch" -Command @("git", "checkout", $Branch)
    if ($code -ne 0) {
        Stop-Autopilot ("could not checkout '$Branch' (likely local changes on '$cur' in the way). " +
                        "Nothing was touched. Commit/stash your work, then re-run.")
    }
}

$code = Invoke-Step -Name "git fetch origin $Branch" -Command @("git", "fetch", "origin", $Branch)
if ($code -ne 0) {
    Write-Log "WARN: git fetch failed (offline? credentials?). Continuing with the LOCAL branch state; the final push may fail."
    Add-Result "git sync" "WARN" ((Get-Date) - $t0).TotalSeconds
} else {
    $code = Invoke-Step -Name "git pull --rebase --autostash" -Command @("git", "pull", "--rebase", "--autostash", "origin", $Branch)
    if ($code -ne 0) {
        # Do NOT leave a half-done rebase behind; abort it, then stop with clear instructions.
        Invoke-Step -Name "git rebase --abort (cleanup)" -Command @("git", "rebase", "--abort") | Out-Null
        Invoke-Step -Name "git merge --abort (cleanup)"  -Command @("git", "merge", "--abort")  | Out-Null
        Stop-Autopilot ("MERGE/REBASE CONFLICT pulling origin/$Branch. The rebase was aborted and your " +
                        "local commits/changes are UNTOUCHED. Resolve by hand: 'git status', then either " +
                        "'git pull --rebase origin $Branch' and fix conflicts, or ask Claude Code. " +
                        "(If autostash left a stash: 'git stash list' / 'git stash pop'.)")
    }
    Add-Result "git sync" "OK" ((Get-Date) - $t0).TotalSeconds
}

# ---------------------------------------------------------------------------
# 2. Thai-IP pulls (each continues on failure with a logged warning)
# ---------------------------------------------------------------------------

# 2a. data.go.th sweep (DIW factories, DLT vehicles, NSO employment, OAE crops).
#     Resume-safe: re-runs skip already-downloaded CSVs. Needs DATA_GO_TH_TOKEN (pipeline/.env or env).
$t0 = Get-Date
$code = Invoke-Step -Name "autox_dgt_ingest.py (data.go.th gov sweep)" `
                    -Command (New-PyCommand "autox_dgt_ingest.py") -WorkDir $PipeDir
$dgtOk = ($code -eq 0)
if ($dgtOk) { Add-Result "data.go.th sweep" "OK" ((Get-Date) - $t0).TotalSeconds }
else {
    Write-Log "WARN: data.go.th sweep failed (token missing/expired? not on a Thai IP? site down?). Continuing."
    Add-Result "data.go.th sweep" "WARN" ((Get-Date) - $t0).TotalSeconds
}

# 2b. Fold dgt_out CSVs into clean source-data layers. Runs even if 2a warned — a PREVIOUS pull's
#     CSVs may still be in dgt_out/. It exits non-zero when dgt_out is empty; that's a warn, not fatal.
$t0 = Get-Date
$code = Invoke-Step -Name "ingest_gov.py (fold gov CSVs into source-data)" `
                    -Command (New-PyCommand "ingest_gov.py") -WorkDir $PipeDir
if ($code -eq 0) { Add-Result "gov fold-in" "OK" ((Get-Date) - $t0).TotalSeconds }
else {
    Write-Log "WARN: ingest_gov.py failed (usually: no CSVs in pipeline/dgt_out yet). Continuing with existing layers."
    Add-Result "gov fold-in" "WARN" ((Get-Date) - $t0).TotalSeconds
}

# 2c. Competitor store-locator census (authoritative brand branch-finders; Thai-IP only) + merge
#     into platform/data/competitors_national.json.
$t0 = Get-Date
$code = Invoke-Step -Name "pull_competitor_branches.py --pull --merge (competitor census)" `
                    -Command (New-PyCommand "pull_competitor_branches.py" @("--pull", "--merge")) -WorkDir $PipeDir
if ($code -eq 0) { Add-Result "competitor census" "OK" ((Get-Date) - $t0).TotalSeconds }
else {
    Write-Log "WARN: competitor store-locator pull failed (sites move/block sometimes). Continuing with the committed census."
    Add-Result "competitor census" "WARN" ((Get-Date) - $t0).TotalSeconds
}

# 2d. OPTIONAL long batch: Overture 3D building catchments for every province (hours; resumable).
if ($Provinces) {
    $t0 = Get-Date
    $code = Invoke-Step -Name "pull_all_provinces.py --max-buildings 60000 (Overture 3D batch)" `
                        -Command (New-PyCommand "pull_all_provinces.py" @("--max-buildings", "60000")) -WorkDir $PipeDir
    if ($code -eq 0) { Add-Result "Overture province batch" "OK" ((Get-Date) - $t0).TotalSeconds }
    else {
        Write-Log "WARN: Overture province batch had failures (it skips finished provinces on re-run). Continuing."
        Add-Result "Overture province batch" "WARN" ((Get-Date) - $t0).TotalSeconds
    }
} else {
    Write-Log "Overture 3D province batch: SKIPPED (run with -Provinces to enable; it can take hours)."
    Add-Result "Overture province batch" "SKIP" 0
}

# ---------------------------------------------------------------------------
# 3. Deterministic derive chain (order mirrors pipeline/refresh_all.sh).
#    Each builder is re-run then --check'd byte-exact. A builder that exits non-zero but whose
#    --check still passes only lost an OPTIONAL upstream source (e.g. overture_places.json is
#    kept local-only) -> SKIP, not a failure. Real failures BLOCK the commit.
# ---------------------------------------------------------------------------
$script:DeriveFailed = $false

function Invoke-Builder {
    param([string]$Script, [string]$Label)
    $path = Join-Path $PipeDir $Script
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Log "builder $Script not present in this tree — skipped."
        Add-Result $Label "SKIP" 0
        return
    }
    $t0 = Get-Date
    $run = Invoke-Step -Name "$Script (rebuild)" -Command (New-PyCommand $Script) -WorkDir $PipeDir
    $chk = Invoke-Step -Name "$Script --check"   -Command (New-PyCommand $Script @("--check")) -WorkDir $PipeDir
    $secs = ((Get-Date) - $t0).TotalSeconds
    if ($run -eq 0 -and $chk -eq 0) {
        Add-Result $Label "OK" $secs
    } elseif ($run -ne 0 -and $chk -eq 0) {
        # skip-pass: optional upstream source absent; committed output is unchanged + still exact.
        Write-Log "NOTE: $Script no-op'd (optional upstream source absent) but --check passes — SKIP, not a failure."
        Add-Result $Label "SKIP" $secs
    } else {
        Write-Log "FAIL: $Script did not reproduce byte-exact (or crashed). This BLOCKS the commit."
        Add-Result $Label "FAIL" $secs
        $script:DeriveFailed = $true
    }
}

Invoke-Builder "derive.py"                   "derive (master -> branches/meta)"
Invoke-Builder "build_amphoe.py"             "build_amphoe (928 districts)"
Invoke-Builder "build_province.py"           "build_province (77 deep-dives)"
Invoke-Builder "build_crop_stress.py"        "build_crop_stress (agri stress)"
Invoke-Builder "build_occupations.py"        "build_occupations (optional src)"
Invoke-Builder "build_amphoe_occupations.py" "build_amphoe_occupations (optional src)"
Invoke-Builder "build_opportunity_score.py"  "build_opportunity_score (composite)"

if ($script:DeriveFailed) {
    Stop-Autopilot ("one or more derive builders FAILED — platform/data may be inconsistent, so nothing " +
                    "was committed. Pulled raw data is still on disk (pipeline/dgt_out, source-data). " +
                    "Read the log above, or hand the log to Claude Code.")
}

# ---------------------------------------------------------------------------
# 4. QA gate — bash tests/run.sh check (only if bash exists, e.g. Git Bash)
# ---------------------------------------------------------------------------
$bash = Get-Command bash -ErrorAction SilentlyContinue
if ($bash) {
    $t0 = Get-Date
    $code = Invoke-Step -Name "tests/run.sh check (QA gate)" -Command @("bash", "tests/run.sh", "check") -WorkDir $RepoRoot
    if ($code -eq 0) { Add-Result "QA gate" "OK" ((Get-Date) - $t0).TotalSeconds }
    else {
        Add-Result "QA gate" "FAIL" ((Get-Date) - $t0).TotalSeconds
        Stop-Autopilot ("QA gate failed — NOT committing possibly-broken data. Pulled raw inputs are safe on " +
                        "disk. Re-run after a fix, or hand pipeline/autopilot_log.txt to Claude Code.")
    }
} else {
    Write-Log "NOTE: bash not found on PATH — QA gate skipped. (Install Git for Windows' Git Bash to enable it.)"
    Add-Result "QA gate" "SKIP" 0
}

# ---------------------------------------------------------------------------
# 5. Commit + push (add only data dirs; nothing destructive; retry push once rebased)
# ---------------------------------------------------------------------------
$t0 = Get-Date
Invoke-Step -Name "git add source-data/ platform/data/" -Command @("git", "add", "--", "source-data", "platform/data") | Out-Null
# (gitignore keeps secrets/synthetic/raw caches out: .env, dgt_out/, overture tiles, synthetic tape, this log.)

& git diff --cached --quiet 2>&1 | Out-Null
$hasStaged = ($LASTEXITCODE -ne 0)
if (-not $hasStaged) {
    Write-Log "Nothing new to commit — data unchanged since the last run. Done."
    Add-Result "commit+push" "SKIP" ((Get-Date) - $t0).TotalSeconds
    Write-Summary
    Write-Log "AUTOPILOT DONE (no changes)."
    exit 0
}

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
$statusLines = @()
foreach ($r in $script:StepResults) { $statusLines += ("- {0}: {1}" -f $r.Name, $r.Status) }
$code = Invoke-Step -Name "git commit" -Command @(
    "git", "commit",
    "-m", "data: Thai-IP desktop autopilot refresh ($stamp)",
    "-m", "Unattended session via pipeline/desktop_autopilot.ps1 (gov sweep + competitor census + derive chain).",
    "-m", ($statusLines -join "`n")
)
if ($code -ne 0) { Stop-Autopilot "git commit failed — see log. Staged changes were left staged; nothing lost." }

if ($NoPush) {
    Write-Log "Push SKIPPED (-NoPush). Commit is local on $Branch."
    Add-Result "commit+push" "OK" ((Get-Date) - $t0).TotalSeconds
    Write-Summary
    Write-Log "AUTOPILOT DONE (committed locally, not pushed)."
    exit 0
}

$pushed = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    $code = Invoke-Step -Name "git push (attempt $attempt/3)" -Command @("git", "push", "-u", "origin", $Branch)
    if ($code -eq 0) { $pushed = $true; break }
    Write-Log "push rejected — pulling with rebase and retrying..."
    $code = Invoke-Step -Name "git pull --rebase (push retry)" -Command @("git", "pull", "--rebase", "origin", $Branch)
    if ($code -ne 0) {
        Invoke-Step -Name "git rebase --abort (cleanup)" -Command @("git", "rebase", "--abort") | Out-Null
        Stop-Autopilot ("push retry hit a rebase conflict. Your commit is SAFE locally on $Branch — " +
                        "push it by hand after resolving: 'git pull --rebase origin $Branch' then 'git push'.")
    }
}
if ($pushed) {
    Add-Result "commit+push" "OK" ((Get-Date) - $t0).TotalSeconds
    Write-Summary
    Write-Log "AUTOPILOT DONE — refreshed data committed and pushed to origin/$Branch."
    exit 0
} else {
    Add-Result "commit+push" "FAIL" ((Get-Date) - $t0).TotalSeconds
    Stop-Autopilot ("push failed 3 times (network/credentials?). Your commit is SAFE locally on $Branch — " +
                    "run 'git push -u origin $Branch' by hand when online.")
}
