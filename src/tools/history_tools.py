"""History and comments tools."""

import logging
from typing import Any, Dict, List, Optional

from src.response_filter import filter_response
from src.session import execute_taiga_operation, get_authenticated_client, get_session_id

logger = logging.getLogger(__name__)

# Valid object types for history API
VALID_HISTORY_TYPES = {"userstory", "task", "issue", "epic", "wiki"}

# Mapping from history type to API resource endpoint
HISTORY_TYPE_TO_RESOURCE = {
    "userstory": "userstories",
    "task": "tasks",
    "issue": "issues",
    "epic": "epics",
    "wiki": "wiki",
}


def _simplify_history_user(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Simplify nested user objects in history entries."""
    for entry in entries:
        if "user" in entry and isinstance(entry["user"], dict):
            entry["user"] = {
                "id": entry["user"].get("pk"),
                "name": entry["user"].get("name"),
            }
    return entries


def list_history(object_type: str, object_id: int, session_id: Optional[str] = None, verbosity: str = "standard") -> List[Dict[str, Any]]:
    """Lists history entries for an object, including comments and changes."""
    if object_type not in VALID_HISTORY_TYPES:
        raise ValueError(f"Invalid object_type '{object_type}'. Must be one of: {', '.join(sorted(VALID_HISTORY_TYPES))}")
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing list_history for {object_type}/{object_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    result = execute_taiga_operation("list_history", lambda: taiga_client_wrapper.api.get(f"/history/{object_type}/{object_id}"), f"{object_type}/{object_id}")
    filtered = filter_response(result, "history_entry", verbosity)
    if verbosity != "full" and isinstance(filtered, list):
        filtered = _simplify_history_user(filtered)
    return filtered


def add_comment(object_type: str, object_id: int, comment: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Adds a comment to an object via PATCH with comment field."""
    if object_type not in VALID_HISTORY_TYPES:
        raise ValueError(f"Invalid object_type '{object_type}'. Must be one of: {', '.join(sorted(VALID_HISTORY_TYPES))}")
    if not comment or not comment.strip():
        raise ValueError("Comment cannot be empty")
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing add_comment to {object_type}/{object_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    resource_endpoint = HISTORY_TYPE_TO_RESOURCE[object_type]

    def do_add_comment():
        obj = taiga_client_wrapper.api.get(f"/{resource_endpoint}/{object_id}")
        version = obj.get("version")
        if version is None:
            raise ValueError(f"Could not get version for {object_type}/{object_id}")
        result = taiga_client_wrapper.api.patch(f"/{resource_endpoint}/{object_id}", json={"comment": comment.strip(), "version": version})
        return {"status": "comment_added", "object_type": object_type, "object_id": object_id, "comment": comment.strip(), "new_version": result.get("version")}

    return execute_taiga_operation("add_comment", do_add_comment, f"{object_type}/{object_id}")


def register(mcp):
    mcp.tool("list_history", description="Lists history entries (including comments) for an object. object_type must be one of: userstory, task, issue, epic, wiki. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(list_history)
    mcp.tool("add_comment", description="Adds a comment to an object. object_type must be one of: userstory, task, issue, epic, wiki. Uses default session if session_id not provided.")(add_comment)
