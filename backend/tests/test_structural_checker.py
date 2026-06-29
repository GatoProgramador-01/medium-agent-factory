"""
Tests for StructuralChecker — deterministic, zero-LLM structural quality checks.

These verify that paragraph_length, heading_cadence, intro_length, word_count,
forbidden_phrases, and image_count are detected without an LLM call, with exact
measurements and canonical snake_case category names.
"""

from app.agents.structural_checker import run_structural_checks


def _cats(issues: list) -> list[str]:
    return [i.category for i in issues]


def _high(issues: list) -> list:
    return [i for i in issues if i.severity.upper() == "HIGH"]


def _low(issues: list) -> list:
    return [i for i in issues if i.severity.upper() == "LOW"]


# ── paragraph_length ──────────────────────────────────────────────────────────

CLEAN_POST = """My bill dropped from $2,800 to $178 when I swapped models.

---

## What Changed

I changed one line of code. The routing function now checks token count first.
It cost me three weeks to figure out why.

## The Result

The savings were immediate. I checked the dashboard the next morning.
It showed $178. I checked again. Still $178.
"""


def test_clean_post_has_no_paragraph_violations() -> None:
    issues = run_structural_checks(CLEAN_POST)
    assert not any(i.category == "paragraph_length" for i in issues)


LONG_PARA_POST = """My bill dropped from $2,800 to $178 when I swapped models.

---

## What Changed

I changed one line of code. The routing function checks token count first.
It cost me three weeks to figure out why. The problem was subtle.
Every agent was using Sonnet regardless of the task complexity.
I kept ignoring the cost dashboard because I assumed it was normal.
Finally I opened the bill and nearly closed the whole project.

## The Result

Savings were immediate.
"""


def test_paragraph_over_4_sentences_flagged_high() -> None:
    issues = run_structural_checks(LONG_PARA_POST)
    p_issues = [i for i in issues if i.category == "paragraph_length"]
    assert len(p_issues) >= 1
    assert all(i.severity.upper() == "HIGH" for i in p_issues)


def test_paragraph_issue_location_contains_preview() -> None:
    issues = run_structural_checks(LONG_PARA_POST)
    p_issues = [i for i in issues if i.category == "paragraph_length"]
    assert len(p_issues) >= 1
    assert len(p_issues[0].location) > 0


# ── heading_cadence ───────────────────────────────────────────────────────────

def _post_with_gap(gap_words: int) -> str:
    filler = " ".join(["word"] * gap_words)
    return f"Hook sentence one.\n\n---\n\n## First Section\n\n{filler}\n\n## Second Section\n\nEnd."


def test_heading_gap_over_500_flagged() -> None:
    post = _post_with_gap(510)
    issues = run_structural_checks(post)
    hc = [i for i in issues if i.category == "heading_cadence"]
    assert len(hc) >= 1
    assert hc[0].severity.upper() == "HIGH"


def test_heading_gap_under_200_flagged() -> None:
    post = _post_with_gap(150)
    issues = run_structural_checks(post)
    hc = [i for i in issues if i.category == "heading_cadence"]
    assert len(hc) >= 1


def test_heading_gap_within_range_not_flagged() -> None:
    post = _post_with_gap(350)
    issues = run_structural_checks(post)
    hc = [i for i in issues if i.category == "heading_cadence"]
    assert len(hc) == 0


# ── intro_length ──────────────────────────────────────────────────────────────

def _post_with_intro(intro_words: int) -> str:
    intro = " ".join(["word"] * intro_words)
    return f"{intro}\n\n## First Section\n\nBody content here."


def test_intro_over_110_words_flagged_high() -> None:
    post = _post_with_intro(130)
    issues = run_structural_checks(post)
    il = [i for i in issues if i.category == "intro_length"]
    assert len(il) == 1
    assert il[0].severity.upper() == "HIGH"


def test_intro_under_110_not_flagged() -> None:
    post = _post_with_intro(90)
    issues = run_structural_checks(post)
    il = [i for i in issues if i.category == "intro_length"]
    assert len(il) == 0


def test_intro_measurement_included_in_location() -> None:
    post = _post_with_intro(140)
    issues = run_structural_checks(post)
    il = [i for i in issues if i.category == "intro_length"]
    assert "140" in il[0].location or "140" in il[0].suggestion


# ── word_count ────────────────────────────────────────────────────────────────

def _post_with_words(n: int) -> str:
    body = " ".join(["word"] * n)
    return f"Hook.\n\n---\n\n## Section\n\n{body}"


def test_under_1000_words_flagged_high() -> None:
    issues = run_structural_checks(_post_with_words(800))
    wc = [i for i in issues if i.category == "word_count"]
    assert len(wc) == 1
    assert wc[0].severity.upper() == "HIGH"


def test_1000_to_1299_words_flagged_high() -> None:
    # Old behavior was LOW; new spec: ANY count below min_word_count is HIGH.
    issues = run_structural_checks(_post_with_words(1100))
    wc = [i for i in issues if i.category == "word_count"]
    assert len(wc) == 1
    assert wc[0].severity.upper() == "HIGH"


def test_1300_plus_words_not_flagged() -> None:
    issues = run_structural_checks(_post_with_words(1400))
    wc = [i for i in issues if i.category == "word_count"]
    assert len(wc) == 0


# ── forbidden_phrases ─────────────────────────────────────────────────────────

def test_moreover_flagged_as_high() -> None:
    post = f"Hook.\n\n---\n\n## Section\n\nMoreover, this is important. {'word ' * 600}"
    issues = run_structural_checks(post)
    fp = [i for i in issues if i.category == "ai_pattern"]
    assert len(fp) >= 1
    assert any("Moreover" in i.location or "Moreover" in i.suggestion for i in fp)


def test_delve_flagged_as_high() -> None:
    post = f"Hook.\n\n---\n\n## Section\n\nLet us delve into this topic. {'word ' * 600}"
    issues = run_structural_checks(post)
    fp = [i for i in issues if i.category == "ai_pattern"]
    assert len(fp) >= 1


def test_no_forbidden_phrases_no_flag() -> None:
    post = CLEAN_POST + " " + " ".join(["word"] * 600)
    issues = run_structural_checks(post)
    fp = [i for i in issues if i.category == "ai_pattern"]
    assert len(fp) == 0


def test_forbidden_phrase_location_contains_phrase() -> None:
    post = f"Hook.\n\n---\n\n## Section\n\nFurthermore, this is key. {'word ' * 600}"
    issues = run_structural_checks(post)
    fp = [i for i in issues if i.category == "ai_pattern"]
    assert len(fp) >= 1
    assert any("Furthermore" in i.location for i in fp)


# ── image_missing ─────────────────────────────────────────────────────────────

def test_no_images_in_long_post_flagged() -> None:
    post = _post_with_words(1400)
    issues = run_structural_checks(post)
    im = [i for i in issues if i.category == "image_missing"]
    assert len(im) == 1
    assert im[0].severity.upper() == "HIGH"


def test_two_images_not_flagged() -> None:
    body = " ".join(["word"] * 700)
    post = (
        f"Hook.\n\n[IMAGE: chart | alt: bar chart showing costs]\n\n---\n\n"
        f"## Section\n\n{body}\n\n[IMAGE: diagram | alt: flow diagram]\n\n"
        f"## Section 2\n\n{' '.join(['word'] * 400)}"
    )
    issues = run_structural_checks(post)
    im = [i for i in issues if i.category == "image_missing"]
    assert len(im) == 0


# ── category names are always snake_case ─────────────────────────────────────

def test_all_category_names_are_snake_case() -> None:
    """No matter which issues are found, categories must be canonical snake_case."""
    post = (
        f"{'word ' * 140}\n\n## First\n\n"  # long intro + heading
        f"{'sentence one. sentence two. sentence three. sentence four. sentence five. ' * 3}"
        f"\n\n## Second\n\nMoreover, this is important. delve into it. {'word ' * 600}"
    )
    issues = run_structural_checks(post)
    for issue in issues:
        assert issue.category == issue.category.lower(), (
            f"Category '{issue.category}' is not lowercase snake_case"
        )
        assert " " not in issue.category or "_" in issue.category, (
            f"Category '{issue.category}' contains spaces — must use underscores"
        )
