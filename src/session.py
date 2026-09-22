"""Session management for Taiga MCP server.

Handles both stdio (username/password) and OAuth session modes.
Tools call resolve_client(); it dispatches on the mode:

- stdio: the explicit session_id, else the default session built from
  TAIGA_USERNAME/TAIGA_PASSWORD at startup.
- OAuth (streamable-http with an OAuth bridge): the Taiga client linked to the
  caller's OAuth subject. Unlinked subjects are refused with the link URL, and
  an explicit session_id is rejected so the service-account session cannot be
  selected by hand.
"""

import logging
from typing import Any, Dict, Optional

from mcp.server.auth.middleware.auth_context import get_access_token
from pytaigaclient.exceptions import TaigaAuthenticationError, TaigaException

from src.config import settings
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


class NotLinkedError(PermissionError):
    """The OAuth subject has no linked Taiga account, or its link was just removed."""


def link_url() -> str:
    """Public URL of the browser linking flow."""
    base = (settings.oauth_audience or "").rstrip("/")
    return f"{base}/link-account"


def current_oauth_sub() -> str:
    """OAuth subject of the current request (the verifier maps JWT sub -> client_id)."""
    access_token = get_access_token()
    if access_token is None:
        raise PermissionError("Not authenticated. OAuth token required.")
    return access_token.client_id


def get_session_id(session_id: Optional[str] = None) -> str:
    """Get session ID, defaulting to 'default' if available (stdio mode)."""
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


def resolve_client(session_id: Optional[str] = None) -> TaigaClientWrapper:
    """Return the Taiga client a tool call must act with. See module docstring."""
    bridge = get_oauth_bridge()
    if bridge is None:
        return get_authenticated_client(get_session_id(session_id))

    if session_id:
        raise ValueError(
            "session_id is not accepted in OAuth mode: the Taiga identity follows "
            "your OAuth login. Omit session_id."
        )
    oauth_sub = current_oauth_sub()
    client = bridge.get_client_sync(oauth_sub)
    if client is None:
        raise NotLinkedError(
            f"No Taiga account is linked to your login. Link one at {link_url()} and retry."
        )
    return client


def _unlink_on_dead_token(error: TaigaAuthenticationError) -> Optional[NotLinkedError]:
    """In OAuth mode a 401 from Taiga means the linked token is dead: forget it.
    403 is a permission problem with a live token and is left alone."""
    bridge = get_oauth_bridge()
    if bridge is None or getattr(error, "status_code", None) != 401:
        return None
    try:
        oauth_sub = current_oauth_sub()
    except PermissionError:
        return None
    bridge.handle_taiga_auth_failure(oauth_sub)
    return NotLinkedError(
        f"Taiga rejected the linked token, so the link was removed. Re-link at {link_url()} and retry."
    )


def execute_taiga_operation(operation_name: str, operation_callable, error_context: str = ""):
    """Execute a Taiga API operation with standardized error handling."""
    context_str = f" for {error_context}" if error_context else ""
    try:
        result = operation_callable()
        return result
    except TaigaAuthenticationError as e:
        not_linked = _unlink_on_dead_token(e)
        if not_linked is not None:
            logger.warning(f"Taiga 401 in {operation_name}{context_str}: link removed")
            raise not_linked from e
        logger.error(f"Taiga auth error in {operation_name}{context_str}: {e}", exc_info=False)
        raise e
    except TaigaException as e:
        logger.error(f"Taiga API error in {operation_name}{context_str}: {e}", exc_info=False)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in {operation_name}{context_str}: {e}", exc_info=True)
        raise RuntimeError(f"Server error in {operation_name}: {e}")
