"""OAuth-to-Taiga session bridge.

Maps OAuth user identities (sub claims) to Taiga API clients.
Uses TTLCache for in-memory session eviction and per-user locks
for thread-safe access to non-thread-safe requests.Session objects.
"""

import asyncio
import logging
from typing import Optional

import anyio
from cachetools import TTLCache

from src.auth.credential_store import TaigaCredentialStore
from src.taiga_client import TaigaClientWrapper

logger = logging.getLogger(__name__)


class OAuthSessionBridge:
    """Bridges OAuth identity to Taiga API sessions.

    Each OAuth user (identified by `sub` claim) gets their own TaigaClientWrapper
    initialized with a stored Taiga auth token. Clients are cached in memory
    with TTL eviction.

    Per-user concurrency control: Each user gets an asyncio.Lock. This ensures
    that concurrent MCP requests for the same user are serialized before dispatching
    to the thread pool, preventing two threads from accessing the same non-thread-safe
    requests.Session simultaneously. Different users run fully in parallel.
    """

    def __init__(self, taiga_host: str, credential_store: TaigaCredentialStore):
        self.taiga_host = taiga_host
        self.credential_store = credential_store
        # TTLCache: max 100 sessions, 30min TTL
        self._active_clients: TTLCache = TTLCache(maxsize=100, ttl=1800)
        # Per-user locks to serialize concurrent requests for the same user
        self._user_locks: TTLCache = TTLCache(maxsize=100, ttl=1800)

    async def get_client(self, oauth_sub: str) -> Optional[TaigaClientWrapper]:
        """Get a Taiga client for the given OAuth user, with per-user locking."""
        if oauth_sub not in self._user_locks:
            self._user_locks[oauth_sub] = asyncio.Lock()
        lock = self._user_locks[oauth_sub]

        async with lock:
            return await anyio.to_thread.run_sync(
                lambda: self._get_client_sync(oauth_sub)
            )

    def _get_client_sync(self, oauth_sub: str) -> Optional[TaigaClientWrapper]:
        """Synchronous client resolution (runs in thread pool)."""
        # 1. Check in-memory TTLCache
        if oauth_sub in self._active_clients:
            client = self._active_clients[oauth_sub]
            if client.is_authenticated:
                return client

        # 2. Fall back to credential store (synchronous sqlite3)
        taiga_token = self.credential_store.get_taiga_token(oauth_sub)
        if taiga_token:
            client = TaigaClientWrapper(host=self.taiga_host)
            client.set_token(taiga_token)
            self._active_clients[oauth_sub] = client
            return client

        # 3. Not linked
        return None

    def handle_taiga_auth_failure(self, oauth_sub: str):
        """Called when Taiga returns 401. Auto-unlink stale tokens."""
        self._active_clients.pop(oauth_sub, None)
        self.credential_store.remove_user(oauth_sub)
        self._user_locks.pop(oauth_sub, None)
        logger.warning(f"Auto-unlinked user {oauth_sub[:8]}... due to Taiga auth failure")

    def invalidate_cached_client(self, oauth_sub: str):
        """Remove a user's cached client (without removing stored credentials)."""
        self._active_clients.pop(oauth_sub, None)
