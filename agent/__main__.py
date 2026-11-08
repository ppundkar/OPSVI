"""Run the VOCE server."""

from __future__ import annotations

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


def main() -> None:
    settings = get_settings()
    ssl = tls_paths(settings)
    scheme = "https" if ssl else "http"
    print(f"VOCE listening on {scheme}://{settings.host}:{settings.port}", flush=True)
    if ssl and settings.host in {"0.0.0.0", "::"}:
        print(f"Open https://<fqdn-or-ip>:{settings.port}", flush=True)
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
