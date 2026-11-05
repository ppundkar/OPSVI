"""Persistent endpoint registry used by the admin page and live scans.

The registry file holds passwords. It is created on the server that runs the
agent and is not part of the application package.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from agent.config import DEFAULT_ENDPOINTS, DEFAULT_REGISTRY, Settings
from agent.endpoints import normalize_endpoint
from agent.models import EndpointInput, EndpointPublic, EndpointWrite
from agent.yamlutil import load_yaml

_LOCK = threading.Lock()
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_ENV = re.compile(r"^\$\{ENV:[A-Za-z0-9_]+\}$")


def store_file(settings: Settings) -> Path:
    if settings.endpoints_path:
        return Path(settings.endpoints_path)
    return DEFAULT_REGISTRY


def active_store_file(settings: Settings) -> Path | None:
    chosen = store_file(settings)
    if chosen.exists():
        return chosen
    if not settings.endpoints_path and DEFAULT_ENDPOINTS.exists():
        return DEFAULT_ENDPOINTS
    return None


def load_configured(settings: Settings) -> list[EndpointInput]:
    path = active_store_file(settings)
    if path is None:
        return []
    return _load_path(path)


def list_public(settings: Settings) -> list[EndpointPublic]:
    return [_public(row) for row in _read_rows(settings)]


def register_endpoint(body: EndpointWrite, settings: Settings) -> EndpointPublic:
    _check_id(body.id)
    with _LOCK:
        rows = _read_rows(settings)
        if any(row["id"] == body.id for row in rows):
            raise ValueError(f"Endpoint {body.id} is already registered")
        if not body.password.strip():
            raise ValueError("A password, or ${ENV:VARIABLE_NAME}, is required")
        row = _row_from_write(body, "")
        rows.append(row)
        _write_rows(rows, settings)
    return _public(row)


def update_endpoint(endpoint_id: str, body: EndpointWrite, settings: Settings) -> EndpointPublic:
    _check_id(endpoint_id)
    if body.id != endpoint_id:
        raise ValueError("The endpoint id cannot be changed. Register a new endpoint instead.")
    with _LOCK:
        rows = _read_rows(settings)
        found = next((index for index, row in enumerate(rows) if row["id"] == endpoint_id), None)
        if found is None:
            raise ValueError(f"Endpoint {endpoint_id} is not registered")
        row = _row_from_write(body, rows[found].get("password", ""))
        rows[found] = row
        _write_rows(rows, settings)
    return _public(row)


def delete_endpoint(endpoint_id: str, settings: Settings) -> None:
    with _LOCK:
        rows = _read_rows(settings)
        kept = [row for row in rows if row["id"] != endpoint_id]
        if len(kept) == len(rows):
            raise ValueError(f"Endpoint {endpoint_id} is not registered")
        _write_rows(kept, settings)


def get_endpoint(endpoint_id: str, settings: Settings) -> EndpointInput:
    from agent.endpoints import _interpolate

    rows = _read_rows(settings)
    found = next((row for row in rows if row["id"] == endpoint_id), None)
    if found is None:
        raise ValueError(f"Endpoint {endpoint_id} is not registered")
    return normalize_endpoint(EndpointInput.model_validate(_interpolate(found)))


def _check_id(value: str) -> None:
    if not _ID.match(value):
        raise ValueError("id must start with a letter or number and contain only letters, numbers, dots, hyphens, and underscores")


def _row_from_write(body: EndpointWrite, previous_password: str) -> dict:
    password = body.password.strip() or previous_password
    if not password:
        raise ValueError("A password, or ${ENV:VARIABLE_NAME}, is required")
    return {
        "id": body.id,
        "kind": body.kind,
        "url": body.url,
        "username": body.username.strip(),
        "password": password,
        "verify_ssl": body.verify_ssl,
        "use_powershell": body.use_powershell,
        "deep_stats": body.deep_stats,
        "orphaned_disks": body.orphaned_disks,
        "site": body.site.strip(),
    }


def _public(row: dict) -> EndpointPublic:
    stored = str(row.get("password") or "")
    if _ENV.match(stored):
        name = stored[6:-1]
        source = "env" if os.environ.get(name) else "missing"
    elif stored:
        source = "stored"
    else:
        source = "missing"
    return EndpointPublic(
        id=row["id"],
        kind=row["kind"],
        url=row["url"],
        username=row.get("username") or "",
        password_set=source in {"stored", "env"},
        secret_source=source,
        verify_ssl=bool(row.get("verify_ssl", True)),
        use_powershell=bool(row.get("use_powershell", False)),
        deep_stats=bool(row.get("deep_stats", False)),
        orphaned_disks=bool(row.get("orphaned_disks", False)),
        site=row.get("site") or "",
    )


def _read_rows(settings: Settings) -> list[dict]:
    path = active_store_file(settings)
    if path is None:
        return []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = load_yaml(path.read_text(encoding="utf-8")) or {}
    rows = data.get("endpoints") if isinstance(data, dict) else data
    return [dict(row) for row in rows or []]


def _write_rows(rows: list[dict], settings: Settings) -> None:
    path = store_file(settings)
    if path.suffix.lower() != ".json":
        raise ValueError("The endpoint registry path must be a .json file")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"endpoints": rows}, indent=2)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        return


def _load_path(path: Path) -> list[EndpointInput]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = load_yaml(path.read_text(encoding="utf-8")) or {}
    rows = data.get("endpoints") if isinstance(data, dict) else data
    from agent.endpoints import _interpolate

    return [normalize_endpoint(EndpointInput.model_validate(_interpolate(row))) for row in rows or []]
