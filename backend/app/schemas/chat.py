from __future__ import annotations

from pydantic import BaseModel


class ChatMessage(BaseModel):
    model_config = {"extra": "allow"}

    role: str
    content: str | None = None


class ChatStreamRequest(BaseModel):
    id: str
    messages: list[ChatMessage]
    trigger: str | None = None
