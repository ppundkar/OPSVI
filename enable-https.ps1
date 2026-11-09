param(
    [string[]]$DnsName = @(),
    [string[]]$IpAddress = @()
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if ($DnsName.Count -eq 0 -and $IpAddress.Count -eq 0) {
    $DnsName = @($env:COMPUTERNAME)
    try {
        $fqdn = [System.Net.Dns]::GetHostEntry($env:COMPUTERNAME).HostName
        if ($fqdn -and $DnsName -notcontains $fqdn) { $DnsName += $fqdn }
    } catch {
        Write-Host "Could not resolve this computer's DNS name. The certificate still includes the computer name."
    }
    try {
        $IpAddress = @(
            [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
                Where-Object { $_.AddressFamily -eq "InterNetwork" -and $_.ToString() -ne "127.0.0.1" } |
                ForEach-Object { $_.ToString() }
        )
    } catch {
        $IpAddress = @()
    }
}

$dns = [System.Collections.Generic.List[string]]::new()
$ips = [System.Collections.Generic.List[string]]::new()
foreach ($name in @("localhost") + $DnsName) {
    if ($name -and -not $dns.Contains($name)) { $dns.Add($name) }
}
foreach ($name in @("127.0.0.1") + $IpAddress) {
    if ($name -and -not $ips.Contains($name)) { $ips.Add($name) }
}

$sanParts = @()
foreach ($name in $dns) { $sanParts += "DNS=$name" }
foreach ($name in $ips) { $sanParts += "IPAddress=$name" }
$san = "2.5.29.17={text}" + ($sanParts -join "&")
$cn = if ($DnsName.Count -gt 0) { $DnsName[0] } else { $IpAddress[0] }

$cert = New-SelfSignedCertificate `
    -Subject "CN=$cn" `
    -FriendlyName "VOCE $cn" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -KeyExportPolicy Exportable `
    -HashAlgorithm SHA256 `
    -NotAfter (Get-Date).AddYears(2) `
    -TextExtension @($san, "2.5.29.37={text}1.3.6.1.5.5.7.3.1")

$store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "CurrentUser")
$store.Open("ReadWrite")
$store.Add($cert)
$store.Close()

$tls = Join-Path $Root "data\tls"
New-Item -ItemType Directory -Force -Path $tls | Out-Null
$certPath = Join-Path $tls "cert.pem"
$keyPath = Join-Path $tls "key.pem"
$derPath = Join-Path $tls "voce.cer"

function Convert-ToPem([byte[]]$Bytes, [string]$Label) {
    $body = [Convert]::ToBase64String($Bytes, [System.Base64FormattingOptions]::InsertLineBreaks)
    return "-----BEGIN $Label-----`r`n$body`r`n-----END $Label-----`r`n"
}

$rsa = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($cert)
$parameters = $rsa.ExportParameters($true)
function Get-Hex([byte[]]$Bytes) { return ([System.BitConverter]::ToString($Bytes)).Replace("-", "") }
$payload = @{
    n = Get-Hex $parameters.Modulus
    e = Get-Hex $parameters.Exponent
    d = Get-Hex $parameters.D
    p = Get-Hex $parameters.P
    q = Get-Hex $parameters.Q
    dp = Get-Hex $parameters.DP
    dq = Get-Hex $parameters.DQ
    qi = Get-Hex $parameters.InverseQ
} | ConvertTo-Json -Compress
$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
$encoder = @'
import json, sys
from pathlib import Path

def der_len(n):
    if n < 128:
        return bytes([n])
    size = (n.bit_length() + 7) // 8
    return bytes([0x80 | size]) + n.to_bytes(size, "big")

def der_int(value):
    body = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
    if body[0] & 0x80:
        body = bytes([0]) + body
    return bytes([2]) + der_len(len(body)) + body

def der_seq(parts):
    body = b"".join(parts)
    return bytes([48]) + der_len(len(body)) + body

data = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig"))
numbers = [int(data[name], 16) for name in ("n", "e", "d", "p", "q", "dp", "dq", "qi")]
pkcs1 = der_seq([der_int(0), *(der_int(number) for number in numbers)])
body = "\n".join(__import__("base64").encodebytes(pkcs1).decode("ascii").strip().splitlines())
Path(sys.argv[1]).write_text("-----BEGIN RSA PRIVATE KEY-----\n" + body + "\n-----END RSA PRIVATE KEY-----\n", encoding="ascii")
'@
$encoderPath = Join-Path $tls "_encode_key.py"
Set-Content -Path $encoderPath -Value $encoder -Encoding ASCII
$jsonPath = Join-Path $tls "_key.json"
[System.IO.File]::WriteAllText($jsonPath, $payload)
& $python $encoderPath $keyPath $jsonPath
Remove-Item -Force $jsonPath
$encodeExit = $LASTEXITCODE
Remove-Item -Force $encoderPath
if ($encodeExit -ne 0 -or -not (Test-Path $keyPath)) {
    throw "Could not write the HTTPS private key."
}
[System.IO.File]::WriteAllText($certPath, (Convert-ToPem $cert.RawData "CERTIFICATE"))
[System.IO.File]::WriteAllBytes($derPath, $cert.RawData)

icacls $keyPath /inheritance:r | Out-Null
icacls $keyPath /grant:r "${env:USERNAME}:(R)" | Out-Null

function Set-DotEnv([string]$Key, [string]$Value) {
    $path = Join-Path $Root ".env"
    if (-not (Test-Path $path)) {
        Copy-Item (Join-Path $Root ".env.example") $path
    }
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.AddRange([string[]]@(Get-Content -Path $path))
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match ("^" + [regex]::Escape($Key) + "=")) {
            $lines[$i] = "$Key=$Value"
            $found = $true
        }
    }
    if (-not $found) { $lines.Add("$Key=$Value") }
    [System.IO.File]::WriteAllLines($path, $lines)
}

Set-DotEnv "VCO_HOST" "0.0.0.0"
Set-DotEnv "VCO_SSL_CERTFILE" "data/tls/cert.pem"
Set-DotEnv "VCO_SSL_KEYFILE" "data/tls/key.pem"

Write-Host "Certificate names: $($dns -join ', '), $($ips -join ', ')"
Write-Host "Trusted for the current Windows user."
Write-Host "Other computers import data\tls\voce.cer into Trusted Root Certification Authorities."
$port = 8080
$envFile = Join-Path $Root ".env"
foreach ($line in Get-Content $envFile) {
    if ($line -match '^VCO_PORT=(\d+)$') { $port = $Matches[1] }
}
Write-Host "Restart with .\start.ps1"
foreach ($name in ($dns + $ips)) {
    if ($name -eq "localhost" -or $name -eq "127.0.0.1") { continue }
    Write-Host "Dashboard: https://${name}:$port"
    Write-Host "Admin:     https://${name}:$port/admin"
}
