"""SQLite-backed credential store with Fernet encryption.

Maps OAuth sub claims to encrypted Taiga auth tokens.
Uses SQLite with WAL mode for concurrent-safe access.
"""

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class TaigaCredentialStore:
    """SQLite-backed credential store with Fernet encryption for token values.

    Storage details:
    - Token values encrypted with Fernet before storing in SQLite
    - WAL mode allows concurrent reads during writes
    - All methods are synchronous (stdlib sqlite3). Callers in HTTP mode
      wrap with anyio.to_thread.run_sync() for async safety.
    """

    def __init__(self, db_path: str, encryption_key: str):
        self.db_path = Path(db_path).expanduser()
        self.fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.db_path))
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                oauth_sub TEXT PRIMARY KEY,
                taiga_token_encrypted BLOB NOT NULL,
                linked_at REAL NOT NULL,
                last_used_at REAL
            )
        """)
        db.commit()
        db.close()

        # Restrict file permissions (owner read/write only)
        try:
            os.chmod(str(self.db_path), 0o600)
        except OSError:
            logger.warning(f"Could not set permissions on {self.db_path}")

    def get_taiga_token(self, oauth_sub: str) -> Optional[str]:
        """Get and decrypt cached Taiga auth token."""
        db = sqlite3.connect(str(self.db_path))
        try:
            row = db.execute(
                "SELECT taiga_token_encrypted FROM credentials WHERE oauth_sub = ?",
                (oauth_sub,),
            ).fetchone()
            if row:
                try:
                    token = self.fernet.decrypt(row[0]).decode()
                    # Update last_used_at
                    db.execute(
                        "UPDATE credentials SET last_used_at = ? WHERE oauth_sub = ?",
                        (time.time(), oauth_sub),
                    )
                    db.commit()
                    return token
                except InvalidToken:
                    logger.error(f"Failed to decrypt token for user {oauth_sub[:8]}...")
                    return None
            return None
        finally:
            db.close()

    def store_taiga_token(self, oauth_sub: str, taiga_auth_token: str):
        """Encrypt and store Taiga auth token."""
        encrypted = self.fernet.encrypt(taiga_auth_token.encode())
        db = sqlite3.connect(str(self.db_path))
        try:
            db.execute(
                """INSERT OR REPLACE INTO credentials
                   (oauth_sub, taiga_token_encrypted, linked_at, last_used_at)
                   VALUES (?, ?, ?, ?)""",
                (oauth_sub, encrypted, time.time(), time.time()),
            )
            db.commit()
            logger.info(f"Stored Taiga token for user {oauth_sub[:8]}...")
        finally:
            db.close()

    def remove_user(self, oauth_sub: str):
        """Remove a user's credentials (revocation/unlinking)."""
        db = sqlite3.connect(str(self.db_path))
        try:
            db.execute("DELETE FROM credentials WHERE oauth_sub = ?", (oauth_sub,))
            db.commit()
            logger.info(f"Removed credentials for user {oauth_sub[:8]}...")
        finally:
            db.close()

    def is_linked(self, oauth_sub: str) -> bool:
        """Check if a user has linked their Taiga account."""
        db = sqlite3.connect(str(self.db_path))
        try:
            row = db.execute(
                "SELECT 1 FROM credentials WHERE oauth_sub = ?",
                (oauth_sub,),
            ).fetchone()
            return row is not None
        finally:
            db.close()
