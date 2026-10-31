"""Bearer-token authentication on /link-status and /unlink-account.

These routes must identify the caller from a verified token only: a forged,
unsigned, wrongly-signed, foreign or expired Bearer token is rejected with 401
and never unlinks anyone. A Bearer header that fails verification does not fall
back to the session cookie. The cookie path (browser linking flow) keeps working.

No network: the verifier's JWKS client is stubbed with a locally generated key.
"""

import base64
import hashlib
import hmac
import json
import os
import tempfile
import time
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr
from starlette.applications import Starlette
from starlette.testclient import TestClient

from src.auth import link_routes
from src.auth.credential_store import TaigaCredentialStore
from src.auth.token_verifier import Auth0TokenVerifier

ISSUER = "https://test.auth0.com/"
AUDIENCE = "https://taiga-mcp.test.dev"
VICTIM = "auth0|victim-0001"
OTHER = "auth0|attacker-0002"

ROUTES = [("GET", "/link-status"), ("POST", "/unlink-account")]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _claims(**overrides):
    claims = {
        "sub": VICTIM,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 3600,
        "scope": "taiga:read taiga:write",
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


@pytest.fixture(scope="module")
def server_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def attacker_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def sign(server_key):
    def _sign(**overrides):
        return jwt.encode(_claims(**overrides), server_key, algorithm="RS256")

    return _sign


@pytest.fixture
def verifier(server_key):
    """The real Auth0TokenVerifier with its JWKS client stubbed to our key."""
    v = Auth0TokenVerifier(issuer_url=ISSUER, audience=AUDIENCE)
    signing_key = MagicMock()
    signing_key.key = server_key.public_key()
    v._jwks_client = MagicMock()
    v._jwks_client.get_signing_key_from_jwt.return_value = signing_key
    return v


@pytest.fixture
def fernet_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(link_routes.settings, "credential_encryption_key", SecretStr(key))
    return key


@pytest.fixture
def store(fernet_key):
    with tempfile.TemporaryDirectory() as tmpdir:
        s = TaigaCredentialStore(
            db_path=os.path.join(tmpdir, "creds.db"), encryption_key=fernet_key
        )
        s.store_taiga_token(VICTIM, "victim-taiga-token")
        s.store_taiga_token(OTHER, "other-taiga-token")
        yield s


def _client(store, verifier, bridge=None, required_scopes=None):
    routes = link_routes.create_link_routes(
        store, bridge=bridge, token_verifier=verifier, required_scopes=required_scopes
    )
    return TestClient(Starlette(routes=routes))


def _call(client, method, path, token=None, cookie=None, raw_auth=None):
    headers = {}
    if raw_auth is not None:
        headers["Authorization"] = raw_auth
    elif token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if cookie is not None:
        client.cookies.set("taiga_link_session", cookie)
    return client.request(method, path, headers=headers)


def _cookie_for(sub, fernet_key):
    session_key = link_routes._derive_session_key(fernet_key)
    return link_routes._sign_session(sub, session_key, 600)


# --- forged tokens ---------------------------------------------------------


def _unsigned(_sign, _attacker_key, _server_key):
    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(json.dumps(_claims()).encode())
    return f"{header}.{payload}."


def _hs256_secret(_sign, _attacker_key, _server_key):
    return jwt.encode(_claims(), "attacker-chosen-secret-0123456789abcdef", algorithm="HS256")


def _hs256_public_key_confusion(_sign, _attacker_key, server_key):
    """HS256 signed with the server's public key PEM as the HMAC secret."""
    pem = server_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(json.dumps(_claims()).encode())
    sig = hmac.new(pem, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(sig)}"


def _rs256_attacker_key(_sign, attacker_key, _server_key):
    return jwt.encode(_claims(), attacker_key, algorithm="RS256")


def _wrong_issuer(sign, _a, _s):
    return sign(iss="https://evil.auth0.com/")


def _wrong_audience(sign, _a, _s):
    return sign(aud="https://some-other-api.example")


def _expired(sign, _a, _s):
    return sign(exp=int(time.time()) - 60)


def _missing_sub(sign, _a, _s):
    return sign(sub=None)


def _not_a_jwt(_sign, _a, _s):
    return "not-a-jwt"


def _empty(_sign, _a, _s):
    return ""


FORGED = {
    "unsigned_alg_none": _unsigned,
    "hs256_attacker_secret": _hs256_secret,
    "hs256_public_key_confusion": _hs256_public_key_confusion,
    "rs256_attacker_key": _rs256_attacker_key,
    "wrong_issuer": _wrong_issuer,
    "wrong_audience": _wrong_audience,
    "expired": _expired,
    "missing_sub": _missing_sub,
    "not_a_jwt": _not_a_jwt,
    "empty": _empty,
}


@pytest.mark.parametrize("method,path", ROUTES)
@pytest.mark.parametrize("kind", list(FORGED))
def test_forged_bearer_is_rejected_and_nothing_unlinked(
    method, path, kind, store, verifier, sign, attacker_key, server_key
):
    bridge = MagicMock()
    client = _client(store, verifier, bridge=bridge)
    token = FORGED[kind](sign, attacker_key, server_key)

    resp = _call(client, method, path, token=token)

    assert resp.status_code == 401, resp.text
    assert "linked" not in resp.json()
    bridge.unlink.assert_not_called()
    assert store.is_linked(VICTIM)


@pytest.mark.parametrize("kind", list(FORGED))
def test_forged_bearer_without_bridge_does_not_remove_user(
    kind, store, verifier, sign, attacker_key, server_key
):
    client = _client(store, verifier, bridge=None)
    token = FORGED[kind](sign, attacker_key, server_key)

    resp = _call(client, "POST", "/unlink-account", token=token)

    assert resp.status_code == 401
    assert store.is_linked(VICTIM)


@pytest.mark.parametrize("method,path", ROUTES)
def test_invalid_bearer_does_not_fall_back_to_cookie(
    method, path, store, verifier, attacker_key, fernet_key
):
    """A presented-but-invalid Bearer token fails closed, even with a valid cookie."""
    bridge = MagicMock()
    client = _client(store, verifier, bridge=bridge)
    forged = jwt.encode(_claims(), attacker_key, algorithm="RS256")

    resp = _call(client, method, path, token=forged, cookie=_cookie_for(OTHER, fernet_key))

    assert resp.status_code == 401
    bridge.unlink.assert_not_called()
    assert store.is_linked(OTHER)
    assert store.is_linked(VICTIM)


@pytest.mark.parametrize("method,path", ROUTES)
def test_bearer_rejected_when_no_verifier_configured(method, path, store, sign):
    """Without a verifier there is no way to trust a Bearer token: fail closed."""
    bridge = MagicMock()
    client = _client(store, None, bridge=bridge)

    resp = _call(client, method, path, token=sign())

    assert resp.status_code == 401
    bridge.unlink.assert_not_called()
    assert store.is_linked(VICTIM)


@pytest.mark.parametrize("method,path", ROUTES)
def test_no_credentials_is_unauthorized(method, path, store, verifier):
    client = _client(store, verifier)
    resp = _call(client, method, path)
    assert resp.status_code == 401


# --- accepted tokens ---------------------------------------------------------


def test_valid_bearer_link_status(store, verifier, sign):
    client = _client(store, verifier)
    resp = _call(client, "GET", "/link-status", token=sign())
    assert resp.status_code == 200
    assert resp.json()["linked"] is True
    assert resp.json()["oauth_sub"] == VICTIM[:8] + "..."


def test_valid_bearer_scheme_is_case_insensitive(store, verifier, sign):
    client = _client(store, verifier)
    resp = _call(client, "GET", "/link-status", raw_auth=f"bearer {sign()}")
    assert resp.status_code == 200


def test_valid_bearer_unlinks_through_bridge(store, verifier, sign):
    bridge = MagicMock()
    client = _client(store, verifier, bridge=bridge)
    resp = _call(client, "POST", "/unlink-account", token=sign())
    assert resp.status_code == 200
    assert resp.json()["status"] == "unlinked"
    bridge.unlink.assert_called_once_with(VICTIM)


def test_valid_bearer_unlinks_only_its_own_subject(store, verifier, sign):
    client = _client(store, verifier, bridge=None)
    resp = _call(client, "POST", "/unlink-account", token=sign())
    assert resp.status_code == 200
    assert not store.is_linked(VICTIM)
    assert store.is_linked(OTHER)


def test_valid_bearer_with_required_scopes(store, verifier, sign):
    bridge = MagicMock()
    client = _client(store, verifier, bridge=bridge, required_scopes=["taiga:read"])
    resp = _call(client, "POST", "/unlink-account", token=sign())
    assert resp.status_code == 200
    bridge.unlink.assert_called_once_with(VICTIM)


@pytest.mark.parametrize("method,path", ROUTES)
def test_bearer_missing_required_scope_is_forbidden(method, path, store, verifier, sign):
    """Same scope policy as /mcp: a token /mcp would refuse cannot unlink."""
    bridge = MagicMock()
    client = _client(store, verifier, bridge=bridge, required_scopes=["taiga:write"])
    resp = _call(client, method, path, token=sign(scope="taiga:read"))
    assert resp.status_code == 403
    bridge.unlink.assert_not_called()
    assert store.is_linked(VICTIM)


# --- cookie session path -----------------------------------------------------


def test_cookie_session_link_status(store, verifier, fernet_key):
    client = _client(store, verifier)
    resp = _call(client, "GET", "/link-status", cookie=_cookie_for(VICTIM, fernet_key))
    assert resp.status_code == 200
    assert resp.json()["linked"] is True


def test_cookie_session_unlink(store, verifier, fernet_key):
    bridge = MagicMock()
    client = _client(store, verifier, bridge=bridge)
    resp = _call(client, "POST", "/unlink-account", cookie=_cookie_for(VICTIM, fernet_key))
    assert resp.status_code == 200
    bridge.unlink.assert_called_once_with(VICTIM)


def test_cookie_session_works_without_verifier(store, fernet_key):
    client = _client(store, None)
    resp = _call(client, "GET", "/link-status", cookie=_cookie_for(VICTIM, fernet_key))
    assert resp.status_code == 200


def test_tampered_cookie_is_rejected(store, verifier, fernet_key):
    bridge = MagicMock()
    client = _client(store, verifier, bridge=bridge)
    cookie = _cookie_for(OTHER, fernet_key)
    decoded = base64.urlsafe_b64decode(cookie).decode().replace(OTHER, VICTIM)
    forged = base64.urlsafe_b64encode(decoded.encode()).decode()
    resp = _call(client, "POST", "/unlink-account", cookie=forged)
    assert resp.status_code == 401
    bridge.unlink.assert_not_called()


# --- server wiring -----------------------------------------------------------


def test_server_wires_verifier_into_link_routes(store, verifier, attacker_key, sign, monkeypatch):
    """The routes the HTTP server mounts use the same verifier as /mcp."""
    import src.server as server
    import src.session as session

    bridge = MagicMock()
    bridge.credential_store = store
    monkeypatch.setattr(session, "_oauth_bridge", bridge)
    monkeypatch.setattr(session, "_link_token_verifier", verifier, raising=False)

    client = TestClient(Starlette(routes=server.build_link_routes()))

    forged = jwt.encode(_claims(), attacker_key, algorithm="RS256")
    assert _call(client, "POST", "/unlink-account", token=forged).status_code == 401
    bridge.unlink.assert_not_called()

    assert _call(client, "POST", "/unlink-account", token=sign()).status_code == 200
    bridge.unlink.assert_called_once_with(VICTIM)


def _oauth_settings():
    from types import SimpleNamespace

    return SimpleNamespace(
        transport="streamable-http",
        has_oauth_config=True,
        oauth_issuer_url=ISSUER,
        oauth_audience=AUDIENCE,
        scopes_list=["taiga:read"],
        jwks_cache_ttl=600,
        get_encryption_key=lambda: None,
    )


def test_create_mcp_server_shares_its_verifier_with_link_routes(monkeypatch):
    import src.server as server
    import src.session as session

    monkeypatch.setattr(server, "settings", _oauth_settings())
    monkeypatch.setattr(session, "_link_token_verifier", None, raising=False)

    mcp_server = server.create_mcp_server()

    assert session.get_link_token_verifier() is mcp_server._token_verifier


def test_audience_check_is_explicitly_left_to_the_verifier(monkeypatch):
    """mcp>=1.30 warns when validate_token_resource is unset; our verifier checks `aud`."""
    import warnings

    import src.server as server

    monkeypatch.setattr(server, "settings", _oauth_settings())
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        mcp_server = server.create_mcp_server()

    assert mcp_server.settings.auth.validate_token_resource is False
