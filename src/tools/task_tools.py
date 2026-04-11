"""Task tools."""

import logging
from typing import Any, Dict, List, Optional

from pytaigaclient.exceptions import TaigaException

from src.response_filter import filter_response, validate_kwargs
from src.session import execute_taiga_operation, get_authenticated_client, get_session_id

logger = logging.getLogger(__name__)


def list_tasks(
    project_id: int,
    filters: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    verbosity: str = "standard",
) -> List[Dict[str, Any]]:
    """Lists tasks for a project."""
    actual_session_id = get_session_id(session_id)
    parsed_filters = filters or {}
    logger.info(
        f"Executing list_tasks for project {project_id}, session {actual_session_id[:8]}, filters: {parsed_filters}"
    )
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
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
    actual_session_id = get_session_id(session_id)
    parsed_kwargs = validate_kwargs("task", kwargs or {})
    logger.info(
        f"Executing create_task '{subject}' in project {project_id}, session {actual_session_id[:8]}..."
    )
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
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
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_task ID {task_id} for session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
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
    actual_session_id = get_session_id(session_id)
    parsed_kwargs = validate_kwargs("task", kwargs or {})
    logger.info(
        f"Executing update_task ID {task_id} for session {actual_session_id[:8]} with data: {parsed_kwargs}"
    )
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    try:
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
    except TaigaException as e:
        logger.error(f"Taiga API error updating task {task_id}: {e}", exc_info=False)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error updating task {task_id}: {e}", exc_info=True)
        raise RuntimeError(f"Server error updating task: {e}")


def delete_task(task_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Deletes a task by ID."""
    actual_session_id = get_session_id(session_id)
    logger.warning(f"Executing delete_task ID {task_id} for session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)

    def do_delete():
        taiga_client_wrapper.api.tasks.delete(task_id=task_id)
        return {"status": "deleted", "task_id": task_id}

    return execute_taiga_operation("delete_task", do_delete, f"task {task_id}")


def assign_task_to_user(
    task_id: int, user_id: int, session_id: Optional[str] = None
) -> Dict[str, Any]:
    """Assigns a task to a user."""
    actual_session_id = get_session_id(session_id)
    logger.info(
        f"Executing assign_task_to_user: Task {task_id} -> User {user_id}, session {actual_session_id[:8]}..."
    )
    return update_task(task_id, {"assigned_to": user_id}, actual_session_id)


def unassign_task_from_user(task_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Unassigns a task."""
    actual_session_id = get_session_id(session_id)
    logger.info(
        f"Executing unassign_task_from_user: Task {task_id}, session {actual_session_id[:8]}..."
    )
    return update_task(task_id, {"assigned_to": None}, actual_session_id)


def get_task_statuses(project_id: int, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves the list of task statuses for a project."""
    actual_session_id = get_session_id(session_id)
    logger.info(
        f"Executing get_task_statuses for project {project_id}, session {actual_session_id[:8]}..."
    )
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    return execute_taiga_operation(
        "get_task_statuses",
        lambda: taiga_client_wrapper.api.get("/task-statuses", params={"project": project_id}),
        f"project {project_id}",
    )


def register(mcp):
    mcp.tool("list_tasks", description="Lists tasks within a specific project, optionally filtered. verbosity: 'minimal' (id/ref/subject/status/project), 'standard' (default), 'full'. Uses default session if session_id not provided.")(list_tasks)
    mcp.tool("create_task", description="Creates a new task within a project. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(create_task)
    mcp.tool("get_task", description="Gets detailed information about a specific task by its ID. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_task)
    mcp.tool("update_task", description="Updates details of an existing task. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(update_task)
    mcp.tool("delete_task", description="Deletes a task by its ID. Uses default session if session_id not provided.")(delete_task)
    mcp.tool("assign_task_to_user", description="Assigns a specific task to a specific user. Uses default session if session_id not provided.")(assign_task_to_user)
    mcp.tool("unassign_task_from_user", description="Unassigns a specific task (sets assigned user to null). Uses default session if session_id not provided.")(unassign_task_from_user)
    mcp.tool("get_task_statuses", description="Lists the available statuses for tasks within a specific project. Uses default session if session_id not provided.")(get_task_statuses)
