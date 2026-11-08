from pathlib import Path

import pytest

from agent.__main__ import tls_paths
from agent.config import Settings
from agent.main import app
from fastapi.testclient import TestClient


def test_tls_is_off_until_both_files_exist(tmp_path: Path):
    assert tls_paths(Settings(ssl_certfile="", ssl_keyfile="")) == {}
    with pytest.raises(SystemExit):
        tls_paths(Settings(ssl_certfile="cert.pem", ssl_keyfile=""))
    missing = tmp_path / "missing.pem"
    present = tmp_path / "present.pem"
    present.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        tls_paths(Settings(ssl_certfile=str(present), ssl_keyfile=str(missing)))
    other = tmp_path / "key.pem"
    other.write_text("y", encoding="utf-8")
    paths = tls_paths(Settings(ssl_certfile=str(present), ssl_keyfile=str(other)))
    assert paths["ssl_certfile"] == str(present)
    assert paths["ssl_keyfile"] == str(other)


def test_dashboard_uses_voce_name():
    with TestClient(app) as client:
        page = client.get("/")
    assert page.status_code == 200
    assert "VMware Cost Optimization Engine" in page.text
    assert "VOCE" in page.text
