from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_row(chunk_id: str, ticker: str = "AAPL") -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc1",
        "chunk_text": f"text for {chunk_id}",
        "chunk_index": 0,
        "ticker": ticker,
        "company": "Apple Inc.",
        "filing_type": "10-K",
        "filing_date": "2024-02-02",
        "accession_number": "0001234567-24-000001",
        "source_url": "https://sec.gov/",
        "score": 0.9,
    }


@pytest.fixture
def mock_openai():
    client = AsyncMock()
    embedding_response = MagicMock()
    embedding_response.data = [MagicMock(embedding=[0.1] * 1536)]
    client.embeddings.create = AsyncMock(return_value=embedding_response)
    return client


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.mark.asyncio
async def test_retrieve_returns_source_passages(mock_session, mock_openai):
    from app.retrieval.retriever import DocumentRetriever

    semantic_rows = [_make_row("c1"), _make_row("c2")]
    fulltext_rows = [_make_row("c2"), _make_row("c3")]

    with (
        patch("app.retrieval.retriever.semantic_search", AsyncMock(return_value=semantic_rows)),
        patch("app.retrieval.retriever.fulltext_search", AsyncMock(return_value=fulltext_rows)),
    ):
        retriever = DocumentRetriever(mock_session, mock_openai)
        passages = await retriever.retrieve("What was revenue?")

    assert len(passages) > 0
    assert all(hasattr(p, "chunk_id") for p in passages)
    assert all(hasattr(p, "chunk_text") for p in passages)


@pytest.mark.asyncio
async def test_retrieve_calls_openai_embeddings(mock_session, mock_openai):
    from app.retrieval.retriever import DocumentRetriever

    with (
        patch("app.retrieval.retriever.semantic_search", AsyncMock(return_value=[])),
        patch("app.retrieval.retriever.fulltext_search", AsyncMock(return_value=[])),
    ):
        retriever = DocumentRetriever(mock_session, mock_openai)
        await retriever.retrieve("test query")

    mock_openai.embeddings.create.assert_called_once()
    call_kwargs = mock_openai.embeddings.create.call_args
    assert call_kwargs.kwargs["input"] == ["test query"]


@pytest.mark.asyncio
async def test_retrieve_empty_when_no_results(mock_session, mock_openai):
    from app.retrieval.retriever import DocumentRetriever

    with (
        patch("app.retrieval.retriever.semantic_search", AsyncMock(return_value=[])),
        patch("app.retrieval.retriever.fulltext_search", AsyncMock(return_value=[])),
    ):
        retriever = DocumentRetriever(mock_session, mock_openai)
        passages = await retriever.retrieve("obscure query")

    assert passages == []


@pytest.mark.asyncio
async def test_retrieve_deduplicates_via_fusion(mock_session, mock_openai):
    from app.retrieval.retriever import DocumentRetriever

    # c1 in both → should appear once
    rows = [_make_row("c1"), _make_row("c2")]

    with (
        patch("app.retrieval.retriever.semantic_search", AsyncMock(return_value=rows)),
        patch("app.retrieval.retriever.fulltext_search", AsyncMock(return_value=rows)),
    ):
        retriever = DocumentRetriever(mock_session, mock_openai)
        passages = await retriever.retrieve("revenue")

    chunk_ids = [p.chunk_id for p in passages]
    assert len(chunk_ids) == len(set(chunk_ids))
