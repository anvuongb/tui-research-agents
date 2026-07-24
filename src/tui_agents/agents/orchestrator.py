from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Coroutine

from tui_agents.agents.collector import CollectorAgent
from tui_agents.agents.distiller import DistillerAgent
from tui_agents.agents.implementer import ImplementerAgent
from tui_agents.agents.prototyper import PrototyperAgent
from tui_agents.llm.client import LLMClient
from tui_agents.sources.arxiv import SearchResult
from tui_agents.storage.database import Database
from tui_agents.storage.models import Implementation, Paper, StageStatus
from tui_agents.storage.vector_store import VectorStore
from tui_agents.utils.config import Config


ProgressFn = Callable[[str, str, float], Coroutine[Any, Any, None]]


class Orchestrator:
    def __init__(
        self,
        config: Config,
        database: Database,
        vector_store: VectorStore,
        llm: LLMClient,
    ):
        self.config = config
        self.db = database
        self.vector_store = vector_store
        self.llm = llm
        self._logger = logging.getLogger("tui_agents.orchestrator")

        self.collector = CollectorAgent(llm, database, vector_store, config)
        self.distiller = DistillerAgent(llm, database, vector_store)
        self.implementer = ImplementerAgent(llm, database, vector_store, config)
        self.prototyper = PrototyperAgent(llm, database, vector_store, config)

    async def search_papers(
        self,
        query: str,
        sources: list[str] | None = None,
        max_results: int = 20,
        progress: ProgressFn | None = None,
    ) -> list[SearchResult]:
        return await self.collector.search_only(query, sources, max_results, progress)

    async def collect_papers(
        self,
        query: str,
        sources: list[str] | None = None,
        max_results: int = 20,
        progress: ProgressFn | None = None,
    ) -> list[Paper]:
        return await self.collector.search_and_collect(query, sources, max_results, progress)

    async def collect_single_paper(
        self,
        result: SearchResult,
        progress: ProgressFn | None = None,
    ) -> Paper | None:
        return await self.collector.collect_paper(result, progress)

    async def distill_paper(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
    ):
        return await self.distiller.distill(paper_id, progress=progress)

    async def implement_paper(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
        github_url: str | None = None,
        skip_eval: bool = False,
    ) -> Implementation | None:
        return await self.implementer.implement(
            paper_id, progress=progress, github_url=github_url, skip_eval=skip_eval
        )

    async def prototype_paper(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any] | None:
        return await self.prototyper.prototype(paper_id, progress=progress)

    async def delete_paper(self, paper_id: str) -> None:
        import shutil
        from pathlib import Path

        paper = await self.db.get_paper(paper_id)
        if not paper:
            return

        try:
            self.vector_store.delete_by_paper(paper_id)
        except Exception:
            pass

        await self.db.delete_paper(paper_id)

        if paper.pdf_path:
            try:
                pdf = Path(paper.pdf_path)
                if pdf.exists():
                    pdf.unlink()
                pdf.parent.rmdir() if pdf.parent.exists() and not any(pdf.parent.iterdir()) else None
            except Exception:
                pass

        code_dir = Path(self.config.code_dir) / paper_id
        if code_dir.exists():
            try:
                shutil.rmtree(str(code_dir))
            except Exception:
                pass

    async def run_pipeline(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        paper = await self.db.get_paper(paper_id)
        if not paper:
            return {"status": "error", "error": f"Paper not found: {paper_id}"}

        stages = self.config.pipeline_stages
        results: dict[str, Any] = {"paper_id": paper_id, "stages": {}}

        for i, stage in enumerate(stages):
            if progress:
                await progress(
                    "pipeline",
                    f"Running stage {i+1}/{len(stages)}: {stage}",
                    i / len(stages),
                )

            if stage == "distiller":
                if progress:
                    await progress(stage, f"Distilling: {paper.title[:60]}...", i / len(stages))
                distillation = await self.distiller.distill(paper_id, progress=progress)
                results["stages"][stage] = {
                    "completed": distillation is not None,
                    "id": distillation.id if distillation else None,
                }
                if not distillation:
                    return results
            elif stage == "implementer":
                if progress:
                    await progress(stage, f"Implementing: {paper.title[:60]}...", i / len(stages))
                impl = await self.implementer.implement(paper_id, progress=progress)
                results["stages"][stage] = {
                    "completed": impl is not None,
                    "id": impl.id if impl else None,
                }
                if not impl:
                    return results
            elif stage == "prototyper":
                if progress:
                    await progress(stage, f"Prototyping: {paper.title[:60]}...", i / len(stages))
                proto = await self.prototyper.prototype(paper_id, progress=progress)
                results["stages"][stage] = {
                    "completed": proto is not None,
                }
                if not proto:
                    return results
            else:
                if progress:
                    await progress(stage, f"Stage '{stage}' not yet implemented", i / len(stages))

        return results
