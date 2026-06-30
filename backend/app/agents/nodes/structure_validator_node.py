"""
Structure Validator Node — checks structural completeness of a markdown post.

The Story (El Relato):
A technically correct article can still fail readers if it lacks navigational
scaffolding. This node audits four structural signals: heading density (reader
orientation), presence of lists (scannability), paragraph length calibration
(reading flow), and a conclusion signal (closure). Together they produce a
0–1 score that answers: "Is this post built like a well-structured article?"

The Flow (El Flujo):
1. Extract post content (full markdown — no code stripping; headings and lists
   are markdown constructs we want to detect).
2. Count H1/H2/H3 headings via regex.
3. Detect any bulleted or numbered lists.
4. Compute average paragraph length by splitting on double-newlines.
5. Check whether the last 400 characters contain a conclusion signal phrase.
6. Combine into a 0–1 score: heading_score + list_score + conclusion_score + para_score.
7. Replace (not accumulate) the poor_structure issue slot in structural_check_issues.
"""

import re
import statistics
from typing import Any, Dict

_HEADING_PATTERN = re.compile(r"^#{1,3} \w", re.MULTILINE)
_BULLET_LIST_PATTERN = re.compile(r"^[\-\*\+] \w", re.MULTILINE)
_NUMBERED_LIST_PATTERN = re.compile(r"^\d+\. \w", re.MULTILINE)

_CONCLUSION_SIGNALS = [
    "in summary",
    "in conclusion",
    "key takeaway",
    "remember",
    "final thought",
    "to summarize",
    "bottom line",
    "in short",
    "takeaway",
    "conclusion",
]


async def structure_validator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Checks structural completeness of a markdown post (no LLM calls).

    Args:
        state: Pipeline state with optional "post" key containing GeneratedPost.

    Returns:
        Dict with structure_score, structure_passed, structure_metrics,
        completed_steps, and optionally updated structural_check_issues.
    """
    post = state.get("post")
    if not post:
        return {}

    content = post.content
    if not content:
        return {
            "structure_score": 0.0,
            "structure_passed": False,
            "structure_metrics": {
                "heading_count": 0,
                "avg_paragraph_length": 0.0,
                "has_lists": False,
                "has_conclusion_signals": False,
            },
            "completed_steps": ["structure_validation"],
        }

    # 1. Heading count (H1/H2/H3 only)
    heading_count = len(_HEADING_PATTERN.findall(content))

    # 2. List detection (bullet or numbered)
    has_lists = bool(_BULLET_LIST_PATTERN.search(content) or _NUMBERED_LIST_PATTERN.search(content))

    # 3. Average paragraph length (split on double newlines — Unix, Windows, trailing-space blanks)
    paragraphs = [p.strip() for p in re.split(r"\r?\n[ \t]*\r?\n", content.strip()) if p.strip()]
    if paragraphs:
        para_word_counts = [len(p.split()) for p in paragraphs]
        avg_paragraph_length = statistics.mean(para_word_counts)
    else:
        avg_paragraph_length = 0.0

    # 4. Conclusion signal — last 400 chars OR last 20%, whichever window is larger
    cutoff = max(0, len(content) - max(400, len(content) // 5))
    tail = content[cutoff:].lower()
    has_conclusion_signals = any(signal in tail for signal in _CONCLUSION_SIGNALS)

    # 5. Scoring
    heading_score = min(0.30, (heading_count / 4.0) * 0.30)
    list_score = 0.20 if has_lists else 0.0
    conclusion_score = 0.25 if has_conclusion_signals else 0.0

    if avg_paragraph_length == 0:
        para_score = 0.0
    elif avg_paragraph_length < 20:
        para_score = (avg_paragraph_length / 20.0) * 0.25
    elif avg_paragraph_length <= 120:
        para_score = 0.25
    else:
        para_score = max(0.0, 0.25 - ((avg_paragraph_length - 120) / 400.0) * 0.25)

    structure_score = round(
        min(1.0, heading_score + list_score + conclusion_score + para_score),
        3,
    )

    structure_passed = structure_score >= 0.50

    result: Dict[str, Any] = {
        "structure_score": structure_score,
        "structure_passed": structure_passed,
        "structure_metrics": {
            "heading_count": heading_count,
            "avg_paragraph_length": round(avg_paragraph_length, 2),
            "has_lists": has_lists,
            "has_conclusion_signals": has_conclusion_signals,
        },
        "completed_steps": ["structure_validation"],
    }

    # 6. Replace-not-accumulate the poor_structure slot
    if not structure_passed:
        headings_needed = max(0, 4 - heading_count)
        if has_lists:
            list_hint = "."
        else:
            list_hint = ", add bullet lists for scannable content."
        conclusion_hint = " Add a conclusion paragraph." if not has_conclusion_signals else ""

        existing = [
            i
            for i in state.get("structural_check_issues", [])
            if i.get("category") != "poor_structure"
        ]
        result["structural_check_issues"] = [
            *existing,
            {
                "category": "poor_structure",
                "severity": "MEDIUM",
                "suggestion": (
                    f"Structure score {structure_score:.2f} below 0.50. "
                    f"Add {headings_needed} more H2/H3 headings{list_hint}"
                    f"{conclusion_hint}"
                ),
            },
        ]

    return result
