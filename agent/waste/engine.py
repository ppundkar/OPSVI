"""Waste rules and savings math. This module does not call the network."""

from __future__ import annotations

import math

from agent.config import Rates
from agent.models import Finding, Inventory, InventoryCounts, SavingsSummary, VmRecord

OFF_STATES = {"poweredOff", "suspended"}


def money(value: float) -> float:
    return round(float(value), 2)


def analyze(inventory: Inventory, rates: Rates) -> list[Finding]:
    findings: list[Finding] = []
    idle_host_clusters: set[str] = set()
    thresholds = rates.thresholds

    for vm in inventory.vms:
        if vm.is_template:
            continue
        if vm.power_state in OFF_STATES:
            if vm.powered_off_days is None or vm.powered_off_days >= thresholds.powered_off_days:
                findings.append(_powered_off(vm, rates))
            continue
        if _is_idle(vm, rates):
            findings.append(_idle(vm, rates))
        else:
            cpu_finding = _oversized_cpu(vm, rates)
            if cpu_finding:
                findings.append(cpu_finding)
            mem_finding = _oversized_memory(vm, rates)
            if mem_finding:
                findings.append(mem_finding)
        _append_snapshot(findings, vm, rates)

    for datastore in inventory.datastores:
        if datastore.orphaned_gb <= 0:
            continue
        savings = datastore.orphaned_gb * rates.storage_gb_month
        if savings < rates.min_monthly_savings:
            continue
        findings.append(
            _make(
                category="zombie_vmdk",
                severity="high" if datastore.orphaned_gb >= 500 else "medium",
                confidence=0.85,
                endpoint_id=datastore.endpoint_id,
                resource_type="datastore",
                resource_id=datastore.id,
                resource_name=datastore.name,
                title=f"Zombie VMDKs on {datastore.name}",
                detail=(
                    f"{datastore.orphaned_gb:.0f} GB of VMDK files are not attached to a registered VM."
                ),
                recommendation=(
                    "Confirm the files are absent from VM layouts, archive anything still required, "
                    "then delete the unregistered VMDKs."
                ),
                monthly_savings_usd=savings,
                evidence={"orphaned_gb": datastore.orphaned_gb},
            )
        )

    for segment in inventory.segments:
        if segment.port_count != 0 or not segment.admin_up:
            continue
        if rates.nsx_segment_month < rates.min_monthly_savings:
            continue
        findings.append(
            _make(
                category="unused_segment",
                severity="low",
                confidence=0.9,
                endpoint_id=segment.endpoint_id,
                resource_type="segment",
                resource_id=segment.id,
                resource_name=segment.name,
                title=f"Unused segment {segment.name}",
                detail="The segment is up and has no attached ports.",
                recommendation=(
                    "Confirm no external bindings remain, then remove the segment and any matching "
                    "firewall or DHCP objects."
                ),
                monthly_savings_usd=rates.nsx_segment_month,
                evidence={"port_count": 0},
            )
        )

    for gateway in inventory.gateways:
        if not gateway.enabled or gateway.active_sessions is None or gateway.active_sessions > 0:
            continue
        kind = gateway.gateway_type.lower()
        if kind == "lb":
            findings.append(
                _make(
                    category="idle_load_balancer",
                    severity="medium",
                    confidence=0.7,
                    endpoint_id=gateway.endpoint_id,
                    resource_type="gateway",
                    resource_id=gateway.id,
                    resource_name=gateway.name,
                    title=f"Idle load balancer {gateway.name}",
                    detail="The load balancer reports zero active sessions.",
                    recommendation=(
                        "Validate virtual servers and pools, then remove the load balancer if no "
                        "application still publishes through it."
                    ),
                    monthly_savings_usd=rates.nsx_lb_month,
                    evidence={"active_sessions": 0, "gateway_type": kind},
                )
            )
        elif kind in {"tier1", "edge"} and gateway.status.lower() in {"unused", "idle", "down"}:
            findings.append(
                _make(
                    category="idle_gateway",
                    severity="medium",
                    confidence=0.65,
                    endpoint_id=gateway.endpoint_id,
                    resource_type="gateway",
                    resource_id=gateway.id,
                    resource_name=gateway.name,
                    title=f"Idle gateway {gateway.name}",
                    detail=f"The {kind} gateway is {gateway.status} and has no active sessions.",
                    recommendation=(
                        "Check routed segments and NAT rules, then delete the gateway if the tenant "
                        "network was retired."
                    ),
                    monthly_savings_usd=rates.nsx_gateway_month,
                    evidence={"status": gateway.status, "gateway_type": kind},
                )
            )

    for host in inventory.hosts:
        if host.maintenance or not host.connected:
            continue
        if host.cpu_usage_pct is None or host.mem_usage_pct is None:
            continue
        if host.vm_count > thresholds.host_low_vm_count:
            continue
        if host.cpu_usage_pct > thresholds.host_idle_cpu_pct:
            continue
        if host.mem_usage_pct > thresholds.host_idle_mem_pct:
            continue
        if host.cluster:
            idle_host_clusters.add(host.cluster)
        findings.append(
            _make(
                category="underutilized_host",
                severity="medium",
                confidence=0.45,
                endpoint_id=host.endpoint_id,
                resource_type="host",
                resource_id=host.id,
                resource_name=host.name,
                title=f"Underutilized host {host.name}",
                detail=(
                    f"CPU {host.cpu_usage_pct:.0f}% and memory {host.mem_usage_pct:.0f}% "
                    f"with {host.vm_count} VM(s)."
                ),
                recommendation=(
                    "Confirm the cluster can pass admission control after evacuation, enter "
                    "maintenance mode, then remove the host or reassign its license. "
                    "This upside overlaps VM compute savings."
                ),
                monthly_savings_usd=rates.host_month,
                overlaps_compute=True,
                evidence={
                    "cpu_usage_pct": host.cpu_usage_pct,
                    "mem_usage_pct": host.mem_usage_pct,
                    "vm_count": host.vm_count,
                    "cluster": host.cluster,
                },
            )
        )

    for cluster in inventory.vcf_clusters:
        if cluster.name in idle_host_clusters:
            continue
        if cluster.hosts < thresholds.vcf_min_hosts:
            continue
        if cluster.cpu_usage_pct is None or cluster.mem_usage_pct is None:
            continue
        if cluster.cpu_usage_pct > thresholds.vcf_idle_cpu_pct:
            continue
        if cluster.mem_usage_pct > thresholds.vcf_idle_mem_pct:
            continue
        findings.append(
            _make(
                category="vcf_idle_capacity",
                severity="medium",
                confidence=0.5,
                endpoint_id=cluster.endpoint_id,
                resource_type="cluster",
                resource_id=cluster.name,
                resource_name=cluster.name,
                title=f"Idle capacity in {cluster.domain}/{cluster.name}",
                detail=(
                    f"Workload domain {cluster.domain} cluster {cluster.name} has "
                    f"{cluster.hosts} hosts at CPU {cluster.cpu_usage_pct:.0f}% and "
                    f"memory {cluster.mem_usage_pct:.0f}%."
                ),
                recommendation=(
                    "Model removal of one host in SDDC Manager after a capacity check. "
                    "Do not add this figure on top of host-level savings for the same cluster."
                ),
                monthly_savings_usd=rates.host_month,
                overlaps_compute=True,
                evidence={
                    "domain": cluster.domain,
                    "hosts": cluster.hosts,
                    "cpu_usage_pct": cluster.cpu_usage_pct,
                    "mem_usage_pct": cluster.mem_usage_pct,
                },
            )
        )

    kept = [item for item in findings if item.monthly_savings_usd >= rates.min_monthly_savings]
    kept.sort(key=lambda item: (-item.monthly_savings_usd, item.resource_name, item.category))
    return kept


def summarize(findings: list[Finding], rates: Rates, counts: InventoryCounts) -> SavingsSummary:
    del counts
    gross = money(sum(item.monthly_savings_usd for item in findings))
    conservative = money(
        sum(item.monthly_savings_usd for item in findings if not item.overlaps_compute)
    )
    buckets: dict[str, float] = {}
    for item in findings:
        buckets[item.category] = buckets.get(item.category, 0.0) + item.monthly_savings_usd
    ordered = {
        key: money(value)
        for key, value in sorted(buckets.items(), key=lambda pair: (-pair[1], pair[0]))
    }
    return SavingsSummary(
        currency=rates.currency,
        finding_count=len(findings),
        gross_monthly_usd=gross,
        conservative_monthly_usd=conservative,
        upside_monthly_usd=money(gross - conservative),
        annual_conservative_usd=money(conservative * 12),
        three_year_conservative_usd=money(conservative * 36),
        by_category=ordered,
    )


def _is_idle(vm: VmRecord, rates: Rates) -> bool:
    if vm.cpu_usage_pct is None or vm.mem_usage_pct is None:
        return False
    return (
        vm.cpu_usage_pct <= rates.thresholds.idle_cpu_pct
        and vm.mem_usage_pct <= rates.thresholds.idle_mem_pct
    )


def _powered_off(vm: VmRecord, rates: Rates) -> Finding:
    compute = vm.vcpu * rates.cpu_vcpu_month + vm.memory_gb * rates.memory_gb_month
    storage = vm.used_gb * rates.storage_gb_month
    age = "unknown age" if vm.powered_off_days is None else f"{vm.powered_off_days} days"
    snapshot_note = ""
    if vm.snapshot_gb > 0:
        snapshot_note = f" Snapshots still hold {vm.snapshot_gb:.0f} GB and are included in the delete."
    return _make(
        category="zombie_vm",
        severity="high" if (vm.powered_off_days or 0) >= rates.thresholds.powered_off_days else "medium",
        confidence=0.9 if vm.powered_off_days is not None else 0.6,
        endpoint_id=vm.endpoint_id,
        resource_type="vm",
        resource_id=vm.id,
        resource_name=vm.name,
        title=f"Zombie VM {vm.name}",
        detail=(
            f"{vm.name} has been {vm.power_state} for {age} with {vm.vcpu} vCPU, "
            f"{vm.memory_gb:.0f} GB RAM, and {vm.used_gb:.0f} GB used storage.{snapshot_note}"
        ),
        recommendation=(
            "Confirm the owner and the last backup, then delete the VM. "
            "Compute is idle now; disks should be removed only after the backup check."
        ),
        monthly_savings_usd=compute + storage,
        evidence=_vm_evidence(vm),
    )


def _idle(vm: VmRecord, rates: Rates) -> Finding:
    compute = vm.vcpu * rates.cpu_vcpu_month + vm.memory_gb * rates.memory_gb_month
    return _make(
        category="idle_vm",
        severity="high" if compute * rates.idle_reclaim_factor >= 200 else "medium",
        confidence=0.8,
        endpoint_id=vm.endpoint_id,
        resource_type="vm",
        resource_id=vm.id,
        resource_name=vm.name,
        title=f"Idle VM {vm.name}",
        detail=(
            f"Average CPU {vm.cpu_usage_pct:.1f}% and memory {vm.mem_usage_pct:.1f}% "
            f"on {vm.vcpu} vCPU / {vm.memory_gb:.0f} GB."
        ),
        recommendation=(
            "Park or decommission the guest. Savings count compute only and keep a "
            f"{(1 - rates.idle_reclaim_factor):.0%} holdback until the change window. "
            "Add storage savings only if the disks are deleted."
        ),
        monthly_savings_usd=compute * rates.idle_reclaim_factor,
        evidence=_vm_evidence(vm),
    )


def _oversized_cpu(vm: VmRecord, rates: Rates) -> Finding | None:
    if vm.cpu_usage_pct is None or vm.vcpu < rates.thresholds.min_vcpu_to_resize:
        return None
    if vm.cpu_usage_pct > rates.thresholds.oversize_cpu_pct:
        return None
    target = max(1, vm.vcpu // 2)
    projected = vm.cpu_usage_pct * vm.vcpu / target
    if projected > 70:
        target = max(1, math.ceil(vm.vcpu * vm.cpu_usage_pct / 50))
        if target >= vm.vcpu:
            return None
        projected = vm.cpu_usage_pct * vm.vcpu / target
    saved = vm.vcpu - target
    if saved < 1:
        return None
    return _make(
        category="oversized_cpu",
        severity="medium" if saved * rates.cpu_vcpu_month >= 50 else "low",
        confidence=0.75,
        endpoint_id=vm.endpoint_id,
        resource_type="vm",
        resource_id=vm.id,
        resource_name=vm.name,
        title=f"Oversized CPU on {vm.name}",
        detail=(
            f"CPU averages {vm.cpu_usage_pct:.1f}% across {vm.vcpu} vCPU. "
            f"A target of {target} vCPU projects about {projected:.0f}% utilization."
        ),
        recommendation=(
            f"Reduce {vm.name} from {vm.vcpu} to {target} vCPU during a maintenance window "
            "and watch ready time for one week before cutting further."
        ),
        monthly_savings_usd=saved * rates.cpu_vcpu_month,
        evidence={**_vm_evidence(vm), "target_vcpu": target},
    )


def _oversized_memory(vm: VmRecord, rates: Rates) -> Finding | None:
    if vm.mem_usage_pct is None or vm.memory_gb < rates.thresholds.min_mem_gb:
        return None
    if vm.mem_usage_pct > rates.thresholds.oversize_mem_pct:
        return None
    headroom = rates.thresholds.mem_headroom or 0.7
    target = max(rates.thresholds.min_target_mem_gb, vm.memory_gb * (vm.mem_usage_pct / 100) / headroom)
    target = round(target, 1)
    saved = vm.memory_gb - target
    if saved < 1:
        return None
    return _make(
        category="oversized_memory",
        severity="medium" if saved * rates.memory_gb_month >= 50 else "low",
        confidence=0.75,
        endpoint_id=vm.endpoint_id,
        resource_type="vm",
        resource_id=vm.id,
        resource_name=vm.name,
        title=f"Oversized memory on {vm.name}",
        detail=(
            f"Memory averages {vm.mem_usage_pct:.1f}% of {vm.memory_gb:.0f} GB. "
            f"A target of {target:.1f} GB keeps about {int(headroom * 100)}% headroom."
        ),
        recommendation=(
            f"Reduce {vm.name} memory from {vm.memory_gb:.0f} GB to {target:.1f} GB "
            "after confirming guest tools and ballooning behavior."
        ),
        monthly_savings_usd=saved * rates.memory_gb_month,
        evidence={**_vm_evidence(vm), "target_memory_gb": target},
    )


def _append_snapshot(findings: list[Finding], vm: VmRecord, rates: Rates) -> None:
    if vm.snapshot_gb <= 0 or vm.oldest_snapshot_days < rates.thresholds.snapshot_days:
        return
    savings = vm.snapshot_gb * rates.snapshot_gb_month
    if savings < rates.min_monthly_savings:
        return
    findings.append(
        _make(
            category="stale_snapshot",
            severity="medium" if vm.oldest_snapshot_days >= 14 or vm.snapshot_gb >= 100 else "low",
            confidence=0.95,
            endpoint_id=vm.endpoint_id,
            resource_type="vm",
            resource_id=vm.id,
            resource_name=vm.name,
            title=f"Stale snapshot on {vm.name}",
            detail=(
                f"{vm.snapshot_count or 1} snapshot(s), oldest {vm.oldest_snapshot_days} days, "
                f"about {vm.snapshot_gb:.0f} GB."
            ),
            recommendation=(
                "Consolidate the snapshot chain in a maintenance window. "
                "Long chains increase datastore latency as well as cost."
            ),
            monthly_savings_usd=savings,
            evidence=_vm_evidence(vm),
        )
    )


def _vm_evidence(vm: VmRecord) -> dict:
    return {
        "power_state": vm.power_state,
        "vcpu": vm.vcpu,
        "memory_gb": vm.memory_gb,
        "used_gb": vm.used_gb,
        "cpu_usage_pct": vm.cpu_usage_pct,
        "mem_usage_pct": vm.mem_usage_pct,
        "powered_off_days": vm.powered_off_days,
        "snapshot_gb": vm.snapshot_gb,
        "oldest_snapshot_days": vm.oldest_snapshot_days,
        "metrics_source": vm.metrics_source,
    }


def _make(**kwargs) -> Finding:
    kwargs["monthly_savings_usd"] = money(kwargs["monthly_savings_usd"])
    kwargs["id"] = f"{kwargs['category']}:{kwargs['endpoint_id']}:{kwargs['resource_id']}"
    return Finding(**kwargs)
