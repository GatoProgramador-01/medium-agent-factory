"""
Structural quality checks — pure Python, zero LLM calls.

Detects paragraph_length, heading_cadence, intro_length, word_count,
ai_pattern (forbidden phrases), and image_missing with exact measurements.
All category names are canonical snake_case.
"""

import re

from app.models.post import QualityIssue

_FORBIDDEN_PHRASES: list[str] = [
    "Moreover",
    "Furthermore",
    "Additionally",
    "In conclusion",
    "Let's dive in",
    "delve",
    "tapestry",
    "game-changer",
    "cutting-edge",
    "transformative",
    "serves as a",
    "unlock the",
    "in the realm of",
    "perhaps",
    "it could be argued",
    "many people",
]

def _count_sentences(text: str) -> int:
    """Count full sentences (≥3 words) to avoid treating emphasis fragments as sentences."""
    text = text.strip()
    if not text:
        return 0
    units = re.split(r"(?<=[.!?])\s+", text)
    return sum(1 for u in units if len(u.split()) >= 3)


def _paragraphs(content: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]


def _strip_markdown(text: str) -> str:
    text = re.sub(r"^#{1,6}\s.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^---+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[IMAGE:.*?\]", "", text, flags=re.IGNORECASE)
    return text


def _check_paragraph_length(content: str) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for para in _paragraphs(content):
        if para.startswith("#") or re.match(r"^-{3,}$", para):
            continue
        if re.match(r"^\[IMAGE:", para, re.IGNORECASE):
            continue
        count = _count_sentences(para)
        if count > 4:
            preview = para[:80].rstrip() + ("…" if len(para) > 80 else "")
            issues.append(
                QualityIssue(
                    category="paragraph_length",
                    severity="HIGH",
                    location=preview,
                    suggestion=(
                        f"Paragraph has {count} sentences (max 4). "
                        "Split at a natural break."
                    ),
                )
            )
    return issues


def _split_into_sections(content: str) -> list[tuple[str, str]]:
    """Return list of (heading_text, section_body) pairs, including a None heading for pre-first-heading text."""
    parts: list[tuple[str, str]] = []
    heading_re = re.compile(r"^(#{1,6}\s.+)$", re.MULTILINE)
    positions = [(m.start(), m.group(1)) for m in heading_re.finditer(content)]
    if not positions:
        return [("", content)]
    if positions[0][0] > 0:
        parts.append(("", content[: positions[0][0]]))
    for idx, (pos, heading) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(content)
        body = content[pos + len(heading) : end]
        parts.append((heading, body))
    return parts


def _word_count_text(text: str) -> int:
    clean = _strip_markdown(text)
    return len(clean.split())


def _check_heading_cadence(content: str) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    h2_re = re.compile(r"^#{2}\s.+$", re.MULTILINE)
    h2_matches = list(h2_re.finditer(content))
    if len(h2_matches) < 2:
        return issues
    for i in range(len(h2_matches) - 1):
        h_start = h2_matches[i].end()
        h_end = h2_matches[i + 1].start()
        between_text = content[h_start:h_end]
        word_gap = len(_strip_markdown(between_text).split())
        h_a = h2_matches[i].group(0).strip()
        h_b = h2_matches[i + 1].group(0).strip()
        location = f"{h_a!r} → {h_b!r}"
        if word_gap > 500:
            issues.append(
                QualityIssue(
                    category="heading_cadence",
                    severity="HIGH",
                    location=location,
                    suggestion=(
                        f"Gap between headings is {word_gap} words (max 500). "
                        "Insert a new H2 to break it up."
                    ),
                )
            )
        elif word_gap < 200:
            issues.append(
                QualityIssue(
                    category="heading_cadence",
                    severity="LOW",
                    location=location,
                    suggestion=(
                        f"Gap between headings is only {word_gap} words (min 200). "
                        "Merge with adjacent section or expand content."
                    ),
                )
            )
    return issues


def _intro_text(content: str) -> str:
    if "---" in content:
        return content.split("---")[0]
    h2_match = re.search(r"^#{2}\s", content, re.MULTILINE)
    if h2_match:
        return content[: h2_match.start()]
    return content[:500]


def _check_intro_length(content: str) -> list[QualityIssue]:
    intro = _intro_text(content)
    wc = len(intro.split())
    if wc > 110:
        return [
            QualityIssue(
                category="intro_length",
                severity="HIGH",
                location=f"Intro is {wc} words",
                suggestion=(
                    f"Intro has {wc} words (max 110). "
                    "Cut from the end — never from the hook."
                ),
            )
        ]
    return []


def _check_word_count(content: str) -> list[QualityIssue]:
    wc = len(_strip_markdown(content).split())
    if wc < 1000:
        return [
            QualityIssue(
                category="word_count",
                severity="HIGH",
                location=f"Total word count: {wc}",
                suggestion=f"Post is only {wc} words. Minimum is 1,300.",
            )
        ]
    if wc < 1300:
        return [
            QualityIssue(
                category="word_count",
                severity="LOW",
                location=f"Total word count: {wc}",
                suggestion=f"Post is {wc} words — below the 1,300-word target.",
            )
        ]
    return []


def _check_forbidden_phrases(content: str) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for phrase in _FORBIDDEN_PHRASES:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        if pattern.search(content):
            issues.append(
                QualityIssue(
                    category="ai_pattern",
                    severity="HIGH",
                    location=f'Found: "{phrase}"',
                    suggestion=f'Remove AI phrase "{phrase}" — rewrite the sentence.',
                )
            )
    return issues


def _check_image_missing(content: str) -> list[QualityIssue]:
    wc = len(_strip_markdown(content).split())
    if wc < 1300:
        return []
    image_count = len(re.findall(r"\[IMAGE:", content, re.IGNORECASE))
    if image_count < 2:
        return [
            QualityIssue(
                category="image_missing",
                severity="HIGH",
                location=f"Images found: {image_count}",
                suggestion=(
                    "Posts over 1,300 words need at least 2 "
                    "[IMAGE: description | alt: alt text] placeholders."
                ),
            )
        ]
    return []


def run_structural_checks(content: str) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    issues.extend(_check_paragraph_length(content))
    issues.extend(_check_heading_cadence(content))
    issues.extend(_check_intro_length(content))
    issues.extend(_check_word_count(content))
    issues.extend(_check_forbidden_phrases(content))
    issues.extend(_check_image_missing(content))
    return issues
