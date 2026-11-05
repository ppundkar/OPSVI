"""Combine collector output and prefer Aria time-series over point samples."""

from __future__ import annotations

from agent.models import Inventory, InventoryCounts


def counts_for(inventory: Inventory) -> InventoryCounts:
    return InventoryCounts(
        vms=len(inventory.vms),
        hosts=len(inventory.hosts),
        datastores=len(inventory.datastores),
        segments=len(inventory.segments),
        gateways=len(inventory.gateways),
        vcf_clusters=len(inventory.vcf_clusters),
        metric_patches=len(inventory.metric_patches),
    )


def overlay_metrics(inventory: Inventory) -> Inventory:
    """Aria 7-day averages replace vCenter point-in-time CPU and memory."""

    if not inventory.metric_patches:
        return inventory
    by_name: dict[str, list] = {}
    for patch in inventory.metric_patches:
        by_name.setdefault(patch.name.casefold(), []).append(patch)

    matched: set[str] = set()
    for vm in inventory.vms:
        patches = by_name.get(vm.name.casefold())
        if not patches:
            continue
        patch = patches[0]
        matched.add(vm.name.casefold())
        if patch.cpu_usage_pct is not None:
            vm.cpu_usage_pct = patch.cpu_usage_pct
        if patch.mem_usage_pct is not None:
            vm.mem_usage_pct = patch.mem_usage_pct
        vm.metrics_source = "aria"

    missing = [name for name in by_name if name not in matched]
    if missing:
        inventory.warnings.append(
            f"Aria metrics for {len(missing)} VM names did not match a vCenter VM"
        )
    return inventory
