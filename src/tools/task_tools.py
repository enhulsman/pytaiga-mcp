"""Task tools."""

import logging
from typing import Any, Dict, List, Optional

from src.response_filter import filter_response, validate_kwargs
from src.session import execute_taiga_operation, resolve_client

logger = logging.getLogger(__name__)


def list_tasks(
    project_id: int,
    filters: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    verbosity: str = "standard",
) -> List[Dict[str, Any]]:
    """Lists tasks for a project."""
    parsed_filters = filters or {}
    logger.info(
        f"Executing list_tasks for project {project_id}, filters: {parsed_filters}"
    )
    taiga_client_wrapper = resolve_client(session_id)
    query = {"project": project_id, **parsed_filters}
    result = execute_taiga_operation(
        "list_tasks",
        lambda: taiga_client_wrapper.api.get("/tasks", params=query),
        f"project {project_id}",
    )
    return filter_response(result, "task", verbosity)


def create_task(
    project_id: int,
    subject: str,
    kwargs: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    verbosity: str = "standard",
) -> Dict[str, Any]:
    """Creates a task."""
    parsed_kwargs = validate_kwargs("task", kwargs or {})
    logger.info(
        f"Executing create_task '{subject}' in project {project_id}..."
    )
    taiga_client_wrapper = resolve_client(session_id)
    if not subject:
        raise ValueError("Task subject cannot be empty.")
    result = execute_taiga_operation(
        "create_task",
        lambda: taiga_client_wrapper.api.tasks.create(
            project=project_id, subject=subject, data=parsed_kwargs if parsed_kwargs else None
        ),
        f"task '{subject}'",
    )
    return filter_response(result, "task", verbosity)


def get_task(
    task_id: int, session_id: Optional[str] = None, verbosity: str = "standard"
) -> Dict[str, Any]:
    """Retrieves task details by ID."""
    logger.info(f"Executing get_task ID {task_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    result = execute_taiga_operation(
        "get_task", lambda: taiga_client_wrapper.api.tasks.get(task_id), f"task {task_id}"
    )
    return filter_response(result, "task", verbosity)


def update_task(
    task_id: int,
    kwargs: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    verbosity: str = "standard",
) -> Dict[str, Any]:
    """Updates a task."""
    parsed_kwargs = validate_kwargs("task", kwargs or {})
    logger.info(
        f"Executing update_task ID {task_id} with data: {parsed_kwargs}"
    )
    taiga_client_wrapper = resolve_client(session_id)

    def do_update():
        if not parsed_kwargs:
            result = taiga_client_wrapper.api.tasks.get(task_id)
            return filter_response(result, "task", verbosity)
        current_task = taiga_client_wrapper.api.tasks.get(task_id)
        version = current_task.get("version")
        if not version:
            raise ValueError(f"Could not determine version for task {task_id}")
        updated_task = taiga_client_wrapper.api.tasks.edit(
            task_id=task_id, version=version, data=parsed_kwargs
        )
        logger.info(f"Task {task_id} update request sent.")
        return filter_response(updated_task, "task", verbosity)

    return execute_taiga_operation("update_task", do_update, f"task {task_id}")


def delete_task(task_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Deletes a task by ID."""
    logger.warning(f"Executing delete_task ID {task_id}...")
    taiga_client_wrapper = resolve_client(session_id)

    def do_delete():
        taiga_client_wrapper.api.tasks.delete(task_id=task_id)
        return {"status": "deleted", "task_id": task_id}

    return execute_taiga_operation("delete_task", do_delete, f"task {task_id}")


def assign_task_to_user(
    task_id: int, user_id: int, session_id: Optional[str] = None
) -> Dict[str, Any]:
    """Assigns a task to a user."""
    logger.info(
        f"Executing assign_task_to_user: Task {task_id} -> User {user_id}..."
    )
    return update_task(task_id, {"assigned_to": user_id}, session_id)


def unassign_task_from_user(task_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Unassigns a task."""
    logger.info(
        f"Executing unassign_task_from_user: Task {task_id}..."
    )
    return update_task(task_id, {"assigned_to": None}, session_id)


def get_task_statuses(project_id: int, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves the list of task statuses for a project."""
    logger.info(
        f"Executing get_task_statuses for project {project_id}..."
    )
    taiga_client_wrapper = resolve_client(session_id)
    return execute_taiga_operation(
        "get_task_statuses",
        lambda: taiga_client_wrapper.api.get("/task-statuses", params={"project": project_id}),
        f"project {project_id}",
    )


def get_task_by_ref(
    project_id: int, ref: int, session_id: Optional[str] = None, verbosity: str = "standard"
) -> Dict[str, Any]:
    """Retrieves task details by its #ref number within a project."""
    logger.info(f"Executing get_task_by_ref ref #{ref} in project {project_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    # Raw endpoint on purpose: pytaigaclient's get_by_ref helpers are unreliable (Tasks
    # sends the query as a body), and one code path for all four types is easier to test.
    result = execute_taiga_operation(
        "get_task_by_ref",
        lambda: taiga_client_wrapper.api.get(
            "/tasks/by_ref", params={"ref": ref, "project": project_id}
        ),
        f"task #{ref} in project {project_id}",
    )
    return filter_response(result, "task", verbosity)


def register(mcp):
    mcp.tool("list_tasks", description="Lists tasks for a project. Filters: status (ID), user_story (ID), milestone (ID), assigned_to (user ID), tags (comma-separated), status__is_closed (bool). Use get_task_statuses for valid status IDs. verbosity: 'minimal', 'standard' (default), 'full'.")(list_tasks)
    mcp.tool("create_task", description="Creates a new task within a project. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(create_task)
    mcp.tool("get_task", description="Gets detailed information about a specific task by its ID. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_task)
    mcp.tool("get_task_by_ref", description="Gets detailed information about a task by its #ref number, the number shown in the Taiga UI and in search results (not the internal id; use get_task for that). Requires project_id. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_task_by_ref)
    mcp.tool("update_task", description="Updates details of an existing task. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(update_task)
    mcp.tool("delete_task", description="Deletes a task by its ID. Uses default session if session_id not provided.")(delete_task)
    mcp.tool("assign_task_to_user", description="Assigns a specific task to a specific user. Uses default session if session_id not provided.")(assign_task_to_user)
    mcp.tool("unassign_task_from_user", description="Unassigns a specific task (sets assigned user to null). Uses default session if session_id not provided.")(unassign_task_from_user)
    mcp.tool("get_task_statuses", description="Lists available task statuses for a project. Use returned IDs with list_tasks filters: {\"status\": <id>}.")(get_task_statuses)
