import asyncio
import json
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
    role: str
    content: str


class ChatStreamRequest(BaseModel):
    thread_id: str
    messages: list[ChatMessage]


async def _stream_stub() -> AsyncGenerator[str, None]:
    for word in _STUB_TEXT.split():
        yield f'0:{json.dumps(word + " ")}\n'
        await asyncio.sleep(0.02)
    finish = json.dumps(
        {
            "finishReason": "stop",
            "usage": {"promptTokens": 0, "completionTokens": 0},
            "isContinued": False,
        }
    )
    yield f"e:{finish}\n"
    data_finish = json.dumps(
        {"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": 0}}
    )
    yield f"d:{data_finish}\n"


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamRequest,
    _user: AuthUser = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        _stream_stub(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Vercel-AI-Data-Stream": "v1"},
    )
