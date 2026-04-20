# Run SwitchBoard in development mode with auto-reload (PowerShell).
#Requires -Version 5.1

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir

Set-Location $RepoRoot

# Load .env if present
$EnvFile = Join-Path $RepoRoot '.env'
if (Test-Path $EnvFile) {
    Write-Host '[run_dev] Loading .env'
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*?)\s*=\s*(.*)\s*$') {
            $key   = $Matches[1].Trim()
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
        }
    }
}

$Port     = if ($env:SWITCHBOARD_PORT) { $env:SWITCHBOARD_PORT } else { '20401' }
$LogLevel = if ($env:LOG_LEVEL) { $env:LOG_LEVEL } else { 'info' }

Write-Host "[run_dev] Starting SwitchBoard on port $Port (reload enabled)"

uvicorn switchboard.app:app `
    --reload `
    --host 0.0.0.0 `
    --port $Port `
    --log-level $LogLevel
