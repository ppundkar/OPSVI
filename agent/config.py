"""Runtime settings and contract rates."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
DEFAULT_RATES = ROOT / "config" / "rates.yaml"
DEFAULT_ENDPOINTS = ROOT / "config" / "endpoints.yaml"
DEFAULT_REGISTRY = DATA / "endpoints.json"


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    powered_off_days: int = 14
    idle_cpu_pct: float = 5
    idle_mem_pct: float = 20
    oversize_cpu_pct: float = 20
    oversize_mem_pct: float = 30
    min_vcpu_to_resize: int = 4
    min_mem_gb: float = 8
    min_target_mem_gb: float = 2
    mem_headroom: float = 0.70
    snapshot_days: int = 7
    host_idle_cpu_pct: float = 15
    host_idle_mem_pct: float = 20
    host_low_vm_count: int = 2
    vcf_idle_cpu_pct: float = 30
    vcf_idle_mem_pct: float = 35
    vcf_min_hosts: int = 4


class Rates(BaseModel):
    """Monthly unit prices. Amounts are USD unless currency is changed."""

    model_config = ConfigDict(extra="forbid")

    currency: str = "USD"
    cpu_vcpu_month: float = 18.0
    memory_gb_month: float = 3.5
    storage_gb_month: float = 0.06
    snapshot_gb_month: float = 0.09
    nsx_segment_month: float = 12.0
    nsx_lb_month: float = 75.0
    nsx_gateway_month: float = 40.0
    host_month: float = 450.0
    idle_reclaim_factor: float = 0.85
    min_monthly_savings: float = 1.0
    thresholds: Thresholds = Field(default_factory=Thresholds)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VCO_",
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8080
    api_key: str = ""
    cache_ttl_seconds: int = 120
    collector_timeout_seconds: float = 20
    powershell_timeout_seconds: float = 90
    max_concurrency: int = 8
    aria_stat_limit: int = 150
    nsx_port_lookup_limit: int = 150
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: float = 4
    teams_webhook_url: str = ""
    powerbi_token: str = ""
    powerbi_group_id: str = ""
    powerbi_dataset_id: str = ""
    rates_path: str = ""
    endpoints_path: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_rates(path: Path | None = None) -> Rates:
    settings = get_settings()
    chosen = path or (Path(settings.rates_path) if settings.rates_path else DEFAULT_RATES)
    if not chosen.exists():
        return Rates()
    data = load_yaml(chosen.read_text(encoding="utf-8")) or {}
    return Rates.model_validate(data)
