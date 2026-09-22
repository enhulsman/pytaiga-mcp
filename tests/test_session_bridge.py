"""Tests for OAuth session bridge."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from src.auth.credential_store import TaigaCredentialStore
from src.auth.session_bridge import OAuthSessionBridge


@pytest.fixture
def credential_store():
    """Create a temporary credential store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_credentials.db")
        key = Fernet.generate_key().decode()
        yield TaigaCredentialStore(db_path=db_path, encryption_key=key)


@pytest.fixture
def bridge(credential_store):
    """Create a session bridge with test credential store."""
    return OAuthSessionBridge(
        taiga_host="https://taiga.test.dev",
        credential_store=credential_store,
    )


class TestSessionBridge:
    @pytest.mark.asyncio
    async def test_unlinked_user_returns_none(self, bridge):
        """Unlinked user gets None client."""
        client = await bridge.get_client("auth0|unknown")
        assert client is None

    @pytest.mark.asyncio
    async def test_linked_user_gets_client(self, bridge, credential_store):
        """Linked user gets a TaigaClientWrapper with set_token called."""
        credential_store.store_taiga_token("auth0|user1", "test-taiga-token")

        with patch("src.auth.session_bridge.TaigaClientWrapper") as MockClient:
            mock_instance = MagicMock()
            mock_instance.is_authenticated = True
            MockClient.return_value = mock_instance

            client = await bridge.get_client("auth0|user1")
            assert client is not None
            mock_instance.set_token.assert_called_once_with("test-taiga-token", token_type="Application")

    @pytest.mark.asyncio
    async def test_cached_client_reused(self, bridge, credential_store):
        """Second call reuses cached client, doesn't hit credential store again."""
        credential_store.store_taiga_token("auth0|user1", "test-token")

        with patch("src.auth.session_bridge.TaigaClientWrapper") as MockClient:
            mock_instance = MagicMock()
            mock_instance.is_authenticated = True
            MockClient.return_value = mock_instance

            # First call creates client
            client1 = await bridge.get_client("auth0|user1")
            # Second call should reuse cached
            client2 = await bridge.get_client("auth0|user1")

            assert client1 is client2
            # TaigaClientWrapper should only be created once
            assert MockClient.call_count == 1

    @pytest.mark.asyncio
    async def test_handle_auth_failure_unlinks(self, bridge, credential_store):
        """Auth failure removes cached client and stored credentials."""
        credential_store.store_taiga_token("auth0|user1", "test-token")

        with patch("src.auth.session_bridge.TaigaClientWrapper") as MockClient:
            mock_instance = MagicMock()
            mock_instance.is_authenticated = True
            MockClient.return_value = mock_instance

            await bridge.get_client("auth0|user1")

        # Now handle auth failure
        bridge.handle_taiga_auth_failure("auth0|user1")

        # Should be unlinked from credential store
        assert not credential_store.is_linked("auth0|user1")

        # Cache should be empty, next call returns None
        client = await bridge.get_client("auth0|user1")
        assert client is None

    def test_invalidate_cached_client(self, bridge):
        """invalidate_cached_client removes from cache but not credential store."""
        # Put something in cache manually
        bridge._active_clients["auth0|user1"] = MagicMock()

        bridge.invalidate_cached_client("auth0|user1")
        assert "auth0|user1" not in bridge._active_clients

    @pytest.mark.asyncio
    async def test_different_users_independent(self, bridge, credential_store):
        """Different users get independent clients."""
        credential_store.store_taiga_token("auth0|user1", "token1")
        credential_store.store_taiga_token("auth0|user2", "token2")

        with patch("src.auth.session_bridge.TaigaClientWrapper") as MockClient:
            mock1 = MagicMock()
            mock1.is_authenticated = True
            mock2 = MagicMock()
            mock2.is_authenticated = True
            MockClient.side_effect = [mock1, mock2]

            client1 = await bridge.get_client("auth0|user1")
            client2 = await bridge.get_client("auth0|user2")

            assert client1 is not client2
            mock1.set_token.assert_called_once_with("token1", token_type="Application")
            mock2.set_token.assert_called_once_with("token2", token_type="Application")


class TestApplicationTokenBridge:
    def test_client_uses_application_token_type(self, bridge, credential_store):
        credential_store.store_taiga_token("auth0|user1", "app-token", app_token_id=42)
        with patch("src.auth.session_bridge.TaigaClientWrapper") as MockClient:
            instance = MagicMock()
            instance.is_authenticated = True
            MockClient.return_value = instance
            client = bridge.get_client_sync("auth0|user1")
        assert client is instance
        instance.set_token.assert_called_once_with("app-token", token_type="Application")

    def test_get_client_sync_unlinked_returns_none(self, bridge):
        assert bridge.get_client_sync("auth0|unknown") is None

    def test_unlink_revokes_in_taiga_and_removes_locally(self, bridge, credential_store):
        credential_store.store_taiga_token("auth0|user1", "app-token", app_token_id=42)
        with patch("src.auth.session_bridge.TaigaClientWrapper") as MockClient:
            instance = MagicMock()
            instance.is_authenticated = True
            MockClient.return_value = instance
            revoked = bridge.unlink("auth0|user1")
        assert revoked is True
        instance.api.delete.assert_called_once_with("/application-tokens/42")
        assert credential_store.is_linked("auth0|user1") is False

    def test_unlink_still_removes_locally_when_taiga_call_fails(self, bridge, credential_store):
        credential_store.store_taiga_token("auth0|user1", "app-token", app_token_id=42)
        with patch("src.auth.session_bridge.TaigaClientWrapper") as MockClient:
            instance = MagicMock()
            instance.is_authenticated = True
            instance.api.delete.side_effect = RuntimeError("taiga down")
            MockClient.return_value = instance
            revoked = bridge.unlink("auth0|user1")
        assert revoked is False
        assert credential_store.is_linked("auth0|user1") is False

    def test_unlink_without_token_id_skips_taiga_call(self, bridge, credential_store):
        credential_store.store_taiga_token("auth0|user1", "app-token")
        with patch("src.auth.session_bridge.TaigaClientWrapper") as MockClient:
            instance = MagicMock()
            instance.is_authenticated = True
            MockClient.return_value = instance
            revoked = bridge.unlink("auth0|user1")
        assert revoked is False
        instance.api.delete.assert_not_called()
        assert credential_store.is_linked("auth0|user1") is False

    def test_unlink_unknown_user_is_noop(self, bridge):
        assert bridge.unlink("auth0|nobody") is False
