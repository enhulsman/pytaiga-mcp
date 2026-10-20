"""History tool contracts using a fake client, without Taiga calls."""

from copy import deepcopy
from unittest.mock import MagicMock, call

import pytest
from pytaigaclient.exceptions import TaigaException

from src.tools import history_tools

HISTORY_TYPES = [
    ("userstory", "userstories"),
    ("task", "tasks"),
    ("issue", "issues"),
    ("epic", "epics"),
    ("wiki", "wiki"),
]


@pytest.fixture
def client(monkeypatch):
    fake = MagicMock()
    resolver = MagicMock(return_value=fake)
    monkeypatch.setattr(history_tools, "resolve_client", resolver)
    return fake, resolver


@pytest.mark.parametrize("object_type, endpoint", HISTORY_TYPES)
def test_list_history_uses_endpoint_and_session(client, object_type, endpoint):
    fake, resolver = client
    fake.api.get.return_value = [
        {
            "id": 1,
            "comment": "Hello",
            "user": {"pk": 2, "name": "Test User", "extra": 3},
            "diff": [["old", "new"]],
            "is_hidden": False,
            "extra": "remove",
        }
    ]

    assert history_tools.list_history(object_type, 42, session_id="test-session") == [
        {
            "id": 1,
            "comment": "Hello",
            "user": {"id": 2, "name": "Test User"},
            "diff": [["old", "new"]],
            "is_hidden": False,
        }
    ]
    resolver.assert_called_once_with("test-session")
    fake.api.get.assert_called_once_with(f"/history/{object_type}/42")


@pytest.mark.parametrize(
    "verbosity, expected",
    [
        ("minimal", [{"id": 1, "comment": "Hi", "user": {"id": 2, "name": "Test User"}}]),
        (
            "standard",
            [{"id": 1, "comment": "Hi", "user": {"id": 2, "name": "Test User"}, "diff": [[1, 2]]}],
        ),
        (
            "full",
            [
                {
                    "id": 1,
                    "comment": "Hi",
                    "user": {"pk": 2, "name": "Test User", "extra": 3},
                    "diff": [[1, 2]],
                    "extra": 4,
                }
            ],
        ),
    ],
)
def test_list_history_verbosity(client, verbosity, expected):
    fake, resolver = client
    payload = [
        {
            "id": 1,
            "comment": "Hi",
            "user": {"pk": 2, "name": "Test User", "extra": 3},
            "diff": [[1, 2]],
            "extra": 4,
        }
    ]
    fake.api.get.return_value = deepcopy(payload)

    assert history_tools.list_history("task", 42, verbosity=verbosity) == expected
    assert fake.api.get.return_value == payload
    resolver.assert_called_once_with(None)


@pytest.mark.parametrize(
    "payload, expected",
    [
        ([], []),
        (None, None),
        (
            [{}, {"user": None}, {"user": 3}, {"user": {}}],
            [{}, {"user": None}, {"user": 3}, {"user": {"id": None, "name": None}}],
        ),
    ],
)
def test_list_history_empty_and_missing_fields(client, payload, expected):
    fake, _ = client
    fake.api.get.return_value = payload

    assert history_tools.list_history("task", 42) == expected


def test_list_history_propagates_taiga_error(client):
    fake, _ = client
    error = TaigaException("fake history failure")
    fake.api.get.side_effect = error

    with pytest.raises(TaigaException) as caught:
        history_tools.list_history("task", 42)

    assert caught.value is error
    fake.api.get.assert_called_once_with("/history/task/42")


@pytest.mark.parametrize("object_type, endpoint", HISTORY_TYPES)
def test_add_comment_fetches_version_then_patches(client, object_type, endpoint):
    fake, resolver = client
    fake.api.get.return_value = {"version": 0}
    fake.api.patch.return_value = {"version": 1}

    assert history_tools.add_comment(object_type, 42, "  Hello\n", "test-session") == {
        "status": "comment_added",
        "object_type": object_type,
        "object_id": 42,
        "comment": "Hello",
        "new_version": 1,
    }
    resolver.assert_called_once_with("test-session")
    assert fake.api.mock_calls == [
        call.get(f"/{endpoint}/42"),
        call.patch(f"/{endpoint}/42", json={"comment": "Hello", "version": 0}),
    ]


@pytest.mark.parametrize("operation", ["get", "patch"])
def test_add_comment_propagates_taiga_error(client, operation):
    fake, resolver = client
    fake.api.get.return_value = {"version": 3}
    error = TaigaException("fake comment failure")
    getattr(fake.api, operation).side_effect = error

    with pytest.raises(TaigaException) as caught:
        history_tools.add_comment("task", 42, "Hello")

    assert caught.value is error
    resolver.assert_called_once_with(None)
    fake.api.get.assert_called_once_with("/tasks/42")
    if operation == "get":
        fake.api.patch.assert_not_called()
    else:
        fake.api.patch.assert_called_once_with("/tasks/42", json={"comment": "Hello", "version": 3})


@pytest.mark.parametrize("payload", [{}, {"version": None}])
def test_add_comment_missing_version_does_not_patch(client, payload):
    fake, _ = client
    fake.api.get.return_value = payload

    with pytest.raises(RuntimeError, match="Could not get version for task/42"):
        history_tools.add_comment("task", 42, "Hello")

    fake.api.patch.assert_not_called()


@pytest.mark.parametrize("comment", ["", " ", "\n\t"])
def test_add_comment_rejects_blank_before_resolving(client, comment):
    fake, resolver = client

    with pytest.raises(ValueError, match="Comment cannot be empty"):
        history_tools.add_comment("task", 42, comment)

    resolver.assert_not_called()
    assert fake.api.mock_calls == []


@pytest.mark.parametrize("tool", [history_tools.list_history, history_tools.add_comment])
def test_history_tools_reject_invalid_type_before_resolving(client, tool):
    fake, resolver = client
    args = ("invalid", 42, "Hello") if tool is history_tools.add_comment else ("invalid", 42)

    with pytest.raises(ValueError, match="Invalid object_type 'invalid'"):
        tool(*args)

    resolver.assert_not_called()
    assert fake.api.mock_calls == []


def test_register_exposes_both_tools():
    mcp = MagicMock()
    registered = {}
    mcp.tool.side_effect = lambda name, **_: lambda function: registered.setdefault(name, function)

    history_tools.register(mcp)

    assert registered == {
        "list_history": history_tools.list_history,
        "add_comment": history_tools.add_comment,
    }
