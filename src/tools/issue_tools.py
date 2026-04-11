"""Issue tools."""

import logging
from typing import Any, Dict, List, Optional

from pytaigaclient.exceptions import TaigaException

from src.response_filter import filter_response, validate_kwargs
from src.session import execute_taiga_operation, get_authenticated_client, get_session_id

logger = logging.getLogger(__name__)


def list_issues(project_id: int, filters: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> List[Dict[str, Any]]:
    actual_session_id = get_session_id(session_id)
    parsed_filters = filters or {}
    logger.info(f"Executing list_issues for project {project_id}, session {actual_session_id[:8]}, filters: {parsed_filters}")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    query = {"project": project_id, **parsed_filters}
    result = execute_taiga_operation("list_issues", lambda: taiga_client_wrapper.api.issues.list(query_params=query), f"project {project_id}")
    return filter_response(result, "issue", verbosity)


def create_issue(project_id: int, subject: str, priority_id: int, status_id: int, severity_id: int, type_id: int, kwargs: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    parsed_kwargs = validate_kwargs("issue", kwargs or {})
    logger.info(f"Executing create_issue '{subject}' in project {project_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    if not subject:
        raise ValueError("Issue subject cannot be empty.")
    issue_data = {"priority": priority_id, "status": status_id, "type": type_id, "severity": severity_id, **parsed_kwargs}
    result = execute_taiga_operation("create_issue", lambda: taiga_client_wrapper.api.issues.create(project=project_id, subject=subject, data=issue_data), f"issue '{subject}'")
    return filter_response(result, "issue", verbosity)


def get_issue(issue_id: int, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_issue ID {issue_id} for session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    result = execute_taiga_operation("get_issue", lambda: taiga_client_wrapper.api.issues.get(issue_id), f"issue {issue_id}")
    return filter_response(result, "issue", verbosity)


def update_issue(issue_id: int, kwargs: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    parsed_kwargs = validate_kwargs("issue", kwargs or {})
    logger.info(f"Executing update_issue ID {issue_id} for session {actual_session_id[:8]} with data: {parsed_kwargs}")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    try:
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
    except TaigaException as e:
        logger.error(f"Taiga API error updating issue {issue_id}: {e}", exc_info=False)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error updating issue {issue_id}: {e}", exc_info=True)
        raise RuntimeError(f"Server error updating issue: {e}")


def delete_issue(issue_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.warning(f"Executing delete_issue ID {issue_id} for session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)

    def do_delete():
        taiga_client_wrapper.api.issues.delete(issue_id=issue_id)
        return {"status": "deleted", "issue_id": issue_id}

    return execute_taiga_operation("delete_issue", do_delete, f"issue {issue_id}")


def assign_issue_to_user(issue_id: int, user_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing assign_issue_to_user: Issue {issue_id} -> User {user_id}, session {actual_session_id[:8]}...")
    return update_issue(issue_id, {"assigned_to": user_id}, actual_session_id)


def unassign_issue_from_user(issue_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing unassign_issue_from_user: Issue {issue_id}, session {actual_session_id[:8]}...")
    return update_issue(issue_id, {"assigned_to": None}, actual_session_id)


def get_issue_statuses(project_id: int, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_issue_statuses for project {project_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    return execute_taiga_operation("get_issue_statuses", lambda: taiga_client_wrapper.api.issue_statuses.list(query_params={"project": project_id}), f"project {project_id}")


def get_issue_priorities(project_id: int, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_issue_priorities for project {project_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    return execute_taiga_operation("get_issue_priorities", lambda: taiga_client_wrapper.api.issue_priorities.list(query_params={"project": project_id}), f"project {project_id}")


def get_issue_severities(project_id: int, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_issue_severities for project {project_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    return execute_taiga_operation("get_issue_severities", lambda: taiga_client_wrapper.api.issue_severities.list(query_params={"project": project_id}), f"project {project_id}")


def get_issue_types(project_id: int, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_issue_types for project {project_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    return execute_taiga_operation("get_issue_types", lambda: taiga_client_wrapper.api.issue_types.list(query_params={"project": project_id}), f"project {project_id}")


def register(mcp):
    mcp.tool("list_issues", description="Lists issues within a specific project, optionally filtered. verbosity: 'minimal' (id/ref/subject/status/priority/severity/project), 'standard' (default), 'full'. Uses default session if session_id not provided.")(list_issues)
    mcp.tool("create_issue", description="Creates a new issue within a project. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(create_issue)
    mcp.tool("get_issue", description="Gets detailed information about a specific issue by its ID. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_issue)
    mcp.tool("update_issue", description="Updates details of an existing issue. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(update_issue)
    mcp.tool("delete_issue", description="Deletes an issue by its ID. Uses default session if session_id not provided.")(delete_issue)
    mcp.tool("assign_issue_to_user", description="Assigns a specific issue to a specific user. Uses default session if session_id not provided.")(assign_issue_to_user)
    mcp.tool("unassign_issue_from_user", description="Unassigns a specific issue (sets assigned user to null). Uses default session if session_id not provided.")(unassign_issue_from_user)
    mcp.tool("get_issue_statuses", description="Lists the available statuses for issues within a specific project. Uses default session if session_id not provided.")(get_issue_statuses)
    mcp.tool("get_issue_priorities", description="Lists the available priorities for issues within a specific project. Uses default session if session_id not provided.")(get_issue_priorities)
    mcp.tool("get_issue_severities", description="Lists the available severities for issues within a specific project. Uses default session if session_id not provided.")(get_issue_severities)
    mcp.tool("get_issue_types", description="Lists the available types for issues within a specific project. Uses default session if session_id not provided.")(get_issue_types)
