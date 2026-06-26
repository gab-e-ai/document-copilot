from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AuthUser, get_current_user
from app.database.session import get_session

router = APIRouter()


class ChatMessage(BaseModel):
    model_config = {"extra": "allow"}

    role: str
    content: str | None = None


class ChatStreamRequest(BaseModel):
    id: str
    messages: list[ChatMessage]
    trigger: str | None = None


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamRequest,
    user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    from app.chat.orchestrator import run_chat_turn

    stream = run_chat_turn(body, user, session)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"x-vercel-ai-ui-message-stream": "v1"},
    )
