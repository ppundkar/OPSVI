"""Aria Operations utilization. One batched stats call keeps the scan fast."""

from __future__ import annotations

import time

import httpx

from agent.collectors.http import as_list, read_json
from agent.config import Settings
from agent.models import EndpointInput, Inventory, MetricPatch


async def probe_aria(endpoint: EndpointInput, client: httpx.AsyncClient) -> str:
    token = await _login(endpoint, client)
    await _logout(client, token)
    return "Aria Operations token"


async def collect_aria(endpoint: EndpointInput, client: httpx.AsyncClient, settings: Settings) -> Inventory:
    token = await _login(endpoint, client)
    headers = {"Authorization": f"vRealizeOpsToken {token}", "Accept": "application/json"}
    try:
        response = await client.get(
            "/suite-api/api/resources",
            params={"resourceKind": "VirtualMachine", "pageSize": settings.aria_stat_limit},
            headers=headers,
        )
        payload = read_json(response, "Aria Operations")
        resources = as_list(payload.get("resourceList") if isinstance(payload, dict) else payload)
        resources = resources[: settings.aria_stat_limit]
        if not resources:
            return Inventory()
        stats = await _stats(client, headers, [str(item.get("identifier")) for item in resources if item.get("identifier")])
        patches = parse_aria_stats(resources, stats)
        inventory = Inventory(metric_patches=patches)
        total = payload.get("pageInfo", {}).get("totalCount") if isinstance(payload, dict) else None
        if total and int(total) > len(resources):
            inventory.warnings.append(
                f"Aria stats capped at {settings.aria_stat_limit} of {total} virtual machines"
            )
        return inventory
    finally:
        await _logout(client, token)


async def _login(endpoint: EndpointInput, client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/suite-api/api/auth/token/acquire",
        json={
            "username": endpoint.username,
            "password": endpoint.password.get_secret_value(),
            "authSource": "local",
        },
    )
    payload = read_json(response, "Aria Operations")
    token = payload.get("token") if isinstance(payload, dict) else None
    if not token:
        raise RuntimeError("Aria Operations did not return a token")
    return str(token)


async def _logout(client: httpx.AsyncClient, token: str) -> None:
    try:
        await client.post(
            "/suite-api/api/auth/token/release",
            headers={"Authorization": f"vRealizeOpsToken {token}"},
        )
    except Exception:
        return


async def _stats(client: httpx.AsyncClient, headers: dict, resource_ids: list[str]) -> dict:
    end = int(time.time() * 1000)
    begin = end - 7 * 24 * 60 * 60 * 1000
    response = await client.post(
        "/suite-api/api/resources/stats/query",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "resourceId": resource_ids,
            "statKey": ["cpu|usage_average", "mem|usage_average"],
            "begin": begin,
            "end": end,
            "rollUpType": "AVG",
            "intervalType": "DAYS",
            "intervalQuantifier": 1,
        },
    )
    if response.status_code == 404:
        return {}
    return read_json(response, "Aria Operations")


def parse_aria_stats(resources: list[dict], stats_payload: dict) -> list[MetricPatch]:
    names = {}
    for resource in resources:
        identifier = str(resource.get("identifier") or "")
        key = resource.get("resourceKey") or {}
        names[identifier] = str(key.get("name") or resource.get("name") or identifier)
    values = _index_stats(stats_payload)
    patches: list[MetricPatch] = []
    seen: set[str] = set()
    for identifier, metrics in values.items():
        name = names.get(identifier)
        if not name:
            continue
        seen.add(identifier)
        patches.append(
            MetricPatch(
                name=name,
                resource_id=identifier,
                cpu_usage_pct=metrics.get("cpu|usage_average"),
                mem_usage_pct=metrics.get("mem|usage_average"),
            )
        )
    for identifier, name in names.items():
        if identifier in seen or not name:
            continue
        patches.append(MetricPatch(name=name, resource_id=identifier))
    return patches


def _index_stats(payload: dict) -> dict[str, dict[str, float]]:
    found: dict[str, dict[str, float]] = {}
    if not isinstance(payload, dict):
        return found
    rows = payload.get("values") or payload.get("resource-stat") or []
    for row in as_list(rows):
        identifier = str(row.get("resourceId") or row.get("resource-id") or "")
        stat_list = row.get("stat-list") or row.get("statList") or {}
        stats = as_list(stat_list.get("stat") if isinstance(stat_list, dict) else stat_list)
        bucket = found.setdefault(identifier, {})
        for stat in stats:
            key = stat.get("statKey") or {}
            if isinstance(key, dict):
                name = str(key.get("key") or "")
            else:
                name = str(key)
            data = stat.get("data") or stat.get("values") or []
            if isinstance(data, dict):
                data = data.get("value") or data.get("data") or []
            if isinstance(data, list) and data:
                try:
                    bucket[name] = float(data[-1])
                except (TypeError, ValueError):
                    continue
    return found
