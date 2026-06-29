from pathlib import Path

BASE = Path(__file__).parent.parent / "prompts"
INIT = (BASE / "content_generator_human_initial.txt").read_text(encoding="utf-8")
REV = (BASE / "content_generator_human_revision.txt").read_text(encoding="utf-8")


def test_initial_has_structural_plan_check():
    assert "STRUCTURAL PLAN" in INIT


def test_initial_has_citations_check():
    assert "INLINE CITATIONS" in INIT or "CITATIONS" in INIT


def test_initial_has_exemplar_guidance():
    assert "exemplar" in INIT.lower() and ("Study" in INIT or "blueprint" in INIT)


def test_revision_has_expansion_math():
    assert "EXPANSION MATH" in REV


def test_revision_has_expansion_math_checkbox():
    assert "Expansion math" in REV or "expansion math" in REV
