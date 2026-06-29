"""Topic refiner agent. Synthesizes raw topic + research + grounding context into a
structured editorial brief for the content generator.

Runs after research_node, before content_generation_node in the pipeline.
Uses supervisor model (Sonnet) — editorial judgment is the most critical bottleneck
in the pipeline. A weak brief produces a weak post regardless of generation quality.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.retry import with_langchain_retry
from app.prompt_loader import load_prompt, load_template


class TopicBrief(BaseModel):
    """Structured editorial brief produced by the TopicRefiner.

    Replaces the raw topic string as input to the content generator.
    Each field directly maps to a section of the generation prompt.
    """

    refined_angle: str = Field(
        description=(
            "The single specific argument this post will make. Not the topic — the TAKE. "
            "Must be falsifiable and non-obvious. "
            "Example: 'DeepSeek V3 wins on cost up to 8K tokens/call; above that, Claude caching closes the gap.'"
        )
    )
    hook_seed: str = Field(
        description=(
            "The exact first sentence of the post. Outcome-first pattern: "
            "'[specific outcome] when [specific action].' "
            "Must give a number, dollar figure, or named failure before word 15. "
            "Example: 'My bill dropped from $2,800 to $178 the month I stopped sending long contexts to DeepSeek.'"
        )
    )
    target_audience: str = Field(
        description=(
            "Specific reader profile: their role, their current assumption, and what will surprise them. "
            "Example: 'Backend engineers running LLM pipelines who assume cheapest model = best ROI always.'"
        )
    )
    h2_structure: list[str] = Field(
        min_length=4,
        max_length=6,
        description=(
            "4-6 H2 headings in post order. Each must be a curiosity trigger, not a label. "
            "Each heading implies a distinct sub-argument. "
            "Example: ['The Number That Made Me Switch', 'Where DeepSeek Breaks', 'The Caching Loophole', 'What I Still Use Claude For']"
        ),
    )
    key_claims: list[str] = Field(
        min_length=2,
        max_length=6,
        description=(
            "2-6 specific factual claims the fact_checker should find sources for. "
            "These are named product prices, published statistics, or company announcements — not personal experience. "
            "Example: ['DeepSeek V3 input pricing as of 2024', 'Claude Sonnet cache hit pricing vs standard']"
        ),
    )
    concession: str = Field(
        description=(
            "The one specific scenario where the alternative approach wins. "
            "Builds trust through honesty. Must name the exact threshold/context. "
            "Example: 'For document processing over 8K tokens per call, Claude prompt caching makes it competitive or cheaper.'"
        )
    )
    formatted_brief: str = Field(
        description=(
            "The complete brief as a single string for injection into the content generator prompt. "
            "Combines all fields into a structured paragraph the generator can follow directly. "
            "Should be 150-250 words. Starts with the angle, includes hook_seed, h2_structure, key_claims, concession."
        )
    )

    @field_validator("h2_structure", "key_claims", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                cleaned = (
                    v.replace("'", "'")
                    .replace("'", "'")
                    .replace(""", '"').replace(""", '"')
                    .replace("—", "-")
                    .replace("–", "-")
                    .replace("…", "...")
                )
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    return []
        return v


async def run_topic_refinement(
    run_id: str,
    topic: str,
    research_results: str,
    grounding_context: str = "",
    evidence_brief: str = "",
) -> TopicBrief:
    """Synthesizes raw topic, research data, and user grounding into a structured editorial brief.

    The Story (El Relato):
    In the story of our agent pipeline, this function is where raw, unpolished ideas are transformed
    into structured editorial blueprints. Often, a user will supply a generic topic. The topic refiner
    takes this raw topic, the evidence brief gathered from scanning a codebase, the web research findings,
    and user-provided grounding notes, and feeds them to our supervisor model (Claude Sonnet). The supervisor
    analyzes these materials to formulate a contrarian perspective, identify the reader persona, organize
    the section outline, list verifiable key claims, and write a specific concession to build author trust.

    The Flow (El Flujo):
    1. Initialize the token tracker and retrieve the supervisor model (Sonnet).
    2. Load system and human templates from prompts.
    3. Truncate web research results to fit context limits (4000 characters).
    4. Call the LLM with structured output mapping to the `TopicBrief` schema.
    5. Ensure the LLM returned a valid `TopicBrief` model, raising an error if it returned None.
    6. Return the finalized editorial blueprint.

    Args:
        run_id: Pipeline run identifier for cost tracking.
        topic: Raw topic string from the user (may be vague).
        research_results: Aggregated output from the web_researcher (Tavily results).
        grounding_context: Optional user-provided facts and context from the UI
            grounding brief. Empty string if not provided.
        evidence_brief: Optional repository evidence brief (as a formatted string).

    Returns:
        TopicBrief containing refined_angle, hook_seed, target_audience, h2_structure,
        key_claims, concession, and formatted_brief.

    Raises:
        ValueError: If the LLM returns None (structured output failure).
    """
    model_name = get_model_name("supervisor")
    tracker = AgentTokenTracker(
        agent_name="topic_refiner",
        run_id=run_id,
        model=model_name,
    )

    llm = with_langchain_retry(
        get_llm("supervisor", callbacks=[tracker]).with_structured_output(TopicBrief)
    )

    messages = [
        SystemMessage(content=load_prompt("topic_refiner_system")),
        HumanMessage(
            content=load_template("topic_refiner_human").format(
                topic=topic,
                research_results=(
                    research_results[:4000]
                    if research_results
                    else "No research available."
                ),
                evidence_brief=evidence_brief or "(no repository evidence)",
                grounding_context=grounding_context or "No grounding context provided.",
            )
        ),
    ]

    output: TopicBrief | None = await llm.ainvoke(messages)
    if output is None:
        raise ValueError("topic_refiner: LLM returned None — structured output failed")

    return output
