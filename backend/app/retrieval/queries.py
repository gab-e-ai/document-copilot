from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def semantic_search(
    session: AsyncSession,
    query_embedding: list[float],
    limit: int = 20,
) -> list[dict]:
    """Return chunks ordered by cosine similarity to query_embedding."""
    sql = text("""
        SELECT
            dc.id::text            AS chunk_id,
            dc.chunk_text,
            dc.metadata_json,
            dc.chunk_index,
            sd.id::text            AS document_id,
            sd.ticker,
            sd.company,
            sd.filing_type,
            sd.filing_date::text   AS filing_date,
            sd.accession_number,
            sd.source_url,
            1 - (dc.embedding <=> CAST(:embedding AS vector)) AS score
        FROM document_chunks dc
        JOIN source_documents sd ON sd.id = dc.document_id
        WHERE dc.embedding IS NOT NULL
        ORDER BY dc.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)
    result = await session.execute(
        sql, {"embedding": str(query_embedding), "limit": limit}
    )
    return [dict(row._mapping) for row in result.all()]


async def fulltext_search(
    session: AsyncSession,
    query: str,
    limit: int = 20,
) -> list[dict]:
    """Return chunks ranked by Postgres ts_rank against search_vector."""
    sql = text("""
        SELECT
            dc.id::text            AS chunk_id,
            dc.chunk_text,
            dc.metadata_json,
            dc.chunk_index,
            sd.id::text            AS document_id,
            sd.ticker,
            sd.company,
            sd.filing_type,
            sd.filing_date::text   AS filing_date,
            sd.accession_number,
            sd.source_url,
            ts_rank(dc.search_vector, plainto_tsquery('english', :query)) AS score
        FROM document_chunks dc
        JOIN source_documents sd ON sd.id = dc.document_id
        WHERE dc.search_vector @@ plainto_tsquery('english', :query)
        ORDER BY score DESC
        LIMIT :limit
    """)
    result = await session.execute(sql, {"query": query, "limit": limit})
    return [dict(row._mapping) for row in result.all()]
