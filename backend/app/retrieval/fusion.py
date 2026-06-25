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
