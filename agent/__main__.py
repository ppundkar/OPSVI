"""Run the VOCE server."""

from __future__ import annotations

import socket
import ssl
from pathlib import Path

import uvicorn

from agent.config import ROOT, Settings, get_settings


def tls_paths(settings: Settings) -> dict[str, str]:
    """Return uvicorn SSL arguments when both certificate files are configured."""

    cert_value = settings.ssl_certfile.strip()
    key_value = settings.ssl_keyfile.strip()
    if not cert_value and not key_value:
        return {}
    if not cert_value or not key_value:
        raise SystemExit("Set both VCO_SSL_CERTFILE and VCO_SSL_KEYFILE, or leave both empty.")
    cert = Path(cert_value)
    key = Path(key_value)
    if not cert.is_absolute():
        cert = ROOT / cert
    if not key.is_absolute():
        key = ROOT / key
    if not cert.is_file() or not key.is_file():
        raise SystemExit(f"HTTPS certificate files were not found: {cert} and {key}")
    return {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}


def public_names(hostname: str, fqdn: str, addresses: list[str]) -> list[str]:
    """Names and addresses a browser can use. Loopback is only a fallback."""

    names: list[str] = []
    for value in (fqdn, hostname, *addresses):
        candidate = value.strip().rstrip(".")
        if not candidate or candidate in names:
            continue
        lowered = candidate.lower()
        if lowered in {"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"}:
            continue
        if lowered.startswith("127.") or lowered.startswith("169.254.") or lowered.startswith("fe80:"):
            continue
        names.append(candidate)
    return names or ["127.0.0.1"]


def server_names() -> list[str]:
    hostname = socket.gethostname()
    fqdn = socket.getfqdn()
    addresses: list[str] = []
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            if family == socket.AF_INET:
                addresses.append(sockaddr[0])
    except OSError:
        addresses = []
    return public_names(hostname, fqdn, addresses)


def browse_urls(settings: Settings, ssl: bool) -> list[str]:
    scheme = "https" if ssl else "http"
    return [f"{scheme}://{_host_for_url(name)}:{settings.port}" for name in server_names()]


def _host_for_url(name: str) -> str:
    if ":" in name and not name.startswith("["):
        return f"[{name}]"
    return name


def certificate_names(path: Path) -> set[str]:
    decoded = ssl._ssl._test_decode_cert(str(path))
    names = set()
    for _kind, value in decoded.get("subjectAltName", ()):
        names.add(str(value).lower())
    for group in decoded.get("subject", ()):
        for key, value in group:
            if key == "commonName":
                names.add(str(value).lower())
    return names


def names_cover(present: set[str], required: list[str]) -> bool:
    folded = {item.lower() for item in present}
    return all(name.lower() in folded for name in required)


def certificate_covers_server(path: Path) -> bool:
    return names_cover(certificate_names(path), server_names())


def default_cert_is_stale() -> bool:
    """True when the generated certificate is missing this server's name or IP."""

    settings = get_settings()
    configured = settings.ssl_certfile.strip().replace("\\", "/")
    if configured and configured != "data/tls/cert.pem":
        return False
    cert = ROOT / "data" / "tls" / "cert.pem"
    if not cert.is_file():
        return False
    return not certificate_covers_server(cert)


def print_browse_urls() -> None:
    settings = get_settings()
    ssl = bool(tls_paths(settings)) if settings.ssl_certfile.strip() or settings.ssl_keyfile.strip() else False
    for url in browse_urls(settings, ssl):
        print(f"Dashboard: {url}", flush=True)
        print(f"Admin:     {url}/admin", flush=True)


def main() -> None:
    settings = get_settings()
    ssl = tls_paths(settings)
    scheme = "https" if ssl else "http"
    print(f"VOCE listening on {scheme}://{settings.host}:{settings.port}", flush=True)
    for url in browse_urls(settings, bool(ssl)):
        print(f"Dashboard: {url}", flush=True)
        print(f"Admin:     {url}/admin", flush=True)
    if ssl and default_cert_is_stale():
        print(
            "The HTTPS certificate is only valid for localhost. "
            "The browser will say this site cannot provide a secure connection. "
            "Run .\\enable-https.ps1 or ./enable-https.sh, then restart VOCE.",
            flush=True,
        )
    uvicorn.run(
        "agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        access_log=False,
        **ssl,
    )


if __name__ == "__main__":
    main()
