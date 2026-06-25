from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_semantic_search_returns_list_of_dicts(mock_session):
    from app.retrieval.queries import semantic_search

    row = MagicMock()
    row._mapping = {
        "chunk_id": "abc",
        "document_id": "doc1",
        "chunk_text": "Revenue grew 12%.",
        "chunk_index": 0,
        "ticker": "AAPL",
        "company": "Apple Inc.",
        "filing_type": "10-K",
        "filing_date": "2024-02-02",
        "accession_number": "0001234567-24-000001",
        "source_url": "https://sec.gov/",
        "score": 0.91,
    }
    mock_session.execute = AsyncMock(return_value=MagicMock(all=lambda: [row]))

    results = await semantic_search(mock_session, [0.1] * 1536, limit=5)

    assert isinstance(results, list)
    assert results[0]["chunk_id"] == "abc"
    assert results[0]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_fulltext_search_returns_list_of_dicts(mock_session):
    from app.retrieval.queries import fulltext_search

    row = MagicMock()
    row._mapping = {
        "chunk_id": "xyz",
        "document_id": "doc2",
        "chunk_text": "Operating expenses decreased.",
        "chunk_index": 1,
        "ticker": "MSFT",
        "company": "Microsoft Corporation",
        "filing_type": "10-K",
        "filing_date": "2024-01-25",
        "accession_number": "0000789019-24-000002",
        "source_url": "https://sec.gov/2",
        "score": 0.75,
    }
    mock_session.execute = AsyncMock(return_value=MagicMock(all=lambda: [row]))

    results = await fulltext_search(mock_session, "operating expenses", limit=5)

    assert isinstance(results, list)
    assert results[0]["chunk_id"] == "xyz"
    assert results[0]["company"] == "Microsoft Corporation"


@pytest.mark.asyncio
async def test_semantic_search_empty_returns_empty_list(mock_session):
    from app.retrieval.queries import semantic_search

    mock_session.execute = AsyncMock(return_value=MagicMock(all=lambda: []))

    results = await semantic_search(mock_session, [0.0] * 1536)

    assert results == []


@pytest.mark.asyncio
async def test_fulltext_search_empty_returns_empty_list(mock_session):
    from app.retrieval.queries import fulltext_search

    mock_session.execute = AsyncMock(return_value=MagicMock(all=lambda: []))

    results = await fulltext_search(mock_session, "nonexistent term")

    assert results == []
