from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.auth.dependencies import AuthUser, get_current_user


def _make_creds(token: str):
    creds = MagicMock()
    creds.credentials = token
    return creds


async def test_valid_token_returns_auth_user():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "user-abc", "email": "analyst@driftwood.com"}

    with patch("app.auth.dependencies.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_cls.return_value = mock_client

        user = await get_current_user(_make_creds("valid-token"))

    assert user.id == "user-abc"
    assert user.email == "analyst@driftwood.com"
    assert isinstance(user, AuthUser)


async def test_supabase_returns_non_200_raises_401():
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("app.auth.dependencies.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_cls.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_make_creds("bad-token"))

    assert exc_info.value.status_code == 401


async def test_network_error_raises_401():
    with patch("app.auth.dependencies.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.side_effect = Exception("network down")
        mock_cls.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_make_creds("any-token"))

    assert exc_info.value.status_code == 401
