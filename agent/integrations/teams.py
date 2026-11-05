"""Microsoft Teams incoming webhook."""

from __future__ import annotations

import httpx

from agent.config import Settings
from agent.models import NotifyResult, OptimizeResponse


def build_card(result: OptimizeResponse) -> dict:
    summary = result.summary
    facts = [
        {"name": "Committed monthly", "value": f"{summary.conservative_monthly_usd:,.0f} {summary.currency}"},
        {"name": "Annual", "value": f"{summary.annual_conservative_usd:,.0f} {summary.currency}"},
        {"name": "Upside monthly", "value": f"{summary.upside_monthly_usd:,.0f} {summary.currency}"},
        {"name": "Findings", "value": str(summary.finding_count)},
        {"name": "Response", "value": f"{result.duration_ms:.0f} ms"},
    ]
    lines = [result.ai.summary, ""]
    for finding in result.findings[:5]:
        lines.append(f"- {finding.resource_name}: {finding.monthly_savings_usd:,.0f} {summary.currency}/month. {finding.recommendation}")
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"VMware savings {summary.conservative_monthly_usd:,.0f} {summary.currency}/month",
        "themeColor": "0F6E56",
        "title": "VMware cost optimization",
        "sections": [{"facts": facts, "text": "\n".join(lines)}],
    }


async def notify_teams(result: OptimizeResponse, settings: Settings) -> NotifyResult:
    if not settings.teams_webhook_url:
        return NotifyResult(status="skipped", detail="Set VCO_TEAMS_WEBHOOK_URL to send a Teams card. The report was still created.")
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            response = await client.post(settings.teams_webhook_url, json=build_card(result))
        if response.status_code >= 300:
            return NotifyResult(status="failed", detail=f"Teams webhook returned {response.status_code}")
        return NotifyResult(status="sent", detail="Teams accepted the card")
    except Exception as exc:
        return NotifyResult(status="failed", detail=f"Teams notification failed: {exc.__class__.__name__}")
