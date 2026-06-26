from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import ChatStreamRequest
from app.assistant.agent import run_agent
from app.assistant.deps import DocumentAgentDeps
from app.auth.dependencies import AuthUser
from app.chat.messages import WireMessage, extract_user_query
from app.chat.streaming import stream_answer_and_citations
from app.config import settings
from app.database.chats import get_or_create_thread, save_citations, save_message
from app.grounding.validator import GroundingValidator
from app.retrieval.retriever import DocumentRetriever


async def run_chat_turn(
    body: ChatStreamRequest,
    user: AuthUser,
    session: AsyncSession,
) -> AsyncGenerator[str, None]:
    # Convert ChatMessage list to WireMessage list for extract_user_query
    wire_messages = [WireMessage(role=m.role, content=m.content) for m in body.messages]
    user_query = extract_user_query(wire_messages)

    # Validate/normalise the thread_id — AI SDK may send arbitrary strings
    try:
        uuid.UUID(body.id)
        thread_id = body.id
    except (ValueError, AttributeError):
        thread_id = str(uuid.uuid4())

    await get_or_create_thread(session, thread_id, user.id)
    await save_message(session, thread_id, "user", user_query)

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    retriever = DocumentRetriever(session, openai_client)
    validator = GroundingValidator()

    deps = DocumentAgentDeps(
        user_id=user.id,
        thread_id=thread_id,
        retriever=retriever,
        grounding_validator=validator,
    )

    answer = await run_agent(user_query, deps)
    validator.validate(answer, deps.retrieved_passages)

    serialized_citations = [c.model_dump() for c in answer.citations]
    assistant_message_id = await save_message(
        session, thread_id, "assistant", answer.answer
    )
    await save_citations(session, assistant_message_id, answer.citations)
    await session.commit()

    async for chunk in stream_answer_and_citations(answer.answer, serialized_citations):
        yield chunk
