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
async def test_stream_answer_sends_annotation_when_citations_present():
    from app.chat.streaming import stream_answer_and_citations

    citation = {"chunk_id": "c1", "excerpt": "Revenue was $90B.", "company": "Apple Inc."}
    types = []
    async for chunk in stream_answer_and_citations("Answer [1].", [citation]):
        if chunk.startswith("data: {"):
            payload = json.loads(chunk[len("data: "):-2])
            types.append(payload["type"])

    assert "message-annotation" in types


@pytest.mark.asyncio
async def test_stream_answer_no_annotation_without_citations():
    from app.chat.streaming import stream_answer_and_citations

    types = []
    async for chunk in stream_answer_and_citations("No evidence found.", []):
        if chunk.startswith("data: {"):
            payload = json.loads(chunk[len("data: "):-2])
            types.append(payload["type"])

    assert "message-annotation" not in types
