from dataclasses import dataclass, field
from datetime import datetime, UTC


@dataclass(frozen=True)
class AgentRunRecord:
    run_id: str
    agent_name: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    duration_ms: int
    model: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_doc(self) -> dict:
        return {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
            "duration_ms": self.duration_ms,
            "model": self.model,
            "created_at": self.created_at,
        }
