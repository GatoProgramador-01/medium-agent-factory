"""TDD tests for the RepoAnalyzer agent.

Expected behavior:
  1. Analyze a local repository path without network or LLM calls.
  2. Read only safe project evidence such as README, package, pyproject, and tests.
  3. Detect stack, useful commands, architecture hints, and simple metrics.
  4. Return an EvidenceBrief Pydantic model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "sample-repo"
    _write(
        repo / "README.md",
        """# Sample Product

FastAPI powers the backend API and React renders the frontend.

## Architecture

- backend/app exposes routers and agents
- frontend/src contains the user interface
- tests cover the API boundary
""",
    )
    _write(
        repo / "package.json",
        json.dumps(
            {
                "scripts": {
                    "dev": "next dev",
                    "test": "vitest run",
                    "build": "next build",
                },
                "dependencies": {
                    "next": "15.0.0",
                    "react": "19.0.0",
                },
                "devDependencies": {"vitest": "2.0.0"},
            }
        ),
    )
    _write(
        repo / "pyproject.toml",
        """[project]
dependencies = [
    "fastapi>=0.115.0",
    "pydantic>=2.10.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
""",
    )
    _write(
        repo / "backend" / "app" / "main.py",
        "from fastapi import FastAPI\napp = FastAPI()\n",
    )
    _write(
        repo / "tests" / "test_api.py",
        "def test_healthcheck():\n    assert True\n",
    )
    _write(repo / ".env", "SECRET_TOKEN=do-not-read\n")
    _write(repo / "coverage.xml", "SECRET_TOKEN=coverage-noise\n")
    _write(
        repo / "node_modules" / "leftpad" / "index.js",
        "module.exports = 'noise'\n",
    )
    _write(repo / "dist" / "bundle.js", "const leaked = 'generated-noise';\n")
    return repo


class TestRepoAnalyzer:
    def test_analyze_returns_evidence_brief_for_local_repo(self, tmp_path: Path) -> None:
        from app.agents.repo_analyzer import RepoAnalyzer
        from app.models.evidence_brief import EvidenceBrief

        repo = _make_repo(tmp_path)

        brief = RepoAnalyzer().analyze(repo)

        assert isinstance(brief, EvidenceBrief)
        assert Path(brief.repository_path) == repo
        assert {"python", "fastapi", "pydantic", "react", "next"}.issubset(
            set(brief.stack)
        )
        assert brief.commands["frontend_test"] == "vitest run"
        assert brief.commands["frontend_build"] == "next build"
        assert brief.commands["backend_test"] == "pytest"
        assert brief.metrics["readme_files"] == 1
        assert brief.metrics["package_manifests"] == 2
        assert brief.metrics["test_files"] == 1
        assert brief.metrics["files_scanned"] >= 4
        assert any("backend/app" in hint for hint in brief.architecture_hints)
        assert any("frontend/src" in hint for hint in brief.architecture_hints)
        assert any("README.md" in item for item in brief.evidence)

    def test_analyze_ignores_secret_and_dependency_directories(
        self, tmp_path: Path
    ) -> None:
        from app.agents.repo_analyzer import RepoAnalyzer

        repo = _make_repo(tmp_path)

        brief = RepoAnalyzer().analyze(repo)
        combined_evidence = "\n".join(brief.evidence + brief.architecture_hints)

        assert "SECRET_TOKEN" not in combined_evidence
        assert "do-not-read" not in combined_evidence
        assert "coverage-noise" not in combined_evidence
        assert "node_modules" not in combined_evidence
        assert "generated-noise" not in combined_evidence
        assert "dist" not in combined_evidence

    def test_analyze_python_repo_without_package_json(self, tmp_path: Path) -> None:
        from app.agents.repo_analyzer import RepoAnalyzer

        repo = tmp_path / "python-only"
        _write(repo / "README.md", "# Worker\n\nAsync Python service with pytest tests.\n")
        _write(
            repo / "pyproject.toml",
            """[project]
dependencies = ["pydantic>=2", "httpx>=0.28"]

[project.optional-dependencies]
dev = ["pytest>=8"]
""",
        )
        _write(repo / "tests" / "test_worker.py", "def test_worker():\n    assert True\n")

        brief = RepoAnalyzer().analyze(repo)

        assert {"python", "pydantic", "pytest"}.issubset(set(brief.stack))
        assert brief.commands["backend_test"] == "pytest"
        assert "frontend_test" not in brief.commands
        assert brief.metrics["package_manifests"] == 1
        assert brief.metrics["test_files"] == 1

    def test_analyze_detects_pytest_from_test_file_content(self, tmp_path: Path) -> None:
        from app.agents.repo_analyzer import RepoAnalyzer

        repo = tmp_path / "tests-only-signal"
        _write(repo / "README.md", "# Utility\n\nSmall Python helper.\n")
        _write(repo / "pyproject.toml", "[project]\ndependencies = []\n")
        _write(
            repo / "tests" / "test_cli.py",
            "import pytest\n\n@pytest.mark.parametrize('value', [1])\ndef test_cli(value):\n    assert value\n",
        )

        brief = RepoAnalyzer().analyze(repo)

        assert "pytest" in brief.stack
        assert brief.commands["backend_test"] == "pytest"
        assert any("tests/test_cli.py:" in item for item in brief.evidence)

    def test_evidence_entries_name_source_files(self, tmp_path: Path) -> None:
        from app.agents.repo_analyzer import RepoAnalyzer

        repo = _make_repo(tmp_path)

        brief = RepoAnalyzer().analyze(repo)

        assert all(":" in item for item in brief.evidence)
        assert any(item.startswith("pyproject.toml:") for item in brief.evidence)
        assert any(item.startswith("package.json:") for item in brief.evidence)
        assert any(item.startswith("tests/test_api.py:") for item in brief.evidence)

    def test_analyze_rejects_missing_repository_path(self, tmp_path: Path) -> None:
        from app.agents.repo_analyzer import RepoAnalyzer

        with pytest.raises(FileNotFoundError):
            RepoAnalyzer().analyze(tmp_path / "missing")

    def test_analyze_rejects_file_path(self, tmp_path: Path) -> None:
        from app.agents.repo_analyzer import RepoAnalyzer

        not_a_repo = tmp_path / "README.md"
        not_a_repo.write_text("# Not a repository\n", encoding="utf-8")

        with pytest.raises(NotADirectoryError):
            RepoAnalyzer().analyze(not_a_repo)

    def test_module_exposes_convenience_function(self, tmp_path: Path) -> None:
        from app.agents.repo_analyzer import analyze_repository
        from app.models.evidence_brief import EvidenceBrief

        repo = _make_repo(tmp_path)

        brief = analyze_repository(repo)

        assert isinstance(brief, EvidenceBrief)
        assert "fastapi" in brief.stack

    def test_convenience_function_accepts_string_path(self, tmp_path: Path) -> None:
        from app.agents.repo_analyzer import analyze_repository

        repo = _make_repo(tmp_path)

        brief = analyze_repository(str(repo))

        assert Path(brief.repository_path) == repo
        assert "next" in brief.stack
