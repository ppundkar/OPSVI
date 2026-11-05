"""Shared HTTP helpers for endpoint collectors."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import httpx

from agent.models import EndpointInput


def endpoint_host(endpoint: EndpointInput) -> str:
    parsed = urlparse(endpoint.url)
    host = parsed.hostname or endpoint.url
    if parsed.port:
        return f"{host}:{parsed.port}"
    return host


def redact(text: str, secret: str) -> str:
    cleaned = " ".join(text.split())
    if secret:
        cleaned = cleaned.replace(secret, "***")
    return cleaned[:300]


def raise_for_auth(response: httpx.Response, system: str) -> None:
    if response.status_code in {401, 403}:
        raise PermissionError(f"{system} authentication failed ({response.status_code})")
    response.raise_for_status()


def read_json(response: httpx.Response, system: str):
    raise_for_auth(response, system)
    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError(f"{system} returned non-JSON ({response.status_code})") from exc


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def basic_auth(endpoint: EndpointInput) -> httpx.BasicAuth:
    return httpx.BasicAuth(endpoint.username, endpoint.password.get_secret_value())


def client_for(endpoint: EndpointInput, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=endpoint.url,
        verify=endpoint.verify_ssl,
        timeout=httpx.Timeout(timeout),
        follow_redirects=False,
        headers={"User-Agent": "vmware-cost-agent/1.0", "Accept": "application/json"},
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


def strip_userinfo(url: str) -> tuple[str, str, str]:
    """Return url without embedded credentials, plus any username and password found there."""

    parsed = urlparse(url.strip())
    username = parsed.username or ""
    password = parsed.password or ""
    if not username and not password:
        return url.rstrip("/"), "", ""
    host = parsed.hostname or ""
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    cleaned = urlunparse((parsed.scheme, netloc, parsed.path, "", "", "")).rstrip("/")
    return cleaned, username, password
