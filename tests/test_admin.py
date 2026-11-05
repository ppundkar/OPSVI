"""Admin registry: endpoints persist and passwords stay off the response."""

from fastapi.testclient import TestClient

from agent.main import app
from agent.registry import get_endpoint


def test_admin_registers_updates_and_removes(tmp_path):
    store = tmp_path / "endpoints.json"
    with TestClient(app) as client:
        client.app.state.settings.endpoints_path = str(store)
        created = client.post("/v1/admin/endpoints", json={
            "id": "vc-prod",
            "kind": "vcenter",
            "url": "https://vcenter.example.com",
            "username": "administrator@vsphere.local",
            "password": "s3cret-value",
            "site": "prod",
            "verify_ssl": True,
        })
        assert created.status_code == 200
        assert "s3cret-value" not in created.text
        body = created.json()
        assert body["password_set"] is True
        assert body["secret_source"] == "stored"
        listed = client.get("/v1/admin/endpoints")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == "vc-prod"
        assert "s3cret-value" not in listed.text
        duplicate = client.post("/v1/admin/endpoints", json={
            "id": "vc-prod",
            "kind": "vcenter",
            "url": "https://vcenter.example.com",
            "username": "administrator@vsphere.local",
            "password": "other",
        })
        assert duplicate.status_code == 400
        updated = client.put("/v1/admin/endpoints/vc-prod", json={
            "id": "vc-prod",
            "kind": "vcenter",
            "url": "https://vcenter.example.com",
            "username": "svc-finops",
            "password": "",
            "site": "lab",
        })
        assert updated.status_code == 200
        assert updated.json()["username"] == "svc-finops"
        assert updated.json()["site"] == "lab"
        stored = get_endpoint("vc-prod", client.app.state.settings)
        assert stored.password.get_secret_value() == "s3cret-value"
        assert stored.username == "svc-finops"
        page = client.get("/admin")
        assert page.status_code == 200
        assert "Register endpoints" in page.text
        removed = client.delete("/v1/admin/endpoints/vc-prod")
        assert removed.status_code == 200
        assert client.get("/v1/admin/endpoints").json() == []
