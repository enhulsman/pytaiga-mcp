# taiga_client.py
import logging
import math
import os
from contextvars import ContextVar
from time import monotonic
from typing import Optional

from pytaigaclient import TaigaClient
from pytaigaclient.exceptions import TaigaAuthenticationError, TaigaException

logger = logging.getLogger(__name__)

_auth_in_progress = ContextVar("taiga_auth_in_progress", default=False)


class _AuthLogFilter(logging.Filter):
    def filter(self, record):
        # The SDK logs credentials at DEBUG and raw error bodies at ERROR.
        # Suppress its records before any handler sees them, only in the
        # context doing authentication; other requests retain normal logging.
        return not _auth_in_progress.get()


logging.getLogger("pytaigaclient.client").addFilter(_AuthLogFilter())


class _LoginRejected(TaigaException):
    """The server explicitly rejected the login credentials (without its body)."""


class TransientReloginError(TaigaException):
    """Re-login failed without evidence that the stored credentials are invalid."""


class TaigaClientWrapper:
    """
    A wrapper around the pytaiga-client library to manage API instance
    and authentication state.
    """

    def __init__(self, host: str):
        if not host:
            raise ValueError("Taiga host URL cannot be empty.")
        # Store host, but initialize client later during login/token auth
        self.host = host
        # Use the new client type
        self.api: Optional[TaigaClient] = None
        self.logged_in_at: Optional[float] = None
        self._request_once = None
        logger.info(f"TaigaClientWrapper initialized for host: {self.host}")

    def login(self, username: str, password: str) -> bool:
        """
        Authenticates with the Taiga instance using username and password.
        Uses pytaigaclient.
        """
        try:
            # SECURITY: Don't log username to avoid credential exposure
            logger.info(f"Attempting login on {self.host}")
            # Initialize the client here
            api_instance = TaigaClient(host=self.host, disable_pagination=True)
            # Use the auth resource's login method
            auth_context = _auth_in_progress.set(True)
            try:
                api_instance.auth.login(username=username, password=password)
            finally:
                _auth_in_progress.reset(auth_context)
            logged_in_at = monotonic()
            # Resources dispatch through _request. Retry the rejected request,
            # rather than replaying a tool that may already have made changes.
            request_once = api_instance._request
            api_instance._request = self._request_with_relogin
            self._request_once = request_once
            self.api = api_instance
            self.logged_in_at = logged_in_at
            logger.info("Login successful. Auth token acquired.")
            return True
        except TaigaException as error:
            # SECURITY: Don't log username in error messages
            logger.error("Taiga login failed on %s", self.host)
            # Callers may log this exception, so never propagate an auth body.
            # Leave the current client intact if a replacement login fails.
            if isinstance(error, TaigaAuthenticationError) and error.status_code in (401, 403):
                raise _LoginRejected("Taiga login failed.") from None
            raise TaigaException("Taiga login failed.") from None
        except Exception:
            # SECURITY: Don't log username in error messages
            logger.error("Unexpected login error on %s", self.host)
            # Wrap unexpected errors in TaigaException if needed, or re-raise
            raise TaigaException("Unexpected login error.") from None

    def _can_relogin(self) -> bool:
        # Read credentials only when needed; never retain them on this wrapper.
        from src import session

        return (
            not session.is_oauth_mode()
            and session.settings.transport == "stdio"
            and session.active_sessions.get(session.DEFAULT_SESSION_ID) is self
            and self.host == session.settings.host
            and session.settings.has_credentials
            and self.logged_in_at is not None
        )

    def _relogin(self):
        from src.session import settings

        logger.info("Taiga re-login on %s", self.host)
        try:
            self.login(settings.get_username_value(), settings.get_password_value())
        except _LoginRejected:
            raise _LoginRejected("Taiga re-login failed.") from None
        except TaigaException:
            # Upstream error bodies may echo the credentials used to log in.
            raise TransientReloginError("Taiga re-login failed.") from None

    def should_invalidate_after_status_failure(self, error: TaigaException) -> bool:
        """Keep the recoverable default session unless authentication was rejected."""
        if not self._can_relogin():
            return True
        # A status 403 is a permission failure; only a login rejection or a
        # status 401 remaining after the single retry proves auth is invalid.
        return isinstance(error, _LoginRejected) or (
            isinstance(error, TaigaAuthenticationError) and error.status_code == 401
        )

    def refresh_if_expired(self):
        """Refresh only the environment-backed stdio default session."""
        if not self._can_relogin():
            return
        try:
            max_age = float(os.environ.get("TAIGA_RELOGIN_MAX_AGE_SECONDS", 23 * 3600))
            if not math.isfinite(max_age) or max_age <= 0:
                raise ValueError
        except ValueError:
            raise ValueError(
                "TAIGA_RELOGIN_MAX_AGE_SECONDS must be a positive finite number."
            ) from None
        if monotonic() - self.logged_in_at > max_age:
            self._relogin()

    def _request_with_relogin(self, *args, **kwargs):
        try:
            return self._request_once(*args, **kwargs)
        except TaigaAuthenticationError as error:
            if error.status_code != 401 or not self._can_relogin():
                raise
            self._relogin()
            # Bypass this handler so a second 401 is propagated unchanged.
            return self._request_once(*args, **kwargs)

    def set_token(self, token: str, token_type: str = "Bearer"):
        """Initialize TaigaClient with a pre-existing auth token (for OAuth mode)."""
        logger.info(f"Initializing TaigaClient with token on {self.host}")
        self.logged_in_at = None
        self._request_once = None
        self.api = TaigaClient(
            host=self.host, auth_token=token, token_type=token_type, disable_pagination=True
        )
        logger.info("TaigaClient initialized with token.")

    @property
    def is_authenticated(self) -> bool:
        """Checks if the client is currently authenticated (has an API instance with a token)."""
        # Check if api exists and has a token
        return self.api is not None and self.api.auth_token is not None

    def _ensure_authenticated(self):
        """Internal helper to check authentication before API calls."""
        if not self.is_authenticated:
            logger.error("Action required authentication, but client is not logged in.")
            raise PermissionError("Client not authenticated. Please login first.")
