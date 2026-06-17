"""
Read Ratio Analyzer — deterministic formula + one narrow LLM call.

Computes the predicted Medium read ratio (fraction of page-loaders who stay
30+ seconds) from measured structural signals and a single LLM hook-quality
score. Every factor is named, measured, and documented so the number is
never a magic black box.

Formula: BASE 0.82, minus deductions for each measured failure.
Cap: [0.20, 0.95]. The only LLM judgment is hook quality (0–1).
Everything else is Python-measured from the content.

WHY this is reliable:
  Medium's engineering blog and Partner Program data show that read ratio
  is primarily structural — it is determined by decisions the writer makes
  before the reader is 100 words in. The factors below are ordered by their
  empirical impact on read ratio drop-off.

FACTORS (ordered by impact):
  1. Hook quality        — does sentence 1 stop the scroll?        (LLM, 0–1)
  2. Intro length        — every word past 100 costs readers       (Python, words)
  3. Reading time        — 5–7 min is the read-ratio sweet spot    (Python, min)
  4. Paragraph density   — short paragraphs keep readers scrolling (Python, avg sentences)
  5. Pattern interrupt   — prevents drop-off at the scroll midpoint(Python, bool)
  6. Sentence variety    — uniform length = robotic = bounce        (Python, CV)
"""

import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.models.post import ReadRatioFactor

_BASE_RATIO = 0.82
_READING_SPEED_WPM = 238  # average adult reading speed, per NNGroup

# ReadRatioFactor is defined in app.models.post — imported above.

# ── Pydantic model for the hook LLM call ──────────────────────────────────────


class _HookScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    reason: str

    @field_validator("score", mode="before")
    @classmethod
    def _normalize(cls, v: Any) -> Any:
        try:
            f = float(v)
            return f / 100.0 if f > 1.0 else f
        except (TypeError, ValueError):
            return v


# ── Structural measurement ─────────────────────────────────────────────────────


def _measure_structure(content: str) -> dict[str, Any]:
    words = content.split()
    word_count = len(words)

    # ── Intro: text before first ## heading or --- separator ──────────────────
    split = re.split(r"\n##\s|\n---\n", content, maxsplit=1)
    intro_text = split[0].strip()
    intro_words = len(intro_text.split())

    # First sentence (for hook scoring)
    sentence_break = re.split(r"(?<=[.!?])\s+", intro_text.replace("\n", " "), maxsplit=1)
    first_sentence = sentence_break[0].strip() if sentence_break else intro_text[:200]

    # ── Paragraph density ─────────────────────────────────────────────────────
    raw_blocks = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    prose_blocks = [
        b for b in raw_blocks
        if not b.startswith("#") and not b.startswith("[IMAGE") and len(b.split()) > 4
    ]

    def _count_sentences(para: str) -> int:
        clean = re.sub(r"\[IMAGE:.*?\]", "", para)
        parts = re.split(r"[.!?]+(?:\s|$)", clean.strip())
        return max(1, len([s for s in parts if s.strip()]))

    para_counts = [_count_sentences(b) for b in prose_blocks]
    avg_para_sentences = sum(para_counts) / len(para_counts) if para_counts else 0.0

    # ── Reading time ──────────────────────────────────────────────────────────
    reading_time_min = word_count / _READING_SPEED_WPM

    # ── H2 headings ───────────────────────────────────────────────────────────
    h2_count = len(re.findall(r"\n##\s", "\n" + content))

    # ── Sentence length variety (coefficient of variation) ────────────────────
    all_sents = re.split(r"[.!?]+\s+", re.sub(r"\[IMAGE:.*?\]", "", content))
    sent_lengths = [len(s.split()) for s in all_sents if len(s.split()) >= 3]
    if len(sent_lengths) >= 5:
        mean = sum(sent_lengths) / len(sent_lengths)
        std = (sum((l - mean) ** 2 for l in sent_lengths) / len(sent_lengths)) ** 0.5
        sentence_cv = std / mean if mean > 0 else 0.0
    else:
        sentence_cv = 0.0

    # ── Pattern interrupt in middle third ─────────────────────────────────────
    mid_start = word_count // 3
    mid_end = 2 * word_count // 3
    middle_text = " ".join(words[mid_start:mid_end])
    has_bold_interrupt = bool(re.search(r"\*\*[^*]{10,80}\*\*", middle_text))
    has_question_interrupt = "?" in middle_text
    has_pattern_interrupt = has_bold_interrupt or has_question_interrupt

    return {
        "word_count": word_count,
        "intro_words": intro_words,
        "first_sentence": first_sentence,
        "avg_para_sentences": avg_para_sentences,
        "reading_time_min": reading_time_min,
        "h2_count": h2_count,
        "sentence_cv": sentence_cv,
        "has_pattern_interrupt": has_pattern_interrupt,
    }


# ── Formula ────────────────────────────────────────────────────────────────────


def _apply_formula(
    signals: dict[str, Any],
    hook_score: float,
) -> tuple[float, list[ReadRatioFactor]]:
    factors: list[ReadRatioFactor] = []
    total = 0.0

    def _add(name: str, measured: str, deduction: float, guidance: str) -> None:
        nonlocal total
        factors.append(ReadRatioFactor(name=name, measured=measured, deduction=deduction, guidance=guidance))
        total += deduction

    # ── 1. Hook quality (highest leverage — reader decides in < 5 seconds) ────
    if hook_score < 0.30:
        _add("Hook quality", f"{hook_score:.2f}/1.0", 0.16,
             "Sentence 1 sets context instead of hooking. Rewrite it: start with a moment, "
             "a specific number, a failure, or a surprising fact.")
    elif hook_score < 0.55:
        _add("Hook quality", f"{hook_score:.2f}/1.0", 0.09,
             "Hook is weak. Add a specific number, dollar amount, or named detail to sentence 1.")
    elif hook_score < 0.75:
        _add("Hook quality", f"{hook_score:.2f}/1.0", 0.04,
             "Hook is decent. Make sentence 1 more specific to lift it into 0.75+ territory.")

    # ── 2. Intro length ───────────────────────────────────────────────────────
    iw = signals["intro_words"]
    if iw > 150:
        _add("Intro length", f"{iw} words", 0.18,
             f"Intro is {iw} words — cut to under 100. Readers leave before word 120.")
    elif iw > 120:
        _add("Intro length", f"{iw} words", 0.11,
             f"Intro is {iw} words — trim to 60–100. Every word past 100 loses readers.")
    elif iw > 100:
        _add("Intro length", f"{iw} words", 0.05,
             f"Intro is {iw} words — marginal. Trim toward 80 words for best read ratio.")
    elif iw < 40:
        _add("Intro length", f"{iw} words", 0.02,
             "Intro is very brief. Ensure the core insight is clear by word 40.")

    # ── 3. Reading time ───────────────────────────────────────────────────────
    rt = signals["reading_time_min"]
    if rt < 3.0:
        _add("Reading time", f"{rt:.1f} min", 0.13,
             f"Post is only {rt:.1f} min — too short for meaningful Partner Program earnings. "
             "Add 200+ words of specific detail.")
    elif rt < 4.5:
        _add("Reading time", f"{rt:.1f} min", 0.05,
             f"Post is {rt:.1f} min. The 5–7 min range earns the most. Add 200+ words.")
    elif rt > 9.0:
        _add("Reading time", f"{rt:.1f} min", 0.11,
             f"Post is {rt:.1f} min — read ratio drops sharply above 8 min. Cut to ~1,600 words.")
    elif rt > 7.5:
        _add("Reading time", f"{rt:.1f} min", 0.05,
             f"Post is {rt:.1f} min. Trim to 1,400–1,600 words for best read ratio.")

    # ── 4. Paragraph density ──────────────────────────────────────────────────
    aps = signals["avg_para_sentences"]
    if aps > 4.0:
        _add("Paragraph density", f"{aps:.1f} avg sentences/para", 0.10,
             f"Average paragraph has {aps:.1f} sentences — heavy. Break all >3-sentence paragraphs.")
    elif aps > 3.0:
        _add("Paragraph density", f"{aps:.1f} avg sentences/para", 0.05,
             f"Paragraphs average {aps:.1f} sentences. More white space = higher scan-ability.")

    # ── 5. Pattern interrupt ──────────────────────────────────────────────────
    if not signals["has_pattern_interrupt"]:
        _add("Pattern interrupt", "none detected", 0.04,
             "Drop-off peaks at the scroll midpoint. Add a bold one-liner or rhetorical question "
             "in the middle third of the post.")

    # ── 6. Sentence variety ───────────────────────────────────────────────────
    cv = signals["sentence_cv"]
    if cv < 0.25:
        _add("Sentence variety", f"CV={cv:.2f}", 0.04,
             f"Sentence lengths are uniform (CV={cv:.2f}). Mix short punchy lines with longer "
             "analytical sentences — rhythm signals human writing.")

    predicted = round(max(0.20, min(0.95, _BASE_RATIO - total)), 2)
    factors_sorted = sorted(factors, key=lambda f: f.deduction, reverse=True)
    return predicted, factors_sorted


# ── LLM hook scorer ────────────────────────────────────────────────────────────


async def _score_hook(run_id: str, first_sentence: str) -> float:
    """Score ONLY sentence 1 as a hook. Narrow call — one float output."""
    model_name = get_model_name("worker")
    tracker = AgentTokenTracker(
        agent_name="read_ratio_analyzer", run_id=run_id, model=model_name
    )
    llm = get_llm("worker", callbacks=[tracker]).with_structured_output(_HookScore)

    messages = [
        SystemMessage(content=(
            "Score this opening sentence as a Medium article hook from 0.0 to 1.0.\n\n"
            "Scoring rubric:\n"
            "  1.0 — drops reader into a specific moment, number, failure, or surprising fact\n"
            "  0.8 — specific and compelling, but slightly generic\n"
            "  0.6 — specific detail present, but stakes aren't immediately clear\n"
            "  0.4 — mildly interesting, vague, or semi-context-setting\n"
            "  0.2 — pure background or context, no tension or curiosity\n"
            "  0.0 — announces the topic ('In this article...') or introduces the author\n\n"
            "Score ONLY this one sentence. Return score (0.0–1.0) and a one-sentence reason."
        )),
        HumanMessage(content=f'First sentence: "{first_sentence}"'),
    ]

    result: _HookScore | None = await llm.ainvoke(messages)  # type: ignore[assignment]
    if result is None:
        return 0.5
    return result.score


# ── Public entrypoint ──────────────────────────────────────────────────────────


@dataclass
class ReadRatioReport:
    predicted_ratio: float
    hook_score: float
    factors: list[ReadRatioFactor]   # ordered by deduction (highest first)
    improvement_hints: list[str]     # top 3 actionable items
    signals: dict[str, Any]          # raw measurements for logging


async def analyze_read_ratio(
    run_id: str,
    content: str,
) -> ReadRatioReport:
    """
    Compute a transparent, auditable Medium read ratio prediction.

    Returns ReadRatioReport with the full breakdown of every factor
    that contributed to the final number.
    """
    signals = _measure_structure(content)
    hook_score = await _score_hook(run_id, signals["first_sentence"])
    predicted, factors = _apply_formula(signals, hook_score)
    hints = [f.guidance for f in factors[:3]]

    return ReadRatioReport(
        predicted_ratio=predicted,
        hook_score=hook_score,
        factors=factors,
        improvement_hints=hints,
        signals=signals,
    )


def format_breakdown(report: ReadRatioReport) -> str:
    """Return a human-readable breakdown for injection into revision prompts."""
    return format_factors_breakdown(report.predicted_ratio, report.factors)


def format_factors_breakdown(
    predicted_ratio: float,
    factors: "list[ReadRatioFactor]",
) -> str:
    """Build the breakdown string from raw factors — usable without a full ReadRatioReport."""
    if not factors:
        return (
            f"Read ratio: {predicted_ratio:.0%} — no structural issues detected. "
            "Maintain the intro length and paragraph density."
        )
    lines = [f"Predicted read ratio: {predicted_ratio:.0%} (base 82%, deductions below)"]
    for f in factors:
        lines.append(f"  -{f.deduction:.0%} {f.name} [{f.measured}]: {f.guidance}")
    return "\n".join(lines)
