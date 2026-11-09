param(
    [switch]$Start,
    [switch]$Service
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python 3.11 or newer is required. Install it, then reopen PowerShell so 'python' is on PATH."
}

& $python.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.11 or newer is required. The python on PATH is older."
}

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    & $python.Source -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
New-Item -ItemType Directory -Force -Path ".\data", ".\out" | Out-Null
if (-not (Test-Path ".\.env")) {
    Copy-Item ".\.env.example" ".\.env"
}

$configuredCert = ""
foreach ($line in Get-Content ".\.env") {
    if ($line -match '^VCO_SSL_CERTFILE=(.+)$') { $configuredCert = $Matches[1].Trim() }
}
$certExists = $false
if ($configuredCert) {
    $certExists = Test-Path $configuredCert
}
if (-not $certExists) {
    $certExists = (Test-Path ".\data\tls\cert.pem") -and (Test-Path ".\data\tls\key.pem")
}
if ($certExists) {
    Write-Host "Keeping the HTTPS certificate already on this server."
} else {
    & ".\enable-https.ps1"
}

Write-Host ""
Write-Host "Installed in $Root"
Write-Host "Start:  .\start.ps1"
& ".\.venv\Scripts\python.exe" -c "from agent.__main__ import print_browse_urls; print_browse_urls()"
Write-Host "Guide:  INSTALL.md"
Write-Host ""

if ($Service) {
    $task = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Root\start.ps1`""
    schtasks /Create /TN "VOCE" /SC ONSTART /RL LIMITED /F /TR $task | Out-Host
    Write-Host "Startup task 'VOCE' registered."
}

if ($Start) {
    & ".\start.ps1"
}
