"""Power BI push dataset. CSV files are written even when push is not configured."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from agent.config import OUT, ROOT, Settings
from agent.models import OptimizeResponse, PowerBiResult

SCHEMA_PATH = ROOT / "dashboard" / "powerbi" / "dataset.json"
DATASET_ID_PATH = OUT / "powerbi" / "dataset_id.txt"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def finding_rows(result: OptimizeResponse) -> list[dict]:
    return [
        {
            "FindingId": item.id,
            "AnalysisId": result.analysis_id,
            "CollectedAt": result.collected_at,
            "Category": item.category,
            "Severity": item.severity,
            "Confidence": item.confidence,
            "EndpointId": item.endpoint_id,
            "ResourceType": item.resource_type,
            "ResourceName": item.resource_name,
            "MonthlySavings": item.monthly_savings_usd,
            "OverlapsCompute": item.overlaps_compute,
            "Title": item.title,
            "Recommendation": item.recommendation,
        }
        for item in result.findings
    ]


def summary_rows(result: OptimizeResponse) -> list[dict]:
    summary = result.summary
    return [
        {
            "AnalysisId": result.analysis_id,
            "CollectedAt": result.collected_at,
            "Currency": summary.currency,
            "ConservativeMonthly": summary.conservative_monthly_usd,
            "GrossMonthly": summary.gross_monthly_usd,
            "AnnualConservative": summary.annual_conservative_usd,
            "ThreeYearConservative": summary.three_year_conservative_usd,
            "FindingCount": summary.finding_count,
            "VmCount": result.counts.vms,
            "CollectMs": result.collect_ms,
            "TotalMs": result.duration_ms,
            "Partial": result.partial,
            "AiSource": result.ai.source,
        }
    ]


async def push_powerbi(result: OptimizeResponse, settings: Settings, files: list[str]) -> PowerBiResult:
    if not settings.powerbi_token or not settings.powerbi_group_id:
        return PowerBiResult(
            status="skipped",
            detail="CSV files are ready for import. Set VCO_POWERBI_TOKEN and VCO_POWERBI_GROUP_ID to push a dataset.",
            files=files,
        )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            dataset_id = await _dataset_id(client, settings)
            findings = finding_rows(result)
            summary = summary_rows(result)
            await _replace_rows(client, settings, dataset_id, "Findings", findings)
            await _replace_rows(client, settings, dataset_id, "Summary", summary)
        return PowerBiResult(
            status="sent",
            detail=f"Pushed {len(findings)} findings and 1 summary row",
            rows_pushed=len(findings) + 1,
            files=files,
            dataset_id=dataset_id,
        )
    except Exception as exc:
        return PowerBiResult(
            status="failed",
            detail=f"Power BI push failed: {exc.__class__.__name__}. CSV files are still available.",
            files=files,
        )


async def _dataset_id(client: httpx.AsyncClient, settings: Settings) -> str:
    if settings.powerbi_dataset_id:
        return settings.powerbi_dataset_id
    if DATASET_ID_PATH.exists():
        saved = DATASET_ID_PATH.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    response = await client.post(
        f"https://api.powerbi.com/v1.0/myorg/groups/{settings.powerbi_group_id}/datasets?defaultRetentionPolicy=basicFIFO",
        headers=_headers(settings),
        json=load_schema(),
    )
    response.raise_for_status()
    dataset_id = response.json()["id"]
    DATASET_ID_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATASET_ID_PATH.write_text(dataset_id, encoding="utf-8")
    return dataset_id


async def _replace_rows(
    client: httpx.AsyncClient,
    settings: Settings,
    dataset_id: str,
    table: str,
    rows: list[dict],
) -> None:
    base = (
        "https://api.powerbi.com/v1.0/myorg/groups/"
        f"{settings.powerbi_group_id}/datasets/{dataset_id}/tables/{table}/rows"
    )
    deleted = await client.delete(base, headers=_headers(settings))
    if deleted.status_code not in {200, 202, 204, 404}:
        deleted.raise_for_status()
    for start in range(0, len(rows), 10000):
        response = await client.post(base, headers=_headers(settings), json={"rows": rows[start : start + 10000]})
        response.raise_for_status()


def _headers(settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.powerbi_token}", "Content-Type": "application/json"}
