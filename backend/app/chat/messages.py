from __future__ import annotations

from pydantic import BaseModel


class WireMessage(BaseModel):
    model_config = {"extra": "allow"}

    role: str
    content: str | None = None


def _text_from_parts(msg: WireMessage) -> str | None:
    """Extract text from an AI SDK UIMessage `parts` array, if present."""
    parts = getattr(msg, "parts", None)
    if not isinstance(parts, list):
        return None
    texts = [
        p["text"]
        for p in parts
        if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
    ]
    joined = " ".join(texts).strip()
    return joined or None


def extract_user_query(messages: list[WireMessage]) -> str:
    """Return the text of the last user message; raise ValueError if none.

    Supports both the plain ``{role, content}`` shape and the AI SDK v5+
    UIMessage shape where text lives in ``parts: [{type: "text", text: ...}]``.
    """
    for msg in reversed(messages):
        if msg.role != "user":
            continue
        if msg.content:
            return msg.content
        text = _text_from_parts(msg)
        if text:
            return text
    raise ValueError("No user message found in the request")
