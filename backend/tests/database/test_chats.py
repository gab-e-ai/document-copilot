from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_save_message_returns_uuid(mock_session):
    from app.database.chats import save_message

    thread_id = str(uuid.uuid4())
    message_id = await save_message(mock_session, thread_id, "user", "Hello?")

    assert isinstance(message_id, uuid.UUID)
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_save_message_with_json(mock_session):
    from app.database.chats import save_message

    thread_id = str(uuid.uuid4())
    msg_json = {"role": "user", "content": "Hello?"}
    message_id = await save_message(mock_session, thread_id, "user", "Hello?", msg_json)

    assert isinstance(message_id, uuid.UUID)


@pytest.mark.asyncio
async def test_save_citations_adds_one_row_per_citation(mock_session):
    from app.assistant.outputs import Citation
    from app.database.chats import save_citations

    message_id = uuid.uuid4()
    citations = [
        Citation(
            chunk_id=str(uuid.uuid4()),
            excerpt="Revenue was $90B.",
            company="Apple Inc.",
            filing_type="10-K",
            filing_date="2024-02-02",
            accession_number="0001234567-24-000001",
        ),
        Citation(
            chunk_id=str(uuid.uuid4()),
            excerpt="Operating costs fell.",
            company="Apple Inc.",
            filing_type="10-K",
            filing_date="2024-02-02",
            accession_number="0001234567-24-000001",
        ),
    ]
    await save_citations(mock_session, message_id, citations)

    assert mock_session.add.call_count == 2


@pytest.mark.asyncio
async def test_save_citations_no_op_for_empty_list(mock_session):
    from app.database.chats import save_citations

    await save_citations(mock_session, uuid.uuid4(), [])
    mock_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_thread_creates_when_missing(mock_session):
    from app.database.chats import get_or_create_thread

    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    thread_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    thread = await get_or_create_thread(mock_session, thread_id, user_id)

    assert thread is not None
    mock_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_thread_returns_existing(mock_session):
    from app.database.chats import get_or_create_thread
    from app.database.models import ChatThread

    existing = MagicMock(spec=ChatThread)
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
    )

    thread_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    thread = await get_or_create_thread(mock_session, thread_id, user_id)

    assert thread is existing
    mock_session.add.assert_not_called()
