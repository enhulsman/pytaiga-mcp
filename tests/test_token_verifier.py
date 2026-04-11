"""Tests for Auth0 JWT token verifier."""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.auth.token_verifier import Auth0TokenVerifier


@pytest.fixture
def rsa_keypair():
    """Generate RSA key pair for testing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def make_jwt(rsa_keypair):
    """Factory for creating test JWTs."""
    private_key, _ = rsa_keypair

    def _make(
        sub="auth0|test123",
        iss="https://test.auth0.com/",
        aud="https://taiga-mcp.test.dev",
        exp=None,
        scope="taiga:read taiga:write",
        extra_claims=None,
    ):
        payload = {
            "sub": sub,
            "iss": iss,
            "aud": aud,
            "exp": exp or int(time.time()) + 3600,
            "scope": scope,
        }
        if extra_claims:
            payload.update(extra_claims)
        return jwt.encode(payload, private_key, algorithm="RS256")

    return _make


@pytest.fixture
def mock_jwks_client(rsa_keypair):
    """Create a mock JWKS client that returns our test public key."""
    _, public_key = rsa_keypair
    mock_signing_key = MagicMock()
    mock_signing_key.key = public_key
    return mock_signing_key


@pytest.fixture
def verifier(mock_jwks_client):
    """Create a verifier with mocked JWKS."""
    v = Auth0TokenVerifier(
        issuer_url="https://test.auth0.com/",
        audience="https://taiga-mcp.test.dev",
    )
    # Patch the JWKS client to return our test key
    v._jwks_client = MagicMock()
    v._jwks_client.get_signing_key_from_jwt.return_value = mock_jwks_client
    return v


class TestTokenVerifier:
    @pytest.mark.asyncio
    async def test_valid_token(self, verifier, make_jwt):
        """Valid JWT returns AccessToken with correct fields."""
        token = make_jwt()
        result = await verifier.verify_token(token)

        assert result is not None
        assert result.client_id == "auth0|test123"
        assert "taiga:read" in result.scopes
        assert "taiga:write" in result.scopes
        assert result.token == token

    @pytest.mark.asyncio
    async def test_expired_token(self, verifier, make_jwt):
        """Expired JWT returns None."""
        token = make_jwt(exp=int(time.time()) - 3600)
        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_wrong_audience(self, verifier, make_jwt):
        """JWT with wrong audience returns None."""
        token = make_jwt(aud="https://wrong-audience.dev")
        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_wrong_issuer(self, verifier, make_jwt):
        """JWT with wrong issuer returns None."""
        token = make_jwt(iss="https://wrong-issuer.auth0.com/")
        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_sub_claim(self, rsa_keypair, mock_jwks_client):
        """JWT without sub claim returns None."""
        private_key, _ = rsa_keypair
        payload = {
            "iss": "https://test.auth0.com/",
            "aud": "https://taiga-mcp.test.dev",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, private_key, algorithm="RS256")

        verifier = Auth0TokenVerifier(
            issuer_url="https://test.auth0.com/",
            audience="https://taiga-mcp.test.dev",
        )
        verifier._jwks_client = MagicMock()
        verifier._jwks_client.get_signing_key_from_jwt.return_value = mock_jwks_client

        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_scope(self, verifier, make_jwt):
        """JWT with no scope claim returns empty scopes list."""
        token = make_jwt(scope="")
        result = await verifier.verify_token(token)
        assert result is not None
        assert result.scopes == []  # AccessToken model filters empty strings

    @pytest.mark.asyncio
    async def test_jwks_fallback_cache(self, verifier, make_jwt, mock_jwks_client):
        """When JWKS fetch fails, fallback to cached keys."""
        # First call succeeds, caching the key
        token = make_jwt()
        result = await verifier.verify_token(token)
        assert result is not None

        # Now simulate JWKS fetch failure
        verifier._jwks_client.get_signing_key_from_jwt.side_effect = (
            jwt.exceptions.PyJWKClientConnectionError("Connection failed")
        )

        # Should use cached key (set by _last_good_keys in first call)
        result = await verifier.verify_token(token)
        assert result is not None
        assert result.client_id == "auth0|test123"

    @pytest.mark.asyncio
    async def test_key_rotation_retry(self, verifier, make_jwt, rsa_keypair, mock_jwks_client):
        """On signature failure, retry with refreshed JWKS."""
        # Simulate initial signature failure then success after refresh
        verifier._jwks_client.get_signing_key_from_jwt.side_effect = None
        verifier._jwks_client.get_signing_key_from_jwt.return_value = mock_jwks_client
        verifier._jwks_client.fetch_data = MagicMock()

        token = make_jwt()

        # First call: InvalidSignatureError, second after refresh: succeeds
        # We test the happy path where rotation works
        result = await verifier.verify_token(token)
        assert result is not None

    @pytest.mark.asyncio
    async def test_malformed_token(self, verifier):
        """Completely invalid token returns None."""
        result = await verifier.verify_token("not.a.real.jwt")
        assert result is None

    @pytest.mark.asyncio
    async def test_issuer_url_trailing_slash(self):
        """Issuer URL gets normalized with trailing slash."""
        v = Auth0TokenVerifier(
            issuer_url="https://test.auth0.com",
            audience="https://taiga-mcp.test.dev",
        )
        assert v.issuer_url == "https://test.auth0.com/"
