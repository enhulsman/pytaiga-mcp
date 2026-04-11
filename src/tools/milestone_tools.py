"""Milestone (Sprint) tools."""

import logging
from typing import Any, Dict, List, Optional

from pytaigaclient.exceptions import TaigaException

from src.response_filter import filter_response, validate_kwargs
from src.session import execute_taiga_operation, get_authenticated_client, get_session_id

logger = logging.getLogger(__name__)


def list_milestones(project_id: int, closed: Optional[bool] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> List[Dict[str, Any]]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing list_milestones for project {project_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    result = execute_taiga_operation("list_milestones", lambda: taiga_client_wrapper.api.milestones.list(project=project_id, closed=closed), f"project {project_id}")
    return filter_response(result, "milestone", verbosity)


def create_milestone(project_id: int, name: str, estimated_start: str, estimated_finish: str, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing create_milestone '{name}' in project {project_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    if not all([name, estimated_start, estimated_finish]):
        raise ValueError("Milestone requires name, estimated_start, and estimated_finish.")
    result = execute_taiga_operation("create_milestone", lambda: taiga_client_wrapper.api.milestones.create(project=project_id, name=name, estimated_start=estimated_start, estimated_finish=estimated_finish), f"milestone '{name}'")
    return filter_response(result, "milestone", verbosity)


def get_milestone(milestone_id: int, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_milestone ID {milestone_id} for session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    result = execute_taiga_operation("get_milestone", lambda: taiga_client_wrapper.api.milestones.get(milestone_id), f"milestone {milestone_id}")
    return filter_response(result, "milestone", verbosity)


def update_milestone(milestone_id: int, kwargs: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    parsed_kwargs = validate_kwargs("milestone", kwargs or {})
    logger.info(f"Executing update_milestone ID {milestone_id} for session {actual_session_id[:8]} with data: {parsed_kwargs}")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    try:
        if not parsed_kwargs:
            result = taiga_client_wrapper.api.milestones.get(milestone_id)
            return filter_response(result, "milestone", verbosity)
        current_milestone = taiga_client_wrapper.api.milestones.get(milestone_id)
        version = current_milestone.get("version")
        if not version:
            raise ValueError(f"Could not determine version for milestone {milestone_id}")
        updated_milestone = taiga_client_wrapper.api.milestones.edit(milestone_id=milestone_id, version=version, **parsed_kwargs)
        logger.info(f"Milestone {milestone_id} update request sent.")
        return filter_response(updated_milestone, "milestone", verbosity)
    except TaigaException as e:
        logger.error(f"Taiga API error updating milestone {milestone_id}: {e}", exc_info=False)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error updating milestone {milestone_id}: {e}", exc_info=True)
        raise RuntimeError(f"Server error updating milestone: {e}")


def delete_milestone(milestone_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.warning(f"Executing delete_milestone ID {milestone_id} for session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)

    def do_delete():
        taiga_client_wrapper.api.milestones.delete(milestone_id=milestone_id)
        return {"status": "deleted", "milestone_id": milestone_id}

    return execute_taiga_operation("delete_milestone", do_delete, f"milestone {milestone_id}")


def get_milestone_stats(milestone_id: int, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing get_milestone_stats for milestone {milestone_id}, session {actual_session_id[:8]}...")
    taiga_client_wrapper = get_authenticated_client(actual_session_id)
    result = execute_taiga_operation("get_milestone_stats", lambda: taiga_client_wrapper.api.milestones.stats(milestone_id), f"milestone {milestone_id}")
    return filter_response(result, "milestone_stats", verbosity)


def register(mcp):
    mcp.tool("list_milestones", description="Lists milestones (sprints) for a project. Set closed=false for open sprints only, closed=true for closed only. Returns all by default. verbosity: 'minimal', 'standard' (default), 'full'.")(list_milestones)
    mcp.tool("create_milestone", description="Creates a new milestone (sprint) within a project. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(create_milestone)
    mcp.tool("get_milestone", description="Gets detailed information about a specific milestone by its ID. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_milestone)
    mcp.tool("update_milestone", description="Updates details of an existing milestone. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(update_milestone)
    mcp.tool("delete_milestone", description="Deletes a milestone by its ID. Uses default session if session_id not provided.")(delete_milestone)
    mcp.tool("get_milestone_stats", description="Gets statistics for a specific milestone (sprint). verbosity: 'minimal' (total/completed points), 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_milestone_stats)
