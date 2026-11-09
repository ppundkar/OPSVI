"""Run the VOCE server."""

from __future__ import annotations

import os
import socket
import ssl
import subprocess
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


FALLBACK_PORTS = (8443, 8088, 18080, 8888)


def bind_state(host: str, port: int) -> str | None:
    """Return why a port cannot be used, or None when this process can bind it."""

    bind_host = "0.0.0.0" if host in {"", "::", "0.0.0.0"} else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((bind_host, port))
    except OSError as exc:
        code = getattr(exc, "winerror", None) or exc.errno
        if code in {10048, 98}:
            return "in-use"
        if code in {10013, 13}:
            return "forbidden"
        return "unavailable"
    return None


def choose_port(requested: int, states: dict[int, str | None]) -> int:
    state = states.get(requested)
    if state is None:
        return requested
    if state == "in-use":
        raise SystemExit(
            f"Port {requested} is already in use. Close the other VOCE window, or set VCO_PORT in .env to a free port."
        )
    for port in (requested, *FALLBACK_PORTS):
        if states.get(port) is None:
            return port
    raise SystemExit(
        f"Windows refused port {requested}. Set VCO_PORT in .env to a free port, then run .\\start.ps1 again."
    )


def remember_setting(key: str, value: str) -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    updated = False
    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            updated = True
    if not updated:
        lines.append(f"{prefix}{value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def listen_host(host: str) -> str:
    """Use every network address so the server name and IP both reach VOCE."""

    if host.strip().lower() in {"127.0.0.1", "localhost", "::1"}:
        return "0.0.0.0"
    return host


def windows_firewall_command(port: int) -> list[str]:
    return [
        "netsh",
        "advfirewall",
        "firewall",
        "add",
        "rule",
        f"name=VOCE {port}",
        "dir=in",
        "action=allow",
        "protocol=TCP",
        f"localport={port}",
        "profile=any",
    ]


def allow_windows_port(port: int) -> None:
    if os.name != "nt":
        return
    result = subprocess.run(windows_firewall_command(port), capture_output=True, text=True)
    text = f"{result.stdout}\n{result.stderr}".lower()
    if result.returncode == 0 or "already exists" in text:
        print(f"Windows Firewall allows inbound TCP {port}.", flush=True)
        return
    print(
        "Other computers cannot connect until Windows Firewall allows this port. "
        "Open PowerShell as Administrator and run:",
        flush=True,
    )
    print(" ".join(windows_firewall_command(port)), flush=True)


def resolve_port(host: str, requested: int) -> tuple[int, str]:
    candidates = [requested, *[port for port in FALLBACK_PORTS if port != requested]]
    states = {port: bind_state(host, port) for port in candidates}
    chosen = choose_port(requested, states)
    if chosen == requested:
        return chosen, ""
    remember_setting("VCO_PORT", str(chosen))
    return chosen, (
        f"Windows refused port {requested}. VOCE is using {chosen} instead, and .env now has VCO_PORT={chosen}."
    )


def print_browse_urls() -> None:
    settings = get_settings()
    ssl = bool(tls_paths(settings)) if settings.ssl_certfile.strip() or settings.ssl_keyfile.strip() else False
    for url in browse_urls(settings, ssl):
        print(f"Dashboard: {url}", flush=True)
        print(f"Admin:     {url}/admin", flush=True)


def main() -> None:
    settings = get_settings()
    host = listen_host(settings.host)
    if host != settings.host:
        settings.host = host
        remember_setting("VCO_HOST", host)
        print("VOCE is listening on every address so the server name and IP work.", flush=True)
    chosen, notice = resolve_port(settings.host, settings.port)
    settings.port = chosen
    if notice:
        print(notice, flush=True)
    allow_windows_port(settings.port)
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
