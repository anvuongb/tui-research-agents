from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Coroutine

from tui_agents.agents.base import BaseAgent
from tui_agents.llm.client import LLMClient
from tui_agents.llm.tools import COLLECTOR_TOOLS
from tui_agents.sources.arxiv import ArxivClient, SearchResult
from tui_agents.sources.pdf import chunk_text, estimate_token_count, extract_text_from_pdf
from tui_agents.sources.semantic_scholar import SemanticScholarClient
from tui_agents.storage.database import Database
from tui_agents.storage.models import Paper, PaperSource, StageStatus
from tui_agents.storage.vector_store import VectorStore
from tui_agents.utils.config import Config


ProgressFn = Callable[[str, str, float], Coroutine[Any, Any, None]]


def _title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _is_title_subsumed(shorter: str, longer: str) -> bool:
    s = shorter.lower().strip()
    l = longer.lower().strip()
    return s in l or l in s


def _deduplicate(results: list[SearchResult], threshold: float = 0.80) -> list[SearchResult]:
    deduped: list[SearchResult] = []
    for r in results:
        duplicate = False
        for existing in deduped:
            if r.source_id and r.source_id == existing.source_id:
                duplicate = True
                break
            if _is_title_subsumed(r.title, existing.title):
                duplicate = True
                break
            if _title_similarity(r.title, existing.title) >= threshold:
                duplicate = True
                break
        if not duplicate:
            deduped.append(r)
    return deduped


class CollectorAgent(BaseAgent):
    agent_type = "collector"

    def __init__(
        self,
        llm: LLMClient,
        database: Database,
        vector_store: VectorStore,
        config: Config,
    ):
        super().__init__(llm, database)
        self.vector_store = vector_store
        self.config = config
        self.arxiv = ArxivClient(config)
        self.semantic_scholar = SemanticScholarClient(config)
        self._papers_dir = Path(config.papers_dir)
        self._papers_dir.mkdir(parents=True, exist_ok=True)

    async def search_sources(
        self,
        query: str,
        sources: list[str] | None = None,
        max_results: int = 20,
        progress: ProgressFn | None = None,
    ) -> list[SearchResult]:
        if sources is None:
            sources = ["arxiv", "semantic_scholar"]

        all_results: list[SearchResult] = []

        if "arxiv" in sources and self.config.arxiv_enabled:
            if progress:
                await progress("search", "Searching arXiv...", 0.1)
            try:
                arxiv_results = await asyncio.to_thread(
                    self.arxiv.search_sync, query, max_results
                )
                all_results.extend(arxiv_results)
            except Exception as e:
                if progress:
                    await progress("search", f"arXiv search failed: {e}", 0.1)

        if "semantic_scholar" in sources and self.config.semantic_scholar_enabled:
            if progress:
                await progress("search", "Searching Semantic Scholar...", 0.3)
            try:
                ss_results = await self.semantic_scholar.search(query, max_results)
                all_results.extend(ss_results)
            except Exception as e:
                if progress:
                    await progress("search", f"Semantic Scholar search failed: {e}", 0.3)

        deduped = _deduplicate(all_results)

        if progress:
            await progress("search", f"Found {len(deduped)} papers (deduplicated from {len(all_results)})", 0.5)

        return deduped

    async def collect_paper(
        self,
        result: SearchResult,
        progress: ProgressFn | None = None,
    ) -> Paper | None:
        paper_id = str(uuid.uuid4())
        source = PaperSource.ARXIV if result.source == "arxiv" else PaperSource.SEMANTIC_SCHOLAR

        pdf_path: str | None = None
        if result.pdf_url:
            if progress:
                await progress("download", f"Downloading: {result.title[:60]}...", 0.6)
            pdf_path = await self._download_pdf(result.pdf_url, paper_id)

        if progress:
            await progress("extract", "Extracting text...", 0.7)

        full_text = ""
        if pdf_path:
            try:
                full_text = extract_text_from_pdf(pdf_path)
            except Exception as e:
                if progress:
                    await progress("extract", f"PDF extraction failed: {e}", 0.7)

        paper = Paper(
            id=paper_id,
            source=source,
            source_id=result.source_id,
            title=result.title,
            authors=result.authors,
            abstract=result.abstract or full_text[:500],
            url=result.url,
            pdf_path=pdf_path,
            published_date=result.published_date,
            tags=[],
            status="collected",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        if full_text:
            if progress:
                await progress("chunk", f"Chunking text ({estimate_token_count(full_text)} tokens)...", 0.8)
            chunks = chunk_text(
                full_text,
                chunk_size=4000,
                chunk_overlap=500,
                metadata={"paper_id": paper_id, "title": paper.title},
            )

            if progress:
                await progress("embed", f"Embedding {len(chunks)} chunks...", 0.9)

            embedding_ids: list[str] = []
            for chunk in chunks:
                doc_id = self.vector_store.add(
                    text=chunk.text,
                    metadata={
                        "paper_id": paper_id,
                        "chunk_index": str(chunk.chunk_index),
                        "total_chunks": str(chunk.total_chunks),
                        "source": result.source,
                    },
                )
                embedding_ids.append(doc_id)
            paper.embedding_id = embedding_ids[0] if embedding_ids else None

        await self.db.upsert_paper(paper)

        if progress:
            await progress("done", f"Collected: {paper.title[:80]}", 1.0)

        return paper

    async def search_and_collect(
        self,
        query: str,
        sources: list[str] | None = None,
        max_results: int = 20,
        progress: ProgressFn | None = None,
    ) -> list[Paper]:
        search_results = await self.search_sources(query, sources, max_results, progress)
        papers: list[Paper] = []

        for i, result in enumerate(search_results):
            if progress:
                await progress(
                    "collecting",
                    f"Processing {i+1}/{len(search_results)}: {result.title[:60]}...",
                    i / max(len(search_results), 1),
                )
            try:
                paper = await self.collect_paper(result, progress)
                if paper:
                    papers.append(paper)
            except Exception as e:
                if progress:
                    await progress("error", f"Failed to collect '{result.title[:60]}': {e}", 0.0)

        return papers

    async def search_only(
        self,
        query: str,
        sources: list[str] | None = None,
        max_results: int = 20,
        progress: ProgressFn | None = None,
    ) -> list[SearchResult]:
        return await self.search_sources(query, sources, max_results, progress)

    async def _download_pdf(self, pdf_url: str, paper_id: str) -> str | None:
        try:
            import asyncio

            import httpx

            dest_dir = self._papers_dir / paper_id
            dest_dir.mkdir(parents=True, exist_ok=True)

            if "arxiv.org" in pdf_url:
                arxiv_id = pdf_url.rstrip("/").split("/")[-1]
                if arxiv_id.endswith(".pdf"):
                    arxiv_id = arxiv_id[:-4]
                import re
                arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
                async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                    resp = await client.get(pdf_url)
                    resp.raise_for_status()
                    dest_path = dest_dir / f"{arxiv_id}.pdf"
                    dest_path.write_bytes(resp.content)
                    return str(dest_path)
            else:
                async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                    resp = await client.get(pdf_url)
                    resp.raise_for_status()
                    dest_path = dest_dir / f"paper.pdf"
                    dest_path.write_bytes(resp.content)
                    return str(dest_path)
        except Exception as e:
            from tui_agents.utils.logging import get_logger
            get_logger().warning(f"PDF download failed for {pdf_url}: {e}")
            return None

    async def _search_arxiv_direct(
        self, query: str, max_results: int, progress: ProgressFn | None = None
    ) -> list[SearchResult]:
        if progress:
            await progress("search", "Searching arXiv directly via LLM...", 0.1)
        return await asyncio.to_thread(self.arxiv.search_sync, query, max_results)

    async def execute(self, paper_id: str, **kwargs) -> dict[str, Any]:
        return {"status": "collector does not execute on existing papers. Use search_and_collect or collect_paper."}
