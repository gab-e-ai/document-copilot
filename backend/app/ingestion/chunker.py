import tiktoken

_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def _split_oversized(para: str, max_tokens: int) -> list[str]:
    """Hard-split a paragraph that alone exceeds max_tokens into token-bounded pieces.

    Prevents any single chunk from exceeding the embedding model's input limit
    (e.g. a large table rendered as one block with no double-newline breaks).
    """
    tokens = _ENCODING.encode(para)
    if len(tokens) <= max_tokens:
        return [para]
    return [
        _ENCODING.decode(tokens[i : i + max_tokens]).strip()
        for i in range(0, len(tokens), max_tokens)
    ]


def chunk_text(
    text: str,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[str]:
    """Split text into overlapping, token-bounded chunks on paragraph boundaries.

    Paragraphs are delimited by double newlines. A paragraph that alone exceeds
    max_tokens is hard-split at the token level so no chunk exceeds max_tokens.
    """
    paragraphs: list[str] = []
    for p in text.split("\n\n"):
        p = p.strip()
        if p:
            paragraphs.extend(_split_oversized(p, max_tokens))
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
