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
