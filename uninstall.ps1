param(
    [switch]$KeepConfig,
    [switch]$DeleteFolder
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Remove-TaskIfOurs([string]$Name) {
    $query = schtasks /Query /TN $Name /FO LIST /V 2>$null
    if ($LASTEXITCODE -ne 0) {
        return
    }
    schtasks /End /TN $Name 2>$null | Out-Null
    $text = ($query | Out-String)
    if ($text -like "*$Root*") {
        schtasks /Delete /TN $Name /F | Out-Null
        Write-Host "Removed scheduled task '$Name'."
    } else {
        Write-Host "Left scheduled task '$Name' because it points at another folder."
    }
}

function Stop-VoceProcess {
    $listeners = @()
    $port = 8080
    $envFile = Join-Path $Root ".env"
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match '^VCO_PORT=(\d+)$') { $port = [int]$Matches[1] }
        }
    }
    try {
        $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        $listeners = @()
    }
    $seen = @{}
    foreach ($procId in $listeners) {
        if (-not $procId -or $seen.ContainsKey($procId)) { continue }
        $seen[$procId] = $true
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        if ($proc -and $proc.CommandLine -and $proc.CommandLine -like "*$Root*") {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped process $procId listening on port $port."
        }
    }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.CommandLine -and $_.CommandLine -like "*$Root*" -and $_.CommandLine -like "*-m agent*") {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped VOCE process $($_.ProcessId)."
        }
    }
}

function Remove-DefaultCertificate {
    $cerPath = Join-Path $Root "data\tls\voce.cer"
    if (-not (Test-Path $cerPath)) {
        Write-Host "No default certificate file to remove from the Windows certificate store."
        return
    }
    $thumb = (New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $cerPath).Thumbprint
    foreach ($storeName in @("My", "Root")) {
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, "CurrentUser")
        $store.Open("ReadWrite")
        $matches = @($store.Certificates | Where-Object { $_.Thumbprint -eq $thumb })
        foreach ($item in $matches) {
            $store.Remove($item)
            Write-Host "Removed certificate $thumb from CurrentUser\$storeName."
        }
        $store.Close()
    }
}

Write-Host "Uninstalling VOCE in $Root"
Stop-VoceProcess
Remove-TaskIfOurs "VOCE"
Remove-TaskIfOurs "VOCE Scan"
Remove-DefaultCertificate

if ($KeepConfig) {
    if (Test-Path ".\.venv") {
        Remove-Item -Recurse -Force ".\.venv"
        Write-Host "Removed .venv. Kept .env, data, and out."
    }
} else {
    foreach ($path in @(".venv", ".env", "data", "out")) {
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path
            Write-Host "Removed $path"
        }
    }
}

Write-Host ""
Write-Host "VOCE is uninstalled from this folder."
Write-Host "Python, Git, and PowerCLI were left installed."
Write-Host "vCenter, NSX, Aria, and VCF were not changed."
Write-Host "If a browser on another computer trusted data\tls\voce.cer, remove that certificate there."
Write-Host "Saved endpoints and the HTTPS key are deleted unless you passed -KeepConfig."
Write-Host ""

if ($DeleteFolder) {
    $parent = Split-Path -Parent $Root
    Write-Host "Removing the project folder after this script exits."
    Start-Process -FilePath "cmd.exe" -WindowStyle Hidden -ArgumentList "/c", "timeout /t 2 /nobreak >nul & rmdir /s /q `"$Root`""
    Set-Location $parent
}
