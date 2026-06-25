from __future__ import annotations

from app.assistant.outputs import GroundedAnswer, SourcePassage


class GroundingError(Exception):
    pass


class GroundingValidator:
    def validate(
        self,
        answer: GroundedAnswer,
        retrieved: list[SourcePassage],
    ) -> GroundedAnswer:
        """Raise GroundingError if any citation references a chunk not in retrieved."""
        retrieved_ids = {p.chunk_id for p in retrieved}
        for citation in answer.citations:
            if citation.chunk_id not in retrieved_ids:
                raise GroundingError(
                    f"Citation chunk_id {citation.chunk_id!r} was not retrieved "
                    "for this request — the model cited a hallucinated source"
                )
        return answer
