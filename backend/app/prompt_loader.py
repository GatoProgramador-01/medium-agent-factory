"""
Prompt loader — reads all .txt files from backend/prompts/ at import time.

Usage:
    from app.prompt_loader import load_prompt, load_template

    # Plain string — use as SystemMessage content
    system_msg = load_prompt("quality_analyzer_system")

    # Pre-formatted template — call .format(**vars) inline
    human_msg  = load_template("quality_analyzer_human").format(
        title=title, content=content
    )

Files live in:  backend/prompts/<name>.txt
Naming rule:    <agent>_<role>.txt  (e.g. quality_analyzer_system.txt)

Why this exists:
  Prompts are versioned in git like code. Any change to prompts/ triggers the
  eval CI gate (.github/workflows/eval.yml path filter), so a prompt regression
  can never ship without a failing test catching it first.

LangChain Hub alternative (team collaboration layer, optional):
    from langchain import hub
    prompt = hub.pull("your-org/quality-analyzer-system:abc123")
    hub.push("your-org/quality-analyzer-system", ChatPromptTemplate.from_template(text))
  Use Hub when multiple engineers iterate on prompts outside the codebase.
  Use local files (this module) for single-team projects or when offline CI is required.
"""

from pathlib import Path
from string import Template

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Load all prompts into memory once at startup — dict[name → raw text]
_CACHE: dict[str, str] = {}

for _path in _PROMPTS_DIR.glob("*.txt"):
    _CACHE[_path.stem] = _path.read_text(encoding="utf-8")

if not _CACHE:
    raise RuntimeError(
        f"No prompt files found in {_PROMPTS_DIR}. "
        "Run from the backend/ directory or check the prompts/ path."
    )


def load_prompt(name: str) -> str:
    """Return the raw prompt text for the given file stem (no .txt extension)."""
    try:
        return _CACHE[name]
    except KeyError:
        available = sorted(_CACHE.keys())
        raise KeyError(
            f"Prompt '{name}' not found. Available: {available}"
        ) from None


class _PromptTemplate:
    """Thin wrapper that exposes .format(**kwargs) on a prompt string."""

    def __init__(self, text: str, name: str) -> None:
        self._text = text
        self._name = name

    def format(self, **kwargs: object) -> str:
        try:
            return self._text.format(**kwargs)
        except KeyError as e:
            raise KeyError(
                f"Prompt '{self._name}' missing variable {e}. "
                f"Provided keys: {sorted(kwargs.keys())}"
            ) from e

    def __str__(self) -> str:
        return self._text


def load_template(name: str) -> _PromptTemplate:
    """Return a formattable template for the given prompt file stem."""
    return _PromptTemplate(load_prompt(name), name)
