from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_body(text: str = "What was Apple revenue?"):
    import uuid
    from app.schemas.chat import ChatStreamRequest, ChatMessage
    return ChatStreamRequest(
        id=str(uuid.uuid4()),
        messages=[ChatMessage(role="user", content=text)],
    )


def _make_user():
    from app.auth.dependencies import AuthUser
    return AuthUser(id="u1", email="test@example.com")


@pytest.mark.asyncio
async def test_run_chat_turn_yields_sse_events():
    from app.assistant.outputs import Citation, GroundedAnswer
    from app.chat.orchestrator import run_chat_turn

    mock_answer = GroundedAnswer(
        answer="Revenue was $90B [1].",
        citations=[
            Citation(
                chunk_id="c1",
                excerpt="Revenue was $90B.",
                company="Apple Inc.",
                filing_type="10-K",
                filing_date="2024-02-02",
                accession_number="0001234567-24-000001",
            )
        ],
    )

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    with (
        patch("app.chat.orchestrator.DocumentRetriever"),
        patch("app.chat.orchestrator.run_agent", AsyncMock(return_value=mock_answer)),
        patch("app.chat.orchestrator.GroundingValidator") as mock_val_cls,
        patch("app.chat.orchestrator.AsyncOpenAI"),
        patch("app.chat.orchestrator.get_or_create_thread", AsyncMock(return_value=MagicMock())),
        patch("app.chat.orchestrator.save_message", AsyncMock(return_value=__import__("uuid").uuid4())),
        patch("app.chat.orchestrator.save_citations", AsyncMock()),
    ):
        mock_val_cls.return_value.validate = MagicMock(return_value=mock_answer)

        events = []
        stream = await run_chat_turn(_make_body(), _make_user(), mock_session)
        async for chunk in stream:
            events.append(chunk)

    assert any("text-delta" in e for e in events)
    assert any("[DONE]" in e for e in events)


@pytest.mark.asyncio
async def test_run_chat_turn_calls_save_message():
    from app.assistant.outputs import GroundedAnswer
    from app.chat.orchestrator import run_chat_turn

    mock_answer = GroundedAnswer(answer="No evidence found.", citations=[])
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    save_message_mock = AsyncMock(return_value=__import__("uuid").uuid4())
    with (
        patch("app.chat.orchestrator.DocumentRetriever"),
        patch("app.chat.orchestrator.run_agent", AsyncMock(return_value=mock_answer)),
        patch("app.chat.orchestrator.GroundingValidator") as mock_val_cls,
        patch("app.chat.orchestrator.AsyncOpenAI"),
        patch("app.chat.orchestrator.get_or_create_thread", AsyncMock(return_value=MagicMock())),
        patch("app.chat.orchestrator.save_message", save_message_mock),
        patch("app.chat.orchestrator.save_citations", AsyncMock()),
    ):
        mock_val_cls.return_value.validate = MagicMock(return_value=mock_answer)
        stream = await run_chat_turn(_make_body(), _make_user(), mock_session)
        async for _ in stream:
            pass

    assert save_message_mock.call_count >= 1
