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

        # DeepSeek V3 compatibility notes:
        # - json_schema (OpenAI strict structured outputs) → not supported, returns 400
        # - function_calling → tool_choice is forced, but DeepSeek ignores it for complex
        #   nested schemas (~5+ fields) and returns plain text → LangChain parses as None
        # - json_mode → reliable for all schemas; BUT LangChain does NOT inject the field
        #   schema into the prompt (only sets response_format). We must inject it ourselves
        #   or DeepSeek wraps the whole output under a single generic key like {"post":"..."}.
        class _DeepSeekChatOpenAI(ChatOpenAI):  # type: ignore[misc]
            def with_structured_output(  # type: ignore[override]
                self, schema: Any, *, method: str = "json_mode", **kw: Any
            ) -> Any:
                import json as _json

                inner = super().with_structured_output(schema, method=method, **kw)

                # Build the schema instruction once at chain-construction time.
                try:
                    schema_str = _json.dumps(schema.model_json_schema(), indent=2)
                    schema_block = (
                        "Respond ONLY with a valid JSON object that matches this schema "
                        "exactly — no extra keys, no wrapper object:\n"
                        f"```json\n{schema_str}\n```"
                    )
                except Exception:
                    schema_block = "Respond with valid JSON."

                def _inject_schema(messages: Any) -> Any:
                    # Append schema instructions to the first SystemMessage so DeepSeek
                    # knows the exact field names. Without this json_mode returns a generic
                    # wrapper like {"post": "..."} instead of the structured fields.
                    if not isinstance(messages, list):
                        return messages
                    for i, m in enumerate(messages):
                        if isinstance(m, SystemMessage):
                            patched = SystemMessage(
                                content=m.content + "\n\n" + schema_block
                            )
                            return messages[:i] + [patched] + messages[i + 1 :]
                    return [SystemMessage(content=schema_block)] + messages

                def _guard(output: Any) -> Any:
                    if output is None:
                        raise OutputParserException(
                            "DeepSeek json_mode returned None — will retry"
                        )
                    return output

                return RunnableLambda(_inject_schema) | inner | RunnableLambda(_guard)

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
