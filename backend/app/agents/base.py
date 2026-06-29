"""
Token tracking callback + base agent context.

Every agent call is wrapped with AgentTokenTracker which records:
  - tokens_in / tokens_out
  - cost_usd  (Anthropic claude-sonnet-4-6: $3/M in, $15/M out)
              (claude-haiku-4-5-20251001:   $0.25/M in, $1.25/M out)
              (DeepSeek deepseek-chat:       $0.27/M in, $1.10/M out)
              (DeepSeek deepseek-reasoner:   $0.55/M in, $2.19/M out)
  - duration_ms
  - provider  (anthropic | deepseek | local)
Then persists the record to MongoDB agent_runs collection.
"""

import time
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from app.database import get_db
from app.models.agent_run import AgentRunRecord

# Pricing per 1M tokens (USD) — update when provider changes rates
_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
    "deepseek-chat": (0.27, 1.10),       # DeepSeek V3
    "deepseek-reasoner": (0.55, 2.19),   # DeepSeek R1
}
_DEFAULT_PRICING = (0.0, 0.0)  # local/unknown models: no API cost


def _cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = _PRICING.get(model, _DEFAULT_PRICING)
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def _provider(model: str) -> str:
    """Derive provider tag from model name."""
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("deepseek"):
        return "deepseek"
    return "local"


class AgentTokenTracker(AsyncCallbackHandler):
    """LangChain async callback that records token usage and cost per LLM call.

    Attach as a callback to any LangChain LLM via get_llm(..., callbacks=[tracker]).
    Persists one AgentRunRecord to MongoDB agent_runs after each on_llm_end.
    Accumulates totals across multiple calls for summary() reporting.
    """

    def __init__(self, agent_name: str, run_id: str, model: str) -> None:
        """Initialise the tracker for a single agent invocation scope.

        Args:
            agent_name: Human-readable name logged to agent_runs (e.g. "quality_analyzer").
            run_id: Pipeline run UUID — links this record to posts / pipeline_runs.
            model: Exact model identifier string (e.g. "claude-haiku-4-5-20251001")
                used for cost lookup in _PRICING.
        """
        super().__init__()
        self.agent_name = agent_name
        self.run_id = run_id
        self.model = model
        self._start: float | None = None
        self._tokens_in = 0
        self._tokens_out = 0

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        """Record wall-clock start time when the LLM call begins.

        Args:
            serialized: LangChain-provided serialized LLM config (unused).
            prompts: List of prompt strings sent to the LLM (unused).
            **kwargs: Additional LangChain callback arguments (unused).
        """
        self._start = time.perf_counter()

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract token counts, compute cost, and persist to MongoDB.

        Reads input/output token counts from response.llm_output["usage"],
        supporting both Anthropic (input_tokens/output_tokens) and OpenAI
        (prompt_tokens/completion_tokens) field names. Inserts one document
        to db.agent_runs via AgentRunRecord.to_doc().

        Args:
            response: LangChain LLMResult containing llm_output usage metadata.
            **kwargs: Additional LangChain callback arguments (unused).
        """
        duration_ms = int((time.perf_counter() - (self._start or 0)) * 1000)

        usage: dict[str, int] = {}
        if response.llm_output:
            usage = response.llm_output.get("usage", {})

        tokens_in = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        tokens_out = usage.get("output_tokens") or usage.get("completion_tokens") or 0
        self._tokens_in += tokens_in
        self._tokens_out += tokens_out

        record = AgentRunRecord(
            run_id=self.run_id,
            agent_name=self.agent_name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=_cost(self.model, tokens_in, tokens_out),
            duration_ms=duration_ms,
            model=self.model,
            provider=_provider(self.model),
        )

        db = get_db()
        await db.agent_runs.insert_one(record.to_doc())

    def summary(self) -> dict[str, Any]:
        """Return accumulated token usage and cost for all calls in this scope.

        Returns:
            Dict with keys "agent" (str), "tokens_in" (int), "tokens_out" (int),
            and "cost_usd" (float rounded to 6 decimal places).
        """
        return {
            "agent": self.agent_name,
            "tokens_in": self._tokens_in,
            "tokens_out": self._tokens_out,
            "cost_usd": round(_cost(self.model, self._tokens_in, self._tokens_out), 6),
        }
