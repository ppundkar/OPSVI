"""HTML and CSV exports."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from agent import PRODUCT_NAME, PRODUCT_SHORT
from agent.config import OUT
from agent.models import OptimizeResponse

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_ENV = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "j2"]),
)
_CSS = (TEMPLATE_DIR / "theme.css").read_text(encoding="utf-8")


def _brand() -> dict[str, str]:
    return {"product_name": PRODUCT_NAME, "product_short": PRODUCT_SHORT}


def render_dashboard() -> str:
    return _ENV.get_template("dashboard.html.j2").render(css=_CSS, **_brand())


def render_admin() -> str:
    return _ENV.get_template("admin.html.j2").render(css=_CSS, **_brand())


def render_report(result: OptimizeResponse) -> str:
    return _ENV.get_template("report.html.j2").render(css=_CSS, result=result, **_brand())


def findings_csv(result: OptimizeResponse) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "AnalysisId",
            "CollectedAt",
            "Category",
            "Severity",
            "Confidence",
            "EndpointId",
            "ResourceType",
            "ResourceName",
            "ResourceId",
            "MonthlySavings",
            "OverlapsCompute",
            "Title",
            "Recommendation",
            "Detail",
        ]
    )
    for item in result.findings:
        writer.writerow(
            [
                result.analysis_id,
                result.collected_at,
                item.category,
                item.severity,
                item.confidence,
                item.endpoint_id,
                item.resource_type,
                item.resource_name,
                item.resource_id,
                item.monthly_savings_usd,
                item.overlaps_compute,
                item.title,
                item.recommendation,
                item.detail,
            ]
        )
    return buffer.getvalue()


def summary_csv(result: OptimizeResponse) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    summary = result.summary
    writer.writerow(
        [
            "AnalysisId",
            "CollectedAt",
            "Currency",
            "ConservativeMonthly",
            "GrossMonthly",
            "UpsideMonthly",
            "AnnualConservative",
            "ThreeYearConservative",
            "FindingCount",
            "VmCount",
            "CollectMs",
            "TotalMs",
            "Partial",
            "AiSource",
            "Mode",
        ]
    )
    writer.writerow(
        [
            result.analysis_id,
            result.collected_at,
            summary.currency,
            summary.conservative_monthly_usd,
            summary.gross_monthly_usd,
            summary.upside_monthly_usd,
            summary.annual_conservative_usd,
            summary.three_year_conservative_usd,
            summary.finding_count,
            result.counts.vms,
            result.collect_ms,
            result.duration_ms,
            result.partial,
            result.ai.source,
            result.mode,
        ]
    )
    return buffer.getvalue()


def write_exports(result: OptimizeResponse) -> tuple[Path, Path, Path, Path]:
    report_dir = OUT / "reports"
    powerbi_dir = OUT / "powerbi"
    report_dir.mkdir(parents=True, exist_ok=True)
    powerbi_dir.mkdir(parents=True, exist_ok=True)
    html = render_report(result)
    findings = findings_csv(result)
    summary = summary_csv(result)
    html_path = report_dir / f"{result.analysis_id}.html"
    csv_path = report_dir / f"{result.analysis_id}.csv"
    html_path.write_text(html, encoding="utf-8")
    csv_path.write_text("\ufeff" + findings, encoding="utf-8")
    (report_dir / "latest.html").write_text(html, encoding="utf-8")
    (report_dir / "latest.csv").write_text("\ufeff" + findings, encoding="utf-8")
    findings_path = powerbi_dir / "findings.csv"
    summary_path = powerbi_dir / "summary.csv"
    findings_path.write_text("\ufeff" + findings, encoding="utf-8")
    summary_path.write_text("\ufeff" + summary, encoding="utf-8")
    return html_path, csv_path, findings_path, summary_path
