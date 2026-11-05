"""NSX-V and NSX-T inventory."""

from __future__ import annotations

import asyncio

import httpx

from agent.collectors.http import as_list, basic_auth, read_json
from agent.config import Settings
from agent.models import EndpointInput, Inventory, NsxGateway, NsxSegment


async def probe_nsxt(endpoint: EndpointInput, client: httpx.AsyncClient) -> str:
    headers = await _nsxt_session(endpoint, client)
    response = await client.get("/policy/api/v1/infra/segments", params={"page_size": 1}, headers=headers)
    read_json(response, "NSX-T")
    await _nsxt_logout(client, headers)
    return "NSX-T session"


async def probe_nsx(endpoint: EndpointInput, client: httpx.AsyncClient) -> str:
    response = await client.get("/api/2.0/services/vsmstatus", auth=basic_auth(endpoint))
    if response.status_code == 404:
        response = await client.get("/api/1.0/appliance-management/summary", auth=basic_auth(endpoint))
    read_json(response, "NSX")
    return "NSX-V basic authentication"


async def collect_nsxt(endpoint: EndpointInput, client: httpx.AsyncClient, settings: Settings) -> Inventory:
    headers = await _nsxt_session(endpoint, client)
    try:
        segments = await _paged(client, "/policy/api/v1/infra/segments", headers)
        tier1s = await _paged(client, "/policy/api/v1/infra/tier-1s", headers)
        load_balancers = await _paged(client, "/policy/api/v1/infra/lb-services", headers)
        port_counts = await _port_counts(client, headers, segments, settings.nsx_port_lookup_limit)
        parsed = parse_nsxt(segments, tier1s, load_balancers, port_counts, endpoint.id)
        if len(segments) > settings.nsx_port_lookup_limit:
            parsed.warnings.append(
                f"NSX port lookup capped at {settings.nsx_port_lookup_limit} segments; "
                "remaining segments were inventoried without a waste flag"
            )
        return parsed
    finally:
        await _nsxt_logout(client, headers)


async def collect_nsx(endpoint: EndpointInput, client: httpx.AsyncClient, settings: Settings) -> Inventory:
    del settings
    auth = basic_auth(endpoint)
    wires = await client.get("/api/2.0/vdn/virtualwires", auth=auth)
    edges = await client.get("/api/4.0/edges", auth=auth)
    return parse_nsxv(read_json(wires, "NSX"), read_json(edges, "NSX"), endpoint.id)


async def _nsxt_session(endpoint: EndpointInput, client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/session/create",
        auth=basic_auth(endpoint),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code in {401, 403}:
        raise PermissionError(f"NSX-T authentication failed ({response.status_code})")
    response.raise_for_status()
    token = response.headers.get("X-XSRF-TOKEN") or response.headers.get("x-xsrf-token") or ""
    headers = {"Accept": "application/json"}
    if token:
        headers["X-XSRF-TOKEN"] = token
    return headers


async def _nsxt_logout(client: httpx.AsyncClient, headers: dict[str, str]) -> None:
    try:
        await client.post("/api/session/destroy", headers=headers)
    except Exception:
        return


async def _paged(client: httpx.AsyncClient, path: str, headers: dict[str, str]) -> list[dict]:
    items: list[dict] = []
    cursor = None
    for _ in range(20):
        params = {"page_size": 200}
        if cursor:
            params["cursor"] = cursor
        response = await client.get(path, params=params, headers=headers)
        if response.status_code == 404:
            return items
        payload = read_json(response, "NSX-T")
        items.extend(as_list(payload.get("results") if isinstance(payload, dict) else payload))
        cursor = payload.get("cursor") if isinstance(payload, dict) else None
        if not cursor:
            break
    return items


async def _port_counts(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    segments: list[dict],
    limit: int,
) -> dict[str, int | None]:
    selected = segments[: max(limit, 0)]
    semaphore = asyncio.Semaphore(10)

    async def one(segment: dict) -> tuple[str, int | None]:
        seg_id = str(segment.get("id") or "")
        async with semaphore:
            response = await client.get(f"/policy/api/v1/infra/segments/{seg_id}/ports", headers=headers)
        if response.status_code == 404:
            return seg_id, None
        if response.status_code >= 400:
            return seg_id, None
        payload = response.json()
        results = as_list(payload.get("results") if isinstance(payload, dict) else payload)
        if isinstance(payload, dict) and payload.get("result_count") is not None:
            return seg_id, int(payload["result_count"])
        return seg_id, len(results)

    pairs = await asyncio.gather(*(one(segment) for segment in selected))
    return {key: value for key, value in pairs}


def parse_nsxt(segments, tier1s, load_balancers, port_counts: dict[str, int | None], endpoint_id: str) -> Inventory:
    parsed_segments: list[NsxSegment] = []
    for row in segments:
        seg_id = str(row.get("id") or row.get("display_name") or "segment")
        admin = str(row.get("admin_state") or "UP")
        parsed_segments.append(
            NsxSegment(
                endpoint_id=endpoint_id,
                id=seg_id,
                name=str(row.get("display_name") or seg_id),
                port_count=port_counts.get(seg_id),
                admin_up=admin.upper() != "DOWN",
            )
        )
    gateways: list[NsxGateway] = []
    for row in tier1s:
        gateways.append(
            NsxGateway(
                endpoint_id=endpoint_id,
                id=str(row.get("id") or row.get("display_name")),
                name=str(row.get("display_name") or row.get("id") or "tier1"),
                gateway_type="tier1",
                active_sessions=_sessions(row),
                status=str(row.get("status") or row.get("ha_mode") or ""),
            )
        )
    for row in load_balancers:
        gateways.append(
            NsxGateway(
                endpoint_id=endpoint_id,
                id=str(row.get("id") or row.get("display_name")),
                name=str(row.get("display_name") or row.get("id") or "lb"),
                gateway_type="lb",
                active_sessions=_sessions(row),
                status=str(row.get("enabled") or ""),
                enabled=row.get("enabled", True) is not False,
            )
        )
    return Inventory(segments=parsed_segments, gateways=gateways)


def parse_nsxv(wires_payload, edges_payload, endpoint_id: str) -> Inventory:
    wire_rows = []
    if isinstance(wires_payload, dict):
        wire_rows = as_list(wires_payload.get("data") or wires_payload.get("virtualWires"))
    edge_rows = []
    if isinstance(edges_payload, dict):
        paging = edges_payload.get("edgePage") or edges_payload
        edge_rows = as_list(paging.get("data") or paging.get("edges"))
    segments = []
    for row in wire_rows:
        ports = row.get("vmCount", row.get("vcenterPortCount", row.get("portCount")))
        segments.append(
            NsxSegment(
                endpoint_id=endpoint_id,
                id=str(row.get("objectId") or row.get("name")),
                name=str(row.get("name") or row.get("objectId")),
                port_count=int(ports) if ports is not None else None,
            )
        )
    gateways = []
    for row in edge_rows:
        edge_type = str(row.get("edgeType") or row.get("type") or "edge").lower()
        if "lb" in edge_type or row.get("loadBalancer"):
            kind = "lb"
        else:
            kind = "edge"
        state = str(row.get("state") or row.get("edgeStatus") or "")
        gateways.append(
            NsxGateway(
                endpoint_id=endpoint_id,
                id=str(row.get("objectId") or row.get("id") or row.get("name")),
                name=str(row.get("name") or "edge"),
                gateway_type=kind,
                active_sessions=_sessions(row),
                status=state,
            )
        )
    return Inventory(segments=segments, gateways=gateways)


def _sessions(row: dict) -> int | None:
    for key in ("active_sessions", "activeSessions", "session_count", "sessionCount"):
        if row.get(key) is not None:
            return int(row[key])
    return None
