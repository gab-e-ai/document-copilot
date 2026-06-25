from __future__ import annotations

import pytest


def _passage(chunk_id: str) -> "SourcePassage":
    from app.assistant.outputs import SourcePassage
    return SourcePassage(
        chunk_id=chunk_id,
        document_id="doc1",
        chunk_text="text",
        chunk_index=0,
        ticker="AAPL",
        company="Apple Inc.",
        filing_type="10-K",
        filing_date="2024-02-02",
        accession_number="0001234567-24-000001",
        source_url="https://sec.gov/",
    )


def _citation(chunk_id: str) -> "Citation":
    from app.assistant.outputs import Citation
    return Citation(
        chunk_id=chunk_id,
        excerpt="Revenue was $90B.",
        company="Apple Inc.",
        filing_type="10-K",
        filing_date="2024-02-02",
        accession_number="0001234567-24-000001",
    )


def test_validate_passes_when_all_citations_retrieved():
    from app.assistant.outputs import GroundedAnswer
    from app.grounding.validator import GroundingValidator

    answer = GroundedAnswer(
        answer="Revenue was $90B [1].",
        citations=[_citation("c1")],
    )
    retrieved = [_passage("c1"), _passage("c2")]

    validator = GroundingValidator()
    result = validator.validate(answer, retrieved)

    assert result is answer


def test_validate_raises_for_unretrieved_chunk():
    from app.assistant.outputs import GroundedAnswer
    from app.grounding.validator import GroundingError, GroundingValidator

    answer = GroundedAnswer(
        answer="Something [1].",
        citations=[_citation("c999")],  # c999 was never retrieved
    )
    retrieved = [_passage("c1")]

    validator = GroundingValidator()
    with pytest.raises(GroundingError, match="c999"):
        validator.validate(answer, retrieved)


def test_validate_passes_with_no_citations():
    from app.assistant.outputs import GroundedAnswer
    from app.grounding.validator import GroundingValidator

    answer = GroundedAnswer(
        answer="The corpus does not contain enough evidence.",
        citations=[],
    )
    validator = GroundingValidator()
    result = validator.validate(answer, [])
    assert result is answer


def test_validate_passes_with_multiple_valid_citations():
    from app.assistant.outputs import GroundedAnswer
    from app.grounding.validator import GroundingValidator

    answer = GroundedAnswer(
        answer="Revenue [1] and profit [2].",
        citations=[_citation("c1"), _citation("c2")],
    )
    retrieved = [_passage("c1"), _passage("c2"), _passage("c3")]
    validator = GroundingValidator()
    result = validator.validate(answer, retrieved)
    assert len(result.citations) == 2
