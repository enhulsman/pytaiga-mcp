"""Session management for Taiga MCP server.

Handles both stdio (username/password) and OAuth session modes.
The abstraction point is get_taiga_client() which dispatches based on auth mode.
"""

import logging
from typing import Any, Dict, Optional

from pytaigaclient.exceptions import TaigaException

from src.taiga_client import TaigaClientWrapper

logger = logging.getLogger(__name__)

# --- Manual Session Management (stdio mode) ---
active_sessions: Dict[str, TaigaClientWrapper] = {}
DEFAULT_SESSION_ID = "default"

# --- OAuth Session Bridge (set during server creation if OAuth is configured) ---
_oauth_bridge = None


def set_oauth_bridge(bridge):
    """Set the OAuth session bridge (called during server init in HTTP+OAuth mode)."""
    global _oauth_bridge
    _oauth_bridge = bridge


def get_oauth_bridge():
    """Get the OAuth session bridge (None if not in OAuth mode)."""
    return _oauth_bridge


def is_oauth_mode() -> bool:
    """Check if we're running in OAuth mode."""
    return _oauth_bridge is not None


def get_session_id(session_id: Optional[str] = None) -> str:
    """Get session ID, defaulting to 'default' if available.

    In OAuth mode, this is not used -- get_taiga_client_for_oauth() is used instead.
    """
    if session_id:
        return session_id
    if DEFAULT_SESSION_ID in active_sessions:
        return DEFAULT_SESSION_ID
    raise ValueError(
        "No session_id provided and no default session available. "
        "Set TAIGA_USERNAME/TAIGA_PASSWORD environment variables or use login() tool."
    )


def get_authenticated_client(session_id: str) -> TaigaClientWrapper:
    """Retrieves the authenticated TaigaClientWrapper for a given session ID (stdio mode)."""
    client = active_sessions.get(session_id)
    if not client or not client.is_authenticated:
        logger.warning(
            f"Invalid or expired session ID provided: {session_id[:8] if session_id else 'None'}..."
        )
        raise PermissionError("Invalid or expired session ID. Please login again.")
    logger.debug(f"Retrieved valid client for session ID: {session_id[:8]}...")
    return client


def execute_taiga_operation(operation_name: str, operation_callable, error_context: str = ""):
    """Execute a Taiga API operation with standardized error handling."""
    context_str = f" for {error_context}" if error_context else ""
    try:
        result = operation_callable()
        return result
    except TaigaException as e:
        logger.error(f"Taiga API error in {operation_name}{context_str}: {e}", exc_info=False)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in {operation_name}{context_str}: {e}", exc_info=True)
        raise RuntimeError(f"Server error in {operation_name}: {e}")
