"""Issue tools."""

import logging
from typing import Any, Dict, List, Optional

from src.response_filter import filter_response, validate_kwargs
from src.session import execute_taiga_operation, resolve_client

logger = logging.getLogger(__name__)


def list_issues(project_id: int, filters: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> List[Dict[str, Any]]:
    parsed_filters = filters or {}
    logger.info(f"Executing list_issues for project {project_id}, filters: {parsed_filters}")
    taiga_client_wrapper = resolve_client(session_id)
    query = {"project": project_id, **parsed_filters}
    result = execute_taiga_operation("list_issues", lambda: taiga_client_wrapper.api.issues.list(query_params=query), f"project {project_id}")
    return filter_response(result, "issue", verbosity)


def create_issue(project_id: int, subject: str, priority_id: int, status_id: int, severity_id: int, type_id: int, kwargs: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    parsed_kwargs = validate_kwargs("issue", kwargs or {})
    logger.info(f"Executing create_issue '{subject}' in project {project_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    if not subject:
        raise ValueError("Issue subject cannot be empty.")
    issue_data = {"priority": priority_id, "status": status_id, "type": type_id, "severity": severity_id, **parsed_kwargs}
    result = execute_taiga_operation("create_issue", lambda: taiga_client_wrapper.api.issues.create(project=project_id, subject=subject, data=issue_data), f"issue '{subject}'")
    return filter_response(result, "issue", verbosity)


def get_issue(issue_id: int, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    logger.info(f"Executing get_issue ID {issue_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    result = execute_taiga_operation("get_issue", lambda: taiga_client_wrapper.api.issues.get(issue_id), f"issue {issue_id}")
    return filter_response(result, "issue", verbosity)


def update_issue(issue_id: int, kwargs: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    parsed_kwargs = validate_kwargs("issue", kwargs or {})
    logger.info(f"Executing update_issue ID {issue_id} with data: {parsed_kwargs}")
    taiga_client_wrapper = resolve_client(session_id)

    def do_update():
        if not parsed_kwargs:
            result = taiga_client_wrapper.api.issues.get(issue_id)
            return filter_response(result, "issue", verbosity)
        current_issue = taiga_client_wrapper.api.issues.get(issue_id)
        version = current_issue.get("version")
        if not version:
            raise ValueError(f"Could not determine version for issue {issue_id}")
        updated_issue = taiga_client_wrapper.api.issues.edit(issue_id=issue_id, version=version, data=parsed_kwargs)
        logger.info(f"Issue {issue_id} update request sent.")
        return filter_response(updated_issue, "issue", verbosity)

    return execute_taiga_operation("update_issue", do_update, f"issue {issue_id}")


def delete_issue(issue_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    logger.warning(f"Executing delete_issue ID {issue_id}...")
    taiga_client_wrapper = resolve_client(session_id)

    def do_delete():
        taiga_client_wrapper.api.issues.delete(issue_id=issue_id)
        return {"status": "deleted", "issue_id": issue_id}

    return execute_taiga_operation("delete_issue", do_delete, f"issue {issue_id}")


def assign_issue_to_user(issue_id: int, user_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    logger.info(f"Executing assign_issue_to_user: Issue {issue_id} -> User {user_id}...")
    return update_issue(issue_id, {"assigned_to": user_id}, session_id)


def unassign_issue_from_user(issue_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    logger.info(f"Executing unassign_issue_from_user: Issue {issue_id}...")
    return update_issue(issue_id, {"assigned_to": None}, session_id)


def get_issue_statuses(project_id: int, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    logger.info(f"Executing get_issue_statuses for project {project_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    return execute_taiga_operation("get_issue_statuses", lambda: taiga_client_wrapper.api.issue_statuses.list(query_params={"project": project_id}), f"project {project_id}")


def get_issue_priorities(project_id: int, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    logger.info(f"Executing get_issue_priorities for project {project_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    return execute_taiga_operation("get_issue_priorities", lambda: taiga_client_wrapper.api.issue_priorities.list(query_params={"project": project_id}), f"project {project_id}")


def get_issue_severities(project_id: int, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    logger.info(f"Executing get_issue_severities for project {project_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    return execute_taiga_operation("get_issue_severities", lambda: taiga_client_wrapper.api.issue_severities.list(query_params={"project": project_id}), f"project {project_id}")


def get_issue_types(project_id: int, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    logger.info(f"Executing get_issue_types for project {project_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    return execute_taiga_operation("get_issue_types", lambda: taiga_client_wrapper.api.issue_types.list(query_params={"project": project_id}), f"project {project_id}")


def get_issue_by_ref(
    project_id: int, ref: int, session_id: Optional[str] = None, verbosity: str = "standard"
) -> Dict[str, Any]:
    """Retrieves issue details by its #ref number within a project."""
    logger.info(f"Executing get_issue_by_ref ref #{ref} in project {project_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    # Raw endpoint on purpose: pytaigaclient's get_by_ref helpers are unreliable (Tasks
    # sends the query as a body), and one code path for all four types is easier to test.
    result = execute_taiga_operation(
        "get_issue_by_ref",
        lambda: taiga_client_wrapper.api.get(
            "/issues/by_ref", params={"ref": ref, "project": project_id}
        ),
        f"issue #{ref} in project {project_id}",
    )
    return filter_response(result, "issue", verbosity)


def register(mcp):
    mcp.tool("list_issues", description="Lists issues for a project. Filters: status (ID), severity (ID), priority (ID), type (ID), assigned_to (user ID), tags (comma-separated), status__is_closed (bool). Use get_issue_statuses/priorities/severities/types for valid IDs. verbosity: 'minimal', 'standard' (default), 'full'.")(list_issues)
    mcp.tool("create_issue", description="Creates a new issue within a project. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(create_issue)
    mcp.tool("get_issue", description="Gets detailed information about a specific issue by its ID. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_issue)
    mcp.tool("get_issue_by_ref", description="Gets detailed information about a issue by its #ref number, the number shown in the Taiga UI and in search results (not the internal id; use get_issue for that). Requires project_id. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_issue_by_ref)
    mcp.tool("update_issue", description="Updates details of an existing issue. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(update_issue)
    mcp.tool("delete_issue", description="Deletes an issue by its ID. Uses default session if session_id not provided.")(delete_issue)
    mcp.tool("assign_issue_to_user", description="Assigns a specific issue to a specific user. Uses default session if session_id not provided.")(assign_issue_to_user)
    mcp.tool("unassign_issue_from_user", description="Unassigns a specific issue (sets assigned user to null). Uses default session if session_id not provided.")(unassign_issue_from_user)
    mcp.tool("get_issue_statuses", description="Lists available issue statuses for a project. Use returned IDs with list_issues filters: {\"status\": <id>}.")(get_issue_statuses)
    mcp.tool("get_issue_priorities", description="Lists available issue priorities for a project. Use returned IDs with list_issues filters: {\"priority\": <id>}.")(get_issue_priorities)
    mcp.tool("get_issue_severities", description="Lists available issue severities for a project. Use returned IDs with list_issues filters: {\"severity\": <id>}.")(get_issue_severities)
    mcp.tool("get_issue_types", description="Lists available issue types for a project. Use returned IDs with list_issues filters: {\"type\": <id>}.")(get_issue_types)
