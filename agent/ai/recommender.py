"""Recommendations. A short model call is optional; the rules path always returns."""

from __future__ import annotations

import json
import re

import httpx

from agent.config import Settings
from agent.models import AiAction, AiPlan, Finding, SavingsSummary

_FENCE = re.compile(r"^```(?:json)?|```$", re.IGNORECASE | re.MULTILINE)
_RISK = {"low", "medium", "high"}


def rules_plan(findings: list[Finding], summary: SavingsSummary) -> AiPlan:
    actions: list[AiAction] = []
    ordered = sorted(findings, key=lambda item: (item.overlaps_compute, -item.monthly_savings_usd))
    for index, finding in enumerate(ordered[:6], start=1):
        risk = "low" if finding.category in {"stale_snapshot", "unused_segment", "orphaned_disk"} else "medium"
        if finding.overlaps_compute:
            risk = "high"
        actions.append(
            AiAction(
                priority=index,
                title=finding.title,
                monthly_savings_usd=finding.monthly_savings_usd,
                risk=risk,
                steps=[finding.recommendation],
            )
        )
    if summary.finding_count == 0:
        text = "No waste rules fired for this estate. Inventory was still collected."
    else:
        text = (
            f"Commit to {summary.conservative_monthly_usd:,.0f} {summary.currency} per month "
            f"({summary.annual_conservative_usd:,.0f} annual) across {summary.finding_count} findings. "
            f"Another {summary.upside_monthly_usd:,.0f} {summary.currency} per month is consolidation upside "
            "and overlaps compute already counted on virtual machines. "
            "Start with snapshots, orphaned disks, and powered-off VMs, then rightsizing, then host removal."
        )
    return AiPlan(source="rules", summary=text, actions=actions, model_name=None)


async def recommend(
    findings: list[Finding],
    summary: SavingsSummary,
    settings: Settings,
    include_ai: bool,
) -> tuple[AiPlan, str | None]:
    fallback = rules_plan(findings, summary)
    if not include_ai or not settings.ai_api_key:
        return fallback, None
    try:
        plan = await _complete(findings[:15], summary, settings)
        return plan, None
    except Exception as exc:
        return fallback, f"AI recommendations fell back to rules: {exc.__class__.__name__}"


async def _complete(findings: list[Finding], summary: SavingsSummary, settings: Settings) -> AiPlan:
    payload = {
        "summary": summary.model_dump(),
        "findings": [item.model_dump() for item in findings],
    }
    prompt = (
        "You are a VMware FinOps architect. Use only the findings JSON. "
        "Do not invent resources. Do not tell the operator to delete anything before a backup check. "
        "Return JSON with keys summary (string) and actions (list of "
        "{priority, title, monthly_savings_usd, risk, steps}). "
        "risk is low, medium, or high. Keep at most 5 actions, highest savings first."
    )
    url = settings.ai_base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.ai_api_key}"},
            json={
                "model": settings.ai_model,
                "temperature": 0.2,
                "max_tokens": 600,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(payload)},
                ],
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    return _parse_plan(content, settings.ai_model, summary)


def _parse_plan(content: str, model_name: str, summary: SavingsSummary) -> AiPlan:
    text = _FENCE.sub("", content).strip()
    data = json.loads(text)
    actions = []
    for index, row in enumerate(data.get("actions") or [], start=1):
        risk = str(row.get("risk") or "medium").lower()
        if risk not in _RISK:
            risk = "medium"
        steps = row.get("steps") or []
        if isinstance(steps, str):
            steps = [steps]
        actions.append(
            AiAction(
                priority=int(row.get("priority") or index),
                title=str(row.get("title") or "Review finding"),
                monthly_savings_usd=float(row.get("monthly_savings_usd") or 0),
                risk=risk,  # type: ignore[arg-type]
                steps=[str(step) for step in steps][:4],
            )
        )
    if not actions:
        raise ValueError("model returned no actions")
    summary_text = str(data.get("summary") or "").strip() or rules_plan([], summary).summary
    return AiPlan(source="model", summary=summary_text, actions=actions[:5], model_name=model_name)
