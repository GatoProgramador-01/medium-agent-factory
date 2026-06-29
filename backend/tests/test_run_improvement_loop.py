from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_prompt_files_loadable():
    from run_improvement_loop import _load_prompt_files

    files = _load_prompt_files()
    assert len(files) >= 4
    assert "content_generator_system.txt" in files
    assert len(files["content_generator_system.txt"]) > 100


def test_render_markdown_structure():
    from run_improvement_loop import _render_markdown
    from app.agents.prompt_analyst import PromptAnalysisReport, PromptSuggestion

    report = PromptAnalysisReport(
        run_count=10,
        top_issue="paragraph_length",
        regression_rate=0.20,
        suggestions=[
            PromptSuggestion(
                file="f.txt",
                section="s",
                issue="i",
                current_behavior="b",
                suggested_change="c",
                priority=1,
            )
        ],
        summary="Test summary.",
    )
    md = _render_markdown(report, {"word_count": {"avg": 1200, "pct_under_1300": 60.0}})
    assert "# Prompt Improvement Report" in md
    assert "P1" in md
    assert "f.txt" in md
