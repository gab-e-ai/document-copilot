from __future__ import annotations

import json
import pytest


def test_extract_user_query_returns_last_user_message():
    from app.chat.messages import WireMessage, extract_user_query

    messages = [
        WireMessage(role="user", content="First question"),
        WireMessage(role="assistant", content="First answer"),
        WireMessage(role="user", content="Follow-up question"),
    ]
    assert extract_user_query(messages) == "Follow-up question"


def test_extract_user_query_reads_ai_sdk_parts():
    from app.chat.messages import WireMessage, extract_user_query

    # AI SDK v5+ UIMessage shape: text lives in `parts`, not `content`.
    messages = [
        WireMessage.model_validate(
            {
                "role": "user",
                "parts": [{"type": "text", "text": "What was Apple's revenue in 2024?"}],
            }
        )
    ]
    assert extract_user_query(messages) == "What was Apple's revenue in 2024?"


def test_extract_user_query_raises_when_no_user_message():
    from app.chat.messages import WireMessage, extract_user_query

    messages = [WireMessage(role="assistant", content="Hello")]
    with pytest.raises(ValueError, match="No user message"):
        extract_user_query(messages)


def test_extract_user_query_raises_for_empty_list():
    from app.chat.messages import extract_user_query

    with pytest.raises(ValueError):
        extract_user_query([])


def test_sse_formats_dict_as_data_line():
    from app.chat.streaming import sse

    result = sse({"type": "finish"})
    assert result.startswith("data: ")
    assert result.endswith("\n\n")
    payload = json.loads(result[len("data: "):-2])
    assert payload == {"type": "finish"}


@pytest.mark.asyncio
async def test_stream_answer_yields_text_parts():
    from app.chat.streaming import stream_answer_and_citations

    events = []
    async for chunk in stream_answer_and_citations("Hello world", []):
        if chunk != "data: [DONE]\n\n":
            payload = json.loads(chunk[len("data: "):-2])
            events.append(payload)

    types = [e["type"] for e in events]
    assert "text-start" in types
    assert "text-delta" in types
    assert "text-end" in types
    assert "finish-step" in types
    assert "finish" in types


@pytest.mark.asyncio
async def test_stream_answer_includes_all_words():
    from app.chat.streaming import stream_answer_and_citations

    collected = ""
    async for chunk in stream_answer_and_citations("Revenue grew strongly", []):
        if chunk.startswith("data: {"):
            payload = json.loads(chunk[len("data: "):-2])
            if payload.get("type") == "text-delta":
                collected += payload.get("delta", "")

    assert "Revenue" in collected
    assert "grew" in collected
    assert "strongly" in collected


@pytest.mark.asyncio
async def test_stream_answer_sends_citations_data_part_when_present():
    from app.chat.streaming import stream_answer_and_citations

    citation = {"chunk_id": "c1", "excerpt": "Revenue was $90B.", "company": "Apple Inc."}
    payloads = []
    async for chunk in stream_answer_and_citations("Answer [1].", [citation]):
        if chunk.startswith("data: {"):
            payloads.append(json.loads(chunk[len("data: "):-2]))

    types = [p["type"] for p in payloads]
    # AI SDK v5+ custom data part carrying citations.
    assert "data-citations" in types
    data_part = next(p for p in payloads if p["type"] == "data-citations")
    assert data_part["data"]["citations"] == [citation]


@pytest.mark.asyncio
async def test_stream_answer_no_citations_data_part_without_citations():
    from app.chat.streaming import stream_answer_and_citations

    types = []
    async for chunk in stream_answer_and_citations("No evidence found.", []):
        if chunk.startswith("data: {"):
            payload = json.loads(chunk[len("data: "):-2])
            types.append(payload["type"])

    assert "data-citations" not in types
