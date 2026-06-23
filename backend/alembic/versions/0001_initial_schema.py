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
