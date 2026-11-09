from pathlib import Path

import pytest

from agent.__main__ import browse_urls, choose_port, names_cover, public_names, tls_paths
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


def test_browse_urls_use_server_name_and_ip():
    assert public_names("jump", "jump.corp.example", ["10.1.2.3", "127.0.0.1"]) == [
        "jump.corp.example",
        "jump",
        "10.1.2.3",
    ]
    assert public_names("localhost", "localhost", ["127.0.0.1"]) == ["127.0.0.1"]
    settings = Settings(host="0.0.0.0", port=8080)
    urls = browse_urls(settings, True)
    assert urls
    assert all(url.startswith("https://") and url.endswith(":8080") for url in urls)
    assert "https://127.0.0.1:8080" not in urls or urls == ["https://127.0.0.1:8080"]


def test_forbidden_port_moves_to_a_fallback():
    assert choose_port(8080, {8080: None}) == 8080
    assert choose_port(8080, {8080: "forbidden", 8443: None}) == 8443
    with pytest.raises(SystemExit, match="already in use"):
        choose_port(8080, {8080: "in-use"})


def test_localhost_certificate_does_not_cover_a_server_name():
    assert names_cover({"localhost", "127.0.0.1"}, ["127.0.0.1"])
    assert not names_cover({"localhost", "127.0.0.1"}, ["jump.corp.example", "10.1.2.3"])
    assert names_cover({"jump.corp.example", "10.1.2.3", "localhost"}, ["jump.corp.example", "10.1.2.3"])


def test_dashboard_uses_voce_name():
    with TestClient(app) as client:
        page = client.get("/")
    assert page.status_code == 200
    assert "VMware Cost Optimization Engine" in page.text
    assert "VOCE" in page.text
