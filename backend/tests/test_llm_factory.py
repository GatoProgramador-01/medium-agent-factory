"""
Unit tests for llm_factory — model name selection and provider switching.
No LLM calls are made; the factory function itself is under test.
"""

from unittest.mock import patch

from app.agents.llm_factory import get_model_name


class TestGetModelName:
    def test_worker_role_returns_worker_model(self) -> None:
        with patch("app.agents.llm_factory.settings") as s:
            s.use_local_llm = False
            s.worker_model = "claude-haiku-4-5-20251001"
            s.supervisor_model = "claude-sonnet-4-6"
            assert get_model_name("worker") == "claude-haiku-4-5-20251001"

    def test_supervisor_role_returns_supervisor_model(self) -> None:
        with patch("app.agents.llm_factory.settings") as s:
            s.use_local_llm = False
            s.worker_model = "claude-haiku-4-5-20251001"
            s.supervisor_model = "claude-sonnet-4-6"
            assert get_model_name("supervisor") == "claude-sonnet-4-6"

    def test_default_role_is_worker(self) -> None:
        with patch("app.agents.llm_factory.settings") as s:
            s.use_local_llm = False
            s.worker_model = "claude-haiku-4-5-20251001"
            s.supervisor_model = "claude-sonnet-4-6"
            assert get_model_name() == "claude-haiku-4-5-20251001"

    def test_local_llm_always_returns_local_model(self) -> None:
        with patch("app.agents.llm_factory.settings") as s:
            s.use_local_llm = True
            s.local_llm_model = "llama3.2"
            # Role is irrelevant when using local LLM
            assert get_model_name("worker") == "llama3.2"
            assert get_model_name("supervisor") == "llama3.2"

    def test_local_llm_overrides_anthropic_models(self) -> None:
        with patch("app.agents.llm_factory.settings") as s:
            s.use_local_llm = True
            s.local_llm_model = "mistral"
            s.worker_model = "claude-haiku-4-5-20251001"
            s.supervisor_model = "claude-sonnet-4-6"
            assert get_model_name("supervisor") == "mistral"
