"""Parallel login and collection across vCenter, NSX, Aria, and VCF."""

from __future__ import annotations

import asyncio
import time

from agent.collectors.aria import collect_aria, probe_aria
from agent.collectors.http import client_for, redact
from agent.collectors.nsx import collect_nsx, collect_nsxt, probe_nsx, probe_nsxt
from agent.collectors.powershell import collect_vcenter_powershell
from agent.collectors.vcenter import collect_vcenter, probe_vcenter
from agent.collectors.vcf import collect_vcf, probe_vcf
from agent.config import Settings
from agent.merge import counts_for, overlay_metrics
from agent.models import EndpointInput, EndpointStatus, Inventory

MAX_VMS = 20000


async def probe_all(endpoints: list[EndpointInput], settings: Settings) -> list[EndpointStatus]:
    semaphore = asyncio.Semaphore(max(1, settings.max_concurrency))

    async def one(endpoint: EndpointInput) -> EndpointStatus:
        async with semaphore:
            return await _probe_one(endpoint, settings)

    return list(await asyncio.gather(*(one(endpoint) for endpoint in endpoints)))


async def collect_all(endpoints: list[EndpointInput], settings: Settings) -> tuple[Inventory, list[EndpointStatus]]:
    semaphore = asyncio.Semaphore(max(1, settings.max_concurrency))

    async def one(endpoint: EndpointInput):
        async with semaphore:
            return await _collect_one(endpoint, settings)

    parts = await asyncio.gather(*(one(endpoint) for endpoint in endpoints))
    inventory = Inventory()
    statuses: list[EndpointStatus] = []
    for status, part in parts:
        statuses.append(status)
        if part is not None:
            inventory.extend(part)
    overlay_metrics(inventory)
    if len(inventory.vms) > MAX_VMS:
        inventory.warnings.append(f"VM analysis capped at {MAX_VMS} records")
        inventory.vms = inventory.vms[:MAX_VMS]
    return inventory, statuses


async def _probe_one(endpoint: EndpointInput, settings: Settings) -> EndpointStatus:
    started = time.perf_counter()
    secret = endpoint.password.get_secret_value()
    try:
        _require_secret(endpoint)
        async with client_for(endpoint, settings.collector_timeout_seconds) as client:
            detail = await _PROBES[endpoint.kind](endpoint, client)
        return _status(endpoint, True, started, detail=detail)
    except Exception as exc:
        return _status(endpoint, False, started, error=redact(str(exc), secret))


async def _collect_one(endpoint: EndpointInput, settings: Settings) -> tuple[EndpointStatus, Inventory | None]:
    started = time.perf_counter()
    secret = endpoint.password.get_secret_value()
    try:
        _require_secret(endpoint)
        if endpoint.kind == "vcenter" and endpoint.use_powershell:
            try:
                inventory = await collect_vcenter_powershell(endpoint, settings)
                return _status(
                    endpoint,
                    True,
                    started,
                    detail="PowerCLI",
                    resource_count=_resource_count(inventory),
                ), inventory
            except Exception as exc:
                async with client_for(endpoint, settings.collector_timeout_seconds) as client:
                    inventory = await collect_vcenter(endpoint, client)
                inventory.warnings.append(f"PowerCLI failed, used vSphere REST: {redact(str(exc), secret)}")
                return _status(
                    endpoint,
                    True,
                    started,
                    detail="vSphere REST after PowerCLI failure",
                    resource_count=_resource_count(inventory),
                ), inventory
        async with client_for(endpoint, settings.collector_timeout_seconds) as client:
            inventory = await _COLLECT[endpoint.kind](endpoint, client, settings)
        return _status(
            endpoint,
            True,
            started,
            detail=_DETAIL[endpoint.kind],
            resource_count=_resource_count(inventory),
        ), inventory
    except Exception as exc:
        return _status(endpoint, False, started, error=redact(str(exc), secret)), None


def _require_secret(endpoint: EndpointInput) -> None:
    if not endpoint.username or not endpoint.password.get_secret_value():
        raise ValueError("username and password are required")


def _status(
    endpoint: EndpointInput,
    ok: bool,
    started: float,
    detail: str = "",
    error: str | None = None,
    resource_count: int = 0,
) -> EndpointStatus:
    return EndpointStatus(
        id=endpoint.id,
        kind=endpoint.kind,
        url=endpoint.url,
        ok=ok,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        resource_count=resource_count,
        error=error,
        detail=detail,
    )


def _resource_count(inventory: Inventory) -> int:
    counted = counts_for(inventory)
    return (
        counted.vms
        + counted.hosts
        + counted.datastores
        + counted.segments
        + counted.gateways
        + counted.vcf_clusters
        + counted.metric_patches
    )


async def _collect_vcenter(endpoint, client, settings):
    del settings
    return await collect_vcenter(endpoint, client)


async def _collect_nsxt(endpoint, client, settings):
    return await collect_nsxt(endpoint, client, settings)


async def _collect_nsx(endpoint, client, settings):
    return await collect_nsx(endpoint, client, settings)


async def _collect_aria(endpoint, client, settings):
    return await collect_aria(endpoint, client, settings)


async def _collect_vcf(endpoint, client, settings):
    del settings
    return await collect_vcf(endpoint, client)


_PROBES = {
    "vcenter": probe_vcenter,
    "nsxt": probe_nsxt,
    "nsx": probe_nsx,
    "aria": probe_aria,
    "vcf": probe_vcf,
}
_COLLECT = {
    "vcenter": _collect_vcenter,
    "nsxt": _collect_nsxt,
    "nsx": _collect_nsx,
    "aria": _collect_aria,
    "vcf": _collect_vcf,
}
_DETAIL = {
    "vcenter": "vSphere REST",
    "nsxt": "NSX-T policy API",
    "nsx": "NSX-V API",
    "aria": "Aria Operations stats",
    "vcf": "SDDC Manager",
}
