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
