from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


@dataclass
class AtomicClaim:
    text: str        # exact phrase from the post
    claim_type: str  # "statistic" | "percentage" | "dollar_amount" | "date" | "company_claim"
    search_query: str
    location: str    # e.g. "paragraph 1"


@dataclass
class VerificationResult:
    claim: AtomicClaim
    verdict: str          # "SUPPORTED" | "UNVERIFIABLE"
    source_url: str | None
    source_title: str | None


@dataclass
class SeriesDocument:
    series_id: str
    theme: str
    series_title: str
    series_description: str
    post_count: int
    status: str  # "running" | "completed" | "failed"
    run_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class PostStatus(StrEnum):
    DRAFT = "draft"
    REVISED = "revised"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class QualityIssue:
    category: str  # "ai_pattern" | "readability" | "formatting" | "structure"
    severity: str  # "high" | "medium" | "low"
    location: str  # excerpt or section reference
    suggestion: str


@dataclass
class ReadRatioFactor:
    name: str       # e.g. "Intro length"
    measured: str   # e.g. "143 words"
    deduction: float
    guidance: str   # what to fix


@dataclass
class QualityReport:
    score: float  # 0.0–1.0, mean of 4 G-Eval content axes
    read_ratio_prediction: float  # from read_ratio_analyzer formula
    medium_boost_eligible: bool   # meets all Medium Boost criteria
    issues: list[QualityIssue]
    strengths: list[str]
    revision_prompt: str  # injected into next content-gen pass
    word_count: int = 0   # computed from content, not LLM
    read_ratio_factors: list[ReadRatioFactor] = field(default_factory=list)
    read_ratio_hook_score: float = 0.0
    # G-Eval content axes (Layer B rubric scores)
    hook_strength: float = 0.0
    specificity_score: float = 0.0
    voice_authenticity: float = 0.0
    insight_value: float = 0.0


@dataclass
class PostDocument:
    run_id: str
    topic: str
    trend_context: str
    title: str
    content: str
    tags: list[str]
    status: PostStatus
    quality_report: QualityReport | None = None
    pull_quote: str | None = None
    format_changes: list[str] = field(default_factory=list)
    series_id: str | None = None
    series_position: int | None = None
    medium_url: str | None = None
    revision_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_doc(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "run_id": self.run_id,
            "topic": self.topic,
            "trend_context": self.trend_context,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "status": str(self.status),
            "revision_count": self.revision_count,
            "medium_url": self.medium_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.quality_report:
            doc["quality_report"] = {
                "score": self.quality_report.score,
                "read_ratio_prediction": self.quality_report.read_ratio_prediction,
                "issues": [
                    {
                        "category": i.category,
                        "severity": i.severity,
                        "location": i.location,
                        "suggestion": i.suggestion,
                    }
                    for i in self.quality_report.issues
                ],
                "strengths": self.quality_report.strengths,
                "revision_prompt": self.quality_report.revision_prompt,
            }
        return doc
