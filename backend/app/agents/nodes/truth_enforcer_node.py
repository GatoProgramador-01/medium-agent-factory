"""
Truth Enforcer — ensures numbers > 10 are attributed to sources or experiments.

The Story (El Relato):
This node enforces epistemic honesty. Every concrete number above 10 must have
a clear attribution anchor — either pointing to an external source (http/https),
a personal measurement ("I tested", "I measured"), or experimental methodology
("in my setup", "my experiment"). This prevents unsourced claims that erode
reader trust.

The Flow (El Flujo):
1. Extract post content and search for numbers > 10.
2. For each number, retrieve its sentence context.
3. Check if the sentence contains an attribution anchor.
4. Collect unattributed numbers and determine pass/fail status.
5. Return structured findings and updated state.
"""

import re
from typing import Any, Dict

from app.agents.nodes._sentence_utils import strip_code_blocks


async def truth_enforcer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Enforces attribution for numbers > 10 in post content.

    Args:
        state: Pipeline state with optional "post" key containing GeneratedPost.

    Returns:
        Dict with unattributed_numbers, truth_enforcer_passed, and updated
        structural_check_issues if issues found.
    """
    post = state.get("post")
    if not post:
        return {}

    content = post.content
    if not content:
        return {
            "unattributed_numbers": [],
            "truth_enforcer_passed": True,
            "completed_steps": ["truth_enforcement"],
        }

    # Strip code blocks from scannable content, but keep full content for sentence context
    scannable_content = strip_code_blocks(content)

    # 1. Extract all numbers > 10 from stripped content
    number_pattern = r"\b(\d+(?:,\d{3})*(?:\.\d+)?)\b"
    matches = re.finditer(number_pattern, scannable_content)

    numbers_with_context = []
    for match in matches:
        try:
            # Remove commas for numeric comparison
            num_str = match.group(1).replace(",", "")
            num_value = float(num_str)
            if num_value > 10:
                sentence = _get_sentence_for_position(content, match.start())
                numbers_with_context.append(
                    {
                        "number": match.group(1),
                        "value": num_value,
                        "sentence": sentence,
                        "position": match.start(),
                    }
                )
        except ValueError:
            continue

    # 2. Check for attribution anchors
    attribution_anchors = [
        "http",
        "https",
        "In my test",
        "I measured",
        "I found",
        "my setup",
        "per my",
        "I ran",
        "I observed",
        "my experiment",
        "I profiled",
    ]

    unattributed_numbers: list[str] = []
    for num_info in numbers_with_context:
        sentence = num_info["sentence"]
        has_anchor = any(anchor.lower() in sentence.lower() for anchor in attribution_anchors)
        if not has_anchor:
            unattributed_numbers.append(num_info["number"])

    # 3. Determine pass/fail
    truth_enforcer_passed = len(unattributed_numbers) == 0

    # 4. Build result
    result = {
        "unattributed_numbers": unattributed_numbers,
        "truth_enforcer_passed": truth_enforcer_passed,
        "completed_steps": ["truth_enforcement"],
    }

    # 5. Update structural issues if not passed
    if not truth_enforcer_passed:
        existing = [
            i
            for i in state.get("structural_check_issues", [])
            if i.get("category") != "unattributed_number"
        ]
        result["structural_check_issues"] = [
            *existing,
            {
                "category": "unattributed_number",
                "severity": "HIGH",
                "suggestion": f"Numbers {', '.join(unattributed_numbers)} lack attribution. Add source URL or measurement context (e.g., 'I measured', 'per my test').",
            },
        ]

    return result


def _get_sentence_for_position(content: str, position: int) -> str:
    """Extract the sentence containing the given position, plus surrounding context.

    Args:
        content: Full content string.
        position: Character position in content.

    Returns:
        The sentence containing the position plus 1 sentence before/after for context.
    """

    def _is_sentence_boundary(text: str, idx: int) -> bool:
        """True only when punctuation is followed by whitespace or end-of-string (not URLs/decimals)."""
        return text[idx] in ".!?" and (idx + 1 >= len(text) or text[idx + 1] in " \n\r\t")

    # Find sentence start (previous . ! or ? followed by whitespace)
    start = position
    for i in range(position - 1, -1, -1):
        if _is_sentence_boundary(content, i):
            start = i + 1
            while start < len(content) and content[start].isspace():
                start += 1
            break
    else:
        start = 0

    # Find sentence end (next . ! or ? followed by whitespace)
    end = position
    for i in range(position, len(content)):
        if _is_sentence_boundary(content, i):
            end = i + 1
            break
    else:
        end = len(content)

    # Expand end to include next sentence for attribution context (e.g., "Check http://...")
    expanded_end = end
    for i in range(end, len(content)):
        if _is_sentence_boundary(content, i):
            expanded_end = i + 1
            break
    else:
        expanded_end = len(content)

    return content[start:expanded_end].strip()
