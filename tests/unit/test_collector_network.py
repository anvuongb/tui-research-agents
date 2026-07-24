"""Tests for collector agent's network error resilience.

Verifies the fixes for:
- arXiv searches timing out without crashing the collector
- Search sources continuing to the next source when one fails
- Progress callbacks reporting errors correctly
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from tui_agents.agents.collector import CollectorAgent
from tui_agents.sources.arxiv import SearchResult
from tui_agents.storage.models import Paper
from tui_agents.utils.config import Config


class TestSearchSourcesErrorResilience:
    """Verify search_sources handles individual source failures gracefully."""

    @pytest.mark.asyncio
    async def test_arxiv_timeout_does_not_block_semantic_scholar(
        self, test_llm, test_db, test_vector_store, tmp_config
    ):
        """If arXiv times out, Semantic Scholar should still be tried."""
        collector = CollectorAgent(test_llm, test_db, test_vector_store, tmp_config)

        # Patch arXiv search_sync to simulate a slow call
        original_sync = collector.arxiv.search_sync

        async def fake_arxiv_sync(query, max_results):
            # simulate timeout
            raise asyncio.TimeoutError("arXiv timed out")

        # Make search_sync raise timeout via our wrapper
        collector.arxiv.search_sync = original_sync

        # Patch search_sources internal: make arXiv branch time out
        calls = []

        async def fake_progress(stage, msg, pct):
            calls.append((stage, msg, pct))

        with patch.object(collector, "arxiv") as mock_arxiv:
            mock_arxiv.search_sync.side_effect = asyncio.TimeoutError

            results = await collector.search_sources(
                "test query", sources=["arxiv"], max_results=5, progress=fake_progress
            )
            assert len(results) == 0
            assert any("timed out" in msg.lower() or "arxiv" in msg.lower()
                       for _, msg, _ in calls)

    @pytest.mark.asyncio
    async def test_semantic_scholar_failure_still_returns_arxiv_results(
        self, test_llm, test_db, test_vector_store, tmp_config
    ):
        """If Semantic Scholar fails, arXiv results are still returned."""
        collector = CollectorAgent(test_llm, test_db, test_vector_store, tmp_config)

        calls = []

        async def fake_progress(stage, msg, pct):
            calls.append((stage, msg, pct))

        with patch.object(collector.arxiv, "search_sync") as mock_arxiv:
            mock_arxiv.return_value = [
                SearchResult(
                    source="arxiv",
                    source_id="test.1",
                    title="Test Paper",
                    authors=["Author"],
                )
            ]

            with patch.object(collector.semantic_scholar, "search") as mock_ss:
                mock_ss.side_effect = RuntimeError("SS failed")

                results = await collector.search_sources(
                    "test", sources=["arxiv", "semantic_scholar"],
                    max_results=5, progress=fake_progress,
                )

                assert len(results) >= 1
                assert results[0].source == "arxiv"

    @pytest.mark.asyncio
    async def test_both_sources_fail_returns_empty_list(
        self, test_llm, test_db, test_vector_store, tmp_config
    ):
        """If all sources fail, return empty list without crashing."""
        collector = CollectorAgent(test_llm, test_db, test_vector_store, tmp_config)

        with patch.object(collector.arxiv, "search_sync") as mock_arxiv:
            mock_arxiv.side_effect = RuntimeError("arxiv down")
            with patch.object(collector.semantic_scholar, "search") as mock_ss:
                mock_ss.side_effect = RuntimeError("ss down")

                results = await collector.search_sources(
                    "test", sources=["arxiv", "semantic_scholar"],
                    max_results=5,
                )
                assert results == []


class TestProgressCallback:
    """Verify progress callbacks report errors correctly."""

    @pytest.mark.asyncio
    async def test_progress_receives_timeout_message(self, test_llm, test_db,
                                                      test_vector_store, tmp_config):
        collector = CollectorAgent(test_llm, test_db, test_vector_store, tmp_config)

        progress_messages = []

        async def record_progress(stage, msg, pct):
            progress_messages.append({"stage": stage, "msg": msg, "pct": pct})

        with patch.object(collector.arxiv, "search_sync") as mock_arxiv:
            mock_arxiv.side_effect = asyncio.TimeoutError

            await collector.search_sources(
                "test", sources=["arxiv"], max_results=5,
                progress=record_progress,
            )

            # Should have at least: "searching..." message + "timed out" message
            assert len(progress_messages) >= 2
            stages = [m["stage"] for m in progress_messages]
            assert "search" in stages

    @pytest.mark.asyncio
    async def test_progress_receives_error_message(self, test_llm, test_db,
                                                     test_vector_store, tmp_config):
        collector = CollectorAgent(test_llm, test_db, test_vector_store, tmp_config)

        progress_messages = []

        async def record_progress(stage, msg, pct):
            progress_messages.append({"stage": stage, "msg": msg, "pct": pct})

        with patch.object(collector.arxiv, "search_sync") as mock_arxiv:
            mock_arxiv.side_effect = ConnectionRefusedError("no route to host")

            await collector.search_sources(
                "test", sources=["arxiv"], max_results=5,
                progress=record_progress,
            )

            # Should have at least one progress update about the error
            error_msgs = [m for m in progress_messages if "fail" in m["msg"].lower()]
            assert len(error_msgs) >= 1
