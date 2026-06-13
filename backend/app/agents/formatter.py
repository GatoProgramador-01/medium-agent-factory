"""
FormatterAgent — structural post formatter (Haiku, one pass, no revision loop)

Runs after quality analysis passes, before finalize. Applies mechanical fixes only:
  1. Split paragraphs > 4 sentences at natural break points (no word changes)
  2. Add --- separator between intro and first ## heading if missing
  3. Standardize [IMAGE: desc | alt: text] format
  4. Extract pull quote (best single line, copied verbatim from content)

Cost: ~$0.002/post (Haiku). Never triggers a revision cycle.
"""

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.retry import with_langchain_retry
from app.prompt_loader import load_prompt, load_template


class FormattedPost(BaseModel):
    formatted_content: str = Field(
        description="Full post with structural fixes applied. Every word is identical to input."
    )
    pull_quote: str = Field(
        description="Single most quotable sentence, copied exactly from the content. No paraphrasing."
    )
    changes_applied: list[str] = Field(
        description="List of structural changes made, e.g. 'Split paragraph starting with X after sentence 3'"
    )

    @field_validator("changes_applied", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            cleaned = (
                v.replace("‘", "'")
                .replace("’", "'")
                .replace("“", '"')
                .replace("”", '"')
                .replace("—", "-")
                .replace("–", "-")
                .replace("…", "...")
            )
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return []


def detect_long_paragraphs(content: str, max_sentences: int = 4) -> list[str]:
    """Return paragraphs that exceed max_sentences. Pure function, no LLM."""
    long: list[str] = []
    for paragraph in content.split("\n\n"):
        p = paragraph.strip()
        if not p or p.startswith("#") or p.startswith("[IMAGE") or p.startswith("---"):
            continue
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", p) if s.strip()]
        if len(sentences) > max_sentences:
            long.append(p)
    return long


async def format_post(run_id: str, title: str, content: str) -> FormattedPost:
    long_paragraphs = detect_long_paragraphs(content)
    long_paragraphs_text = (
        "\n\n---\n\n".join(long_paragraphs)
        if long_paragraphs
        else "None — only apply separator and image format fixes if needed."
    )

    model_name = get_model_name("worker")
    tracker = AgentTokenTracker(
        agent_name="formatter",
        run_id=run_id,
        model=model_name,
    )

    llm = with_langchain_retry(
        get_llm("worker", max_tokens=4096, callbacks=[tracker]).with_structured_output(
            FormattedPost
        )
    )

    messages = [
        SystemMessage(content=load_prompt("formatter_system")),
        HumanMessage(
            content=load_template("formatter_human").format(
                title=title,
                content=content,
                long_paragraphs=long_paragraphs_text,
            )
        ),
    ]

    result: FormattedPost = await llm.ainvoke(messages)
    return result
