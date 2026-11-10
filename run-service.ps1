$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$logDir = Join-Path $PSScriptRoot "out"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "voce-service.log"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Write-Log([string]$Message) {
    "$(Get-Date -Format o) $Message" | Out-File -FilePath $log -Append -Encoding utf8
}

if (-not (Test-Path $python)) {
    Write-Log "Python was not found at $python. Run install.ps1 first."
    exit 1
}

Write-Log "VOCE service starting"
& $python -m agent >> $log 2>&1
$code = $LASTEXITCODE
if ($null -eq $code) { $code = 1 }
Write-Log "VOCE service exited with code $code"
exit $code
