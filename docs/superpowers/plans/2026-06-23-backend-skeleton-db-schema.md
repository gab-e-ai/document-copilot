# Backend Skeleton + DB Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the FastAPI app skeleton and apply the initial Alembic migration that creates all product tables (profiles, chats, documents, chunks) with pgvector, full-text search, and row-level security in Supabase.

**Architecture:** FastAPI app lives in `backend/app/`; SQLAlchemy models define the schema; Alembic manages migrations against Supabase's direct Postgres connection. The migration runs all Postgres-specific operations (pgvector extension, vector columns, generated tsvector columns, HNSW/GIN indexes, RLS policies, signup trigger) via raw SQL because SQLAlchemy autogenerate cannot reliably infer them.

**Tech Stack:** Python 3.12+, FastAPI, pydantic-settings, SQLAlchemy 2 (mapped_column / DeclarativeBase), Alembic, pgvector, Supabase Postgres.

## Global Constraints

- Python ≥ 3.12; all commands run via `uv run` from `backend/`
- Async by default in route handlers; no blocking I/O on the event loop
- `app.config.settings` is the single source of truth for env vars — never call `os.getenv` in app code
- Alembic must use the direct/session connection URL (`db.<ref>.supabase.co:5432`), NOT the transaction pooler
- RLS must be enabled on user-owned tables; corpus tables (source_documents, document_chunks) are protected by service-role key on the backend
- Tests: unit tests only (no live DB, no live network); pytest marks `integration` for anything that needs Supabase

---

## File Map

```
backend/
├── app/
│   ├── __init__.py                    CREATE — empty
│   ├── config.py                      CREATE — pydantic-settings Settings class + module-level instance
│   ├── main.py                        CREATE — FastAPI app, CORS, /health
│   └── database/
│       ├── __init__.py                CREATE — empty
│       └── models.py                  CREATE — all 6 SQLAlchemy models + Base
├── alembic/
│   ├── env.py                         MODIFY — import Base.metadata; read DATABASE_URL from settings
│   └── versions/
│       └── 0001_initial_schema.py     CREATE — manual migration for all tables, indexes, RLS, trigger
├── tests/
│   ├── conftest.py                    CREATE — sets fake env vars before imports via os.environ.setdefault
│   ├── __init__.py                    CREATE — empty
│   ├── test_config.py                 CREATE — Settings class validation
│   ├── test_main.py                   CREATE — /health endpoint
│   └── database/
│       ├── __init__.py                CREATE — empty
│       └── test_models.py             CREATE — model structure: table names, column types, FKs
└── pyproject.toml                     MODIFY — add [tool.pytest.ini_options]
```

---

## Task 1: Config + FastAPI skeleton

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_config.py`
- Create: `backend/tests/test_main.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Produces: `app.config.Settings` class; `app.config.settings` module-level instance; `app.main.app` FastAPI instance
- Consumed by: all later tasks (models import config; routes import config and app)

- [ ] **Step 1: Add pytest config to pyproject.toml**

Open `backend/pyproject.toml` and append:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff.lint]
select = ["E", "F", "I"]
```

- [ ] **Step 2: Create test env fixture**

Create `backend/tests/conftest.py`:

```python
import os

# Set fake env vars before any app module is imported.
# Using setdefault means real env vars (e.g., CI secrets) are not overwritten.
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
```

Create `backend/tests/__init__.py` — empty file.

- [ ] **Step 3: Write failing config tests**

Create `backend/tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_loads_with_explicit_values():
    s = Settings(
        supabase_url="https://abc.supabase.co",
        supabase_anon_key="anon",
        supabase_service_role_key="service",
        database_url="postgresql://user:pass@localhost/db",
        openai_api_key="sk-test",
        _env_file=None,
    )
    assert s.openai_embedding_model == "text-embedding-3-small"
    assert s.openai_embedding_dimensions == 1536
    assert s.allowed_origins == ["http://localhost:5173"]


def test_settings_missing_required_raises():
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_parses_allowed_origins_list():
    s = Settings(
        supabase_url="https://abc.supabase.co",
        supabase_anon_key="anon",
        supabase_service_role_key="service",
        database_url="postgresql://user:pass@localhost/db",
        openai_api_key="sk-test",
        allowed_origins=["http://localhost:5173", "http://localhost:3000"],
        _env_file=None,
    )
    assert len(s.allowed_origins) == 2
```

- [ ] **Step 4: Run test — expect failure**

```bash
cd backend && uv run pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 5: Create `app/__init__.py`**

```bash
mkdir -p backend/app
touch backend/app/__init__.py
```

- [ ] **Step 6: Implement `app/config.py`**

Create `backend/app/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    allowed_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
```

- [ ] **Step 7: Run config tests — expect pass**

```bash
cd backend && uv run pytest tests/test_config.py -v
```

Expected: 3 PASSED

- [ ] **Step 8: Write failing health test**

Create `backend/tests/test_main.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 9: Run health test — expect failure**

```bash
cd backend && uv run pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 10: Implement `app/main.py`**

Create `backend/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

app = FastAPI(title="Document Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 11: Run all tests — expect all pass**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: 4 PASSED

- [ ] **Step 12: Commit**

```bash
git add backend/app/__init__.py backend/app/config.py backend/app/main.py \
        backend/tests/__init__.py backend/tests/conftest.py \
        backend/tests/test_config.py backend/tests/test_main.py \
        backend/pyproject.toml
git commit -m "feat(backend): add FastAPI skeleton with config and health endpoint"
```

---

## Task 2: SQLAlchemy models + Alembic env wiring

**Files:**
- Create: `backend/app/database/__init__.py`
- Create: `backend/app/database/models.py`
- Create: `backend/tests/database/__init__.py`
- Create: `backend/tests/database/test_models.py`
- Modify: `backend/alembic/env.py`

**Interfaces:**
- Produces: `app.database.models.Base` (DeclarativeBase with all 6 models attached); importable model classes `Profile`, `ChatThread`, `ChatMessage`, `MessageCitation`, `SourceDocument`, `DocumentChunk`
- Consumed by: Task 3 (migration imports `Base.metadata`), future tasks (ORM queries)

- [ ] **Step 1: Write failing model tests**

Create `backend/tests/database/__init__.py` — empty file.

Create `backend/tests/database/test_models.py`:

```python
import uuid
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID as PG_UUID
from pgvector.sqlalchemy import Vector

from app.database.models import (
    Base,
    ChatMessage,
    ChatThread,
    DocumentChunk,
    MessageCitation,
    Profile,
    SourceDocument,
)


def test_all_tables_registered():
    expected = {
        "profiles",
        "chat_threads",
        "chat_messages",
        "message_citations",
        "source_documents",
        "document_chunks",
    }
    assert set(Base.metadata.tables.keys()) == expected


def test_profile_primary_key():
    col = Profile.__table__.c["id"]
    assert col.primary_key
    assert isinstance(col.type, PG_UUID)


def test_chat_thread_fk_to_profiles():
    col = ChatThread.__table__.c["user_id"]
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    assert "profiles.id" in str(fks[0].target_fullname)


def test_chat_message_fk_to_threads():
    col = ChatMessage.__table__.c["thread_id"]
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    assert "chat_threads.id" in str(fks[0].target_fullname)


def test_message_citation_fks():
    msg_col = MessageCitation.__table__.c["message_id"]
    chunk_col = MessageCitation.__table__.c["chunk_id"]
    assert "chat_messages.id" in str(list(msg_col.foreign_keys)[0].target_fullname)
    assert "document_chunks.id" in str(list(chunk_col.foreign_keys)[0].target_fullname)


def test_document_chunk_has_embedding_column():
    col = DocumentChunk.__table__.c["embedding"]
    assert isinstance(col.type, Vector)


def test_document_chunk_has_search_vector_column():
    col = DocumentChunk.__table__.c["search_vector"]
    assert isinstance(col.type, TSVECTOR)


def test_document_chunk_fk_to_source_documents():
    col = DocumentChunk.__table__.c["document_id"]
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    assert "source_documents.id" in str(fks[0].target_fullname)


def test_source_document_has_accession_number_unique():
    col = SourceDocument.__table__.c["accession_number"]
    assert col.unique
```

- [ ] **Step 2: Run model tests — expect failure**

```bash
cd backend && uv run pytest tests/database/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.database'`

- [ ] **Step 3: Create `app/database/__init__.py`**

```bash
mkdir -p backend/app/database
touch backend/app/database/__init__.py
```

- [ ] **Step 4: Implement `app/database/models.py`**

Create `backend/app/database/models.py`:

```python
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    threads: Mapped[list["ChatThread"]] = relationship(back_populates="profile")


class ChatThread(Base):
    __tablename__ = "chat_threads"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    profile: Mapped["Profile"] = relationship(back_populates="threads")
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="thread")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chat_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    thread: Mapped["ChatThread"] = relationship(back_populates="messages")
    citations: Mapped[list["MessageCitation"]] = relationship(back_populates="message")


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    filing_type: Mapped[str] = mapped_column(String(20), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accession_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    # search_vector is a GENERATED ALWAYS AS STORED column managed by Postgres.
    # Defined here for ORM queries; created via raw SQL in the migration.
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["SourceDocument"] = relationship(back_populates="chunks")
    citations: Mapped[list["MessageCitation"]] = relationship(back_populates="chunk")


class MessageCitation(Base):
    __tablename__ = "message_citations"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    message: Mapped["ChatMessage"] = relationship(back_populates="citations")
    chunk: Mapped["DocumentChunk"] = relationship(back_populates="citations")
```

- [ ] **Step 5: Run model tests — expect pass**

```bash
cd backend && uv run pytest tests/database/test_models.py -v
```

Expected: 9 PASSED

- [ ] **Step 6: Update `alembic/env.py` to use models metadata**

Replace the contents of `backend/alembic/env.py` entirely:

```python
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# Make `app` importable when running alembic from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Override the placeholder URL in alembic.ini with the real one from settings.
# Must be the direct/session connection URL, not the Supabase transaction pooler.
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 7: Run all tests — expect all pass**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: all PASSED (new tests + Task 1 tests)

- [ ] **Step 8: Commit**

```bash
git add backend/app/database/__init__.py backend/app/database/models.py \
        backend/tests/database/__init__.py backend/tests/database/test_models.py \
        backend/alembic/env.py
git commit -m "feat(backend): add SQLAlchemy models and wire Alembic to app metadata"
```

---

## Task 3: Write and apply the initial migration

**Files:**
- Create: `backend/alembic/versions/0001_initial_schema.py`
- Create: `backend/.env` (from `.env.example` — contains secrets, never commit)

**Interfaces:**
- Produces: all 6 product tables in Supabase Postgres; pgvector extension; HNSW + GIN indexes; RLS policies; signup trigger
- Consumed by: every future step that reads or writes the database

> **Note:** This task applies schema directly to your Supabase project. Make sure your `.env` has the correct `DATABASE_URL` (direct/session connection) before running `alembic upgrade`.

- [ ] **Step 1: Create your `.env` file**

```bash
cd backend && cp .env.example .env
```

Open `backend/.env` and fill in the real values from the Supabase dashboard:
- **SUPABASE_URL**: Dashboard → Settings → API → Project URL
- **SUPABASE_ANON_KEY**: Dashboard → Settings → API → anon (public) key
- **SUPABASE_SERVICE_ROLE_KEY**: Dashboard → Settings → API → service_role (secret) key
- **DATABASE_URL**: Dashboard → Settings → Database → Connection string → **URI** (Session mode / direct, port 5432, host `db.<ref>.supabase.co`)
- **OPENAI_API_KEY**: your OpenAI key (not needed for the migration, but Settings() requires it)

Do NOT commit `.env`. Verify `.gitignore` includes `*.env` or `.env`.

- [ ] **Step 2: Verify `.env` is gitignored**

```bash
cd backend && git check-ignore -v .env
```

Expected output: a line confirming `.env` is ignored. If nothing is printed, open the root `.gitignore` and add `backend/.env`.

- [ ] **Step 3: Write the migration file**

Create `backend/alembic/versions/0001_initial_schema.py`:

```python
"""Initial schema: pgvector, all product tables, indexes, RLS, signup trigger."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector must exist before any vector column is created
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "profiles",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # FK to Supabase's auth.users — written as raw SQL because it crosses schemas
    op.execute(
        "ALTER TABLE profiles ADD CONSTRAINT profiles_id_fkey "
        "FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE"
    )

    op.create_table(
        "chat_threads",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "chat_messages",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "thread_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("chat_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("message_json", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "source_documents",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("filing_type", sa.String(20), nullable=False),
        sa.Column("filing_date", sa.Date, nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=True),
        sa.Column("accession_number", sa.String(50), nullable=False, unique=True),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("content_markdown", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # document_chunks has a vector(1536) column and a GENERATED tsvector column.
    # Both require explicit SQL; Alembic cannot generate them reliably.
    op.execute("""
        CREATE TABLE document_chunks (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id     uuid NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
            chunk_index     integer NOT NULL,
            chunk_text      text NOT NULL,
            embedding       vector(1536),
            search_vector   tsvector GENERATED ALWAYS AS (
                                to_tsvector('english', chunk_text)
                            ) STORED,
            token_count     integer,
            metadata_json   jsonb NOT NULL DEFAULT '{}',
            created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)

    op.create_table(
        "message_citations",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "message_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("excerpt", sa.Text, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("section", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ---------- Indexes ----------

    # HNSW index for fast approximate nearest-neighbor vector search
    op.execute("""
        CREATE INDEX document_chunks_embedding_hnsw_idx
        ON document_chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
    # GIN index for full-text search over the generated tsvector
    op.execute("""
        CREATE INDEX document_chunks_search_vector_gin_idx
        ON document_chunks USING gin (search_vector)
    """)
    # GIN index for JSON metadata filtering (ticker, company, year, etc.)
    op.execute("""
        CREATE INDEX document_chunks_metadata_json_gin_idx
        ON document_chunks USING gin (metadata_json)
    """)
    op.create_index("chat_threads_user_id_idx", "chat_threads", ["user_id"])
    op.create_index("chat_messages_thread_id_idx", "chat_messages", ["thread_id"])
    op.create_index("document_chunks_document_id_idx", "document_chunks", ["document_id"])
    op.create_index(
        "source_documents_ticker_filing_date_idx",
        "source_documents",
        ["ticker", "filing_date"],
    )

    # ---------- Signup trigger ----------
    # Automatically creates a profiles row when a user signs up via Supabase Auth.
    op.execute("""
        CREATE OR REPLACE FUNCTION public.handle_new_user()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER SET search_path = public
        AS $$
        BEGIN
            INSERT INTO public.profiles (id, email)
            VALUES (new.id, new.email)
            ON CONFLICT (id) DO NOTHING;
            RETURN new;
        END;
        $$
    """)
    op.execute("""
        CREATE OR REPLACE TRIGGER on_auth_user_created
            AFTER INSERT ON auth.users
            FOR EACH ROW EXECUTE FUNCTION public.handle_new_user()
    """)

    # ---------- Row-Level Security ----------
    for table in ("profiles", "chat_threads", "chat_messages", "message_citations"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    # profiles: each user can only see and modify their own row
    op.execute("CREATE POLICY profiles_select_own ON profiles FOR SELECT USING (auth.uid() = id)")
    op.execute("CREATE POLICY profiles_insert_own ON profiles FOR INSERT WITH CHECK (auth.uid() = id)")
    op.execute("CREATE POLICY profiles_update_own ON profiles FOR UPDATE USING (auth.uid() = id)")

    # chat_threads: owned by user_id
    op.execute("CREATE POLICY chat_threads_select_own ON chat_threads FOR SELECT USING (auth.uid() = user_id)")
    op.execute("CREATE POLICY chat_threads_insert_own ON chat_threads FOR INSERT WITH CHECK (auth.uid() = user_id)")
    op.execute("CREATE POLICY chat_threads_update_own ON chat_threads FOR UPDATE USING (auth.uid() = user_id)")
    op.execute("CREATE POLICY chat_threads_delete_own ON chat_threads FOR DELETE USING (auth.uid() = user_id)")

    # chat_messages: visible if the parent thread belongs to the user
    op.execute("""
        CREATE POLICY chat_messages_select_own ON chat_messages FOR SELECT USING (
            EXISTS (
                SELECT 1 FROM chat_threads
                WHERE id = thread_id AND user_id = auth.uid()
            )
        )
    """)
    op.execute("""
        CREATE POLICY chat_messages_insert_own ON chat_messages FOR INSERT WITH CHECK (
            EXISTS (
                SELECT 1 FROM chat_threads
                WHERE id = thread_id AND user_id = auth.uid()
            )
        )
    """)

    # message_citations: visible through message → thread ownership chain
    op.execute("""
        CREATE POLICY message_citations_select_own ON message_citations FOR SELECT USING (
            EXISTS (
                SELECT 1 FROM chat_messages m
                JOIN chat_threads t ON t.id = m.thread_id
                WHERE m.id = message_id AND t.user_id = auth.uid()
            )
        )
    """)

    # ---------- Grants ----------
    # Corpus tables are read-only for authenticated users; writes go through the
    # service-role key on the backend (which bypasses RLS entirely).
    op.execute("GRANT USAGE ON SCHEMA public TO anon, authenticated")
    op.execute("GRANT SELECT ON source_documents TO authenticated")
    op.execute("GRANT SELECT ON document_chunks TO authenticated")
    op.execute("GRANT ALL ON profiles TO authenticated")
    op.execute("GRANT ALL ON chat_threads TO authenticated")
    op.execute("GRANT ALL ON chat_messages TO authenticated")
    op.execute("GRANT SELECT, INSERT ON message_citations TO authenticated")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users")
    op.execute("DROP FUNCTION IF EXISTS public.handle_new_user()")
    op.drop_table("message_citations")
    op.execute("DROP TABLE IF EXISTS document_chunks")
    op.drop_table("source_documents")
    op.drop_table("chat_messages")
    op.drop_table("chat_threads")
    op.drop_table("profiles")
    op.execute("DROP EXTENSION IF EXISTS vector")
```

- [ ] **Step 4: Verify migration imports cleanly**

```bash
cd backend && uv run python -c "from alembic.versions import 0001_initial_schema"
```

Wait — Python can't import filenames starting with a digit directly. Verify the file is syntactically valid instead:

```bash
cd backend && uv run python -m py_compile alembic/versions/0001_initial_schema.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 5: Dry-run — generate SQL without applying**

```bash
cd backend && uv run alembic upgrade head --sql 2>&1 | head -80
```

Expected: A stream of `CREATE TABLE`, `CREATE INDEX`, `CREATE POLICY` statements printed to stdout. No connection to Supabase is made.

- [ ] **Step 6: Apply the migration to Supabase**

Ensure your `backend/.env` has the correct `DATABASE_URL` (direct connection, port 5432).

```bash
cd backend && uv run alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Context impl PostgreSQLImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, Initial schema: pgvector, ...
```

- [ ] **Step 7: Verify tables exist in Supabase**

In the Supabase Dashboard → Table Editor, confirm these tables are visible:
- `profiles`
- `chat_threads`
- `chat_messages`
- `message_citations`
- `source_documents`
- `document_chunks`

Also check Authentication → Triggers to confirm `on_auth_user_created` is listed.

- [ ] **Step 8: Run all tests — confirm nothing broke**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: all PASSED (no DB connection needed — all tests are unit tests)

- [ ] **Step 9: Commit**

```bash
git add backend/alembic/versions/0001_initial_schema.py backend/alembic/env.py
git commit -m "feat(backend): add initial Alembic migration with pgvector, RLS, and signup trigger"
```

---

## Self-Review

**Spec coverage check:**

| Architecture requirement | Covered by |
|---|---|
| `app/main.py` FastAPI entrypoint | Task 1 |
| `app/config.py` single settings source | Task 1 |
| SQLAlchemy models for all 6 tables | Task 2 |
| Alembic autogenerate support (env.py wired to Base.metadata) | Task 2 |
| `CREATE EXTENSION vector` | Task 3 migration |
| `vector(1536)` embedding column | Task 3 migration |
| Generated `tsvector` column | Task 3 migration |
| HNSW index for pgvector search | Task 3 migration |
| GIN index for full-text search | Task 3 migration |
| GIN index for JSON metadata | Task 3 migration |
| RLS enablement on user tables | Task 3 migration |
| RLS policies scoped to `auth.uid()` | Task 3 migration |
| Signup trigger → auto-create profile | Task 3 migration |
| Direct/session DB URL for Alembic | Task 3 step 1 (`.env` instructions) |
| Fail fast on missing config | Task 1 (pydantic-settings validation) |

**Placeholder scan:** No TODOs, TBDs, or "fill in later" in code blocks.

**Type consistency:**
- `Settings` fields use snake_case matching `.env.example` keys: `openai_embedding_model`, `openai_embedding_dimensions`, `allowed_origins`
- `Base` in `models.py` is the same `Base` imported in `env.py`
- Migration revision `"0001"` matches filename `0001_initial_schema.py`
