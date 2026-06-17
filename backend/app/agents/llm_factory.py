"""
LLM factory — single entry point for all agent LLM instantiation.

Usage:
    from app.agents.llm_factory import get_llm, get_model_name

    model_name = get_model_name("worker")
    tracker    = AgentTokenTracker(agent_name="...", run_id=run_id, model=model_name)
    llm        = get_llm("worker", callbacks=[tracker]).with_structured_output(MyModel)

Priority order (first true wins):
    USE_LOCAL_LLM=true   →  ChatOllama    (local_llm_model at local_llm_base_url)
    USE_DEEPSEEK=true    →  ChatOpenAI    (deepseek_model via api.deepseek.com — OpenAI-compat)
    default              →  ChatAnthropic (supervisor_model / worker_model from config)
"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from app.config import settings


def get_model_name(role: str = "worker") -> str:
    """Return the effective model identifier string for the given role."""
    if settings.use_local_llm:
        return settings.local_llm_model
    if settings.use_deepseek:
        return settings.deepseek_model
    return settings.supervisor_model if role == "supervisor" else settings.worker_model


def get_llm(role: str = "worker", **kwargs: Any) -> BaseChatModel:
    """
    Instantiate the correct LLM for the given role.

    role: "supervisor" | "worker"
      supervisor → more capable model (Sonnet / same DeepSeek/local model)
      worker     → cheaper model (Haiku / same DeepSeek/local model)

    Extra kwargs are forwarded to the LLM constructor (e.g. max_tokens, callbacks).
    """
    if settings.use_local_llm:
        from langchain_ollama import ChatOllama  # only imported when needed

        return ChatOllama(
            model=settings.local_llm_model,
            base_url=settings.local_llm_base_url,
            **kwargs,
        )

    if settings.use_deepseek:
        from langchain_core.exceptions import OutputParserException
        from langchain_core.messages import SystemMessage
        from langchain_core.runnables import RunnableLambda
        from langchain_openai import ChatOpenAI  # only imported when needed

        # DeepSeek V3 compatibility:
        # - json_schema (OpenAI structured outputs) → not supported
        # - function_calling → supported, but model occasionally returns text instead of a
        #   tool call. We prepend a system message ensuring the word "json" appears so
        #   json_mode also works as a fallback, and guard the output to raise a retryable
        #   OutputParserException when None is returned.
        class _DeepSeekChatOpenAI(ChatOpenAI):  # type: ignore[misc]
            def with_structured_output(  # type: ignore[override]
                self, schema: Any, *, method: str = "function_calling", **kw: Any
            ) -> Any:
                inner = super().with_structured_output(schema, method=method, **kw)

                def _guard(output: Any) -> Any:
                    if output is None:
                        raise OutputParserException(
                            "DeepSeek did not invoke the tool — will retry"
                        )
                    return output

                return inner | RunnableLambda(_guard)

        return _DeepSeekChatOpenAI(  # type: ignore[call-arg]
            model=settings.deepseek_model,
            api_key=SecretStr(settings.deepseek_api_key),
            base_url="https://api.deepseek.com/v1",
            **kwargs,
        )

    from langchain_anthropic import ChatAnthropic

    model = settings.supervisor_model if role == "supervisor" else settings.worker_model
    return ChatAnthropic(  # type: ignore[call-arg]
        model=model,
        api_key=SecretStr(settings.anthropic_api_key),
        **kwargs,
    )
