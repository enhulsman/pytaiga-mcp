"""OAuth discovery must advertise the exact registered API identifier."""

from types import SimpleNamespace

import httpx
import pytest

import src.server


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "audience",
    [
        "https://mcp.example.test",
        "https://mcp.example.test/",
        "https://mcp.example.test/api",
    ],
)
async def test_discovery_preserves_registered_audience(monkeypatch, audience):
    settings = SimpleNamespace(
        transport="streamable-http",
        has_oauth_config=True,
        oauth_issuer_url="https://issuer.example.test/",
        oauth_audience=audience,
        scopes_list=["taiga:read", "taiga:write"],
        jwks_cache_ttl=600,
        get_encryption_key=lambda: None,
    )
    monkeypatch.setattr(src.server, "settings", settings)
    server = src.server.create_mcp_server()
    assert server._token_verifier.audience == audience
    app = server.streamable_http_app()
    metadata_path = "/.well-known/oauth-protected-resource"
    if audience.endswith("/api"):
        metadata_path += "/api"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://mcp.example.test"
    ) as client:
        response = await client.get(metadata_path)

    assert response.status_code == 200
    metadata = response.json()
    assert metadata["resource"] == audience
    assert metadata["authorization_servers"] == [settings.oauth_issuer_url]
    assert metadata["scopes_supported"] == ["taiga:read", "taiga:write"]
