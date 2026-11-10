"""Waste rules and savings totals."""

from agent.config import Rates, load_rates
from agent.demo.sample import build_demo_inventory
from agent.merge import counts_for, exclude_templates
from agent.models import VmRecord
from agent.waste.engine import analyze, summarize


def names(findings, category=None):
    rows = findings if category is None else [item for item in findings if item.category == category]
    return {item.resource_name for item in rows}


def test_rates_file_matches_defaults():
    assert load_rates().model_dump() == Rates().model_dump()


def test_demo_estate_covers_each_waste_class():
    inventory = build_demo_inventory()
    findings = analyze(inventory, Rates())
    found = {item.category for item in findings}
    assert {
        "zombie_vm",
        "idle_vm",
        "oversized_cpu",
        "oversized_memory",
        "stale_snapshot",
        "zombie_vmdk",
        "unused_segment",
        "idle_load_balancer",
        "idle_gateway",
        "underutilized_host",
        "vcf_idle_capacity",
    } <= found
    assert "legacy-app" in names(findings, "zombie_vm")
    assert "old-worker" in names(findings, "zombie_vm")
    assert "dev-sandbox" in names(findings, "idle_vm")
    assert "patch-window" not in names(findings)
    assert "win-template" not in names(findings)
    template_inventory = build_demo_inventory()
    assert any(vm.is_template and vm.snapshot_gb > 0 for vm in template_inventory.vms)
    skipped = exclude_templates(template_inventory)
    assert skipped == 1
    assert "win-template" not in {vm.name for vm in template_inventory.vms}
    assert "healthy-erp" not in names(findings)
    assert "healthy-web" not in names(findings)
    assert "esx-04" not in names(findings)
    assert "esx-05" not in names(findings)
    assert "seg-down" not in names(findings)
    assert "lb-prod" not in names(findings)
    assert "cl-prod" not in names(findings)
    assert "retired-sql" not in names(findings, "stale_snapshot")
    assert "fileserver" in names(findings, "stale_snapshot")
    summary = summarize(findings, Rates(), counts_for(inventory))
    assert summary.conservative_monthly_usd < summary.gross_monthly_usd
    assert summary.upside_monthly_usd == round(summary.gross_monthly_usd - summary.conservative_monthly_usd, 2)
    assert summary.annual_conservative_usd == round(summary.conservative_monthly_usd * 12, 2)
    assert all(item.overlaps_compute for item in findings if item.category in {"underutilized_host", "vcf_idle_capacity"})
    assert not any(item.overlaps_compute for item in findings if item.category == "zombie_vm")


def test_powered_off_savings_include_compute_and_storage():
    rates = Rates()
    vm = VmRecord(
        endpoint_id="vc",
        id="vm-1",
        name="old",
        power_state="POWERED_OFF",
        vcpu=4,
        memory_gb=16,
        used_gb=180,
        powered_off_days=60,
        cpu_usage_pct=1,
        mem_usage_pct=1,
    )
    findings = analyze(
        build_demo_inventory().model_copy(update={"vms": [vm], "hosts": [], "datastores": [], "segments": [], "gateways": [], "vcf_clusters": []}),
        rates,
    )
    assert len(findings) == 1
    expected = round(4 * rates.cpu_vcpu_month + 16 * rates.memory_gb_month + 180 * rates.storage_gb_month, 2)
    assert findings[0].monthly_savings_usd == expected
    assert findings[0].category == "zombie_vm"


def test_idle_holdback_and_rightsizing_skip_when_idle():
    rates = Rates()
    idle = VmRecord(
        endpoint_id="vc",
        id="vm-idle",
        name="idle",
        power_state="poweredOn",
        vcpu=8,
        memory_gb=32,
        cpu_usage_pct=1,
        mem_usage_pct=8,
        metrics_source="aria",
    )
    findings = analyze(
        build_demo_inventory().model_copy(update={"vms": [idle], "hosts": [], "datastores": [], "segments": [], "gateways": [], "vcf_clusters": []}),
        rates,
    )
    assert [item.category for item in findings] == ["idle_vm"]
    expected = round((8 * rates.cpu_vcpu_month + 32 * rates.memory_gb_month) * rates.idle_reclaim_factor, 2)
    assert findings[0].monthly_savings_usd == expected
    assert findings[0].evidence["metrics_source"] == "aria"


def test_missing_utilization_does_not_invent_waste():
    vm = VmRecord(endpoint_id="vc", id="vm-2", name="unknown", power_state="poweredOn", vcpu=16, memory_gb=64)
    findings = analyze(
        build_demo_inventory().model_copy(update={"vms": [vm], "hosts": [], "datastores": [], "segments": [], "gateways": [], "vcf_clusters": []}),
        Rates(),
    )
    assert findings == []
