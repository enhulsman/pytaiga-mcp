"""Tool registration dispatcher for Taiga MCP server."""

from src.session import is_oauth_mode
from src.tools import (
    epic_tools,
    history_tools,
    issue_tools,
    member_tools,
    milestone_tools,
    project_tools,
    search_tools,
    task_tools,
    userstory_tools,
    wiki_tools,
)


def register_all_tools(mcp):
    """Register all tool modules with the MCP server.

    In stdio mode: register login/logout/session tools
    In OAuth mode: register link_status/unlink tools
    Core tools (projects, stories, etc.) are always registered.
    """
    if is_oauth_mode():
        from src.tools import oauth_tools
        oauth_tools.register(mcp)
    else:
        from src.tools import auth_tools
        auth_tools.register(mcp)

    # Core tools -- always registered
    project_tools.register(mcp)
    userstory_tools.register(mcp)
    task_tools.register(mcp)
    issue_tools.register(mcp)
    epic_tools.register(mcp)
    milestone_tools.register(mcp)
    wiki_tools.register(mcp)
    member_tools.register(mcp)
    history_tools.register(mcp)
    search_tools.register(mcp)
