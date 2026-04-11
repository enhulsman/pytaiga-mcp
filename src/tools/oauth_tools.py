"""OAuth-mode tools (link status, unlink account).

These tools are registered only in OAuth mode, replacing the
stdio-mode login/logout/session tools.
"""

import logging
from typing import Any, Dict

from src.config import settings
from src.session import get_oauth_bridge

logger = logging.getLogger(__name__)


def _get_current_user_sub() -> str:
    """Get the current OAuth user's sub claim from the MCP auth context."""
    from mcp.server.auth.middleware.auth_context import get_access_token

    access_token = get_access_token()
    if not access_token:
        raise PermissionError("Not authenticated. OAuth token required.")
    return access_token.client_id  # We map JWT sub -> client_id in the verifier


def taiga_link_status() -> Dict[str, Any]:
    """Check if your Taiga account is linked. Returns linking URL if not."""
    oauth_sub = _get_current_user_sub()
    bridge = get_oauth_bridge()
    if not bridge:
        raise RuntimeError("OAuth mode not configured")

    if bridge.credential_store.is_linked(oauth_sub):
        return {"linked": True, "message": "Taiga account is linked and active."}

    link_url = f"{settings.oauth_audience}/link-account"
    return {
        "linked": False,
        "link_url": link_url,
        "message": "Visit the link URL to connect your Taiga account.",
    }


def taiga_unlink_account() -> Dict[str, Any]:
    """Unlink your Taiga account from your OAuth identity."""
    oauth_sub = _get_current_user_sub()
    bridge = get_oauth_bridge()
    if not bridge:
        raise RuntimeError("OAuth mode not configured")

    bridge.handle_taiga_auth_failure(oauth_sub)
    return {"status": "unlinked", "message": "Taiga account has been unlinked."}


def register(mcp):
    """Register OAuth-mode tools."""
    mcp.tool(
        "taiga_link_status",
        description="Check if your Taiga account is linked to your OAuth identity. Returns a linking URL if not linked.",
    )(taiga_link_status)
    mcp.tool(
        "taiga_unlink_account",
        description="Unlink your Taiga account from your OAuth identity. You will need to re-link to use Taiga tools.",
    )(taiga_unlink_account)
