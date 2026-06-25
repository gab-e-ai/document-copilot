from unittest.mock import MagicMock

from app.ingestion.writer import COMPANY_NAMES, ingest_document


def _entry(ticker: str = "AAPL") -> dict:
    return {
        "ticker": ticker,
        "form": "10-K",
        "filing_date": "2024-11-01",
        "report_date": "2024-09-28",
        "accession_number": f"0000320193-24-{ticker}",
        "source_url": f"https://sec.gov/{ticker.lower()}.htm",
    }


def _session(existing=None) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    session.execute.return_value = result
    return session


def test_returns_chunk_count_on_new_document():
    session = _session(existing=None)
    n = ingest_document(
        _entry(),
        "# Annual Report\n\nSome content.",
        ["chunk A", "chunk B"],
        [[0.1] * 1536, [0.2] * 1536],
        [10, 12],
        session,
    )
    assert n == 2
    assert session.add.call_count >= 3  # 1 SourceDocument + 2 DocumentChunks
    session.commit.assert_called_once()


def test_returns_zero_and_skips_if_already_exists():
    session = _session(existing=MagicMock())
    n = ingest_document(
        _entry(),
        "markdown",
        ["chunk"],
        [[0.0] * 1536],
        [5],
        session,
    )
    assert n == 0
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_company_names_map_covers_all_corpus_tickers():
    for ticker in ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"):
        assert ticker in COMPANY_NAMES
        assert COMPANY_NAMES[ticker]


def test_metadata_json_fields_present():
    captured_chunks = []

    def capture_add(obj):
        captured_chunks.append(obj)

    session = _session(existing=None)
    session.add.side_effect = capture_add

    ingest_document(
        _entry("MSFT"),
        "content",
        ["only chunk"],
        [[0.5] * 1536],
        [7],
        session,
    )

    # Find the DocumentChunk (not the SourceDocument)
    from app.database.models import DocumentChunk

    dc = next((o for o in captured_chunks if isinstance(o, DocumentChunk)), None)
    assert dc is not None
    for key in ("ticker", "company", "filing_type", "filing_date", "fiscal_year",
                "accession_number", "source_url"):
        assert key in dc.metadata_json, f"missing key: {key}"
