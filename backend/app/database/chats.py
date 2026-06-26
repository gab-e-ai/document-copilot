from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.outputs import Citation
from app.database.models import ChatMessage, ChatThread, MessageCitation


async def get_or_create_thread(
    session: AsyncSession,
    thread_id: str,
    user_id: str,
) -> ChatThread:
    """Get an existing chat thread or create a new one if it doesn't exist."""
    existing = (
        await session.execute(
            select(ChatThread).where(ChatThread.id == uuid.UUID(thread_id))
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing

    thread = ChatThread(id=uuid.UUID(thread_id), user_id=uuid.UUID(user_id))
    session.add(thread)
    await session.flush()
    return thread


async def save_message(
    session: AsyncSession,
    thread_id: str,
    role: str,
    content: str,
    message_json: dict | None = None,
) -> uuid.UUID:
    """Save a chat message and return its ID."""
    message_id = uuid.uuid4()
    session.add(
        ChatMessage(
            id=message_id,
            thread_id=uuid.UUID(thread_id),
            role=role,
            content=content,
            message_json=message_json,
        )
    )
    await session.flush()
    return message_id


async def save_citations(
    session: AsyncSession,
    message_id: uuid.UUID,
    citations: list[Citation],
) -> None:
    """Save citations for a message."""
    for citation in citations:
        session.add(
            MessageCitation(
                id=uuid.uuid4(),
                message_id=message_id,
                chunk_id=uuid.UUID(citation.chunk_id),
                excerpt=citation.excerpt,
                section=None,
                page_number=None,
            )
        )
