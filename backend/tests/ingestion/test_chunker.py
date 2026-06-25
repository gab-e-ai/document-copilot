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
