# Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate the Supabase corpus by parsing raw SEC 10-K HTML filings from `data/downloads/`, chunking and embedding them, and writing `source_documents` + `document_chunks` rows so Step 5 can run retrieval against real data.

**Architecture:** A standalone backend batch pipeline (`python -m app.ingestion`) reads the manifest at `data/downloads/manifest.json`, converts each HTML filing to Markdown with `html2text`, splits into token-bounded paragraphs with `tiktoken`, calls OpenAI `text-embedding-3-small` in batches of 100, and upserts via SQLAlchemy ORM. The Postgres `search_vector` column is `GENERATED ALWAYS AS STORED`, so only `chunk_text` is written — Postgres fills the `tsvector` automatically. Idempotency: skip any `accession_number` already in `source_documents`.

**Tech Stack:** Python 3.12, FastAPI project venv (`uv run`), `html2text` (HTML → Markdown), `tiktoken` (token counting, `cl100k_base`), `openai==2.41.1` (already installed), SQLAlchemy ORM (already installed)

## Global Constraints

- Backend: Python ≥ 3.12; all commands via `uv run` from `backend/`
- Backend: `app.config.settings` is the single source of truth — no `os.getenv` in app code
- Backend: unit tests only (no live network, no live DB); mock OpenAI and SQLAlchemy Session in all tests
- No new FastAPI routes or async code in this step — the pipeline is a sync batch script
- `search_vector` is a `GENERATED ALWAYS AS STORED` tsvector — never write to it; fix `DocumentChunk` model to reflect this with `Computed()`
- Embedding model: `settings.openai_embedding_model` (default `"text-embedding-3-small"`), dimensions: `settings.openai_embedding_dimensions` (default `1536`)
- Chunk size: 512 tokens max; overlap: 64 tokens; token encoding: `cl100k_base`
- Batch size for OpenAI embeddings API: 100 chunks per request
- Idempotency: skip a document whose `accession_number` already exists in `source_documents`
- Company name mapping (all five tickers present in `data/downloads/`): AAPL → "Apple Inc.", MSFT → "Microsoft Corporation", NVDA → "NVIDIA Corporation", AMZN → "Amazon.com, Inc.", GOOGL → "Alphabet Inc."
- `metadata_json` on each chunk must contain: `ticker`, `company`, `filing_type`, `filing_date`, `fiscal_year`, `accession_number`, `source_url`

---

## File Map

```
backend/
├── app/
│   ├── database/
│   │   └── models.py                 MODIFY — add Computed() to search_vector column
│   └── ingestion/
│       ├── __init__.py               CREATE — empty package marker
│       ├── __main__.py               CREATE — entry point for `python -m app.ingestion`
│       ├── html_to_markdown.py       CREATE — HTML → clean Markdown string
│       ├── chunker.py                CREATE — paragraph-aware token-bounded chunker
│       ├── embedder.py               CREATE — batched OpenAI sync embedding calls
│       ├── writer.py                 CREATE — SQLAlchemy ORM upsert for SourceDocument + DocumentChunk
│       └── pipeline.py               CREATE — orchestrates parser → chunker → embedder → writer per filing
└── tests/
    └── ingestion/
        ├── __init__.py               CREATE — empty
        ├── test_html_to_markdown.py  CREATE — unit tests for HTML → Markdown conversion
        ├── test_chunker.py           CREATE — unit tests for chunking and token counting
        ├── test_embedder.py          CREATE — unit tests with mocked OpenAI client
        ├── test_writer.py            CREATE — unit tests with mocked SQLAlchemy Session
        └── test_pipeline.py          CREATE — integration-style test with mocked sub-components
```

---

## Task 1: HTML-to-Markdown converter + model fix

**Files:**
- Modify: `backend/app/database/models.py` (add `Computed` to `search_vector`)
- Modify: `backend/pyproject.toml` (add `html2text`, `tiktoken`)
- Create: `backend/app/ingestion/__init__.py`
- Create: `backend/app/ingestion/html_to_markdown.py`
- Create: `backend/tests/ingestion/__init__.py`
- Create: `backend/tests/ingestion/test_html_to_markdown.py`

**Interfaces:**
- Consumes: nothing
- Produces: `html_to_markdown(html: str) -> str` from `app.ingestion.html_to_markdown`

- [ ] **Step 1: Fix `DocumentChunk.search_vector` in models.py**

`search_vector` is a `GENERATED ALWAYS AS STORED` tsvector column in Postgres. SQLAlchemy must never write to it. Add `Computed()` so the ORM treats it as server-generated.

Open `backend/app/database/models.py`. At the top, add `Computed` to the sqlalchemy import:

```python
from sqlalchemy import (
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
```

Replace the `search_vector` mapped column in `DocumentChunk`:

```python
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', chunk_text)", persisted=True),
        nullable=True,
    )
```

- [ ] **Step 2: Add dependencies**

```bash
cd backend && uv add html2text tiktoken
```

Verify the packages appear in `pyproject.toml` with exact version pins, and `uv.lock` is updated.

- [ ] **Step 3: Verify existing tests still pass after model change**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: all 20 tests pass. The model change is schema-only; no migration needed because the Postgres column already exists as GENERATED.

- [ ] **Step 4: Create empty package markers**

Create `backend/app/ingestion/__init__.py`:

```python
```

Create `backend/tests/ingestion/__init__.py`:

```python
```

- [ ] **Step 5: Write failing tests for html_to_markdown**

Create `backend/tests/ingestion/test_html_to_markdown.py`:

```python
from app.ingestion.html_to_markdown import html_to_markdown


def test_strips_html_tags():
    html = "<p>Hello <b>world</b></p>"
    result = html_to_markdown(html)
    assert "Hello" in result
    assert "world" in result
    assert "<b>" not in result
    assert "<p>" not in result


def test_preserves_heading_text():
    html = "<h1>Section One</h1><p>Content here.</p>"
    result = html_to_markdown(html)
    assert "Section One" in result
    assert "Content here." in result


def test_empty_body_returns_blank():
    result = html_to_markdown("<html><body></body></html>")
    assert result.strip() == ""


def test_returns_string():
    result = html_to_markdown("<p>text</p>")
    assert isinstance(result, str)
```

- [ ] **Step 6: Run tests — expect FAIL (ImportError)**

```bash
cd backend && uv run pytest tests/ingestion/test_html_to_markdown.py -v
```

Expected: 4 errors / collection failures (`No module named 'app.ingestion.html_to_markdown'`).

- [ ] **Step 7: Implement html_to_markdown**

Create `backend/app/ingestion/html_to_markdown.py`:

```python
import html2text as _html2text


def html_to_markdown(html: str) -> str:
    h = _html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_tables = False
    h.body_width = 0  # don't hard-wrap lines
    h.unicode_snob = True
    return h.handle(html)
```

- [ ] **Step 8: Run tests — expect PASS**

```bash
cd backend && uv run pytest tests/ingestion/test_html_to_markdown.py -v
```

Expected: 4 passed.

- [ ] **Step 9: Run full suite to check no regressions**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
cd backend && git add app/database/models.py app/ingestion/__init__.py \
  app/ingestion/html_to_markdown.py \
  tests/ingestion/__init__.py tests/ingestion/test_html_to_markdown.py \
  pyproject.toml uv.lock
git commit -m "feat(ingestion): html-to-markdown converter, fix DocumentChunk.search_vector as Computed"
```

---

## Task 2: Paragraph-aware text chunker

**Files:**
- Create: `backend/app/ingestion/chunker.py`
- Create: `backend/tests/ingestion/test_chunker.py`

**Interfaces:**
- Consumes: `tiktoken` (installed in Task 1)
- Produces:
  - `count_tokens(text: str) -> int` from `app.ingestion.chunker`
  - `chunk_text(text: str, max_tokens: int = 512, overlap_tokens: int = 64) -> list[str]` from `app.ingestion.chunker`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/ingestion/test_chunker.py`:

```python
from app.ingestion.chunker import chunk_text, count_tokens


def test_count_tokens_returns_positive_int():
    assert count_tokens("hello world") > 0
    assert count_tokens("hello world") < 10


def test_count_tokens_empty_string():
    assert count_tokens("") == 0


def test_single_paragraph_below_limit_returns_one_chunk():
    chunks = chunk_text("This is one short paragraph.", max_tokens=512)
    assert len(chunks) == 1
    assert "short paragraph" in chunks[0]


def test_two_paragraphs_that_fit_return_one_chunk():
    chunks = chunk_text("First paragraph.\n\nSecond paragraph.", max_tokens=512)
    assert len(chunks) == 1
    assert "First paragraph" in chunks[0]
    assert "Second paragraph" in chunks[0]


def test_many_paragraphs_exceeding_limit_splits():
    # ~6 words × 30 paragraphs ≈ 180 tokens total; limit 50 → must split
    text = "\n\n".join([f"Paragraph {i} has some content here." for i in range(30)])
    chunks = chunk_text(text, max_tokens=50, overlap_tokens=10)
    assert len(chunks) > 1


def test_each_chunk_within_generous_token_bound():
    # Generous bound = max_tokens + one average paragraph to allow partial overrun at boundaries
    text = "\n\n".join([f"Sentence number {i} with a few extra words added." for i in range(100)])
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=20)
    for chunk in chunks:
        # Allow up to 2× to account for a single large paragraph at a boundary
        assert count_tokens(chunk) <= 200


def test_empty_string_returns_empty_list():
    assert chunk_text("") == []


def test_whitespace_only_returns_empty_list():
    assert chunk_text("   \n\n   \n\n  ") == []


def test_all_content_preserved_across_chunks():
    paragraphs = [f"Unique fact {i}." for i in range(20)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_tokens=50, overlap_tokens=10)
    combined = " ".join(chunks)
    for p in paragraphs:
        assert p in combined
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && uv run pytest tests/ingestion/test_chunker.py -v
```

Expected: ImportError on all tests.

- [ ] **Step 3: Implement chunker**

Create `backend/app/ingestion/chunker.py`:

```python
import tiktoken

_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def chunk_text(
    text: str,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[str]:
    """Split text into overlapping, token-bounded chunks on paragraph boundaries.

    Paragraphs are delimited by double newlines. A paragraph that alone exceeds
    max_tokens is kept as its own chunk without further splitting.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    buf: list[str] = []
    buf_tokens = 0

    for para in paragraphs:
        pt = count_tokens(para)
        if buf and buf_tokens + pt > max_tokens:
            # Flush current buffer
            chunks.append("\n\n".join(buf))
            # Keep trailing paragraphs whose total is within overlap_tokens
            overlap_buf: list[str] = []
            overlap_count = 0
            for p in reversed(buf):
                p_tokens = count_tokens(p)
                if overlap_count + p_tokens > overlap_tokens:
                    break
                overlap_buf.insert(0, p)
                overlap_count += p_tokens
            buf = overlap_buf
            buf_tokens = overlap_count
        buf.append(para)
        buf_tokens += pt

    if buf:
        chunks.append("\n\n".join(buf))

    return chunks
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd backend && uv run pytest tests/ingestion/test_chunker.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Run full suite**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/chunker.py backend/tests/ingestion/test_chunker.py
git commit -m "feat(ingestion): paragraph-aware token-bounded chunker"
```

---

## Task 3: OpenAI embedder (batched, sync)

**Files:**
- Create: `backend/app/ingestion/embedder.py`
- Create: `backend/tests/ingestion/test_embedder.py`

**Interfaces:**
- Consumes: `openai.OpenAI` (sync client, already installed)
- Produces: `embed_chunks(chunks: list[str], client: OpenAI, model: str, dimensions: int) -> list[list[float]]` from `app.ingestion.embedder`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/ingestion/test_embedder.py`:

```python
from unittest.mock import MagicMock

from app.ingestion.embedder import BATCH_SIZE, embed_chunks


def _mock_client(n: int) -> MagicMock:
    """Return a mock OpenAI client whose embeddings.create returns n embeddings."""
    client = MagicMock()

    def fake_create(input, model, dimensions):  # noqa: A002
        resp = MagicMock()
        resp.data = [MagicMock(embedding=[0.0] * dimensions) for _ in input]
        return resp

    client.embeddings.create.side_effect = fake_create
    return client


def test_returns_one_embedding_per_chunk():
    client = _mock_client(3)
    result = embed_chunks(["a", "b", "c"], client, "text-embedding-3-small", 1536)
    assert len(result) == 3


def test_each_embedding_has_correct_dimension():
    client = _mock_client(2)
    result = embed_chunks(["hello", "world"], client, "text-embedding-3-small", 1536)
    assert all(len(e) == 1536 for e in result)


def test_empty_input_returns_empty_list_without_calling_api():
    client = MagicMock()
    result = embed_chunks([], client, "text-embedding-3-small", 1536)
    assert result == []
    client.embeddings.create.assert_not_called()


def test_batches_into_groups_of_batch_size():
    total = BATCH_SIZE * 2 + 10
    client = _mock_client(total)
    embed_chunks([f"chunk {i}" for i in range(total)], client, "text-embedding-3-small", 1536)
    assert client.embeddings.create.call_count == 3  # ceil(total / BATCH_SIZE)


def test_single_batch_makes_one_api_call():
    client = _mock_client(5)
    embed_chunks([f"c{i}" for i in range(5)], client, "text-embedding-3-small", 1536)
    assert client.embeddings.create.call_count == 1
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && uv run pytest tests/ingestion/test_embedder.py -v
```

Expected: ImportError on all tests.

- [ ] **Step 3: Implement embedder**

Create `backend/app/ingestion/embedder.py`:

```python
from openai import OpenAI

BATCH_SIZE = 100


def embed_chunks(
    chunks: list[str],
    client: OpenAI,
    model: str,
    dimensions: int,
) -> list[list[float]]:
    """Embed chunks in batches of BATCH_SIZE. Returns one float list per chunk."""
    if not chunks:
        return []

    embeddings: list[list[float]] = []
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        response = client.embeddings.create(input=batch, model=model, dimensions=dimensions)
        embeddings.extend(item.embedding for item in response.data)
    return embeddings
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd backend && uv run pytest tests/ingestion/test_embedder.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run full suite**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/embedder.py backend/tests/ingestion/test_embedder.py
git commit -m "feat(ingestion): batched OpenAI embedder"
```

---

## Task 4: Database writer + pipeline orchestrator

**Files:**
- Create: `backend/app/ingestion/writer.py`
- Create: `backend/app/ingestion/pipeline.py`
- Create: `backend/app/ingestion/__main__.py`
- Create: `backend/tests/ingestion/test_writer.py`
- Create: `backend/tests/ingestion/test_pipeline.py`

**Interfaces:**
- Consumes:
  - `html_to_markdown(html: str) -> str` from `app.ingestion.html_to_markdown`
  - `chunk_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]` from `app.ingestion.chunker`
  - `count_tokens(text: str) -> int` from `app.ingestion.chunker`
  - `embed_chunks(chunks, client, model, dimensions) -> list[list[float]]` from `app.ingestion.embedder`
  - `SourceDocument`, `DocumentChunk` from `app.database.models`
  - `settings` from `app.config`
- Produces:
  - `ingest_document(entry: dict, content_markdown: str, chunks: list[str], embeddings: list[list[float]], token_counts: list[int], session: Session) -> int` from `app.ingestion.writer` (returns chunk count, 0 if skipped)
  - `run_pipeline(manifest_path: Path, downloads_dir: Path) -> None` from `app.ingestion.pipeline`
  - CLI: `cd backend && uv run python -m app.ingestion [--manifest PATH] [--downloads PATH]`

- [ ] **Step 1: Write failing writer tests**

Create `backend/tests/ingestion/test_writer.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && uv run pytest tests/ingestion/test_writer.py -v
```

Expected: ImportError on all tests.

- [ ] **Step 3: Implement writer**

Create `backend/app/ingestion/writer.py`:

```python
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
```

- [ ] **Step 4: Run writer tests — expect PASS**

```bash
cd backend && uv run pytest tests/ingestion/test_writer.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Write failing pipeline tests**

Create `backend/tests/ingestion/test_pipeline.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.pipeline import run_pipeline


@pytest.fixture()
def corpus(tmp_path: Path):
    """Minimal corpus: one AAPL 10-K HTML file + matching manifest."""
    downloads = tmp_path / "downloads"
    year_dir = downloads / "2024"
    year_dir.mkdir(parents=True)
    html_file = year_dir / "aapl.htm"
    html_file.write_text("<html><body><h1>AAPL 10-K</h1><p>Revenue grew.</p></body></html>")

    manifest = {
        "filings": [
            {
                "ticker": "AAPL",
                "form": "10-K",
                "filing_date": "2024-11-01",
                "report_date": "2024-09-28",
                "accession_number": "0000320193-24-000001",
                "source_url": "https://sec.gov/aapl.htm",
                "local_path": "2024/aapl.htm",
            }
        ]
    }
    manifest_path = downloads / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path, downloads


def test_pipeline_calls_embed_and_write_for_each_filing(corpus):
    manifest_path, downloads_dir = corpus

    with (
        patch("app.ingestion.pipeline.OpenAI") as mock_openai_cls,
        patch("app.ingestion.pipeline.create_engine"),
        patch("app.ingestion.pipeline.Session") as mock_session_cls,
        patch("app.ingestion.pipeline.embed_chunks", return_value=[[0.1] * 1536]) as mock_embed,
        patch("app.ingestion.pipeline.ingest_document", return_value=1) as mock_write,
        patch("app.ingestion.pipeline.settings") as mock_settings,
    ):
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_embedding_model = "text-embedding-3-small"
        mock_settings.openai_embedding_dimensions = 1536
        mock_settings.database_url = "postgresql+psycopg://localhost/test"

        mock_session_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        run_pipeline(manifest_path, downloads_dir)

    mock_embed.assert_called_once()
    mock_write.assert_called_once()


def test_pipeline_skips_missing_local_file(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    manifest = {
        "filings": [
            {
                "ticker": "AAPL",
                "form": "10-K",
                "filing_date": "2024-11-01",
                "report_date": "2024-09-28",
                "accession_number": "0000320193-24-000001",
                "source_url": "https://sec.gov/aapl.htm",
                "local_path": "2024/nonexistent.htm",
            }
        ]
    }
    manifest_path = downloads / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    with (
        patch("app.ingestion.pipeline.OpenAI"),
        patch("app.ingestion.pipeline.create_engine"),
        patch("app.ingestion.pipeline.embed_chunks") as mock_embed,
        patch("app.ingestion.pipeline.ingest_document") as mock_write,
        patch("app.ingestion.pipeline.settings") as mock_settings,
    ):
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_embedding_model = "text-embedding-3-small"
        mock_settings.openai_embedding_dimensions = 1536
        mock_settings.database_url = "postgresql+psycopg://localhost/test"

        run_pipeline(manifest_path, downloads_dir)

    mock_embed.assert_not_called()
    mock_write.assert_not_called()
```

- [ ] **Step 6: Run pipeline tests — expect FAIL**

```bash
cd backend && uv run pytest tests/ingestion/test_pipeline.py -v
```

Expected: ImportError on all tests.

- [ ] **Step 7: Implement pipeline orchestrator**

Create `backend/app/ingestion/pipeline.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

from openai import OpenAI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.chunker import chunk_text, count_tokens
from app.ingestion.embedder import embed_chunks
from app.ingestion.html_to_markdown import html_to_markdown
from app.ingestion.writer import ingest_document

_MAX_TOKENS = 512
_OVERLAP_TOKENS = 64


def run_pipeline(manifest_path: Path, downloads_dir: Path) -> None:
    manifest = json.loads(manifest_path.read_text())
    client = OpenAI(api_key=settings.openai_api_key)
    engine = create_engine(settings.database_url)

    total_docs = 0
    total_chunks = 0

    for entry in manifest["filings"]:
        html_path = downloads_dir / entry["local_path"]
        if not html_path.exists():
            print(f"  SKIP {entry['ticker']} {entry['filing_date']}: {html_path} not found")
            continue

        print(f"Processing {entry['ticker']} {entry['filing_date']} ...", end=" ", flush=True)

        html = html_path.read_text(encoding="utf-8", errors="replace")
        md = html_to_markdown(html)
        chunks = chunk_text(md, max_tokens=_MAX_TOKENS, overlap_tokens=_OVERLAP_TOKENS)
        token_counts = [count_tokens(c) for c in chunks]
        embeddings = embed_chunks(
            chunks,
            client,
            settings.openai_embedding_model,
            settings.openai_embedding_dimensions,
        )

        with Session(engine) as session:
            n = ingest_document(entry, md, chunks, embeddings, token_counts, session)

        if n == 0:
            print("already ingested, skipped.")
        else:
            print(f"{n} chunks written.")
            total_docs += 1
            total_chunks += n

    print(f"\nDone: {total_docs} document(s), {total_chunks} chunk(s) ingested.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest SEC filings into Supabase.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data" / "downloads" / "manifest.json",
    )
    parser.add_argument(
        "--downloads",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data" / "downloads",
    )
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        print("Run: uv run data/download.py", file=sys.stderr)
        sys.exit(1)

    run_pipeline(args.manifest, args.downloads)
```

- [ ] **Step 8: Create CLI entry point**

Create `backend/app/ingestion/__main__.py`:

```python
from app.ingestion.pipeline import main

main()
```

- [ ] **Step 9: Run pipeline tests — expect PASS**

```bash
cd backend && uv run pytest tests/ingestion/test_pipeline.py -v
```

Expected: 2 passed.

- [ ] **Step 10: Run full suite**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: all tests pass (≥ 24 total).

- [ ] **Step 11: Smoke-test CLI help**

```bash
cd backend && uv run python -m app.ingestion --help
```

Expected: prints usage showing `--manifest` and `--downloads` arguments, exits 0.

- [ ] **Step 12: Commit**

```bash
git add backend/app/ingestion/writer.py backend/app/ingestion/pipeline.py \
  backend/app/ingestion/__main__.py \
  backend/tests/ingestion/test_writer.py backend/tests/ingestion/test_pipeline.py
git commit -m "feat(ingestion): database writer, pipeline orchestrator, and CLI entry point"
```

---

## Self-Review

### Spec Coverage

| Architecture requirement | Task |
|---|---|
| HTML SEC filings → Markdown | Task 1 (`html_to_markdown`) |
| Paragraph-aware chunking, 512-token max, 64-token overlap | Task 2 (`chunk_text`) |
| Token counting via `cl100k_base` | Task 2 (`count_tokens`) |
| OpenAI `text-embedding-3-small`, 1536 dims, batch 100 | Task 3 (`embed_chunks`) |
| Write `source_documents` row per filing | Task 4 (`ingest_document` → `SourceDocument`) |
| Write `document_chunks` rows with embedding + metadata | Task 4 (`ingest_document` → `DocumentChunk`) |
| `search_vector` auto-populated by Postgres GENERATED column | Task 1 (`Computed()` model fix) |
| `metadata_json` with all 7 required fields | Task 4 (`ingest_document`, `metadata_json` dict) |
| Idempotency: skip already-ingested `accession_number` | Task 4 (`ingest_document` early-return) |
| No live network in tests; mock OpenAI and SQLAlchemy Session | Tasks 3, 4 (all tests mock clients/sessions) |
| All commands via `uv run` from `backend/` | Tasks 1–4 (all `cd backend && uv run ...`) |
| `settings` as single source of truth | Task 4 (`pipeline.py` reads `settings.*`) |
| CLI: `python -m app.ingestion` | Task 4 (`__main__.py`) |

### Placeholder Scan

No TODOs, no TBDs, no "similar to above" references. Every step has exact code.

### Type Consistency

- `chunk_text` returns `list[str]`; `embed_chunks` consumes `list[str]` and returns `list[list[float]]`; `ingest_document` consumes `list[str]`, `list[list[float]]`, `list[int]` — all consistent across Tasks 2, 3, 4.
- `count_tokens` returns `int`; used as `token_counts: list[int]` in `pipeline.py` — consistent.
- `ingest_document(entry, content_markdown, chunks, embeddings, token_counts, session) -> int` — same signature in writer.py (produces) and test_writer.py + test_pipeline.py (consumes).
- `run_pipeline(manifest_path: Path, downloads_dir: Path) -> None` — same signature in pipeline.py (produces) and test_pipeline.py (consumes).
- `COMPANY_NAMES` exported from `writer.py`, imported in `test_writer.py` — consistent.
