# server.py
"""Taiga MCP Server - thin entrypoint.

Creates the FastMCP instance, manages lifespan, and registers tools.
Supports stdio and streamable-http transports with optional OAuth 2.1.
"""

import logging
import logging.config
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from src.config import settings
from src.session import DEFAULT_SESSION_ID, active_sessions, set_oauth_bridge
from src.taiga_client import TaigaClientWrapper
from src.tools import register_all_tools

# Re-export for backward compatibility with tests
from src.response_filter import (  # noqa: F401
    ALLOWED_KWARGS,
    RESPONSE_FIELDS,
    VALID_VERBOSITY_LEVELS,
    filter_response as _filter_response,
    validate_kwargs as _validate_kwargs,
)
from src.session import (  # noqa: F401
    execute_taiga_operation as _execute_taiga_operation,
    get_authenticated_client as _get_authenticated_client,
    get_session_id as _get_session_id,
)
from src.tools.history_tools import (  # noqa: F401
    HISTORY_TYPE_TO_RESOURCE,
    VALID_HISTORY_TYPES,
    _simplify_history_user,
)

# Re-export tool functions for backward compatibility with tests
from src.tools.auth_tools import get_default_session, login, logout, session_status  # noqa: F401
from src.tools.project_tools import (  # noqa: F401
    list_projects, list_all_projects, get_project, get_project_by_slug,
    create_project, update_project, delete_project,
)
from src.tools.userstory_tools import (  # noqa: F401
    list_user_stories, create_user_story, get_user_story, update_user_story,
    delete_user_story, assign_user_story_to_user, unassign_user_story_from_user,
    get_user_story_statuses,
)
from src.tools.task_tools import (  # noqa: F401
    list_tasks, create_task, get_task, update_task, delete_task,
    assign_task_to_user, unassign_task_from_user, get_task_statuses,
)
from src.tools.issue_tools import (  # noqa: F401
    list_issues, create_issue, get_issue, update_issue, delete_issue,
    assign_issue_to_user, unassign_issue_from_user,
    get_issue_statuses, get_issue_priorities, get_issue_severities, get_issue_types,
)
from src.tools.epic_tools import (  # noqa: F401
    list_epics, create_epic, get_epic, update_epic, delete_epic,
    assign_epic_to_user, unassign_epic_from_user,
    list_epic_user_stories, link_story_to_epic, unlink_story_from_epic,
)
from src.tools.milestone_tools import (  # noqa: F401
    list_milestones, create_milestone, get_milestone, update_milestone,
    delete_milestone, get_milestone_stats,
)
from src.tools.wiki_tools import (  # noqa: F401
    list_wiki_pages, get_wiki_page, create_wiki_page, update_wiki_page, delete_wiki_page,
)
from src.tools.member_tools import get_project_members, invite_project_user  # noqa: F401
from src.tools.history_tools import list_history, add_comment  # noqa: F401

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()  # Log to stderr by default
    ],
)
logger = logging.getLogger(__name__)
logging.getLogger("pytaigaclient").setLevel(logging.WARNING)


# --- Lifespan for Auto-Authentication ---
@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server startup and shutdown lifecycle.

    Performs auto-authentication if credentials are in environment (stdio mode).
    """
    if settings.has_credentials:
        logger.info("Environment credentials detected. Attempting auto-authentication...")
        try:
            wrapper = TaigaClientWrapper(host=settings.host)
            success = wrapper.login(
                username=settings.get_username_value(), password=settings.get_password_value()
            )
            if success:
                active_sessions[DEFAULT_SESSION_ID] = wrapper
                logger.info(
                    f"Auto-authentication successful. Default session created: '{DEFAULT_SESSION_ID}'"
                )
            else:
                logger.warning("Auto-authentication failed. Manual login required.")
        except Exception as e:
            logger.error(f"Auto-authentication error: {e}")
            logger.warning("Continuing without auto-authentication. Manual login required.")
    else:
        logger.info("No environment credentials found. Manual login required via login() tool.")

    try:
        yield
    finally:
        logger.info("Server shutting down. Cleaning up sessions...")
        active_sessions.clear()


def create_mcp_server() -> FastMCP:
    """Create and configure the MCP server based on settings.

    Returns a FastMCP instance configured for either stdio or HTTP+OAuth mode.
    """
    transport = settings.transport

    if transport == "streamable-http" and settings.has_oauth_config:
        # HTTP mode with OAuth: configure auth
        from mcp.server.auth.settings import AuthSettings
        from src.auth.credential_store import TaigaCredentialStore
        from src.auth.session_bridge import OAuthSessionBridge
        from src.auth.token_verifier import Auth0TokenVerifier

        auth_settings = AuthSettings(
            issuer_url=settings.oauth_issuer_url,
            resource_server_url=settings.oauth_audience,
            required_scopes=settings.scopes_list or None,
        )

        token_verifier = Auth0TokenVerifier(
            issuer_url=settings.oauth_issuer_url,
            audience=settings.oauth_audience,
            jwks_cache_ttl=settings.jwks_cache_ttl,
        )

        # Initialize credential store and session bridge
        encryption_key = settings.get_encryption_key()
        if encryption_key:
            credential_store = TaigaCredentialStore(
                db_path=settings.credential_store_path,
                encryption_key=encryption_key,
            )
            bridge = OAuthSessionBridge(
                taiga_host=settings.host,
                credential_store=credential_store,
            )
            set_oauth_bridge(bridge)
            logger.info("OAuth session bridge initialized")

        server = FastMCP(
            "Taiga Bridge",
            dependencies=["pytaigaclient"],
            lifespan=server_lifespan,
            auth=auth_settings,
            token_verifier=token_verifier,
            host="0.0.0.0",
            port=8000,
        )
        logger.info("Created MCP server with OAuth authentication (0.0.0.0:8000)")

    elif transport == "streamable-http":
        # HTTP mode WITHOUT OAuth: safety bind to localhost only
        server = FastMCP(
            "Taiga Bridge",
            dependencies=["pytaigaclient"],
            lifespan=server_lifespan,
            host="127.0.0.1",
            port=8000,
        )
        logger.warning("HTTP mode without OAuth -- binding to 127.0.0.1 only")

    else:
        # stdio mode (default)
        server = FastMCP(
            "Taiga Bridge",
            dependencies=["pytaigaclient"],
            lifespan=server_lifespan,
        )

    return server


def _get_transport() -> str:
    """Determine transport from CLI args or config."""
    if "--streamable-http" in sys.argv:
        return "streamable-http"
    if "--sse" in sys.argv:
        return "sse"
    return settings.transport


async def run_http_with_link_routes(mcp_server: FastMCP):
    """Run streamable HTTP server with link routes mounted alongside MCP.

    We must manage the MCP session manager's lifecycle ourselves since
    mounting the MCP Starlette app inside our own app means its lifespan
    doesn't automatically run.
    """
    import uvicorn
    from contextlib import asynccontextmanager
    from starlette.applications import Starlette
    from starlette.routing import Mount

    # Get the MCP's Starlette app (includes auth middleware, /mcp endpoint, etc.)
    mcp_app = mcp_server.streamable_http_app()

    # Build link routes if credential store is available
    extra_routes = []
    from src.session import get_oauth_bridge
    bridge = get_oauth_bridge()
    if bridge:
        from src.auth.link_routes import create_link_routes
        link_routes = create_link_routes(bridge.credential_store)
        if link_routes:
            extra_routes = link_routes
            logger.info(f"Mounted {len(link_routes)} link routes")

    # The session manager was created by streamable_http_app() but its
    # task group needs to be started via run(). Normally the MCP app's
    # lifespan handles this, but since we're wrapping it, we do it here.
    @asynccontextmanager
    async def combined_lifespan(app):
        async with mcp_server._session_manager.run():
            yield

    combined_app = Starlette(
        routes=[
            *extra_routes,
            Mount("/", app=mcp_app),
        ],
        lifespan=combined_lifespan,
    )

    host = mcp_server.settings.host
    port = mcp_server.settings.port
    config = uvicorn.Config(combined_app, host=host, port=port)
    server = uvicorn.Server(config)
    await server.serve()


# --- MCP Server Definition ---
mcp = create_mcp_server()

# --- Register All Tools ---
register_all_tools(mcp)

# --- Run the server ---
if __name__ == "__main__":
    transport = _get_transport()
    if transport == "streamable-http" and settings.has_oauth_config:
        import anyio
        anyio.run(lambda: run_http_with_link_routes(mcp))
    else:
        mcp.run(transport=transport)
