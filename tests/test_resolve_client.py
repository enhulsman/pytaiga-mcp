"""Tests for the client resolution layer (src.session.resolve_client).

stdio mode: unchanged behaviour, the default session or an explicit session_id.
OAuth mode: the Taiga identity follows the OAuth subject; unlinked subjects are
refused with the link URL; an explicit session_id is rejected so nobody can
select the service-account session by hand.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pytaigaclient.exceptions import TaigaAuthenticationError

import src.session as session
from src.session import (
    NotLinkedError,
    execute_taiga_operation,
    resolve_client,
    set_oauth_bridge,
)


def _auth_error(status_code: int) -> TaigaAuthenticationError:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {"_error_message": "denied"}
    response.text = "denied"
    return TaigaAuthenticationError(status_code, response)


@pytest.fixture
def stdio_mode():
    """No bridge: the server behaves as in stdio mode."""
    set_oauth_bridge(None)
    saved = dict(session.active_sessions)
    session.active_sessions.clear()
    yield
    session.active_sessions.clear()
    session.active_sessions.update(saved)


@pytest.fixture
def oauth_mode():
    """A bridge is set: the server behaves as in OAuth mode. Yields the bridge mock."""
    bridge = MagicMock()
    bridge.get_client_sync.return_value = None
    set_oauth_bridge(bridge)
    saved = dict(session.active_sessions)
    default_client = MagicMock(name="service-account-client")
    default_client.is_authenticated = True
    session.active_sessions[session.DEFAULT_SESSION_ID] = default_client
    with patch.object(session.settings, "oauth_audience", "https://taiga-mcp.example.test/"):
        yield bridge
    set_oauth_bridge(None)
    session.active_sessions.clear()
    session.active_sessions.update(saved)


def _token(sub: str):
    return SimpleNamespace(client_id=sub, scopes=["taiga:read", "taiga:write"])


class TestStdioMode:
    def test_default_session_when_no_session_id(self, stdio_mode):
        client = MagicMock()
        client.is_authenticated = True
        session.active_sessions[session.DEFAULT_SESSION_ID] = client
        assert resolve_client(None) is client

    def test_explicit_session_id_is_honoured(self, stdio_mode):
        client = MagicMock()
        client.is_authenticated = True
        session.active_sessions["abc"] = client
        assert resolve_client("abc") is client

    def test_no_default_session_raises_value_error(self, stdio_mode):
        with pytest.raises(ValueError):
            resolve_client(None)

    def test_unknown_session_id_raises_permission_error(self, stdio_mode):
        with pytest.raises(PermissionError):
            resolve_client("does-not-exist")

    def test_401_is_reraised_unchanged(self, stdio_mode):
        with pytest.raises(TaigaAuthenticationError):
            execute_taiga_operation("op", lambda: (_ for _ in ()).throw(_auth_error(401)))


class TestOAuthMode:
    def test_linked_subject_gets_its_own_client(self, oauth_mode):
        linked = MagicMock(name="bas-client")
        oauth_mode.get_client_sync.return_value = linked
        with patch("src.session.get_access_token", return_value=_token("auth0|bas")):
            assert resolve_client(None) is linked
        oauth_mode.get_client_sync.assert_called_once_with("auth0|bas")

    def test_two_subjects_get_two_clients(self, oauth_mode):
        clients = {"auth0|bas": MagicMock(name="bas"), "auth0|peter": MagicMock(name="peter")}
        oauth_mode.get_client_sync.side_effect = lambda sub: clients[sub]
        with patch("src.session.get_access_token", return_value=_token("auth0|bas")):
            first = resolve_client(None)
        with patch("src.session.get_access_token", return_value=_token("auth0|peter")):
            second = resolve_client(None)
        assert first is clients["auth0|bas"]
        assert second is clients["auth0|peter"]
        assert first is not second

    def test_unlinked_subject_is_refused_with_link_url(self, oauth_mode):
        oauth_mode.get_client_sync.return_value = None
        with patch("src.session.get_access_token", return_value=_token("auth0|new")):
            with pytest.raises(NotLinkedError) as exc:
                resolve_client(None)
        assert "https://taiga-mcp.example.test/link-account" in str(exc.value)
        assert isinstance(exc.value, PermissionError)

    def test_unlinked_subject_never_falls_back_to_service_account(self, oauth_mode):
        oauth_mode.get_client_sync.return_value = None
        default_client = session.active_sessions[session.DEFAULT_SESSION_ID]
        with patch("src.session.get_access_token", return_value=_token("auth0|new")):
            with pytest.raises(NotLinkedError):
                resolve_client(None)
        default_client.api.assert_not_called()

    def test_explicit_session_id_is_rejected(self, oauth_mode):
        """Passing session_id="default" must not select the service account."""
        with patch("src.session.get_access_token", return_value=_token("auth0|bas")):
            with pytest.raises(ValueError):
                resolve_client(session.DEFAULT_SESSION_ID)
        oauth_mode.get_client_sync.assert_not_called()

    def test_missing_access_token_is_refused(self, oauth_mode):
        with patch("src.session.get_access_token", return_value=None):
            with pytest.raises(PermissionError):
                resolve_client(None)

    def test_401_unlinks_and_reports_link_url(self, oauth_mode):
        with patch("src.session.get_access_token", return_value=_token("auth0|bas")):
            with pytest.raises(NotLinkedError) as exc:
                execute_taiga_operation("op", lambda: (_ for _ in ()).throw(_auth_error(401)))
        oauth_mode.handle_taiga_auth_failure.assert_called_once_with("auth0|bas")
        assert "link-account" in str(exc.value)

    def test_403_does_not_unlink(self, oauth_mode):
        """Taiga maps 401 and 403 to the same exception class; only 401 means a dead token."""
        with patch("src.session.get_access_token", return_value=_token("auth0|bas")):
            with pytest.raises(TaigaAuthenticationError):
                execute_taiga_operation("op", lambda: (_ for _ in ()).throw(_auth_error(403)))
        oauth_mode.handle_taiga_auth_failure.assert_not_called()
