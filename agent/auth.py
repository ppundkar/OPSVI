"""Optional Active Directory sign-in and role checks."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import ssl
import time
from dataclasses import dataclass

from ldap3 import Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from agent.config import DATA, Settings

COOKIE = "voce_session"
ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    username: str
    role: str


def auth_enabled(settings: Settings) -> bool:
    return settings.auth_mode.strip().lower() == "ad"


def session_secret(settings: Settings) -> str:
    configured = settings.session_secret.strip()
    if configured:
        return configured
    path = DATA / "session.key"
    if path.is_file():
        saved = path.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    path.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(32)
    path.write_text(generated, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return generated


def role_for(groups: list[str], settings: Settings) -> str:
    ranked = (
        ("admin", settings.ad_group_admin),
        ("operator", settings.ad_group_operator),
        ("viewer", settings.ad_group_viewer),
    )
    for role, configured in ranked:
        if configured.strip() and any(_group_match(group, configured) for group in groups):
            return role
    return ""


def required_role(method: str, path: str) -> str:
    if path in {"/admin"} or path.startswith("/v1/admin"):
        return "admin"
    if method.upper() == "POST" and path in {"/v1/optimize", "/v1/sessions/test"}:
        return "operator"
    return "viewer"


def issue_token(principal: Principal, settings: Settings) -> str:
    payload = {
        "u": principal.username,
        "r": principal.role,
        "e": int(time.time()) + max(60, settings.session_ttl_seconds),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    signature = hmac.new(session_secret(settings).encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def read_token(token: str, settings: Settings) -> Principal | None:
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    expected = hmac.new(session_secret(settings).encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if int(payload["e"]) < time.time():
            return None
        role = str(payload["r"])
        username = str(payload["u"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None
    if role not in ROLE_RANK or not username:
        return None
    return Principal(username, role)


def authenticate(username: str, password: str, settings: Settings) -> Principal:
    account = username.strip()
    if not account or not password:
        raise AuthError("Enter the Active Directory account and password.")
    if not settings.ad_url.strip() or not settings.ad_base_dn.strip():
        raise AuthError("Active Directory is not configured. Set VCO_AD_URL and VCO_AD_BASE_DN.")
    if not any(item.strip() for item in (settings.ad_group_admin, settings.ad_group_operator, settings.ad_group_viewer)):
        raise AuthError("No VOCE role groups are configured.")
    groups = directory_groups(account, password, settings)
    role = role_for(groups, settings)
    if not role:
        raise AuthError("This account is not in a VOCE role group.")
    return Principal(account, role)


def directory_groups(username: str, password: str, settings: Settings) -> list[str]:
    """Bind to Active Directory and return the account's memberOf values."""

    tls = Tls(validate=ssl.CERT_REQUIRED if settings.ad_verify_tls else ssl.CERT_NONE)
    use_ssl = settings.ad_url.lower().startswith("ldaps")
    server = Server(settings.ad_url, use_ssl=use_ssl, tls=tls, connect_timeout=8)
    bind_name = username if "@" in username or username.lower().startswith("cn=") else _upn(username, settings)
    try:
        if settings.ad_bind_dn.strip():
            with Connection(server, user=settings.ad_bind_dn, password=settings.ad_bind_password, auto_bind=True, receive_timeout=8) as service:
                entry = _find_user(service, username, settings)
            with Connection(server, user=entry["dn"], password=password, auto_bind=True, receive_timeout=8):
                return entry["groups"]
        with Connection(server, user=bind_name, password=password, auto_bind=True, receive_timeout=8) as person:
            return _find_user(person, username, settings)["groups"]
    except AuthError:
        raise
    except LDAPException as exc:
        raise AuthError("Active Directory did not accept that account.") from exc


def _upn(username: str, settings: Settings) -> str:
    domain = settings.ad_domain.strip()
    if not domain:
        raise AuthError("Set VCO_AD_DOMAIN, or sign in with a user@domain account.")
    return f"{username}@{domain}"


def _find_user(connection: Connection, username: str, settings: Settings) -> dict:
    account = username.split("@", 1)[0]
    safe = escape_filter_chars(account)
    found = connection.search(
        settings.ad_base_dn,
        f"(&(objectClass=user)(|(sAMAccountName={safe})(userPrincipalName={escape_filter_chars(username)})))",
        attributes=["memberOf", "sAMAccountName"],
        size_limit=2,
    )
    if not found or len(connection.entries) != 1:
        raise AuthError("Active Directory did not accept that account.")
    entry = connection.entries[0]
    groups = [str(value) for value in (entry.memberOf.values if entry.memberOf else [])]
    return {"dn": entry.entry_dn, "groups": groups}


def _group_match(member_dn: str, configured: str) -> bool:
    member = member_dn.strip().lower()
    wanted = configured.strip().lower()
    if member == wanted:
        return True
    return member.startswith(f"cn={wanted},")
