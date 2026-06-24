import asyncio
import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import AuthUser, get_current_user

router = APIRouter()

_STUB_TEXT = (
    "This is a stubbed response. "
    "Full retrieval and LLM integration coming in Step 4."
)


class ChatMessage(BaseModel):
    model_config = {"extra": "allow"}

    role: str
    content: str | None = None


class ChatStreamRequest(BaseModel):
    id: str  # chat session id sent by @ai-sdk/react v6 HttpChatTransport
    messages: list[ChatMessage]
    trigger: str | None = None


def _sse(event: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


async def _stream_stub() -> AsyncGenerator[str, None]:
    part_id = str(uuid.uuid4())

    # Signal start of a new text part
    yield _sse({"type": "text-start", "id": part_id})

    # Stream each word as a text-delta
    for word in _STUB_TEXT.split():
        yield _sse({"type": "text-delta", "id": part_id, "delta": word + " "})
        await asyncio.sleep(0.02)

    # Close the text part
    yield _sse({"type": "text-end", "id": part_id})

    # Step and message finish signals
    yield _sse({"type": "finish-step"})
    yield _sse({"type": "finish", "finishReason": "stop"})

    # SSE termination sentinel
    yield "data: [DONE]\n\n"


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamRequest,
    _user: AuthUser = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        _stream_stub(),
        media_type="text/event-stream",
        headers={"x-vercel-ai-ui-message-stream": "v1"},
    )
