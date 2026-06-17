"""
LLM retry utilities — two patterns, one choice per situation.

Pattern A — LangChain-native  (use this by default)
  chain.with_retry(...)  works on any Runnable, including
  .with_structured_output() chains.
  Retries appear in LangSmith traces automatically.
  Import: with_langchain_retry(chain)

Pattern B — tenacity decorator  (use when wrapping a whole async function)
  More control: per-exception logic, custom before_sleep hooks.
  Import: @retryable_llm_call(max_attempts=3)

Retryable errors (transient — server/network side):
  - RateLimitError (429) — Anthropic rate limit, wait and retry
  - APIConnectionError — network blip, retry immediately
  - InternalServerError (500/529) — Anthropic overloaded, backoff
  - ConnectionError / TimeoutError — infrastructure noise

Non-retryable (our fault — never retry):
  - AuthenticationError (401) — bad key, no point retrying
  - InvalidRequestError (400) — malformed request
  - OutputParserException — structured output failed after retries
"""

import logging
from collections.abc import Callable
from typing import Any

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

logger = logging.getLogger(__name__)

# Build the retryable exception tuple at import time.
# anthropic exceptions are optional — not imported if USE_LOCAL_LLM=true.
# OutputParserException covers DeepSeek skipping a tool call (returns None → guard raises).
from langchain_core.exceptions import OutputParserException

_RETRYABLE: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
    OutputParserException,
)

try:
    from anthropic import APIConnectionError, InternalServerError, RateLimitError

    _RETRYABLE = _RETRYABLE + (RateLimitError, APIConnectionError, InternalServerError)
except ImportError:
    pass

try:
    # ollama connection errors when local model is unavailable
    from httpx import ConnectError, RemoteProtocolError

    _RETRYABLE = _RETRYABLE + (ConnectError, RemoteProtocolError)
except ImportError:
    pass


# ── Pattern A: LangChain-native ────────────────────────────────────────────────


def with_langchain_retry(chain: Any, max_attempts: int = 3) -> Any:
    """
    Wrap any LangChain Runnable with built-in retry.

    Preferred over the tenacity decorator because:
    - Retries are visible in LangSmith traces
    - Works seamlessly after .with_structured_output()
    - No extra function wrapper needed

    Usage:
        chain = get_llm("worker").with_structured_output(MyModel)
        result = await with_langchain_retry(chain).ainvoke(messages)
    """
    return chain.with_retry(
        retry_if_exception_type=_RETRYABLE,
        wait_exponential_jitter=True,
        stop_after_attempt=max_attempts,
    )


# ── Pattern B: tenacity decorator ─────────────────────────────────────────────


def retryable_llm_call(max_attempts: int = 3) -> Callable[..., Any]:
    """
    Tenacity decorator for async functions that call an LLM.

    Use when wrapping a whole function rather than a single Runnable,
    or when you need the before_sleep log for debugging.

    Usage:
        @retryable_llm_call(max_attempts=3)
        async def call_llm() -> MyModel:
            return await chain.ainvoke(messages)

        result = await call_llm()
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=30) + wait_random(0, 2),
        retry=retry_if_exception_type(_RETRYABLE),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
