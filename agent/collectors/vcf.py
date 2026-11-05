"""VMware Cloud Foundation workload domains and clusters."""

from __future__ import annotations

import httpx

from agent.collectors.http import as_list, read_json
from agent.models import EndpointInput, Inventory, VcfCluster


async def probe_vcf(endpoint: EndpointInput, client: httpx.AsyncClient) -> str:
    token = await _login(endpoint, client)
    await _logout(client, token)
    return "SDDC Manager token"


async def collect_vcf(endpoint: EndpointInput, client: httpx.AsyncClient) -> Inventory:
    token = await _login(endpoint, client)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        domains = read_json(await client.get("/v1/domains", headers=headers), "VCF")
        clusters = read_json(await client.get("/v1/clusters", headers=headers), "VCF")
        inventory = parse_vcf(domains, clusters, endpoint.id)
        if inventory.vcf_clusters and all(item.cpu_usage_pct is None for item in inventory.vcf_clusters):
            inventory.warnings.append(
                "VCF returned clusters without utilization. Idle-capacity findings need Aria or host stats."
            )
        return inventory
    finally:
        await _logout(client, token)


async def _login(endpoint: EndpointInput, client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/v1/tokens",
        json={"username": endpoint.username, "password": endpoint.password.get_secret_value()},
    )
    payload = read_json(response, "VCF")
    token = payload.get("accessToken") or payload.get("access_token")
    if not token:
        raise RuntimeError("VCF did not return an access token")
    return str(token)


async def _logout(client: httpx.AsyncClient, token: str) -> None:
    try:
        await client.delete("/v1/tokens", headers={"Authorization": f"Bearer {token}"})
    except Exception:
        return


def parse_vcf(domains_payload, clusters_payload, endpoint_id: str) -> Inventory:
    domains = {}
    domain_rows = as_list(
        (domains_payload or {}).get("elements") if isinstance(domains_payload, dict) else domains_payload
    )
    for row in domain_rows:
        domains[str(row.get("id") or "")] = str(row.get("name") or row.get("id") or "domain")
    clusters = []
    rows = as_list(
        (clusters_payload or {}).get("elements") if isinstance(clusters_payload, dict) else clusters_payload
    )
    for row in rows:
        domain_id = str(row.get("domainId") or row.get("domain", {}).get("id") or "")
        if isinstance(row.get("domain"), dict):
            domain_name = str(row["domain"].get("name") or domains.get(domain_id) or domain_id or "domain")
        else:
            domain_name = domains.get(domain_id) or str(row.get("domainName") or domain_id or "domain")
        util = row.get("utilization") or row.get("resourceUtilization") or {}
        clusters.append(
            VcfCluster(
                endpoint_id=endpoint_id,
                domain=domain_name,
                name=str(row.get("name") or row.get("id") or "cluster"),
                hosts=int(row.get("hostCount") or row.get("hosts") or len(row.get("hosts") or []) or 0),
                cores=int(row.get("coreCount") or util.get("cores") or 0),
                cpu_usage_pct=_pct(util, ("cpuUsedPct", "cpuPercent", "cpu")),
                mem_usage_pct=_pct(util, ("memoryUsedPct", "memoryPercent", "memory")),
            )
        )
    return Inventory(vcf_clusters=clusters)


def _pct(payload: dict, keys: tuple[str, ...]) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        if payload.get(key) is not None:
            try:
                return float(payload[key])
            except (TypeError, ValueError):
                return None
    return None
