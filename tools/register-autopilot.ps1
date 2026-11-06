# Registers StoryWrap-Autopilot and re-times the daily loop (owner, 2026-10-27: "always push at 7pm, harvest the comments at 2pm the next day, and start the next episode
# immediately without coming back to me; make it an automation schedule that triggers you, and if the session is closed and VS Code is not open, open it and start you").
#
#   Review:     powershell -ExecutionPolicy Bypass -File tools\register-autopilot.ps1 -DryRun        (prints what would change; changes nothing)
#   Register:   powershell -ExecutionPolicy Bypass -File tools\register-autopilot.ps1
#   Undo:       powershell -ExecutionPolicy Bypass -File tools\register-autopilot.ps1 -Unregister    (removes StoryWrap-Autopilot, re-enables StoryWrap-Daily; the Post task stays at 19:00)
#
# What it does (the times come from board\schedule.json, the one source):
#   1. creates the per-user task StoryWrap-Autopilot (no admin needed): it ticks every 15 min AROUND THE CLOCK, indefinitely (owner, 2026-10-30, R-505: the old trigger stopped at 18:30
#      and a stop after that waited until the next 14:00 until a person asked). A tick with nothing due logs one idle line and ends; the 14:00 harvest is decided in the code
#      (tools/autopilot.py decide), not by the trigger. Action = tools\autopilot.ps1 (opens VS Code if it is closed, runs `daily.py autopilot` headless, starts one headless Lead session on
#      exit code 6). Settings: Run only when the user is logged on (Interactive, needed to open VS Code), StartWhenAvailable (a missed tick runs at the next logon), NO WakeToRun (a tick every
#      15 min must not wake a sleeping PC all night; the first tick after it wakes catches up), no overlap (IgnoreNew), execution limit 5 h.
#      The Lead runs this script once after the merge of fix/autorun-1030; running it again is safe (-Force replaces the task).
#   2. DISABLES StoryWrap-Daily (the old 10:00 / 12:00 / 14:00 `daily.py run`): the autopilot replaces it.
#   3. moves the StoryWrap-Post trigger to 19:00 (daily, every 5 min until 20:25, retries only; the action and settings are kept). If Post is not registered yet, run
#      tools\register-tasks.ps1 first (it registers Post, Harvest, Board, Health at the same times).
# StoryWrap-Harvest (hourly :35) is left as the safety net for the 14:00 harvest. The task points at the checkout this script lives in (after the merge: <repo>).
param([switch]$DryRun, [switch]$Unregister)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$schedPath = Join-Path $root "board\schedule.json"
if (-not (Test-Path $schedPath)) { $schedPath = Join-Path $root "config\schedule.example.json" }   # no own schedule yet: the shipped example
$sched = Get-Content $schedPath -Raw -Encoding UTF8 | ConvertFrom-Json
$name = "StoryWrap-Autopilot"
$a = $sched.tasks.$name
$p = $sched.tasks."StoryWrap-Post"
$launcher = Join-Path $root "tools\autopilot.ps1"

function Has-Task([string]$n) { [bool](Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue) }

if ($Unregister) {
    if ($DryRun) { Write-Output "[dry run] would remove $name and re-enable StoryWrap-Daily"; return }
    if (Has-Task $name) { Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName $name -Confirm:$false; Write-Output "Removed $name" }
    if (Has-Task "StoryWrap-Daily") { Enable-ScheduledTask -TaskName "StoryWrap-Daily" | Out-Null; Write-Output "Re-enabled StoryWrap-Daily" }
    $lock = Join-Path $root "work\daily\autopilot.lock"
    if (Test-Path $lock) { Write-Output "Note: $lock exists (a run may be live); it is not removed here." }
    return
}

# --- 1. StoryWrap-Autopilot
$limit = New-TimeSpan -Minutes ([int]([double]$a.limit_h * 60))
# first tick: the next every_min mark counted from the schedule's `from`; repeats for 3650 days (the way register-tasks.ps1 registers the Board task)
$fp = $a.from.Split(":")
$first = (Get-Date).Date.AddHours([int]$fp[0]).AddMinutes([int]$fp[1])
while ($first -lt (Get-Date).AddMinutes(1)) { $first = $first.AddMinutes([int]$a.every_min) }
$trg = New-ScheduledTaskTrigger -Once -At $first -RepetitionInterval (New-TimeSpan -Minutes ([int]$a.every_min)) -RepetitionDuration (New-TimeSpan -Days 3650)
$arg = "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$launcher`""
$user = "$env:USERDOMAIN\$env:USERNAME"
# --- 3. StoryWrap-Post: the new trigger
$ptrg = New-ScheduledTaskTrigger -Daily -At $p.from
$ptrg.Repetition = (New-ScheduledTaskTrigger -Once -At $p.from -RepetitionInterval (New-TimeSpan -Minutes ([int]$p.every_min)) -RepetitionDuration (New-TimeSpan -Minutes ([int]([double]$p.for_h * 60)))).Repetition

if ($DryRun) {
    Write-Output "[dry run] $name : every $($a.every_min) min around the clock (first $($first.ToString('HH:mm')), repeats for 3650 days); per-user ($user, no admin), LogonType Interactive (run only when logged on), StartWhenAvailable, no WakeToRun, MultipleInstances IgnoreNew, limit $($a.limit_h) h"
    Write-Output "    action: conhost.exe $arg   (working dir $root)"
    Write-Output ("[dry run] StoryWrap-Daily : " + $(if (Has-Task "StoryWrap-Daily") { "would be DISABLED (replaced by the autopilot)" } else { "not registered: nothing to disable" }))
    Write-Output ("[dry run] StoryWrap-Post : " + $(if (Has-Task "StoryWrap-Post") { "trigger would become daily at $($p.from), every $($p.every_min) min for $($p.for_h) h (last tick 20:25); action and settings kept" } else { "not registered: run tools\register-tasks.ps1 first" }))
    return
}

$action = New-ScheduledTaskAction -Execute "conhost.exe" -Argument $arg -WorkingDirectory $root
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit $limit
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
New-Item -ItemType Directory -Force (Join-Path $root "work\daily") | Out-Null
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trg -Settings $settings -Principal $principal -Description ("Story-Wrap: " + $a.what) -Force | Out-Null
Write-Output "Registered $name (every $($a.every_min) min around the clock from $($first.ToString('HH:mm')), Interactive, StartWhenAvailable, IgnoreNew, limit $($a.limit_h) h)"

# --- 2. StoryWrap-Daily off
if (Has-Task "StoryWrap-Daily") { Disable-ScheduledTask -TaskName "StoryWrap-Daily" | Out-Null; Write-Output "Disabled StoryWrap-Daily (the autopilot replaces it)" }
else { Write-Output "StoryWrap-Daily is not registered: nothing to disable" }

# --- 3. StoryWrap-Post to 19:00
if (Has-Task "StoryWrap-Post") { Set-ScheduledTask -TaskName "StoryWrap-Post" -Trigger $ptrg | Out-Null; Write-Output "StoryWrap-Post trigger set: daily $($p.from), every $($p.every_min) min for $($p.for_h) h (last tick 20:25)" }
else { Write-Output "StoryWrap-Post is not registered: run tools\register-tasks.ps1 (it registers Post at $($p.from))" }
