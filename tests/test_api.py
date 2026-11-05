"""API, exports, and recommendation fallback."""

from fastapi.testclient import TestClient

from agent.ai.recommender import rules_plan
from agent.config import Rates
from agent.demo.sample import build_demo_inventory
from agent.endpoints import normalize_endpoint
from agent.integrations.powerbi import finding_rows, load_schema, summary_rows
from agent.integrations.teams import build_card
from agent.main import app
from agent.merge import counts_for
from agent.models import EndpointInput
from agent.waste.engine import analyze, summarize


def _client():
    return TestClient(app)


def test_demo_optimize_is_fast_and_cached():
    with _client() as client:
        first = client.post("/v1/optimize", json={"demo": True, "include_ai": True})
        assert first.status_code == 200
        assert first.headers["x-response-time-ms"]
        body = first.json()
        assert body["cache_hit"] is False
        assert body["mode"] == "demo"
        assert body["summary"]["conservative_monthly_usd"] > 0
        assert body["ai"]["source"] == "rules"
        assert body["duration_ms"] < 1500
        assert "password" not in first.text.lower()
        second = client.post("/v1/optimize", json={"demo": True, "include_ai": True})
        assert second.json()["cache_hit"] is True
        assert second.json()["analysis_id"] == body["analysis_id"]
        report = client.get("/v1/reports/latest.html")
        assert report.status_code == 200
        assert "Committed monthly" in report.text
        csv_response = client.get("/v1/reports/latest.csv")
        assert csv_response.status_code == 200
        assert "ResourceName" in csv_response.text
        assert "legacy-app" in csv_response.text


def test_rejects_mixed_sources_and_missing_endpoints(tmp_path):
    with _client() as client:
        client.app.state.settings.endpoints_path = str(tmp_path / "missing.json")
        mixed = client.post("/v1/optimize", json={"demo": True, "use_config": True})
        assert mixed.status_code == 400
        missing = client.post("/v1/sessions/test", json={"use_config": True})
        assert missing.status_code == 400
        health = client.get("/health")
        assert health.json()["status"] == "ok"


def test_teams_and_powerbi_skip_without_credentials():
    with _client() as client:
        client.app.state.settings.teams_webhook_url = ""
        client.app.state.settings.powerbi_token = ""
        client.app.state.settings.powerbi_group_id = ""
        response = client.post("/v1/optimize", json={"demo": True, "notify_teams": True, "push_powerbi": True, "refresh": True})
        body = response.json()
        assert body["teams"]["status"] == "skipped"
        assert body["powerbi"]["status"] == "skipped"
        assert body["powerbi"]["files"]


def test_powerbi_rows_match_dataset_schema():
    inventory = build_demo_inventory()
    rates = Rates()
    findings = analyze(inventory, rates)
    from agent.models import AiPlan, EndpointStatus, ExportPaths, OptimizeResponse

    result = OptimizeResponse(
        analysis_id="test",
        collected_at="2026-11-05T00:00:00Z",
        mode="demo",
        cache_hit=False,
        partial=False,
        duration_ms=1,
        collect_ms=1,
        analyze_ms=1,
        ai_ms=1,
        export_ms=1,
        endpoints=[EndpointStatus(id="vc", kind="vcenter", url="https://vc.local", ok=True, latency_ms=1)],
        counts=counts_for(inventory),
        summary=summarize(findings, rates, counts_for(inventory)),
        findings=findings,
        ai=AiPlan(source="rules", summary="ok", actions=[]),
        exports=ExportPaths(
            html_path="",
            csv_path="",
            powerbi_findings_csv="",
            powerbi_summary_csv="",
            html_url="",
            csv_url="",
        ),
    )
    schema = load_schema()
    finding_columns = {column["name"] for column in schema["tables"][0]["columns"]}
    summary_columns = {column["name"] for column in schema["tables"][1]["columns"]}
    assert set(finding_rows(result)[0]) == finding_columns
    assert set(summary_rows(result)[0]) == summary_columns
    card = build_card(result)
    assert "Committed monthly" in {fact["name"] for fact in card["sections"][0]["facts"]}
    assert rules_plan(findings, result.summary).actions


def test_endpoint_env_password_and_url_userinfo(monkeypatch):
    from agent.endpoints import _interpolate

    monkeypatch.setenv("VCO_VC_PROD_PASSWORD", "from-env")
    loaded = normalize_endpoint(EndpointInput.model_validate(_interpolate({
        "id": "vc-prod",
        "kind": "vcenter",
        "url": "https://vcenter.example.com",
        "username": "admin",
        "password": "${ENV:VCO_VC_PROD_PASSWORD}",
    })))
    assert loaded.password.get_secret_value() == "from-env"
    embedded = normalize_endpoint(EndpointInput(
        id="vc",
        kind="vcenter",
        url="https://admin:embedded@vcenter.example.com/sdk",
    ))
    assert embedded.url == "https://vcenter.example.com/sdk"
    assert embedded.username == "admin"
    assert embedded.password.get_secret_value() == "embedded"
