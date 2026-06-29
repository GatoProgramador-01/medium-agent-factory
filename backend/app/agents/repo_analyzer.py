"""Local repository analyzer for evidence-first writing workflows."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.models.evidence_brief import EvidenceBrief

_SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
}
_SKIP_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    "coverage.xml",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}
_SAFE_ROOT_FILES = {
    "README.md",
    "README.rst",
    "README.txt",
    "package.json",
    "pyproject.toml",
}
_SAFE_SUFFIXES = {".py", ".toml", ".json", ".md", ".rst", ".txt"}


class RepoAnalyzer:
    """Analyze a local repository using safe, deterministic file inspection."""

    def analyze(self, repository_path: str | Path) -> EvidenceBrief:
        repo = Path(repository_path)
        if not repo.exists():
            raise FileNotFoundError(repo)
        if not repo.is_dir():
            raise NotADirectoryError(repo)

        safe_files = list(_iter_safe_files(repo))
        evidence: list[str] = []
        stack: set[str] = set()
        commands: dict[str, str] = {}
        architecture_hints: list[str] = []

        readme_files = 0
        package_manifests = 0
        test_files = 0

        for path in safe_files:
            rel = _rel(path, repo)
            text = _read_text(path)
            if not text:
                continue

            if path.name.lower().startswith("readme"):
                readme_files += 1
                _analyze_readme(rel, text, stack, architecture_hints, evidence)
            elif path.name == "package.json":
                package_manifests += 1
                _analyze_package_json(rel, text, stack, commands, evidence)
            elif path.name == "pyproject.toml":
                package_manifests += 1
                _analyze_pyproject(rel, text, stack, commands, evidence)
            elif _is_test_file(path, repo):
                test_files += 1
                _analyze_test_file(rel, text, stack, commands, evidence)
            elif rel.replace("\\", "/") == "backend/app/main.py":
                _add_evidence(evidence, rel, "FastAPI application entrypoint found")
                stack.add("fastapi")

        if (repo / "backend" / "app").is_dir():
            architecture_hints.append("backend/app contains application code")
        if (repo / "frontend" / "src").is_dir():
            architecture_hints.append("frontend/src contains user interface code")

        metrics = {
            "files_scanned": len(safe_files),
            "test_files": test_files,
            "readme_files": readme_files,
            "package_manifests": package_manifests,
        }

        if not evidence:
            _add_evidence(
                evidence,
                ".",
                "Repository exists but no safe evidence files matched",
            )
        if not stack:
            stack.add("unknown")

        return EvidenceBrief(
            repository_path=str(repo),
            stack=sorted(stack),
            commands=commands,
            architecture_hints=_dedupe(architecture_hints),
            metrics=metrics,
            evidence=_dedupe(evidence),
        )


def analyze_repository(repository_path: str | Path) -> EvidenceBrief:
    return RepoAnalyzer().analyze(repository_path)


def _iter_safe_files(repo: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(repo).parts
        if any(part in _SKIP_DIRS for part in rel_parts[:-1]):
            continue
        if path.name in _SKIP_FILES:
            continue
        rel = path.relative_to(repo)
        is_safe_root = len(rel.parts) == 1 and path.name in _SAFE_ROOT_FILES
        is_safe_test = _is_test_file(path, repo)
        is_safe_app_hint = rel.as_posix() == "backend/app/main.py"
        if (
            is_safe_root or is_safe_test or is_safe_app_hint
        ) and path.suffix in _SAFE_SUFFIXES:
            files.append(path)
    return sorted(files)


def _read_text(path: Path, limit: int = 80_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _analyze_readme(
    rel: str,
    text: str,
    stack: set[str],
    architecture_hints: list[str],
    evidence: list[str],
) -> None:
    lower = text.lower()
    _detect_stack_from_text(lower, stack)
    for hint in ("backend/app", "frontend/src", "api", "frontend", "backend", "tests"):
        if hint in lower:
            architecture_hints.append(f"{rel} mentions {hint}")
    first_line = next(
        (line.strip("# ").strip() for line in text.splitlines() if line.strip()),
        "",
    )
    if first_line:
        _add_evidence(evidence, rel, first_line)


def _analyze_package_json(
    rel: str,
    text: str,
    stack: set[str],
    commands: dict[str, str],
    evidence: list[str],
) -> None:
    try:
        data: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        _add_evidence(evidence, rel, "package.json could not be parsed")
        return

    deps = {
        **data.get("dependencies", {}),
        **data.get("devDependencies", {}),
    }
    for name in deps:
        normalized = name.lower()
        if normalized in {"react", "next", "vitest", "typescript"}:
            stack.add(normalized)

    scripts = data.get("scripts", {})
    if isinstance(scripts, dict):
        if scripts.get("test"):
            commands["frontend_test"] = str(scripts["test"])
            _add_evidence(evidence, rel, f"scripts.test = {scripts['test']}")
        if scripts.get("build"):
            commands["frontend_build"] = str(scripts["build"])
            _add_evidence(evidence, rel, f"scripts.build = {scripts['build']}")


def _analyze_pyproject(
    rel: str,
    text: str,
    stack: set[str],
    commands: dict[str, str],
    evidence: list[str],
) -> None:
    lower = text.lower()
    stack.add("python")
    _detect_stack_from_text(lower, stack)
    if "pytest" in lower or "[tool.pytest" in lower:
        stack.add("pytest")
        commands.setdefault("backend_test", "pytest")
        _add_evidence(evidence, rel, "pytest configured for backend tests")
    elif "[project]" in lower:
        _add_evidence(evidence, rel, "Python project metadata found")


def _analyze_test_file(
    rel: str,
    text: str,
    stack: set[str],
    commands: dict[str, str],
    evidence: list[str],
) -> None:
    stack.add("python")
    if "pytest" in text or re.search(r"def test_", text):
        stack.add("pytest")
        commands.setdefault("backend_test", "pytest")
    _add_evidence(evidence, rel, "test file found")


def _detect_stack_from_text(lower_text: str, stack: set[str]) -> None:
    signals = {
        "python": ("python", "pyproject"),
        "fastapi": ("fastapi",),
        "pydantic": ("pydantic",),
        "react": ("react",),
        "next": ("next", "next.js"),
        "pytest": ("pytest",),
    }
    for name, needles in signals.items():
        if any(needle in lower_text for needle in needles):
            stack.add(name)


def _is_test_file(path: Path, repo: Path) -> bool:
    rel = path.relative_to(repo).as_posix()
    return (
        "/tests/" in f"/{rel}"
        and path.suffix == ".py"
        and (path.name.startswith("test_") or path.name.endswith("_test.py"))
    )


def _add_evidence(evidence: list[str], rel: str, detail: str) -> None:
    normalized_rel = rel.replace("\\", "/")
    evidence.append(f"{normalized_rel}: {detail.strip()}")


def _rel(path: Path, repo: Path) -> str:
    return path.relative_to(repo).as_posix()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
