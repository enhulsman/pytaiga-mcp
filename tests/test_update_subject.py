"""Unit tests for renaming work items without contacting Taiga."""

from unittest.mock import MagicMock

import pytest

from src.tools import epic_tools, issue_tools, task_tools, userstory_tools

CASES = [
    (userstory_tools, "user_story", "user_stories", False),
    (task_tools, "task", "tasks", True),
    (issue_tools, "issue", "issues", True),
    (epic_tools, "epic", "epics", False),
]


@pytest.fixture(params=CASES, ids=[case[1] for case in CASES])
def resource(request, monkeypatch):
    module, name, collection, uses_data = request.param
    client = MagicMock()
    api = getattr(client.api, collection)
    api.get.return_value = {"id": 99, "subject": "Old title", "version": 7}
    api.edit.return_value = {"id": 99, "subject": "New title", "version": 8}
    resolve = MagicMock(return_value=client)
    monkeypatch.setattr(module, "resolve_client", resolve)
    return module, name, uses_data, client, api, resolve


@pytest.mark.parametrize("subject", ["Nieuwe titel", "  New  title\n ", "x" * 1000])
def test_update_passes_subject_to_edit(resource, subject):
    module, name, uses_data, _, api, _ = resource
    fields = {"subject": subject}

    getattr(module, f"update_{name}")(99, kwargs=fields)

    expected = {f"{name}_id": 99, "version": 7}
    expected.update({"data": fields} if uses_data else fields)
    api.get.assert_called_once_with(99)
    api.edit.assert_called_once_with(**expected)
    assert fields == {"subject": subject}


def test_update_keeps_version(resource):
    module, name, _, _, api, _ = resource
    api.get.return_value["version"] = 23

    getattr(module, f"update_{name}")(99, kwargs={"subject": "Nieuwe titel"})

    api.edit.assert_called_once()
    assert api.edit.call_args.kwargs["version"] == 23


@pytest.mark.parametrize("subject", ["", " ", "\t\n", "\u2003", None, 12])
def test_update_rejects_blank_subject_without_api_call(resource, subject):
    module, name, _, client, _, resolve = resource

    with pytest.raises(ValueError, match="subject"):
        getattr(module, f"update_{name}")(99, kwargs={"subject": subject})

    resolve.assert_not_called()
    assert client.mock_calls == []


@pytest.mark.parametrize("duplicate", ["Other title", "", None])
def test_create_rejects_subject_in_kwargs_without_api_call(resource, duplicate):
    module, name, _, client, _, resolve = resource
    required = {}
    if name == "issue":
        required = {"priority_id": 1, "status_id": 2, "severity_id": 3, "type_id": 4}

    with pytest.raises(ValueError, match="subject"):
        getattr(module, f"create_{name}")(
            project_id=5, subject="Explicit title", kwargs={"subject": duplicate}, **required
        )

    resolve.assert_not_called()
    assert client.mock_calls == []


@pytest.mark.parametrize("fields", [{"foo": 1}, {"foo": 1, "description": "Details"}])
def test_other_unknown_kwargs_still_stripped(resource, fields):
    module, name, uses_data, _, api, _ = resource

    getattr(module, f"update_{name}")(99, kwargs=fields)

    api.get.assert_called_once_with(99)
    if "description" in fields:
        expected = {f"{name}_id": 99, "version": 7}
        valid = {"description": "Details"}
        expected.update({"data": valid} if uses_data else valid)
        api.edit.assert_called_once_with(**expected)
    else:
        api.edit.assert_not_called()
