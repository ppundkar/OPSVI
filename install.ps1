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

Write-Host ""
Write-Host "Installed in $Root"
Write-Host "Start:  .\start.ps1"
Write-Host "Admin:  http://127.0.0.1:8080/admin"
Write-Host "Guide:  INSTALL.md"
Write-Host ""

if ($Service) {
    $task = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Root\start.ps1`""
    schtasks /Create /TN "VMware Cost Agent" /SC ONSTART /RL LIMITED /F /TR $task | Out-Host
    Write-Host "Startup task 'VMware Cost Agent' registered."
}

if ($Start) {
    & ".\start.ps1"
}
