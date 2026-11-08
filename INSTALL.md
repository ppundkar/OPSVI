# Installation

Install VOCE (VMware Cost Optimization Engine) on Windows or Linux, then register vCenter, NSX, Aria Operations, and VCF from the admin page. The same folder runs on any server that has Python 3.11 or newer. VOCE does not change vSphere, NSX, or VCF objects.

## What you copy

Copy this project folder to the server. Leave out `.venv`, `.env`, `out`, `data/endpoints.json`, and `data/tls` from another machine. Those are created on the server where VOCE runs. `data/endpoints.json` contains the passwords registered in the admin page. `data/tls` contains that server's private key.

## Requirements

- Python 3.11 or newer on the PATH (`python` on Windows, `python3` on Linux)
- Outbound HTTPS from this server to each endpoint
- For PowerCLI collection only: Windows, VMware PowerCLI, and the vCenter endpoint option “Use PowerCLI” in the admin page
- Optional: a Teams webhook and a Power BI service principal, set in `.env`

## Windows

Open PowerShell in the project folder.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
.\start.ps1
```

To install and start immediately:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Start
```

To register a task that starts the agent when the server boots:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Service
```

The task name is `VOCE`.

## Linux

```bash
chmod +x install.sh start.sh
./install.sh
./start.sh
```

To also install a systemd service (run as root, or with sudo):

```bash
sudo ./install.sh --systemd
sudo systemctl enable --now vmware-cost-agent
```

The unit file is written to `/etc/systemd/system/vmware-cost-agent.service` using the folder you installed into.

## First start

The installer creates a virtual environment, installs the Python packages, creates `data` and `out`, and copies `.env.example` to `.env` when `.env` is missing. It also creates a default HTTPS certificate when this server does not already have one.

Open:

- Dashboard: https://127.0.0.1:8080
- Endpoint admin: https://127.0.0.1:8080/admin

The dashboard can analyze the built-in demo estate before any endpoint exists. Live scans use only the endpoints you register.

## Register endpoints

1. Open https://127.0.0.1:8080/admin
2. Choose the system type.
   - vCenter: `vcenter`
   - NSX-T or current NSX: `nsxt`
   - NSX-V: `nsx`
   - Aria Operations: `aria`
   - VMware Cloud Foundation SDDC Manager: `vcf`
3. Set an id you will recognize, such as `vc-prod`. Use letters, numbers, dots, hyphens, or underscores.
4. Set the base URL, for example `https://vcenter.example.com`. Do not put the password in the URL.
5. Set the username.
6. Set the password, or enter an environment variable reference such as `${ENV:VCO_VC_PROD_PASSWORD}`. The variable must exist in the server environment or in `.env` before the agent starts.
7. Save the endpoint.
8. Click Test login. A successful row shows the login time. A failure shows the reason and leaves the endpoint registered.
9. Repeat for NSX, Aria, and VCF.
10. Return to the dashboard and click Analyze registered endpoints.

Editing an endpoint and leaving the password blank keeps the saved secret. Remove deletes it from the next scan.

PowerCLI, deep 7-day stats, and orphaned-disk scans are vCenter options. Leave them off for the fastest scan. Turn on PowerCLI on a Windows host that has VMware PowerCLI installed.

The registry is `data/endpoints.json`. Restrict that file to the account that runs the agent. It is created with mode `600` on Linux.

## Default certificate

`install.ps1` and `install.sh` create a certificate the first time VOCE is installed on that server. A later install leaves an existing certificate in place, including a custom one.

The default certificate includes:

- the computer name
- the DNS name of the computer, when the server can resolve it
- each IPv4 address of the server
- `localhost` and `127.0.0.1`

The files are `data/tls/cert.pem`, `data/tls/key.pem`, and `data/tls/voce.cer`. `.env` points at the first two and sets `VCO_HOST=0.0.0.0`. Open `https://127.0.0.1:8080`, `https://localhost:8080`, or `https://<server-ip>:8080`.

On Windows, the install trusts that certificate for the user who ran `install.ps1`. On another computer, import `data/tls/voce.cer` into Trusted Root Certification Authorities. On Linux, browsers trust it after that same import, or after the server administrator adds `data/tls/cert.pem` to the system trust store.

To use `https://<server>` with no port, set `VCO_PORT=443` and start VOCE from an elevated shell. Port 8080 is the default so the process does not need that privilege.

To add a name that was not known at install time, run the helper again and restart. This replaces the default certificate.

```powershell
.\enable-https.ps1 -DnsName voce.corp.example -IpAddress 10.1.2.3
.\start.ps1
```

```bash
./enable-https.sh voce.corp.example 10.1.2.3
./start.sh
```

## Install a custom certificate

Use this when a company or public certificate authority should identify VOCE. Do this after the normal install. The installer will not overwrite the files once `.env` points at them.

1. Ask the certificate owner for a certificate that contains the name and address browsers will use. Include the FQDN as a DNS name and the server IP as an IP address. A name missing from the certificate makes the browser warn.
2. Collect two PEM files. The certificate file may include the server certificate and the intermediate certificates, with the server certificate first. The private key must be unencrypted. Do not send the private key by email or put it in git.
3. If the authority delivered a `.pfx` file, convert it on the VOCE server. Git for Windows and most Linux servers include `openssl`. Replace `voce.pfx` with the file you received.

```bash
openssl pkcs12 -in voce.pfx -nokeys -out custom-cert.pem
openssl pkcs12 -in voce.pfx -nocerts -nodes -out custom-key.pem
```

4. Copy those files into the VOCE folder:

```text
data/tls/custom-cert.pem
data/tls/custom-key.pem
```

5. On Linux, restrict the key to the account that runs VOCE:

```bash
chmod 600 data/tls/custom-key.pem
```

6. Edit `.env` on that server. Leave every other setting as it is.

```text
VCO_HOST=0.0.0.0
VCO_SSL_CERTFILE=data/tls/custom-cert.pem
VCO_SSL_KEYFILE=data/tls/custom-key.pem
```

7. Restart VOCE. On Windows run `.\start.ps1`. On Linux run `./start.sh`, or `sudo systemctl restart vmware-cost-agent` when the service is installed.
8. Open `https://<fqdn>:8080`. The browser should show the company or public authority as the issuer. If the authority is already trusted by the organization, other computers do not need `voce.cer`.
9. Confirm a scan still runs. On the VOCE server:

```powershell
.\powershell\Invoke-CostOptimization.ps1 -Demo
```

The script trusts the certificate named by `VCO_SSL_CERTFILE`. A scheduled task on that server uses the same check.

To return to the default certificate, set the two `.env` values back to `data/tls/cert.pem` and `data/tls/key.pem`, or delete those files and run `.\enable-https.ps1` or `./enable-https.sh` again.

## Listen on the network

The default bind is `127.0.0.1`, so only the server itself can open the page. `enable-https.ps1` sets `VCO_HOST=0.0.0.0`. To reach the page without HTTPS, edit `.env`:

```text
VCO_HOST=0.0.0.0
VCO_PORT=8080
VCO_API_KEY=choose-a-long-random-key
```

Browser calls from the dashboard do not send `VCO_API_KEY`. Leave that key empty when people use the pages in a browser, and limit the port with the firewall. Set the key when scripts call `/v1` from another machine, and send the header `X-API-Key`.

Example tunnel from your workstation:

```bash
ssh -L 8080:127.0.0.1:8080 user@cost-agent-server
```

Then open https://127.0.0.1:8080/admin on your workstation. The tunnel reaches the HTTPS listener, so the workstation must trust `data/tls/voce.cer` or the custom certificate.

## Teams and prices

Set `VCO_TEAMS_WEBHOOK_URL` in `.env` to a Teams incoming webhook. Replace the monthly prices in `config/rates.yaml` with your contract rates before you publish a savings number.

## Power BI

Every scan writes two files on the agent server. Each new scan replaces the previous files:

- `out/powerbi/findings.csv` — one row per waste item
- `out/powerbi/summary.csv` — one row for that scan

The dashboard button **Push Power BI** sends the built-in demo estate. A live estate is pushed only by `-UseConfig -PushPowerBI` or `POST /v1/optimize` with `use_config` and `push_powerbi` set to true.

The push path talks to the Power BI Service at `https://api.powerbi.com`. Each push deletes the current rows in `Findings` and `Summary`, then loads the latest scan. The dataset holds the latest analysis. It does not keep a history of earlier scans.

| Table | Contents |
| --- | --- |
| `Findings` | Category, severity, resource, monthly savings, recommendation, `OverlapsCompute` |
| `Summary` | Committed monthly, gross, annual, three-year, finding count, VM count |

`OverlapsCompute = FALSE` is the committed savings. Host and VCF rows are consolidation upside. Column names are fixed in `dashboard/powerbi/dataset.json`. A push dataset must use those names.

### Existing Power BI Service workspace

Use this when the workspace already exists at `https://app.powerbi.com`.

1. Open the workspace and copy the workspace ID from the URL: `https://app.powerbi.com/groups/<workspace-id>/...`.
2. In Microsoft Entra ID, register an application and create a client secret.
3. On that application, add the application permission **Power BI Service → Dataset.ReadWrite.All** and grant admin consent.
4. In the Power BI admin portal, allow service principals to use Power BI APIs.
5. Add the application, or a security group that contains it, as a **Member** of the existing workspace.
6. Request a token. The token expires in about one hour, so a scheduled scan needs a new token before each push.

```http
POST https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=<app-id>
&client_secret=<secret>
&scope=https://analysis.windows.net/powerbi/api/.default
```

7. Put the token and workspace ID in `.env` on the agent server, then restart the agent:

```text
VCO_POWERBI_TOKEN=<access_token>
VCO_POWERBI_GROUP_ID=<workspace-id>
```

Leave `VCO_POWERBI_DATASET_ID` empty on the first push. The agent creates a push dataset named `VOCE` in that workspace and saves the dataset ID in `out/powerbi/dataset_id.txt`.

8. Register vCenter, NSX, Aria, and VCF at `https://127.0.0.1:8080/admin`.
9. Push the live scan:

```powershell
.\powershell\Invoke-CostOptimization.ps1 -UseConfig -PushPowerBI -Refresh
```

The same call over HTTPS:

```http
POST https://127.0.0.1:8080/v1/optimize
Content-Type: application/json

{"use_config":true,"include_ai":true,"refresh":true,"push_powerbi":true}
```

10. In the workspace, open `VMwareCostOptimization`. Create a many-to-one relationship from `Findings[AnalysisId]` to `Summary[AnalysisId]`. Add these measures:

```dax
Latest Conservative Monthly =
VAR Latest = MAX ( Summary[CollectedAt] )
RETURN
    CALCULATE (
        MAX ( Summary[ConservativeMonthly] ),
        Summary[CollectedAt] = Latest
    )

Committed Findings =
CALCULATE (
    SUM ( Findings[MonthlySavings] ),
    Findings[OverlapsCompute] = FALSE
)
```

11. If a push dataset with these exact tables already exists, set `VCO_POWERBI_DATASET_ID` to that dataset ID so the agent updates it instead of creating a second dataset. An import or DirectQuery model cannot receive this push. Keep this push dataset beside the existing model, or use the CSV files with a gateway refresh.
12. Confirm the command or API response has `powerbi.status` of `sent`. In the service, `Summary` has one row and `Findings` matches the scan.

### New Power BI Service workspace

Use this for a new workspace or a new capacity. The agent does not install Power BI. It still calls `https://api.powerbi.com`.

1. In the Power BI Service, create a workspace, for example `VMware FinOps`. If the tenant uses Premium or Fabric capacity, assign the workspace to that capacity.
2. Copy the workspace ID from the browser URL.
3. Register the Entra application, grant **Dataset.ReadWrite.All**, and allow service principals in the Power BI admin portal, as in the existing-workspace steps.
4. Add the application as a **Member** of the new workspace.
5. Request a token and set `VCO_POWERBI_TOKEN` and `VCO_POWERBI_GROUP_ID` in `.env`. Leave `VCO_POWERBI_DATASET_ID` empty.
6. Restart the agent and run:

```powershell
.\powershell\Invoke-CostOptimization.ps1 -UseConfig -PushPowerBI -Refresh
```

7. The first successful push creates `VMwareCostOptimization`. Build the report in that workspace with the relationship and measures above.

When the agent moves to another server, request a new token there. Copy `out/powerbi/dataset_id.txt` if that server must keep writing to the same dataset. Otherwise the first push creates a new dataset in the workspace.

### Power BI Report Server

An on-premises Power BI Report Server does not accept this push API. Point the report at the CSV files.

1. Install Power BI Report Server and the matching Power BI Desktop Report Server build.
2. Make `out/powerbi` readable by the report server, on a local disk or a file share.
3. In Power BI Desktop, choose **Get data → Text/CSV** and load `findings.csv` and `summary.csv`.
4. Create the same `AnalysisId` relationship and the two measures.
5. Save the report to the report server.
6. Refresh the files before the report refresh:

```powershell
.\powershell\Invoke-CostOptimization.ps1 -UseConfig -Refresh
```

7. Schedule the Report Server refresh after that scan. Each scan replaces the two CSV files, and the next refresh shows the new snapshot.

### Weekly Power BI push

Refresh the Entra token into `VCO_POWERBI_TOKEN` before the scan. Then run `Invoke-CostOptimization.ps1 -UseConfig -PushPowerBI -Refresh`. For Report Server, omit `-PushPowerBI` and refresh the report from the CSV folder.

## Scheduled scan

Windows, after the agent is already running as a service or you start it at boot:

```powershell
schtasks /Create /TN "VOCE Scan" /SC WEEKLY /D MON /ST 06:00 /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\path\to\AIOPS\powershell\Invoke-CostOptimization.ps1 -UseConfig -NotifyTeams -PushPowerBI -Refresh"
```

Linux cron, with the agent already listening:

```text
0 6 * * 1 curl -s --cacert /path/to/AIOPS/data/tls/cert.pem -X POST https://127.0.0.1:8080/v1/optimize -H 'Content-Type: application/json' -d '{"use_config":true,"include_ai":true,"refresh":true,"notify_teams":true,"push_powerbi":true}'
```

`-UseConfig` and `use_config` read the endpoints saved in the admin page.

## Move to another server

1. Install Python 3.11 or newer on the new server.
2. Copy the application folder without `.venv`, `.env`, `out`, and `data/endpoints.json`.
3. Run `install.ps1` or `install.sh`.
4. Edit the new `.env` for the bind address, API key, Teams, and Power BI values.
5. Start the agent and register the endpoints again at `/admin`.

Re-registering on the new server avoids copying passwords inside the application folder.

## Checks

```text
GET https://127.0.0.1:8080/health
```

returns `"status": "ok"`. The admin page lists every saved endpoint. Test login on each row before the first live analysis.
