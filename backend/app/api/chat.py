from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AuthUser, get_current_user
from app.database.session import get_session
from app.schemas.chat import ChatStreamRequest

router = APIRouter()


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamRequest,
    user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    from app.chat.orchestrator import run_chat_turn

    stream: AsyncGenerator[str, None] = await run_chat_turn(body, user, session)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"x-vercel-ai-ui-message-stream": "v1"},
    )
