"""
SeriesPlannerAgent — decomposes a theme into a structured post series (Haiku, one call)

Input:  a high-level theme + optional context
Output: SeriesPlan with 3–5 PostPlan objects, each with a unique angle and hook seed

The planner runs once before the content generation loop. Each PostPlan.topic is
passed directly to run_pipeline() as the custom_topic.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.retry import with_langchain_retry
from app.prompt_loader import load_prompt, load_template


class PostPlan(BaseModel):
    position: int = Field(description="Publication order within the series (1-based)")
    topic: str = Field(description="Full topic string passed to the content generator")
    angle: str = Field(description="Unique perspective this post covers")
    hook_seed: str = Field(description="Opening scene, stat, or failure to anchor the hook")


class SeriesPlan(BaseModel):
    series_title: str = Field(description="Compelling collection title shown on Medium")
    series_description: str = Field(description="One sentence: what a reader gains from the full series")
    posts: list[PostPlan] = Field(description="3–5 post plans in publication order")

    @field_validator("posts", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            cleaned = (
                v.replace("‘", "'").replace("’", "'")
                .replace("“", '"').replace("”", '"')
                .replace("—", "-").replace("–", "-")
                .replace("…", "...")
            )
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return []


async def plan_series(
    run_id: str,
    theme: str,
    context: str = "",
) -> SeriesPlan:
    model_name = get_model_name("supervisor")
    tracker = AgentTokenTracker(
        agent_name="series_planner",
        run_id=run_id,
        model=model_name,
    )

    llm = with_langchain_retry(
        get_llm("supervisor", callbacks=[tracker]).with_structured_output(SeriesPlan)
    )

    messages = [
        SystemMessage(content=load_prompt("series_planner_system")),
        HumanMessage(
            content=load_template("series_planner_human").format(
                theme=theme,
                context=context or "No additional context provided.",
            )
        ),
    ]

    result: SeriesPlan = await llm.ainvoke(messages)
    return result
