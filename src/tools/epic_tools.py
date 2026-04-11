"""Epic tools."""

import logging
from typing import Any, Dict, List, Optional

from pytaigaclient.exceptions import TaigaException

from src.response_filter import filter_response, validate_kwargs
from src.session import execute_taiga_operation, get_authenticated_client, get_session_id

logger = logging.getLogger(__name__)


def list_epics(project_id: int, filters: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> List[Dict[str, Any]]:
    actual_session_id = get_session_id(session_id)
    parsed_filters = filters or {}
    logger.info(f"Executing list_epics for project {project_id}, session {actual_session_id[:8]}, filters: {parsed_filters}")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    query = {"project": project_id, **parsed_filters}
    result = execute_taiga_operation("list_epics", lambda: taiga_client_wrapper.api.epics.list(query_params=query), f"project {project_id}")
    return filter_response(result, "epic", verbosity)


def create_epic(project_id: int, subject: str, kwargs: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    parsed_kwargs = validate_kwargs("epic", kwargs or {})
    logger.info(f"Executing create_epic '{subject}' in project {project_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    if not subject:
        raise ValueError("Epic subject cannot be empty.")
    result = execute_taiga_operation("create_epic", lambda: taiga_client_wrapper.api.epics.create(project=project_id, subject=subject, **parsed_kwargs), f"epic '{subject}'")
    return filter_response(result, "epic", verbosity)


def get_epic(epic_id: int, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_epic ID {epic_id} for session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    result = execute_taiga_operation("get_epic", lambda: taiga_client_wrapper.api.epics.get(epic_id), f"epic {epic_id}")
    return filter_response(result, "epic", verbosity)


def update_epic(epic_id: int, kwargs: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    parsed_kwargs = validate_kwargs("epic", kwargs or {})
    logger.info(f"Executing update_epic ID {epic_id} for session {actual_session_id[:8]} with data: {parsed_kwargs}")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    try:
        if not parsed_kwargs:
            result = taiga_client_wrapper.api.epics.get(epic_id)
            return filter_response(result, "epic", verbosity)
        current_epic = taiga_client_wrapper.api.epics.get(epic_id)
        version = current_epic.get("version")
        if not version:
            raise ValueError(f"Could not determine version for epic {epic_id}")
        updated_epic = taiga_client_wrapper.api.epics.edit(epic_id=epic_id, version=version, **parsed_kwargs)
        logger.info(f"Epic {epic_id} update request sent.")
        return filter_response(updated_epic, "epic", verbosity)
    except TaigaException as e:
        logger.error(f"Taiga API error updating epic {epic_id}: {e}", exc_info=False)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error updating epic {epic_id}: {e}", exc_info=True)
        raise RuntimeError(f"Server error updating epic: {e}")


def delete_epic(epic_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.warning(f"Executing delete_epic ID {epic_id} for session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)

    def do_delete():
        taiga_client_wrapper.api.epics.delete(epic_id=epic_id)
        return {"status": "deleted", "epic_id": epic_id}

    return execute_taiga_operation("delete_epic", do_delete, f"epic {epic_id}")


def assign_epic_to_user(epic_id: int, user_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing assign_epic_to_user: Epic {epic_id} -> User {user_id}, session {actual_session_id[:8]}...")
    return update_epic(epic_id, {"assigned_to": user_id}, actual_session_id)


def unassign_epic_from_user(epic_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing unassign_epic_from_user: Epic {epic_id}, session {actual_session_id[:8]}...")
    return update_epic(epic_id, {"assigned_to": None}, actual_session_id)


def list_epic_user_stories(epic_id: int, session_id: Optional[str] = None, verbosity: str = "standard") -> List[Dict[str, Any]]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing list_epic_user_stories for epic {epic_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    result = execute_taiga_operation("list_epic_user_stories", lambda: taiga_client_wrapper.api.epics.list_related_user_stories(epic_id), f"epic {epic_id}")
    return filter_response(result, "epic_related_user_story", verbosity)


def link_story_to_epic(epic_id: int, user_story_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing link_story_to_epic: Epic {epic_id} <- Story {user_story_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    result = execute_taiga_operation("link_story_to_epic", lambda: taiga_client_wrapper.api.epics.add_related_user_story(epic_id, user_story_id, epic=epic_id), f"epic {epic_id} <- story {user_story_id}")
    return result if isinstance(result, dict) else {"status": "linked", "epic_id": epic_id, "user_story_id": user_story_id}


def unlink_story_from_epic(epic_id: int, user_story_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing unlink_story_from_epic: Epic {epic_id} -/- Story {user_story_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)

    def do_unlink():
        taiga_client_wrapper.api.epics.delete_related_user_story(epic_id, user_story_id)
        return {"status": "unlinked", "epic_id": epic_id, "user_story_id": user_story_id}

    return execute_taiga_operation("unlink_story_from_epic", do_unlink, f"epic {epic_id} -/- story {user_story_id}")


def register(mcp):
    mcp.tool("list_epics", description="Lists epics within a specific project, optionally filtered. verbosity: 'minimal' (id/ref/subject/status/project), 'standard' (default), 'full'. Uses default session if session_id not provided.")(list_epics)
    mcp.tool("create_epic", description="Creates a new epic within a project. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(create_epic)
    mcp.tool("get_epic", description="Gets detailed information about a specific epic by its ID. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_epic)
    mcp.tool("update_epic", description="Updates details of an existing epic. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(update_epic)
    mcp.tool("delete_epic", description="Deletes an epic by its ID. Uses default session if session_id not provided.")(delete_epic)
    mcp.tool("assign_epic_to_user", description="Assigns a specific epic to a specific user. Uses default session if session_id not provided.")(assign_epic_to_user)
    mcp.tool("unassign_epic_from_user", description="Unassigns a specific epic (sets assigned user to null). Uses default session if session_id not provided.")(unassign_epic_from_user)
    mcp.tool("list_epic_user_stories", description="Lists user stories related to a specific epic. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(list_epic_user_stories)
    mcp.tool("link_story_to_epic", description="Links a user story to an epic. Uses default session if session_id not provided.")(link_story_to_epic)
    mcp.tool("unlink_story_from_epic", description="Unlinks a user story from an epic. Uses default session if session_id not provided.")(unlink_story_from_epic)
