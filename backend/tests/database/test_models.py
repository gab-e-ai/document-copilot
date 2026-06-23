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
