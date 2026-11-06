# Registers the Story-Wrap Windows scheduled tasks (modelled on the Linkedin project's register-task.ps1).
# The times live in board/schedule.json (one source: this script, the board's Schedule tab and a test read it).
#
#   Review first:  powershell -ExecutionPolicy Bypass -File tools\register-tasks.ps1 -DryRun
#   Register:      powershell -ExecutionPolicy Bypass -File tools\register-tasks.ps1
#   With the board server at logon:   ... -File tools\register-tasks.ps1 -WithServer
#   Remove all:    powershell -ExecutionPolicy Bypass -File tools\register-tasks.ps1 -Remove
#
# Tasks: StoryWrap-Post (fixed 19:00 on every platform; ticks every 5 min to 20:25 only to retry), StoryWrap-Harvest (safety net: 14:00 the day after the later post, 24 h ideas pass),
# StoryWrap-Board (refresh board data), StoryWrap-Health. StoryWrap-Autopilot (14:00 harvest and the next episode; replaces StoryWrap-Daily) is in schedule.json for the board but is
# registered by tools\register-autopilot.ps1 (it needs a logged-on principal and the VS Code launcher), so this script skips every task that has "registered_by". Every run writes work\daily\task-<name>.log.
# Registering is a decision for the Lead and the owner: nothing here runs at import and nothing is registered by tests.
param([switch]$DryRun, [switch]$Remove, [switch]$WithServer)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$schedPath = Join-Path $root "board\schedule.json"
if (-not (Test-Path $schedPath)) { $schedPath = Join-Path $root "config\schedule.example.json" }   # no own schedule yet: the shipped example
$sched = Get-Content $schedPath -Raw -Encoding UTF8 | ConvertFrom-Json
$names = @($sched.tasks.PSObject.Properties.Name)

if ($Remove) {
    foreach ($n in $names + "StoryWrap-BoardServer") {
        if (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $n -Confirm:$false; Write-Output "Removed $n" }
    }
    return
}

$uv = if ($DryRun) { "uv" } else { (Get-Command uv).Source }
New-Item -ItemType Directory -Force (Join-Path $root "work\daily") | Out-Null

foreach ($n in $names) {
    $t = $sched.tasks.$n
    if ($t.registered_by) { Write-Output ("[skip] {0}: registered by {1}" -f $n, $t.registered_by); continue }
    $log = Join-Path $root ("work\daily\task-" + $n.Substring(10).ToLower() + ".log")
    # conhost --headless: no console window flashes on the desktop. PYTHONUTF8 is mandatory (Arabic).
    $tail = $t.cmd -replace "^uv run ", ""
    $arg = "--headless cmd.exe /c set `"PYTHONUTF8=1`"&& cd /d `"$root`" && `"$uv`" run $tail >> `"$log`" 2>&1"
    $limit = New-TimeSpan -Minutes ([int]([double]$t.limit_h * 60))
    if ($t.kind -eq "daily") {
        $times = @($t.at) + @($t.extra_at | Where-Object { $_ })
        $triggers = @($times | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ })
        $when = "daily at " + ($times -join ", ")
    }
    elseif ($t.for_h) {
        $trg = New-ScheduledTaskTrigger -Daily -At $t.from
        $rep = (New-ScheduledTaskTrigger -Once -At $t.from -RepetitionInterval (New-TimeSpan -Minutes ([int]$t.every_min)) -RepetitionDuration (New-TimeSpan -Minutes ([int]([double]$t.for_h * 60)))).Repetition
        $trg.Repetition = $rep
        $triggers = @($trg)
        $when = "daily from $($t.from) every $($t.every_min) min for $($t.for_h) h"
    }
    else {
        $first = (Get-Date).Date.AddHours(0).AddMinutes(0)
        $parts = $t.from.Split(":")
        $at = (Get-Date).Date.AddHours([int]$parts[0]).AddMinutes([int]$parts[1])
        while ($at -lt (Get-Date).AddMinutes(1)) { $at = $at.AddMinutes([int]$t.every_min) }
        $triggers = @(New-ScheduledTaskTrigger -Once -At $at -RepetitionInterval (New-TimeSpan -Minutes ([int]$t.every_min)) -RepetitionDuration (New-TimeSpan -Days 3650))
        $when = "every $($t.every_min) min (first $($at.ToString('HH:mm')))"
    }
    if ($DryRun) { Write-Output ("[dry run] {0}: {1}; limit {2} h`n    conhost.exe {3}" -f $n, $when, $t.limit_h, $arg); continue }
    $action = New-ScheduledTaskAction -Execute "conhost.exe" -Argument $arg -WorkingDirectory $root
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit $limit
    Register-ScheduledTask -TaskName $n -Action $action -Trigger $triggers -Settings $settings -Description ("Story-Wrap: " + $t.what) -Force | Out-Null
    Write-Output ("Registered {0} ({1}). Log: {2}" -f $n, $when, $log)
}

if ($WithServer) {
    $pyw = Join-Path (Split-Path (Get-Command python).Source) "pythonw.exe"
    if ($DryRun) { Write-Output "[dry run] StoryWrap-BoardServer: at logon; $pyw board\serve.py (http://127.0.0.1:8771)"; return }
    $action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$root\board\serve.py`"" -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName "StoryWrap-BoardServer" -Action $action -Trigger $trigger -Settings $settings -Description "Story-Wrap board on 127.0.0.1:8771" -Force | Out-Null
    Write-Output "Registered StoryWrap-BoardServer (at logon). Open http://127.0.0.1:8771/"
}
