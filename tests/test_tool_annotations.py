"""Every tool tells MCP clients whether it reads, adds or changes data.

Clients use these hints to decide what to approve without asking; a tool
without them counts as destructive. The three sets below are the contract: a
new tool fails this test until it is placed in exactly one of them.
"""

import asyncio

import pytest
from mcp.server.fastmcp import FastMCP

import src.tools
from src.tools import register_all_tools


def _annotations(monkeypatch, oauth):
    monkeypatch.setattr(src.tools, "is_oauth_mode", lambda: oauth)
    server = FastMCP("annotations-test")
    register_all_tools(server)
    return {t.name: t.annotations for t in asyncio.run(server.list_tools())}


@pytest.fixture
def annotations(monkeypatch):
    """The union of both modes: stdio adds login tools, OAuth adds link tools."""
    return {**_annotations(monkeypatch, False), **_annotations(monkeypatch, True)}


READ_ONLY = {
    "get_default_session",
    "get_epic",
    "get_epic_by_ref",
    "get_issue",
    "get_issue_by_ref",
    "get_issue_priorities",
    "get_issue_severities",
    "get_issue_statuses",
    "get_issue_types",
    "get_milestone",
    "get_milestone_stats",
    "get_project",
    "get_project_by_slug",
    "get_project_members",
    "get_task",
    "get_task_by_ref",
    "get_task_statuses",
    "get_user_story",
    "get_user_story_by_ref",
    "get_user_story_statuses",
    "get_wiki_page",
    "list_all_projects",
    "list_epic_user_stories",
    "list_epics",
    "list_history",
    "list_issues",
    "list_milestones",
    "list_projects",
    "list_tasks",
    "list_user_stories",
    "list_wiki_pages",
    "search",
    "session_status",
    "taiga_link_status",
}

ADDITIVE = {
    "add_comment",
    "create_epic",
    "create_issue",
    "create_milestone",
    "create_project",
    "create_task",
    "create_user_story",
    "create_wiki_page",
    "invite_project_user",
    "link_story_to_epic",
    "login",
}

DESTRUCTIVE = {
    "assign_epic_to_user",
    "assign_issue_to_user",
    "assign_task_to_user",
    "assign_user_story_to_user",
    "delete_epic",
    "delete_issue",
    "delete_milestone",
    "delete_project",
    "delete_task",
    "delete_user_story",
    "delete_wiki_page",
    "logout",
    "taiga_unlink_account",
    "unassign_epic_from_user",
    "unassign_issue_from_user",
    "unassign_task_from_user",
    "unassign_user_story_from_user",
    "unlink_story_from_epic",
    "update_epic",
    "update_issue",
    "update_milestone",
    "update_project",
    "update_task",
    "update_user_story",
    "update_wiki_page",
}


def test_every_tool_is_classified_exactly_once(annotations):
    assert READ_ONLY | ADDITIVE | DESTRUCTIVE == set(annotations)
    assert not READ_ONLY & ADDITIVE
    assert not READ_ONLY & DESTRUCTIVE
    assert not ADDITIVE & DESTRUCTIVE


def test_read_only_tools_say_so(annotations):
    wrong = [n for n in READ_ONLY if not (annotations[n] and annotations[n].readOnlyHint is True)]
    assert wrong == []


def test_additive_tools_write_without_destroying(annotations):
    wrong = [
        n for n in ADDITIVE
        if not (annotations[n] and annotations[n].readOnlyHint is False
                and annotations[n].destructiveHint is False)
    ]
    assert wrong == []


def test_destructive_tools_are_flagged(annotations):
    wrong = [
        n for n in DESTRUCTIVE
        if not (annotations[n] and annotations[n].readOnlyHint is False
                and annotations[n].destructiveHint is True)
    ]
    assert wrong == []


def test_no_write_promises_a_free_repeat(annotations):
    wrong = [n for n in ADDITIVE | DESTRUCTIVE if annotations[n].idempotentHint is not False]
    assert wrong == []


def test_every_tool_talks_to_one_fixed_system(annotations):
    wrong = [n for n, a in annotations.items() if not (a and a.openWorldHint is False)]
    assert wrong == []
