"""Tests for the paper deduplication logic in the Collector agent."""

import pytest

from tui_agents.agents.collector import _deduplicate, _is_title_subsumed, _title_similarity
from tui_agents.sources.arxiv import SearchResult


class TestTitleSimilarity:
    def test_exact_match_returns_1(self):
        assert _title_similarity("Diffusion Models", "Diffusion Models") == 1.0

    def test_case_insensitive(self):
        assert _title_similarity("Diffusion Models", "diffusion models") == 1.0

    def test_completely_different_titles(self):
        similarity = _title_similarity("Bananas", "Gradient Descent for Neural Networks")
        assert similarity < 0.3

    def test_similar_titles_high_score(self):
        similarity = _title_similarity("Diffusion Models", "Diffusion Modeling for Images")
        assert similarity > 0.5


class TestTitleSubsumed:
    def test_shorter_is_prefix_of_longer(self):
        assert _is_title_subsumed(
            "Score-Based Generative Modeling",
            "Score-Based Generative Modeling through Stochastic Differential Equations",
        )

    def test_longer_contains_shorter(self):
        assert _is_title_subsumed(
            "Score-Based Generative Modeling through Stochastic Differential Equations",
            "Score-Based Generative Modeling",
        )

    def test_different_titles_not_subsumed(self):
        assert not _is_title_subsumed(
            "Diffusion Models",
            "Transformer Architecture",
        )


class TestDeduplication:
    def _make_result(self, source="arxiv", source_id="1", title="Test", authors=None):
        if authors is None:
            authors = ["Author A"]
        return SearchResult(
            source=source,
            source_id=source_id,
            title=title,
            authors=authors,
        )

    def test_deduplicate_by_same_source_id(self):
        r1 = self._make_result(source_id="1234.5678", title="Diffusion Models")
        r2 = self._make_result(source_id="1234.5678", title="Diffusion Models")
        results = _deduplicate([r1, r2])
        assert len(results) == 1

    def test_deduplicate_by_subsumed_title(self):
        r1 = self._make_result(source_id="a", title="Score-Based Generative Modeling")
        r2 = self._make_result(source_id="b", title="Score-Based Generative Modeling through SDEs")
        results = _deduplicate([r1, r2])
        assert len(results) == 1

    def test_deduplicate_by_similar_title(self):
        r1 = self._make_result(source_id="a", title="Diffusion Models for Optimal Transport")
        r2 = self._make_result(source_id="b", title="Diffusion Models for Optimal Transport with Applications")
        results = _deduplicate([r1, r2])
        assert len(results) == 1, f"Expected 1, got {len(results)}: {[r.title for r in results]}"

    def test_keeps_distinct_titles(self):
        r1 = self._make_result(source_id="a", title="Diffusion Models for Optimal Transport")
        r2 = self._make_result(source_id="b", title="Completely Different Topic")
        results = _deduplicate([r1, r2])
        assert len(results) == 2

    def test_mixed_sources_deduplicate(self):
        r1 = self._make_result(source="arxiv", source_id="arxiv.1", title="Diffusion Models for OT")
        r2 = self._make_result(source="semantic_scholar", source_id="ss.1", title="Diffusion Models for OT with Applications")
        r3 = self._make_result(source="arxiv", source_id="arxiv.2", title="Unrelated Paper")
        results = _deduplicate([r1, r2, r3])
        assert len(results) == 2, f"Expected 2, got {len(results)}: {[r.title for r in results]}"

    def test_empty_list(self):
        assert _deduplicate([]) == []
