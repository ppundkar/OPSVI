"""Collector parsers and metric merge."""

import pytest

from agent.collectors.aria import parse_aria_stats
from agent.collectors.http import assert_read_only
from agent.collectors.nsx import parse_nsxt, parse_nsxv
from agent.collectors.vcenter import parse_vcenter_rest
from agent.collectors.vcf import parse_vcf
from agent.merge import overlay_metrics
from agent.models import Inventory, MetricPatch, VmRecord
from agent.waste.engine import analyze
from agent.config import Rates


def test_infrastructure_writes_are_refused():
    assert_read_only("GET", "/api/vcenter/vm")
    assert_read_only("POST", "/api/session")
    assert_read_only("DELETE", "/v1/tokens")
    with pytest.raises(RuntimeError, match="read-only"):
        assert_read_only("POST", "/api/vcenter/vm/vm-1/power")
    with pytest.raises(RuntimeError, match="read-only"):
        assert_read_only("DELETE", "/api/vcenter/vm/vm-1")


def test_vcenter_rest_normalizes_power_and_memory():
    inventory = parse_vcenter_rest(
        {"value": [{"vm": "vm-10", "name": "app", "power_state": "POWERED_OFF", "cpu_count": 2, "memory_size_MiB": 2048}]},
        {"value": [{"host": "host-1", "name": "esx1", "connection_state": "DISCONNECTED"}]},
        {"value": [{"datastore": "ds-1", "name": "ds", "capacity": 1024**4, "free_space": 512 * 1024**3}]},
        "vc-prod",
    )
    assert inventory.vms[0].power_state == "poweredOff"
    assert inventory.vms[0].memory_gb == 2
    assert inventory.hosts[0].connected is False
    assert inventory.datastores[0].capacity_gb == 1024


def test_vcenter_rest_marks_templates():
    inventory = parse_vcenter_rest(
        {"value": [{"vm": "vm-9", "name": "gold", "power_state": "POWERED_OFF", "type": "TEMPLATE"}]},
        {"value": []},
        {"value": []},
        "vc-prod",
    )
    assert inventory.vms[0].is_template is True


def test_nsxt_flags_only_known_empty_segments():
    inventory = parse_nsxt(
        [{"id": "seg-old", "display_name": "old", "admin_state": "UP"}, {"id": "seg-web", "display_name": "web", "admin_state": "UP"}],
        [{"id": "t1", "display_name": "t1", "status": "unused", "active_sessions": 0}],
        [{"id": "lb", "display_name": "lb", "enabled": True, "active_sessions": 0}],
        {"seg-old": 0, "seg-web": 4},
        "nsx",
    )
    findings = analyze(inventory, Rates())
    names = {item.resource_name for item in findings}
    assert names == {"old", "t1", "lb"}


def test_nsxv_virtual_wire_shape():
    inventory = parse_nsxv(
        {"data": [{"objectId": "virtualwire-1", "name": "vxw", "vmCount": 0}]},
        {"edgePage": {"data": [{"objectId": "edge-1", "name": "edge", "edgeType": "gatewayServices", "state": "unused", "activeSessions": 0}]}},
        "nsx",
    )
    assert inventory.segments[0].port_count == 0
    assert inventory.gateways[0].gateway_type == "edge"


def test_aria_stats_map_onto_vm_names():
    patches = parse_aria_stats(
        [{"identifier": "res-1", "resourceKey": {"name": "batch-night"}}],
        {"values": [{"resourceId": "res-1", "stat-list": {"stat": [
            {"statKey": {"key": "cpu|usage_average"}, "data": [1.5]},
            {"statKey": {"key": "mem|usage_average"}, "data": [9.0]},
        ]}}]},
    )
    inventory = Inventory(vms=[
        VmRecord(endpoint_id="vc", id="vm", name="batch-night", power_state="poweredOn", vcpu=8, memory_gb=32, cpu_usage_pct=80, mem_usage_pct=80)
    ], metric_patches=patches)
    overlay_metrics(inventory)
    assert inventory.vms[0].cpu_usage_pct == 1.5
    assert inventory.vms[0].metrics_source == "aria"
    findings = analyze(inventory, Rates())
    assert findings[0].category == "idle_vm"


def test_vcf_cluster_utilization():
    inventory = parse_vcf(
        {"elements": [{"id": "dom-1", "name": "wld-dmz"}]},
        {"elements": [{"id": "cl-1", "name": "cl-dmz", "domainId": "dom-1", "hostCount": 4, "utilization": {"cpuUsedPct": 12, "memoryUsedPct": 18}}]},
        "vcf",
    )
    assert inventory.vcf_clusters[0].domain == "wld-dmz"
    assert inventory.vcf_clusters[0].cpu_usage_pct == 12


def test_unmatched_aria_names_are_warnings_not_waste():
    inventory = Inventory(
        vms=[VmRecord(endpoint_id="vc", id="vm", name="kept", power_state="poweredOn")],
        metric_patches=[MetricPatch(name="missing", cpu_usage_pct=1, mem_usage_pct=1)],
    )
    overlay_metrics(inventory)
    assert inventory.warnings
    assert analyze(inventory, Rates()) == []
