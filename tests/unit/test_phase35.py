"""Tests for Phase 3.5: GitHub client, CodeViewer, GitHubLinkModal, cache operations."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tui_agents.agents.implementer import ImplementerAgent
from tui_agents.app.screens.code_viewer import CodeViewer
from tui_agents.app.screens.github_link_modal import GitHubLinkModal
from tui_agents.sources.github import GitHubClient
from tui_agents.storage.models import (
    Distillation,
    Implementation,
    Paper,
    PaperSource,
)


class TestGitHubClient:
    def test_init_reads_config(self, tmp_config):
        client = GitHubClient(tmp_config)
        assert client._max_repos == 5

    def test_headers_without_token(self, tmp_config):
        client = GitHubClient(tmp_config)
        assert "Authorization" not in client._headers
        assert "User-Agent" in client._headers

    @pytest.mark.asyncio
    async def test_search_repos_returns_list(self, tmp_config):
        client = GitHubClient(tmp_config)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "full_name": "user/repo",
                    "name": "repo",
                    "description": "A test repo",
                    "html_url": "https://github.com/user/repo",
                    "stargazers_count": 42,
                    "language": "Python",
                    "default_branch": "main",
                }
            ]
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = mock_response
            mock_response.raise_for_status = MagicMock()

            results = await client.search_repos("diffusion", "optimal transport")
            assert len(results) == 1
            assert results[0]["full_name"] == "user/repo"
            assert results[0]["stars"] == 42

    @pytest.mark.asyncio
    async def test_search_repos_handles_403_rate_limit(self, tmp_config):
        client = GitHubClient(tmp_config)

        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "403", request=MagicMock(), response=mock_response
            )

            results = await client.search_repos("test", "")
            assert results == []

    @pytest.mark.asyncio
    async def test_search_repos_handles_timeout(self, tmp_config):
        client = GitHubClient(tmp_config)

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("timeout")

            results = await client.search_repos("test", "")
            assert results == []

    @pytest.mark.asyncio
    async def test_load_repo_by_url_parses_correctly(self, tmp_config):
        client = GitHubClient(tmp_config)

        with patch.object(client, "load_repo_code") as mock_load:
            mock_load.return_value = {"code": "test"}
            result = await client.load_repo_by_url("https://github.com/user/repo")
            mock_load.assert_called_once_with("user/repo")
            assert result is not None


class TestCodeViewer:
    def test_creates_with_valid_params(self, test_orchestrator):
        viewer = CodeViewer(
            title="Test Paper",
            code="def test(): pass",
            dependencies=["torch"],
        )
        assert viewer._title == "Test Paper"
        assert viewer._code == "def test(): pass"
        assert "torch" in viewer._dependencies

    def test_accepts_source_url(self):
        viewer = CodeViewer(
            title="Test", code="x", dependencies=[],
            source_url="github.com/user/repo",
        )
        assert viewer._source_url == "github.com/user/repo"


class TestGitHubLinkModal:
    def test_creates_with_reason(self):
        modal = GitHubLinkModal("No matches found")
        assert "No matches" in modal._reason

    def test_dismiss_on_skip_button(self):
        modal = GitHubLinkModal("Test")
        modal.dismiss = MagicMock()
        modal.on_button_pressed(MagicMock(
            button=MagicMock(id="skip-btn"),
        ))
        modal.dismiss.assert_called_once_with(None)

    def test_dismiss_on_submit_button(self):
        modal = GitHubLinkModal("Test")
        modal.dismiss = MagicMock()

        mock_input = MagicMock()
        mock_input.value = "github.com/user/repo"
        modal.query_one = MagicMock(return_value=mock_input)

        modal.on_button_pressed(MagicMock(
            button=MagicMock(id="submit-btn"),
        ))
        modal.dismiss.assert_called_once_with("github.com/user/repo")


class TestCacheOperations:
    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, test_db):
        query_key = "test-key-abc"
        results = [{"name": "repo1"}, {"name": "repo2"}]

        await test_db.set_cached_github(query_key, results, ttl_seconds=3600)

        cached = await test_db.get_cached_github(query_key)
        assert cached is not None
        assert len(cached) == 2
        assert cached[0]["name"] == "repo1"

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, test_db):
        cached = await test_db.get_cached_github("nonexistent-key")
        assert cached is None

    @pytest.mark.asyncio
    async def test_cache_clear(self, test_db):
        await test_db.set_cached_github("key1", [{"a": 1}])
        await test_db.set_cached_github("key2", [{"b": 2}])

        await test_db.clear_github_cache()

        assert await test_db.get_cached_github("key1") is None
        assert await test_db.get_cached_github("key2") is None


class TestImplementerEnhanced:
    @pytest.mark.asyncio
    async def test_load_paper_text_returns_string(self, test_llm, test_db,
                                                    test_vector_store, tmp_config):
        agent = ImplementerAgent(test_llm, test_db, test_vector_store, tmp_config)

        test_vector_store.add(
            text="Paper section one content.",
            metadata={"paper_id": "paper-text-test", "chunk_index": "0", "total_chunks": "2"},
        )
        test_vector_store.add(
            text="Paper section two content.",
            metadata={"paper_id": "paper-text-test", "chunk_index": "1", "total_chunks": "2"},
        )

        text = await agent._load_paper_text("paper-text-test")
        assert "section one" in text
        assert "section two" in text

    @pytest.mark.asyncio
    async def test_load_paper_text_empty_for_missing(self, test_llm, test_db,
                                                       test_vector_store, tmp_config):
        agent = ImplementerAgent(test_llm, test_db, test_vector_store, tmp_config)
        text = await agent._load_paper_text("nonexistent-paper")
        assert text == ""

    @pytest.mark.asyncio
    async def test_implement_rejects_missing_distillation(self, test_llm, test_db,
                                                            test_vector_store, tmp_config):
        agent = ImplementerAgent(test_llm, test_db, test_vector_store, tmp_config)

        await test_db.upsert_paper(Paper(
            id="no-dist-impl", source=PaperSource.ARXIV, source_id="t.1",
            title="No Dist", authors=["A"], status="collected",
        ))

        result = await agent.implement("no-dist-impl")
        assert result is None
