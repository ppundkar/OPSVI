"""Deterministic estate used for the fast path and the local dashboard."""

from __future__ import annotations

from agent.models import (
    DatastoreRecord,
    HostRecord,
    Inventory,
    NsxGateway,
    NsxSegment,
    VcfCluster,
    VmRecord,
)

VC = "vc-prod"
NSX = "nsx-prod"
VCF = "vcf-prod"


def build_demo_inventory() -> Inventory:
    vms = [
        VmRecord(
            endpoint_id=VC, id="vm-legacy", name="legacy-app", power_state="poweredOff",
            vcpu=4, memory_gb=16, used_gb=180, provisioned_gb=200, powered_off_days=60,
            metrics_source="vcenter",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-sql", name="retired-sql", power_state="poweredOff",
            vcpu=8, memory_gb=32, used_gb=400, provisioned_gb=500, powered_off_days=20,
            snapshot_count=1, snapshot_gb=40, oldest_snapshot_days=20, metrics_source="vcenter",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-patch", name="patch-window", power_state="poweredOff",
            vcpu=2, memory_gb=4, used_gb=40, powered_off_days=3, metrics_source="vcenter",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-template", name="win-template", power_state="poweredOff",
            vcpu=2, memory_gb=4, used_gb=60, powered_off_days=100, is_template=True,
        ),
        VmRecord(
            endpoint_id=VC, id="vm-worker", name="old-worker", power_state="suspended",
            vcpu=4, memory_gb=8, used_gb=80, powered_off_days=30, metrics_source="vcenter",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-batch", name="batch-night", power_state="poweredOn",
            vcpu=8, memory_gb=32, used_gb=120, cpu_usage_pct=1.2, mem_usage_pct=8,
            metrics_source="aria", cluster="prod",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-sandbox", name="dev-sandbox", power_state="poweredOn",
            vcpu=4, memory_gb=8, used_gb=80, cpu_usage_pct=3, mem_usage_pct=12,
            metrics_source="aria", cluster="lab",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-web", name="web-frontend", power_state="poweredOn",
            vcpu=8, memory_gb=16, used_gb=60, cpu_usage_pct=11, mem_usage_pct=55,
            metrics_source="aria", cluster="prod",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-api", name="api-gateway", power_state="poweredOn",
            vcpu=8, memory_gb=32, used_gb=40, cpu_usage_pct=18, mem_usage_pct=22,
            metrics_source="aria", cluster="prod",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-db", name="db-prod", power_state="poweredOn",
            vcpu=4, memory_gb=64, used_gb=800, cpu_usage_pct=62, mem_usage_pct=18,
            metrics_source="aria", cluster="prod",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-files", name="fileserver", power_state="poweredOn",
            vcpu=4, memory_gb=16, used_gb=2000, cpu_usage_pct=25, mem_usage_pct=40,
            snapshot_count=2, snapshot_gb=240, oldest_snapshot_days=14,
            metrics_source="aria", cluster="prod",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-vdi", name="vdi-builder", power_state="poweredOn",
            vcpu=2, memory_gb=8, used_gb=50, cpu_usage_pct=8, mem_usage_pct=30,
            metrics_source="aria", cluster="vdi",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-mon", name="monitoring", power_state="poweredOn",
            vcpu=4, memory_gb=8, used_gb=40, cpu_usage_pct=6, mem_usage_pct=45,
            metrics_source="aria", cluster="mgmt",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-erp", name="healthy-erp", power_state="poweredOn",
            vcpu=4, memory_gb=16, used_gb=200, cpu_usage_pct=55, mem_usage_pct=60,
            metrics_source="aria", cluster="prod",
        ),
        VmRecord(
            endpoint_id=VC, id="vm-web2", name="healthy-web", power_state="poweredOn",
            vcpu=2, memory_gb=4, used_gb=30, cpu_usage_pct=40, mem_usage_pct=50,
            snapshot_count=1, snapshot_gb=5, oldest_snapshot_days=2,
            metrics_source="aria", cluster="prod",
        ),
    ]
    hosts = [
        HostRecord(
            endpoint_id=VC, id="host-1", name="esx-01", cpu_usage_pct=70, mem_usage_pct=75,
            vm_count=20, cluster="prod", cores=48, memory_gb=512, connected=True,
        ),
        HostRecord(
            endpoint_id=VC, id="host-2", name="esx-02", cpu_usage_pct=8, mem_usage_pct=12,
            vm_count=1, cluster="lab-edge", cores=32, memory_gb=256, connected=True,
        ),
        HostRecord(
            endpoint_id=VC, id="host-3", name="esx-03", cpu_usage_pct=40, mem_usage_pct=50,
            vm_count=10, cluster="prod", cores=48, memory_gb=512, connected=True,
        ),
        HostRecord(
            endpoint_id=VC, id="host-4", name="esx-04", cpu_usage_pct=2, mem_usage_pct=3,
            vm_count=0, cluster="prod", cores=32, memory_gb=256, maintenance=True,
        ),
        HostRecord(
            endpoint_id=VC, id="host-5", name="esx-05", cpu_usage_pct=1, mem_usage_pct=1,
            vm_count=0, cluster="prod", cores=32, memory_gb=256, connected=False,
        ),
    ]
    datastores = [
        DatastoreRecord(endpoint_id=VC, id="ds-1", name="ds-prod", capacity_gb=8000, free_gb=2500, orphaned_gb=0),
        DatastoreRecord(endpoint_id=VC, id="ds-2", name="ds-iso", capacity_gb=4000, free_gb=1800, orphaned_gb=650),
        DatastoreRecord(endpoint_id=VC, id="ds-3", name="ds-archive", capacity_gb=2000, free_gb=900, orphaned_gb=40),
    ]
    segments = [
        NsxSegment(endpoint_id=NSX, id="seg-web", name="seg-web", port_count=24),
        NsxSegment(endpoint_id=NSX, id="seg-db", name="seg-db", port_count=6),
        NsxSegment(endpoint_id=NSX, id="seg-old", name="seg-old", port_count=0),
        NsxSegment(endpoint_id=NSX, id="seg-lab", name="seg-lab", port_count=0),
        NsxSegment(endpoint_id=NSX, id="seg-down", name="seg-down", port_count=0, admin_up=False),
    ]
    gateways = [
        NsxGateway(
            endpoint_id=NSX, id="t1-app", name="t1-app", gateway_type="tier1",
            active_sessions=100, status="up",
        ),
        NsxGateway(
            endpoint_id=NSX, id="lb-legacy", name="lb-legacy", gateway_type="lb",
            active_sessions=0, status="up",
        ),
        NsxGateway(
            endpoint_id=NSX, id="lb-prod", name="lb-prod", gateway_type="lb",
            active_sessions=40, status="up",
        ),
        NsxGateway(
            endpoint_id=NSX, id="t1-unused", name="t1-unused", gateway_type="tier1",
            active_sessions=0, status="unused",
        ),
    ]
    clusters = [
        VcfCluster(
            endpoint_id=VCF, domain="wld-prod", name="cl-prod", hosts=6,
            cpu_usage_pct=48, mem_usage_pct=55, cores=288,
        ),
        VcfCluster(
            endpoint_id=VCF, domain="wld-dmz", name="cl-dmz", hosts=4,
            cpu_usage_pct=12, mem_usage_pct=18, cores=128,
        ),
    ]
    return Inventory(
        vms=vms,
        hosts=hosts,
        datastores=datastores,
        segments=segments,
        gateways=gateways,
        vcf_clusters=clusters,
    )
