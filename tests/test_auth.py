from fastapi.testclient import TestClient

from agent.auth import AuthError, role_for
from agent.main import app


def test_role_matches_group_name_or_dn():
    from agent.config import Settings

    settings = Settings(
        ad_group_admin="VOCE-Admins",
        ad_group_operator="CN=VOCE-Operators,OU=Groups,DC=corp,DC=example",
        ad_group_viewer="VOCE-Viewers",
    )
    assert role_for(["CN=VOCE-Admins,OU=Groups,DC=corp,DC=example"], settings) == "admin"
    assert role_for(["CN=VOCE-Operators,OU=Groups,DC=corp,DC=example"], settings) == "operator"
    assert role_for(["CN=Finance,OU=Groups,DC=corp,DC=example"], settings) == ""


def test_ad_sign_in_enforces_roles(monkeypatch):
    def groups(username, password, settings):
        if password != "correct" or username != "viewer@corp.example":
            raise AuthError("Active Directory did not accept that account.")
        return ["CN=VOCE-Viewers,OU=Groups,DC=corp,DC=example"]

    monkeypatch.setattr("agent.auth.directory_groups", groups)

    with TestClient(app) as client:
        settings = client.app.state.settings
        previous = (
            settings.auth_mode,
            settings.session_secret,
            settings.api_key,
            settings.ad_url,
            settings.ad_base_dn,
            settings.ad_group_admin,
            settings.ad_group_operator,
            settings.ad_group_viewer,
        )
        settings.auth_mode = "ad"
        settings.session_secret = "test-secret"
        settings.api_key = "script-key"
        settings.ad_url = "ldaps://dc.corp.example:636"
        settings.ad_base_dn = "DC=corp,DC=example"
        settings.ad_group_admin = "VOCE-Admins"
        settings.ad_group_operator = "VOCE-Operators"
        settings.ad_group_viewer = "VOCE-Viewers"
        try:
            anonymous = client.get("/", follow_redirects=False)
            assert anonymous.status_code == 303
            assert anonymous.headers["location"] == "/login"
            denied = client.post("/login", data={"username": "viewer@corp.example", "password": "wrong"})
            assert denied.status_code == 401
            signed = client.post("/login", data={"username": "viewer@corp.example", "password": "correct"}, follow_redirects=False)
            assert signed.status_code == 303
            page = client.get("/")
            assert page.status_code == 200
            assert "viewer@corp.example" in page.text
            assert "Analyze demo estate" not in page.text
            blocked = client.post("/v1/optimize", json={"demo": True})
            assert blocked.status_code == 403
            admin_page = client.get("/admin")
            assert admin_page.status_code == 403
            scanned = client.post("/v1/optimize", json={"demo": True}, headers={"X-API-Key": "script-key"})
            assert scanned.status_code == 200
        finally:
            (
                settings.auth_mode,
                settings.session_secret,
                settings.api_key,
                settings.ad_url,
                settings.ad_base_dn,
                settings.ad_group_admin,
                settings.ad_group_operator,
                settings.ad_group_viewer,
            ) = previous
