"""HTTP API for the VMware cost optimization agent."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from agent import __version__
from agent.config import get_settings, load_rates
from agent.endpoints import load_endpoints
from agent.models import (
    EndpointPublic,
    EndpointStatus,
    EndpointWrite,
    OptimizeRequest,
    OptimizeResponse,
    SessionTestRequest,
    SessionTestResponse,
)
from agent.integrations.powerbi import push_powerbi
from agent.integrations.teams import notify_teams
from agent.orchestrator import probe_all
from agent.registry import delete_endpoint, get_endpoint, list_public, register_endpoint, update_endpoint
from agent.reports.export import render_admin, render_dashboard
from agent.service import ReportStore, TtlCache, run_analysis
from agent.timing import TimingBoard


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = get_settings()
    app.state.rates = load_rates()
    app.state.cache = TtlCache()
    app.state.reports = ReportStore()
    app.state.timings = TimingBoard()
    yield


app = FastAPI(
    title="VMware Cost Optimization Agent",
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=800)


@app.middleware("http")
async def api_key_gate(request: Request, call_next):
    settings = getattr(request.app.state, "settings", None)
    if settings and settings.api_key and request.url.path.startswith("/v1"):
        if request.headers.get("x-api-key") != settings.api_key:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def response_time(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["X-Response-Time-Ms"] = f"{elapsed:.1f}"
    response.headers["Server-Timing"] = f"app;dur={elapsed:.1f}"
    response.headers["Cache-Control"] = "no-store"
    timings = getattr(request.app.state, "timings", None)
    if timings is not None:
        timings.add(request.url.path, elapsed)
    return response


@app.exception_handler(ValueError)
async def value_error(_, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    return render_dashboard()


@app.get("/admin", response_class=HTMLResponse)
def admin() -> str:
    return render_admin()


@app.get("/health")
@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok", "service": "vmware-cost-agent", "version": __version__}


@app.get("/v1/rates")
def rates(request: Request) -> dict:
    return request.app.state.rates.model_dump()


@app.get("/v1/metrics")
def metrics(request: Request) -> dict:
    return request.app.state.timings.summary()


@app.post("/v1/sessions/test", response_model=SessionTestResponse)
async def test_sessions(body: SessionTestRequest, request: Request) -> SessionTestResponse:
    settings = request.app.state.settings
    endpoints = body.endpoints or (load_endpoints(settings) if body.use_config else [])
    if not endpoints:
        raise ValueError("No endpoints are registered. Open /admin and add each system.")
    started = time.perf_counter()
    statuses = await probe_all(endpoints, settings)
    return SessionTestResponse(
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        endpoints=statuses,
    )


@app.get("/v1/admin/endpoints", response_model=list[EndpointPublic])
def admin_list(request: Request) -> list[EndpointPublic]:
    return list_public(request.app.state.settings)


@app.post("/v1/admin/endpoints", response_model=EndpointPublic)
def admin_create(body: EndpointWrite, request: Request) -> EndpointPublic:
    return register_endpoint(body, request.app.state.settings)


@app.put("/v1/admin/endpoints/{endpoint_id}", response_model=EndpointPublic)
def admin_update(endpoint_id: str, body: EndpointWrite, request: Request) -> EndpointPublic:
    return update_endpoint(endpoint_id, body, request.app.state.settings)


@app.delete("/v1/admin/endpoints/{endpoint_id}")
def admin_delete(endpoint_id: str, request: Request) -> dict:
    delete_endpoint(endpoint_id, request.app.state.settings)
    return {"deleted": endpoint_id}


@app.post("/v1/admin/endpoints/{endpoint_id}/test", response_model=EndpointStatus)
async def admin_test(endpoint_id: str, request: Request) -> EndpointStatus:
    settings = request.app.state.settings
    started = time.perf_counter()
    statuses = await probe_all([get_endpoint(endpoint_id, settings)], settings)
    status = statuses[0]
    status.latency_ms = round(max(status.latency_ms, (time.perf_counter() - started) * 1000), 2)
    return status


@app.post("/v1/optimize", response_model=OptimizeResponse)
async def optimize(body: OptimizeRequest, request: Request) -> OptimizeResponse:
    state = request.app.state
    result, html, csv_text = await run_analysis(body, state.settings, state.rates, state.cache)
    if html:
        state.reports.put(result.analysis_id, html, csv_text)
    if body.notify_teams:
        result.teams = await notify_teams(result, state.settings)
    if body.push_powerbi:
        result.powerbi = await push_powerbi(
            result,
            state.settings,
            [result.exports.powerbi_findings_csv, result.exports.powerbi_summary_csv],
        )
    return result


@app.get("/v1/reports/{report_name}")
def report_file(request: Request, report_name: str):
    if report_name.endswith(".html"):
        analysis_id = report_name[: -len(".html")] or "latest"
        return HTMLResponse(_lookup(request, analysis_id, "html"))
    if report_name.endswith(".csv"):
        analysis_id = report_name[: -len(".csv")] or "latest"
        text = _lookup(request, analysis_id, "csv")
        filename = "vmware-cost-latest.csv" if analysis_id == "latest" else f"vmware-cost-{analysis_id}.csv"
        return Response(
            content="\ufeff" + text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    raise HTTPException(status_code=404, detail="Report not found")


def _lookup(request: Request, analysis_id: str, kind: str) -> str:
    store: ReportStore = request.app.state.reports
    chosen = store.latest if analysis_id == "latest" else analysis_id
    if not chosen:
        raise HTTPException(status_code=404, detail="No report yet. Run an analysis first.")
    bucket = store.html if kind == "html" else store.csv
    text = bucket.get(chosen)
    if text is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return text
