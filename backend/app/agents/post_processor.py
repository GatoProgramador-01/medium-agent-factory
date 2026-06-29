"""
post_processor.py — Deterministic post-processing transforms.

These functions run in finalize_node AFTER format_node, before saving the final post.
No LLM calls — pure string manipulation only.
"""

import re


def inject_captions(content: str) -> str:
    """
    Append a generic caption placeholder to any [IMAGE: ...] block that lacks | caption:.
    The caption placeholder is deterministic so the formatter LLM doesn't need to invent one.
    """
    pattern = r"\[IMAGE: ([^\]]*?)\]"

    def _add_caption(m: re.Match) -> str:
        inner = m.group(1)
        if "| caption:" in inner:
            return m.group(0)
        # Keep existing structure, append caption placeholder
        return f"[IMAGE: {inner} | caption: Image source: see References]"

    return re.sub(pattern, _add_caption, content)


def merge_sources_sections(content: str) -> str:
    """
    If both ## Sources and ## References exist, merge into ## Sources.
    Collects all bullet/numbered lines from both sections, deduplicates, keeps one section.
    """
    # Extract sections
    sources_match = re.search(r"## Sources\s*\n((?:[-\d*].*\n?)*)", content)
    refs_match = re.search(r"## References\s*\n((?:[-\d*].*\n?)*)", content)

    if not (sources_match and refs_match):
        return content  # only one or neither — nothing to merge

    # Collect all lines from both, deduplicate preserving order.
    # Normalize each line by stripping bullet/number prefix before dedup comparison
    # so "- https://a.com" and "1. https://a.com" are treated as the same entry.
    all_lines = []
    seen: set[str] = set()
    for match in [sources_match, refs_match]:
        for line in match.group(1).splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            # Normalize: strip leading "- ", "* ", "1. ", "12. " etc.
            # Pattern covers: "- text", "* text", "1. text", "12) text"
            normalized = re.sub(r"^(?:[-*]\s+|\d+[.)]\s*)", "", stripped).strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                all_lines.append(f"- {normalized}")

    merged = "## Sources\n" + "\n".join(all_lines)
    # Remove both original sections
    content = re.sub(r"## Sources\s*\n(?:[-\d*].*\n?)*", "", content)
    content = re.sub(r"## References\s*\n(?:[-\d*].*\n?)*", "", content)
    return content.rstrip() + "\n\n" + merged
