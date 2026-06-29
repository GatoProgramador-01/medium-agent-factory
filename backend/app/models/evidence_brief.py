"""Evidence models for repository-grounded editorial planning."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class EvidenceBrief(BaseModel):
    """Repository evidence pack returned by RepoAnalyzer."""

    repository_path: str = Field(min_length=1)
    stack: list[str] = Field(min_length=1)
    commands: dict[str, str] = Field(default_factory=dict)
    architecture_hints: list[str] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)
    evidence: list[str] = Field(min_length=1)

    @field_validator("repository_path")
    @classmethod
    def _reject_blank_path(cls, value: str) -> str:
        """Normalize repository paths and reject whitespace-only values."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("repository_path must be non-empty")
        return cleaned

    @field_validator("stack", "architecture_hints", "evidence")
    @classmethod
    def _reject_blank_items(cls, value: list[str]) -> list[str]:
        """Reject blank list items so evidence stays useful downstream."""
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("list items must be non-empty")
        return cleaned

    @field_validator("commands")
    @classmethod
    def _reject_blank_commands(cls, value: dict[str, str]) -> dict[str, str]:
        """Allow no commands, but require meaningful names and command strings."""
        cleaned = {key.strip(): command.strip() for key, command in value.items()}
        if any(not key or not command for key, command in cleaned.items()):
            raise ValueError("commands must not contain blank keys or values")
        return cleaned

    @field_validator("metrics", mode="before")
    @classmethod
    def _reject_invalid_metrics(cls, value: Any) -> Any:
        """Metrics are counts; negative values indicate a bad analyzer result."""
        if not isinstance(value, dict):
            return value
        for key, metric in value.items():
            if not str(key).strip():
                raise ValueError("metrics must not contain blank keys")
            if isinstance(metric, bool) or not isinstance(metric, int):
                raise ValueError("metrics must be integers")
            if metric < 0:
                raise ValueError("metrics must be non-negative")
        return value
