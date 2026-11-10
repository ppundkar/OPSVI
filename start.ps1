$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Run .\install.ps1 first."
}

$port = 8080
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^VCO_PORT=(\d+)$') { $port = [int]$Matches[1] }
    }
}

function Test-VoceListening {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
}

$task = Get-ScheduledTask -TaskName "VOCE" -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "The VOCE startup task is not registered, so the site stops when Windows restarts."
    Write-Host "Open PowerShell as Administrator in this folder and run:"
    Write-Host "  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Service"
    exit 1
}

if ($task.State -eq "Running" -and (Test-VoceListening)) {
    Write-Host "VOCE is already running. Task Scheduler shows task VOCE as Running."
    & $python -c "from agent.__main__ import print_browse_urls; print_browse_urls()"
    exit 0
}

if (Test-VoceListening) {
    Write-Host "Stopping a copy of VOCE that is not the scheduled task."
    $owners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($procId in $owners) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

Start-ScheduledTask -TaskName "VOCE"
$ready = $false
foreach ($try in 1..15) {
    Start-Sleep -Seconds 1
    $task = Get-ScheduledTask -TaskName "VOCE"
    if ($task.State -eq "Running" -and (Test-VoceListening)) {
        $ready = $true
        break
    }
}
if (-not $ready) {
    Write-Host "Task VOCE did not stay running. The last lines of out\voce-service.log:"
    $log = Join-Path $PSScriptRoot "out\voce-service.log"
    if (Test-Path $log) { Get-Content $log -Tail 30 }
    exit 1
}
Write-Host "VOCE is running. Task Scheduler shows task VOCE as Running."
Write-Host "Closing this window does not stop it, and it starts again after boot."
& $python -c "from agent.__main__ import print_browse_urls; print_browse_urls()"
