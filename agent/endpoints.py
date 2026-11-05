"""Load endpoint definitions and keep secrets out of logs."""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import SecretStr

from agent.collectors.http import strip_userinfo
from agent.config import Settings
from agent.models import EndpointInput

_ENV = re.compile(r"\$\{ENV:([A-Za-z0-9_]+)\}")


def load_endpoints(settings: Settings, path: Path | None = None) -> list[EndpointInput]:
    from agent.registry import load_configured, _load_path

    if path is not None:
        if not path.exists():
            return []
        return _load_path(path)
    return load_configured(settings)


def normalize_endpoint(endpoint: EndpointInput) -> EndpointInput:
    cleaned, user, password = strip_userinfo(endpoint.url)
    username = endpoint.username or user
    secret = endpoint.password.get_secret_value() or password
    if not secret:
        env_name = "VCO_" + re.sub(r"[^A-Za-z0-9]", "_", endpoint.id).upper() + "_PASSWORD"
        secret = os.environ.get(env_name, "")
    return endpoint.model_copy(update={"url": cleaned, "username": username, "password": SecretStr(secret)})


def _interpolate(value):
    if isinstance(value, dict):
        return {key: _interpolate(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_interpolate(item) for item in value]
    if isinstance(value, str):
        return _ENV.sub(lambda match: os.environ.get(match.group(1), ""), value)
    return value
