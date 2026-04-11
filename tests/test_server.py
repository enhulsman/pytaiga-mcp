import uuid
from unittest.mock import MagicMock, patch

import pytest

# Import the server module instead of specific functions
import src.server
from src.taiga_client import TaigaClientWrapper

from pytaigaclient import TaigaClient

# Test constants
TEST_HOST = "https://your-test-taiga-instance.com"
TEST_USERNAME = "test_user"
TEST_PASSWORD = "test_password"


class TestTaigaTools:
    @pytest.fixture
    def session_setup(self):
        """Create a session setup for testing"""
        # Generate a session ID
        session_id = str(uuid.uuid4())

        # Create and return a mock client
        mock_client = MagicMock()
        mock_client.is_authenticated = True

        # Store the mock client in active_sessions
        src.server.active_sessions[session_id] = mock_client

        return session_id, mock_client

    def test_login(self):
        """Test the login functionality"""
        with patch.object(TaigaClientWrapper, "login", return_value=True):
            # Clear any existing sessions
            src.server.active_sessions.clear()

            # Call the login function
            result = src.server.login(TEST_HOST, TEST_USERNAME, TEST_PASSWORD)

            # Verify results
            assert "session_id" in result
            assert result["session_id"] in src.server.active_sessions

            # Cleanup
            src.server.active_sessions.clear()

    @patch("src.taiga_client.TaigaClient")
    def test_login_disables_pagination(self, MockTaigaClient):
        """Verify TaigaClient is created with disable_pagination=True on login."""
        mock_instance = MockTaigaClient.return_value
        mock_instance.auth.login.return_value = None
        mock_instance.auth_token = "fake-token"
        wrapper = TaigaClientWrapper(host="https://taiga.example.com")
        wrapper.login("user", "pass")
        MockTaigaClient.assert_called_with(
            host="https://taiga.example.com", disable_pagination=True
        )

    @patch("src.taiga_client.TaigaClient")
    def test_set_token_disables_pagination(self, MockTaigaClient):
        """Verify TaigaClient is created with disable_pagination=True on set_token."""
        wrapper = TaigaClientWrapper(host="https://taiga.example.com")
        wrapper.set_token("fake-token", "Bearer")
        MockTaigaClient.assert_called_with(
            host="https://taiga.example.com",
            auth_token="fake-token",
            token_type="Bearer",
            disable_pagination=True,
        )

    def test_list_projects(self, session_setup):
        """Test list_projects functionality"""
        session_id, mock_client = session_setup

        # Setup list projects return - return actual dictionaries
        mock_client.api.projects.list.return_value = [{"id": 123, "name": "Test Project"}]

        # List projects and verify
        projects = src.server.list_projects(session_id)
        assert len(projects) == 1
        assert projects[0]["name"] == "Test Project"
        assert projects[0]["id"] == 123

    def test_update_project(self, session_setup):
        """Test update_project functionality"""
        session_id, mock_client = session_setup

        # Setup get project return with version (needed for update)
        mock_client.api.projects.get.return_value = {"id": 123, "name": "Old Name", "version": 1}

        # Setup update return
        mock_client.api.projects.update.return_value = {"id": 123, "name": "New Name", "version": 2}

        # Update the project name - kwargs as dict, then session_id
        result = src.server.update_project(123, {"name": "New Name"}, session_id)

        # Verify the update was called with correct parameters
        mock_client.api.projects.update.assert_called_once_with(
            project_id=123, version=1, project_data={"name": "New Name"}
        )
        assert result["name"] == "New Name"

    def test_list_user_stories(self, session_setup):
        """Test list_user_stories functionality"""
        session_id, mock_client = session_setup

        # Setup list user stories return - return actual dictionaries
        mock_client.api.user_stories.list.return_value = [{"id": 456, "subject": "Test User Story"}]

        # List user stories and verify - filters as empty dict, then session_id
        stories = src.server.list_user_stories(123, {}, session_id)
        assert len(stories) == 1
        assert stories[0]["subject"] == "Test User Story"
        assert stories[0]["id"] == 456

        # Verify the correct project filter was used
        mock_client.api.user_stories.list.assert_called_once_with(project=123)

    def test_create_user_story(self, session_setup):
        """Test create_user_story functionality"""
        session_id, mock_client = session_setup

        # Setup create user story return - return actual dictionary
        mock_client.api.user_stories.create.return_value = {"id": 456, "subject": "New Story"}

        # Create user story and verify - kwargs as dict, then session_id
        story = src.server.create_user_story(
            123, "New Story", {"description": "Test description"}, session_id
        )
        assert story["subject"] == "New Story"
        assert story["id"] == 456

        # Verify the create was called with correct parameters
        mock_client.api.user_stories.create.assert_called_once_with(
            project=123, subject="New Story", description="Test description"
        )

    def test_list_tasks(self, session_setup):
        """Test list_tasks functionality"""
        session_id, mock_client = session_setup

        # Setup list tasks return - the code uses api.get("/tasks") instead of api.tasks.list()
        # due to a pytaigaclient bug workaround
        mock_client.api.get.return_value = [{"id": 789, "subject": "Test Task"}]

        # List tasks and verify - filters as empty dict, then session_id
        tasks = src.server.list_tasks(123, {}, session_id)
        assert len(tasks) == 1
        assert tasks[0]["subject"] == "Test Task"
        assert tasks[0]["id"] == 789

        # Verify the correct API call was made (uses get instead of tasks.list due to bug workaround)
        mock_client.api.get.assert_called_once_with("/tasks", params={"project": 123})


class TestResponseFiltering:
    """Tests for the response filtering functionality."""

    def test_filter_standard_always_includes_version(self):
        """version is required for updates in standard level."""
        # These resource types don't have version (not updateable or special stats/read-only)
        no_version_resources = {"member", "milestone_stats", "epic_related_user_story", "history_entry"}
        for resource_type, levels in src.server.RESPONSE_FIELDS.items():
            if resource_type not in no_version_resources:
                assert "version" in levels["standard"], (
                    f"{resource_type} missing version in standard"
                )

    def test_filter_minimal_includes_id(self):
        """All minimal levels must include id."""
        # These resource types don't have id (special stats or relation objects)
        no_id_resources = {"milestone_stats", "epic_related_user_story"}
        for resource_type, levels in src.server.RESPONSE_FIELDS.items():
            if resource_type not in no_id_resources:
                assert "id" in levels["minimal"], f"{resource_type} missing id in minimal"

    def test_filter_minimal_includes_project_where_applicable(self):
        """Resources with project association must include project in minimal."""
        project_resources = ["user_story", "task", "issue", "epic", "milestone", "wiki_page"]
        for resource_type in project_resources:
            assert "project" in src.server.RESPONSE_FIELDS[resource_type]["minimal"], (
                f"{resource_type} missing project in minimal"
            )

    def test_filter_response_handles_none(self):
        """_filter_response should return None when given None."""
        assert src.server._filter_response(None, "user_story") is None

    def test_filter_response_handles_empty_list(self):
        """_filter_response should return empty list when given empty list."""
        assert src.server._filter_response([], "user_story") == []

    def test_filter_response_unknown_type_returns_full(self):
        """Unknown resource types should return full response."""
        data = {"id": 1, "extra": "field"}
        assert src.server._filter_response(data, "unknown_type") == data

    def test_filter_response_full_verbosity_returns_all(self):
        """Full verbosity should return all fields."""
        data = {
            "id": 1,
            "subject": "Test",
            "version": 1,
            "watchers": [1, 2],
            "extra_field": "value",
        }
        result = src.server._filter_response(data, "user_story", verbosity="full")
        assert result == data

    def test_filter_response_standard_filters_fields(self):
        """Standard verbosity should filter to defined fields."""
        data = {
            "id": 1,
            "ref": 123,
            "subject": "Test",
            "description": "Desc",
            "status": 1,
            "version": 2,
            "watchers": [1, 2],
            "extra_internal_field": "should_be_filtered",
        }
        result = src.server._filter_response(data, "user_story", verbosity="standard")
        assert "id" in result
        assert "ref" in result
        assert "subject" in result
        assert "version" in result
        assert "watchers" not in result
        assert "extra_internal_field" not in result

    def test_filter_response_minimal_filters_to_core(self):
        """Minimal verbosity should filter to core identification fields."""
        data = {
            "id": 1,
            "ref": 123,
            "subject": "Test",
            "status": 1,
            "project": 10,
            "description": "Long description",
            "version": 2,
            "watchers": [1, 2],
        }
        result = src.server._filter_response(data, "user_story", verbosity="minimal")
        assert result == {"id": 1, "ref": 123, "subject": "Test", "status": 1, "project": 10}

    def test_filter_response_list_filters_each_item(self):
        """_filter_response should filter each item in a list."""
        data = [
            {"id": 1, "subject": "Story 1", "watchers": [1]},
            {"id": 2, "subject": "Story 2", "watchers": [2]},
        ]
        result = src.server._filter_response(data, "user_story", verbosity="minimal")
        assert len(result) == 2
        assert "watchers" not in result[0]
        assert "watchers" not in result[1]

    def test_filter_response_invalid_verbosity_falls_back_to_standard(self):
        """Typos in verbosity should warn and use standard."""
        data = {"id": 1, "subject": "Test", "version": 1, "watchers": [1, 2]}
        result = src.server._filter_response(data, "user_story", verbosity="stanard")  # typo
        assert "id" in result
        assert "version" in result
        assert "watchers" not in result


class TestExtendedTools:
    """Tests for extended tools added in Phase 1."""

    @pytest.fixture
    def session_setup(self):
        """Create a session setup for testing."""
        session_id = str(uuid.uuid4())
        mock_client = MagicMock()
        mock_client.is_authenticated = True
        src.server.active_sessions[session_id] = mock_client
        return session_id, mock_client

    def test_get_task_statuses(self, session_setup):
        """Test get_task_statuses functionality."""
        session_id, mock_client = session_setup

        # Setup mock return
        mock_client.api.get.return_value = [
            {"id": 1, "name": "New", "slug": "new"},
            {"id": 2, "name": "In progress", "slug": "in-progress"},
        ]

        # Call the function
        statuses = src.server.get_task_statuses(123, session_id)
        assert len(statuses) == 2
        assert statuses[0]["name"] == "New"

        # Verify correct API call
        mock_client.api.get.assert_called_once_with("/task-statuses", params={"project": 123})

    def test_get_milestone_stats(self, session_setup):
        """Test get_milestone_stats functionality."""
        session_id, mock_client = session_setup

        # Setup mock return
        mock_client.api.milestones.stats.return_value = {
            "total_points": 100,
            "completed_points": 75,
            "total_userstories": 10,
            "completed_userstories": 7,
        }

        # Call the function
        stats = src.server.get_milestone_stats(456, session_id)
        assert stats["total_points"] == 100
        assert stats["completed_points"] == 75

        # Verify correct API call
        mock_client.api.milestones.stats.assert_called_once_with(456)

    def test_create_wiki_page(self, session_setup):
        """Test create_wiki_page functionality."""
        session_id, mock_client = session_setup

        # Setup mock return
        mock_client.api.wiki.create.return_value = {
            "id": 1,
            "slug": "test-page",
            "content": "Test content",
            "project": 123,
        }

        # Call the function
        page = src.server.create_wiki_page(123, "test-page", "Test content", {}, session_id)
        assert page["slug"] == "test-page"
        assert page["content"] == "Test content"

        # Verify correct API call
        mock_client.api.wiki.create.assert_called_once_with(
            project=123, slug="test-page", content="Test content"
        )

    def test_update_wiki_page(self, session_setup):
        """Test update_wiki_page functionality."""
        session_id, mock_client = session_setup

        # Setup mock returns
        mock_client.api.wiki.get.return_value = {
            "id": 1,
            "slug": "test-page",
            "content": "Old content",
            "version": 1,
        }
        mock_client.api.wiki.edit.return_value = {
            "id": 1,
            "slug": "test-page",
            "content": "New content",
            "version": 2,
        }

        # Call the function
        page = src.server.update_wiki_page(1, {"content": "New content"}, session_id)
        assert page["content"] == "New content"

        # Verify correct API calls
        mock_client.api.wiki.edit.assert_called_once_with(
            wiki_page_id=1, version=1, data={"content": "New content"}
        )

    def test_delete_wiki_page(self, session_setup):
        """Test delete_wiki_page functionality."""
        session_id, mock_client = session_setup

        # Setup mock
        mock_client.api.wiki.delete.return_value = None

        # Call the function
        result = src.server.delete_wiki_page(1, session_id)
        assert result["status"] == "deleted"
        assert result["wiki_page_id"] == 1

        # Verify correct API call
        mock_client.api.wiki.delete.assert_called_once_with(wiki_page_id=1)

    def test_list_epic_user_stories(self, session_setup):
        """Test list_epic_user_stories functionality."""
        session_id, mock_client = session_setup

        # Setup mock return
        mock_client.api.epics.list_related_user_stories.return_value = [
            {"epic": 1, "user_story": 10, "order": 1},
            {"epic": 1, "user_story": 11, "order": 2},
        ]

        # Call the function
        stories = src.server.list_epic_user_stories(1, session_id)
        assert len(stories) == 2
        assert stories[0]["user_story"] == 10

        # Verify correct API call
        mock_client.api.epics.list_related_user_stories.assert_called_once_with(1)

    def test_link_story_to_epic(self, session_setup):
        """Test link_story_to_epic functionality."""
        session_id, mock_client = session_setup

        # Setup mock return
        mock_client.api.epics.add_related_user_story.return_value = {
            "epic": 1,
            "user_story": 10,
            "order": 1,
        }

        # Call the function
        result = src.server.link_story_to_epic(1, 10, session_id)
        assert result["epic"] == 1
        assert result["user_story"] == 10

        # Verify correct API call (includes epic=epic_id workaround for pytaigaclient bug)
        mock_client.api.epics.add_related_user_story.assert_called_once_with(1, 10, epic=1)

    def test_unlink_story_from_epic(self, session_setup):
        """Test unlink_story_from_epic functionality."""
        session_id, mock_client = session_setup

        # Setup mock
        mock_client.api.epics.delete_related_user_story.return_value = None

        # Call the function
        result = src.server.unlink_story_from_epic(1, 10, session_id)
        assert result["status"] == "unlinked"
        assert result["epic_id"] == 1
        assert result["user_story_id"] == 10

        # Verify correct API call
        mock_client.api.epics.delete_related_user_story.assert_called_once_with(1, 10)

    def test_assign_user_story_to_user(self, session_setup):
        """Test assign_user_story_to_user functionality.

        This test verifies the json.dumps bug fix - the function should pass
        a dict (not a JSON string) to update_user_story.
        """
        session_id, mock_client = session_setup

        # Setup mock returns for the delegation chain
        mock_client.api.user_stories.get.return_value = {"id": 1, "version": 1}
        mock_client.api.user_stories.edit.return_value = {
            "id": 1,
            "assigned_to": 5,
            "version": 2,
        }

        # Call the function
        result = src.server.assign_user_story_to_user(1, 5, session_id)
        assert result["assigned_to"] == 5

        # Verify the edit was called with correct kwargs (dict, not JSON string)
        mock_client.api.user_stories.edit.assert_called_once_with(
            user_story_id=1, version=1, assigned_to=5
        )

    def test_unassign_user_story_from_user(self, session_setup):
        """Test unassign_user_story_from_user functionality."""
        session_id, mock_client = session_setup

        # Setup mock returns
        mock_client.api.user_stories.get.return_value = {"id": 1, "version": 1}
        mock_client.api.user_stories.edit.return_value = {
            "id": 1,
            "assigned_to": None,
            "version": 2,
        }

        # Call the function
        result = src.server.unassign_user_story_from_user(1, session_id)
        assert result["assigned_to"] is None

        # Verify the edit was called with assigned_to=None
        mock_client.api.user_stories.edit.assert_called_once_with(
            user_story_id=1, version=1, assigned_to=None
        )

    def test_list_history(self, session_setup):
        """Test list_history functionality."""
        session_id, mock_client = session_setup

        # Setup mock return with full user object (as returned by Taiga API)
        mock_client.api.get.return_value = [
            {
                "id": "abc-123",
                "type": 1,
                "key": "userstories.userstory:32",
                "comment": "Test comment",
                "user": {
                    "pk": 5,
                    "username": "testuser",
                    "name": "Test User",
                    "photo": "https://example.com/photo.jpg",
                    "gravatar_id": "abc123",
                },
                "created_at": "2026-01-12T10:00:00Z",
                "diff": {"status": [1, 2]},
                "values_diff": {"status": ["New", "Done"]},
            }
        ]

        # Call the function (default standard verbosity)
        result = src.server.list_history("userstory", 32, session_id)
        assert len(result) == 1
        assert result[0]["comment"] == "Test comment"
        assert result[0]["key"] == "userstories.userstory:32"

        # Verify user object is simplified (no photo/gravatar)
        assert result[0]["user"] == {"id": 5, "name": "Test User"}
        assert "photo" not in result[0]["user"]
        assert "gravatar_id" not in result[0]["user"]

        # Verify correct API call
        mock_client.api.get.assert_called_once_with("/history/userstory/32")

    def test_list_history_invalid_type(self, session_setup):
        """Test list_history rejects invalid object types."""
        session_id, _ = session_setup

        with pytest.raises(ValueError) as exc_info:
            src.server.list_history("invalid_type", 32, session_id)

        assert "Invalid object_type" in str(exc_info.value)
        assert "userstory" in str(exc_info.value)

    def test_add_comment(self, session_setup):
        """Test add_comment functionality."""
        session_id, mock_client = session_setup

        # Setup mock returns
        mock_client.api.get.return_value = {"id": 32, "version": 5}
        mock_client.api.patch.return_value = {"id": 32, "version": 6}

        # Call the function
        result = src.server.add_comment("userstory", 32, "New comment", session_id)
        assert result["status"] == "comment_added"
        assert result["comment"] == "New comment"
        assert result["new_version"] == 6

        # Verify correct API calls
        mock_client.api.get.assert_called_once_with("/userstories/32")
        mock_client.api.patch.assert_called_once_with(
            "/userstories/32", json={"comment": "New comment", "version": 5}
        )

    def test_add_comment_empty_rejected(self, session_setup):
        """Test add_comment rejects empty comments."""
        session_id, _ = session_setup

        with pytest.raises(ValueError) as exc_info:
            src.server.add_comment("userstory", 32, "   ", session_id)

        assert "empty" in str(exc_info.value).lower()
