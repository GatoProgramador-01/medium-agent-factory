from pathlib import Path

BASE = Path(__file__).parent.parent / "prompts"
GEN = (BASE / "content_generator_system.txt").read_text(encoding="utf-8")
REV = (BASE / "content_reviser_system.txt").read_text(encoding="utf-8")

def test_generator_has_structural_plan():
    assert "Step 1:" in GEN and "Step 2:" in GEN

def test_generator_requires_sentence_count_audit():
    initial = (BASE / "content_generator_human_initial.txt").read_text(encoding="utf-8")
    assert "count its sentences" in GEN
    assert "SENTENCE COUNT AUDIT" in initial

def test_generator_has_failure_modes():
    assert "MOST COMMON FAILURE MODES" in GEN

def test_generator_concession_has_placement():
    assert "PLACE IT in section 3" in GEN or "section 3 or 4" in GEN

def test_reviser_has_expansion_math():
    assert "EXPANSION MATH" in REV

def test_reviser_has_regression_check():
    assert "REGRESSION" in REV and "In essence" in REV

def test_reviser_has_structural_math_in_checklist():
    assert "Structural math" in REV
