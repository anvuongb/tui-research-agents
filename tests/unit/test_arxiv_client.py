"""Tests for arXiv client query construction and category filter handling.

Verifies the fixes for:
- Multi-OR category filter causing arXiv API to hang
- Query building with/without category filter
- Config-driven category filter behavior
"""

from tui_agents.sources.arxiv import ArxivClient, _CAT_FILTER
from tui_agents.utils.config import Config


def _make_config(category_filter: str | None = None) -> Config:
    config = Config("config/default.yaml")
    if category_filter is not None:
        config._data.setdefault("sources", {}).setdefault("arxiv", {})[
            "category_filter"
        ] = category_filter
    return config


class TestQueryBuilding:
    """Verify that _build_query produces correct arXiv API search strings."""

    def test_no_filter_produces_raw_query(self):
        client = ArxivClient(_make_config(category_filter=""))
        result = client._build_query("diffusion models")
        assert result == "diffusion models"

    def test_single_category_wrapped_in_parens(self):
        client = ArxivClient(_make_config(category_filter="cat:cs.LG"))
        result = client._build_query("optimal transport")
        assert result == "(cat:cs.LG) AND (optimal transport)"

    def test_multi_category_uses_or_syntax(self):
        client = ArxivClient(_make_config(
            category_filter="cat:cs.LG OR cat:cs.AI OR cat:cs.CV OR cat:stat.ML"
        ))
        result = client._build_query("diffusion")
        assert result.startswith("(cat:cs.LG OR cat:cs.AI OR cat:cs.CV OR cat:stat.ML) AND ")
        assert "(diffusion)" in result

    def test_query_terms_are_preserved(self):
        client = ArxivClient(_make_config(category_filter="cat:cs.LG"))
        result = client._build_query("score-based generative modeling")
        assert "score-based generative modeling" in result

    def test_special_characters_in_query_preserved(self):
        client = ArxivClient(_make_config(category_filter="cat:cs.LG"))
        result = client._build_query('"optimal transport" AND diffusion')
        assert '"optimal transport" AND diffusion' in result

    def test_category_filter_combined_with_and(self):
        client = ArxivClient(_make_config(category_filter="cat:cs.LG"))
        result = client._build_query("test")
        assert " AND " in result
        assert result.count("(") == 2
        assert result.count(")") == 2


class TestDefaultCategoryFilter:
    """Verify that the default built-in category filter is valid and not too long."""

    def test_default_filter_is_not_empty(self):
        assert _CAT_FILTER != ""
        assert "cat:" in _CAT_FILTER

    def test_default_filter_not_too_many_or_clauses(self):
        """Regression test: too many OR clauses (6+) hung the arXiv API engine."""
        or_count = _CAT_FILTER.count(" OR ")
        assert or_count <= 4, (
            f"Default filter has {or_count} OR clauses — "
            "too many OR clauses can hang the arXiv API"
        )

    def test_default_config_uses_builtin_filter(self):
        config = Config("config/default.yaml")
        client = ArxivClient(config)
        query = client._build_query("test")
        assert client._category_filter == _CAT_FILTER
        assert query == f"({_CAT_FILTER}) AND (test)"


class TestConfigDrivenFilter:
    """Verify that config.yaml settings override the built-in default."""

    def test_config_override_is_used(self):
        client = ArxivClient(_make_config(category_filter="cat:cs.CV"))
        assert client._category_filter == "cat:cs.CV"

    def test_empty_config_disables_filter(self):
        client = ArxivClient(_make_config(category_filter=""))
        assert client._build_query("test") == "test"

    def test_none_config_disables_filter(self):
        config = Config("config/default.yaml")
        config._data.setdefault("sources", {}).setdefault("arxiv", {})[
            "category_filter"
        ] = None
        client = ArxivClient(config)
        assert client._build_query("test") == "test"
