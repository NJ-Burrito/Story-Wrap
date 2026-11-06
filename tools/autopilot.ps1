# The StoryWrap-Autopilot task action (owner, 2026-10-27): make sure VS Code is open on this checkout, run the autopilot headless, and if it ends in a state that needs
# judgement (exit code 6), start ONE headless Lead session. Registered by tools\register-autopilot.ps1; it can also be run by hand.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot.ps1               do it
#   powershell -ExecutionPolicy Bypass -File tools\autopilot.ps1 -PlanOnly     print the commands as JSON and do nothing (the same shape as autopilot.launch_plan; a test keeps them equal)
#
# (a) VS Code: if no Code.exe runs, start it on the project folder (`code` from PATH, else %LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe).
# (b) `uv run tools/daily.py autopilot` (it starts the headless Claude jobs itself through daily.build_cmd: writer, critic, healer). It never posts.
# (c) exit code 6 (NEEDS-LEAD): `uv run tools/daily.py autopilot --lead` once: a headless Sonnet session (NJ_ROLE=job, dontAsk, capped turns and budget, no shell) that reads
#     handoff.md and the log, writes work\daily\autopilot-lead-<date>.md and one repair decision, which the autopilot executes. It never commits, posts or loosens a gate.
# Exit code = the autopilot's (0 done / waiting / idle, 1 stage failed, 3 token budget, 4 render cap, 5 paid service), or the Lead repair's.
param([switch]$PlanOnly, [switch]$CodeRunning, [string]$CodePath, [string]$LocalAppData, [string]$Uv)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$tokens = "5000000"          # SW_LLM_DAILY_TOKENS of autopilot runs (the owner 2026-10-28: 5 M a day; one episode used about 1 M)

function Get-AutopilotPlan([string]$Root, [string]$UvExe, [bool]$Running, [string]$OnPath, [string]$LocalApp) {
    $exe = if ($OnPath) { $OnPath } elseif ($LocalApp) { Join-Path $LocalApp "Programs\Microsoft VS Code\Code.exe" } else { $null }
    $vscode = if ($Running -or -not $exe) { $null } else { @($exe, $Root) }
    [ordered]@{
        vscode    = $vscode
        autopilot = @($UvExe, "run", "tools/daily.py", "autopilot")
        lead      = @($UvExe, "run", "tools/daily.py", "autopilot", "--lead")
        env       = [ordered]@{ PYTHONUTF8 = "1"; SW_LLM_DAILY_TOKENS = $tokens }
    }
}

if ($PlanOnly) {
    $u = if ($Uv) { $Uv } else { "uv" }
    $la = if ($PSBoundParameters.ContainsKey("LocalAppData")) { $LocalAppData } else { $env:LOCALAPPDATA }
    Get-AutopilotPlan $root $u $CodeRunning.IsPresent $CodePath $la | ConvertTo-Json -Depth 4
    return
}

$uvExe = if ($Uv) { $Uv } else { (Get-Command uv).Source }
$codeCmd = (Get-Command code -ErrorAction SilentlyContinue | Select-Object -First 1).Source
$running = [bool](Get-Process -Name "Code" -ErrorAction SilentlyContinue)
$plan = Get-AutopilotPlan $root $uvExe $running $codeCmd $env:LOCALAPPDATA
$log = Join-Path $root "work\daily\task-autopilot.log"
New-Item -ItemType Directory -Force (Join-Path $root "work\daily") | Out-Null
Set-Location $root
$env:PYTHONUTF8 = "1"
$env:SW_LLM_DAILY_TOKENS = $tokens

function Say([string]$m) { Add-Content -Path $log -Value ("{0} [autopilot.ps1] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) -Encoding UTF8 }

if ($plan.vscode) {
    try { Start-Process -FilePath $plan.vscode[0] -ArgumentList ('"' + $plan.vscode[1] + '"'); Say "VS Code was not running: started on $root"; Start-Sleep -Seconds 10 }
    catch { Say "VS Code could not be started: $($_.Exception.Message)" }      # the autopilot does not need the window: go on
} else { Say "VS Code is already running (or no launcher was found)" }

function Run-Step([string[]]$cmd) {
    # Start-Process with redirected files: no quoting trap, no PowerShell wrapping of stderr, UTF-8 kept (Arabic). Waited for; the exit code is the child's.
    $o = Join-Path $root "work\daily\task-autopilot.out.tmp"; $e = Join-Path $root "work\daily\task-autopilot.err.tmp"
    $p = Start-Process -FilePath $cmd[0] -ArgumentList ($cmd[1..($cmd.Length - 1)]) -WorkingDirectory $root -NoNewWindow -Wait -PassThru -RedirectStandardOutput $o -RedirectStandardError $e
    foreach ($f in @($o, $e)) { if (Test-Path $f) { Add-Content -Path $log -Value (Get-Content $f -Raw -Encoding UTF8) -Encoding UTF8; Remove-Item $f -Force } }
    return $p.ExitCode
}

$rc = Run-Step $plan.autopilot
Say "autopilot exit $rc"
if ($rc -eq 6) {
    $rc = Run-Step $plan.lead
    Say "Lead repair exit $rc"
}
exit $rc
