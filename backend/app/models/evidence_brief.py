"""Evidence brief model for local repository analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class EvidenceBrief(BaseModel):
    """Structured evidence extracted from a repository without LLM calls."""

    repository_path: str = Field(min_length=1)
    stack: list[str] = Field(min_length=1)
    commands: dict[str, str] = Field(default_factory=dict)
    architecture_hints: list[str] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)
    evidence: list[str] = Field(min_length=1)

    @field_validator("repository_path")
    @classmethod
    def _path_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("repository_path must not be blank")
        return value

    @field_validator("stack", "architecture_hints", "evidence")
    @classmethod
    def _list_items_not_blank(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("list fields must not contain blank items")
        return cleaned

    @field_validator("commands")
    @classmethod
    def _commands_not_blank(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned = {key.strip(): command.strip() for key, command in value.items()}
        if any(not key or not command for key, command in cleaned.items()):
            raise ValueError("commands must not contain blank keys or values")
        return cleaned

    @field_validator("metrics")
    @classmethod
    def _metrics_non_negative(cls, value: dict[str, int]) -> dict[str, int]:
        if any(metric < 0 for metric in value.values()):
            raise ValueError("metrics must be non-negative")
        return value
