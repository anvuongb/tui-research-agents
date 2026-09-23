from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

from tui_agents.agents.benchmarker import BenchmarkerAgent
from tui_agents.agents.collector import CollectorAgent
from tui_agents.agents.distiller import DistillerAgent
from tui_agents.agents.implementer import ImplementerAgent
from tui_agents.agents.prototyper import PrototyperAgent
from tui_agents.llm.client import LLMClient
from tui_agents.sources.arxiv import SearchResult
from tui_agents.storage.database import Database
from tui_agents.storage.models import Implementation, Paper
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
        self.benchmarker = BenchmarkerAgent(llm, database, vector_store, config)

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
        previous_benchmark_context: dict[str, Any] | None = None,
    ) -> Implementation | None:
        return await self.implementer.implement(
            paper_id, progress=progress, github_url=github_url, skip_eval=skip_eval,
            previous_benchmark_context=previous_benchmark_context,
        )

    async def prototype_paper(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any] | None:
        return await self.prototyper.prototype(paper_id, progress=progress)

    async def benchmark_paper(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
        impl_version_idx: int = 0,
    ):
        return await self.benchmarker.benchmark(paper_id, progress=progress, impl_version_idx=impl_version_idx)

    async def delete_paper(self, paper_id: str) -> None:
        import shutil
        from pathlib import Path

        paper = await self.db.get_paper(paper_id)
        if not paper:
            return

        try:
            self.vector_store.delete_by_paper(paper_id)
        except Exception as e:
            self._logger.warning(f"Failed to delete vectors for {paper_id}: {e}")

        await self.db.delete_paper(paper_id)

        data_root = str(Path(self.config.data_dir).resolve())
        if paper.pdf_path:
            try:
                pdf = Path(paper.pdf_path).resolve()
                if str(pdf).startswith(data_root) and pdf.exists():
                    pdf.unlink()
                    parent = pdf.parent
                    if parent.exists() and not any(parent.iterdir()):
                        parent.rmdir()
            except Exception as e:
                self._logger.warning(f"Failed to delete PDF for {paper_id}: {e}")

        code_dir = (Path(self.config.code_dir) / paper_id).resolve()
        if str(code_dir).startswith(data_root) and code_dir.exists():
            try:
                shutil.rmtree(str(code_dir))
            except Exception as e:
                self._logger.warning(f"Failed to delete code dir for {paper_id}: {e}")

    async def run_pipeline(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        paper = await self.db.get_paper(paper_id)
        if not paper:
            return {"status": "error", "error": f"Paper not found: {paper_id}"}

        max_iterations = self.config.loop_max_iterations
        iteration = 0
        last_benchmark: Any = None
        results: dict[str, Any] = {"paper_id": paper_id, "iterations": []}

        while iteration < max_iterations:
            iter_result: dict[str, Any] = {"iteration": iteration + 1}

            if progress:
                await progress("loop", f"Iteration {iteration+1}/{max_iterations}", iteration / max_iterations)

            if iteration > 0 and last_benchmark:
                prev_context = {
                    "previous_metrics": last_benchmark.metrics,
                    "passed": last_benchmark.passed_threshold,
                    "analysis": getattr(last_benchmark, "analysis", ""),
                }
            else:
                prev_context = None

            if progress:
                await progress("implementer", f"Implementing (iteration {iteration+1})...", 0.0)
            impl = await self.implementer.implement(
                paper_id, progress=progress,
                previous_benchmark_context=prev_context,
            )
            iter_result["implementer"] = {"completed": impl is not None, "id": impl.id if impl else None}
            if not impl:
                results["iterations"].append(iter_result)
                break

            impls = await self.db.list_implementations(paper_id)
            impl_idx = len(impls) - 1

            if progress:
                await progress("prototyper", "Prototyping...", 0.0)
            proto = await self.prototyper.prototype(paper_id, progress=progress)
            iter_result["prototyper"] = {"completed": proto is not None}
            if not proto:
                results["iterations"].append(iter_result)
                break

            if progress:
                await progress("benchmarker", "Benchmarking...", 0.0)
            bench = await self.benchmarker.benchmark(
                paper_id, progress=progress, impl_version_idx=impl_idx,
            )
            iter_result["benchmarker"] = {
                "completed": bench is not None,
                "passed": bench.passed_threshold if bench else False,
            }

            if bench and bench.passed_threshold:
                results["iterations"].append(iter_result)
                results["status"] = "passed"
                results["total_iterations"] = iteration + 1
                return results

            last_benchmark = bench
            iteration += 1

        results["status"] = "max_iterations"
        results["total_iterations"] = iteration
        return results
