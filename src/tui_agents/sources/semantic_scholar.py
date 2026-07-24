from __future__ import annotations

import asyncio
from typing import Any

import httpx

from tui_agents.sources.arxiv import SearchResult
from tui_agents.utils.config import Config


BASE_URL = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,abstract,authors,year,url,externalIds,paperId,publicationTypes,openAccessPdf"


class SemanticScholarClient:
    def __init__(self, config: Config):
        self._config = config
        api_key = config.semantic_scholar_api_key
        if api_key and api_key != "${SEMANTIC_SCHOLAR_API_KEY}":
            self._headers = {"x-api-key": api_key}
        else:
            self._headers = {}
        self._rate_limit_sem = asyncio.Semaphore(10)

    async def search(self, query: str, max_results: int = 20) -> list[SearchResult]:
        params: dict[str, Any] = {
            "query": query,
            "limit": min(max_results, 100),
            "fields": FIELDS,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{BASE_URL}/paper/search",
                    params=params,
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            from tui_agents.utils.logging import get_logger
            get_logger().warning(f"Semantic Scholar search error: {e}")
            return []

        results: list[SearchResult] = []
        for item in data.get("data", []):
            paper_id = item.get("paperId", "")
            title = item.get("title", "Untitled")
            abstract = item.get("abstract") or ""

            authors: list[str] = []
            for a in item.get("authors", []):
                name = a.get("name", "")
                if name:
                    authors.append(name)

            year = item.get("year")
            published_date = str(year) if year else None

            url = item.get("url") or None

            pdf_url = None
            open_access = item.get("openAccessPdf")
            if open_access and open_access.get("url"):
                pdf_url = open_access["url"]

            external_ids = item.get("externalIds", {}) or {}
            arxiv_id = external_ids.get("ArXiv", "")
            doi = external_ids.get("DOI", "")

            results.append(SearchResult(
                source="semantic_scholar",
                source_id=paper_id,
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                pdf_url=pdf_url,
                published_date=published_date,
                doi=doi,
            ))

        return results

    async def get_paper_details(self, paper_id: str) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{BASE_URL}/paper/{paper_id}",
                    params={"fields": FIELDS},
                    headers=self._headers,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            from tui_agents.utils.logging import get_logger
            get_logger().warning(f"Semantic Scholar paper details error: {e}")
            return None
