<#
.SYNOPSIS
    Collect vCenter inventory for the cost optimization agent.

.DESCRIPTION
    Emits one JSON document on stdout. Username and password are read from
    VCO_USERNAME and VCO_PASSWORD so they are not placed on the command line.
    Requires VMware.PowerCLI. The default path uses a single Get-View pass.
    -Deep adds a 7-day average and powered-off ages. -IncludeOrphanedDisks
    scans datastores and is slower.

.PARAMETER Server
    vCenter hostname or host:port.

.PARAMETER Deep
    Collect 7-day CPU and memory averages and powered-off event ages.

.PARAMETER IncludeOrphanedDisks
    Search datastores for VMDK files that are not in a VM layout.

.PARAMETER TrustAll
    Accept an untrusted vCenter certificate. Leave this off for production.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [switch]$Deep,
    [switch]$IncludeOrphanedDisks,
    [switch]$TrustAll
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$InformationPreference = "SilentlyContinue"

function ConvertTo-AgentJson {
    param($Value)
    if ($null -eq $Value) { return "null" }
    if ($Value -is [bool]) {
        if ($Value) { return "true" }
        return "false"
    }
    if ($Value -is [string]) {
        $text = $Value.Replace("\", "\\").Replace('"', '\"').Replace("`r", "\r").Replace("`n", "\n")
        return '"' + $text + '"'
    }
    if (($Value -is [System.Collections.IList]) -and -not ($Value -is [string])) {
        $items = @($Value | ForEach-Object { ConvertTo-AgentJson $_ })
        return "[" + ($items -join ",") + "]"
    }
    if ($Value -is [System.Collections.IDictionary]) {
        $pairs = @()
        foreach ($key in $Value.Keys) {
            $pairs += ((ConvertTo-AgentJson ([string]$key)) + ":" + (ConvertTo-AgentJson $Value[$key]))
        }
        return "{" + ($pairs -join ",") + "}"
    }
    if ($Value -is [double] -or $Value -is [decimal] -or $Value -is [float]) {
        return [System.Convert]::ToString($Value, [System.Globalization.CultureInfo]::InvariantCulture)
    }
    if ($Value -is [ValueType]) {
        return [System.Convert]::ToString($Value, [System.Globalization.CultureInfo]::InvariantCulture)
    }
    return ConvertTo-AgentJson ([string]$Value)
}

function Write-Failure {
    param([string]$Message)
    [Console]::Error.WriteLine($Message)
    $payload = @{
        vms = @()
        hosts = @()
        datastores = @()
        segments = @()
        gateways = @()
        vcf_clusters = @()
        metric_patches = @()
        warnings = @($Message)
    }
    Write-Output (ConvertTo-AgentJson $payload)
}

$username = $env:VCO_USERNAME
$password = $env:VCO_PASSWORD
if (-not $username -or -not $password) {
    Write-Failure "Set VCO_USERNAME and VCO_PASSWORD before running Collect-VCenter.ps1"
    exit 2
}

if (-not (Get-Module -ListAvailable -Name VMware.PowerCLI)) {
    Write-Failure "VMware.PowerCLI is not installed on this host"
    exit 2
}

Import-Module VMware.PowerCLI -ErrorAction Stop | Out-Null
$certAction = "Fail"
if ($TrustAll) { $certAction = "Ignore" }
foreach ($scope in @("Process", "Session", "User")) {
    try {
        Set-PowerCLIConfiguration -Scope $scope -InvalidCertificateAction $certAction -ParticipateInCEIP $false -Confirm:$false | Out-Null
        break
    } catch {
        continue
    }
}

$secure = ConvertTo-SecureString $password -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential($username, $secure)
$connection = $null
try {
    $connection = Connect-VIServer -Server $Server -Credential $credential -ErrorAction Stop
    $hostViews = @(Get-View -ViewType HostSystem -Property Name,Runtime.ConnectionState,Runtime.InMaintenanceMode,Summary.Hardware,Summary.QuickStats,Vm)
    $vmViews = @(Get-View -ViewType VirtualMachine -Property Name,Runtime.PowerState,Runtime.Host,Config.Hardware,Config.Template,Guest.ToolsStatus,Summary.Storage,Summary.QuickStats,Snapshot,LayoutEx)
    $dsViews = @(Get-View -ViewType Datastore -Property Name,Summary,Browser)

    $hostMhz = @{}
    $hostNames = @{}
    foreach ($item in $hostViews) {
        $hostMhz[$item.MoRef.Value] = [double]$item.Summary.Hardware.CpuMhz
        $hostNames[$item.MoRef.Value] = [string]$item.Name
    }

    $statCpu = @{}
    $statMem = @{}
    $offDays = @{}
    if ($Deep) {
        $stats = @(Get-Stat -Entity (Get-VM) -Stat cpu.usage.average,mem.usage.average -Start (Get-Date).AddDays(-7) -IntervalMins 1440 -ErrorAction SilentlyContinue)
        $grouped = $stats | Group-Object { $_.Entity.Name + "|" + $_.MetricId }
        foreach ($group in $grouped) {
            $parts = $group.Name.Split("|")
            $average = ($group.Group | Measure-Object -Property Value -Average).Average
            if ($parts[1] -like "cpu.usage*") { $statCpu[$parts[0]] = [math]::Round($average, 1) }
            if ($parts[1] -like "mem.usage*") { $statMem[$parts[0]] = [math]::Round($average, 1) }
        }
        $events = @(Get-VIEvent -Start (Get-Date).AddDays(-90) -MaxSamples 2000 -ErrorAction SilentlyContinue | Where-Object { $_.GetType().Name -eq "VmPoweredOffEvent" })
        foreach ($event in $events) {
            $name = [string]$event.Vm.Name
            if (-not $offDays.ContainsKey($name) -or $event.CreatedTime -gt $offDays[$name]) {
                $offDays[$name] = $event.CreatedTime
            }
        }
    }

    $orphans = @{}
    $warnings = @()
    if ($IncludeOrphanedDisks) {
        $registered = @{}
        foreach ($vm in $vmViews) {
            if ($vm.LayoutEx -and $vm.LayoutEx.File) {
                foreach ($file in @($vm.LayoutEx.File)) {
                    if ($file.Name) { $registered[$file.Name.ToLowerInvariant()] = $true }
                }
            }
        }
        foreach ($ds in $dsViews) {
            try {
                $spec = New-Object VMware.Vim.HostDatastoreBrowserSearchSpec
                $spec.MatchPattern = "*.vmdk"
                $flags = New-Object VMware.Vim.FileQueryFlags
                $flags.FileSize = $true
                $flags.FileType = $true
                $spec.Details = $flags
                $taskRef = $ds.Browser.SearchDatastoreSubFolders_Task(("[" + $ds.Name + "]"), $spec)
                $taskView = Get-View -Id $taskRef
                $deadline = (Get-Date).AddSeconds(20)
                while ($taskView.Info.State -eq "running" -or $taskView.Info.State -eq "queued") {
                    if ((Get-Date) -gt $deadline) { throw "orphan scan timed out" }
                    Start-Sleep -Milliseconds 400
                    $taskView.UpdateViewData(@("Info.State", "Info.Result", "Info.Error"))
                }
                if ($taskView.Info.State -ne "success") { throw "orphan scan did not succeed" }
                $bytes = [int64]0
                foreach ($folder in @($taskView.Info.Result)) {
                    foreach ($file in @($folder.File)) {
                        if ($file.Path -notmatch '\.vmdk$' -or $file.Path -match '-delta\.vmdk$|-sesparse\.vmdk$|-flat\.vmdk$|-ctk\.vmdk$') { continue }
                        $fullName = ($folder.FolderPath.TrimEnd("/") + "/" + $file.Path).ToLowerInvariant()
                        if (-not $registered.ContainsKey($fullName)) { $bytes += [int64]$file.FileSize }
                    }
                }
                $orphans[$ds.MoRef.Value] = [math]::Round($bytes / 1GB, 1)
            } catch {
                $warnings += ("Orphan scan skipped for " + $ds.Name + ": " + $_.Exception.Message)
            }
        }
    }

    $vms = @()
    foreach ($vm in $vmViews) {
        $cpuPct = $null
        $memPct = $null
        $hostId = $null
        if ($vm.Runtime.Host) { $hostId = $vm.Runtime.Host.Value }
        $mhz = 0
        if ($hostId -and $hostMhz.ContainsKey($hostId)) { $mhz = $hostMhz[$hostId] }
        $quick = $vm.Summary.QuickStats
        $vcpu = 0
        $memoryMb = 0
        if ($vm.Config -and $vm.Config.Hardware) {
            $vcpu = [int]$vm.Config.Hardware.NumCPU
            $memoryMb = [double]$vm.Config.Hardware.MemoryMB
        }
        if ($quick -and $mhz -gt 0 -and $vcpu -gt 0 -and $null -ne $quick.OverallCpuUsage) {
            $cpuPct = [math]::Round(([double]$quick.OverallCpuUsage) / ($vcpu * $mhz) * 100, 1)
        }
        $toolsOk = $false
        if ($vm.Guest -and [string]$vm.Guest.ToolsStatus -eq "toolsOk") { $toolsOk = $true }
        if ($toolsOk -and $quick -and $memoryMb -gt 0 -and $null -ne $quick.GuestMemoryUsage) {
            $memPct = [math]::Round(([double]$quick.GuestMemoryUsage) / $memoryMb * 100, 1)
        }
        if ($statCpu.ContainsKey([string]$vm.Name)) { $cpuPct = $statCpu[[string]$vm.Name] }
        if ($statMem.ContainsKey([string]$vm.Name)) { $memPct = $statMem[[string]$vm.Name] }

        $snapCount = 0
        $snapBytes = [int64]0
        $oldest = $null
        if ($vm.Snapshot -and $vm.Snapshot.RootSnapshotList) {
            $stack = New-Object System.Collections.Stack
            foreach ($node in @($vm.Snapshot.RootSnapshotList)) { [void]$stack.Push($node) }
            while ($stack.Count -gt 0) {
                $node = $stack.Pop()
                $snapCount += 1
                if ($null -eq $oldest -or $node.CreateTime -lt $oldest) { $oldest = $node.CreateTime }
                if ($node.ChildSnapshotList) {
                    foreach ($child in @($node.ChildSnapshotList)) { [void]$stack.Push($child) }
                }
            }
        }
        if ($vm.LayoutEx -and $vm.LayoutEx.File) {
            foreach ($file in @($vm.LayoutEx.File)) {
                if ($file.Name -match '-delta\.vmdk$|-sesparse\.vmdk$|\.vmsn$|\.vmem$') {
                    $snapBytes += [int64]$file.Size
                }
            }
        }
        $oldestDays = 0
        if ($oldest) { $oldestDays = [int][math]::Floor(((Get-Date) - $oldest).TotalDays) }
        $poweredOffDays = $null
        if ($offDays.ContainsKey([string]$vm.Name)) {
            $poweredOffDays = [int][math]::Floor(((Get-Date) - $offDays[[string]$vm.Name]).TotalDays)
        }
        $usedGb = 0
        $provisionedGb = 0
        if ($vm.Summary.Storage) {
            $committed = [double]$vm.Summary.Storage.Committed
            $uncommitted = [double]$vm.Summary.Storage.Uncommitted
            $usedGb = [math]::Round($committed / 1GB, 1)
            $provisionedGb = [math]::Round(($committed + $uncommitted) / 1GB, 1)
        }
        $isTemplate = $false
        if ($vm.Config -and $vm.Config.Template) { $isTemplate = $true }
        $vms += @{
            endpoint_id = "vcenter"
            id = [string]$vm.MoRef.Value
            name = [string]$vm.Name
            power_state = [string]$vm.Runtime.PowerState
            vcpu = $vcpu
            memory_gb = [math]::Round($memoryMb / 1024, 2)
            used_gb = $usedGb
            provisioned_gb = $provisionedGb
            cpu_usage_pct = $cpuPct
            mem_usage_pct = $memPct
            powered_off_days = $poweredOffDays
            snapshot_count = $snapCount
            snapshot_gb = [math]::Round($snapBytes / 1GB, 1)
            oldest_snapshot_days = $oldestDays
            is_template = $isTemplate
            tools_ok = $toolsOk
            host = $(if ($hostId -and $hostNames.ContainsKey($hostId)) { $hostNames[$hostId] } else { "" })
            metrics_source = $(if ($Deep) { "powercli-deep" } else { "powercli" })
        }
    }

    $hosts = @()
    foreach ($item in $hostViews) {
        $cores = [int]$item.Summary.Hardware.NumCpuCores
        $mhz = [double]$item.Summary.Hardware.CpuMhz
        $cpuPct = $null
        $memPct = $null
        if ($item.Summary.QuickStats -and $mhz -gt 0 -and $cores -gt 0 -and $null -ne $item.Summary.QuickStats.OverallCpuUsage) {
            $cpuPct = [math]::Round(([double]$item.Summary.QuickStats.OverallCpuUsage) / ($cores * $mhz) * 100, 1)
        }
        $memoryBytes = [double]$item.Summary.Hardware.MemorySize
        if ($item.Summary.QuickStats -and $memoryBytes -gt 0 -and $null -ne $item.Summary.QuickStats.OverallMemoryUsage) {
            $memPct = [math]::Round(([double]$item.Summary.QuickStats.OverallMemoryUsage) * 1MB / $memoryBytes * 100, 1)
        }
        $vmCount = 0
        if ($item.Vm) { $vmCount = @($item.Vm).Count }
        $connected = ([string]$item.Runtime.ConnectionState).ToLowerInvariant() -eq "connected"
        $hosts += @{
            endpoint_id = "vcenter"
            id = [string]$item.MoRef.Value
            name = [string]$item.Name
            cpu_usage_pct = $cpuPct
            mem_usage_pct = $memPct
            vm_count = $vmCount
            cores = $cores
            memory_gb = [math]::Round($memoryBytes / 1GB, 1)
            maintenance = [bool]$item.Runtime.InMaintenanceMode
            connected = $connected
        }
    }

    $datastores = @()
    foreach ($ds in $dsViews) {
        $orphaned = 0
        if ($orphans.ContainsKey($ds.MoRef.Value)) { $orphaned = $orphans[$ds.MoRef.Value] }
        $datastores += @{
            endpoint_id = "vcenter"
            id = [string]$ds.MoRef.Value
            name = [string]$ds.Name
            capacity_gb = [math]::Round([double]$ds.Summary.Capacity / 1GB, 1)
            free_gb = [math]::Round([double]$ds.Summary.FreeSpace / 1GB, 1)
            orphaned_gb = $orphaned
        }
    }

    $payload = @{
        vms = $vms
        hosts = $hosts
        datastores = $datastores
        segments = @()
        gateways = @()
        vcf_clusters = @()
        metric_patches = @()
        warnings = $warnings
    }
    Write-Output (ConvertTo-AgentJson $payload)
} catch {
    Write-Failure $_.Exception.Message
    exit 1
} finally {
    if ($connection) {
        Disconnect-VIServer -Server $connection -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    }
    $password = $null
    $secure = $null
    $credential = $null
}
