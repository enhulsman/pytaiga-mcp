"""Project management tools."""

import logging
from typing import Any, Dict, List, Optional

from pytaigaclient.exceptions import TaigaException

from src.response_filter import filter_response, validate_kwargs
from src.session import execute_taiga_operation, get_authenticated_client, get_session_id

logger = logging.getLogger(__name__)


def list_projects(
    session_id: Optional[str] = None, verbosity: str = "standard"
) -> List[Dict[str, Any]]:
    """Lists projects accessible by the authenticated user."""
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing list_projects for session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)

    result = execute_taiga_operation(
        "list_projects", lambda: taiga_client_wrapper.api.projects.list()
    )
    return filter_response(result, "project", verbosity)


def list_all_projects(
    session_id: Optional[str] = None, verbosity: str = "standard"
) -> List[Dict[str, Any]]:
    """Lists all projects visible to the authenticated user."""
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing list_all_projects for session {actual_session_id[:8]}...")
    return list_projects(actual_session_id, verbosity)


def get_project(
    project_id: int, session_id: Optional[str] = None, verbosity: str = "standard"
) -> Dict[str, Any]:
    """Retrieves project details by ID."""
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_project ID {project_id} for session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)

    result = execute_taiga_operation(
        "get_project",
        lambda: taiga_client_wrapper.api.projects.get(project_id),
        f"project {project_id}",
    )
    return filter_response(result, "project", verbosity)


def get_project_by_slug(
    slug: str, session_id: Optional[str] = None, verbosity: str = "standard"
) -> Dict[str, Any]:
    """Retrieves project details by slug."""
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_project_by_slug '{slug}' for session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)

    result = execute_taiga_operation(
        "get_project_by_slug",
        lambda: taiga_client_wrapper.api.projects.get(slug=slug),
        f"slug '{slug}'",
    )
    return filter_response(result, "project", verbosity)


def create_project(
    name: str,
    description: str,
    kwargs: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    verbosity: str = "standard",
) -> Dict[str, Any]:
    """Creates a new project. Requires name and description. Optional args via kwargs dict."""
    actual_session_id = get_session_id(session_id)
    parsed_kwargs = validate_kwargs("project", kwargs or {})
    logger.info(
        f"Executing create_project '{name}' for session {actual_session_id[:8]} with data: {parsed_kwargs}"
    )
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    if not name or not description:
        raise ValueError("Project name and description are required.")

    result = execute_taiga_operation(
        "create_project",
        lambda: taiga_client_wrapper.api.projects.create(
            name=name, description=description, **parsed_kwargs
        ),
        f"project '{name}'",
    )
    return filter_response(result, "project", verbosity)


def update_project(
    project_id: int,
    kwargs: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    verbosity: str = "standard",
) -> Dict[str, Any]:
    """Updates a project. Pass fields to update as kwargs dict."""
    actual_session_id = get_session_id(session_id)
    parsed_kwargs = validate_kwargs("project", kwargs or {})
    logger.info(
        f"Executing update_project ID {project_id} for session {actual_session_id[:8]} with data: {parsed_kwargs}"
    )
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    try:
        if not parsed_kwargs:
            logger.info(f"No fields provided for update on project {project_id}")
            result = taiga_client_wrapper.api.projects.get(project_id=project_id)
            return filter_response(result, "project", verbosity)

        current_project = taiga_client_wrapper.api.projects.get(project_id=project_id)
        version = current_project.get("version")
        if not version:
            raise ValueError(f"Could not determine version for project {project_id}")

        updated_project = taiga_client_wrapper.api.projects.update(
            project_id=project_id, version=version, project_data=parsed_kwargs
        )
        logger.info(f"Project {project_id} update request sent.")
        return filter_response(updated_project, "project", verbosity)
    except TaigaException as e:
        logger.error(f"Taiga API error updating project {project_id}: {e}", exc_info=False)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error updating project {project_id}: {e}", exc_info=True)
        raise RuntimeError(f"Server error updating project: {e}")


def delete_project(project_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Deletes a project by ID."""
    actual_session_id = get_session_id(session_id)
    logger.warning(
        f"Executing delete_project ID {project_id} for session {actual_session_id[:8]}..."
    )
    taiga_client_wrapper = get_authenticated_client(actual_session_id)

    def do_delete():
        taiga_client_wrapper.api.projects.delete(project_id=project_id)
        return {"status": "deleted", "project_id": project_id}

    return execute_taiga_operation("delete_project", do_delete, f"project {project_id}")


def register(mcp):
    mcp.tool(
        "list_projects",
        description="Lists projects accessible to the authenticated user. verbosity: 'minimal' (id/name/slug), 'standard' (default), 'full'. Uses default session if session_id not provided.",
    )(list_projects)
    mcp.tool(
        "list_all_projects",
        description="Lists all projects visible to the user (requires admin privileges for full list). verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.",
    )(list_all_projects)
    mcp.tool(
        "get_project",
        description="Gets detailed information about a specific project by its ID. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.",
    )(get_project)
    mcp.tool(
        "get_project_by_slug",
        description="Gets detailed information about a specific project by its slug. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.",
    )(get_project_by_slug)
    mcp.tool(
        "create_project",
        description="Creates a new project. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.",
    )(create_project)
    mcp.tool(
        "update_project",
        description="Updates details of an existing project. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.",
    )(update_project)
    mcp.tool(
        "delete_project",
        description="Deletes a project by its ID. This is irreversible. Uses default session if session_id not provided.",
    )(delete_project)
