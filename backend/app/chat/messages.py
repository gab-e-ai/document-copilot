from __future__ import annotations

from pydantic import BaseModel


class WireMessage(BaseModel):
    model_config = {"extra": "allow"}

    role: str
    content: str | None = None


def extract_user_query(messages: list[WireMessage]) -> str:
    """Return the text of the last user message; raise ValueError if none."""
    for msg in reversed(messages):
        if msg.role == "user" and msg.content:
            return msg.content
    raise ValueError("No user message found in the request")
