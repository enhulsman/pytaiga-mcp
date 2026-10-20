"""Direct contracts for response filtering and kwargs validation."""

import pytest

from src.response_filter import filter_response, validate_kwargs


@pytest.mark.parametrize(
    "resource_type, kwargs, expected",
    [
        ("project", {"name": "Demo", "is_private": False}, {"name": "Demo", "is_private": False}),
        ("task", {"status": 2, "version": 99, "unknown": True}, {"status": 2}),
        ("issue", {"unknown": True}, {}),
        ("user_story", {"tags": [["ui", "blue"], ["api"]]}, {"tags": [["ui", "blue"], ["api"]]}),
        ("epic", {"description": None, "watchers": []}, {"description": None, "watchers": []}),
        ("milestone", {"name": "Sprint", "order": 0}, {"name": "Sprint", "order": 0}),
        ("wiki_page", {"content": "Notes", "watchers": [1]}, {"content": "Notes", "watchers": [1]}),
        ("task", {}, {}),
        ("unknown_resource", {"custom": [[1], []]}, {"custom": [[1], []]}),
    ],
)
def test_validate_kwargs_returns_exact_allowed_values(resource_type, kwargs, expected):
    original = kwargs.copy()

    assert validate_kwargs(resource_type, kwargs) == expected
    assert kwargs == original


def test_validate_kwargs_logs_stripped_keys(caplog):
    assert validate_kwargs("task", {"status": 2, "unexpected": 3}) == {"status": 2}
    assert "Stripping unexpected kwargs for task" in caplog.text
    assert "unexpected" in caplog.text


def test_validate_kwargs_strict_rejects_unexpected_fields():
    with pytest.raises(ValueError, match="Unexpected kwargs for task"):
        validate_kwargs("task", {"status": 2, "unexpected": 3}, strict=True)


@pytest.mark.parametrize("kwargs", [{}, {"status": 0, "tags": []}])
def test_validate_kwargs_strict_accepts_allowed_or_empty_values(kwargs):
    assert validate_kwargs("task", kwargs, strict=True) == kwargs


@pytest.mark.parametrize("strict", [False, True])
def test_validate_kwargs_unknown_resource_passes_through_with_warning(caplog, strict):
    assert validate_kwargs("unknown", {"custom": [1]}, strict=strict) == {"custom": [1]}
    assert "No kwargs allowlist defined for resource type 'unknown'" in caplog.text


@pytest.mark.parametrize(
    "resource_type, payload, expected",
    [
        (
            "project",
            {"id": 1, "name": "Demo", "slug": "demo", "description": "Long"},
            {"id": 1, "name": "Demo", "slug": "demo"},
        ),
        (
            "user_story",
            {"id": 1, "ref": 2, "subject": "Story", "status": 3, "project": 4, "version": 5},
            {"id": 1, "ref": 2, "subject": "Story", "status": 3, "project": 4},
        ),
        (
            "task",
            {"id": 1, "ref": 2, "subject": "Task", "status": 3, "project": 4, "version": 5},
            {"id": 1, "ref": 2, "subject": "Task", "status": 3, "project": 4},
        ),
        (
            "issue",
            {
                "id": 1,
                "ref": 2,
                "subject": "Issue",
                "status": 3,
                "priority": 4,
                "severity": 5,
                "project": 6,
                "version": 7,
            },
            {
                "id": 1,
                "ref": 2,
                "subject": "Issue",
                "status": 3,
                "priority": 4,
                "severity": 5,
                "project": 6,
            },
        ),
        (
            "epic",
            {"id": 1, "ref": 2, "subject": "Epic", "status": 3, "project": 4, "color": "blue"},
            {"id": 1, "ref": 2, "subject": "Epic", "status": 3, "project": 4},
        ),
        (
            "milestone",
            {"id": 1, "name": "Sprint", "slug": "sprint", "project": 2, "closed": False},
            {"id": 1, "name": "Sprint", "slug": "sprint", "project": 2},
        ),
        (
            "member",
            {"id": 1, "user": 2, "full_name": "Test User", "email": "test@example.invalid"},
            {"id": 1, "user": 2, "full_name": "Test User"},
        ),
        (
            "wiki_page",
            {"id": 1, "slug": "notes", "project": 2, "content": "Long"},
            {"id": 1, "slug": "notes", "project": 2},
        ),
        (
            "milestone_stats",
            {"total_points": 10, "completed_points": 0, "total_tasks": 3},
            {"total_points": 10, "completed_points": 0},
        ),
        (
            "epic_related_user_story",
            {"epic": 1, "user_story": 2, "order": 0, "extra": True},
            {"epic": 1, "user_story": 2, "order": 0},
        ),
        (
            "history_entry",
            {
                "id": 1,
                "type": 2,
                "key": "k",
                "comment": "Hi",
                "user": {"pk": 3},
                "created_at": "today",
                "diff": [[1, 2]],
            },
            {
                "id": 1,
                "type": 2,
                "key": "k",
                "comment": "Hi",
                "user": {"pk": 3},
                "created_at": "today",
            },
        ),
    ],
)
def test_filter_response_minimal_fields(resource_type, payload, expected):
    assert filter_response(payload, resource_type, "minimal") == expected


def test_filter_response_standard_retains_version_and_nested_values():
    payload = {
        "id": 1,
        "version": 0,
        "tags": [["ui", "blue"], []],
        "assigned_to_extra_info": {"id": 2, "name": "Test User", "extra": [1, 2]},
        "unknown": "remove",
    }

    assert filter_response(payload, "task") == {
        "id": 1,
        "version": 0,
        "tags": [["ui", "blue"], []],
        "assigned_to_extra_info": {"id": 2, "name": "Test User", "extra": [1, 2]},
    }
    assert payload["unknown"] == "remove"


@pytest.mark.parametrize("verbosity", ["minimal", "standard", "full"])
@pytest.mark.parametrize("payload", [None, {}, []])
def test_filter_response_empty_payloads(payload, verbosity):
    assert filter_response(payload, "task", verbosity) == payload


def test_filter_response_list_handles_missing_keys_and_nested_lists():
    payload = [{"id": 1, "tags": [["ui"], []], "unknown": 2}, {}, {"unknown": 3}]

    assert filter_response(payload, "task") == [{"id": 1, "tags": [["ui"], []]}, {}, {}]
    assert payload == [{"id": 1, "tags": [["ui"], []], "unknown": 2}, {}, {"unknown": 3}]


@pytest.mark.parametrize("payload", [{"custom": [[1], []]}, [{"custom": [[1], []]}]])
def test_filter_response_unknown_resource_keeps_payload(payload):
    assert filter_response(payload, "unknown") == payload


@pytest.mark.parametrize("payload", [{"id": 1, "custom": [[1]]}, [{"custom": [[1]]}]])
def test_filter_response_full_keeps_all_fields(payload):
    assert filter_response(payload, "task", "full") == payload


def test_filter_response_invalid_verbosity_uses_standard(caplog):
    assert filter_response({"id": 1, "version": 2, "unknown": 3}, "task", "invalid") == {
        "id": 1,
        "version": 2,
    }
    assert "Invalid verbosity 'invalid', using 'standard'" in caplog.text
