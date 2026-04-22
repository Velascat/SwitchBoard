# Smoke test: hit each SwitchBoard endpoint and verify basic responses (PowerShell).
#Requires -Version 5.1

$ErrorActionPreference = 'Stop'

$BaseUrl = if ($env:SWITCHBOARD_URL) { $env:SWITCHBOARD_URL } else { 'http://localhost:20401' }
$Pass    = 0
$Fail    = 0

function Write-Pass { param([string]$Msg) Write-Host "  PASS  $Msg" -ForegroundColor Green }
function Write-Fail { param([string]$Msg) Write-Host "  FAIL  $Msg" -ForegroundColor Red  }

function Invoke-Check {
    param([string]$Description, [int]$ActualStatus, [int]$ExpectedStatus)
    if ($ActualStatus -eq $ExpectedStatus) {
        Write-Pass "$Description [HTTP $ActualStatus]"
        $script:Pass++
    } else {
        Write-Fail "$Description [expected HTTP $ExpectedStatus, got HTTP $ActualStatus]"
        $script:Fail++
    }
}

function Get-StatusCode {
    param([string]$Uri, [string]$Method = 'GET', [string]$Body = $null)
    try {
        $params = @{ Uri = $Uri; Method = $Method; UseBasicParsing = $true }
        if ($Body) {
            $params['Body']        = $Body
            $params['ContentType'] = 'application/json'
        }
        $resp = Invoke-WebRequest @params
        return $resp.StatusCode
    } catch [System.Net.WebException] {
        return [int]$_.Exception.Response.StatusCode
    }
}

Write-Host "SwitchBoard smoke tests → $BaseUrl"
Write-Host '-------------------------------------------'

# 1. Health check
Write-Host ''
Write-Host '1. GET /health'
$status = Get-StatusCode -Uri "$BaseUrl/health"
Invoke-Check 'GET /health returns 200' $status 200
try {
    $body = Invoke-RestMethod -Uri "$BaseUrl/health" -UseBasicParsing
    $body | ConvertTo-Json -Depth 5 | Write-Host
} catch { Write-Host "   (could not pretty-print response)" }

# 2. Model list
Write-Host ''
Write-Host '2. GET /v1/models'
$status = Get-StatusCode -Uri "$BaseUrl/v1/models"
Invoke-Check 'GET /v1/models returns 200' $status 200
try {
    $body = Invoke-RestMethod -Uri "$BaseUrl/v1/models" -UseBasicParsing
    $body | ConvertTo-Json -Depth 5 | Write-Host
} catch { Write-Host '   (could not pretty-print response)' }

# 3. Route selection
Write-Host ''
Write-Host '3. POST /route'
$payload = '{"task_id":"smoke-1","project_id":"switchboard-smoke","task_type":"documentation","execution_mode":"goal","goal_text":"Say hello.","target":{"repo_key":"docs","clone_url":"https://example.invalid/docs.git","base_branch":"main","allowed_paths":[]},"priority":"normal","risk_level":"low","constraints":{"allowed_paths":[],"require_clean_validation":true},"validation_profile":{"profile_name":"default","commands":[]},"branch_policy":{"push_on_success":true,"open_pr":false},"labels":[]}'
$status  = Get-StatusCode -Uri "$BaseUrl/route" -Method 'POST' -Body $payload
Invoke-Check 'POST /route returns 200' $status 200

# 4. Admin decisions
Write-Host ''
Write-Host '4. GET /admin/decisions/recent'
$status = Get-StatusCode -Uri "$BaseUrl/admin/decisions/recent?n=5"
Invoke-Check 'GET /admin/decisions/recent returns 200' $status 200
try {
    $body = Invoke-RestMethod -Uri "$BaseUrl/admin/decisions/recent?n=5" -UseBasicParsing
    $body | ConvertTo-Json -Depth 5 | Write-Host
} catch { Write-Host '   (could not pretty-print response)' }

# Summary
Write-Host ''
Write-Host '-------------------------------------------'
Write-Host "Results: $Pass passed, $Fail failed"
if ($Fail -gt 0) { exit 1 } else { exit 0 }
