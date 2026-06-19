"""Unit tests for PostDocument model."""

from app.models.post import PostDocument, PostStatus


class TestPostDocumentToDoc:
    def _make_post(self, content: str = "Hello world this is a test") -> PostDocument:
        return PostDocument(
            run_id="test-run",
            topic="AI",
            trend_context="trending",
            title="Test Post",
            content=content,
            tags=["ai"],
            status=PostStatus.DRAFT,
        )

    def test_to_doc_includes_word_count(self) -> None:
        post = self._make_post("one two three four five")
        doc = post.to_doc()
        assert "word_count" in doc
        assert doc["word_count"] == 5

    def test_to_doc_word_count_matches_content(self) -> None:
        content = "word " * 1800
        post = self._make_post(content.strip())
        doc = post.to_doc()
        assert doc["word_count"] == 1800

    def test_to_doc_word_count_empty_content(self) -> None:
        post = self._make_post("")
        doc = post.to_doc()
        assert doc["word_count"] == 0
