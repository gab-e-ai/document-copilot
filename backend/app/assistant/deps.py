from __future__ import annotations

from dataclasses import dataclass, field

from app.assistant.outputs import SourcePassage
from app.grounding.validator import GroundingValidator
from app.retrieval.retriever import DocumentRetriever


@dataclass
class DocumentAgentDeps:
    user_id: str
    thread_id: str
    retriever: DocumentRetriever
    grounding_validator: GroundingValidator
    retrieved_passages: list[SourcePassage] = field(default_factory=list)
