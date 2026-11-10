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
    & ".\.venv\Scripts\python.exe" -c "from agent.__main__ import default_cert_is_stale; raise SystemExit(2 if default_cert_is_stale() else 0)"
    if ($LASTEXITCODE -eq 2) {
        Write-Host "The HTTPS certificate does not include this server's name or IP. Creating a new one."
        & ".\enable-https.ps1"
    } else {
        Write-Host "Keeping the HTTPS certificate already on this server."
    }
} else {
    & ".\enable-https.ps1"
}

Write-Host ""
Write-Host "Installed in $Root"
Write-Host "Start:  .\start.ps1"
Write-Host "Guide:  INSTALL.md"
Write-Host ""

function Install-VoceService {
    foreach ($path in @(
        $Root,
        (Join-Path $Root ".venv"),
        (Join-Path $Root "agent"),
        (Join-Path $Root "config"),
        (Join-Path $Root "data"),
        (Join-Path $Root "out"),
        (Join-Path $Root ".env")
    )) {
        if (Test-Path $path) {
            icacls $path /grant "SYSTEM:(OI)(CI)M" | Out-Null
        }
    }
    $runner = Join-Path $Root "run-service.ps1"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`"" -WorkingDirectory $Root
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $trigger.Delay = "PT30S"
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName "VOCE" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host "Task Scheduler task VOCE stays in the Running state while the site is up."
    Write-Host "It starts 30 seconds after boot and starts again if it stops."
}

if ($Service) {
    try {
        Install-VoceService
        Start-ScheduledTask -TaskName "VOCE"
    } catch {
        Write-Host "Could not register the startup task. Open PowerShell as Administrator and run .\install.ps1 -Service"
        Write-Host $_.Exception.Message
    }
}

if ($Start) {
    & ".\start.ps1"
}
