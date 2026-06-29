"""
ContentGeneratorAgent — cheapest-first model strategy

revision_number 0 (initial):   Haiku  — cheap draft, good enough ~60% of the time
revision_number 1:              Haiku  — apply corrections, often sufficient
revision_number 2+ (last):      Sonnet — quality upgrade, only when Haiku fails twice

Cost comparison vs always-Sonnet:
  Best case  (Haiku initial passes):      ~$0.005/post  (was $0.05)
  Common     (one Haiku revision):        ~$0.012/post  (was $0.05)
  Worst case (Sonnet revision needed):    ~$0.035/post  (was $0.05)
"""

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.retry import with_langchain_retry
from app.config import settings
from app.prompt_loader import load_prompt, load_template


def enforce_paragraph_sentence_limit(
    content: str,
    max_sentences: int = 4,
) -> str:
    """Split prose paragraphs before structural checks can trigger revisions.

    This is intentionally mechanical: it only inserts blank lines between
    existing sentences. It does not rewrite words, headings, code blocks, image
    placeholders, or separators.
    """
    if max_sentences < 1:
        raise ValueError("max_sentences must be at least 1")

    parts = re.split(r"(\n\s*\n)", content)
    fixed: list[str] = []
    for part in parts:
        if not part or re.fullmatch(r"\n\s*\n", part):
            fixed.append(part)
            continue

        paragraph = part.strip()
        if _should_skip_paragraph_split(paragraph):
            fixed.append(part)
            continue

        split_paragraph = _split_paragraph_by_sentence_limit(
            paragraph,
            max_sentences=max_sentences,
        )
        fixed.append(
            split_paragraph
            if part == paragraph
            else part.replace(paragraph, split_paragraph)
        )

    return "".join(fixed)


def _should_skip_paragraph_split(paragraph: str) -> bool:
    lines = paragraph.splitlines()
    return (
        paragraph.startswith("#")
        or re.fullmatch(r"-{3,}", paragraph) is not None
        or paragraph.startswith("```")
        or "```" in paragraph
        or re.match(r"^\[IMAGE:", paragraph, re.IGNORECASE) is not None
        or any(line.lstrip().startswith("|") for line in lines)
        or any(re.match(r"^\s*(-|\*|\d+\.)\s+", line) for line in lines)
    )


def _split_paragraph_by_sentence_limit(
    paragraph: str,
    max_sentences: int,
) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraph) if s.strip()]
    if _count_full_sentences(sentences) <= max_sentences:
        return paragraph

    chunks: list[list[str]] = []
    current: list[str] = []
    current_count = 0
    for sentence in sentences:
        sentence_count = 1 if len(sentence.split()) >= 3 else 0
        if current and current_count + sentence_count > max_sentences:
            chunks.append(current)
            current = []
            current_count = 0
        current.append(sentence)
        current_count += sentence_count

    if current:
        chunks.append(current)

    return "\n\n".join(" ".join(chunk) for chunk in chunks)


def _count_full_sentences(sentences: list[str]) -> int:
    return sum(1 for sentence in sentences if len(sentence.split()) >= 3)


class GeneratedPost(BaseModel):
    title: str = Field(description="Compelling title, 6-12 words, no clickbait")
    subtitle: str = Field(description="One-sentence hook under the title")
    content: str = Field(
        description=(
            "Full Medium post in Markdown. "
            "1,700–1,900 words. TARGET 1,700 minimum — do not submit under 1,500. "
            "No H1 (title is separate). "
            "Image placeholders as: [IMAGE: description | alt: 10-15 word alt text]"
        )
    )
    tags: list[str] = Field(description="Exactly 5 Medium tags, lowercase")
    image_suggestions: list[str] = Field(
        description="3 image ideas with suggested search terms for Unsplash/Pexels"
    )

    @field_validator("tags", "image_suggestions", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            cleaned = (
                v.replace("‘", "'")
                .replace("’", "'")  # ' '
                .replace("“", '"')
                .replace("”", '"')  # " "
                .replace("—", "-")
                .replace("–", "-")  # — –
                .replace("…", "...")  # …
            )
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return []


def _pick_role(
    revision_number: int,
    score: float | None = None,
    min_score: float = 0.70,
    has_high_ai_pattern: bool = False,
) -> str:
    """Selects the LLM role for revision based on cycle number and score proximity.

    Escalates to supervisor (Sonnet) early when the post is close to passing
    (within 0.06 of min_score) or has a HIGH ai_pattern issue (which requires
    stronger rewriting ability than Haiku provides reliably).

    For Anthropic: use supervisor (Sonnet) when score is within 0.06 of min_score,
    or always on revision 2+, or when HIGH ai_pattern issues are present.

    For DeepSeek/local LLM: always use 'worker' regardless.

    Args:
        revision_number: Current revision cycle (0-indexed from caller).
        score: Current quality score, or None if unknown.
        min_score: Minimum passing score threshold from config.
        has_high_ai_pattern: True if the quality report has a HIGH severity
            ai_pattern issue.

    Returns:
        "supervisor" for Sonnet (strong model) or "worker" for Haiku (fast/cheap).
    """
    if settings.use_deepseek or settings.use_local_llm:
        return "worker"

    if revision_number >= 2:
        return "supervisor"
    if has_high_ai_pattern:
        return "supervisor"
    if score is not None and score >= min_score - 0.06:
        return "supervisor"
    return "worker"


async def generate_initial_post(
    run_id: str,
    topic: str,
    trend_context: str,
    tags: list[str],
    audience: str,
    exemplar_section: str = "",
    series_context: str = "",
) -> GeneratedPost:
    """Generate initial post from topic and context.

    The Story (El Relato):
    In the story of our content pipeline, this function is the First Draft Writer.
    It takes the refined topic angle and the target audience provided by the Chief Editor,
    along with web research and repository evidence. It also looks at the selected few-shot exemplar
    (representing past successful content) to establish the correct stylistic tone.
    It then invokes the LLM writer (defaulting to Haiku for budget-conscious efficiency) to draft
    the article, returning a complete `GeneratedPost` structure containing a title, subtitle,
    content, lowercase tags, and visual suggestions.

    The Flow (El Flujo):
    1. Select the appropriate LLM model (Haiku is chosen for initial drafts).
    2. Check if a series context is present and format it.
    3. Load system and human templates from prompt files.
    4. Call the generator LLM with structured output mapping to the `GeneratedPost` schema.
    5. Apply sentence-length formatting to split long paragraphs in the draft content.
    6. Return the structured `GeneratedPost` object.

    Args:
        run_id: Unique run identifier.
        topic: Post topic to write about.
        trend_context: Current trend info and timing context.
        tags: List of Medium tags to apply.
        audience: Target audience description.
        exemplar_section: Optional few-shot exemplar blueprint for injection.
        series_context: Optional series position context for multi-part series.

    Returns:
        GeneratedPost with title, subtitle, content, tags, and image suggestions.
    """
    role = _pick_role(revision_number=0, score=None)
    series_block = (
        "SERIES CONTEXT (position this post correctly within the series):\n"
        f"{series_context}\n"
        if series_context
        else ""
    )
    return await _call_generator(
        run_id=run_id,
        agent_label="content_generator_initial",
        role=role,
        messages=[
            SystemMessage(content=load_prompt("content_generator_system")),
            HumanMessage(
                content=load_template("content_generator_human_initial").format(
                    topic=topic,
                    trend_context=trend_context,
                    tags=", ".join(tags),
                    audience=audience,
                    exemplar_section=exemplar_section,
                    series_context=series_block,
                )
            ),
        ],
    )


async def revise_post(
    run_id: str,
    title: str,
    content: str,
    score: float,
    revision_prompt: str,
    issues: list[dict[str, Any]],
    strengths: list[str] | None = None,
    gate_failures: list[str] | None = None,
    read_ratio_breakdown: str | None = None,
    revision_number: int = 1,
    prior_cycle_summary: str = "",
) -> GeneratedPost:
    """Revise post based on quality feedback.

    The Story (El Relato):
    In the story of our content pipeline, this function is the Detail-Oriented Proofreader.
    If the initial post fails the quality checks, it is sent here to fix specific issues.
    This function analyzes the quality report feedback, including structural issues, fact-checking failures,
    and style warnings. It checks the number of revision attempts: if the article failed multiple times,
    or has complex stylistic errors (like severe AI-like vocabulary patterns), it escalates the task from
    Haiku to our more capable supervisor model (Claude Sonnet) to perform high-precision rewrites.

    The Flow (El Flujo):
    1. Check for high-severity AI vocabulary patterns or if revision cycle is >= 2.
    2. Invoke `_pick_role` to select between worker (Haiku) or supervisor (Sonnet) models.
    3. Measure the word count and introductory paragraph length.
    4. Compile the lists of issues, strengths, gate failures, and read ratio predictions.
    5. Load revision system and human instructions.
    6. Invoke the LLM with structured feedback to generate a clean, corrected draft.
    7. Format sentence splits and return the revised `GeneratedPost`.

    Args:
        run_id: Unique run identifier.
        title: Current post title.
        content: Current post markdown.
        score: Quality score from analyzer (0.0-1.0).
        revision_prompt: Specific LLM rewrite instructions.
        issues: List of QualityIssue dicts (severity, category, location, suggestion).
        strengths: List of phrases to preserve (optional).
        gate_failures: Hard gate failures preventing publication (optional).
        read_ratio_breakdown: Detailed read ratio analysis (optional).
        revision_number: Iteration count (1 = first revision, etc.).
        prior_cycle_summary: Summary of changes from prior iteration (optional).

    Returns:
        GeneratedPost with revised content.
    """
    has_high_ai_pattern = any(
        i.get("severity") == "HIGH" and i.get("category") == "ai_pattern"
        for i in (issues or [])
    )
    role = _pick_role(
        revision_number=revision_number,
        score=score,
        min_score=settings.min_quality_score,
        has_high_ai_pattern=has_high_ai_pattern,
    )
    word_count = len(content.split())

    # Compute intro word count so the reviser sees it as a number before STEP 0
    intro_text = (
        content.split("---")[0].split("## ")[0]
        if ("---" in content or "## " in content)
        else content[:500]
    )
    intro_word_count = len(intro_text.split())

    issues_list = "\n".join(
        f"- [{i['severity'].upper()}] {i['category']}: {i['suggestion']}"
        + (f"\n  LOCATION: {i['location']}" if i.get("location") else "")
        for i in issues
    )
    strengths_list = (
        "\n".join(f"• {s}" for s in strengths)
        if strengths
        else "  (no specific strengths identified)"
    )
    gate_failures_list = (
        "\n".join(f"✗ {f}" for f in gate_failures)
        if gate_failures
        else "  (no hard gate failures — score improvement only)"
    )
    read_ratio_section = (
        read_ratio_breakdown
        if read_ratio_breakdown
        else "  (no read ratio breakdown available)"
    )

    return await _call_generator(
        run_id=run_id,
        agent_label=f"content_generator_revision_{revision_number}",
        role=role,
        messages=[
            SystemMessage(content=load_prompt("content_reviser_system")),
            HumanMessage(
                content=load_template("content_generator_human_revision").format(
                    title=title,
                    content=content,
                    word_count=word_count,
                    score=round(score, 2),
                    min_score=settings.min_quality_score,
                    revision_prompt=revision_prompt,
                    issues_list=issues_list,
                    strengths_list=strengths_list,
                    gate_failures_list=gate_failures_list,
                    read_ratio_section=read_ratio_section,
                    prior_cycle_summary=prior_cycle_summary,
                    intro_word_count=intro_word_count,
                )
            ),
        ],
    )


async def expand_post(
    run_id: str,
    title: str,
    content: str,
    deficit: int,
) -> str:
    """
    Generate ONE new H2 section (~deficit words) to append to a post that
    cleared all quality gates but is short of the minimum word count.
    Returns only the new section text; the caller appends it to post.content.
    Uses creation mode (not revision mode) so the LLM adds, never edits.
    """
    role = "worker"
    model_name = get_model_name(role)
    tracker = AgentTokenTracker(
        agent_name="content_generator_expand",
        run_id=run_id,
        model=model_name,
    )

    llm = with_langchain_retry(get_llm(role, max_tokens=1024, callbacks=[tracker]))

    messages: list[Any] = [
        SystemMessage(
            content=(
                "You are a technical writer adding one new section to an existing "
                "Medium post. "
                "Output ONLY the new section — nothing else, no preamble, no "
                "sign-off. "
                "Start with a Markdown H2 heading (## Section Title). "
                "Every sentence must contain a specific fact, number, named tool, "
                "or concrete example. "
                "Do not summarize, repeat, or conclude — add new information only."
            )
        ),
        HumanMessage(
            content=(
                f"Post title: {title}\n\n"
                f"Existing content:\n{content}\n\n"
                f"---\n"
                f"The post needs approximately {deficit} more words. "
                f"Write ONE new H2 section (~{deficit} words) covering the most "
                "obvious follow-up "
                "topic a reader would ask about after reading the existing content. "
                "Use specific numbers, tool names, and real examples — no vague "
                "generalizations. "
                "Output the new section only, starting with ##"
            )
        ),
    ]

    result = await llm.ainvoke(messages)
    content = result.content if hasattr(result, "content") else str(result)
    return enforce_paragraph_sentence_limit(content)


async def _call_generator(
    run_id: str,
    agent_label: str,
    role: str,
    messages: list[Any],
) -> GeneratedPost:
    """Call LLM with structured output for post generation/revision.

    Args:
        run_id: Unique run identifier for token tracking.
        agent_label: Agent name for logging (e.g., 'content_generator_initial').
        role: LLM role ('worker' or 'supervisor').
        messages: LangChain message list (SystemMessage, HumanMessage, etc).

    Returns:
        GeneratedPost with structured fields.
    """
    model_name = get_model_name(role)
    tracker = AgentTokenTracker(
        agent_name=agent_label,
        run_id=run_id,
        model=model_name,
    )

    llm = with_langchain_retry(
        get_llm(role, max_tokens=4096, callbacks=[tracker]).with_structured_output(
            GeneratedPost
        )
    )

    result: GeneratedPost = await llm.ainvoke(messages)
    result.content = enforce_paragraph_sentence_limit(result.content)
    return result
