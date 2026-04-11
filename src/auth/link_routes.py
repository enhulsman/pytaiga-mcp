"""Browser-based credential linking routes.

Provides a standalone OAuth + HTML form flow for linking Taiga accounts
to OAuth identities. Passwords never transit through MCP/Claude.

Flow:
1. User visits /link-account -> OAuth redirect to Auth0 (PKCE)
2. Auth0 callback -> session cookie set
3. /link-account/form -> HTML form for Taiga credentials
4. POST /link-account/form -> authenticate to Taiga, store token
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.parse
from typing import Optional

import anyio
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from src.auth.credential_store import TaigaCredentialStore
from src.config import settings
from src.taiga_client import TaigaClientWrapper

logger = logging.getLogger(__name__)

# In-memory PKCE state dict -- requires single-process deployment
_pending_states: dict[str, dict] = {}
STATE_TTL = 300  # 5 minutes


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return code_verifier, code_challenge


def _cleanup_expired_states():
    """Remove expired PKCE state entries."""
    now = time.time()
    expired = [k for k, v in _pending_states.items() if now - v["created_at"] > STATE_TTL]
    for k in expired:
        del _pending_states[k]


def _derive_session_key(fernet_key: str) -> bytes:
    """Derive session signing key from Fernet key (domain separation)."""
    return hmac.new(
        fernet_key.encode(), b"taiga-mcp:link-session", hashlib.sha256
    ).digest()


def _sign_session(sub: str, session_key: bytes, ttl: int) -> str:
    """Create a signed session cookie value."""
    payload = json.dumps({"sub": sub, "exp": int(time.time()) + ttl})
    signature = hmac.new(session_key, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{signature}".encode()).decode()


def _verify_session(cookie_value: str, session_key: bytes) -> Optional[str]:
    """Verify session cookie and return sub if valid."""
    try:
        decoded = base64.urlsafe_b64decode(cookie_value.encode()).decode()
        payload_str, signature = decoded.rsplit("|", 1)
        expected = hmac.new(session_key, payload_str.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(payload_str)
        if payload.get("exp", 0) < time.time():
            return None
        return payload.get("sub")
    except Exception:
        return None


def create_link_routes(credential_store: TaigaCredentialStore) -> list[Route]:
    """Create Starlette routes for the credential linking flow."""

    encryption_key = settings.get_encryption_key()
    if not encryption_key:
        logger.warning("No encryption key configured, link routes disabled")
        return []

    session_key = _derive_session_key(encryption_key)
    link_client_id = settings.oauth_link_client_id
    link_client_secret = settings.get_link_client_secret()
    issuer_url = settings.oauth_issuer_url.rstrip("/") if settings.oauth_issuer_url else ""
    audience = settings.oauth_audience or ""
    session_ttl = settings.link_session_ttl

    def _is_secure_request(request: Request) -> bool:
        """Check if the request came over HTTPS (or via a trusted proxy like CF)."""
        if request.url.scheme == "https":
            return True
        # Cloudflare/reverse proxy sets this header
        if request.headers.get("x-forwarded-proto") == "https":
            return True
        return False

    async def link_account(request: Request) -> Response:
        """Initiate Auth0 OAuth redirect with PKCE."""
        if not link_client_id or not issuer_url:
            return HTMLResponse("<h1>Linking not configured</h1>", status_code=503)

        _cleanup_expired_states()

        state = secrets.token_urlsafe(32)
        code_verifier, code_challenge = _generate_pkce()
        _pending_states[state] = {
            "code_verifier": code_verifier,
            "created_at": time.time(),
        }

        # Build callback URL from request
        callback_url = str(request.url_for("link_callback"))

        params = {
            "response_type": "code",
            "client_id": link_client_id,
            "redirect_uri": callback_url,
            "scope": "openid profile",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "audience": audience,
        }
        auth_url = f"{issuer_url}/authorize?{urllib.parse.urlencode(params)}"
        return RedirectResponse(url=auth_url)

    async def link_callback(request: Request) -> Response:
        """Auth0 callback: exchange code for token, set session cookie."""
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")

        if error:
            return HTMLResponse(f"<h1>Auth Error</h1><p>{error}</p>", status_code=400)

        if not code or not state or state not in _pending_states:
            return HTMLResponse("<h1>Invalid callback</h1>", status_code=400)

        state_data = _pending_states.pop(state)
        code_verifier = state_data["code_verifier"]
        callback_url = str(request.url_for("link_callback"))

        # Exchange code for token at Auth0
        import httpx

        token_data = {
            "grant_type": "authorization_code",
            "client_id": link_client_id,
            "code": code,
            "redirect_uri": callback_url,
            "code_verifier": code_verifier,
        }
        if link_client_secret:
            token_data["client_secret"] = link_client_secret

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{issuer_url}/oauth/token",
                    data=token_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if resp.status_code != 200:
                    logger.error(f"Token exchange failed: {resp.status_code} {resp.text}")
                    return HTMLResponse("<h1>Token exchange failed</h1>", status_code=502)

                token_resp = resp.json()
        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return HTMLResponse("<h1>Token exchange error</h1>", status_code=502)

        # Decode JWT to get sub (without validation - we just got it from Auth0)
        import jwt as pyjwt

        try:
            claims = pyjwt.decode(
                token_resp["access_token"],
                options={"verify_signature": False},
            )
            sub = claims.get("sub")
        except Exception:
            return HTMLResponse("<h1>Invalid token</h1>", status_code=400)

        if not sub:
            return HTMLResponse("<h1>Missing sub claim</h1>", status_code=400)

        # Set session cookie and redirect to form
        session_value = _sign_session(sub, session_key, session_ttl)
        response = RedirectResponse(url=str(request.url_for("link_form")))
        response.set_cookie(
            "taiga_link_session",
            session_value,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=session_ttl,
        )
        return response

    async def link_form(request: Request) -> Response:
        """Serve HTML form for Taiga credentials."""
        cookie = request.cookies.get("taiga_link_session")
        sub = _verify_session(cookie, session_key) if cookie else None
        if not sub:
            return HTMLResponse("<h1>Session expired</h1><p>Please start over.</p>", status_code=401)

        is_linked = credential_store.is_linked(sub)
        status_msg = '<p style="color:green">Your Taiga account is already linked. Submit to re-link.</p>' if is_linked else ""

        html = f"""<!DOCTYPE html>
<html>
<head><title>Link Taiga Account</title>
<style>body{{font-family:sans-serif;max-width:400px;margin:50px auto;padding:20px}}
input{{width:100%;padding:8px;margin:5px 0 15px;box-sizing:border-box}}
button{{padding:10px 20px;background:#4c566a;color:white;border:none;cursor:pointer}}
button:hover{{background:#3b4252}}</style></head>
<body>
<h1>Link Taiga Account</h1>
{status_msg}
<p>Enter your Taiga credentials to link your account. Your password is sent directly to the Taiga server and is never stored.</p>
<form method="POST" action="{request.url_for('link_form_submit')}">
<label>Taiga Username</label>
<input type="text" name="username" required autocomplete="username">
<label>Taiga Password</label>
<input type="password" name="password" required autocomplete="current-password">
<button type="submit">Link Account</button>
</form>
</body></html>"""
        return HTMLResponse(html)

    async def link_form_submit(request: Request) -> Response:
        """Process form submission: authenticate to Taiga, store token."""
        cookie = request.cookies.get("taiga_link_session")
        sub = _verify_session(cookie, session_key) if cookie else None
        if not sub:
            return HTMLResponse("<h1>Session expired</h1>", status_code=401)

        form = await request.form()
        username = form.get("username", "").strip()
        password = form.get("password", "")

        if not username or not password:
            return HTMLResponse("<h1>Username and password required</h1>", status_code=400)

        # Authenticate to Taiga in thread pool (blocking I/O)
        try:
            def _do_taiga_login():
                client = TaigaClientWrapper(host=settings.host)
                client.login(username=username, password=password)
                return client.api.auth_token

            taiga_token = await anyio.to_thread.run_sync(_do_taiga_login)
        except Exception as e:
            logger.error(f"Taiga login failed during linking: {e}")
            return HTMLResponse(
                "<h1>Taiga Login Failed</h1><p>Check your credentials and try again.</p>",
                status_code=401,
            )

        # Store encrypted token
        credential_store.store_taiga_token(sub, taiga_token)

        # Clear session cookie
        response = HTMLResponse(
            "<h1>Account Linked!</h1><p>You can close this window and return to Claude.</p>"
        )
        response.delete_cookie("taiga_link_session")
        return response

    async def link_status(request: Request) -> Response:
        """Check if the current OAuth user is linked (via Bearer token or session cookie)."""
        # Try Bearer token first
        auth_header = request.headers.get("authorization", "")
        sub = None

        if auth_header.lower().startswith("bearer "):
            import jwt as pyjwt

            try:
                claims = pyjwt.decode(
                    auth_header[7:], options={"verify_signature": False}
                )
                sub = claims.get("sub")
            except Exception:
                pass

        # Fall back to session cookie
        if not sub:
            cookie = request.cookies.get("taiga_link_session")
            sub = _verify_session(cookie, session_key) if cookie else None

        if not sub:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        linked = credential_store.is_linked(sub)
        return JSONResponse({"linked": linked, "oauth_sub": sub[:8] + "..."})

    async def unlink_account(request: Request) -> Response:
        """Remove credential mapping."""
        auth_header = request.headers.get("authorization", "")
        sub = None

        if auth_header.lower().startswith("bearer "):
            import jwt as pyjwt

            try:
                claims = pyjwt.decode(
                    auth_header[7:], options={"verify_signature": False}
                )
                sub = claims.get("sub")
            except Exception:
                pass

        if not sub:
            cookie = request.cookies.get("taiga_link_session")
            sub = _verify_session(cookie, session_key) if cookie else None

        if not sub:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        credential_store.remove_user(sub)
        return JSONResponse({"status": "unlinked", "oauth_sub": sub[:8] + "..."})

    return [
        Route("/link-account", link_account, methods=["GET"], name="link_account"),
        Route("/link-account/callback", link_callback, methods=["GET"], name="link_callback"),
        Route("/link-account/form", link_form, methods=["GET"], name="link_form"),
        Route("/link-account/form", link_form_submit, methods=["POST"], name="link_form_submit"),
        Route("/link-status", link_status, methods=["GET"]),
        Route("/unlink-account", unlink_account, methods=["POST"]),
    ]
