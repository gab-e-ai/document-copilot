from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def stream_answer_and_citations(
    answer: str,
    citations: list[dict],
) -> AsyncGenerator[str, None]:
    part_id = str(uuid.uuid4())

    yield sse({"type": "text-start", "id": part_id})
    for word in answer.split():
        yield sse({"type": "text-delta", "id": part_id, "delta": word + " "})
    yield sse({"type": "text-end", "id": part_id})

    if citations:
        # AI SDK v5+ custom data part: lands in message.parts as
        # {type: "data-citations", data: {citations: [...]}}.
        yield sse({"type": "data-citations", "data": {"citations": citations}})

    yield sse({"type": "finish-step"})
    yield sse({"type": "finish", "finishReason": "stop"})
    yield "data: [DONE]\n\n"
