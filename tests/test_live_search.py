"""Live checks for search and get-by-ref against a real Taiga instance.

Opt in with TAIGA_LIVE=1; the credentials come from the application's own
settings (TAIGA_API_URL, TAIGA_USERNAME, TAIGA_PASSWORD). Read-only: the tests
only list, search and fetch. Run:

    TAIGA_LIVE=1 uv run --extra dev python -m pytest tests/test_live_search.py -m live -v
"""

import os

import pytest

pytestmark = pytest.mark.live

if os.environ.get("TAIGA_LIVE") != "1":
    pytest.skip("set TAIGA_LIVE=1 to run against a real Taiga", allow_module_level=True)

from src.config import settings  # noqa: E402
from src.taiga_client import TaigaClientWrapper  # noqa: E402
from src.tools import (  # noqa: E402
    epic_tools,
    issue_tools,
    search_tools,
    task_tools,
    userstory_tools,
)

COLLECTIONS = {
    "user_stories": (userstory_tools, "get_user_story_by_ref"),
    "tasks": (task_tools, "get_task_by_ref"),
    "issues": (issue_tools, "get_issue_by_ref"),
    "epics": (epic_tools, "get_epic_by_ref"),
}


@pytest.fixture(scope="module")
def live_client():
    if not (settings.username and settings.password):
        pytest.skip("TAIGA_USERNAME/TAIGA_PASSWORD not configured")
    wrapper = TaigaClientWrapper(settings.host)
    wrapper.login(
        settings.username.get_secret_value(), settings.password.get_secret_value()
    )
    return wrapper


@pytest.fixture(scope="module")
def project_id(live_client):
    projects = live_client.api.projects.list()
    for project in projects:
        if live_client.api.user_stories.list(project=project["id"]):
            return project["id"]
    pytest.skip("no project with user stories for this account")


@pytest.fixture(autouse=True)
def use_live_client(monkeypatch, live_client):
    for module in (userstory_tools, task_tools, issue_tools, epic_tools, search_tools):
        monkeypatch.setattr(module, "resolve_client", lambda session_id=None: live_client)


def _first_item(live_client, collection, project_id):
    if collection == "user_stories":
        items = live_client.api.user_stories.list(project=project_id)
    elif collection == "tasks":
        # pytaigaclient's Tasks resource is unusable (see test_library_task_helper_is_broken)
        items = live_client.api.get("/tasks", params={"project": project_id})
    else:
        items = getattr(live_client.api, collection).list(query_params={"project": project_id})
    if not items:
        pytest.skip(f"project {project_id} has no {collection}")
    return items[0]


@pytest.mark.parametrize("collection", list(COLLECTIONS))
def test_get_by_ref_returns_the_same_item_as_list(live_client, project_id, collection):
    module, tool_name = COLLECTIONS[collection]
    item = _first_item(live_client, collection, project_id)
    result = getattr(module, tool_name)(project_id, item["ref"])
    assert result["id"] == item["id"]
    assert result["ref"] == item["ref"]
    assert result["subject"] == item["subject"]


def test_search_finds_a_known_story_by_a_word_from_its_subject(live_client, project_id):
    story = _first_item(live_client, "user_stories", project_id)
    word = max(story["subject"].split(), key=len)
    result = search_tools.search(project_id, word)
    assert set(result) == {"userstories", "tasks", "issues", "epics", "wikipages", "count"}
    refs = {hit["ref"] for hit in result["userstories"]}
    assert story["ref"] in refs
    hit = next(h for h in result["userstories"] if h["ref"] == story["ref"])
    assert set(hit) <= {"id", "ref", "subject", "slug", "status", "status_name"}
    assert isinstance(result["count"], int)


def test_library_task_helper_is_broken(live_client, project_id):
    """Documents why the tools call the raw endpoint: pytaigaclient's Tasks.get_by_ref
    passes `query_params=` to a client method that only accepts `params=`."""
    task = _first_item(live_client, "tasks", project_id)
    with pytest.raises(TypeError, match="query_params"):
        live_client.api.tasks.get_by_ref(ref=task["ref"], project=project_id)
