from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.agent import run_agent
from app.assistant.deps import DocumentAgentDeps
from app.auth.dependencies import AuthUser
from app.chat.messages import WireMessage, extract_user_query
from app.chat.streaming import sse, stream_answer_and_citations
from app.config import settings
from app.database.chats import get_or_create_thread, save_citations, save_message
from app.grounding.validator import GroundingError, GroundingValidator
from app.retrieval.retriever import DocumentRetriever
from app.schemas.chat import ChatStreamRequest

_openai_client = AsyncOpenAI(api_key=settings.openai_api_key)


async def _error_stream(message: str) -> AsyncGenerator[str, None]:
    yield sse({"type": "error", "error": message})
    yield sse({"type": "finish", "finishReason": "error"})
    yield "data: [DONE]\n\n"


async def run_chat_turn(
    body: ChatStreamRequest,
    user: AuthUser,
    session: AsyncSession,
) -> AsyncGenerator[str, None]:
    wire_messages = [WireMessage(role=m.role, content=m.content) for m in body.messages]
    user_query = extract_user_query(wire_messages)

    thread_id = body.id
    try:
        uuid.UUID(thread_id)
    except ValueError:
        thread_id = str(uuid.uuid4())

    await get_or_create_thread(session, thread_id, user.id)
    await save_message(session, thread_id, "user", user_query)

    retriever = DocumentRetriever(session, _openai_client)
    validator = GroundingValidator()
    deps = DocumentAgentDeps(
        user_id=user.id,
        thread_id=thread_id,
        retriever=retriever,
        grounding_validator=validator,
    )

    try:
        answer = await run_agent(user_query, deps)
        answer = validator.validate(answer, deps.retrieved_passages)
    except GroundingError as exc:
        return _error_stream(str(exc))
    except Exception:
        return _error_stream("An error occurred generating the answer.")

    serialized_citations = [c.model_dump() for c in answer.citations]
    assistant_message_id = await save_message(session, thread_id, "assistant", answer.answer)
    await save_citations(session, assistant_message_id, answer.citations)
    await session.commit()

    return stream_answer_and_citations(answer.answer, serialized_citations)
