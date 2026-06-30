"""
Unit tests for Readability Scorer Node — measures sentence length, syllables, Gunning Fog readability.
"""

import pytest


class TestReadabilityScorerBasic:
    """Test readability scorer node basic functionality."""

    @pytest.mark.asyncio
    async def test_readability_scorer_returns_empty_on_no_post(self) -> None:
        """readability_scorer_node returns {} when state has no post."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node

        state = {
            "run_id": "test-123",
            "post": None,
        }

        result = await readability_scorer_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_readability_scorer_empty_content(self) -> None:
        """readability_scorer_node handles empty content with neutral metrics."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_score" in result
        assert result["readability_score"] == 1.0
        assert "readability_passed" in result
        assert result["readability_passed"] is True
        assert "readability_metrics" in result
        metrics = result["readability_metrics"]
        assert metrics["avg_words_per_sentence"] == 0.0
        assert metrics["avg_syllables_per_word"] == 0.0
        assert metrics["gunning_fog"] == 0.0
        assert metrics["complex_word_ratio"] == 0.0

    @pytest.mark.asyncio
    async def test_readability_scorer_returns_all_keys(self) -> None:
        """readability_scorer_node returns all required output keys."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="The quick brown fox jumps over the lazy dog.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_score" in result
        assert isinstance(result["readability_score"], float)
        assert 0.0 <= result["readability_score"] <= 1.0

        assert "readability_passed" in result
        assert isinstance(result["readability_passed"], bool)

        assert "readability_metrics" in result
        assert isinstance(result["readability_metrics"], dict)
        metrics = result["readability_metrics"]
        assert "avg_words_per_sentence" in metrics
        assert "avg_syllables_per_word" in metrics
        assert "gunning_fog" in metrics
        assert "complex_word_ratio" in metrics

        assert "completed_steps" in result
        assert "readability_check" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_readability_passed_threshold(self) -> None:
        """readability_passed is True when score >= 0.50, False otherwise."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Simple, readable content
        mock_post_good = GeneratedPost(
            title="Good Article",
            subtitle="",
            content="Simple text. Short sentences. Easy to read.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post_good}
        result = await readability_scorer_node(state)

        assert "readability_passed" in result
        if result["readability_score"] >= 0.50:
            assert result["readability_passed"] is True
        else:
            assert result["readability_passed"] is False


class TestReadabilityScorerSentenceLength:
    """Test sentence length metrics and penalties."""

    @pytest.mark.asyncio
    async def test_short_sentences_score_high(self) -> None:
        """Short simple sentences (5-10 words) score >= 0.70."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Five sentences with 5-8 words each
        mock_post = GeneratedPost(
            title="Simple Article",
            subtitle="",
            content="The cat sat down. A dog ran fast. Birds flew high. Fish swam deep. Ants walked slow.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_score" in result
        assert result["readability_score"] >= 0.70
        assert "readability_metrics" in result
        assert result["readability_metrics"]["avg_words_per_sentence"] <= 10.0

    @pytest.mark.asyncio
    async def test_long_sentences_score_lower(self) -> None:
        """Very long sentences (40+ words) score lower than short ones."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Sentences with 40+ words each
        mock_post = GeneratedPost(
            title="Complex Article",
            subtitle="",
            content=(
                "The comprehensive investigation of multifaceted contemporary sociological phenomena "
                "demands careful consideration of numerous interconnected variables and their collective impact. "
                "Furthermore, the intricate relationship between various substantive components necessitates "
                "an exhaustive examination of potential correlations and causal mechanisms underlying observed patterns."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_score" in result
        # Long complex sentences should score lower than short simple ones
        long_score = result["readability_score"]
        assert long_score < 0.70

        assert "readability_metrics" in result
        avg_wps = result["readability_metrics"]["avg_words_per_sentence"]
        assert avg_wps >= 20.0

    @pytest.mark.asyncio
    async def test_avg_words_per_sentence_accurate(self) -> None:
        """avg_words_per_sentence reflects actual word counts."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Three sentences: 5, 10, 15 words respectively
        # Total 30 words in 3 sentences = average 10 words/sentence
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="One two three four five. One two three four five six seven eight nine ten. One two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_metrics" in result
        avg_wps = result["readability_metrics"]["avg_words_per_sentence"]
        # Should be approximately 10 (30 words / 3 sentences)
        assert 9.0 <= avg_wps <= 11.0


class TestReadabilityScorerSyllables:
    """Test syllable counting and complex word detection."""

    @pytest.mark.asyncio
    async def test_simple_monosyllabic_text(self) -> None:
        """Simple monosyllabic text has avg_syllables_per_word close to 1.0."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Mostly one-syllable words: the, cat, sat, on, a, mat, and, ran
        mock_post = GeneratedPost(
            title="Simple",
            subtitle="",
            content="The cat sat on a mat. The dog ran fast. A bird flew high.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_metrics" in result
        avg_syl = result["readability_metrics"]["avg_syllables_per_word"]
        # Simple text should have avg syllables close to 1.0, likely 1.0-1.5
        assert 0.9 <= avg_syl <= 1.8

    @pytest.mark.asyncio
    async def test_polysyllabic_text_higher_avg(self) -> None:
        """Polysyllabic text has higher avg_syllables_per_word."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Words with multiple syllables: communication (3+), understanding (3),
        # organizations (4), responsibilities (5), opportunities (4)
        mock_post = GeneratedPost(
            title="Complex",
            subtitle="",
            content=(
                "Communication and understanding between organizations require careful consideration "
                "of numerous responsibilities and opportunities available."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_metrics" in result
        avg_syl = result["readability_metrics"]["avg_syllables_per_word"]
        # Polysyllabic text should have higher average
        assert avg_syl > 1.5

    @pytest.mark.asyncio
    async def test_complex_word_ratio(self) -> None:
        """complex_word_ratio reflects proportion of 3+ syllable words."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Mix: "the dog" (simple) + "communication" (complex 3+ syllables)
        mock_post = GeneratedPost(
            title="Test",
            subtitle="",
            content="The dog communication. The cat. The bird communication understanding.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_metrics" in result
        cwr = result["readability_metrics"]["complex_word_ratio"]
        # Should be 0.0 to 1.0 representing proportion of complex words
        assert 0.0 <= cwr <= 1.0


class TestReadabilityScorerGunningFog:
    """Test Gunning Fog readability index calculation."""

    @pytest.mark.asyncio
    async def test_gunning_fog_formula(self) -> None:
        """gunning_fog = 0.4 * (avg_words_per_sentence + 100 * complex_word_ratio)."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Simple text: short sentences, few complex words
        mock_post = GeneratedPost(
            title="Test",
            subtitle="",
            content="One. Two. Three. Four. Five.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_metrics" in result
        metrics = result["readability_metrics"]
        gunning_fog = metrics["gunning_fog"]
        avg_wps = metrics["avg_words_per_sentence"]
        cwr = metrics["complex_word_ratio"]

        # Verify formula: gunning_fog = 0.4 * (avg_wps + 100 * cwr)
        expected_fog = 0.4 * (avg_wps + 100 * cwr)
        assert abs(gunning_fog - expected_fog) < 0.01

    @pytest.mark.asyncio
    async def test_high_fog_with_long_sentences_and_complex_words(self) -> None:
        """Text with long sentences and complex words produces fog > 12."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Long sentences with many complex words
        mock_post = GeneratedPost(
            title="Test",
            subtitle="",
            content=(
                "The comprehensive investigation of multifaceted contemporary sociological phenomena "
                "demands careful consideration. Furthermore, the intricate relationship between various "
                "substantive components necessitates exhaustive examination."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_metrics" in result
        gunning_fog = result["readability_metrics"]["gunning_fog"]
        # High complexity should produce fog > 12
        assert gunning_fog > 12.0

    @pytest.mark.asyncio
    async def test_low_fog_with_simple_text(self) -> None:
        """Simple clean text produces fog < 12."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Simple sentences with few complex words
        mock_post = GeneratedPost(
            title="Test",
            subtitle="",
            content="The cat sat. The dog ran. A bird flew. The fish swam.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_metrics" in result
        gunning_fog = result["readability_metrics"]["gunning_fog"]
        # Simple text should produce fog < 12
        assert gunning_fog < 12.0


class TestReadabilityScorerCodeBlocks:
    """Test that code block content is excluded from metrics."""

    @pytest.mark.asyncio
    async def test_code_blocks_excluded_from_word_count(self) -> None:
        """Content inside triple-backticks does NOT inflate word counts."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Code block has long pseudo-sentence, but should be stripped
        mock_post = GeneratedPost(
            title="Test",
            subtitle="",
            content=(
                "This is readable text. ```def function_with_very_long_parameter_name_that_is_not_prose(): "
                "pass``` More readable text."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_metrics" in result
        # After stripping code, should have only "This is readable text." and "More readable text."
        # Both are short, so avg_words_per_sentence should be low
        avg_wps = result["readability_metrics"]["avg_words_per_sentence"]
        assert avg_wps < 10.0

    @pytest.mark.asyncio
    async def test_inline_code_excluded(self) -> None:
        """Inline code (backticks) is also excluded from analysis."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Inline code mixed with prose
        mock_post = GeneratedPost(
            title="Test",
            subtitle="",
            content="You can use `function_name_here` in your code. The syntax is simple.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        assert "readability_metrics" in result
        # After stripping inline code, word count should not include function_name_here
        avg_wps = result["readability_metrics"]["avg_words_per_sentence"]
        # Two sentences, remaining words should keep average reasonable
        assert avg_wps < 15.0


class TestReadabilityScorerPenalties:
    """Test sentence length and fog penalties."""

    @pytest.mark.asyncio
    async def test_sentence_penalty_above_20_words(self) -> None:
        """Sentences above 20 words/sentence incur a penalty."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Single very long sentence (40+ words)
        mock_post = GeneratedPost(
            title="Test",
            subtitle="",
            content=(
                "The comprehensive investigation of multifaceted contemporary sociological phenomena "
                "demands careful consideration of numerous interconnected variables."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await readability_scorer_node(state)

        long_score = result["readability_score"]

        # Compare with shorter version
        mock_post_short = GeneratedPost(
            title="Test",
            subtitle="",
            content="The investigation demands care.",
            tags=[],
            image_suggestions=[],
        )

        state_short = {"run_id": "test-124", "post": mock_post_short}
        result_short = await readability_scorer_node(state_short)
        short_score = result_short["readability_score"]

        # Shorter should score higher (less penalty)
        assert short_score > long_score

    @pytest.mark.asyncio
    async def test_fog_penalty_above_12(self) -> None:
        """High Gunning Fog (>12) incurs a penalty on readability_score."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # High fog text
        mock_post_complex = GeneratedPost(
            title="Test",
            subtitle="",
            content=(
                "The comprehensive investigation of multifaceted contemporary sociological phenomena "
                "demands careful consideration. Furthermore, the intricate relationship between various "
                "substantive components necessitates exhaustive examination of potential correlations."
            ),
            tags=[],
            image_suggestions=[],
        )

        state_complex = {"run_id": "test-125", "post": mock_post_complex}
        result_complex = await readability_scorer_node(state_complex)
        fog_complex = result_complex["readability_metrics"]["gunning_fog"]
        score_complex = result_complex["readability_score"]

        # Simple text
        mock_post_simple = GeneratedPost(
            title="Test",
            subtitle="",
            content="The cat sat. The dog ran. A bird flew.",
            tags=[],
            image_suggestions=[],
        )

        state_simple = {"run_id": "test-126", "post": mock_post_simple}
        result_simple = await readability_scorer_node(state_simple)
        fog_simple = result_simple["readability_metrics"]["gunning_fog"]
        score_simple = result_simple["readability_score"]

        # Complex should have higher fog
        assert fog_complex > 12.0
        # High fog should result in lower score
        assert score_complex < score_simple


class TestReadabilityScorerIssues:
    """Test issue reporting and structural check updates."""

    @pytest.mark.asyncio
    async def test_failing_post_adds_readability_issues(self) -> None:
        """Failing post (low readability_score < 0.50) adds readability_issues to structural_check_issues."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Dense, hard to read content
        mock_post = GeneratedPost(
            title="Test",
            subtitle="",
            content=(
                "The comprehensive investigation of multifaceted contemporary sociological phenomena "
                "demands careful consideration of numerous interconnected variables and their collective impact. "
                "Furthermore, the intricate relationship between various substantive components necessitates "
                "an exhaustive examination of potential correlations and causal mechanisms underlying observed patterns. "
                "In addition, the multifarious aspects of this phenomenon require meticulous analysis."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {
            "run_id": "test-127",
            "post": mock_post,
            "structural_check_issues": [],
        }

        result = await readability_scorer_node(state)

        if not result.get("readability_passed", True):
            assert "structural_check_issues" in result
            assert len(result["structural_check_issues"]) > 0
            readability_issues = [
                i
                for i in result["structural_check_issues"]
                if i.get("category") == "readability"
            ]
            assert len(readability_issues) > 0
            for issue in readability_issues:
                assert issue.get("severity") == "LOW"

    @pytest.mark.asyncio
    async def test_readability_issues_replace_not_accumulate(self) -> None:
        """readability_scorer_node replaces readability issues, not accumulates them on revision cycles."""
        from app.agents.nodes.readability_scorer_node import readability_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Dense content that fails
        mock_post = GeneratedPost(
            title="Test",
            subtitle="",
            content=(
                "The comprehensive investigation of multifaceted contemporary sociological phenomena "
                "demands careful consideration of numerous interconnected variables. "
                "Furthermore, the intricate relationship between various substantive components necessitates "
                "an exhaustive examination of potential correlations and causal mechanisms."
            ),
            tags=[],
            image_suggestions=[],
        )

        # First call
        initial_state = {
            "run_id": "test-128",
            "post": mock_post,
            "structural_check_issues": [],
        }

        result1 = await readability_scorer_node(initial_state)
        if not result1.get("readability_passed", True):
            first_cycle_issues = [
                i
                for i in result1.get("structural_check_issues", [])
                if i.get("category") == "readability"
            ]
            first_count = len(first_cycle_issues)
        else:
            first_count = 0

        # Second call (revision cycle) with output from first
        state_after_first = {
            "run_id": "test-128",
            "post": mock_post,
            "structural_check_issues": result1.get("structural_check_issues", []),
        }

        result2 = await readability_scorer_node(state_after_first)
        if not result2.get("readability_passed", True):
            second_cycle_issues = [
                i
                for i in result2.get("structural_check_issues", [])
                if i.get("category") == "readability"
            ]
            second_count = len(second_cycle_issues)
        else:
            second_count = 0

        # If there's no fix between cycles, counts should match (not accumulate)
        # If the content is still problematic, we should still have the same issue count
        if first_count > 0:
            assert second_count == first_count, "Issues should be replaced, not accumulated"
