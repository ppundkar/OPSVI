# How to use VOCE

VOCE (VMware Cost Optimization Engine) logs in to vCenter, NSX, NSX-T, Aria Operations, and VMware Cloud Foundation, prices waste, and publishes a report. Installation is in [INSTALL.md](INSTALL.md).

## What VOCE never changes

A scan does not change the VMware environment. It does not power off, resize, snapshot, move, or delete virtual machines, templates, disks, hosts, NSX objects, Aria resources, or VCF clusters. Recommendations are text in the report. A person makes any change later, outside VOCE.

The only calls sent to those systems are login, inventory reads, a statistics query, and logout. The collector refuses any other write before it is sent. PowerCLI uses read commands (`Get-View`, `Get-Stat`, `Get-VIEvent`, and a datastore search). `Set-PowerCLIConfiguration` changes PowerCLI preferences on the VOCE computer only.

VOCE does write on its own server: the endpoint list, reports, CSV files, and, when you turn them on, a Teams message and a Power BI dataset refresh. Those are not changes to vCenter, NSX, Aria, or VCF.

Open the dashboard at `https://127.0.0.1:8080` on the server, or `https://<server-name>:8080` from another computer. The first install creates the HTTPS certificate. Other computers trust it after importing `data/tls/voce.cer`.

## Demo estate

Use this before any password is saved.

1. Open the dashboard.
2. Click **Analyze demo estate**.
3. Read the four totals: committed per month, annual, consolidation upside, and finding count.
4. The first recommendations are the committed items. Host removal and idle VCF capacity stay in the upside column.

The demo numbers are a sample. They are not your estate.

## Register the live systems

An administrator opens **Endpoints**.

1. Choose the system: `vcenter`, `nsxt` for current NSX, `nsx` for NSX-V, `aria`, or `vcf`.
2. Set an id such as `vc-prod`, the base URL, and the username.
3. Set the password, or type `${ENV:VCO_VC_PROD_PASSWORD}` and put that variable in `.env`.
4. Save, then click **Test login**. A time means the login worked. The error text means it did not, and the endpoint stays registered.
5. Repeat for each system.
6. Return to the dashboard and click **Analyze registered endpoints**.

A blank password on a later edit keeps the saved secret. **Remove** drops that system from the next scan.

Leave **Use PowerCLI**, **Deep 7-day stats**, and **Scan orphaned disks** off for a fast scan. Turn PowerCLI on only on a Windows host that has VMware PowerCLI. Deep stats add a 7-day average. Orphaned-disk scans walk datastores and are the slow path. If PowerCLI fails, the report falls back to the vSphere REST inventory and says so.

## Read a scan

Committed savings are the items you can act on without double-counting:

- Powered-off or suspended virtual machines older than 14 days. VM templates are left out of the scan, including their snapshots.
- Idle compute, with a 15 percent holdback
- Oversized CPU or memory, with headroom kept
- Snapshots older than 7 days
- Unregistered disks
- NSX segments, load balancers, and gateways with nothing attached

Consolidation upside is host removal and idle VCF capacity. Those amounts are excluded from the committed monthly, annual, and three-year totals because the virtual machines already carry that cost.

Missing CPU or memory counters are not treated as waste. A powered-off virtual machine younger than 14 days is left alone. When Aria has a 7-day average for the same virtual machine name, that average replaces the vCenter point sample.

One failed login does not discard the other systems. The banner says the scan is partial.

A repeated identical scan can reuse the previous result for two minutes. Click **Analyze registered endpoints** again to refresh it.

## Recommendations

Every scan asks for a recommendation. With `VCO_AI_API_KEY` empty, the ranked plan comes from the waste rules. Set that key, and an OpenAI-compatible endpoint, to ask a model for up to five actions. The call has a four-second budget. If it fails, the rules plan is what the report shows.

The model receives the findings only. It does not receive vCenter passwords. Azure OpenAI uses your resource URL in `VCO_AI_BASE_URL`, ending in `/openai/v1`, and the deployment name in `VCO_AI_MODEL`.

## Reports

**HTML report** and **CSV** open the latest scan. The same files are written under `out/reports/`. Each new scan replaces `out/powerbi/findings.csv` and `out/powerbi/summary.csv`.

## Teams

1. Put the incoming webhook in `VCO_TEAMS_WEBHOOK_URL` and restart VOCE.
2. Run a scan with **Notify Teams**, or run `.\powershell\Invoke-CostOptimization.ps1 -UseConfig -NotifyTeams -Refresh`.

A missing webhook is skipped. The scan still finishes.

## Power BI

The dashboard button **Push Power BI** sends the demo estate. A live estate is pushed from the server:

```powershell
.\powershell\Invoke-CostOptimization.ps1 -UseConfig -PushPowerBI -Refresh
```

That requires `VCO_POWERBI_TOKEN` and `VCO_POWERBI_GROUP_ID`. The first push creates a dataset named `VOCE`. Each later push replaces the rows with the latest scan. Setup for an existing workspace, a new workspace, and Power BI Report Server is in [INSTALL.md](INSTALL.md). Report Server uses the CSV files and does not use the push API.

In the report, filter `OverlapsCompute` to false when you want the committed findings only.

## Weekly scan

On the VOCE server:

```powershell
schtasks /Create /TN "VOCE Scan" /SC WEEKLY /D MON /ST 06:00 /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\AIOPS\powershell\Invoke-CostOptimization.ps1 -UseConfig -NotifyTeams -PushPowerBI -Refresh"
```

Change the folder if VOCE is not in `D:\AIOPS`. The task reads `.env` for the API key and the HTTPS certificate.

## Prices

Edit `config/rates.yaml` to the contract prices, then restart VOCE. The next scan uses those rates. Thresholds in the same file control how idle, oversized, and old an object must be before it is priced.

## Sign in and roles

Sign-in is off until `VCO_AUTH_MODE=ad`. The pages are then limited by Active Directory group:

| Role | Can do |
| --- | --- |
| Viewer | Open the dashboard and download reports |
| Operator | Run scans, test logins, notify Teams, and push Power BI |
| Admin | Register, edit, and remove endpoints |

Sign out from the button on the dashboard. Creating the groups and the `.env` values is in [INSTALL.md](INSTALL.md).

The scheduled scan does not type a person's password. It sends `VCO_API_KEY`. Set that key when sign-in is on.

## LDAPS certificate

Yes. A sign-in over LDAPS requires the domain controller's TLS certificate to validate. `VCO_AD_VERIFY_TLS` defaults to true, so VOCE rejects the connection when that certificate is not trusted.

This is separate from the certificate browsers use to open VOCE. `data/tls/cert.pem` identifies VOCE. The domain controller presents its own certificate on port 636.

1. Export the domain's issuing certificate authority as a Base-64 `.cer` file.
2. Import it into the VOCE server's trust store. On Windows, use the computer account's Trusted Root Certification Authorities. On Linux, place it in `/usr/local/share/ca-certificates/` and run `update-ca-certificates`.
3. Set `VCO_AD_URL` to a DNS name that is on the domain controller certificate, for example `ldaps://dc01.corp.example:636`.
4. Test from the VOCE server before you turn sign-in on:

```powershell
openssl s_client -connect dc01.corp.example:636 -showcerts
```

The test should show the certificate subject and no verify error. Then restart VOCE and sign in.

Set `VCO_AD_VERIFY_TLS=false` only in a lab that cannot trust the domain controller certificate. Leave it true for any server other people use.
