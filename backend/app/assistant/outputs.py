from __future__ import annotations

from pydantic import BaseModel, Field


class SourcePassage(BaseModel):
    chunk_id: str
    document_id: str
    chunk_text: str
    chunk_index: int
    ticker: str
    company: str
    filing_type: str
    filing_date: str
    accession_number: str
    source_url: str


class Citation(BaseModel):
    chunk_id: str
    excerpt: str = Field(
        description="Exact short quote from the source passage that supports the claim"
    )
    company: str
    filing_type: str
    filing_date: str
    accession_number: str


class GroundedAnswer(BaseModel):
    answer: str = Field(
        description=(
            "Answer with inline citation markers like [1], [2]. "
            "If evidence is insufficient, say so explicitly."
        )
    )
    citations: list[Citation] = Field(
        description="Citations in order of first appearance in the answer"
    )
