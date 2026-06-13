"""
Unit tests for FormatterAgent — pure functions only, no LLM calls.
"""

from app.agents.formatter import detect_long_paragraphs


class TestDetectLongParagraphs:
    def test_short_paragraph_not_flagged(self) -> None:
        content = "First sentence. Second sentence. Third sentence."
        assert detect_long_paragraphs(content) == []

    def test_exactly_four_sentences_not_flagged(self) -> None:
        content = "One. Two. Three. Four."
        assert detect_long_paragraphs(content) == []

    def test_five_sentences_flagged(self) -> None:
        content = "One. Two. Three. Four. Five."
        result = detect_long_paragraphs(content)
        assert len(result) == 1
        assert "Five." in result[0]

    def test_heading_paragraphs_skipped(self) -> None:
        content = "## This is a heading with. Multiple. Fake. Sentence. Dots."
        assert detect_long_paragraphs(content) == []

    def test_image_placeholders_skipped(self) -> None:
        content = "[IMAGE: a photo | alt: description] with. Some. Extra. Sentence. Dots."
        assert detect_long_paragraphs(content) == []

    def test_separator_lines_skipped(self) -> None:
        content = "---"
        assert detect_long_paragraphs(content) == []

    def test_multiple_paragraphs_only_long_ones_returned(self) -> None:
        short = "Short paragraph. Only two sentences."
        long = "A. B. C. D. E. Five sentences here."
        content = f"{short}\n\n{long}"
        result = detect_long_paragraphs(content)
        assert len(result) == 1
        assert long in result

    def test_multiple_long_paragraphs_all_returned(self) -> None:
        p1 = "One. Two. Three. Four. Five."
        p2 = "A. B. C. D. E. F."
        p3 = "Short. Only two."
        content = f"{p1}\n\n{p3}\n\n{p2}"
        result = detect_long_paragraphs(content)
        assert len(result) == 2
        assert p1 in result
        assert p2 in result

    def test_custom_max_sentences(self) -> None:
        content = "One. Two. Three."
        assert detect_long_paragraphs(content, max_sentences=2) == [content]
        assert detect_long_paragraphs(content, max_sentences=3) == []

    def test_empty_content(self) -> None:
        assert detect_long_paragraphs("") == []

    def test_exclamation_and_question_marks_count_as_sentence_ends(self) -> None:
        content = "Really? Yes! Absolutely. Confirmed. Five sentences total."
        result = detect_long_paragraphs(content)
        assert len(result) == 1
