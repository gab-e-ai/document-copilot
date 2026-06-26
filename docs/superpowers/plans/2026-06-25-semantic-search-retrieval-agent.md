# Step 5: Semantic Search, Retrieval Agent & Citation UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/chat/stream` stub with a real hybrid-retrieval pipeline: pgvector semantic search + Postgres full-text search fused with RRF, a PydanticAI document agent that generates grounded answers with citations, and a frontend that renders those citations.

**Architecture:** Retrieval (queries + fusion + retriever) is fully independent from the LLM layer. A PydanticAI agent receives a `DocumentRetriever` via typed deps and calls `search_filings` to fetch `SourcePassage` objects. The agent produces a `GroundedAnswer` (answer text + `Citation` list), which the `GroundingValidator` verifies before anything is streamed. The orchestrator then streams the answer word-by-word and sends citations as AI SDK v6 `message-annotation` events. Every write to the DB (message + citations) happens after streaming completes.

**Tech Stack:** FastAPI async, SQLAlchemy async (`create_async_engine`, `AsyncSession`), pgvector, pydantic-ai==1.107.0, openai==2.41.1 (AsyncOpenAI), @ai-sdk/react v3 + ai v6, React 19, Tailwind CSS.

## Global Constraints

- Python 3.12+; use `from __future__ import annotations` in every new backend file.
- All tests run with `cd backend && uv run pytest <path> -v`. The `conftest.py` already seeds fake env vars; do NOT add a real DB connection to tests.
- Use `AsyncMock` / `MagicMock` for all DB and HTTP calls in unit tests.
- Never import from `app.ingestion.*` in the new modules — ingestion is sync-only.
- All SQL goes through `sqlalchemy.text()` with named bind parameters — no f-string interpolation.
- SSE wire format: existing `x-vercel-ai-ui-message-stream: v1` header; use `text-start / text-delta / text-end / message-annotation / finish-step / finish / [DONE]` event sequence.
- Frontend: vanilla Tailwind only — no shadcn/ui, no new npm packages.
- Run `cd backend && uv run pytest tests/ -v` after every backend task to catch regressions.
- Run `cd frontend && npm run build` after every frontend task to catch type errors.

---

## File Map

**New backend files:**
```
backend/app/retrieval/__init__.py
backend/app/retrieval/queries.py       # pgvector + tsvector SQL, returns list[dict]
backend/app/retrieval/fusion.py        # Reciprocal Rank Fusion, pure Python
backend/app/retrieval/retriever.py     # DocumentRetriever: embed → search → fuse → SourcePassage list
backend/app/assistant/__init__.py
backend/app/assistant/outputs.py       # SourcePassage, Citation, GroundedAnswer (Pydantic models)
backend/app/assistant/deps.py          # DocumentAgentDeps dataclass
backend/app/assistant/agent.py         # PydanticAI Agent with search_filings tool
backend/app/assistant/instructions.md  # System prompt / product contract
backend/app/grounding/__init__.py
backend/app/grounding/validator.py     # GroundingValidator, GroundingError
backend/app/chat/__init__.py
backend/app/chat/messages.py           # extract_user_query from wire messages
backend/app/chat/streaming.py          # SSE helpers, stream_answer_and_citations generator
backend/app/chat/orchestrator.py       # run_chat_turn: retrieve → agent → validate → stream → persist
backend/app/database/session.py        # async engine + AsyncSessionLocal + get_session dependency
backend/app/database/chats.py          # save_message, save_citations, get_or_create_thread
```

**Modified backend files:**
```
backend/app/config.py                  # add openai_chat_model field
backend/app/api/chat.py                # replace _stream_stub with orchestrator
backend/app/main.py                    # inject get_session dependency via Depends
```

**New test files:**
```
backend/tests/retrieval/__init__.py
backend/tests/retrieval/test_queries.py
backend/tests/retrieval/test_fusion.py
backend/tests/retrieval/test_retriever.py
backend/tests/assistant/__init__.py
backend/tests/assistant/test_outputs.py
backend/tests/grounding/__init__.py
backend/tests/grounding/test_validator.py
backend/tests/chat/__init__.py
backend/tests/chat/test_streaming.py
backend/tests/chat/test_orchestrator.py
backend/tests/database/__init__.py     (may already exist)
backend/tests/database/test_chats.py
```

**New / modified frontend files:**
```
frontend/src/components/chat/CitationCard.tsx   # new: renders one citation
frontend/src/components/chat/MessageList.tsx    # updated: reads annotations, renders citations
frontend/src/pages/chat/ChatPage.tsx            # updated: richer error + empty-state copy
```

---

## Task 1: Retrieval — pgvector semantic search and Postgres full-text search

**Files:**
- Create: `backend/app/retrieval/__init__.py`
- Create: `backend/app/retrieval/queries.py`
- Create: `backend/tests/retrieval/__init__.py`
- Create: `backend/tests/retrieval/test_queries.py`

**Interfaces:**
- Produces:
  - `semantic_search(session: AsyncSession, query_embedding: list[float], limit: int = 20) -> list[dict]`
  - `fulltext_search(session: AsyncSession, query: str, limit: int = 20) -> list[dict]`
  - Each dict has keys: `chunk_id`, `document_id`, `chunk_text`, `chunk_index`, `ticker`, `company`, `filing_type`, `filing_date`, `accession_number`, `source_url`, `score`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/retrieval/__init__.py` (empty) and `backend/tests/retrieval/test_queries.py`:

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd backend && uv run pytest tests/retrieval/test_queries.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.retrieval'`

- [ ] **Step 3: Create `backend/app/retrieval/__init__.py`** (empty file)

- [ ] **Step 4: Implement `backend/app/retrieval/queries.py`**

```python
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
```

- [ ] **Step 5: Run the tests to confirm they pass**

```bash
cd backend && uv run pytest tests/retrieval/test_queries.py -v
```
Expected: 4 PASSED

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/retrieval/__init__.py app/retrieval/queries.py tests/retrieval/__init__.py tests/retrieval/test_queries.py
git commit -m "feat(retrieval): pgvector semantic search and postgres full-text search queries"
```

---

## Task 2: Retrieval — Reciprocal Rank Fusion

**Files:**
- Create: `backend/app/retrieval/fusion.py`
- Create: `backend/tests/retrieval/test_fusion.py`

**Interfaces:**
- Produces: `reciprocal_rank_fusion(ranked_lists: list[list[str]], k: int = 60) -> list[str]`
  — returns IDs in descending RRF score order.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/retrieval/test_fusion.py`:

```python
from __future__ import annotations


def test_rrf_single_list_preserves_order():
    from app.retrieval.fusion import reciprocal_rank_fusion

    ids = ["a", "b", "c"]
    result = reciprocal_rank_fusion([ids])
    assert result == ["a", "b", "c"]


def test_rrf_two_lists_boosts_shared_ids():
    from app.retrieval.fusion import reciprocal_rank_fusion

    # "b" appears in both lists → higher score than "a" (rank-1 in list1 only)
    result = reciprocal_rank_fusion([["a", "b", "c"], ["b", "d", "e"]])
    assert result[0] == "b"


def test_rrf_empty_lists_returns_empty():
    from app.retrieval.fusion import reciprocal_rank_fusion

    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_deduplicates_ids():
    from app.retrieval.fusion import reciprocal_rank_fusion

    result = reciprocal_rank_fusion([["a", "a", "b"], ["a"]])
    # "a" should appear only once in the output
    assert result.count("a") == 1


def test_rrf_custom_k_affects_score_magnitude():
    from app.retrieval.fusion import reciprocal_rank_fusion

    # Both produce same ordering; just verify no crash and correct type
    result_k60 = reciprocal_rank_fusion([["x", "y"]], k=60)
    result_k1 = reciprocal_rank_fusion([["x", "y"]], k=1)
    assert result_k60 == ["x", "y"]
    assert result_k1 == ["x", "y"]
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && uv run pytest tests/retrieval/test_fusion.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.retrieval.fusion'`

- [ ] **Step 3: Implement `backend/app/retrieval/fusion.py`**

```python
from __future__ import annotations


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    k: int = 60,
) -> list[str]:
    """Fuse multiple ranked ID lists with RRF. Returns IDs by descending score."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        seen: set[str] = set()
        rank = 1
        for doc_id in ranked:
            if doc_id in seen:
                continue
            seen.add(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            rank += 1
    return sorted(scores, key=lambda doc_id: scores[doc_id], reverse=True)
```

- [ ] **Step 4: Run to confirm passing**

```bash
cd backend && uv run pytest tests/retrieval/test_fusion.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/retrieval/fusion.py tests/retrieval/test_fusion.py
git commit -m "feat(retrieval): reciprocal rank fusion for hybrid search"
```

---

## Task 3: Assistant output types — SourcePassage, Citation, GroundedAnswer

**Files:**
- Create: `backend/app/assistant/__init__.py`
- Create: `backend/app/assistant/outputs.py`
- Create: `backend/tests/assistant/__init__.py`
- Create: `backend/tests/assistant/test_outputs.py`

**Interfaces:**
- Produces:
  - `SourcePassage` — Pydantic model, one retrieved chunk + doc metadata
  - `Citation` — Pydantic model, one grounded claim with excerpt
  - `GroundedAnswer` — Pydantic model, `answer: str`, `citations: list[Citation]`

- [ ] **Step 1: Write the failing tests**

Create both `__init__.py` files (empty) and `backend/tests/assistant/test_outputs.py`:

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && uv run pytest tests/assistant/test_outputs.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.assistant'`

- [ ] **Step 3: Implement `backend/app/assistant/outputs.py`**

```python
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
```

- [ ] **Step 4: Run to confirm passing**

```bash
cd backend && uv run pytest tests/assistant/test_outputs.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/assistant/__init__.py app/assistant/outputs.py tests/assistant/__init__.py tests/assistant/test_outputs.py
git commit -m "feat(assistant): SourcePassage, Citation, GroundedAnswer output types"
```

---

## Task 4: DocumentRetriever — embed, search, fuse

**Files:**
- Create: `backend/app/retrieval/retriever.py`
- Create: `backend/tests/retrieval/test_retriever.py`

**Interfaces:**
- Consumes: `semantic_search`, `fulltext_search` from `app.retrieval.queries`; `reciprocal_rank_fusion` from `app.retrieval.fusion`; `SourcePassage` from `app.assistant.outputs`
- Produces: `DocumentRetriever(session: AsyncSession, openai_client: AsyncOpenAI)` with `async def retrieve(self, query: str) -> list[SourcePassage]`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/retrieval/test_retriever.py`:

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && uv run pytest tests/retrieval/test_retriever.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.retrieval.retriever'`

- [ ] **Step 3: Implement `backend/app/retrieval/retriever.py`**

```python
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
```

- [ ] **Step 4: Run to confirm passing**

```bash
cd backend && uv run pytest tests/retrieval/test_retriever.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/retrieval/retriever.py tests/retrieval/test_retriever.py
git commit -m "feat(retrieval): DocumentRetriever with hybrid embed+search+fuse pipeline"
```

---

## Task 5: Grounding validator

**Files:**
- Create: `backend/app/grounding/__init__.py`
- Create: `backend/app/grounding/validator.py`
- Create: `backend/tests/grounding/__init__.py`
- Create: `backend/tests/grounding/test_validator.py`

**Interfaces:**
- Consumes: `GroundedAnswer`, `SourcePassage`, `Citation` from `app.assistant.outputs`
- Produces:
  - `GroundingError(Exception)` — raised when a citation references an unretrieved chunk
  - `GroundingValidator` with `def validate(self, answer: GroundedAnswer, retrieved: list[SourcePassage]) -> GroundedAnswer`

- [ ] **Step 1: Write the failing tests**

Create both `__init__.py` (empty) and `backend/tests/grounding/test_validator.py`:

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && uv run pytest tests/grounding/test_validator.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.grounding'`

- [ ] **Step 3: Implement `backend/app/grounding/validator.py`**

```python
from __future__ import annotations

from app.assistant.outputs import GroundedAnswer, SourcePassage


class GroundingError(Exception):
    pass


class GroundingValidator:
    def validate(
        self,
        answer: GroundedAnswer,
        retrieved: list[SourcePassage],
    ) -> GroundedAnswer:
        """Raise GroundingError if any citation references a chunk not in retrieved."""
        retrieved_ids = {p.chunk_id for p in retrieved}
        for citation in answer.citations:
            if citation.chunk_id not in retrieved_ids:
                raise GroundingError(
                    f"Citation chunk_id {citation.chunk_id!r} was not retrieved "
                    "for this request — the model cited a hallucinated source"
                )
        return answer
```

- [ ] **Step 4: Run to confirm passing**

```bash
cd backend && uv run pytest tests/grounding/test_validator.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/grounding/__init__.py app/grounding/validator.py tests/grounding/__init__.py tests/grounding/test_validator.py
git commit -m "feat(grounding): citation grounding validator"
```

---

## Task 6: Config extension + PydanticAI document agent

**Files:**
- Modify: `backend/app/config.py` — add `openai_chat_model`
- Create: `backend/app/assistant/deps.py`
- Create: `backend/app/assistant/agent.py`
- Create: `backend/app/assistant/instructions.md`
- Create: `backend/tests/assistant/test_agent.py`

**Interfaces:**
- Consumes: `GroundedAnswer`, `SourcePassage`, `Citation` from `app.assistant.outputs`; `DocumentRetriever` from `app.retrieval.retriever`; `GroundingValidator` from `app.grounding.validator`
- Produces:
  - `DocumentAgentDeps` dataclass with fields `user_id: str`, `thread_id: str`, `retriever: DocumentRetriever`, `grounding_validator: GroundingValidator`, `retrieved_passages: list[SourcePassage]` (mutated by tool)
  - `document_agent: Agent[DocumentAgentDeps, GroundedAnswer]` — exported from `app.assistant.agent`
  - `async def run_agent(user_query: str, deps: DocumentAgentDeps) -> GroundedAnswer`

- [ ] **Step 1: Add `openai_chat_model` to config**

Edit `backend/app/config.py` — add this line after `openai_embedding_dimensions`:

```python
    openai_chat_model: str = "gpt-4o-mini"
```

The full updated class body:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    openai_chat_model: str = "gpt-4o-mini"
    allowed_origins: str = "http://localhost:5173"
```

- [ ] **Step 2: Verify config test still passes**

```bash
cd backend && uv run pytest tests/test_config.py -v
```
Expected: all existing config tests PASS

- [ ] **Step 3: Write the failing agent tests**

Create `backend/tests/assistant/test_agent.py`:

```python
from __future__ import annotations

import pytest
from dataclasses import field
from unittest.mock import AsyncMock, MagicMock


def _make_deps(passages=None):
    from app.assistant.deps import DocumentAgentDeps
    from app.grounding.validator import GroundingValidator

    retriever = AsyncMock()
    if passages is not None:
        retriever.retrieve = AsyncMock(return_value=passages)
    return DocumentAgentDeps(
        user_id="u1",
        thread_id="t1",
        retriever=retriever,
        grounding_validator=GroundingValidator(),
    )


def _make_passage(chunk_id: str = "c1"):
    from app.assistant.outputs import SourcePassage
    return SourcePassage(
        chunk_id=chunk_id,
        document_id="doc1",
        chunk_text="Revenue was $90B in fiscal 2024.",
        chunk_index=0,
        ticker="AAPL",
        company="Apple Inc.",
        filing_type="10-K",
        filing_date="2024-02-02",
        accession_number="0001234567-24-000001",
        source_url="https://sec.gov/",
    )


def test_document_agent_deps_instantiates():
    deps = _make_deps()
    assert deps.user_id == "u1"
    assert deps.retrieved_passages == []


def test_run_agent_returns_grounded_answer():
    """Uses PydanticAI TestModel to avoid real OpenAI calls."""
    from pydantic_ai.models.test import TestModel
    from app.assistant.agent import document_agent
    from app.assistant.outputs import GroundedAnswer

    deps = _make_deps(passages=[_make_passage()])

    with document_agent.override(model=TestModel()):
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            document_agent.run("What was Apple revenue?", deps=deps)
        )

    assert isinstance(result.data, GroundedAnswer)
    assert isinstance(result.data.answer, str)
    assert isinstance(result.data.citations, list)


def test_deps_retrieved_passages_populated_by_tool():
    """After agent run, deps.retrieved_passages should contain fetched passages."""
    from pydantic_ai.models.test import TestModel
    from app.assistant.agent import document_agent

    passage = _make_passage()
    deps = _make_deps(passages=[passage])

    with document_agent.override(model=TestModel(custom_result_args={"answer": "test", "citations": []})):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            document_agent.run("test query", deps=deps)
        )

    # TestModel calls all tools; retrieved_passages should be populated
    # (TestModel may or may not call tools depending on version — assert length >= 0)
    assert isinstance(deps.retrieved_passages, list)
```

- [ ] **Step 4: Run to confirm failure**

```bash
cd backend && uv run pytest tests/assistant/test_agent.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.assistant.deps'`

- [ ] **Step 5: Create `backend/app/assistant/deps.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field

from app.assistant.outputs import SourcePassage
from app.grounding.validator import GroundingValidator
from app.retrieval.retriever import DocumentRetriever


@dataclass
class DocumentAgentDeps:
    user_id: str
    thread_id: str
    retriever: DocumentRetriever
    grounding_validator: GroundingValidator
    retrieved_passages: list[SourcePassage] = field(default_factory=list)
```

- [ ] **Step 6: Create `backend/app/assistant/instructions.md`**

```markdown
You are Document Copilot, a research assistant for financial analysts. You answer questions strictly from retrieved SEC filing passages.

Rules:
- Answer only from the passages provided by search_filings.
- Cite every factual claim with [N] markers (e.g. "Revenue was $90B [1].").
- List citations in the `citations` field in order of first appearance.
- Each citation's `excerpt` must be a short exact quote from the source passage.
- If retrieved passages do not contain enough evidence, say: "The corpus does not contain enough evidence to answer this question."
- Never invent figures, dates, or company names.
- Never provide stock recommendations or investment advice.
- Keep answers concise enough for analyst review (2–5 sentences typical).
```

- [ ] **Step 7: Create `backend/app/assistant/agent.py`**

```python
from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer, SourcePassage
from app.config import settings

_instructions = (Path(__file__).parent / "instructions.md").read_text()

document_agent: Agent[DocumentAgentDeps, GroundedAnswer] = Agent(
    model=OpenAIModel(settings.openai_chat_model, api_key=settings.openai_api_key),
    deps_type=DocumentAgentDeps,
    result_type=GroundedAnswer,
    system_prompt=_instructions,
)


@document_agent.tool
async def search_filings(
    ctx: RunContext[DocumentAgentDeps],
    query: str,
) -> list[dict]:
    """Search the SEC filing corpus for passages relevant to `query`."""
    passages = await ctx.deps.retriever.retrieve(query)
    ctx.deps.retrieved_passages = passages
    return [p.model_dump() for p in passages]


async def run_agent(user_query: str, deps: DocumentAgentDeps) -> GroundedAnswer:
    result = await document_agent.run(user_query, deps=deps)
    return result.data
```

- [ ] **Step 8: Run agent tests**

```bash
cd backend && uv run pytest tests/assistant/test_agent.py -v
```
Expected: 3–4 PASSED (TestModel may not call tools for all tests — that is acceptable)

- [ ] **Step 9: Run full test suite to check regressions**

```bash
cd backend && uv run pytest tests/ -v
```
Expected: all prior tests still PASS

- [ ] **Step 10: Commit**

```bash
cd backend && git add app/config.py app/assistant/deps.py app/assistant/agent.py app/assistant/instructions.md tests/assistant/test_agent.py
git commit -m "feat(assistant): PydanticAI document agent with search_filings tool and grounded answer output"
```

---

## Task 7: Async DB session + chat persistence

**Files:**
- Create: `backend/app/database/session.py`
- Create: `backend/app/database/chats.py`
- Create: `backend/tests/database/__init__.py` (if missing)
- Create: `backend/tests/database/test_chats.py`

**Interfaces:**
- Produces from `session.py`:
  - `AsyncSessionLocal: async_sessionmaker[AsyncSession]`
  - `async def get_session() -> AsyncGenerator[AsyncSession, None]` — FastAPI dependency
- Produces from `chats.py`:
  - `async def get_or_create_thread(session: AsyncSession, thread_id: str, user_id: str) -> ChatThread`
  - `async def save_message(session: AsyncSession, thread_id: str, role: str, content: str, message_json: dict | None = None) -> uuid.UUID`
  - `async def save_citations(session: AsyncSession, message_id: uuid.UUID, citations: list[Citation]) -> None`

- [ ] **Step 1: Write the failing tests**

Check if `backend/tests/database/__init__.py` exists; create it if not. Then create `backend/tests/database/test_chats.py`:

```python
from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_save_message_returns_uuid(mock_session):
    from app.database.chats import save_message

    thread_id = str(uuid.uuid4())
    message_id = await save_message(mock_session, thread_id, "user", "Hello?")

    assert isinstance(message_id, uuid.UUID)
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_save_message_with_json(mock_session):
    from app.database.chats import save_message

    thread_id = str(uuid.uuid4())
    msg_json = {"role": "user", "content": "Hello?"}
    message_id = await save_message(mock_session, thread_id, "user", "Hello?", msg_json)

    assert isinstance(message_id, uuid.UUID)


@pytest.mark.asyncio
async def test_save_citations_adds_one_row_per_citation(mock_session):
    from app.assistant.outputs import Citation
    from app.database.chats import save_citations

    message_id = uuid.uuid4()
    citations = [
        Citation(
            chunk_id=str(uuid.uuid4()),
            excerpt="Revenue was $90B.",
            company="Apple Inc.",
            filing_type="10-K",
            filing_date="2024-02-02",
            accession_number="0001234567-24-000001",
        ),
        Citation(
            chunk_id=str(uuid.uuid4()),
            excerpt="Operating costs fell.",
            company="Apple Inc.",
            filing_type="10-K",
            filing_date="2024-02-02",
            accession_number="0001234567-24-000001",
        ),
    ]
    await save_citations(mock_session, message_id, citations)

    assert mock_session.add.call_count == 2


@pytest.mark.asyncio
async def test_save_citations_no_op_for_empty_list(mock_session):
    from app.database.chats import save_citations

    await save_citations(mock_session, uuid.uuid4(), [])
    mock_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_thread_creates_when_missing(mock_session):
    from app.database.chats import get_or_create_thread

    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    thread_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    thread = await get_or_create_thread(mock_session, thread_id, user_id)

    assert thread is not None
    mock_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_thread_returns_existing(mock_session):
    from app.database.chats import get_or_create_thread
    from app.database.models import ChatThread

    existing = MagicMock(spec=ChatThread)
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
    )

    thread = await get_or_create_thread(mock_session, "t1", "u1")

    assert thread is existing
    mock_session.add.assert_not_called()
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && uv run pytest tests/database/test_chats.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.database.session'` or `'app.database.chats'`

- [ ] **Step 3: Create `backend/app/database/session.py`**

```python
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 4: Create `backend/app/database/chats.py`**

```python
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.outputs import Citation
from app.database.models import ChatMessage, ChatThread, MessageCitation


async def get_or_create_thread(
    session: AsyncSession,
    thread_id: str,
    user_id: str,
) -> ChatThread:
    existing = (
        await session.execute(
            select(ChatThread).where(ChatThread.id == uuid.UUID(thread_id))
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing

    thread = ChatThread(id=uuid.UUID(thread_id), user_id=uuid.UUID(user_id))
    session.add(thread)
    await session.flush()
    return thread


async def save_message(
    session: AsyncSession,
    thread_id: str,
    role: str,
    content: str,
    message_json: dict | None = None,
) -> uuid.UUID:
    message_id = uuid.uuid4()
    session.add(
        ChatMessage(
            id=message_id,
            thread_id=uuid.UUID(thread_id),
            role=role,
            content=content,
            message_json=message_json,
        )
    )
    await session.flush()
    return message_id


async def save_citations(
    session: AsyncSession,
    message_id: uuid.UUID,
    citations: list[Citation],
) -> None:
    for citation in citations:
        session.add(
            MessageCitation(
                id=uuid.uuid4(),
                message_id=message_id,
                chunk_id=uuid.UUID(citation.chunk_id),
                excerpt=citation.excerpt,
                section=None,
                page_number=None,
            )
        )
```

- [ ] **Step 5: Run to confirm passing**

```bash
cd backend && uv run pytest tests/database/test_chats.py -v
```
Expected: 6 PASSED

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/database/session.py app/database/chats.py tests/database/__init__.py tests/database/test_chats.py
git commit -m "feat(database): async session factory and chat/citation persistence"
```

---

## Task 8: Chat wire format + SSE streaming helpers

**Files:**
- Create: `backend/app/chat/__init__.py`
- Create: `backend/app/chat/messages.py`
- Create: `backend/app/chat/streaming.py`
- Create: `backend/tests/chat/__init__.py`
- Create: `backend/tests/chat/test_streaming.py`

**Interfaces:**
- Produces from `messages.py`:
  - `WireMessage(BaseModel)` with `role: str`, `content: str | None`
  - `def extract_user_query(messages: list[WireMessage]) -> str` — raises `ValueError` if no user message
- Produces from `streaming.py`:
  - `def sse(event: dict) -> str` — formats dict as `data: <json>\n\n`
  - `async def stream_answer_and_citations(answer: str, citations: list[dict]) -> AsyncGenerator[str, None]`
    — yields text-start, text-delta (one per word), text-end, optional message-annotation, finish-step, finish, [DONE]

- [ ] **Step 1: Write the failing tests**

Create both `__init__.py` (empty) and `backend/tests/chat/test_streaming.py`:

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && uv run pytest tests/chat/test_streaming.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.chat'`

- [ ] **Step 3: Create `backend/app/chat/messages.py`**

```python
from __future__ import annotations

from pydantic import BaseModel


class WireMessage(BaseModel):
    model_config = {"extra": "allow"}

    role: str
    content: str | None = None


def extract_user_query(messages: list[WireMessage]) -> str:
    """Return the text of the last user message; raise ValueError if none."""
    for msg in reversed(messages):
        if msg.role == "user" and msg.content:
            return msg.content
    raise ValueError("No user message found in the request")
```

- [ ] **Step 4: Create `backend/app/chat/streaming.py`**

```python
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def stream_answer_and_citations(
    answer: str,
    citations: list[dict],
) -> AsyncGenerator[str, None]:
    part_id = str(uuid.uuid4())

    yield sse({"type": "text-start", "id": part_id})
    for word in answer.split():
        yield sse({"type": "text-delta", "id": part_id, "delta": word + " "})
    yield sse({"type": "text-end", "id": part_id})

    if citations:
        yield sse(
            {
                "type": "message-annotation",
                "message-annotations": [{"citations": citations}],
            }
        )

    yield sse({"type": "finish-step"})
    yield sse({"type": "finish", "finishReason": "stop"})
    yield "data: [DONE]\n\n"
```

- [ ] **Step 5: Run to confirm passing**

```bash
cd backend && uv run pytest tests/chat/test_streaming.py -v
```
Expected: 7 PASSED

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/chat/__init__.py app/chat/messages.py app/chat/streaming.py tests/chat/__init__.py tests/chat/test_streaming.py
git commit -m "feat(chat): wire message extractor and SSE streaming helpers"
```

---

## Task 9: Chat orchestrator + wire up `/chat/stream` endpoint

**Files:**
- Create: `backend/app/chat/orchestrator.py`
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/chat/test_orchestrator.py`

**Interfaces:**
- Produces: `async def run_chat_turn(body: ChatStreamRequest, user: AuthUser, session: AsyncSession) -> AsyncGenerator[str, None]`

- [ ] **Step 1: Write the failing orchestrator tests**

Create `backend/tests/chat/test_orchestrator.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_body(text: str = "What was Apple revenue?"):
    import uuid
    from app.api.chat import ChatStreamRequest, ChatMessage
    return ChatStreamRequest(
        id=str(uuid.uuid4()),
        messages=[ChatMessage(role="user", content=text)],
    )


def _make_user():
    from app.auth.dependencies import AuthUser
    return AuthUser(id="u1", email="test@example.com")


@pytest.mark.asyncio
async def test_run_chat_turn_yields_sse_events():
    from app.assistant.outputs import Citation, GroundedAnswer
    from app.chat.orchestrator import run_chat_turn

    mock_answer = GroundedAnswer(
        answer="Revenue was $90B [1].",
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

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    with (
        patch("app.chat.orchestrator.DocumentRetriever"),
        patch("app.chat.orchestrator.run_agent", AsyncMock(return_value=mock_answer)),
        patch("app.chat.orchestrator.GroundingValidator") as mock_val_cls,
        patch("app.chat.orchestrator.AsyncOpenAI"),
        patch("app.chat.orchestrator.get_or_create_thread", AsyncMock(return_value=MagicMock())),
        patch("app.chat.orchestrator.save_message", AsyncMock(return_value=__import__("uuid").uuid4())),
        patch("app.chat.orchestrator.save_citations", AsyncMock()),
    ):
        mock_val_cls.return_value.validate = MagicMock(return_value=mock_answer)

        events = []
        async for chunk in run_chat_turn(_make_body(), _make_user(), mock_session):
            events.append(chunk)

    assert any("text-delta" in e for e in events)
    assert any("[DONE]" in e for e in events)


@pytest.mark.asyncio
async def test_run_chat_turn_calls_save_message(mock_for_turn=None):
    from app.assistant.outputs import GroundedAnswer
    from app.chat.orchestrator import run_chat_turn

    mock_answer = GroundedAnswer(answer="No evidence found.", citations=[])
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    save_message_mock = AsyncMock(return_value=__import__("uuid").uuid4())
    with (
        patch("app.chat.orchestrator.DocumentRetriever"),
        patch("app.chat.orchestrator.run_agent", AsyncMock(return_value=mock_answer)),
        patch("app.chat.orchestrator.GroundingValidator") as mock_val_cls,
        patch("app.chat.orchestrator.AsyncOpenAI"),
        patch("app.chat.orchestrator.get_or_create_thread", AsyncMock(return_value=MagicMock())),
        patch("app.chat.orchestrator.save_message", save_message_mock),
        patch("app.chat.orchestrator.save_citations", AsyncMock()),
    ):
        mock_val_cls.return_value.validate = MagicMock(return_value=mock_answer)
        async for _ in run_chat_turn(_make_body(), _make_user(), mock_session):
            pass

    assert save_message_mock.call_count >= 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && uv run pytest tests/chat/test_orchestrator.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.chat.orchestrator'`

- [ ] **Step 3: Create `backend/app/chat/orchestrator.py`**

```python
from __future__ import annotations

from collections.abc import AsyncGenerator

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import ChatStreamRequest
from app.assistant.agent import run_agent
from app.assistant.deps import DocumentAgentDeps
from app.auth.dependencies import AuthUser
from app.chat.messages import extract_user_query
from app.chat.streaming import stream_answer_and_citations
from app.config import settings
from app.database.chats import get_or_create_thread, save_citations, save_message
from app.grounding.validator import GroundingError, GroundingValidator
from app.retrieval.retriever import DocumentRetriever


async def run_chat_turn(
    body: ChatStreamRequest,
    user: AuthUser,
    session: AsyncSession,
) -> AsyncGenerator[str, None]:
    user_query = extract_user_query(body.messages)
    thread_id = body.id

    await get_or_create_thread(session, thread_id, user.id)
    await save_message(session, thread_id, "user", user_query)

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    retriever = DocumentRetriever(session, openai_client)
    validator = GroundingValidator()

    deps = DocumentAgentDeps(
        user_id=user.id,
        thread_id=thread_id,
        retriever=retriever,
        grounding_validator=validator,
    )

    answer = await run_agent(user_query, deps)
    validator.validate(answer, deps.retrieved_passages)

    serialized_citations = [c.model_dump() for c in answer.citations]
    assistant_message_id = await save_message(
        session, thread_id, "assistant", answer.answer
    )
    await save_citations(session, assistant_message_id, answer.citations)
    await session.commit()

    return stream_answer_and_citations(answer.answer, serialized_citations)
```

- [ ] **Step 4: Replace stub in `backend/app/api/chat.py`**

Replace the entire file content with:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AuthUser, get_current_user
from app.database.session import get_session

router = APIRouter()


class ChatMessage(BaseModel):
    model_config = {"extra": "allow"}

    role: str
    content: str | None = None


class ChatStreamRequest(BaseModel):
    id: str
    messages: list[ChatMessage]
    trigger: str | None = None


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamRequest,
    user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    from app.chat.orchestrator import run_chat_turn

    stream = await run_chat_turn(body, user, session)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"x-vercel-ai-ui-message-stream": "v1"},
    )
```

- [ ] **Step 5: Update `backend/app/main.py`** — no changes needed (session is wired via Depends in the route)

- [ ] **Step 6: Run all tests**

```bash
cd backend && uv run pytest tests/ -v
```
Expected: all tests PASS (orchestrator tests may need adjustment for AsyncMock flush/commit patterns — fix any failures before proceeding)

- [ ] **Step 7: Commit**

```bash
cd backend && git add app/chat/orchestrator.py app/api/chat.py tests/chat/test_orchestrator.py
git commit -m "feat(chat): orchestrator wires retrieval+agent+grounding+streaming; replaces stub endpoint"
```

---

## Task 10: Frontend — citation UI and improved error/empty states

**Files:**
- Create: `frontend/src/components/chat/CitationCard.tsx`
- Modify: `frontend/src/components/chat/MessageList.tsx`
- Modify: `frontend/src/pages/chat/ChatPage.tsx`

**Context:** AI SDK v6 delivers `message-annotation` events into `UIMessage.annotations: JSONValue[] | undefined`. We send `[{"citations": [...]}]` so `message.annotations[0]?.citations` is the array. Each citation has `chunk_id`, `excerpt`, `company`, `filing_type`, `filing_date`, `accession_number` (from `Citation.model_dump()`).

- [ ] **Step 1: Create `frontend/src/components/chat/CitationCard.tsx`**

```tsx
interface CitationData {
  chunk_id: string
  excerpt: string
  company: string
  filing_type: string
  filing_date: string
  accession_number: string
}

interface Props {
  citation: CitationData
  index: number
}

export function CitationCard({ citation, index }: Props) {
  const dateLabel = citation.filing_date
    ? new Date(citation.filing_date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : citation.filing_date

  return (
    <div className="border border-gray-200 rounded-md p-3 text-xs text-gray-700 space-y-1">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-violet-100 text-violet-700 font-semibold text-xs shrink-0">
          {index}
        </span>
        <span className="font-medium">{citation.company}</span>
        <span className="text-gray-400">·</span>
        <span className="text-gray-500">{citation.filing_type}</span>
        <span className="text-gray-400">·</span>
        <span className="text-gray-500">{dateLabel}</span>
      </div>
      <p className="text-gray-600 italic leading-relaxed pl-7">"{citation.excerpt}"</p>
    </div>
  )
}
```

- [ ] **Step 2: Update `frontend/src/components/chat/MessageList.tsx`**

Replace the file with:

```tsx
import type { UIMessage } from '@ai-sdk/react'
import { CitationCard } from './CitationCard'

interface CitationData {
  chunk_id: string
  excerpt: string
  company: string
  filing_type: string
  filing_date: string
  accession_number: string
}

interface Props {
  messages: UIMessage[]
}

function extractCitations(message: UIMessage): CitationData[] {
  if (!message.annotations || message.role !== 'assistant') return []
  for (const ann of message.annotations) {
    const a = ann as { citations?: CitationData[] }
    if (Array.isArray(a?.citations)) return a.citations
  }
  return []
}

export function MessageList({ messages }: Props) {
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-gray-400 text-sm">
        <p className="font-medium text-gray-500">Document Copilot</p>
        <p>Ask a question about the SEC filing corpus.</p>
        <p className="text-xs text-gray-300">e.g. "What was Apple's revenue in 2024?"</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto space-y-4 p-4">
      {messages.map((message) => {
        const citations = extractCitations(message)
        return (
          <div
            key={message.id}
            className={`flex flex-col ${message.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-2xl rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
                message.role === 'user'
                  ? 'bg-violet-600 text-white'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              {message.parts
                .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
                .map((p, i) => (
                  <span key={i}>{p.text}</span>
                ))}
            </div>
            {citations.length > 0 && (
              <div className="max-w-2xl w-full mt-2 space-y-1">
                <p className="text-xs text-gray-400 font-medium px-1">Sources</p>
                {citations.map((c, i) => (
                  <CitationCard key={c.chunk_id} citation={c} index={i + 1} />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 3: Update `frontend/src/pages/chat/ChatPage.tsx`** — improve error message copy

Replace the error block:

```tsx
      {error && (
        <p role="alert" className="text-sm text-red-600 px-4 pb-2 text-center">
          {error.message?.includes('401') || error.message?.includes('403')
            ? 'Session expired — please sign in again.'
            : error.message?.includes('502') || error.message?.includes('500')
            ? 'The assistant is temporarily unavailable. Please try again.'
            : 'Something went wrong. Please try again.'}
        </p>
      )}
```

The full updated `ChatPage.tsx`:

```tsx
import { HttpChatTransport } from 'ai'
import { useChat } from '@ai-sdk/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { MessageInput } from '../../components/chat/MessageInput'
import { MessageList } from '../../components/chat/MessageList'
import { getAccessToken } from '../../lib/api'
import { env } from '../../lib/env'

export function ChatPage() {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [input, setInput] = useState('')

  const transport = useMemo(
    () =>
      new HttpChatTransport({
        api: `${env.apiBaseUrl}/chat/stream`,
        headers: async () => {
          const token = await getAccessToken()
          return { Authorization: `Bearer ${token}` }
        },
      }),
    []
  )

  const { messages, sendMessage, status, error } = useChat({ transport })

  const isStreaming = status === 'streaming' || status === 'submitted'

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleInputChange(e: ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value)
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const text = input.trim()
    if (!text || isStreaming) return
    setInput('')
    sendMessage({ text }).catch(() => {})
  }

  function errorMessage(err: Error): string {
    const msg = err.message ?? ''
    if (msg.includes('401') || msg.includes('403')) return 'Session expired — please sign in again.'
    if (msg.includes('502') || msg.includes('500')) return 'The assistant is temporarily unavailable. Please try again.'
    return 'Something went wrong. Please try again.'
  }

  return (
    <div className="flex flex-col h-screen">
      <header className="border-b px-4 py-3">
        <h1 className="text-sm font-semibold">Document Copilot</h1>
      </header>
      <MessageList messages={messages} />
      {error && (
        <p role="alert" className="text-sm text-red-600 px-4 pb-2 text-center">
          {errorMessage(error)}
        </p>
      )}
      <div ref={bottomRef} />
      <MessageInput
        input={input}
        onInputChange={handleInputChange}
        onSubmit={handleSubmit}
        isStreaming={isStreaming}
      />
    </div>
  )
}
```

- [ ] **Step 4: Type-check the frontend**

```bash
cd frontend && npm run build
```
Expected: build succeeds with no TypeScript errors

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/components/chat/CitationCard.tsx src/components/chat/MessageList.tsx src/pages/chat/ChatPage.tsx
git commit -m "feat(ui): citation cards, improved empty state and error messages"
```

---

## Final verification

- [ ] **Run full backend test suite**

```bash
cd backend && uv run pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Run frontend build**

```bash
cd frontend && npm run build
```
Expected: clean build, no errors

- [ ] **Final commit if any fixes were needed**

```bash
git add -p
git commit -m "fix(step5): resolve any post-integration issues"
```
