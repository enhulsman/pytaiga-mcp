"""Project member management tools."""

import logging
from typing import Any, Dict, List, Optional

from src.response_filter import filter_response
from src.session import execute_taiga_operation, get_authenticated_client, get_session_id

logger = logging.getLogger(__name__)


def get_project_members(project_id: int, session_id: Optional[str] = None, verbosity: str = "standard") -> List[Dict[str, Any]]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_project_members for project {project_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    result = execute_taiga_operation("get_project_members", lambda: taiga_client_wrapper.api.memberships.list(query_params={"project": project_id}), f"project {project_id}")
    return filter_response(result, "member", verbosity)


def invite_project_user(project_id: int, email: str, role_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing invite_project_user {email} to project {project_id} (role {role_id}), session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    if not email:
        raise ValueError("Email cannot be empty.")

    def do_invite():
        result = taiga_client_wrapper.api.memberships.invite(project=project_id, email=email, role_id=role_id)
        return result if isinstance(result, dict) else {"status": "invited", "email": email, "details": result}

    return execute_taiga_operation("invite_project_user", do_invite, f"email '{email}' to project {project_id}")


def register(mcp):
    mcp.tool("get_project_members", description="Lists members of a specific project. verbosity: 'minimal' (id/user/full_name), 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_project_members)
    mcp.tool("invite_project_user", description="Invites a user to a project by email with a specific role. Uses default session if session_id not provided.")(invite_project_user)
