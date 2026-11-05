<#
.SYNOPSIS
    Run a VMware cost optimization pass through the local agent.

.DESCRIPTION
    -Demo analyzes the built-in estate.
    -UseConfig asks the agent to log in to every system in config/endpoints.yaml.
    -CollectVCenter runs PowerCLI on this host and submits that inventory.
    The agent calculates savings, writes HTML and CSV, and can notify Teams or Power BI.

.PARAMETER Agent
    Base URL of the cost agent. Default is http://127.0.0.1:8080.

.PARAMETER Demo
    Analyze the included demo estate.

.PARAMETER UseConfig
    Collect live endpoints from config/endpoints.yaml.

.PARAMETER CollectVCenter
    Collect this host's vCenter with PowerCLI and submit the inventory.

.PARAMETER VCenter
    vCenter host used with -CollectVCenter. Defaults to VCO_VCENTER_HOST.

.PARAMETER NotifyTeams
    Send the Teams card after the analysis.

.PARAMETER PushPowerBI
    Push the Power BI dataset after the analysis.

.PARAMETER Refresh
    Bypass the agent's short-lived cache.
#>
[CmdletBinding()]
param(
    [string]$Agent = "http://127.0.0.1:8080",
    [switch]$Demo,
    [switch]$UseConfig,
    [switch]$CollectVCenter,
    [string]$VCenter = $env:VCO_VCENTER_HOST,
    [switch]$NotifyTeams,
    [switch]$PushPowerBI,
    [switch]$Refresh,
    [string]$ApiKey = $env:VCO_API_KEY
)

$ErrorActionPreference = "Stop"
$chosen = @(@($Demo, $UseConfig, $CollectVCenter) | Where-Object { $_ })
if ($chosen.Count -ne 1) {
    throw "Choose exactly one of -Demo, -UseConfig, or -CollectVCenter"
}

$headers = @{ "Content-Type" = "application/json" }
if ($ApiKey) { $headers["X-API-Key"] = $ApiKey }

function Convert-Flag([bool]$Value) {
    if ($Value) { return "true" }
    return "false"
}

if ($CollectVCenter) {
    if (-not $VCenter) { throw "Pass -VCenter or set VCO_VCENTER_HOST" }
    if (-not $env:VCO_USERNAME -or -not $env:VCO_PASSWORD) {
        throw "Set VCO_USERNAME and VCO_PASSWORD for the vCenter collection"
    }
    $collector = Join-Path $PSScriptRoot "Collect-VCenter.ps1"
    $json = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $collector -Server $VCenter -Deep
    if ($json -is [array]) { $json = $json -join "" }
    $json = [string]$json
    if ($json.Trim().Length -eq 0) { throw "PowerCLI collection returned no inventory" }
    $body = '{"inventory":' + $json.Trim() + ',"include_ai":true,"refresh":true,"notify_teams":' + (Convert-Flag $NotifyTeams) + ',"push_powerbi":' + (Convert-Flag $PushPowerBI) + '}'
} elseif ($Demo) {
    $body = '{"demo":true,"include_ai":true,"refresh":' + (Convert-Flag $Refresh) + ',"notify_teams":' + (Convert-Flag $NotifyTeams) + ',"push_powerbi":' + (Convert-Flag $PushPowerBI) + '}'
} else {
    $body = '{"use_config":true,"include_ai":true,"refresh":' + (Convert-Flag $Refresh) + ',"notify_teams":' + (Convert-Flag $NotifyTeams) + ',"push_powerbi":' + (Convert-Flag $PushPowerBI) + '}'
}

$response = Invoke-RestMethod -Method Post -Uri ($Agent.TrimEnd("/") + "/v1/optimize") -Headers $headers -Body $body -TimeoutSec 180

[PSCustomObject]@{
    AnalysisId = $response.analysis_id
    CommittedMonthly = $response.summary.conservative_monthly_usd
    Annual = $response.summary.annual_conservative_usd
    Findings = $response.summary.finding_count
    DurationMs = $response.duration_ms
    Partial = $response.partial
    Html = $response.exports.html_path
    Csv = $response.exports.csv_path
    Teams = $response.teams.status
    PowerBI = $response.powerbi.status
} | Format-List
