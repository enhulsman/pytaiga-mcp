"""OAuth-mode tools (link status, unlink account).

These tools are registered only in OAuth mode, replacing the
stdio-mode login/logout/session tools.
"""

import logging
from typing import Any, Dict

from src.session import current_oauth_sub, get_oauth_bridge, link_url

logger = logging.getLogger(__name__)


def taiga_link_status() -> Dict[str, Any]:
    """Check if your Taiga account is linked. Returns linking URL if not."""
    oauth_sub = current_oauth_sub()
    bridge = get_oauth_bridge()
    if not bridge:
        raise RuntimeError("OAuth mode not configured")

    if bridge.credential_store.is_linked(oauth_sub):
        return {"linked": True, "message": "Taiga account is linked; tool calls act as that Taiga user."}

    return {
        "linked": False,
        "link_url": link_url(),
        "message": "No Taiga account is linked. Visit the link URL to connect one; until then every Taiga tool is refused.",
    }


def taiga_unlink_account() -> Dict[str, Any]:
    """Unlink your Taiga account from your OAuth identity."""
    oauth_sub = current_oauth_sub()
    bridge = get_oauth_bridge()
    if not bridge:
        raise RuntimeError("OAuth mode not configured")

    revoked = bridge.unlink(oauth_sub)
    return {
        "status": "unlinked",
        "revoked_in_taiga": revoked,
        "message": "Taiga account has been unlinked."
        + ("" if revoked else " The application token could not be revoked in Taiga; an administrator can remove it there."),
    }


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
