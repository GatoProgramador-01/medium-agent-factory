"""TDD tests for the EvidenceBrief model.

The model should be a Pydantic contract returned by RepoAnalyzer, suitable for
serializing into an agent handoff or API response.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestEvidenceBriefModel:
    def test_evidence_brief_has_required_analysis_fields(self) -> None:
        from app.models.evidence_brief import EvidenceBrief

        brief = EvidenceBrief(
            repository_path="/tmp/example",
            stack=["python", "fastapi", "react"],
            commands={
                "backend_test": "pytest",
                "frontend_test": "npm test",
                "frontend_build": "npm run build",
            },
            architecture_hints=[
                "README mentions API and frontend layers",
                "backend/app contains application code",
            ],
            metrics={
                "files_scanned": 5,
                "test_files": 1,
                "readme_files": 1,
                "package_manifests": 2,
            },
            evidence=[
                "README.md: FastAPI API with React frontend",
                "package.json: scripts.test = vitest",
            ],
        )

        dumped = brief.model_dump()
        assert dumped["repository_path"] == "/tmp/example"
        assert {"python", "fastapi", "react"}.issubset(set(brief.stack))
        assert brief.commands["backend_test"] == "pytest"
        assert brief.metrics["files_scanned"] == 5
        assert brief.evidence

    def test_evidence_brief_requires_non_empty_evidence(self) -> None:
        from app.models.evidence_brief import EvidenceBrief

        with pytest.raises(ValidationError):
            EvidenceBrief(
                repository_path="/tmp/example",
                stack=["python"],
                commands={"test": "pytest"},
                architecture_hints=["backend/app exists"],
                metrics={"files_scanned": 2},
                evidence=[],
            )

    def test_evidence_brief_rejects_negative_metrics(self) -> None:
        from app.models.evidence_brief import EvidenceBrief

        with pytest.raises(ValidationError):
            EvidenceBrief(
                repository_path="/tmp/example",
                stack=["python"],
                commands={"test": "pytest"},
                architecture_hints=["backend/app exists"],
                metrics={"files_scanned": -1},
                evidence=["pyproject.toml declares pytest"],
            )

    def test_evidence_brief_rejects_blank_repository_path(self) -> None:
        from app.models.evidence_brief import EvidenceBrief

        with pytest.raises(ValidationError):
            EvidenceBrief(
                repository_path="",
                stack=["python"],
                commands={"test": "pytest"},
                architecture_hints=["tests directory exists"],
                metrics={"files_scanned": 1},
                evidence=["tests/test_api.py exists"],
            )

        with pytest.raises(ValidationError):
            EvidenceBrief(
                repository_path="   ",
                stack=["python"],
                commands={"test": "pytest"},
                architecture_hints=["tests directory exists"],
                metrics={"files_scanned": 1},
                evidence=["tests/test_api.py exists"],
            )

    def test_evidence_brief_requires_non_empty_stack(self) -> None:
        from app.models.evidence_brief import EvidenceBrief

        with pytest.raises(ValidationError):
            EvidenceBrief(
                repository_path="/tmp/example",
                stack=[],
                commands={"test": "pytest"},
                architecture_hints=["tests directory exists"],
                metrics={"files_scanned": 1},
                evidence=["tests/test_api.py exists"],
            )

    def test_evidence_brief_rejects_blank_list_items(self) -> None:
        from app.models.evidence_brief import EvidenceBrief

        with pytest.raises(ValidationError):
            EvidenceBrief(
                repository_path="/tmp/example",
                stack=["python", ""],
                commands={"test": "pytest"},
                architecture_hints=["tests directory exists"],
                metrics={"files_scanned": 1},
                evidence=["tests/test_api.py exists"],
            )

        with pytest.raises(ValidationError):
            EvidenceBrief(
                repository_path="/tmp/example",
                stack=["python"],
                commands={"test": "pytest"},
                architecture_hints=["tests directory exists"],
                metrics={"files_scanned": 1},
                evidence=[""],
            )

        with pytest.raises(ValidationError):
            EvidenceBrief(
                repository_path="/tmp/example",
                stack=["python"],
                commands={"test": "pytest"},
                architecture_hints=[""],
                metrics={"files_scanned": 1},
                evidence=["tests/test_api.py exists"],
            )

    def test_evidence_brief_rejects_blank_command_entries(self) -> None:
        from app.models.evidence_brief import EvidenceBrief

        with pytest.raises(ValidationError):
            EvidenceBrief(
                repository_path="/tmp/example",
                stack=["python"],
                commands={"": "pytest"},
                architecture_hints=["tests directory exists"],
                metrics={"files_scanned": 1},
                evidence=["tests/test_api.py exists"],
            )

        with pytest.raises(ValidationError):
            EvidenceBrief(
                repository_path="/tmp/example",
                stack=["python"],
                commands={"backend_test": "   "},
                architecture_hints=["tests directory exists"],
                metrics={"files_scanned": 1},
                evidence=["tests/test_api.py exists"],
            )

    def test_evidence_brief_rejects_invalid_metric_entries(self) -> None:
        from app.models.evidence_brief import EvidenceBrief

        for metrics in (
            {"files_scanned": "1"},
            {"files_scanned": True},
            {"": 1},
        ):
            with pytest.raises(ValidationError):
                EvidenceBrief(
                    repository_path="/tmp/example",
                    stack=["python"],
                    commands={"test": "pytest"},
                    architecture_hints=["tests directory exists"],
                    metrics=metrics,
                    evidence=["tests/test_api.py exists"],
                )
