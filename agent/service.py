"""Analysis pipeline: collect, score, recommend, export."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone

from agent.ai.recommender import recommend
from agent.config import OUT, Rates, Settings
from agent.demo.sample import build_demo_inventory
from agent.endpoints import load_endpoints
from agent.merge import counts_for, overlay_metrics
from agent.models import (
    EndpointStatus,
    ExportPaths,
    Inventory,
    OptimizeRequest,
    OptimizeResponse,
)
from agent.orchestrator import collect_all
from agent.reports.export import findings_csv, render_report, write_exports
from agent.waste.engine import analyze, summarize

MAX_VMS = 20000


class TtlCache:
    def __init__(self) -> None:
        self._items: OrderedDict[str, tuple[float, OptimizeResponse]] = OrderedDict()

    def get(self, key: str, ttl: int) -> OptimizeResponse | None:
        found = self._items.get(key)
        if not found:
            return None
        stored_at, value = found
        if time.time() - stored_at > ttl:
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return value

    def put(self, key: str, value: OptimizeResponse) -> None:
        self._items[key] = (time.time(), value)
        self._items.move_to_end(key)
        while len(self._items) > 32:
            self._items.popitem(last=False)


class ReportStore:
    def __init__(self) -> None:
        self.html: dict[str, str] = {}
        self.csv: dict[str, str] = {}
        self.latest: str | None = None

    def put(self, analysis_id: str, html: str, csv_text: str) -> None:
        self.html[analysis_id] = html
        self.csv[analysis_id] = csv_text
        self.latest = analysis_id
        if len(self.html) > 20:
            oldest = next(iter(self.html))
            self.html.pop(oldest, None)
            self.csv.pop(oldest, None)


def cache_key(request: OptimizeRequest, rates: Rates, config_signature: str) -> str:
    payload = {
        "demo": request.demo,
        "use_config": request.use_config,
        "include_ai": request.include_ai,
        "config": config_signature if request.use_config else "",
        "endpoints": [
            (item.id, item.kind, item.url, item.use_powershell, item.deep_stats, item.orphaned_disks)
            for item in request.endpoints
        ],
        "inventory": request.inventory.model_dump() if request.inventory else None,
        "rates": rates.model_dump(),
    }
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_request(request: OptimizeRequest) -> None:
    sources = sum(
        [
            request.demo,
            request.use_config,
            bool(request.endpoints),
            request.inventory is not None,
        ]
    )
    if sources != 1:
        raise ValueError("Choose exactly one source: demo, use_config, endpoints, or inventory")


async def run_analysis(
    request: OptimizeRequest,
    settings: Settings,
    rates: Rates,
    cache: TtlCache,
) -> tuple[OptimizeResponse, str, str]:
    validate_request(request)
    signature = _config_signature(settings) if request.use_config else ""
    key = cache_key(request, rates, signature)
    started = time.perf_counter()
    cached = None if request.refresh else cache.get(key, settings.cache_ttl_seconds)
    if cached is not None:
        result = cached.model_copy(deep=True)
        result.cache_hit = True
        result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        result.teams = None
        result.powerbi = None
        html, csv_text = _read_saved(result)
        return result, html, csv_text

    mode, inventory, statuses, collect_ms = await _collect(request, settings)
    if len(inventory.vms) > MAX_VMS:
        inventory.warnings.append(f"VM analysis capped at {MAX_VMS} records")
        inventory.vms = inventory.vms[:MAX_VMS]
    analyze_started = time.perf_counter()
    findings = analyze(inventory, rates)
    counts = counts_for(inventory)
    summary = summarize(findings, rates, counts)
    analyze_ms = (time.perf_counter() - analyze_started) * 1000
    ai_started = time.perf_counter()
    plan, ai_warning = await recommend(findings, summary, settings, request.include_ai)
    ai_ms = (time.perf_counter() - ai_started) * 1000
    warnings = list(inventory.warnings)
    if ai_warning:
        warnings.append(ai_warning)
    partial = any(not item.ok for item in statuses)
    analysis_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    export_started = time.perf_counter()
    result = OptimizeResponse(
        analysis_id=analysis_id,
        collected_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        mode=mode,
        cache_hit=False,
        partial=partial,
        duration_ms=0,
        collect_ms=round(collect_ms, 2),
        analyze_ms=round(analyze_ms, 2),
        ai_ms=round(ai_ms, 2),
        export_ms=0,
        endpoints=statuses,
        counts=counts,
        summary=summary,
        findings=findings,
        ai=plan,
        exports=ExportPaths(
            html_path="",
            csv_path="",
            powerbi_findings_csv="",
            powerbi_summary_csv="",
            html_url=f"/v1/reports/{analysis_id}.html",
            csv_url=f"/v1/reports/{analysis_id}.csv",
        ),
        warnings=warnings,
        inventory=inventory if request.include_inventory else None,
    )
    result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
    html_path, csv_path, findings_path, summary_path = write_exports(result)
    result.exports = ExportPaths(
        html_path=str(html_path),
        csv_path=str(csv_path),
        powerbi_findings_csv=str(findings_path),
        powerbi_summary_csv=str(summary_path),
        html_url=f"/v1/reports/{analysis_id}.html",
        csv_url=f"/v1/reports/{analysis_id}.csv",
    )
    result.export_ms = round((time.perf_counter() - export_started) * 1000, 2)
    result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
    html = render_report(result)
    csv_text = findings_csv(result)
    html_path.write_text(html, encoding="utf-8")
    (OUT / "reports" / "latest.html").write_text(html, encoding="utf-8")
    cache.put(key, result.model_copy(deep=True))
    return result, html, csv_text


async def _collect(
    request: OptimizeRequest,
    settings: Settings,
) -> tuple[str, Inventory, list[EndpointStatus], float]:
    started = time.perf_counter()
    if request.demo:
        inventory = build_demo_inventory()
        elapsed = (time.perf_counter() - started) * 1000
        return "demo", inventory, _demo_statuses(inventory, elapsed), elapsed
    if request.inventory is not None:
        inventory = request.inventory.model_copy(deep=True)
        overlay_metrics(inventory)
        elapsed = (time.perf_counter() - started) * 1000
        status = EndpointStatus(
            id="submitted",
            kind="vcenter",
            url="inventory://submitted",
            ok=True,
            latency_ms=round(elapsed, 2),
            resource_count=len(inventory.vms) + len(inventory.hosts) + len(inventory.segments),
            detail="Inventory submitted by the caller",
        )
        return "submitted", inventory, [status], elapsed
    endpoints = request.endpoints or load_endpoints(settings)
    if not endpoints:
        raise ValueError("No endpoints are registered. Open /admin and add vCenter, NSX, Aria, or VCF.")
    inventory, statuses = await collect_all(endpoints, settings)
    elapsed = (time.perf_counter() - started) * 1000
    return "live", inventory, statuses, elapsed


def _demo_statuses(inventory: Inventory, elapsed_ms: float) -> list[EndpointStatus]:
    latency = round(max(elapsed_ms, 0.01), 2)
    aria = sum(1 for vm in inventory.vms if vm.metrics_source == "aria")
    specs = [
        ("vc-prod", "vcenter", "https://vcenter.demo.local", len(inventory.vms) + len(inventory.hosts) + len(inventory.datastores)),
        ("nsx-prod", "nsxt", "https://nsx.demo.local", len(inventory.segments) + len(inventory.gateways)),
        ("aria-prod", "aria", "https://aria.demo.local", aria),
        ("vcf-prod", "vcf", "https://sddc.demo.local", len(inventory.vcf_clusters)),
    ]
    return [
        EndpointStatus(
            id=item_id,
            kind=kind,  # type: ignore[arg-type]
            url=url,
            ok=True,
            latency_ms=latency,
            resource_count=count,
            detail="In-memory demo estate",
        )
        for item_id, kind, url, count in specs
    ]


def _config_signature(settings: Settings) -> str:
    from agent.registry import active_store_file

    path = active_store_file(settings)
    if path is None:
        return "missing"
    stat = path.stat()
    return f"{path}:{stat.st_mtime_ns}:{stat.st_size}"


def _read_saved(result: OptimizeResponse) -> tuple[str, str]:
    html_path = OUT / "reports" / f"{result.analysis_id}.html"
    csv_path = OUT / "reports" / f"{result.analysis_id}.csv"
    html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    csv_text = csv_path.read_text(encoding="utf-8") if csv_path.exists() else ""
    if csv_text.startswith("\ufeff"):
        csv_text = csv_text.lstrip("\ufeff")
    return html, csv_text
