"""Wiki page tools."""

import logging
from typing import Any, Dict, List, Optional

from src.response_filter import filter_response, validate_kwargs
from src.session import execute_taiga_operation, resolve_client

logger = logging.getLogger(__name__)


def list_wiki_pages(project_id: int, session_id: Optional[str] = None, verbosity: str = "standard") -> List[Dict[str, Any]]:
    logger.info(f"Executing list_wiki_pages for project {project_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    result = execute_taiga_operation("list_wiki_pages", lambda: taiga_client_wrapper.api.wiki.list(query_params={"project": project_id}), f"project {project_id}")
    return filter_response(result, "wiki_page", verbosity)


def get_wiki_page(wiki_page_id: int, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    logger.info(f"Executing get_wiki_page ID {wiki_page_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    result = execute_taiga_operation("get_wiki_page", lambda: taiga_client_wrapper.api.wiki.get(wiki_page_id), f"wiki page {wiki_page_id}")
    return filter_response(result, "wiki_page", verbosity)


def create_wiki_page(project_id: int, slug: str, content: str, kwargs: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    parsed_kwargs = validate_kwargs("wiki_page", kwargs or {})
    logger.info(f"Executing create_wiki_page '{slug}' in project {project_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    if not slug or not content:
        raise ValueError("Wiki page slug and content are required.")
    result = execute_taiga_operation("create_wiki_page", lambda: taiga_client_wrapper.api.wiki.create(project=project_id, slug=slug, content=content, **parsed_kwargs), f"wiki page '{slug}'")
    return filter_response(result, "wiki_page", verbosity)


def update_wiki_page(wiki_page_id: int, kwargs: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None, verbosity: str = "standard") -> Dict[str, Any]:
    parsed_kwargs = validate_kwargs("wiki_page", kwargs or {})
    logger.info(f"Executing update_wiki_page ID {wiki_page_id} with data: {parsed_kwargs}")
    taiga_client_wrapper = resolve_client(session_id)

    def do_update():
        if not parsed_kwargs:
            result = taiga_client_wrapper.api.wiki.get(wiki_page_id)
            return filter_response(result, "wiki_page", verbosity)
        current_page = taiga_client_wrapper.api.wiki.get(wiki_page_id)
        version = current_page.get("version")
        if not version:
            raise ValueError(f"Could not determine version for wiki page {wiki_page_id}")
        updated_page = taiga_client_wrapper.api.wiki.edit(wiki_page_id=wiki_page_id, version=version, data=parsed_kwargs)
        logger.info(f"Wiki page {wiki_page_id} update request sent.")
        return filter_response(updated_page, "wiki_page", verbosity)

    return execute_taiga_operation("update_wiki_page", do_update, f"wiki page {wiki_page_id}")


def delete_wiki_page(wiki_page_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    logger.warning(f"Executing delete_wiki_page ID {wiki_page_id}...")
    taiga_client_wrapper = resolve_client(session_id)

    def do_delete():
        taiga_client_wrapper.api.wiki.delete(wiki_page_id=wiki_page_id)
        return {"status": "deleted", "wiki_page_id": wiki_page_id}

    return execute_taiga_operation("delete_wiki_page", do_delete, f"wiki page {wiki_page_id}")


def register(mcp):
    mcp.tool("list_wiki_pages", description="Lists wiki pages within a specific project. verbosity: 'minimal' (id/slug/project), 'standard' (default), 'full'. Uses default session if session_id not provided.")(list_wiki_pages)
    mcp.tool("get_wiki_page", description="Gets a specific wiki page by its ID. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(get_wiki_page)
    mcp.tool("create_wiki_page", description="Creates a new wiki page within a project. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(create_wiki_page)
    mcp.tool("update_wiki_page", description="Updates an existing wiki page. verbosity: 'minimal', 'standard' (default), 'full'. Uses default session if session_id not provided.")(update_wiki_page)
    mcp.tool("delete_wiki_page", description="Deletes a wiki page by its ID. Uses default session if session_id not provided.")(delete_wiki_page)
