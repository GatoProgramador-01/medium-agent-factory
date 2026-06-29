import pytest
from pydantic import ValidationError

from app.routers.pipeline import PipelineRequest


def test_pipeline_request_accepts_grounding_context() -> None:
    req = PipelineRequest(
        custom_topic="Claude Code master prompt operating system",
        grounding_context="repo metric: 53 tests\nsoft-block: HTTP 200 empty AJAX body",
    )

    assert req.grounding_context.startswith("repo metric")


def test_pipeline_request_rejects_oversized_grounding_context() -> None:
    with pytest.raises(ValidationError):
        PipelineRequest(
            custom_topic="Claude Code master prompt operating system",
            grounding_context="x" * 12001,
        )
