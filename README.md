# VOCE

VMware Cost Optimization Engine. Advisory FinOps for vCenter, NSX-V, NSX-T, Aria Operations, and VMware Cloud Foundation. It logs in to the systems you configure, inventories them in parallel, prices the waste, and writes an HTML report, a CSV file, a Teams card, and a Power BI push dataset. It does not power off, resize, or delete anything.

## Run it

On a new server, follow [INSTALL.md](INSTALL.md). For day-to-day use of each feature, follow [GUIDE.md](GUIDE.md). To remove VOCE from a server, run `uninstall.ps1` or `uninstall.sh` as described in [INSTALL.md](INSTALL.md). From this folder after installation:

```powershell
.\start.ps1
```

Installation creates a default HTTPS certificate for this computer's name, its IP addresses, `localhost`, and `127.0.0.1`. Open `https://<server-name>:8080` or `https://<server-ip>:8080` for the dashboard, and the same address with `/admin` to register vCenter, NSX, Aria, and VCF. The installer prints those addresses. The dashboard can analyze the built-in demo estate before any endpoint exists. Analyze registered endpoints uses the systems saved in the admin page.

```powershell
.\.venv\Scripts\python -m pytest
```

## What “fast” means here

Live estates are slow when every call waits on the previous one, when PowerCLI walks every datastore, or when a model call has no deadline. This agent avoids that:

- vCenter, NSX, Aria, and VCF are collected at the same time, with a concurrency cap and a per-system timeout. One failed login does not discard the others.
- Each product is authenticated once per scan, then the session is closed.
- Aria CPU and memory averages are one batched stats call, capped by `VCO_ARIA_STAT_LIMIT`.
- NSX port checks are capped by `VCO_NSX_PORT_LOOKUP_LIMIT`. Segments past the cap are inventoried and not marked unused.
- The waste rules are in-process arithmetic. They do not call back to the infrastructure.
- Model recommendations have a four-second budget. If the key is missing, the call fails, or it exceeds the budget, the rules engine still returns a ranked plan.
- PowerCLI is off unless an endpoint sets `use_powershell: true`. Orphaned-disk search is a further opt-in because datastore walks dominate response time.
- Repeated identical scans reuse the previous result for `VCO_CACHE_TTL_SECONDS` (default 120). Teams and Power BI can still be delivered from that cached analysis.

The demo timings on the dashboard are in-process. Live timings are the actual login and collection time for each endpoint.

## Savings

Rates live in `config/rates.yaml`. Replace them with your contract prices.

| Waste | Committed savings |
| --- | --- |
| Powered off or suspended for 14 days. VM templates are not scanned | All vCPU, memory, and used storage. Snapshots on that VM are part of the delete, not a second finding. |
| Idle: CPU at or below 5% and memory at or below 20% | Compute only, with a 15% holdback until the change window |
| vCPU average at or below 20% on 4 or more vCPU | Price of the vCPU removed, keeping projected utilization at or below 70% |
| Memory average at or below 30% on 8 GB or more | Price of the memory removed, leaving 30% headroom above the observed average |
| Snapshot older than 7 days | Snapshot GB, and only while the VM stays |
| Unregistered VMDK | Full storage rate |
| NSX segment up with zero ports | Segment rate |
| Load balancer with zero sessions | Load balancer rate |
| Tier-1 or edge marked unused with zero sessions | Gateway rate |

Host removal and idle VCF clusters are shown as consolidation upside. They are excluded from the committed monthly, annual, and three-year totals because that capacity is already represented by the virtual machines. Missing CPU or memory counters do not become waste. A powered-off VM younger than 14 days is left alone.

Aria 7-day averages replace vCenter point samples when both describe the same VM name.

## Connect a live estate

Register each system at `https://<server-name>:8080/admin` or `https://<server-ip>:8080/admin`. The page writes `data/endpoints.json` on this server. Choose `vcenter`, `nsxt`, `nsx`, `aria`, or `vcf`, then save and use Test login. Step-by-step moves between servers are in [INSTALL.md](INSTALL.md).

A password may be the real secret or `${ENV:VARIABLE_NAME}`. The variable is read from the server environment or `.env` when the agent starts.

For a Windows jump host with PowerCLI, set `use_powershell: true` on the vCenter endpoint. Add `deep_stats: true` for a 7-day average and powered-off age, and `orphaned_disks: true` only when you accept a slower scan. If PowerCLI fails, the agent falls back to the vSphere REST inventory and says so in the report.

```powershell
.\powershell\Invoke-CostOptimization.ps1 -UseConfig -NotifyTeams -PushPowerBI -Refresh
```

Weekly task:

```powershell
schtasks /Create /TN "VOCE Scan" /SC WEEKLY /D MON /ST 06:00 /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\AIOPS\powershell\Invoke-CostOptimization.ps1 -UseConfig -NotifyTeams -PushPowerBI -Refresh"
```

To collect vCenter on a host that has PowerCLI and then hand the inventory to the agent:

```powershell
$env:VCO_USERNAME = "administrator@vsphere.local"
$env:VCO_PASSWORD = "<secret>"
.\powershell\Invoke-CostOptimization.ps1 -CollectVCenter -VCenter vcenter.example.com
```

The password is passed to PowerCLI through the process environment, not as a command-line argument.

REST coverage is enough for power state, NSX objects, Aria averages, and VCF clusters. Snapshot age, guest utilization, and orphaned VMDKs need PowerCLI or Aria. VCF cluster records without a utilization block are inventoried and not priced.

## Teams and Power BI

Set `VCO_TEAMS_WEBHOOK_URL` to an incoming webhook. The optimize call sends a MessageCard only when `notify_teams` is true. A missing webhook is reported as skipped; the analysis still succeeds.

Power BI CSV files are always written:

- `out/powerbi/findings.csv`
- `out/powerbi/summary.csv`
- `out/reports/<analysis-id>.html` and `.csv`

To push a dataset, set `VCO_POWERBI_TOKEN` and `VCO_POWERBI_GROUP_ID`. The agent creates the dataset described in `dashboard/powerbi/dataset.json` on first push, stores the id in `out/powerbi/dataset_id.txt`, clears the table rows, and loads the current analysis. In Power BI Desktop you can also import the CSVs.

Latest committed savings:

```dax
Latest Conservative Monthly =
VAR Latest = MAX(Summary[CollectedAt])
RETURN
    CALCULATE(
        MAX(Summary[ConservativeMonthly]),
        Summary[CollectedAt] = Latest
    )
```

Use `OverlapsCompute` as a filter when you want the committed findings only.

## API

| Call | Purpose |
| --- | --- |
| `GET /` | Dashboard |
| `GET /health` | Liveness |
| `GET /v1/rates` | Contract rates used for the math |
| `GET /v1/metrics` | p50 and p95 of recent responses |
| `POST /v1/sessions/test` | Log in to every configured endpoint and return each latency |
| `POST /v1/optimize` | Collect, price, recommend, export |
| `GET /v1/reports/latest.html` | Last HTML report |
| `GET /v1/reports/latest.csv` | Last CSV report |

`POST /v1/optimize` accepts exactly one source: `demo`, `use_config`, `endpoints`, or `inventory`.

Set `VCO_API_KEY` before binding the process beyond localhost. Clients then send `X-API-Key`. The default bind address is `127.0.0.1`.

## Collection map

| Signal | vSphere REST | PowerCLI | Aria | NSX | VCF |
| --- | --- | --- | --- | --- | --- |
| Power state | yes | yes | | | |
| Snapshots | | yes | | | |
| CPU and memory average | | quick stats, or 7-day with `-Deep` | 7-day average, preferred | | |
| Orphaned VMDK | | opt-in | | | |
| Empty segment, idle gateway | | | | yes | |
| Cluster utilization | | | | | when the API provides it |

## Layout

- `agent/` HTTP API, collectors, waste rules, exports
- `powershell/Collect-VCenter.ps1` PowerCLI inventory
- `powershell/Invoke-CostOptimization.ps1` scheduled entry point
- `config/rates.yaml` prices and thresholds
- `dashboard/powerbi/dataset.json` push dataset schema
- `out/` reports and Power BI files, created on the first run
