[CmdletBinding()]
param(
    [string]$TaskName = "TimeTagger Scheduler",
    [datetime]$StartAt = (Get-Date).AddMinutes(1)
)

$ErrorActionPreference = "Stop"
$Runner = Join-Path $PSScriptRoot "run-scheduler.ps1"

if (-not (Test-Path -LiteralPath $Runner)) {
    throw "Runner script not found at $Runner."
}

$PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$ActionArguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $Runner
$Action = New-ScheduledTaskAction `
    -Execute $PowerShell `
    -Argument $ActionArguments `
    -WorkingDirectory (Split-Path -Parent $PSScriptRoot)

$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $StartAt `
    -RepetitionInterval (New-TimeSpan -Hours 12)

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Materialize the TimeTagger schedule every 12 hours." `
    -Force | Out-Null

Write-Host "Installed scheduled task '$TaskName'."
Write-Host "First run: $StartAt; repeats every 12 hours."

