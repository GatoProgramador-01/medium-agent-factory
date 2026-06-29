from pathlib import Path

PROMPT = (
    Path(__file__).parent.parent / "prompts" / "quality_analyzer_system.txt"
).read_text(encoding="utf-8")


def test_structural_prohibition_present():
    assert "STRUCTURAL METRICS" in PROMPT
    assert "word_count" in PROMPT
    assert "DO NOT REPORT" in PROMPT or "DO NOT report" in PROMPT


def test_chain_of_thought_present():
    assert "CHAIN OF THOUGHT" in PROMPT or "SCORING DISCIPLINE" in PROMPT
    assert "EVIDENCE" in PROMPT


def test_scoring_anchors_present():
    assert "Anchor:" in PROMPT


def test_structural_prohibition_before_rubric():
    struct_pos = PROMPT.find("STRUCTURAL METRICS")
    rubric_pos = PROMPT.find("CONTENT QUALITY RUBRIC")
    assert (
        struct_pos < rubric_pos
    ), "Structural prohibition must appear before the rubric"
