from __future__ import annotations


def test_source_passage_round_trips():
    from app.assistant.outputs import SourcePassage

    p = SourcePassage(
        chunk_id="c1",
        document_id="d1",
        chunk_text="Revenue was $90B.",
        chunk_index=3,
        ticker="AAPL",
        company="Apple Inc.",
        filing_type="10-K",
        filing_date="2024-02-02",
        accession_number="0001234567-24-000001",
        source_url="https://sec.gov/",
    )
    assert p.chunk_id == "c1"
    assert p.ticker == "AAPL"
    assert p.model_dump()["filing_date"] == "2024-02-02"


def test_citation_requires_chunk_id_and_excerpt():
    from app.assistant.outputs import Citation

    c = Citation(
        chunk_id="c1",
        excerpt="Revenue was $90B.",
        company="Apple Inc.",
        filing_type="10-K",
        filing_date="2024-02-02",
        accession_number="0001234567-24-000001",
    )
    assert c.chunk_id == "c1"
    assert "Revenue" in c.excerpt


def test_grounded_answer_holds_citations():
    from app.assistant.outputs import Citation, GroundedAnswer

    ans = GroundedAnswer(
        answer="Apple reported $90B revenue [1].",
        citations=[
            Citation(
                chunk_id="c1",
                excerpt="Revenue was $90B.",
                company="Apple Inc.",
                filing_type="10-K",
                filing_date="2024-02-02",
                accession_number="0001234567-24-000001",
            )
        ],
    )
    assert len(ans.citations) == 1
    assert "[1]" in ans.answer


def test_grounded_answer_allows_empty_citations():
    from app.assistant.outputs import GroundedAnswer

    ans = GroundedAnswer(
        answer="The corpus does not contain enough evidence to answer this question.",
        citations=[],
    )
    assert ans.citations == []
