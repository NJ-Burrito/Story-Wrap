# Registers StoryWrap-Watch: the engagement watcher (tools/watch.py) as a per-user task that starts at logon and keeps running (the owner 2026-10-27, R-481).
# No admin needed: a per-user task, LogonType Interactive, runs only while the user is logged on. Restarts on failure (3 times, 1 min apart).
# The hourly StoryWrap-Engage task is NOT touched: it stays as the safety net.
#
#   Review:     powershell -ExecutionPolicy Bypass -File tools\register-watch.ps1 -DryRun
#   Register:   powershell -ExecutionPolicy Bypass -File tools\register-watch.ps1            (also starts it now unless -NoStart)
#   Remove:     powershell -ExecutionPolicy Bypass -File tools\register-watch.ps1 -Unregister  (stops it and removes the task)
# The task points at the checkout this script lives in (after the merge: <repo>), never at a worktree unless you run it from one.
param([switch]$DryRun, [switch]$Unregister, [switch]$NoStart)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$name = "StoryWrap-Watch"

function Stop-Watcher {
    # Only the watcher this task started: the python whose command line names tools\watch.py in this checkout. Nothing else is touched.
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" | Where-Object { $_.CommandLine -match [regex]::Escape("tools\watch.py") -and $_.CommandLine -match [regex]::Escape($root) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output "Stopped watcher pid $($_.ProcessId)" }
}

if ($Unregister) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Output "Removed $name"
    }
    Stop-Watcher
    $lock = Join-Path $root "work\engage\watch.lock"
    if (Test-Path $lock) { Remove-Item $lock -Force }
    return
}

$uv = if ($DryRun) { "uv" } else { (Get-Command uv).Source }
New-Item -ItemType Directory -Force (Join-Path $root "work\engage") | Out-Null
$log = Join-Path $root "work\engage\watch-console.log"
# conhost --headless: no window. PYTHONUTF8 is mandatory (Arabic). Same pattern as tools\register-tasks.ps1.
$arg = "--headless cmd.exe /c set `"PYTHONUTF8=1`"&& cd /d `"$root`" && `"$uv`" run tools/watch.py >> `"$log`" 2>&1"
if ($DryRun) { Write-Output "[dry run] ${name}: at logon of $env:USERNAME, restart on failure; conhost.exe $arg"; return }

$action = New-ScheduledTaskAction -Execute "conhost.exe" -Argument $arg -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Story-Wrap: engagement watcher (polls platform notification signals, runs an engage tick on change)" -Force | Out-Null
Write-Output "Registered $name (at logon, Interactive, per-user). Log: $root\work\engage\watch.log"
if (-not $NoStart) { Start-ScheduledTask -TaskName $name; Write-Output "Started $name" }
