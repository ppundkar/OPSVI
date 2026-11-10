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

$listening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($listening) {
    Write-Host "VOCE is already running on port $port."
    Write-Host "Closing this window does not stop it."
    & $python -c "from agent.__main__ import print_browse_urls; print_browse_urls()"
    exit 0
}

$outDir = Join-Path $PSScriptRoot "out"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$stdout = Join-Path $outDir "voce.log"
$stderr = Join-Path $outDir "voce.err.log"
Start-Process -FilePath $python -ArgumentList "-m", "agent" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Start-Sleep -Seconds 2
$listening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $listening) {
    Write-Host "VOCE did not stay running. The last lines of the log:"
    if (Test-Path $stderr) { Get-Content $stderr -Tail 20 }
    exit 1
}
Write-Host "VOCE is running in the background. Closing this window does not stop it."
Write-Host "Log: $stdout"
& $python -c "from agent.__main__ import print_browse_urls; print_browse_urls()"
