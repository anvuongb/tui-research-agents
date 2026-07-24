from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import arxiv

from tui_agents.utils.config import Config


@dataclass
class SearchResult:
    source: str
    source_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    url: str | None = None
    pdf_url: str | None = None
    published_date: str | None = None
    doi: str | None = None


_CAT_FILTER = "cat:cs.LG OR cat:cs.AI OR cat:cs.CV OR cat:stat.ML"


class ArxivClient:
    def __init__(self, config: Config):
        self._config = config
        self._client = arxiv.Client(
            page_size=100,
            delay_seconds=config.get("sources", "arxiv", "delay_between_requests", default=3.0),
            num_retries=1,
        )
        self._category_filter = config.get("sources", "arxiv", "category_filter", default=_CAT_FILTER)

    def _build_query(self, query: str) -> str:
        if self._category_filter:
            return f"({self._category_filter}) AND ({query})"
        return query

    async def search(self, query: str, max_results: int = 20) -> list[SearchResult]:
        search = arxiv.Search(
            query=self._build_query(query),
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
            sort_order=arxiv.SortOrder.Descending,
        )

        results: list[SearchResult] = []
        try:
            for result in self._client.results(search):
                authors = [str(a) for a in result.authors]
                published = result.published.isoformat() if result.published else None
                doi = result.doi or None
                entry_id = result.entry_id.split("/")[-1] if result.entry_id else ""

                results.append(SearchResult(
                    source="arxiv",
                    source_id=entry_id,
                    title=result.title or "Untitled",
                    authors=authors,
                    abstract=result.summary or "",
                    url=result.entry_id or None,
                    pdf_url=result.pdf_url or None,
                    published_date=published,
                    doi=doi,
                ))
        except arxiv.ArxivError as e:
            from tui_agents.utils.logging import get_logger
            get_logger().warning(f"arXiv search error: {e}")

        return results

    def search_sync(self, query: str, max_results: int = 20) -> list[SearchResult]:
        search = arxiv.Search(
            query=self._build_query(query),
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
            sort_order=arxiv.SortOrder.Descending,
        )
        results: list[SearchResult] = []
        try:
            for result in self._client.results(search):
                authors = [str(a) for a in result.authors]
                published = result.published.isoformat() if result.published else None
                doi = result.doi or None
                entry_id = result.entry_id.split("/")[-1] if result.entry_id else ""

                results.append(SearchResult(
                    source="arxiv",
                    source_id=entry_id,
                    title=result.title or "Untitled",
                    authors=authors,
                    abstract=result.summary or "",
                    url=result.entry_id or None,
                    pdf_url=result.pdf_url or None,
                    published_date=published,
                    doi=doi,
                ))
        except arxiv.ArxivError as e:
            from tui_agents.utils.logging import get_logger
            get_logger().warning(f"arXiv search error: {e}")

        return results

    async def download_pdf(self, pdf_url: str, dest_path: str) -> bool:
        try:
            paper = next(arxiv.Client().results(arxiv.Search(id_list=[pdf_url.split("/")[-1]])))
            paper.download_pdf(dirpath=str(dest_path))
            return True
        except Exception as e:
            from tui_agents.utils.logging import get_logger
            get_logger().warning(f"arXiv PDF download error for {pdf_url}: {e}")
            return False
