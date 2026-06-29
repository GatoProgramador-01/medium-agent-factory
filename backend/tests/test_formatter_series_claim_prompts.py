from pathlib import Path

BASE = Path(__file__).parent.parent / "prompts"
FMT = (BASE / "formatter_system.txt").read_text(encoding="utf-8")
SER = (BASE / "series_planner_system.txt").read_text(encoding="utf-8")
CLM = (BASE / "claim_extractor_system.txt").read_text(encoding="utf-8")


def test_formatter_has_anti_rewrite_guarantee():
    assert "ANTI-REWRITE" in FMT or "anti-rewrite" in FMT.lower()
    assert "formatter, not an editor" in FMT


def test_formatter_changes_applied_guidance():
    assert "changes_applied" in FMT


def test_series_has_uniqueness_mandate():
    assert "UNIQUENESS" in SER


def test_series_hook_seed_is_specific():
    assert "EXACT opening sentence" in SER or "actual sentence" in SER


def test_claim_extractor_has_exclusion_list():
    assert "WHAT NOT TO EXTRACT" in CLM or "DO NOT extract" in CLM


def test_claim_extractor_first_person_excluded():
    assert "First-person" in CLM or "first-person" in CLM
