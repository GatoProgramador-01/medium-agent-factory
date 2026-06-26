"""Unit tests for provider detection, DeepSeek pricing, AgentRunRecord.provider,
and savings calculation logic.

All tests are pure unit tests — no DB, no asyncio required.
"""

import pytest

from app.agents.base import _cost, _provider
from app.models.agent_run import AgentRunRecord
from app.routers.analytics import _compute_savings


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------


class TestProviderDetection:
    def test_claude_sonnet_is_anthropic(self) -> None:
        assert _provider("claude-sonnet-4-6") == "anthropic"

    def test_claude_haiku_is_anthropic(self) -> None:
        assert _provider("claude-haiku-4-5-20251001") == "anthropic"

    def test_deepseek_chat_is_deepseek(self) -> None:
        assert _provider("deepseek-chat") == "deepseek"

    def test_deepseek_reasoner_is_deepseek(self) -> None:
        assert _provider("deepseek-reasoner") == "deepseek"

    def test_unknown_model_is_local(self) -> None:
        assert _provider("llama3") == "local"

    def test_empty_string_is_local(self) -> None:
        assert _provider("") == "local"


# ---------------------------------------------------------------------------
# DeepSeek pricing
# ---------------------------------------------------------------------------


class TestDeepSeekPricing:
    def test_deepseek_chat_input_price(self) -> None:
        # $0.27 per 1M input tokens
        result = _cost("deepseek-chat", 1_000_000, 0)
        assert result == pytest.approx(0.27)

    def test_deepseek_chat_output_price(self) -> None:
        # $1.10 per 1M output tokens
        result = _cost("deepseek-chat", 0, 1_000_000)
        assert result == pytest.approx(1.10)

    def test_deepseek_reasoner_input_price(self) -> None:
        # $0.55 per 1M input tokens
        result = _cost("deepseek-reasoner", 1_000_000, 0)
        assert result == pytest.approx(0.55)

    def test_deepseek_reasoner_output_price(self) -> None:
        # $2.19 per 1M output tokens
        result = _cost("deepseek-reasoner", 0, 1_000_000)
        assert result == pytest.approx(2.19)

    def test_deepseek_chat_combined_cost(self) -> None:
        # 500K in + 500K out = (0.27 + 1.10) / 2 = 0.685
        result = _cost("deepseek-chat", 500_000, 500_000)
        assert result == pytest.approx(0.685)


# ---------------------------------------------------------------------------
# AgentRunRecord with provider field
# ---------------------------------------------------------------------------


class TestAgentRunRecordProvider:
    def _make_record(self, provider: str = "") -> AgentRunRecord:
        return AgentRunRecord(
            run_id="run-001",
            agent_name="writer",
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.001,
            duration_ms=200,
            model="claude-sonnet-4-6",
            provider=provider,
        )

    def test_to_doc_includes_provider_key(self) -> None:
        doc = self._make_record().to_doc()
        assert "provider" in doc

    def test_to_doc_provider_default_empty_string(self) -> None:
        doc = self._make_record().to_doc()
        assert doc["provider"] == ""

    def test_to_doc_provider_anthropic(self) -> None:
        doc = self._make_record(provider="anthropic").to_doc()
        assert doc["provider"] == "anthropic"

    def test_to_doc_provider_deepseek(self) -> None:
        doc = self._make_record(provider="deepseek").to_doc()
        assert doc["provider"] == "deepseek"

    def test_to_doc_provider_local(self) -> None:
        doc = self._make_record(provider="local").to_doc()
        assert doc["provider"] == "local"

    def test_to_doc_still_includes_all_original_keys(self) -> None:
        doc = self._make_record(provider="anthropic").to_doc()
        required = {
            "run_id", "agent_name", "tokens_in", "tokens_out",
            "cost_usd", "duration_ms", "model", "provider", "created_at",
        }
        assert required.issubset(doc.keys())


# ---------------------------------------------------------------------------
# Savings calculation logic
# ---------------------------------------------------------------------------


class TestCostComparisonLogic:
    def test_savings_all_input_tokens(self) -> None:
        """1M DeepSeek input tokens vs Sonnet: $3.00 equivalent, save $2.73."""
        equivalent, savings, savings_pct = _compute_savings(
            deepseek_tokens_in=1_000_000,
            deepseek_tokens_out=0,
            deepseek_cost_usd=0.27,
        )
        assert equivalent == pytest.approx(3.00)
        assert savings == pytest.approx(2.73)
        assert savings_pct == pytest.approx(91.0, rel=1e-2)

    def test_savings_all_output_tokens(self) -> None:
        """1M DeepSeek output tokens: $15.00 equivalent at Sonnet rates."""
        equivalent, savings, savings_pct = _compute_savings(
            deepseek_tokens_in=0,
            deepseek_tokens_out=1_000_000,
            deepseek_cost_usd=1.10,
        )
        assert equivalent == pytest.approx(15.00)
        assert savings == pytest.approx(13.90)
        assert savings_pct == pytest.approx(92.67, rel=1e-2)

    def test_savings_zero_tokens_returns_zero_pct(self) -> None:
        """No DeepSeek tokens → savings_pct is 0 (no division by zero)."""
        equivalent, savings, savings_pct = _compute_savings(
            deepseek_tokens_in=0,
            deepseek_tokens_out=0,
            deepseek_cost_usd=0.0,
        )
        assert equivalent == pytest.approx(0.0)
        assert savings == pytest.approx(0.0)
        assert savings_pct == pytest.approx(0.0)

    def test_savings_mixed_tokens(self) -> None:
        """500K in + 500K out at DeepSeek chat rates."""
        # equivalent = (500K * 3 + 500K * 15) / 1M = 1.50 + 7.50 = 9.00
        # deepseek cost = 0.685 (from _cost test)
        # savings = 9.00 - 0.685 = 8.315
        equivalent, savings, savings_pct = _compute_savings(
            deepseek_tokens_in=500_000,
            deepseek_tokens_out=500_000,
            deepseek_cost_usd=0.685,
        )
        assert equivalent == pytest.approx(9.00)
        assert savings == pytest.approx(8.315)
        assert savings_pct == pytest.approx(92.39, rel=1e-2)
