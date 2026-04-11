"""Authentication and session management tools (stdio mode)."""

import logging
import uuid
from typing import Any, Dict, Optional

from pytaigaclient.exceptions import TaigaException

from src.config import settings
from src.session import (
    DEFAULT_SESSION_ID,
    active_sessions,
    get_session_id,
)
from src.taiga_client import TaigaClientWrapper

logger = logging.getLogger(__name__)


def get_default_session() -> Dict[str, Any]:
    """Returns the default session ID if environment-based authentication was successful."""
    if DEFAULT_SESSION_ID in active_sessions:
        client = active_sessions[DEFAULT_SESSION_ID]
        if client and client.is_authenticated:
            return {
                "session_id": DEFAULT_SESSION_ID,
                "status": "active",
                "auto_authenticated": True,
            }
    return {
        "status": "unavailable",
        "message": "No default session. Set TAIGA_USERNAME/TAIGA_PASSWORD environment variables or use login() tool.",
    }


def login(
    host: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, str]:
    """Handles Taiga login and creates a session."""
    actual_host = host or settings.host
    actual_username = username or settings.get_username_value()
    actual_password = password or settings.get_password_value()

    if not actual_host:
        raise ValueError("Host URL required. Set TAIGA_API_URL or provide 'host' parameter.")
    if not actual_username or not actual_password:
        raise ValueError(
            "Credentials required. Set TAIGA_USERNAME/TAIGA_PASSWORD or provide parameters."
        )

    logger.info(f"Executing login tool on host '{actual_host}'")

    try:
        wrapper = TaigaClientWrapper(host=actual_host)
        login_successful = wrapper.login(username=actual_username, password=actual_password)

        if login_successful:
            new_session_id = str(uuid.uuid4())
            active_sessions[new_session_id] = wrapper
            logger.info("Login successful. Session created.")
            return {"session_id": new_session_id}
        else:
            logger.error("Login attempt returned False unexpectedly.")
            raise RuntimeError("Login failed for an unknown reason.")

    except (ValueError, TaigaException) as e:
        logger.error(f"Login failed: {e}", exc_info=False)
        raise e
    except Exception as e:
        logger.error(f"Unexpected error during login: {e}", exc_info=True)
        raise RuntimeError("An unexpected server error occurred during login.")


def logout(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Logs out the current session, invalidating the session_id."""
    actual_session_id = get_session_id(session_id)
    logger.info(f"Executing logout for session {actual_session_id[:8]}...")
    client_wrapper = active_sessions.pop(actual_session_id, None)
    if client_wrapper:
        logger.info(f"Session {actual_session_id[:8]} logged out successfully.")
        return {"status": "logged_out", "session_id": actual_session_id}
    else:
        logger.warning(f"Attempted to log out non-existent session: {actual_session_id[:8]}")
        return {"status": "session_not_found", "session_id": actual_session_id}


def session_status(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Checks the validity of the current session_id."""
    actual_session_id = get_session_id(session_id)
    logger.debug(f"Executing session_status check for session {actual_session_id[:8]}...")
    client_wrapper = active_sessions.get(actual_session_id)
    if client_wrapper and client_wrapper.is_authenticated:
        try:
            me = client_wrapper.api.users.get_me()
            username = me.get("username", "Unknown")
            logger.debug(f"Session {actual_session_id[:8]} is active for user {username}.")
            return {
                "status": "active",
                "session_id": actual_session_id,
                "username": username,
            }
        except TaigaException:
            logger.warning(
                f"Session {actual_session_id[:8]} found but token seems invalid (API check failed)."
            )
            active_sessions.pop(actual_session_id, None)
            return {
                "status": "inactive",
                "reason": "token_invalid",
                "session_id": actual_session_id,
            }
        except Exception as e:
            logger.error(
                f"Unexpected error during session status check for {actual_session_id[:8]}: {e}",
                exc_info=True,
            )
            return {
                "status": "error",
                "reason": "check_failed",
                "session_id": actual_session_id,
            }
    elif client_wrapper:
        logger.warning(
            f"Session {actual_session_id[:8]} exists but client wrapper is not authenticated."
        )
        return {
            "status": "inactive",
            "reason": "not_authenticated",
            "session_id": actual_session_id,
        }
    else:
        logger.debug(f"Session {actual_session_id[:8]} not found.")
        return {
            "status": "inactive",
            "reason": "not_found",
            "session_id": actual_session_id,
        }


def register(mcp):
    mcp.tool(
        "get_default_session",
        description="Returns the default session ID if auto-authentication from environment variables was successful.",
    )(get_default_session)
    mcp.tool(
        "login",
        description="Logs into a Taiga instance. Uses environment variables as defaults if parameters not provided.",
    )(login)
    mcp.tool(
        "logout",
        description="Invalidates the current session_id. Uses default session if session_id not provided.",
    )(logout)
    mcp.tool(
        "session_status",
        description="Checks if the provided session_id is currently active and valid. Uses default session if session_id not provided.",
    )(session_status)
