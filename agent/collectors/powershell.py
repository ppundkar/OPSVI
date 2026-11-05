"""Optional PowerCLI collection for snapshots, quick stats, and orphaned disks.

Password and username are read from the process environment so they are not
placed on the PowerShell command line.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlparse

from agent.collectors.http import redact
from agent.config import ROOT, Settings
from agent.models import EndpointInput, Inventory

SCRIPT = ROOT / "powershell" / "Collect-VCenter.ps1"


async def collect_vcenter_powershell(endpoint: EndpointInput, settings: Settings) -> Inventory:
    if not SCRIPT.exists():
        raise FileNotFoundError(f"Missing {SCRIPT}")
    parsed = urlparse(endpoint.url)
    server = parsed.hostname or ""
    if parsed.port:
        server = f"{server}:{parsed.port}"
    timeout = settings.powershell_timeout_seconds
    if endpoint.deep_stats or endpoint.orphaned_disks:
        timeout = max(timeout, 180)
    args = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        "-Server",
        server,
    ]
    if endpoint.deep_stats:
        args.append("-Deep")
    if endpoint.orphaned_disks:
        args.append("-IncludeOrphanedDisks")
    if not endpoint.verify_ssl:
        args.append("-TrustAll")
    env_password = endpoint.password.get_secret_value()
    import os

    env = os.environ.copy()
    env["VCO_USERNAME"] = endpoint.username
    env["VCO_PASSWORD"] = env_password
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError as exc:
        process.kill()
        raise TimeoutError(f"PowerCLI collection exceeded {timeout:.0f}s") from exc
    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    error_text = redact((stderr or b"").decode("utf-8", errors="replace"), env_password)
    if process.returncode != 0:
        message = error_text or text or f"PowerCLI exited {process.returncode}"
        raise RuntimeError(redact(message, env_password))
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"PowerCLI did not return JSON ({error_text[:180]})") from exc
    inventory = Inventory.model_validate(payload)
    for collection in (inventory.vms, inventory.hosts, inventory.datastores):
        for record in collection:
            if not record.endpoint_id:
                record.endpoint_id = endpoint.id
            elif record.endpoint_id == "vcenter":
                record.endpoint_id = endpoint.id
    for record in inventory.vms:
        record.endpoint_id = endpoint.id
    for record in inventory.hosts:
        record.endpoint_id = endpoint.id
    for record in inventory.datastores:
        record.endpoint_id = endpoint.id
    return inventory
