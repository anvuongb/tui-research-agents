"""Worker methods for PapersScreen — search, collect, distill, implement,
prototype, and benchmark execution.

Extracted from papers.py to keep the screen file focused on composition
and event routing. Mixed into PapersScreen.
"""

from __future__ import annotations

import asyncio

from textual.widgets import DataTable, Label

from tui_agents.app.messages import (
    DistillationReady,
    ImplementationReady,
    PapersUpdated,
    ProgressUpdate,
    SearchResultsReady,
)
from tui_agents.sources.arxiv import SearchResult


class PapersWorkers:
    """Async worker orchestration for the Papers screen."""

    async def _run_search(self, query: str) -> None:
        label = self.query_one("#progress-label", Label)
        label.update(f"Searching for: {query}...")

        async def progress_cb(stage: str, msg: str, pct: float) -> None:
            self.post_message(ProgressUpdate("search", stage, msg, pct))

        async def search_worker() -> None:
            try:
                results = await self.app.orchestrator.search_papers(
                    query, max_results=20, progress=progress_cb
                )
                self._search_results = results
                self.post_message(SearchResultsReady(results))
            except Exception as e:
                self.post_message(ProgressUpdate("search", "error", str(e), 0.0))

        self.run_worker(search_worker(), exclusive=True)

    async def _collect_all_results(self) -> None:
        label = self.query_one("#progress-label", Label)
        label.update("Collecting all search results...")
        results_to_collect = list(self._search_results)
        self._search_results = []
        table = self.query_one("#papers-table", DataTable)
        table.clear()

        async def progress_cb(stage: str, msg: str, pct: float) -> None:
            self.post_message(ProgressUpdate("collect", stage, msg, pct))

        async def collect_worker() -> None:
            results = results_to_collect
            collected = 0
            for i, result in enumerate(results):
                try:
                    paper = await self.app.orchestrator.collect_single_paper(
                        result, progress=progress_cb
                    )
                    if paper:
                        collected += 1
                        self.post_message(ProgressUpdate(
                            "collect", "collecting",
                            f"Collected {collected}/{len(results)}: {paper.title[:60]}",
                            (i + 1) / len(results),
                        ))
                except Exception as e:
                    self.post_message(ProgressUpdate("collect", "error", str(e), 0))
            self.post_message(PapersUpdated())

        self.run_worker(collect_worker(), exclusive=True)

    async def _collect_single(self, result: SearchResult) -> None:
        async def progress_cb(stage: str, msg: str, pct: float) -> None:
            self.post_message(ProgressUpdate("collect", stage, msg, pct))

        async def collect_worker() -> None:
            try:
                paper = await self.app.orchestrator.collect_single_paper(result, progress=progress_cb)
                if paper:
                    self.post_message(ProgressUpdate(
                        "collect", "done",
                        f"Collected: {paper.title[:80]}", 1.0
                    ))
                    self.post_message(PapersUpdated())
            except Exception as e:
                self.post_message(ProgressUpdate("collect", "error", str(e), 0))

        self.run_worker(collect_worker(), exclusive=True)

    async def _distill_paper(self, paper_id: str) -> None:
        async def progress_cb(stage: str, msg: str, pct: float) -> None:
            self.post_message(ProgressUpdate("distill", stage, msg, pct))

        async def distill_worker() -> None:
            try:
                distillation = await self.app.orchestrator.distill_paper(
                    paper_id, progress=progress_cb
                )
                if distillation:
                    self.post_message(DistillationReady(paper_id, distillation))
                    self.post_message(PapersUpdated())
            except Exception as e:
                self.post_message(ProgressUpdate("distill", "error", str(e), 0))

        self.run_worker(distill_worker(), exclusive=True)

    async def _implement_paper(self, paper_id: str) -> None:
        self._needs_github_link = False

        async def progress_cb(stage: str, msg: str, pct: float) -> None:
            if stage == "needs_github_link":
                self._needs_github_link = True
            self.post_message(ProgressUpdate("implement", stage, msg, pct))

        async def implement_worker() -> None:
            try:
                impl = await self.app.orchestrator.implement_paper(
                    paper_id, progress=progress_cb
                )
                if impl:
                    self.post_message(ImplementationReady(
                        paper_id, len(impl.code), impl.dependencies
                    ))
                    self.post_message(PapersUpdated())
                    return

                if self._needs_github_link:
                    self.post_message(ProgressUpdate(
                        "implement", "waiting_input",
                        "References may not match. Enter a GitHub URL or skip.", 0.3
                    ))
                    from tui_agents.app.screens.github_link_modal import GitHubLinkModal

                    def push_modal() -> None:
                        modal = GitHubLinkModal(
                            "The GitHub search found repositories that may not be related to this paper."
                        )

                        async def on_dismiss(result: str | None) -> None:
                            if result:
                                self.post_message(ProgressUpdate(
                                    "implement", "github",
                                    f"Loading user-provided repo: {result}", 0.15
                                ))
                                retry_impl = await self.app.orchestrator.implement_paper(
                                    paper_id, progress=progress_cb, github_url=result, skip_eval=True
                                )
                                if retry_impl:
                                    self.post_message(ImplementationReady(
                                        paper_id, len(retry_impl.code), retry_impl.dependencies
                                    ))
                                    self.post_message(PapersUpdated())
                            else:
                                self.post_message(ProgressUpdate(
                                    "implement", "github",
                                    "Skipping relevance check, proceeding with references...", 0.15
                                ))
                                retry_impl = await self.app.orchestrator.implement_paper(
                                    paper_id, progress=progress_cb,
                                    github_url="__skip_eval__", skip_eval=True
                                )
                                if retry_impl:
                                    self.post_message(ImplementationReady(
                                        paper_id, len(retry_impl.code), retry_impl.dependencies
                                    ))
                                    self.post_message(PapersUpdated())

                        self.app.push_screen(modal, on_dismiss)

                    push_modal()
            except Exception as e:
                self.post_message(ProgressUpdate("implement", "error", str(e), 0))

        self.run_worker(implement_worker(), exclusive=True)

    async def _prototype_paper(self, paper_id: str) -> None:
        async def progress_cb(stage: str, msg: str, pct: float) -> None:
            self.post_message(ProgressUpdate("prototype", stage, msg, pct))

        async def prototype_worker() -> None:
            try:
                result = await self.app.orchestrator.prototype_paper(
                    paper_id, progress=progress_cb
                )
                if result:
                    self.post_message(ProgressUpdate(
                        "prototype", "done",
                        "Prototype created", 1.0
                    ))
                    self.post_message(PapersUpdated())
            except Exception as e:
                self.post_message(ProgressUpdate("prototype", "error", str(e), 0))

        self.run_worker(prototype_worker(), exclusive=True)

    async def _start_benchmark(self, paper_id: str, version_idx: int) -> None:
        async def progress_cb(stage: str, msg: str, pct: float) -> None:
            self.post_message(ProgressUpdate("benchmark", stage, msg, pct))

        async def bench_worker() -> None:
            try:
                bench = await self.app.orchestrator.benchmark_paper(
                    paper_id, progress=progress_cb, impl_version_idx=version_idx,
                )
                if bench:
                    passed = "PASSED" if bench.passed_threshold else "FAILED"
                    self.post_message(ProgressUpdate(
                        "benchmark", "done",
                        f"Benchmark {passed} — {len(bench.metrics)} metrics", 1.0,
                    ))
                    self.post_message(PapersUpdated())
                    await self._refresh_library()
            except Exception as e:
                self.post_message(ProgressUpdate("benchmark", "error", str(e), 0))

        asyncio.create_task(bench_worker())
