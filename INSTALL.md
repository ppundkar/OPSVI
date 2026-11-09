# Installation

Install VOCE (VMware Cost Optimization Engine) on Windows or Linux, then register vCenter, NSX, Aria Operations, and VCF from the admin page. Day-to-day use of each feature is in [GUIDE.md](GUIDE.md). The same folder runs on any server that has Python 3.11 or newer. VOCE does not change vSphere, NSX, or VCF objects.

## What you copy

The usual way onto a jump box is `git clone`, in the next section. A folder copy also works. Leave out `.venv`, `.env`, `out`, `data/endpoints.json`, and `data/tls` from another machine. Those are created on the server where VOCE runs. `data/endpoints.json` contains the passwords registered in the admin page. `data/tls` contains that server's private key. Git ignores those files, so a later `git pull` does not overwrite them.

## Requirements

Install these on the jump box before you run `install.ps1` or `install.sh`. The VOCE installer does not install Python.

| What | Required | What it is for |
| --- | --- | --- |
| Windows or Linux | Yes | The server or jump box where VOCE runs. PowerCLI works only on Windows. |
| Python 3.11 or newer | Yes | Runs the app. The command is `python` on Windows and `python3` on Linux, and it must be on `PATH`. |
| pip and venv | Yes | The installer creates `.venv` and installs the Python packages. No C compiler is required. |
| Outbound HTTPS, port 443 | Yes | The jump box must reach vCenter, NSX, Aria Operations, and VCF. |
| Git | Yes, when you clone | Downloads and updates the app from GitHub. The installer does not install Git. |
| Inbound TCP 8080 | When other people open the page | The browser address is `https://<jump-box>:8080`. |
| VMware PowerCLI | Only for the deep vCenter scan | Leave it off for a normal scan. |
| Teams webhook, Power BI, or an AI key | Only for those features | Typed into `.env` after install. Nothing extra to install. |

### Install Python on a Windows jump box

1. Sign in as the account that will run VOCE.
2. Open PowerShell and install Python 3.12:

```powershell
winget install --id Python.Python.3.12 -e --source winget
```

If `winget` is not on that server, download the Windows installer from [python.org](https://www.python.org/downloads/windows/). During setup, check **Add python.exe to PATH** and include pip.

3. Close PowerShell, open a new window, and check the version. It must be 3.11 or newer.

```powershell
python --version
python -m pip --version
```

### Install Python on a Linux jump box

Ubuntu or Debian:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 --version
```

RHEL, Rocky, or Alma:

```bash
sudo dnf install -y python3 python3-pip
python3 --version
```

If that `python3` is older than 3.11, install the `python3.11` package your distribution provides and use that command for the rest of the install. `python3 --version` must print 3.11 or newer.

### Open the network

From the jump box, each VMware address must answer on HTTPS. A quick check is to open the vCenter, NSX, Aria, or SDDC Manager URL in a browser on that same server.

If people will open VOCE from their own computers, allow inbound TCP 8080 to the jump box. Port 443 is optional: set `VCO_PORT=443` in `.env` and start VOCE from an elevated shell.

Active Directory sign-in, described later, also needs outbound TCP 636 to a domain controller.

### Optional: install PowerCLI

Do this only when you want the slower vCenter path: 7-day averages, events, and orphaned disks. A normal scan uses the vCenter REST API and does not need PowerCLI.

On the Windows jump box, in PowerShell:

```powershell
Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
Install-Module -Name VMware.PowerCLI -Scope CurrentUser -Force
```

After the module is installed, turn on **Use PowerCLI for this vCenter** on that endpoint in the admin page. Leave it off on a Linux jump box. Linux has no PowerCLI path.

## Clone or update from Git

The repository is `https://github.com/ppundkar/OPSVI.git`, branch `master`. The jump box needs outbound HTTPS to GitHub. Sign in to GitHub if the repository asks for a username and password. For a password, use a GitHub personal access token, not the GitHub account password.

### Install Git

Windows, in PowerShell:

```powershell
winget install --id Git.Git -e --source winget
```

Close PowerShell, open a new window, and run `git --version`.

Ubuntu or Debian:

```bash
sudo apt update
sudo apt install -y git
git --version
```

RHEL, Rocky, or Alma:

```bash
sudo dnf install -y git
git --version
```

### First time on a jump box

Pick an empty folder. The clone creates `OPSVI` inside it. On Windows, `C:\VOCE` is a simple choice. On Linux, `/opt/voce` is a simple choice.

Windows:

```powershell
New-Item -ItemType Directory -Force -Path C:\VOCE
Set-Location C:\VOCE
git clone --branch master https://github.com/ppundkar/OPSVI.git
Set-Location .\OPSVI
```

Linux:

```bash
sudo mkdir -p /opt/voce
sudo chown "$USER":"$USER" /opt/voce
cd /opt/voce
git clone --branch master https://github.com/ppundkar/OPSVI.git
cd OPSVI
```

You are now in the project folder. Continue with the Windows or Linux install below (`install.ps1` or `install.sh`). That creates `.venv`, `.env`, and the HTTPS certificate on this server.

### Update a jump box that already has VOCE

Run this in the existing project folder, the one that contains `install.ps1`. `git pull` brings in code changes. It leaves `.env`, `data/endpoints.json`, `data/tls`, and `out` on that server.

Windows:

```powershell
Set-Location C:\VOCE\OPSVI
git status
git pull origin master
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
.\start.ps1
```

Linux:

```bash
cd /opt/voce/OPSVI
git status
git pull origin master
./install.sh
./start.sh
```

If VOCE is a systemd service, use `sudo systemctl restart vmware-cost-agent` instead of `./start.sh`.

`git status` before the pull should list only files Git ignores, or nothing. If it lists a changed tracked file, such as `INSTALL.md`, that server has a local edit. Copy that file aside, run `git checkout -- INSTALL.md`, then pull again. Do not delete `.env` or `data` to clear the status. Those paths are ignored and are the live configuration.

`install.ps1` and `install.sh` keep an existing certificate and an existing `.env`. Run them after a pull so any new Python package is installed. Then restart VOCE so the running process loads the new code. Open `https://127.0.0.1:8080/health` and confirm `"status": "ok"`. Endpoints you already saved stay registered.

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

The installer prints the dashboard and admin addresses for this server's name and IP address, for example `https://jump.corp.example:8080` and `https://jump.corp.example:8080/admin`. Use those from another computer. `https://127.0.0.1:8080` still opens the page on the server itself.

The dashboard can analyze the built-in demo estate before any endpoint exists. Live scans use only the endpoints you register.

## Get to a working scan

A working setup means the dashboard opens, each system you care about has a successful **Test login**, and **Analyze registered endpoints** shows that estate. VOCE still only reads. It does not power off, resize, or delete anything. You can stop after vCenter if that is the only system you have. Add NSX, Aria, and VCF when those exist.

Do the demo once before you save any password. On the dashboard, click **Analyze demo estate**. The numbers are a sample, so you can see the page works. Your own numbers appear only after the steps below.

### 1. Put your prices in

Open `config/rates.yaml` on the jump box and replace the sample monthly prices with the prices your organization uses. The fields are dollars per month for one vCPU, one GB of memory, one GB of storage, one NSX segment, one load balancer, one gateway, and one host. Save the file. The next scan uses the new prices. You do not restart VOCE for this file.

### 2. Create a read-only account on each system

Use a separate account for VOCE. It only needs to look. It does not need rights to power off, resize, snapshot, or delete.

| System | Account that is enough |
| --- | --- |
| vCenter | A user that can view virtual machines, hosts, and datastores. The vCenter Read-only role is enough. |
| NSX-T or current NSX | The Auditor role, or another role that can view segments, load balancers, and gateways. |
| NSX-V | A read-only NSX user. |
| Aria Operations | A user that can view objects and metrics. |
| VCF SDDC Manager | A viewer account that can see the domains and clusters. |

Write down the web address, the username, and the password for each system. The address is the same one you type in a browser, for example `https://vcenter.corp.example`. Leave off any path after the host name.

### 3. Open the endpoint page

On the jump box, open https://127.0.0.1:8080/admin. From another computer, open `https://<jump-box-ip>:8080/admin`. If Active Directory sign-in is already on, sign in as someone in `VOCE-Admins`.

You fill in one form per system, then click **Save endpoint**, then **Test login** on that row.

### 4. What each box on the form means

| Box | What to type |
| --- | --- |
| Id | A short name you will recognize, such as `vc-prod`. Letters, numbers, dots, hyphens, or underscores. Start with a letter or number. You cannot change the id later; remove the row and add it again. |
| System | Pick the product. vCenter, NSX-T / NSX, NSX-V, Aria Operations, or VMware Cloud Foundation. |
| URL | The site address, such as `https://vcenter.corp.example`. Do not put the username or password in the address. |
| Username | The account from step 2. For vCenter this is often `readonly@vsphere.local` or `readonly@corp.example`. |
| Password | The account password. To keep the password out of the page, type `${ENV:VCO_VC_PROD_PASSWORD}` and put the real password in `.env` as `VCO_VC_PROD_PASSWORD=the-password`, then restart VOCE before Test login. |
| Site | A label such as `prod` or `lab`. It is printed with the findings so two vCenters stay distinct. |
| Verify TLS certificate | Leave this checked when the system has a real certificate. Clear it only in a lab whose certificate the jump box does not trust. |
| Use PowerCLI for this vCenter | Leave unchecked unless PowerCLI is installed and you want the deep scan. |
| Deep 7-day stats | Leave unchecked for the first scan. Turn it on later, with PowerCLI, when you want a 7-day average instead of one sample. |
| Scan orphaned disks | Leave unchecked for the first scan. It walks datastores and is the slow option. It also needs PowerCLI. |

Click **Save endpoint**. The password is stored in `data/endpoints.json` on this server and is not shown again. On a later edit, leave the password box empty to keep the saved password. **Remove** drops that system from the next scan. Restrict `data/endpoints.json` to the account that runs VOCE. On Linux it is created with mode `600`.

### 5. Register vCenter

1. Click **New endpoint** if the form still has an old row.
2. Id: `vc-prod`
3. System: **vCenter**
4. URL: `https://vcenter.corp.example`
5. Username and password: the read-only vCenter account.
6. Site: `prod`
7. Leave PowerCLI, deep stats, and orphaned disks unchecked.
8. Click **Save endpoint**.
9. On the new row, click **Test login**. A time in the row means the login worked. The error text means it did not. Fix the address, username, or password and save again. The row stays registered either way.

Add a second vCenter the same way with a different id, such as `vc-dr`.

### 6. Register NSX

Current NSX and NSX-T use the same choice.

1. Id: `nsx-prod`
2. System: **NSX-T / NSX**
3. URL: `https://nsx.corp.example` (the NSX Manager address)
4. Username and password: the Auditor or read-only account.
5. Site: `prod`
6. Save, then **Test login**.

An older NSX-V manager uses System **NSX-V** and the NSX-V address. The PowerCLI boxes do nothing for NSX. Leave them unchecked.

### 7. Register Aria Operations

1. Id: `aria-prod`
2. System: **Aria Operations**
3. URL: `https://aria.corp.example`
4. Username and password: the read-only Aria account.
5. Site: `prod`
6. Save, then **Test login**.

When the same virtual machine name exists in vCenter and Aria, the scan uses Aria's 7-day average for CPU and memory. Aria is optional. The vCenter scan still runs without it.

### 8. Register VMware Cloud Foundation

1. Id: `vcf-prod`
2. System: **VMware Cloud Foundation**
3. URL: `https://sddc-manager.corp.example`
4. Username and password: the SDDC Manager viewer account.
5. Site: `prod`
6. Save, then **Test login**.

Skip this form when you do not have SDDC Manager. Host and VCF idle-capacity dollars are upside. They are kept out of the committed monthly total because the virtual machines already carry that cost.

### 9. Run the first live scan

1. Open the dashboard.
2. Click **Analyze registered endpoints**.
3. Wait for the totals. A banner names any system that could not log in. The other systems are still in the report.
4. Open **HTML report** and **CSV**. The same files are under `out/reports/`.
5. Confirm VM templates are called out as skipped. They are not priced.

Click **Analyze registered endpoints** again when you want a fresh collection. An identical scan can reuse the previous result for two minutes.

### 10. Turn on the rest when the scan looks right

These are optional. The scan is already a working report without them.

- **Your prices.** Already set in `config/rates.yaml` in step 1. Change them whenever the contract changes.
- **Teams.** In Teams, create an incoming webhook and paste it into `.env` as `VCO_TEAMS_WEBHOOK_URL`. Restart with `.\start.ps1` or `./start.sh`. The next scan can use **Notify Teams**, or run `.\powershell\Invoke-CostOptimization.ps1 -UseConfig -NotifyTeams -Refresh`.
- **AI recommendations.** Leave `VCO_AI_API_KEY` empty to keep the built-in ranked plan. To ask a model, set `VCO_AI_API_KEY` and restart. The model sees the findings, not the passwords. If the call fails, the report still shows the built-in plan. The exact settings are in `.env.example`.
- **Power BI and a Monday scan.** Follow the Power BI and Scheduled scan sections below. The dashboard button **Push Power BI** sends the demo estate. A live push uses `.\powershell\Invoke-CostOptimization.ps1 -UseConfig -PushPowerBI -Refresh`.
- **People signing in from other computers.** Follow Optional Active Directory sign-in below. Until that is on, anyone who can open the page can run a scan.

A full working jump box is: Python installed, `.\start.ps1` or `./start.sh` running, prices edited, every system you own showing a successful Test login, and one live scan whose HTML report you can open.

## Default certificate

`install.ps1` and `install.sh` create a certificate the first time VOCE is installed on that server. A later install leaves an existing certificate in place, including a custom one.

The default certificate includes:

- the computer name
- the DNS name of the computer, when the server can resolve it
- each IPv4 address of the server
- `localhost` and `127.0.0.1`

The files are `data/tls/cert.pem`, `data/tls/key.pem`, and `data/tls/voce.cer`. `.env` points at the first two and sets `VCO_HOST=0.0.0.0`. Open the dashboard and admin URLs the installer prints, including the port, for example `https://jump.corp.example:8080` and `https://10.1.2.3:8080/admin`.

If the browser says the site cannot provide a secure connection, the certificate name does not match the address in the bar. A certificate made on another computer, or an older certificate that only lists `localhost`, causes that. On the jump box, in the project folder, run `.\enable-https.ps1` or `./enable-https.sh`, then restart with `.\start.ps1` or `./start.sh`. Open one of the addresses it prints, including `:8080`. On another computer, import the new `data/tls/voce.cer` into Trusted Root Certification Authorities. Do not copy `data/tls` from a different server.

On Windows, the install trusts that certificate for the user who ran `install.ps1`. On another computer, import `data/tls/voce.cer` into Trusted Root Certification Authorities. On Linux, browsers trust it after that same import, or after the server administrator adds `data/tls/cert.pem` to the system trust store.

To use `https://<server>` with no port, set `VCO_PORT=443` and start VOCE from an elevated shell. Port 8080 is the default so the process does not need that privilege.

If `.\start.ps1` stops with `winerror 10013` on port 8080, Windows has reserved that port. VOCE then tries 8443 and saves the working port in `.env`. You can also set it yourself:

```text
VCO_PORT=8443
```

Run `.\start.ps1` again and leave that window open. Open the dashboard address it prints, including the new port.

If the browser says `192.168.11.102 refused to connect`, VOCE is not accepting that address. On the jump box:

1. In `.env`, set `VCO_HOST=0.0.0.0` and `VCO_PORT=8443`.
2. Run `.\start.ps1` and leave the window open. It must say `Uvicorn running on https://0.0.0.0:8443`.
3. On the jump box, open `https://127.0.0.1:8443`. When that page loads, open `https://192.168.11.102:8443` from the other computer.
4. If the jump box page loads and the other computer still refuses, open PowerShell as Administrator and run:

```powershell
netsh advfirewall firewall add rule name="VOCE 8443" dir=in action=allow protocol=TCP localport=8443 profile=any
```

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

## Optional Active Directory sign-in and roles

Leave this off when the server is only opened from itself. Turn it on when people open VOCE from other computers. With sign-in off, the pages stay open and no Active Directory group is required.

VOCE checks Active Directory over LDAPS. It does not change accounts or group membership. A person receives one role from their groups:

| Role | Active Directory group | What they can do |
| --- | --- | --- |
| Viewer | `VOCE-Viewers` | Open the dashboard and download HTML and CSV reports |
| Operator | `VOCE-Operators` | Viewer rights, plus run a scan, test logins, notify Teams, and push Power BI |
| Admin | `VOCE-Admins` | Operator rights, plus register, edit, and remove endpoints |

An account in more than one group receives the highest role. An account in none of the groups cannot sign in.

1. In Active Directory Users and Computers, create the three groups `VOCE-Admins`, `VOCE-Operators`, and `VOCE-Viewers`. Put each person in one group.
2. Trust the domain controller certificate, then confirm port 636 is open. LDAPS is required for sign-in, and `VCO_AD_VERIFY_TLS=true` rejects the connection unless the certificate chain is trusted. This is the domain controller certificate, not the VOCE certificate in `data/tls`.
   1. On a domain controller, export the issuing certificate authority as a Base-64 `.cer` file. Export the domain controller certificate as well when its subject name is not the name you will put in `VCO_AD_URL`.
   2. On the VOCE server, import the authority into Trusted Root Certification Authorities for the computer account. On Linux, copy the `.cer` into `/usr/local/share/ca-certificates/` and run `update-ca-certificates`.
   3. The name in `VCO_AD_URL` must match a DNS name on the domain controller certificate. `ldaps://dc01.corp.example:636` fails when the certificate only lists `dc01.corp.example` under another name.
   4. From the VOCE server, test the trust before starting sign-in. A successful test prints the certificate subject and does not print a verify error.

```powershell
openssl s_client -connect dc01.corp.example:636 -showcerts
```

   Leave `VCO_AD_VERIFY_TLS=true`. Set it to `false` only in a lab where the domain controller certificate cannot be trusted.
3. Add the settings below to `.env` on the VOCE server. Use the domain's real names. `VCO_AD_DOMAIN` is the DNS name people use after `@` when they sign in with a short account name.

```text
VCO_AUTH_MODE=ad
VCO_AD_URL=ldaps://dc.corp.example:636
VCO_AD_BASE_DN=DC=corp,DC=example
VCO_AD_DOMAIN=corp.example
VCO_AD_VERIFY_TLS=true
VCO_AD_GROUP_ADMIN=VOCE-Admins
VCO_AD_GROUP_OPERATOR=VOCE-Operators
VCO_AD_GROUP_VIEWER=VOCE-Viewers
```

4. Leave `VCO_AD_BIND_DN` and `VCO_AD_BIND_PASSWORD` empty when each person can read their own group membership. If a sign-in succeeds at Active Directory but VOCE still says the account was not accepted, set those two values to a read-only account that can search users under `VCO_AD_BASE_DN`. That account is used only to find the person. VOCE still checks the person's own password.
5. Set `VCO_API_KEY` to a long random value. The Monday scan and `Invoke-CostOptimization.ps1` send this key and do not use a person's password. Treat the key like an admin password. It is stored only in `.env`.
6. Restart VOCE with `.\start.ps1` or `./start.sh`.
7. Open `https://<server>:8080`. The browser goes to the sign-in page. Sign in as a member of `VOCE-Viewers` and confirm the scan buttons are absent. Sign out, then sign in as a member of `VOCE-Admins` and open Endpoints.
8. On the server, run `.\powershell\Invoke-CostOptimization.ps1 -Demo`. The script reads `VCO_API_KEY` from `.env` and does not prompt for an Active Directory password.

To turn sign-in off again, clear `VCO_AUTH_MODE` and restart. The pages open without a password, as they did at install.

A group value can be the group name, as above, or the full distinguished name. The name matches the `CN` of the group.

## Listen on the network

The default bind is `127.0.0.1`, so only the server itself can open the page. `enable-https.ps1` sets `VCO_HOST=0.0.0.0`. To reach the page without HTTPS, edit `.env`:

```text
VCO_HOST=0.0.0.0
VCO_PORT=8080
VCO_API_KEY=choose-a-long-random-key
```

Browser calls from the dashboard do not send `VCO_API_KEY`. For people using the pages from other computers, turn on Active Directory sign-in in the section above. Set `VCO_API_KEY` when scripts call `/v1`, and send the header `X-API-Key`.

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

1. Install Git and Python 3.11 or newer, using the Requirements steps above.
2. Clone `https://github.com/ppundkar/OPSVI.git` with the commands in Clone or update from Git. A folder copy also works if you leave out `.venv`, `.env`, `out`, `data/endpoints.json`, and `data/tls`.
3. Run `install.ps1` or `install.sh`.
4. Edit the new `.env` for the bind address, API key, Teams, and Power BI values.
5. Start the agent and register the endpoints again, using Get to a working scan above. To refresh this server later, use the update commands in that same Git section.

Re-registering on the new server avoids copying passwords inside the application folder.

## Uninstall

Uninstall stops VOCE on this server and removes the files the installer created here. It does not remove Python, Git, or PowerCLI. It does not change vCenter, NSX, Aria, or VCF. Run it from the project folder, the one that contains `install.ps1`.

Windows:

```powershell
Set-Location C:\VOCE\OPSVI
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
```

Linux:

```bash
cd /opt/voce/OPSVI
chmod +x uninstall.sh
./uninstall.sh
```

If you installed the systemd service, run `sudo ./uninstall.sh` so it can stop and delete `vmware-cost-agent`.

The script does four things:

1. Stops the VOCE process that was started from this folder.
2. On Windows, deletes the scheduled tasks `VOCE` and `VOCE Scan` when those tasks point at this folder. A task that points at a different copy is left alone.
3. On Windows, removes this server's default VOCE certificate from the current user's personal store and Trusted Root store. A company certificate you imported yourself is left in the store. On another computer that trusted `data/tls/voce.cer`, open the certificate store and remove that certificate by hand.
4. Deletes `.venv`, `.env`, `data`, and `out`. That removes saved endpoint passwords, the HTTPS private key, and reports.

The source folder stays, so you can run `install.ps1` or `install.sh` again later.

To uninstall the program but keep passwords, the certificate, and reports:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1 -KeepConfig
```

```bash
./uninstall.sh --keep-config
```

To also delete the project folder after the cleanup:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1 -DeleteFolder
```

```bash
./uninstall.sh --delete-folder
```

`-DeleteFolder` and `--delete-folder` remove the clone, including `INSTALL.md`. Copy anything you still need before you use that switch.

If you added the Monday cron line by hand, delete that line from `crontab -e`. The script does not edit cron.

## Checks

```text
GET https://127.0.0.1:8080/health
```

returns `"status": "ok"`. The admin page lists every saved endpoint. Test login on each row before the first live analysis.
