"""Unit tests for the search tool."""

from unittest.mock import MagicMock

import pytest

import src.tools.search_tools as search_tools

SEARCH_RESPONSE = {
    "userstories": [
        {
            "id": 11,
            "ref": 4,
            "subject": "Login pagina",
            "status": 2,
            "status_extra_info": {"name": "In progress", "color": "#fff"},
            "total_points": 3.0,
            "milestone_slug": "sprint-1",
        }
    ],
    "tasks": [{"id": 22, "ref": 9, "subject": "Login knop", "status": 5, "assigned_to": 1}],
    "issues": [],
    "epics": [{"id": 33, "ref": 1, "subject": "Login", "status": 7, "color": "#000"}],
    "wikipages": [{"id": 44, "slug": "login-flow", "content": "long text"}],
    "count": 4,
}


def _fake_client(response):
    client = MagicMock()
    client.api.get.return_value = response
    return client


def test_search_calls_taiga_search_endpoint(monkeypatch):
    client = _fake_client(SEARCH_RESPONSE)
    monkeypatch.setattr(search_tools, "resolve_client", lambda session_id=None: client)

    search_tools.search(project_id=7, text="login")

    client.api.get.assert_called_once_with("/search", params={"project": 7, "text": "login"})


def test_search_passes_session_id_to_resolve_client(monkeypatch):
    client = _fake_client(SEARCH_RESPONSE)
    seen = []

    def fake_resolve(session_id=None):
        seen.append(session_id)
        return client

    monkeypatch.setattr(search_tools, "resolve_client", fake_resolve)
    search_tools.search(project_id=7, text="login", session_id="sess-1")
    assert seen == ["sess-1"]


def test_search_trims_hits_and_keeps_grouping(monkeypatch):
    client = _fake_client(SEARCH_RESPONSE)
    monkeypatch.setattr(search_tools, "resolve_client", lambda session_id=None: client)

    result = search_tools.search(project_id=7, text="login")

    assert set(result) == {"userstories", "tasks", "issues", "epics", "wikipages", "count"}
    assert result["count"] == 4
    assert result["issues"] == []
    assert result["userstories"] == [
        {"id": 11, "ref": 4, "subject": "Login pagina", "status": 2, "status_name": "In progress"}
    ]
    assert result["tasks"] == [{"id": 22, "ref": 9, "subject": "Login knop", "status": 5}]
    assert result["epics"] == [{"id": 33, "ref": 1, "subject": "Login", "status": 7}]
    assert result["wikipages"] == [{"id": 44, "slug": "login-flow"}]


def test_search_tolerates_missing_groups(monkeypatch):
    client = _fake_client({"userstories": [{"id": 1, "ref": 2, "subject": "x"}], "count": 1})
    monkeypatch.setattr(search_tools, "resolve_client", lambda session_id=None: client)

    result = search_tools.search(project_id=7, text="x")

    assert result["userstories"] == [{"id": 1, "ref": 2, "subject": "x"}]
    assert result["tasks"] == []
    assert result["wikipages"] == []
    assert result["count"] == 1


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_search_rejects_blank_text_before_any_call(monkeypatch, text):
    called = []
    monkeypatch.setattr(
        search_tools, "resolve_client", lambda session_id=None: called.append(session_id)
    )

    with pytest.raises(ValueError):
        search_tools.search(project_id=7, text=text)
    assert called == []


def test_search_strips_surrounding_whitespace(monkeypatch):
    client = _fake_client({"count": 0})
    monkeypatch.setattr(search_tools, "resolve_client", lambda session_id=None: client)

    search_tools.search(project_id=7, text="  login ")

    client.api.get.assert_called_once_with("/search", params={"project": 7, "text": "login"})


def test_search_is_registered():
    mcp = MagicMock()
    registered = {}
    mcp.tool.side_effect = lambda name, description=None: lambda fn: registered.setdefault(name, fn)

    search_tools.register(mcp)

    assert registered["search"] is search_tools.search
