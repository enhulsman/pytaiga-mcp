"""Mint a Taiga application token for a user during account linking.

Taiga's external-apps mechanism issues one non-expiring token per (application,
user). The user's password is used exactly once, to log in and authorize the
application; only the application token is stored. Requests then authenticate
with ``Authorization: Application <token>`` and are attributed to the user.

Flow (both calls are taiga-back endpoints, no taiga-front round-trip needed):
1. POST /application-tokens/authorize {application, state} with the user's Bearer
   token -> {auth_code, state, next_url}
2. POST /application-tokens/validate {application, auth_code, state} -> {token}
3. GET /application-tokens -> find our application's entry to remember its id,
   so unlinking can DELETE it on the Taiga side. Best effort.
"""

import logging
import secrets
from typing import Optional, Tuple

from src.taiga_client import TaigaClientWrapper

logger = logging.getLogger(__name__)


def _application_id_of(entry: dict) -> Optional[str]:
    app = entry.get("application")
    if isinstance(app, dict):
        app = app.get("id")
    return str(app) if app is not None else None


def mint_application_token(bearer_client: TaigaClientWrapper, application_id: str) -> Tuple[str, Optional[int]]:
    """Return (application_token, taiga_app_token_id_or_None) for the logged-in user."""
    state = secrets.token_urlsafe(32)
    authorized = bearer_client.api.post(
        "/application-tokens/authorize",
        json={"application": application_id, "state": state},
    ) or {}
    auth_code = authorized.get("auth_code")
    if not auth_code:
        raise ValueError("Taiga did not return an auth_code for the application")

    validated = bearer_client.api.post(
        "/application-tokens/validate",
        json={"application": application_id, "auth_code": auth_code, "state": state},
    ) or {}
    token = validated.get("token")
    if not token:
        raise ValueError("Taiga did not return an application token")

    app_token_id: Optional[int] = None
    try:
        for entry in bearer_client.api.get("/application-tokens") or []:
            if _application_id_of(entry) == str(application_id):
                app_token_id = entry.get("id")
                break
    except Exception as e:  # revocation convenience only; linking must not fail on it
        logger.warning(f"Could not list application tokens to record the Taiga-side id: {e}")

    return token, app_token_id
