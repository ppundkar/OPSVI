"""Shared inventory, findings, and API models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

Kind = Literal["vcenter", "nsx", "nsxt", "aria", "vcf"]
PowerState = Literal["poweredOn", "poweredOff", "suspended", "unknown"]


def _normalize_power(value: Any) -> str:
    text = str(value or "").replace("_", "").replace("-", "").lower()
    if text in {"poweredoff", "off"}:
        return "poweredOff"
    if text in {"poweredon", "on"}:
        return "poweredOn"
    if "suspend" in text:
        return "suspended"
    if not text:
        return "unknown"
    return "unknown"


class EndpointInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    kind: Kind
    url: str
    username: str = ""
    password: SecretStr = SecretStr("")
    verify_ssl: bool = True
    use_powershell: bool = False
    deep_stats: bool = False
    orphaned_disks: bool = False
    site: str = ""

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: str) -> str:
        return str(value).strip().lower()

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        text = value.strip().rstrip("/")
        if not text.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return text


class VmRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint_id: str
    id: str
    name: str
    power_state: PowerState = "unknown"
    vcpu: int = 0
    memory_gb: float = 0
    used_gb: float = 0
    provisioned_gb: float = 0
    cpu_usage_pct: float | None = None
    mem_usage_pct: float | None = None
    powered_off_days: int | None = None
    snapshot_count: int = 0
    snapshot_gb: float = 0
    oldest_snapshot_days: int = 0
    is_template: bool = False
    tools_ok: bool = True
    cluster: str = ""
    host: str = ""
    metrics_source: str = ""

    @field_validator("power_state", mode="before")
    @classmethod
    def _power(cls, value: Any) -> str:
        return _normalize_power(value)


class HostRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint_id: str
    id: str
    name: str
    cpu_usage_pct: float | None = None
    mem_usage_pct: float | None = None
    vm_count: int = 0
    cluster: str = ""
    cores: int = 0
    memory_gb: float = 0
    maintenance: bool = False
    connected: bool = True


class DatastoreRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint_id: str
    id: str
    name: str
    capacity_gb: float = 0
    free_gb: float = 0
    orphaned_gb: float = 0


class NsxSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint_id: str
    id: str
    name: str
    port_count: int | None = None
    admin_up: bool = True


class NsxGateway(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint_id: str
    id: str
    name: str
    gateway_type: str
    active_sessions: int | None = None
    status: str = ""
    enabled: bool = True


class VcfCluster(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint_id: str
    domain: str
    name: str
    hosts: int = 0
    cpu_usage_pct: float | None = None
    mem_usage_pct: float | None = None
    cores: int = 0


class MetricPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    cpu_usage_pct: float | None = None
    mem_usage_pct: float | None = None
    resource_id: str = ""


class Inventory(BaseModel):
    vms: list[VmRecord] = Field(default_factory=list)
    hosts: list[HostRecord] = Field(default_factory=list)
    datastores: list[DatastoreRecord] = Field(default_factory=list)
    segments: list[NsxSegment] = Field(default_factory=list)
    gateways: list[NsxGateway] = Field(default_factory=list)
    vcf_clusters: list[VcfCluster] = Field(default_factory=list)
    metric_patches: list[MetricPatch] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def extend(self, other: "Inventory") -> None:
        self.vms.extend(other.vms)
        self.hosts.extend(other.hosts)
        self.datastores.extend(other.datastores)
        self.segments.extend(other.segments)
        self.gateways.extend(other.gateways)
        self.vcf_clusters.extend(other.vcf_clusters)
        self.metric_patches.extend(other.metric_patches)
        self.warnings.extend(other.warnings)


class Finding(BaseModel):
    id: str
    category: str
    severity: Literal["high", "medium", "low"]
    confidence: float
    endpoint_id: str
    resource_type: str
    resource_id: str
    resource_name: str
    title: str
    detail: str
    recommendation: str
    monthly_savings_usd: float
    overlaps_compute: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)


class SavingsSummary(BaseModel):
    currency: str
    finding_count: int
    gross_monthly_usd: float
    conservative_monthly_usd: float
    upside_monthly_usd: float
    annual_conservative_usd: float
    three_year_conservative_usd: float
    by_category: dict[str, float]


class InventoryCounts(BaseModel):
    vms: int = 0
    hosts: int = 0
    datastores: int = 0
    segments: int = 0
    gateways: int = 0
    vcf_clusters: int = 0
    metric_patches: int = 0


class EndpointStatus(BaseModel):
    id: str
    kind: Kind
    url: str
    ok: bool
    latency_ms: float
    resource_count: int = 0
    error: str | None = None
    detail: str = ""


class AiAction(BaseModel):
    priority: int
    title: str
    monthly_savings_usd: float
    risk: Literal["low", "medium", "high"]
    steps: list[str]


class AiPlan(BaseModel):
    source: Literal["rules", "model"]
    summary: str
    actions: list[AiAction]
    model_name: str | None = None


class NotifyResult(BaseModel):
    status: Literal["sent", "skipped", "failed"]
    detail: str


class PowerBiResult(BaseModel):
    status: Literal["sent", "skipped", "failed"]
    detail: str
    rows_pushed: int = 0
    files: list[str] = Field(default_factory=list)
    dataset_id: str = ""


class ExportPaths(BaseModel):
    html_path: str
    csv_path: str
    powerbi_findings_csv: str
    powerbi_summary_csv: str
    html_url: str
    csv_url: str


class OptimizeResponse(BaseModel):
    analysis_id: str
    collected_at: str
    mode: Literal["demo", "live", "submitted"]
    cache_hit: bool
    partial: bool
    duration_ms: float
    collect_ms: float
    analyze_ms: float
    ai_ms: float
    export_ms: float
    endpoints: list[EndpointStatus]
    counts: InventoryCounts
    summary: SavingsSummary
    findings: list[Finding]
    ai: AiPlan
    exports: ExportPaths
    warnings: list[str] = Field(default_factory=list)
    teams: NotifyResult | None = None
    powerbi: PowerBiResult | None = None
    inventory: Inventory | None = None


class OptimizeRequest(BaseModel):
    demo: bool = False
    use_config: bool = False
    endpoints: list[EndpointInput] = Field(default_factory=list)
    inventory: Inventory | None = None
    include_ai: bool = True
    include_inventory: bool = False
    notify_teams: bool = False
    push_powerbi: bool = False
    refresh: bool = False


class SessionTestRequest(BaseModel):
    use_config: bool = False
    endpoints: list[EndpointInput] = Field(default_factory=list)


class SessionTestResponse(BaseModel):
    duration_ms: float
    endpoints: list[EndpointStatus]


class EndpointWrite(BaseModel):
    """Registration form. A blank password on update keeps the stored secret."""

    model_config = ConfigDict(extra="ignore")

    id: str
    kind: Kind
    url: str
    username: str = ""
    password: str = ""
    verify_ssl: bool = True
    use_powershell: bool = False
    deep_stats: bool = False
    orphaned_disks: bool = False
    site: str = ""

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: str) -> str:
        return str(value).strip().lower()

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        text = value.strip()
        if not text.replace("-", "").replace("_", "").replace(".", "").isalnum():
            raise ValueError("id may contain only letters, numbers, dots, hyphens, and underscores")
        if len(text) > 64:
            raise ValueError("id must be 64 characters or fewer")
        return text

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        text = value.strip().rstrip("/")
        if not text.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return text


class EndpointPublic(BaseModel):
    id: str
    kind: Kind
    url: str
    username: str
    password_set: bool
    secret_source: Literal["stored", "env", "missing"]
    verify_ssl: bool
    use_powershell: bool
    deep_stats: bool
    orphaned_disks: bool
    site: str = ""
