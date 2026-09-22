"""Structural guard: every core tool module resolves its client through
src.session.resolve_client, never through the stdio-only helpers."""

import inspect
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "src" / "tools"
CORE_MODULES = sorted(
    p for p in TOOLS_DIR.glob("*_tools.py") if p.name not in {"auth_tools.py", "oauth_tools.py", "search_tools.py"}  # search_tools is an empty placeholder
)


@pytest.mark.parametrize("module_path", CORE_MODULES, ids=lambda p: p.stem)
def test_core_tools_do_not_use_stdio_helpers(module_path):
    source = module_path.read_text()
    assert "get_session_id" not in source, f"{module_path.name} still calls get_session_id"
    assert "get_authenticated_client" not in source, f"{module_path.name} still calls get_authenticated_client"
    assert "resolve_client" in source, f"{module_path.name} does not use resolve_client"


def test_core_module_list_is_not_empty():
    assert len(CORE_MODULES) >= 9


def test_tools_pass_caller_session_id_when_delegating():
    """A tool delegating to a sibling passes the caller's session_id through unchanged.
    Passing a resolved id would trip the OAuth-mode rejection of explicit session ids."""
    for module_path in CORE_MODULES:
        assert "actual_session_id" not in module_path.read_text(), module_path.name


def test_representative_tools_call_resolve_client(monkeypatch):
    from unittest.mock import MagicMock

    import src.tools.issue_tools as issue_tools

    client = MagicMock()
    client.api.issues.list.return_value = []
    seen = []

    def fake_resolve(session_id=None):
        seen.append(session_id)
        return client

    monkeypatch.setattr(issue_tools, "resolve_client", fake_resolve)
    issue_tools.list_issues(project_id=1)
    issue_tools.assign_issue_to_user(issue_id=7, user_id=3, session_id="sess-1")
    # list_issues resolved with None; assign delegates to update_issue with the caller's id
    assert seen[0] is None
    assert all(s == "sess-1" for s in seen[1:])
    assert len(seen) >= 2
