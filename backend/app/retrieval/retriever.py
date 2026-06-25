from __future__ import annotations

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.outputs import SourcePassage
from app.config import settings
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.queries import fulltext_search, semantic_search

_TOP_K = 10


class DocumentRetriever:
    def __init__(self, session: AsyncSession, openai_client: AsyncOpenAI) -> None:
        self._session = session
        self._openai = openai_client

    async def retrieve(self, query: str) -> list[SourcePassage]:
        """Embed query, run hybrid search, fuse with RRF, return top-K passages."""
        response = await self._openai.embeddings.create(
            input=[query],
            model=settings.openai_embedding_model,
            dimensions=settings.openai_embedding_dimensions,
        )
        embedding = response.data[0].embedding

        semantic_rows = await semantic_search(self._session, embedding)
        fulltext_rows = await fulltext_search(self._session, query)

        semantic_ids = [r["chunk_id"] for r in semantic_rows]
        fulltext_ids = [r["chunk_id"] for r in fulltext_rows]
        fused_ids = reciprocal_rank_fusion([semantic_ids, fulltext_ids])[:_TOP_K]

        all_rows: dict[str, dict] = {
            r["chunk_id"]: r for r in semantic_rows + fulltext_rows
        }

        return [
            SourcePassage(
                chunk_id=cid,
                document_id=all_rows[cid]["document_id"],
                chunk_text=all_rows[cid]["chunk_text"],
                chunk_index=all_rows[cid]["chunk_index"],
                ticker=all_rows[cid]["ticker"],
                company=all_rows[cid]["company"],
                filing_type=all_rows[cid]["filing_type"],
                filing_date=str(all_rows[cid]["filing_date"]),
                accession_number=all_rows[cid]["accession_number"],
                source_url=all_rows[cid]["source_url"],
            )
            for cid in fused_ids
            if cid in all_rows
        ]
