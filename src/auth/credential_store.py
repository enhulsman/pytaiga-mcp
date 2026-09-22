"""SQLite-backed credential store with Fernet encryption.

Maps OAuth sub claims to encrypted Taiga application tokens, plus the id of the
token on the Taiga side so it can be revoked there on unlink.
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
                last_used_at REAL,
                taiga_app_token_id INTEGER
            )
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(credentials)")}
        if "taiga_app_token_id" not in columns:
            db.execute("ALTER TABLE credentials ADD COLUMN taiga_app_token_id INTEGER")
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

    def store_taiga_token(self, oauth_sub: str, taiga_auth_token: str, app_token_id: Optional[int] = None):
        """Encrypt and store a Taiga token, with the Taiga-side application-token id if known."""
        encrypted = self.fernet.encrypt(taiga_auth_token.encode())
        db = sqlite3.connect(str(self.db_path))
        try:
            db.execute(
                """INSERT OR REPLACE INTO credentials
                   (oauth_sub, taiga_token_encrypted, linked_at, last_used_at, taiga_app_token_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (oauth_sub, encrypted, time.time(), time.time(), app_token_id),
            )
            db.commit()
            logger.info(f"Stored Taiga token for user {oauth_sub[:8]}...")
        finally:
            db.close()

    def get_app_token_id(self, oauth_sub: str) -> Optional[int]:
        """Id of the user's application token on the Taiga side (None if unknown or unlinked)."""
        db = sqlite3.connect(str(self.db_path))
        try:
            row = db.execute(
                "SELECT taiga_app_token_id FROM credentials WHERE oauth_sub = ?",
                (oauth_sub,),
            ).fetchone()
            return row[0] if row and row[0] is not None else None
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
