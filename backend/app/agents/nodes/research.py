from typing import Any, Dict
from app.agents.logger import log_step
from app.agents.web_researcher import research_topic

async def research_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Performs web research for the post topic using Tavily search.

    The Story (El Relato):
    In the story of our publishing pipeline, this node acts as the Investigative Reporter.
    Before writing a single word about a topic, the pipeline needs fresh, grounded data
    from the web to avoid outdated assumptions or shallow generalizations. This node
    reaches out to search APIs to gather facts, trend signals, and URL references. By doing
    so, it feeds the content writer with real-world evidence, ensuring the resulting post
    is both informative and authoritative.

    The Flow (El Flujo):
    1. Log the initiation of the research step for the given custom topic.
    2. Invoke the web research agent (`research_topic`) to query the web via Tavily.
    3. Aggregate retrieved URLs, metrics, and observations into a structured trend context.
    4. Log the completion (with the number of data points found) or warning if no results.
    5. Return the trend context to the pipeline state.

    Args:
        state: Pipeline state containing "custom_topic" and "run_id".

    Returns:
        Dict with "trend_context" key containing aggregated Tavily output, and
        "completed_steps" log entry. Empty trend_context on error.
    """
    run_id = state["run_id"]
    topic = state["custom_topic"]

    await log_step(
        run_id,
        "web_researcher",
        f'Searching web for grounded data on: "{topic}"...',
        data={"topic": topic},
    )
    try:
        trend_context = await research_topic(run_id=run_id, topic=topic)
        if trend_context:
            fact_count = trend_context.count("•")
            await log_step(
                run_id,
                "web_researcher",
                f"Research complete — {fact_count} data points ready for the writer",
                level="success",
                data={"preview": trend_context[:300]},
            )
        else:
            await log_step(
                run_id,
                "web_researcher",
                "No web context available (Tavily key missing or no results) — continuing",
                level="warning",
            )
        return {"trend_context": trend_context, "completed_steps": ["research"]}
    except Exception as e:
        await log_step(
            run_id, "web_researcher", f"Research skipped: {e}", level="warning"
        )
        return {"trend_context": "", "completed_steps": ["research"]}
