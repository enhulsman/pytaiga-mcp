"""Synthetic regression tests for the stdio default session's token lifetime."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from pytaigaclient import TaigaClient as RealTaigaClient
from pytaigaclient.exceptions import (
    TaigaAuthenticationError,
    TaigaException,
    TaigaRateLimitError,
    TaigaServerError,
)

import src.session as session
import src.taiga_client as clients
from src.tools import auth_tools

USERNAME = "synthetic-user"
PASSWORD = "synthetic-password"


def auth_error(status=401):
    response = Mock()
    response.json.return_value = {"_error_message": "denied"}
    response.text = "denied"
    return TaigaAuthenticationError(status, response)


@pytest.fixture
def isolated_sessions():
    # Tool modules import this dictionary directly, so preserve its identity.
    saved = dict(session.active_sessions)
    session.active_sessions.clear()
    try:
        yield
    finally:
        session.active_sessions.clear()
        session.active_sessions.update(saved)


@pytest.fixture
def env(monkeypatch, isolated_sessions):
    clock = SimpleNamespace(now=100.0)
    state = SimpleNamespace(logins=[], calls=[], outcomes=[], login_error=None)

    class FakeTaigaClient:
        def __init__(self, host, **kwargs):
            self.auth_token = kwargs.get("auth_token")
            self.auth = SimpleNamespace(login=self.login)
            self.projects = SimpleNamespace(list=lambda: self._request("GET", "projects"))
            self.users = SimpleNamespace(get_me=lambda: self._request("GET", "users/me"))

        def login(self, username, password):
            state.logins.append((username, password))
            if state.login_error:
                raise state.login_error
            self.auth_token = "synthetic-token"

        def _request(self, *args, **kwargs):
            state.calls.append((args, kwargs))
            outcome = state.outcomes.pop(0) if state.outcomes else [{"id": 1}]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(clients, "TaigaClient", FakeTaigaClient)
    # raising=False lets the initial tests run against the pre-fix wrapper.
    monkeypatch.setattr(clients, "monotonic", lambda: clock.now, raising=False)
    monkeypatch.setattr(session, "_oauth_bridge", None)
    monkeypatch.setattr(
        session,
        "settings",
        SimpleNamespace(
            transport="stdio",
            host="https://taiga.test",
            has_credentials=True,
            get_username_value=lambda: USERNAME,
            get_password_value=lambda: PASSWORD,
        ),
    )
    monkeypatch.delenv("TAIGA_RELOGIN_MAX_AGE_SECONDS", raising=False)
    wrapper = clients.TaigaClientWrapper(session.settings.host)
    wrapper.login(USERNAME, PASSWORD)
    session.active_sessions[session.DEFAULT_SESSION_ID] = wrapper
    return SimpleNamespace(clock=clock, state=state, wrapper=wrapper)


def test_young_token_is_reused(env):
    env.clock.now += 23 * 3600 - 1
    assert session.resolve_client() is env.wrapper
    assert len(env.state.logins) == 1
    assert env.wrapper.logged_in_at == 100.0


def test_old_token_relogs_once(env):
    env.clock.now += 23 * 3600 + 1
    assert session.resolve_client() is env.wrapper
    session.resolve_client()
    assert len(env.state.logins) == 2
    assert env.wrapper.logged_in_at == env.clock.now


def test_age_limit_is_configurable(env, monkeypatch):
    monkeypatch.setenv("TAIGA_RELOGIN_MAX_AGE_SECONDS", "10")
    env.clock.now += 11
    session.resolve_client()
    assert len(env.state.logins) == 2


def test_401_relogs_and_retries_exact_call_once(env):
    env.state.outcomes = [auth_error(), [{"id": 2}]]
    client = session.resolve_client()
    assert client.api.projects.list() == [{"id": 2}]
    assert len(env.state.logins) == 2
    assert env.state.calls == [(("GET", "projects"), {}), (("GET", "projects"), {})]


def test_second_401_is_raised(env):
    second = auth_error()
    env.state.outcomes = [auth_error(), second]
    with pytest.raises(TaigaAuthenticationError) as raised:
        session.resolve_client().api.projects.list()
    assert raised.value is second
    assert len(env.state.logins) == 2
    assert len(env.state.calls) == 2


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("offline"),
        requests.Timeout("timed out"),
        TaigaServerError(503, Mock(json=lambda: {"_error_message": "unavailable"})),
        TaigaException("Request failed: offline"),
    ],
)
def test_status_401_transient_relogin_failure_later_recovers(env, error):
    old_api = env.wrapper.api
    env.state.outcomes = [auth_error()]
    env.state.login_error = error

    assert auth_tools.session_status() == {
        "status": "error",
        "reason": "check_failed",
        "session_id": session.DEFAULT_SESSION_ID,
    }
    assert session.active_sessions[session.DEFAULT_SESSION_ID] is env.wrapper
    assert env.wrapper.api is old_api
    assert session.resolve_client() is env.wrapper
    assert env.wrapper._can_relogin()
    assert len(env.state.logins) == 2
    assert len(env.state.calls) == 1

    env.state.login_error = None
    env.state.outcomes = [auth_error(), {"username": USERNAME}]
    assert auth_tools.session_status() == {
        "status": "active",
        "session_id": session.DEFAULT_SESSION_ID,
        "username": USERNAME,
    }
    assert len(env.state.logins) == 3
    assert len(env.state.calls) == 3
    assert env.wrapper.api is not old_api
    assert session.resolve_client() is env.wrapper


@pytest.mark.parametrize("status", [401, 403])
def test_status_rejected_relogin_invalidates_session(env, status):
    env.state.outcomes = [auth_error()]
    env.state.login_error = auth_error(status)

    assert auth_tools.session_status() == {
        "status": "inactive",
        "reason": "token_invalid",
        "session_id": session.DEFAULT_SESSION_ID,
    }
    assert session.DEFAULT_SESSION_ID not in session.active_sessions
    assert len(env.state.logins) == 2


def test_status_second_401_invalidates_session(env):
    env.state.outcomes = [auth_error(), auth_error()]

    assert auth_tools.session_status()["reason"] == "token_invalid"
    assert session.DEFAULT_SESSION_ID not in session.active_sessions
    assert len(env.state.logins) == 2
    assert len(env.state.calls) == 2


@pytest.mark.parametrize("retry", [False, True])
@pytest.mark.parametrize("status", [429, 500, 503, 403])
def test_status_non_auth_failure_preserves_default_and_recovers(env, retry, status):
    error = (
        auth_error(403)
        if status == 403
        else (TaigaRateLimitError if status == 429 else TaigaServerError)(
            status, Mock(json=lambda: {"_error_message": "unavailable"})
        )
    )
    env.state.outcomes = ([auth_error()] if retry else []) + [error]

    assert auth_tools.session_status() == {
        "status": "error",
        "reason": "check_failed",
        "session_id": session.DEFAULT_SESSION_ID,
    }
    assert session.active_sessions[session.DEFAULT_SESSION_ID] is env.wrapper
    assert env.wrapper._can_relogin()
    assert len(env.state.logins) == (2 if retry else 1)
    assert len(env.state.calls) == (2 if retry else 1)

    env.state.outcomes = [{"username": USERNAME}]
    assert auth_tools.session_status()["status"] == "active"


@pytest.mark.parametrize("retry", [False, True])
def test_status_sdk_wrapped_timeout_preserves_default(env, monkeypatch, retry):
    api = RealTaigaClient(host=session.settings.host, auth_token="synthetic-token")
    monkeypatch.setattr(requests.Session, "request", Mock(side_effect=requests.Timeout("offline")))
    with pytest.raises(TaigaException) as raised:
        api.users.get_me()
    assert isinstance(raised.value.__cause__, requests.Timeout)
    env.state.outcomes = ([auth_error()] if retry else []) + [raised.value]

    assert auth_tools.session_status() == {
        "status": "error",
        "reason": "check_failed",
        "session_id": session.DEFAULT_SESSION_ID,
    }
    assert session.active_sessions[session.DEFAULT_SESSION_ID] is env.wrapper
    assert env.wrapper._can_relogin()
    assert len(env.state.logins) == (2 if retry else 1)
    assert len(env.state.calls) == (2 if retry else 1)


@pytest.mark.parametrize("mode", ["manual", "oauth", "http"])
@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_other_session_status_failures_keep_master_behavior(env, monkeypatch, mode, status):
    session_id = session.DEFAULT_SESSION_ID
    if mode == "manual":
        session_id = auth_tools.login(
            host=session.settings.host, username=USERNAME, password=PASSWORD
        )["session_id"]
    elif mode == "oauth":
        monkeypatch.setattr(session, "_oauth_bridge", Mock())
    else:
        session.settings.transport = "streamable-http"
    error = (
        auth_error(status)
        if status in (401, 403)
        else (TaigaRateLimitError if status == 429 else TaigaServerError)(
            status, Mock(json=lambda: {"_error_message": "unavailable"})
        )
    )
    env.state.outcomes = [error]
    login_count = len(env.state.logins)

    assert auth_tools.session_status(session_id) == {
        "status": "inactive",
        "reason": "token_invalid",
        "session_id": session_id,
    }
    assert session_id not in session.active_sessions
    assert len(env.state.logins) == login_count


def test_403_does_not_relogin(env):
    env.state.outcomes = [auth_error(403)]
    with pytest.raises(TaigaAuthenticationError):
        session.resolve_client().api.projects.list()
    assert len(env.state.logins) == 1


def test_oauth_never_relogs_or_falls_back(env, monkeypatch):
    bridge = Mock()
    bridge.get_client_sync.return_value = env.wrapper
    monkeypatch.setattr(session, "_oauth_bridge", bridge)
    monkeypatch.setattr(session, "current_oauth_sub", lambda: "synthetic-subject")
    env.clock.now += 24 * 3600
    env.state.outcomes = [auth_error()]
    with pytest.raises(TaigaAuthenticationError):
        session.resolve_client().api.projects.list()
    assert len(env.state.logins) == 1
    bridge.get_client_sync.return_value = None
    monkeypatch.setattr(session, "link_url", lambda: "https://taiga.test/link-account")
    with pytest.raises(session.NotLinkedError):
        session.resolve_client()
    assert len(env.state.logins) == 1


def test_manual_login_session_does_not_relogin(env):
    assert auth_tools.active_sessions is session.active_sessions
    manual_id = auth_tools.login(host=session.settings.host, username=USERNAME, password=PASSWORD)[
        "session_id"
    ]
    env.clock.now += 24 * 3600
    client = session.resolve_client(manual_id)
    env.state.outcomes = [auth_error()]
    with pytest.raises(TaigaAuthenticationError):
        client.api.projects.list()
    assert len(env.state.logins) == 2  # startup plus the manual login only


def test_http_without_oauth_does_not_relogin(env):
    session.settings.transport = "streamable-http"
    env.clock.now += 24 * 3600
    env.state.outcomes = [auth_error()]
    with pytest.raises(TaigaAuthenticationError):
        session.resolve_client().api.projects.list()
    assert len(env.state.logins) == 1


def test_relogin_failure_never_logs_credentials(env, caplog):
    env.clock.now += 24 * 3600
    env.state.login_error = TaigaException(f"server echoed {USERNAME} {PASSWORD}")
    with caplog.at_level(logging.INFO), pytest.raises(TaigaException):
        session.resolve_client()
    assert "re-login" in caplog.text
    assert session.settings.host in caplog.text
    assert USERNAME not in caplog.text
    assert PASSWORD not in caplog.text
    assert USERNAME not in vars(env.wrapper).values()
    assert PASSWORD not in vars(env.wrapper).values()


def test_missing_credentials_do_not_relogin(env):
    session.settings.has_credentials = False
    env.clock.now += 24 * 3600
    env.state.outcomes = [auth_error()]
    with pytest.raises(TaigaAuthenticationError):
        session.resolve_client().api.projects.list()
    assert len(env.state.logins) == 1


@pytest.mark.parametrize("trigger", ["initial", "age", "401"])
@pytest.mark.parametrize("status", [401, 503])
def test_real_sdk_auth_body_never_reaches_logs(env, monkeypatch, caplog, trigger, status):
    # Server import sets an explicit SDK threshold; exercise DEBUG even when
    # this test runs after the server tests in the full suite.
    caplog.set_level(logging.DEBUG, logger="pytaigaclient.client")
    monkeypatch.setattr(clients, "TaigaClient", RealTaigaClient)
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(
        {"_error_message": f"raw-auth-body {USERNAME} {PASSWORD}"}
    ).encode()
    request = Mock(return_value=response)
    monkeypatch.setattr(requests.Session, "request", request)
    if trigger == "age":
        env.clock.now += 24 * 3600
        operation = session.resolve_client
    elif trigger == "401":
        env.state.outcomes = [auth_error()]
        operation = env.wrapper.api.projects.list
    else:

        def operation():
            return auth_tools.login(
                host=session.settings.host, username=USERNAME, password=PASSWORD
            )

    with caplog.at_level(logging.DEBUG), pytest.raises(TaigaException):
        operation()

    request.assert_called_once()
    assert caplog.records
    for record in caplog.records:
        assert USERNAME not in record.getMessage()
        assert PASSWORD not in record.getMessage()
        assert "raw-auth-body" not in record.getMessage()
    # Suppression must end even when authentication raises.
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("pytaigaclient.client").debug("SDK logging restored")
    assert "SDK logging restored" in caplog.text


@pytest.mark.parametrize("trigger", ["age", "401"])
@pytest.mark.parametrize("error", [TaigaException("temporary outage"), RuntimeError("offline")])
def test_failed_relogin_preserves_state_and_later_recovers(env, trigger, error):
    old_api = env.wrapper.api
    old_request = env.wrapper._request_once
    old_login_time = env.wrapper.logged_in_at
    if trigger == "age":
        env.clock.now += 24 * 3600
        operation = session.resolve_client
    else:
        env.state.outcomes = [auth_error()]

        def operation():
            return session.resolve_client().api.projects.list()

    env.state.login_error = error

    with pytest.raises(TaigaException, match="re-login failed"):
        operation()

    assert env.wrapper.api is old_api
    assert env.wrapper._request_once is old_request
    assert env.wrapper.logged_in_at == old_login_time
    assert env.wrapper.is_authenticated
    assert env.wrapper._can_relogin()
    assert len(env.state.logins) == 2
    # The retained client can still use a token rejected only by the age policy.
    if trigger == "age":
        assert old_api.projects.list() == [{"id": 1}]

    env.state.login_error = None
    if trigger == "401":
        env.state.outcomes = [auth_error(), [{"id": 2}]]
        assert operation() == [{"id": 2}]
    else:
        assert operation() is env.wrapper
    assert len(env.state.logins) == 3
    assert env.wrapper.api is not old_api
    assert env.wrapper.logged_in_at == env.clock.now
    assert session.resolve_client().api.projects.list() == [{"id": 1}]
