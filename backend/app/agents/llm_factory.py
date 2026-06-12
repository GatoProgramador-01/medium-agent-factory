"""
LLM factory — single entry point for all agent LLM instantiation.

Usage:
    from app.agents.llm_factory import get_llm, get_model_name

    model_name = get_model_name("worker")
    tracker    = AgentTokenTracker(agent_name="...", run_id=run_id, model=model_name)
    llm        = get_llm("worker", callbacks=[tracker]).with_structured_output(MyModel)

Switch between Anthropic and local Ollama with a single env var:
    USE_LOCAL_LLM=false  →  ChatAnthropic (supervisor_model / worker_model from config)
    USE_LOCAL_LLM=true   →  ChatOllama    (local_llm_model at local_llm_base_url)
"""

from langchain_core.language_models import BaseChatModel

from app.config import settings


def get_model_name(role: str = "worker") -> str:
    """Return the effective model identifier string for the given role."""
    if settings.use_local_llm:
        return settings.local_llm_model
    return settings.supervisor_model if role == "supervisor" else settings.worker_model


def get_llm(role: str = "worker", **kwargs: object) -> BaseChatModel:
    """
    Instantiate the correct LLM for the given role.

    role: "supervisor" | "worker"
      supervisor → more capable model (Sonnet / same local model)
      worker     → cheaper model (Haiku / same local model)

    Extra kwargs are forwarded to the LLM constructor (e.g. max_tokens, callbacks).
    """
    if settings.use_local_llm:
        from langchain_ollama import ChatOllama  # optional dep — only imported when needed
        return ChatOllama(
            model=settings.local_llm_model,
            base_url=settings.local_llm_base_url,
            **kwargs,
        )

    from langchain_anthropic import ChatAnthropic
    model = settings.supervisor_model if role == "supervisor" else settings.worker_model
    return ChatAnthropic(
        model=model,
        api_key=settings.anthropic_api_key,
        **kwargs,
    )
