from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer, SourcePassage
from app.config import settings

_instructions = (Path(__file__).parent / "instructions.md").read_text()

document_agent: Agent[DocumentAgentDeps, GroundedAnswer] = Agent(
    model=OpenAIChatModel(
        settings.openai_chat_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
    ),
    deps_type=DocumentAgentDeps,
    output_type=GroundedAnswer,
    system_prompt=_instructions,
)


@document_agent.tool
async def search_filings(
    ctx: RunContext[DocumentAgentDeps],
    query: str,
) -> list[dict]:
    """Search the SEC filing corpus for passages relevant to `query`."""
    passages = await ctx.deps.retriever.retrieve(query)
    ctx.deps.retrieved_passages = passages
    return [p.model_dump() for p in passages]


async def run_agent(user_query: str, deps: DocumentAgentDeps) -> GroundedAnswer:
    result = await document_agent.run(user_query, deps=deps)
    return result.output
