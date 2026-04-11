"""Configuration management with secure credential handling."""

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings

# Get the project root directory (parent of src/)
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"

# Load .env file from project root
load_dotenv(dotenv_path=ENV_FILE_PATH)


class TaigaSettings(BaseSettings):
    """Taiga MCP server settings with secure credential handling."""

    model_config = ConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Connection settings
    host: str = Field(
        default="http://localhost:9000",
        alias="TAIGA_API_URL",
        description="Taiga API base URL",
    )

    # Transport mode
    transport: str = Field(
        default="stdio",
        alias="TAIGA_TRANSPORT",
        description="Transport mode: 'stdio' or 'streamable-http'",
    )

    # Credentials (using SecretStr for security)
    username: Optional[SecretStr] = Field(
        default=None,
        alias="TAIGA_USERNAME",
        description="Taiga username for auto-authentication",
    )
    password: Optional[SecretStr] = Field(
        default=None,
        alias="TAIGA_PASSWORD",
        description="Taiga password for auto-authentication",
    )

    # OAuth settings (only used in streamable-http mode)
    oauth_issuer_url: Optional[str] = Field(
        default=None,
        alias="OAUTH_ISSUER_URL",
        description="Auth0 tenant URL (e.g., https://anamata.auth0.com/)",
    )
    oauth_audience: Optional[str] = Field(
        default=None,
        alias="OAUTH_AUDIENCE",
        description="MCP server resource identifier (e.g., https://taiga-mcp.hulsman.dev)",
    )
    oauth_required_scopes: Optional[str] = Field(
        default=None,
        alias="OAUTH_REQUIRED_SCOPES",
        description="Comma-separated required scopes (e.g., taiga:read,taiga:write)",
    )
    oauth_token_lifetime: int = Field(
        default=900,
        alias="OAUTH_TOKEN_LIFETIME",
        description="Expected token lifetime in seconds (for jti TTL)",
    )
    jwks_cache_ttl: int = Field(
        default=600,
        alias="JWKS_CACHE_TTL",
        description="JWKS cache duration in seconds",
    )

    # Credential store settings
    credential_encryption_key: Optional[SecretStr] = Field(
        default=None,
        alias="TAIGA_CREDENTIAL_ENCRYPTION_KEY",
        description="Fernet key for encrypting stored Taiga tokens",
    )
    credential_store_path: str = Field(
        default="~/.taiga-mcp/credentials.db",
        alias="TAIGA_CREDENTIAL_STORE_PATH",
        description="Path to credential store SQLite database",
    )

    # Browser linking flow settings
    oauth_link_client_id: Optional[str] = Field(
        default=None,
        alias="OAUTH_LINK_CLIENT_ID",
        description="Auth0 app client ID for the browser linking flow",
    )
    oauth_link_client_secret: Optional[SecretStr] = Field(
        default=None,
        alias="OAUTH_LINK_CLIENT_SECRET",
        description="Auth0 app client secret for the browser linking flow",
    )
    link_session_ttl: int = Field(
        default=600,
        alias="LINK_SESSION_TTL",
        description="Session cookie TTL in seconds for linking flow",
    )

    @property
    def has_credentials(self) -> bool:
        """Check if credentials are available for auto-auth."""
        return bool(self.username and self.password)

    @property
    def has_oauth_config(self) -> bool:
        """Check if OAuth settings are configured."""
        return bool(self.oauth_issuer_url and self.oauth_audience)

    @property
    def scopes_list(self) -> list[str]:
        """Parse comma-separated scopes into a list."""
        if not self.oauth_required_scopes:
            return []
        return [s.strip() for s in self.oauth_required_scopes.split(",") if s.strip()]

    def get_username_value(self) -> Optional[str]:
        """Safely get username value."""
        return self.username.get_secret_value() if self.username else None

    def get_password_value(self) -> Optional[str]:
        """Safely get password value."""
        return self.password.get_secret_value() if self.password else None

    def get_encryption_key(self) -> Optional[str]:
        """Safely get encryption key value."""
        return (
            self.credential_encryption_key.get_secret_value()
            if self.credential_encryption_key
            else None
        )

    def get_link_client_secret(self) -> Optional[str]:
        """Safely get link client secret value."""
        return (
            self.oauth_link_client_secret.get_secret_value()
            if self.oauth_link_client_secret
            else None
        )


def mask_credential(value: str, visible_chars: int = 2) -> str:
    """Mask a credential for safe logging."""
    if not value:
        return "<empty>"
    if len(value) <= visible_chars * 2:
        return "*" * len(value)
    return (
        f"{value[:visible_chars]}{'*' * (len(value) - visible_chars * 2)}{value[-visible_chars:]}"
    )


# Global settings instance
settings = TaigaSettings()
