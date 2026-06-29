"""Publication matcher agent. Suggests Medium publications to submit the post to.

Runs as a non-blocking post-finalize step. Suggestions are stored in the post
MongoDB document and displayed in the frontend sidebar. A failed match never
blocks or delays the pipeline.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.retry import retryable_llm_call
from app.prompt_loader import load_prompt, load_template

# Characters that LLMs frequently emit instead of their ASCII equivalents.
_UNICODE_REPLACEMENTS: list[tuple[str, str]] = [
    ("‘", "'"),   # ' LEFT SINGLE QUOTATION MARK
    ("’", "'"),   # ' RIGHT SINGLE QUOTATION MARK
    ("—", "-"),   # — EM DASH
    ("–", "-"),   # – EN DASH
    ("…", "..."), # … HORIZONTAL ELLIPSIS
]


def _normalize_unicode(text: str) -> str:
    """Replace curly single-quotes, em-dashes, and ellipsis with ASCII equivalents.

    Note: curly double-quotes (“/”) are intentionally NOT replaced here
    because they may appear as content inside JSON string values. They are handled
    by the JSON-aware escaping pass in _fix_unescaped_quotes().
    """
    for src, dst in _UNICODE_REPLACEMENTS:
        text = text.replace(src, dst)
    return text


def _fix_unescaped_quotes(s: str) -> str:
    """Escape unescaped double-quote characters that appear inside JSON string values.

    Uses a state machine to distinguish structural quotes (opening/closing a JSON
    string) from content quotes (embedded in the value text). A closing quote is
    identified by the next non-whitespace character being a JSON delimiter
    (, : } ]). Any other quote inside a string is escaped as \\".

    This repairs LLM output where the model emits bare ASCII " inside a string value
    instead of \\", which is otherwise valid JSON but breaks the parser.
    """
    result: list[str] = []
    i = 0
    in_string = False
    prev_backslash = False

    while i < len(s):
        c = s[i]
        if prev_backslash:
            result.append(c)
            prev_backslash = False
        elif c == "\\":
            result.append(c)
            prev_backslash = True
        elif c == '"':
            if in_string:
                # Peek past whitespace to determine whether this is a closing quote.
                j = i + 1
                while j < len(s) and s[j] in " \t\r\n":
                    j += 1
                next_is_delimiter = j < len(s) and s[j] in ",:}]"
                if next_is_delimiter:
                    result.append('"')
                    in_string = False
                else:
                    # Content quote inside a string value — escape it.
                    result.append('\\"')
            else:
                result.append('"')
                in_string = True
        else:
            result.append(c)
        i += 1

    return "".join(result)


class PublicationMatch(BaseModel):
    """A single Medium publication recommendation."""

    name: str = Field(description="Publication name, e.g. 'Towards Data Science'")
    slug: str = Field(description="URL slug, e.g. 'towardsdatascience'")
    fit_score: float = Field(ge=0.0, le=1.0, description="How well this post fits the publication's focus")
    submission_url: str = Field(description="How to submit: publication URL or submission form URL")
    why: str = Field(description="One sentence: why this post fits this publication's audience")
    audience_size: str = Field(
        description="Approximate follower count: 'small (<10K)', 'medium (10K-100K)', 'large (>100K)'"
    )

    @field_validator("name", "why", "audience_size", "slug", "submission_url", mode="before")
    @classmethod
    def _normalize_strings(cls, v: Any) -> Any:
        """Normalize unicode typography in string fields (em-dashes, curly single-quotes)."""
        if isinstance(v, str):
            return _normalize_unicode(v)
        return v


class PublicationMatchResult(BaseModel):
    """Top 3-5 publication recommendations for a post."""

    matches: list[PublicationMatch] = Field(
        min_length=1,
        max_length=5,
        description="1-5 publications ordered by fit_score descending"
    )
    top_pick: str = Field(description="Name of the single best-fit publication")
    strategy: str = Field(
        description=(
            "2-sentence submission strategy: which to try first and why, "
            "and what to do if rejected (self-publish vs. next publication)."
        )
    )

    @field_validator("matches", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        """Coerce a raw LLM JSON string to a list of PublicationMatch dicts.

        Three-pass strategy (never crashes the pipeline):
        1. Raw json.loads — handles well-formed JSON with Unicode content.
        2. Normalize non-structural unicode (em-dashes, single curly quotes), retry.
        3. Escape unescaped " chars that appear inside string values (state machine), retry.
        Falls back to empty list on any remaining JSONDecodeError.
        """
        if not isinstance(v, str):
            return v

        # Pass 1: try raw parse.
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            pass

        # Pass 2: normalize em-dashes and single curly quotes.
        step2 = _normalize_unicode(v)
        try:
            return json.loads(step2)
        except json.JSONDecodeError:
            pass

        # Pass 3: escape bare " inside JSON string values.
        step3 = _fix_unescaped_quotes(step2)
        try:
            return json.loads(step3)
        except json.JSONDecodeError:
            return []


async def run_publication_matching(
    run_id: str,
    title: str,
    tags: list[str],
    quality_score: float,
    medium_boost_eligible: bool,
    refined_angle: str = "",
) -> PublicationMatchResult:
    """Matches a post to Medium publications based on topic and quality signals.

    Args:
        run_id: Pipeline run identifier for cost tracking.
        title: Post title (used to infer subject area).
        tags: Post tags (primary signal for publication matching).
        quality_score: Quality gate score (0-1). Higher scores warrant larger publications.
        medium_boost_eligible: If True, prioritize publications known to forward Boost nominations.
        refined_angle: The post's central argument. Helps match to opinionated publications.

    Returns:
        PublicationMatchResult with ranked matches and submission strategy.

    Raises:
        ValueError: If the LLM returns None.
    """
    model_name = get_model_name("worker")
    tracker = AgentTokenTracker(
        agent_name="publication_matcher",
        run_id=run_id,
        model=model_name,
    )

    llm = get_llm("worker", callbacks=[tracker]).with_structured_output(PublicationMatchResult)

    messages = [
        SystemMessage(content=load_prompt("publication_matcher_system")),
        HumanMessage(
            content=load_template("publication_matcher_human").format(
                title=title,
                tags=", ".join(tags),
                quality_score=quality_score,
                boost_eligible="Yes" if medium_boost_eligible else "No",
                refined_angle=refined_angle or "Not specified.",
            )
        ),
    ]

    @retryable_llm_call(max_attempts=3)
    async def _invoke() -> PublicationMatchResult | None:
        return await llm.ainvoke(messages)  # type: ignore[return-value]

    output: PublicationMatchResult | None = await _invoke()
    if output is None:
        raise ValueError("publication_matcher: LLM returned None")

    return output
