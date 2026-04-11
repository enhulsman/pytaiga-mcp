"""JWT token verification via Auth0 JWKS.

Implements the MCP SDK's TokenVerifier protocol for validating
Bearer tokens issued by Auth0.
"""

import logging

import jwt
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)


class Auth0TokenVerifier:
    """Validates JWTs against Auth0's JWKS endpoint.

    Implements the MCP SDK TokenVerifier protocol:
        async def verify_token(self, token: str) -> AccessToken | None

    JWKS caching strategy:
    - Primary: PyJWKClient with explicit lifespan TTL
    - Fallback: On JWKS fetch failure, use last known good keys
    - Key rotation: On signature failure, force JWKS refresh once before rejecting
    """

    def __init__(self, issuer_url: str, audience: str, jwks_cache_ttl: int = 600):
        self.issuer_url = issuer_url.rstrip("/") + "/"
        self.audience = audience
        self._jwks_client = jwt.PyJWKClient(
            f"{self.issuer_url}.well-known/jwks.json",
            cache_jwk_set=True,
            lifespan=jwks_cache_ttl,
        )
        self._last_good_keys = None

    def _get_signing_key(self, token: str, force_refresh: bool = False):
        """Get signing key from JWKS, with fallback cache."""
        try:
            if force_refresh:
                # Force cache invalidation for key rotation handling
                self._jwks_client.fetch_data()
            key = self._jwks_client.get_signing_key_from_jwt(token)
            self._last_good_keys = key
            return key
        except jwt.exceptions.PyJWKClientConnectionError:
            if self._last_good_keys:
                logger.warning("JWKS fetch failed, using cached keys")
                return self._last_good_keys
            raise

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a Bearer token and return AccessToken if valid.

        Maps JWT `sub` claim into AccessToken.client_id for user identity.
        The SDK uses client_id but we need per-user identity, so we repurpose it.
        """
        try:
            signing_key = self._get_signing_key(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer_url,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
            return AccessToken(
                token=token,
                client_id=payload["sub"],
                scopes=payload.get("scope", "").split(),
                expires_at=payload.get("exp"),
            )
        except jwt.exceptions.InvalidSignatureError:
            # Key rotation: try refreshing JWKS once
            try:
                signing_key = self._get_signing_key(token, force_refresh=True)
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=self.audience,
                    issuer=self.issuer_url,
                    options={"require": ["exp", "iss", "aud", "sub"]},
                )
                return AccessToken(
                    token=token,
                    client_id=payload["sub"],
                    scopes=payload.get("scope", "").split(),
                    expires_at=payload.get("exp"),
                )
            except jwt.exceptions.PyJWTError:
                logger.warning("Token verification failed after JWKS refresh")
                return None
        except jwt.exceptions.PyJWTError as e:
            logger.warning(f"Token verification failed: {e}")
            # Log token prefix to help diagnose opaque vs JWT issues
            if token and not token.startswith("eyJ"):
                logger.warning("Token does not look like a JWT (no eyJ prefix) — Auth0 may be issuing opaque tokens. Set Default Audience in Auth0 tenant settings.")
            return None
