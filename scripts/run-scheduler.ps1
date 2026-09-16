[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Resolve everything relative to this script so Task Scheduler does not need a
# configured "Start in" directory.
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Scheduler = Join-Path $ProjectRoot ".venv\Scripts\timetagger-scheduler.exe"
$Config = Join-Path $ProjectRoot "config\schedule.yaml"
$EnvFile = Join-Path $ProjectRoot ".env"
$LogDirectory = Join-Path $ProjectRoot "logs"

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$LogFile = Join-Path $LogDirectory ("scheduler-{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))

function Write-TaskLog {
    param([string]$Message)
    Add-Content -LiteralPath $LogFile -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

try {
    if (-not (Test-Path -LiteralPath $Scheduler)) {
        throw "Scheduler executable not found at $Scheduler. Create the virtual environment first."
    }
    if (-not (Test-Path -LiteralPath $Config)) {
        throw "Schedule configuration not found at $Config."
    }
    if (-not (Test-Path -LiteralPath $EnvFile)) {
        throw ".env not found at $EnvFile. Copy .env.example and add the API URL and token."
    }

    # Load NAME=VALUE entries into this process only. Values are never logged.
    foreach ($Line in Get-Content -LiteralPath $EnvFile) {
        $Trimmed = $Line.Trim()
        if (-not $Trimmed -or $Trimmed.StartsWith("#")) {
            continue
        }

        $Separator = $Trimmed.IndexOf("=")
        if ($Separator -lt 1) {
            throw "Invalid entry in .env; expected NAME=VALUE."
        }

        $Name = $Trimmed.Substring(0, $Separator).Trim()
        $Value = $Trimmed.Substring($Separator + 1).Trim()
        if (($Value.StartsWith('"') -and $Value.EndsWith('"')) -or
            ($Value.StartsWith("'") -and $Value.EndsWith("'"))) {
            $Value = $Value.Substring(1, $Value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }

    $Arguments = @("--config", $Config)
    if ($DryRun) {
        $Arguments += "--dry-run"
    }

    Write-TaskLog "Starting TimeTagger Scheduler."
    & $Scheduler @Arguments *>> $LogFile
    $ExitCode = $LASTEXITCODE
    Write-TaskLog "TimeTagger Scheduler finished with exit code $ExitCode."
    exit $ExitCode
}
catch {
    Write-TaskLog ("ERROR: {0}" -f $_.Exception.Message)
    exit 1
}

