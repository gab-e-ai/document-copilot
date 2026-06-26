from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import AuthUser, get_current_user
from app.database.session import get_session
from app.main import app


def _auth_override() -> AuthUser:
    return AuthUser(id="test-user-id", email="analyst@driftwood.com")


async def _session_override():
    yield AsyncMock()


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = _auth_override
    app.dependency_overrides[get_session] = _session_override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def unauth_client():
    yield TestClient(app)


def test_stream_requires_auth(unauth_client):
    # Auth check fires before schema validation — any body (or none) is fine here
    response = unauth_client.post(
        "/chat/stream",
        json={"id": "test-chat-id", "messages": []},
    )
    assert response.status_code == 403


def test_stream_returns_200_with_ai_sdk_headers(client):
    from app.assistant.outputs import GroundedAnswer
    from unittest.mock import MagicMock
    mock_answer = GroundedAnswer(answer="test answer", citations=[])

    with patch("app.chat.orchestrator.run_agent", AsyncMock(return_value=mock_answer)), \
         patch("app.chat.orchestrator.get_or_create_thread", AsyncMock(return_value=AsyncMock())), \
         patch("app.chat.orchestrator.save_message", AsyncMock(return_value=__import__("uuid").uuid4())), \
         patch("app.chat.orchestrator.save_citations", AsyncMock()), \
         patch("app.chat.orchestrator.AsyncOpenAI"), \
         patch("app.chat.orchestrator.DocumentRetriever"), \
         patch("app.chat.orchestrator.GroundingValidator") as mock_val_cls:
        mock_val_cls.return_value.validate = MagicMock(return_value=mock_answer)
        response = client.post(
            "/chat/stream",
            json={"id": "test-chat-id", "messages": [{"role": "user", "content": "hello"}]},
            headers={"Authorization": "Bearer fake-token"},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert response.headers.get("x-vercel-ai-ui-message-stream") == "v1"


def test_stream_body_contains_ui_message_stream_parts(client):
    from app.assistant.outputs import GroundedAnswer
    from unittest.mock import MagicMock
    mock_answer = GroundedAnswer(answer="hello world", citations=[])

    with patch("app.chat.orchestrator.run_agent", AsyncMock(return_value=mock_answer)), \
         patch("app.chat.orchestrator.get_or_create_thread", AsyncMock(return_value=AsyncMock())), \
         patch("app.chat.orchestrator.save_message", AsyncMock(return_value=__import__("uuid").uuid4())), \
         patch("app.chat.orchestrator.save_citations", AsyncMock()), \
         patch("app.chat.orchestrator.AsyncOpenAI"), \
         patch("app.chat.orchestrator.DocumentRetriever"), \
         patch("app.chat.orchestrator.GroundingValidator") as mock_val_cls:
        mock_val_cls.return_value.validate = MagicMock(return_value=mock_answer)
        response = client.post(
            "/chat/stream",
            json={"id": "test-chat-id", "messages": [{"role": "user", "content": "hello"}]},
            headers={"Authorization": "Bearer fake-token"},
        )

    lines = response.text.splitlines()

    # Every SSE data line starts with "data: "
    data_lines = [line for line in lines if line.startswith("data: ")]
    assert data_lines, "no SSE data lines found"

    # At least one text-delta event
    def is_type(line: str, event_type: str) -> bool:
        if not line.startswith("data: "):
            return False
        try:
            return json.loads(line[6:]).get("type") == event_type
        except (json.JSONDecodeError, AttributeError):
            return False

    assert any(is_type(line, "text-delta") for line in lines), "missing text-delta event"
    assert any(is_type(line, "finish-step") for line in lines), "missing finish-step event"
    assert any(is_type(line, "finish") for line in lines), "missing finish event"

    # Stream must end with the SSE sentinel (trailing blank lines from \n\n are stripped)
    non_empty = [l for l in lines if l.strip()]
    assert non_empty[-1] == "data: [DONE]", "stream must terminate with data: [DONE]"
