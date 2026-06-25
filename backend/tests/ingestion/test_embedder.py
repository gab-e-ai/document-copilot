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
