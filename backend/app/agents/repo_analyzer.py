"""Repository analyzer for evidence-first editorial planning.

This agent is deterministic: it reads a local repository, extracts stack,
commands, architecture hints, tests, metrics, and notable files, then returns an
EvidenceBrief that writer agents can use without inventing project facts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from app.models.evidence_brief import EvidenceBrief

_TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".py",
    ".sh",
    ".ps1",
}
_TEXT_FILENAMES = {"dockerfile", "makefile"}

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "worktrees",
}


class RepoAnalyzer:
    """Deterministic local repository analyzer."""

    def __init__(self, max_files: int = 250) -> None:
        """Configure analyzer bounds.

        Args:
            max_files: Maximum files to scan before stopping.
        """
        self.max_files = max_files

    def analyze(self, repo_path: str | Path) -> EvidenceBrief:
        """Analyze a repository path and return an EvidenceBrief."""
        return analyze_repository(repo_path, max_files=self.max_files)


def analyze_repository(repo_path: str | Path, max_files: int = 250) -> EvidenceBrief:
    """Analyze a local repository and return an EvidenceBrief.

    Args:
        repo_path: Local repository path.
        max_files: Maximum number of files to inspect to keep analysis bounded.

    Returns:
        EvidenceBrief with deterministic evidence for editorial planning.

    Raises:
        FileNotFoundError: If repo_path does not exist.
        NotADirectoryError: If repo_path is not a directory.
    """
    root = Path(repo_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Repository path not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")

    files = _iter_repo_files(root, max_files=max_files)
    texts = _read_priority_texts(root, files)
    readme_text = _first_existing_text(texts, ("README.md", "readme.md")) or ""

    stack = _detect_stack(files, texts)
    test_files = _find_test_files(files)
    commands = _extract_commands(texts, test_files)
    architecture_hints = _extract_architecture_hints(readme_text, files)
    evidence = _extract_evidence(texts, test_files)
    metrics = {
        "files_scanned": len(files),
        "test_files": len(test_files),
        "readme_files": sum(1 for p in files if p.name.lower() == "readme.md"),
        "package_manifests": sum(
            1
            for p in files
            if p.name.lower() in {"package.json", "pyproject.toml"}
        ),
    }

    return EvidenceBrief(
        repository_path=str(root),
        stack=stack or ["unknown"],
        architecture_hints=architecture_hints,
        commands=commands,
        metrics=metrics,
        evidence=evidence or [f"{root.name}: repository scanned"],
    )


def _iter_repo_files(root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda p: _file_priority(root, p))[:max_files]


def _file_priority(root: Path, path: Path) -> tuple[int, str]:
    rel = str(path.relative_to(root)).replace("\\", "/").lower()
    name = path.name.lower()
    if name in {"readme.md", "package.json", "pyproject.toml", "docker-compose.yml", "dockerfile"}:
        return (0, rel)
    if rel.startswith("backend/") or rel.startswith("frontend/"):
        return (1, rel)
    if "/tests/" in f"/{rel}" or name.startswith("test_") or name.endswith("_test.py"):
        return (2, rel)
    if name.startswith(".env") or rel.startswith(".codex/") or rel.startswith(".claude/worktrees/"):
        return (9, rel)
    return (5, rel)


def _read_priority_texts(root: Path, files: list[Path]) -> dict[str, str]:
    priority = []
    for path in files:
        rel = str(path.relative_to(root)).replace("\\", "/")
        if (
            path.suffix.lower() not in _TEXT_EXTENSIONS
            and path.name.lower() not in _TEXT_FILENAMES
        ):
            continue
        if rel.lower() in {
            "readme.md",
            "docker-compose.yml",
            "dockerfile",
            "makefile",
        } or rel.lower().endswith(("package.json", "pyproject.toml")) or any(
            part in rel.lower() for part in ("test", "script", "src/", "app/")
        ):
            priority.append(path)

    texts: dict[str, str] = {}
    for path in priority[:80]:
        rel = str(path.relative_to(root)).replace("\\", "/")
        try:
            texts[rel] = path.read_text(encoding="utf-8", errors="replace")[:12000]
        except OSError:
            continue
    return texts


def _first_existing_text(texts: dict[str, str], names: tuple[str, ...]) -> str | None:
    lowered = {k.lower(): v for k, v in texts.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _detect_stack(files: list[Path], texts: dict[str, str]) -> list[str]:
    rels = {str(p).replace("\\", "/").lower() for p in files}
    blob = "\n".join(texts.values()).lower()
    stack: list[str] = []
    checks: list[tuple[str, Callable[[], bool]]] = [
        ("typescript", lambda: any(p.endswith(".ts") or p.endswith(".tsx") for p in rels)),
        ("python", lambda: any(p.endswith(".py") for p in rels)),
        ("node", lambda: "package.json" in {Path(p).name for p in rels}),
        ("fastapi", lambda: "fastapi" in blob),
        ("pydantic", lambda: "pydantic" in blob),
        ("react", lambda: "react" in blob),
        ("next", lambda: "next" in blob or any("next.config" in p for p in rels)),
        ("pytest", lambda: "pytest" in blob or any("test_" in Path(p).name for p in rels)),
        ("mongodb", lambda: "mongodb" in blob or "motor" in blob),
        ("docker", lambda: any(Path(p).name in {"dockerfile", "docker-compose.yml"} for p in rels)),
        ("playwright", lambda: "playwright" in blob),
        ("cheerio", lambda: "cheerio" in blob),
        ("axios", lambda: "axios" in blob),
        ("langgraph", lambda: "langgraph" in blob),
    ]
    for name, predicate in checks:
        if predicate():
            stack.append(name)
    return stack


def _extract_commands(texts: dict[str, str], test_files: list[str]) -> dict[str, str]:
    commands: dict[str, str] = {}

    package_items = [(name, text) for name, text in texts.items() if name.endswith("package.json")]
    for package_name, package in package_items:
        try:
            data = json.loads(package)
            scripts = data.get("scripts", {})
            if isinstance(scripts, dict):
                for name, command in scripts.items():
                    if isinstance(command, str):
                        if name == "test":
                            commands["frontend_test"] = command
                        elif name == "build":
                            commands["frontend_build"] = command
                        elif name == "dev":
                            commands["frontend_dev"] = command
                        else:
                            commands[f"frontend_{name}"] = command
        except json.JSONDecodeError:
            pass

    if any(name.endswith("pyproject.toml") for name in texts) or test_files:
        commands.setdefault("backend_test", "pytest")

    for source_file, text in texts.items():
        if source_file.lower() != "readme.md":
            continue
        for match in re.finditer(r"(?m)^\s*(npm|pnpm|yarn|python|pytest|docker|make)\s+([^\n]+)", text):
            command = f"{match.group(1)} {match.group(2).strip()}"
            commands.setdefault(_command_name(command), command)

    return dict(list(commands.items())[:20])


def _find_test_files(files: list[Path]) -> list[str]:
    result = []
    for path in files:
        rel = str(path).replace("\\", "/")
        name = path.name.lower()
        if (
            name.startswith("test_")
            or name.endswith("_test.py")
            or "__tests__" in rel.lower()
            or "/tests/" in rel.lower()
        ):
            # Normalize later via suffix from the first "tests/" marker.
            marker = "tests/"
            result.append(rel[rel.find(marker) :] if marker in rel else path.name)
    return result[:40]


def _extract_architecture_hints(readme_text: str, files: list[Path]) -> list[str]:
    hints: list[str] = []
    for line in readme_text.splitlines():
        stripped = line.strip(" -*#")
        if not stripped or len(stripped) > 180:
            continue
        lowered = stripped.lower()
        if any(
            term in lowered
            for term in (
                "architecture",
                "layer",
                "pipeline",
                "workflow",
                "module",
                "service",
                "worker",
                "checkpoint",
                "backend/",
                "frontend/",
                "src/",
                "tests",
            )
        ):
            hints.append(stripped)

    root = _common_repo_root(files)
    dirs = []
    for path in files:
        try:
            rel_parent = str(path.parent.relative_to(root)).replace("\\", "/") if root else str(path.parent)
        except ValueError:
            rel_parent = str(path.parent).replace("\\", "/")
        dirs.append(rel_parent)
    dirs = sorted(set(dirs))
    for directory in dirs[:20]:
        lowered = directory.lower()
        if any(term in lowered for term in ("src", "app", "lib", "services", "workers", "tests", "scripts")):
            hints.append(f"Directory: {directory}")

    return [hint for hint in _dedupe_strings(hints) if "node_modules" not in hint and "dist" not in hint][:25]


def _common_repo_root(files: list[Path]) -> Path | None:
    if not files:
        return None
    candidates = [p.parent for p in files if p.name.lower() in {"readme.md", "package.json", "pyproject.toml"}]
    if candidates:
        return min(candidates, key=lambda p: len(p.parts))
    common = Path(files[0])
    for path in files[1:]:
        while common not in path.parents and common != path:
            if common.parent == common:
                return None
            common = common.parent
    return common if common.is_dir() else common.parent


def _extract_evidence(texts: dict[str, str], test_files: list[str]) -> list[str]:
    evidence: list[str] = []
    readme = texts.get("README.md") or texts.get("readme.md")
    if readme:
        for line in readme.splitlines():
            stripped = line.strip(" #-*")
            if len(stripped) >= 10 and not stripped.startswith("<") and "badge" not in stripped.lower():
                evidence.append(f"README.md: {stripped[:180]}")
                break

    package_items = [(name, text) for name, text in texts.items() if name.endswith("package.json")]
    for package_name, package in package_items:
        try:
            data = json.loads(package)
            scripts = data.get("scripts", {})
            if isinstance(scripts, dict):
                for key, value in scripts.items():
                    evidence.append(f"{package_name}: scripts.{key} = {value}")
        except json.JSONDecodeError:
            evidence.append(f"{package_name}: present but not parseable")

    pyproject_items = [(name, text) for name, text in texts.items() if name.endswith("pyproject.toml")]
    for pyproject_name, pyproject in pyproject_items:
        deps = []
        for dep in ("fastapi", "pydantic", "pytest", "httpx"):
            if dep in pyproject.lower():
                deps.append(dep)
        evidence.append(
            f"{pyproject_name}: dependencies include {', '.join(deps) if deps else 'project metadata'}"
        )

    for test_file in test_files[:10]:
        evidence.append(f"{test_file}: test file exists")

    return _dedupe_strings(evidence)[:40]


def _command_name(command: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", command.lower()).strip("_")[:40] or "command"


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
