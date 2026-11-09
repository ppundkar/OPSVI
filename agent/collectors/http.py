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


# Session open/close and read queries. Anything else against vCenter, NSX, Aria, or VCF is refused.
_READ_ONLY_WRITES = {
    ("POST", "/api/session"),
    ("DELETE", "/api/session"),
    ("POST", "/suite-api/api/auth/token/acquire"),
    ("POST", "/suite-api/api/auth/token/release"),
    ("POST", "/suite-api/api/resources/stats/query"),
    ("POST", "/api/session/create"),
    ("POST", "/api/session/destroy"),
    ("POST", "/v1/tokens"),
    ("DELETE", "/v1/tokens"),
}


def assert_read_only(method: str, path: str) -> None:
    """Refuse any infrastructure call that is not a read or a session login or logout."""

    normalized = path.split("?", 1)[0].rstrip("/") or "/"
    verb = method.upper()
    if verb in {"GET", "HEAD"}:
        return
    if (verb, normalized) in _READ_ONLY_WRITES:
        return
    raise RuntimeError(f"VOCE is read-only and refused {verb} {normalized}")


async def _block_infrastructure_writes(request: httpx.Request) -> None:
    assert_read_only(request.method, request.url.path)


def client_for(endpoint: EndpointInput, timeout: float) -> httpx.AsyncClient:
    # Connect is short so an unreachable IPv6 address fails over quickly.
    # Read keeps the caller's budget for a large inventory download.
    # trust_env is off so an HTTP proxy on the jump box is not used for vCenter.
    return httpx.AsyncClient(
        base_url=endpoint.url,
        verify=endpoint.verify_ssl,
        timeout=httpx.Timeout(connect=3.0, read=timeout, write=10.0, pool=3.0),
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "voce/1.0", "Accept": "application/json"},
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        event_hooks={"request": [_block_infrastructure_writes]},
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
