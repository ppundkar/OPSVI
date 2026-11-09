"""vCenter inventory over the vSphere Automation REST API."""

from __future__ import annotations

import httpx

from agent.collectors.http import as_list, basic_auth, raise_for_auth, read_json
from agent.models import DatastoreRecord, EndpointInput, HostRecord, Inventory, VmRecord

GIB = 1024**3


async def probe_vcenter(endpoint: EndpointInput, client: httpx.AsyncClient) -> str:
    token = await _login(endpoint, client)
    await _logout(client, token)
    return "vSphere REST session"


async def collect_vcenter(endpoint: EndpointInput, client: httpx.AsyncClient) -> Inventory:
    token = await _login(endpoint, client)
    headers = {"vmware-api-session-id": token}
    try:
        vm_resp, host_resp, ds_resp = await _gather_gets(
            client,
            ("/api/vcenter/vm", headers),
            ("/api/vcenter/host", headers),
            ("/api/vcenter/datastore", headers),
        )
        return parse_vcenter_rest(
            read_json(vm_resp, "vCenter"),
            read_json(host_resp, "vCenter"),
            read_json(ds_resp, "vCenter"),
            endpoint.id,
        )
    finally:
        await _logout(client, token)


async def _gather_gets(client: httpx.AsyncClient, *calls: tuple[str, dict]):
    import asyncio

    return await asyncio.gather(*(client.get(path, headers=headers) for path, headers in calls))


async def _login(endpoint: EndpointInput, client: httpx.AsyncClient) -> str:
    response = await client.post("/api/session", auth=basic_auth(endpoint))
    raise_for_auth(response, "vCenter")
    token = response.text.strip().strip('"')
    if not token:
        raise RuntimeError("vCenter session response was empty")
    return token


async def _logout(client: httpx.AsyncClient, token: str) -> None:
    try:
        await client.delete("/api/session", headers={"vmware-api-session-id": token})
    except Exception:
        return


def _is_template(row: dict) -> bool:
    if row.get("template") is True or row.get("is_template") is True:
        return True
    return str(row.get("type") or row.get("vm_type") or "").upper() == "TEMPLATE"


def parse_vcenter_rest(vms_payload, hosts_payload, datastores_payload, endpoint_id: str) -> Inventory:
    vms: list[VmRecord] = []
    for row in as_list((vms_payload or {}).get("value") if isinstance(vms_payload, dict) else vms_payload):
        memory = row.get("memory_size_MiB")
        vms.append(
            VmRecord(
                endpoint_id=endpoint_id,
                id=str(row.get("vm") or row.get("id") or row.get("name")),
                name=str(row.get("name") or row.get("vm") or "vm"),
                power_state=row.get("power_state") or "unknown",
                is_template=_is_template(row),
                vcpu=int(row.get("cpu_count") or 0),
                memory_gb=round((memory or 0) / 1024, 2),
                metrics_source="vcenter",
            )
        )
    hosts: list[HostRecord] = []
    for row in as_list((hosts_payload or {}).get("value") if isinstance(hosts_payload, dict) else hosts_payload):
        state = str(row.get("connection_state") or "CONNECTED")
        power = str(row.get("power_state") or "")
        hosts.append(
            HostRecord(
                endpoint_id=endpoint_id,
                id=str(row.get("host") or row.get("id") or row.get("name")),
                name=str(row.get("name") or "host"),
                connected=state.upper() == "CONNECTED",
                maintenance=power.upper() in {"STANDBY", "MAINTENANCE"},
            )
        )
    datastores: list[DatastoreRecord] = []
    for row in as_list(
        (datastores_payload or {}).get("value") if isinstance(datastores_payload, dict) else datastores_payload
    ):
        capacity = float(row.get("capacity") or 0)
        free = float(row.get("free_space") or 0)
        datastores.append(
            DatastoreRecord(
                endpoint_id=endpoint_id,
                id=str(row.get("datastore") or row.get("id") or row.get("name")),
                name=str(row.get("name") or "datastore"),
                capacity_gb=round(capacity / GIB, 1),
                free_gb=round(free / GIB, 1),
            )
        )
    return Inventory(vms=vms, hosts=hosts, datastores=datastores)
