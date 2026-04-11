"""Tests for SQLite credential store."""

import os
import tempfile

import pytest
from cryptography.fernet import Fernet

from src.auth.credential_store import TaigaCredentialStore


@pytest.fixture
def store():
    """Create a temporary credential store for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_credentials.db")
        key = Fernet.generate_key().decode()
        yield TaigaCredentialStore(db_path=db_path, encryption_key=key)


@pytest.fixture
def store_path():
    """Return a temporary directory for credential store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestCredentialStore:
    def test_store_and_retrieve_token(self, store):
        """Round-trip: store encrypted token, retrieve decrypted."""
        store.store_taiga_token("auth0|user1", "taiga-token-abc123")
        token = store.get_taiga_token("auth0|user1")
        assert token == "taiga-token-abc123"

    def test_get_nonexistent_user(self, store):
        """Getting token for unknown user returns None."""
        assert store.get_taiga_token("auth0|unknown") is None

    def test_is_linked(self, store):
        """is_linked returns correct status."""
        assert not store.is_linked("auth0|user1")
        store.store_taiga_token("auth0|user1", "token")
        assert store.is_linked("auth0|user1")

    def test_remove_user(self, store):
        """Removing user clears their credentials."""
        store.store_taiga_token("auth0|user1", "token")
        assert store.is_linked("auth0|user1")
        store.remove_user("auth0|user1")
        assert not store.is_linked("auth0|user1")
        assert store.get_taiga_token("auth0|user1") is None

    def test_replace_existing_token(self, store):
        """Storing again replaces the existing token."""
        store.store_taiga_token("auth0|user1", "old-token")
        store.store_taiga_token("auth0|user1", "new-token")
        assert store.get_taiga_token("auth0|user1") == "new-token"

    def test_multiple_users(self, store):
        """Multiple users can be stored independently."""
        store.store_taiga_token("auth0|user1", "token1")
        store.store_taiga_token("auth0|user2", "token2")
        assert store.get_taiga_token("auth0|user1") == "token1"
        assert store.get_taiga_token("auth0|user2") == "token2"

    def test_remove_one_user_preserves_others(self, store):
        """Removing one user doesn't affect others."""
        store.store_taiga_token("auth0|user1", "token1")
        store.store_taiga_token("auth0|user2", "token2")
        store.remove_user("auth0|user1")
        assert not store.is_linked("auth0|user1")
        assert store.get_taiga_token("auth0|user2") == "token2"

    def test_wrong_encryption_key_returns_none(self, store_path):
        """Reading with a different key returns None (decrypt failure)."""
        db_path = os.path.join(store_path, "test.db")
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        store1 = TaigaCredentialStore(db_path=db_path, encryption_key=key1)
        store1.store_taiga_token("auth0|user1", "secret-token")

        store2 = TaigaCredentialStore(db_path=db_path, encryption_key=key2)
        assert store2.get_taiga_token("auth0|user1") is None

    def test_db_directory_created(self, store_path):
        """Store creates parent directories if they don't exist."""
        db_path = os.path.join(store_path, "subdir", "nested", "test.db")
        key = Fernet.generate_key().decode()
        store = TaigaCredentialStore(db_path=db_path, encryption_key=key)
        store.store_taiga_token("auth0|user1", "token")
        assert os.path.exists(db_path)

    def test_remove_nonexistent_user_no_error(self, store):
        """Removing a non-existent user doesn't raise."""
        store.remove_user("auth0|nonexistent")  # Should not raise
