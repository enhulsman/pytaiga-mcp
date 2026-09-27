"""Unit tests for the get_*_by_ref tools."""

from unittest.mock import MagicMock

import pytest

import src.tools.epic_tools as epic_tools
import src.tools.issue_tools as issue_tools
import src.tools.task_tools as task_tools
import src.tools.userstory_tools as userstory_tools

CASES = [
    (userstory_tools, "get_user_story_by_ref", "/userstories/by_ref", "user_story"),
    (task_tools, "get_task_by_ref", "/tasks/by_ref", "task"),
    (issue_tools, "get_issue_by_ref", "/issues/by_ref", "issue"),
    (epic_tools, "get_epic_by_ref", "/epics/by_ref", "epic"),
]


@pytest.mark.parametrize("module, tool_name, endpoint, resource_type", CASES, ids=[c[1] for c in CASES])
def test_by_ref_calls_raw_endpoint_with_ref_and_project(
    monkeypatch, module, tool_name, endpoint, resource_type
):
    client = MagicMock()
    client.api.get.return_value = {"id": 99, "ref": 12, "subject": "x"}
    monkeypatch.setattr(module, "resolve_client", lambda session_id=None: client)

    getattr(module, tool_name)(project_id=5, ref=12)

    client.api.get.assert_called_once_with(endpoint, params={"ref": 12, "project": 5})


@pytest.mark.parametrize("module, tool_name, endpoint, resource_type", CASES, ids=[c[1] for c in CASES])
def test_by_ref_passes_session_id_to_resolve_client(
    monkeypatch, module, tool_name, endpoint, resource_type
):
    client = MagicMock()
    client.api.get.return_value = {"id": 99, "ref": 12, "subject": "x"}
    seen = []

    def fake_resolve(session_id=None):
        seen.append(session_id)
        return client

    monkeypatch.setattr(module, "resolve_client", fake_resolve)
    getattr(module, tool_name)(project_id=5, ref=12, session_id="sess-9")
    assert seen == ["sess-9"]


@pytest.mark.parametrize("module, tool_name, endpoint, resource_type", CASES, ids=[c[1] for c in CASES])
def test_by_ref_filters_response_with_given_verbosity(
    monkeypatch, module, tool_name, endpoint, resource_type
):
    raw = {"id": 99, "ref": 12, "subject": "x"}
    client = MagicMock()
    client.api.get.return_value = raw
    monkeypatch.setattr(module, "resolve_client", lambda session_id=None: client)
    calls = []

    def fake_filter(response, rtype, verbosity="standard"):
        calls.append((response, rtype, verbosity))
        return {"filtered": True}

    monkeypatch.setattr(module, "filter_response", fake_filter)

    result = getattr(module, tool_name)(project_id=5, ref=12, verbosity="minimal")

    assert result == {"filtered": True}
    assert calls == [(raw, resource_type, "minimal")]


@pytest.mark.parametrize("module, tool_name, endpoint, resource_type", CASES, ids=[c[1] for c in CASES])
def test_by_ref_defaults_to_standard_verbosity(
    monkeypatch, module, tool_name, endpoint, resource_type
):
    client = MagicMock()
    client.api.get.return_value = {"id": 99, "ref": 12, "subject": "x"}
    monkeypatch.setattr(module, "resolve_client", lambda session_id=None: client)
    calls = []
    monkeypatch.setattr(
        module, "filter_response", lambda r, t, v="standard": calls.append(v) or r
    )

    getattr(module, tool_name)(project_id=5, ref=12)

    assert calls == ["standard"]


@pytest.mark.parametrize("module, tool_name, endpoint, resource_type", CASES, ids=[c[1] for c in CASES])
def test_by_ref_is_registered_with_ref_guidance(module, tool_name, endpoint, resource_type):
    mcp = MagicMock()
    registered = {}

    def tool(name, description=None):
        registered[name] = description
        return lambda fn: fn

    mcp.tool.side_effect = tool
    module.register(mcp)

    assert tool_name in registered
    description = registered[tool_name]
    assert "#" in description, "description must explain ref is the #N number from the Taiga UI"
    id_tool = tool_name.replace("_by_ref", "")
    assert id_tool in description, "description must point to the id-based tool"
