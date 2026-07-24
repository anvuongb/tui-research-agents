"""Tests for Semantic Scholar client error handling and header construction.

Verifies the fixes for:
- 429 rate limit responses not crashing the client
- API key header construction
- Graceful handling of network errors
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from tui_agents.sources.semantic_scholar import SemanticScholarClient
from tui_agents.utils.config import Config


def _make_config(api_key: str | None = None) -> Config:
    config = Config("config/default.yaml")
    if api_key is not None:
        config._data.setdefault("sources", {}).setdefault("semantic_scholar", {})[
            "api_key"
        ] = api_key
    else:
        config._data.setdefault("sources", {}).setdefault("semantic_scholar", {})[
            "api_key"
        ] = "${SEMANTIC_SCHOLAR_API_KEY}"
    return config


class TestHeaderConstruction:
    def test_no_api_key_means_no_header(self):
        client = SemanticScholarClient(_make_config(api_key="${SEMANTIC_SCHOLAR_API_KEY}"))
        assert "x-api-key" not in client._headers

    def test_empty_api_key_means_no_header(self):
        client = SemanticScholarClient(_make_config(api_key=""))
        assert "x-api-key" not in client._headers

    def test_api_key_adds_header(self):
        client = SemanticScholarClient(_make_config(api_key="abc123"))
        assert client._headers["x-api-key"] == "abc123"


class TestErrorHandling:
    """Verify that HTTP errors and rate limits are caught gracefully."""

    @pytest.mark.asyncio
    async def test_429_rate_limit_returns_empty_list(self):
        """Regression: 429 should not crash — should return [] with a warning."""
        client = SemanticScholarClient(_make_config())

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=MagicMock(),
                response=MagicMock(status_code=429),
            )
            mock_get.return_value = mock_response

            results = await client.search("test query", max_results=5)
            assert results == [], (
                "Expected empty list for 429, got {len(results)} results"
            )

    @pytest.mark.asyncio
    async def test_403_returns_empty_list(self):
        """403 should not crash."""
        client = SemanticScholarClient(_make_config())

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "403 Forbidden",
                request=MagicMock(),
                response=MagicMock(status_code=403),
            )
            mock_get.return_value = mock_response

            results = await client.search("test", max_results=5)
            assert results == []

    @pytest.mark.asyncio
    async def test_network_timeout_returns_empty_list(self):
        """Network timeout should return [] not crash."""
        client = SemanticScholarClient(_make_config())

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Connection timed out")

            results = await client.search("test", max_results=5)
            assert results == []

    @pytest.mark.asyncio
    async def test_connection_error_returns_empty_list(self):
        """Connection errors should be caught."""
        client = SemanticScholarClient(_make_config())

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("Cannot connect")

            results = await client.search("test", max_results=5)
            assert results == []

    @pytest.mark.asyncio
    async def test_get_paper_details_handles_errors(self):
        """get_paper_details should return None on error, not crash."""
        client = SemanticScholarClient(_make_config())

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("timeout")

            result = await client.get_paper_details("paper123")
            assert result is None
