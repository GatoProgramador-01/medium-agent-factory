from app.agents.content_generator import GeneratedPost


class TestGeneratedPostSchema:
    def test_content_field_description_contains_alt_format(self):
        field_info = GeneratedPost.model_fields["content"]
        desc = field_info.description or ""
        assert "| alt:" in desc, f"content field description should reference | alt: format, got: {desc}"
