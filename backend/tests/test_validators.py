"""
Unit tests for the LLM JSON coerce validators in GeneratedPost and _AnalysisOutput.

LLMs regularly emit curly quotes, em-dashes, and ellipsis characters inside
JSON strings, breaking json.loads. These tests verify the normalizer handles
all known failure modes without crashing the pipeline.
"""
import pytest

from app.agents.content_generator import GeneratedPost


def _make_post(**overrides) -> dict:
    base = {
        "title": "Test Title",
        "subtitle": "A subtitle",
        "content": "Content body",
        "tags": ["ai", "writing", "python", "llm", "tools"],
        "image_suggestions": ["photo of a laptop", "team meeting", "coffee cup"],
    }
    return {**base, **overrides}


class TestGeneratedPostCoerce:
    def test_tags_as_list_passes_through(self) -> None:
        post = GeneratedPost(**_make_post(tags=["ai", "llm", "python", "tools", "writing"]))
        assert post.tags == ["ai", "llm", "python", "tools", "writing"]

    def test_tags_as_valid_json_string(self) -> None:
        post = GeneratedPost(**_make_post(tags='["ai", "llm", "python", "tools", "writing"]'))
        assert post.tags == ["ai", "llm", "python", "tools", "writing"]

    def test_tags_with_curly_double_quotes(self) -> None:
        # U+201C = LEFT DOUBLE QUOTATION MARK, U+201D = RIGHT DOUBLE QUOTATION MARK
        lq, rq = chr(0x201C), chr(0x201D)
        curly = f'[{lq}ai{rq}, {lq}llm{rq}, {lq}python{rq}, {lq}tools{rq}, {lq}writing{rq}]'
        post = GeneratedPost(**_make_post(tags=curly))
        expected = ['ai', 'llm', 'python', 'tools', 'writing']
        assert post.tags == expected

    def test_tags_with_em_dash_falls_back_to_empty(self) -> None:
        # Truly unparseable JSON → returns [] gracefully instead of crashing
        bad = "[—completely broken json—]"
        post = GeneratedPost(**_make_post(tags=bad))
        assert post.tags == []

    def test_image_suggestions_as_json_string(self) -> None:
        json_str = '["laptop photo", "team meeting", "coffee cup"]'
        post = GeneratedPost(**_make_post(image_suggestions=json_str))
        assert len(post.image_suggestions) == 3

    def test_image_suggestions_with_curly_double_quotes(self) -> None:
        # LLMs use curly double quotes as string delimiters — normalizer fixes these
        lq, rq = chr(0x201C), chr(0x201D)
        curly = f'[{lq}laptop photo{rq}, {lq}team meeting{rq}, {lq}coffee{rq}]'
        post = GeneratedPost(**_make_post(image_suggestions=curly))
        assert len(post.image_suggestions) == 3

    def test_image_suggestions_single_quoted_falls_back_gracefully(self) -> None:
        # Single-quoted arrays can't become valid JSON (JSON requires double quotes).
        # Verifies the validator returns [] rather than crashing.
        lq, rq = chr(0x2018), chr(0x2019)
        curly = f"[{lq}laptop photo{rq}, {lq}team meeting{rq}, {lq}coffee{rq}]"
        post = GeneratedPost(**_make_post(image_suggestions=curly))
        assert post.image_suggestions == []

    def test_non_string_value_passes_through_unchanged(self) -> None:
        tags = ["ai", "writing", "python", "tools", "llm"]
        post = GeneratedPost(**_make_post(tags=tags))
        assert post.tags is tags or post.tags == tags


class TestPickRole:
    def test_initial_draft_uses_worker(self) -> None:
        from app.agents.content_generator import _pick_role
        assert _pick_role(0) == "worker"

    def test_first_revision_uses_worker(self) -> None:
        from app.agents.content_generator import _pick_role
        assert _pick_role(1) == "worker"

    def test_second_revision_escalates_to_supervisor(self) -> None:
        from app.agents.content_generator import _pick_role
        assert _pick_role(2) == "supervisor"

    def test_any_revision_above_two_stays_supervisor(self) -> None:
        from app.agents.content_generator import _pick_role
        assert _pick_role(3) == "supervisor"
        assert _pick_role(10) == "supervisor"
