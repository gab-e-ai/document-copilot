from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import DocumentChunk, SourceDocument

COMPANY_NAMES: dict[str, str] = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
}


def ingest_document(
    entry: dict,
    content_markdown: str,
    chunks: list[str],
    embeddings: list[list[float]],
    token_counts: list[int],
    session: Session,
) -> int:
    """Write one document and its chunks to Supabase via SQLAlchemy.

    Returns number of chunks written, or 0 if this accession_number already exists.
    """
    existing = session.execute(
        select(SourceDocument).where(
            SourceDocument.accession_number == entry["accession_number"]
        )
    ).scalar_one_or_none()
    if existing is not None:
        return 0

    ticker = entry["ticker"]
    company = COMPANY_NAMES.get(ticker, ticker)
    filing_date = date.fromisoformat(entry["filing_date"])
    fiscal_year = int(entry["report_date"][:4])

    doc = SourceDocument(
        id=uuid.uuid4(),
        ticker=ticker,
        company=company,
        filing_type=entry["form"],
        filing_date=filing_date,
        fiscal_year=fiscal_year,
        accession_number=entry["accession_number"],
        source_url=entry["source_url"],
        content_markdown=content_markdown,
    )
    session.add(doc)
    session.flush()  # populate doc.id before referencing it in chunks

    for i, (chunk_text, embedding, token_count) in enumerate(
        zip(chunks, embeddings, token_counts, strict=True)
    ):
        session.add(
            DocumentChunk(
                id=uuid.uuid4(),
                document_id=doc.id,
                chunk_index=i,
                chunk_text=chunk_text,
                embedding=embedding,
                token_count=token_count,
                metadata_json={
                    "ticker": ticker,
                    "company": company,
                    "filing_type": entry["form"],
                    "filing_date": entry["filing_date"],
                    "fiscal_year": fiscal_year,
                    "accession_number": entry["accession_number"],
                    "source_url": entry["source_url"],
                },
            )
        )

    session.commit()
    return len(chunks)
