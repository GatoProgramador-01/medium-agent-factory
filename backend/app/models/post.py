from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


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
class QualityReport:
    score: float  # 0.0 – 1.0
    read_ratio_prediction: float  # estimated % of viewers who finish
    medium_boost_eligible: bool  # meets all 6 Medium Boost criteria
    issues: list[QualityIssue]
    strengths: list[str]
    revision_prompt: str  # injected into next content-gen pass


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
