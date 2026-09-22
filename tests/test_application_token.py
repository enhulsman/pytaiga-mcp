"""Tests for minting a Taiga application token during account linking."""

from unittest.mock import MagicMock

import pytest

from src.auth.application_token import mint_application_token

APP_ID = "c733a0f2-b7c3-4b48-ba61-1f740547f6f9"


def _client(post_side_effect=None, tokens=None, get_side_effect=None):
    wrapper = MagicMock()
    api = wrapper.api
    if post_side_effect is None:
        def post_side_effect(path, json=None, **kwargs):
            if path == "/application-tokens/authorize":
                return {"auth_code": "code-123", "state": json["state"], "next_url": "x"}
            if path == "/application-tokens/validate":
                return {"token": "app-token-xyz"}
            raise AssertionError(path)
    api.post.side_effect = post_side_effect
    if get_side_effect:
        api.get.side_effect = get_side_effect
    else:
        api.get.return_value = tokens if tokens is not None else [
            {"id": 41, "application": {"id": "other-app"}},
            {"id": 42, "application": {"id": APP_ID}},
        ]
    return wrapper


def test_mint_returns_token_and_taiga_token_id():
    wrapper = _client()
    token, app_token_id = mint_application_token(wrapper, APP_ID)
    assert token == "app-token-xyz"
    assert app_token_id == 42


def test_mint_uses_one_state_for_authorize_and_validate():
    wrapper = _client()
    mint_application_token(wrapper, APP_ID)
    calls = {c.args[0]: c.kwargs["json"] for c in wrapper.api.post.call_args_list}
    authorize = calls["/application-tokens/authorize"]
    validate = calls["/application-tokens/validate"]
    assert authorize["application"] == APP_ID
    assert validate["application"] == APP_ID
    assert validate["auth_code"] == "code-123"
    assert validate["state"] == authorize["state"]
    assert len(authorize["state"]) >= 16


def test_mint_without_token_in_response_raises():
    def post(path, json=None, **kwargs):
        if path.endswith("authorize"):
            return {"auth_code": "c", "state": json["state"]}
        return {"cyphered_token": "legacy"}

    with pytest.raises(ValueError):
        mint_application_token(_client(post_side_effect=post), APP_ID)


def test_mint_without_auth_code_raises():
    def post(path, json=None, **kwargs):
        return {}

    with pytest.raises(ValueError):
        mint_application_token(_client(post_side_effect=post), APP_ID)


def test_mint_tolerates_token_listing_failure():
    """The Taiga-side id is only needed for revocation; linking must not fail without it."""
    def failing_get(path, **kwargs):
        raise RuntimeError("listing broke")

    token, app_token_id = mint_application_token(_client(get_side_effect=failing_get), APP_ID)
    assert token == "app-token-xyz"
    assert app_token_id is None


def test_mint_accepts_flat_application_field():
    wrapper = _client(tokens=[{"id": 7, "application": APP_ID}])
    _, app_token_id = mint_application_token(wrapper, APP_ID)
    assert app_token_id == 7
