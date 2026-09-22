"""User story tools."""

import logging
from typing import Any, Dict, List, Optional

from src.response_filter import filter_response, validate_kwargs
from src.session import execute_taiga_operation, resolve_client

logger = logging.getLogger(__name__)


def list_user_stories(
    project_id: int,
    filters: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    verbosity: str = "standard",
) -> List[Dict[str, Any]]:
    """Lists user stories for a project."""
    parsed_filters = filters or {}
    logger.info(
        f"Executing list_user_stories for project {project_id}, filters: {parsed_filters}"
    )
    taiga_client_wrapper = resolve_client(session_id)

    result = execute_taiga_operation(
        "list_user_stories",
        lambda: taiga_client_wrapper.api.user_stories.list(project=project_id, **parsed_filters),
        f"project {project_id}",
    )
    return filter_response(result, "user_story", verbosity)


def create_user_story(
    project_id: int,
    subject: str,
    kwargs: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    verbosity: str = "standard",
) -> Dict[str, Any]:
    """Creates a user story. Requires project_id and subject."""
    parsed_kwargs = validate_kwargs("user_story", kwargs or {})
    logger.info(
        f"Executing create_user_story '{subject}' in project {project_id}..."
    )
    taiga_client_wrapper = resolve_client(session_id)
    if not subject:
        raise ValueError("User story subject cannot be empty.")

    result = execute_taiga_operation(
        "create_user_story",
        lambda: taiga_client_wrapper.api.user_stories.create(
            project=project_id, subject=subject, **parsed_kwargs
        ),
        f"user story '{subject}'",
    )
    return filter_response(result, "user_story", verbosity)


def get_user_story(
    user_story_id: int, session_id: Optional[str] = None, verbosity: str = "standard"
) -> Dict[str, Any]:
    """Retrieves user story details by ID."""
    logger.info(
        f"Executing get_user_story ID {user_story_id}..."
    )
    taiga_client_wrapper = resolve_client(session_id)

    result = execute_taiga_operation(
        "get_user_story",
        lambda: taiga_client_wrapper.api.user_stories.get(user_story_id),
        f"user story {user_story_id}",
    )
    return filter_response(result, "user_story", verbosity)


def update_user_story(
    user_story_id: int,
    kwargs: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    verbosity: str = "standard",
) -> Dict[str, Any]:
    """Updates a user story. Pass fields to update as kwargs dict."""
    parsed_kwargs = validate_kwargs("user_story", kwargs or {})
    logger.info(
        f"Executing update_user_story ID {user_story_id} with data: {parsed_kwargs}"
    )
    taiga_client_wrapper = resolve_client(session_id)

    def do_update():
        if not parsed_kwargs:
            logger.info(f"No fields provided for update on user story {user_story_id}")
            result = taiga_client_wrapper.api.user_stories.get(user_story_id)
            return filter_response(result, "user_story", verbosity)

        current_story = taiga_client_wrapper.api.user_stories.get(user_story_id)
        version = current_story.get("version")
        if not version:
            raise ValueError(f"Could not determine version for user story {user_story_id}")

        updated_story = taiga_client_wrapper.api.user_stories.edit(
            user_story_id=user_story_id, version=version, **parsed_kwargs
        )
        logger.info(f"User story {user_story_id} update request sent.")
        return filter_response(updated_story, "user_story", verbosity)

    return execute_taiga_operation("update_user_story", do_update, f"user story {user_story_id}")


def delete_user_story(user_story_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Deletes a user story by ID."""
    logger.warning(
        f"Executing delete_user_story ID {user_story_id}..."
    )
    taiga_client_wrapper = resolve_client(session_id)

    def do_delete():
        taiga_client_wrapper.api.user_stories.delete(user_story_id=user_story_id)
        return {"status": "deleted", "user_story_id": user_story_id}

    return execute_taiga_operation("delete_user_story", do_delete, f"user story {user_story_id}")


def assign_user_story_to_user(
    user_story_id: int, user_id: int, session_id: Optional[str] = None
) -> Dict[str, Any]:
    """Assigns a user story to a user."""
    logger.info(
        f"Executing assign_user_story_to_user: US {user_story_id} -> User {user_id}..."
    )
    return update_user_story(user_story_id, {"assigned_to": user_id}, session_id)


def unassign_user_story_from_user(
    user_story_id: int, session_id: Optional[str] = None
) -> Dict[str, Any]:
    """Unassigns a user story."""
    logger.info(
        f"Executing unassign_user_story_from_user: US {user_story_id}..."
    )
    return update_user_story(user_story_id, {"assigned_to": None}, session_id)


def get_user_story_statuses(
    project_id: int, session_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieves the list of user story statuses for a project."""
    logger.info(
        f"Executing get_user_story_statuses for project {project_id}..."
    )
    taiga_client_wrapper = resolve_client(session_id)

    return execute_taiga_operation(
        "get_user_story_statuses",
        lambda: taiga_client_wrapper.api.userstory_statuses.list(
            query_params={"project": project_id}
        ),
        f"project {project_id}",
    )


def register(mcp):
    mcp.tool("list_user_stories", description="Lists user stories for a project. Filters: status (ID), milestone (ID), assigned_to (user ID), epic (ID), tags (comma-separated), status__is_closed (bool). Use get_user_story_statuses for valid status IDs. verbosity: 'minimal', 'standard' (default), 'full'.")(list_user_stories)
    mcp.tool("create_user_story", description="Creates a new user story within a project. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(create_user_story)
    mcp.tool("get_user_story", description="Gets detailed information about a specific user story by its ID. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_user_story)
    mcp.tool("update_user_story", description="Updates details of an existing user story. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(update_user_story)
    mcp.tool("delete_user_story", description="Deletes a user story by its ID. Uses default session if session_id not provided.")(delete_user_story)
    mcp.tool("assign_user_story_to_user", description="Assigns a specific user story to a specific user. Uses default session if session_id not provided.")(assign_user_story_to_user)
    mcp.tool("unassign_user_story_from_user", description="Unassigns a specific user story (sets assigned user to null). Uses default session if session_id not provided.")(unassign_user_story_from_user)
    mcp.tool("get_user_story_statuses", description="Lists available user story statuses for a project. Use returned IDs with list_user_stories filters: {\"status\": <id>}.")(get_user_story_statuses)
