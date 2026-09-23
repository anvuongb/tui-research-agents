from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, Static

from tui_agents.app.messages import (
    DistillationReady,
    ImplementationReady,
    PapersUpdated,
    ProgressUpdate,
    SearchResultsReady,
)
from tui_agents.app.screens.papers_detail import PapersDetail
from tui_agents.app.screens.papers_workers import PapersWorkers
from tui_agents.sources.arxiv import SearchResult


class PapersScreen(PapersWorkers, PapersDetail, Vertical):
    id = "papers-screen"

    SPINNER = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
    STAGE_ORDER = {
        "search": 0, "collecting": 1, "collect": 2, "download": 3, "extract": 4, "chunk": 5, "embed": 6,
        "loading": 7, "paper_text": 8, "analyzing": 9, "github": 10, "evaluate": 11,
        "needs_github_link": 12, "generating": 13, "saving": 14, "done": 15,
        "estimating": 16, "building": 17, "running": 18, "running_output": 19, "evaluating": 20,
        "implementer": 21, "prototyper": 22, "benchmarker": 23, "loop": 24, "pipeline": 25,
        "error": 98, "waiting_input": 99,
    }

    def __init__(self):
        super().__init__()
        self._search_results: list[SearchResult] = []
        self._selected_index: int = -1

    def compose(self) -> ComposeResult:
        yield Label("Search", classes="section-title")
        yield Input(
            placeholder="Type a query (e.g. diffusion models optimal transport) and press Enter...",
            id="search-input",
        )
        with Horizontal(id="search-bar"):
            yield Button("Search", id="search-btn", variant="primary")
            yield Button("Collect All", id="collect-all-btn", variant="success")
            yield Button("Clear", id="clear-btn", variant="default")

        yield Label("Click the search bar above, type a query, and press Enter to search", id="progress-label")

        with Horizontal(id="content-area"):
            yield DataTable(id="papers-table", cursor_type="row")

            with VerticalScroll(id="detail-panel"):
                yield Label("Select a paper to view details", id="detail-title")
                yield Static("", id="detail-authors")
                yield Static("", id="detail-year")
                yield Static("", id="detail-source")
                yield Static("", id="detail-abstract")
                yield Static("", id="detail-distill-summary")
                yield Static("", id="detail-distill-methodology")
                yield Static("", id="detail-distill-contributions")
                yield Static("", id="detail-distill-limitations")
                yield Static("", id="detail-impl-summary")
                with Horizontal(id="impl-controls"):
                    yield Button("◀", id="impl-prev-btn", variant="default")
                    yield Static("v1/1", id="impl-version-label")
                    yield Button("▶", id="impl-next-btn", variant="default")
                    yield Button("View Code", id="view-code-btn", variant="primary")
                    yield Button("Delete", id="delete-impl-btn", variant="error")
                    yield Button("Run Prototype", id="run-proto-btn", variant="success")

        with Horizontal(id="action-bar"):
            yield Button("Collect Selected", id="collect-btn", variant="primary")
            yield Button("Distill Selected", id="distill-btn", variant="warning")
            yield Button("Implement Selected", id="implement-btn", variant="success")
            yield Button("Prototype Selected", id="prototype-btn", variant="error")
            yield Button("Refresh Library", id="refresh-btn", variant="default")
            yield Button("Delete Paper", id="delete-paper-btn", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#papers-table", DataTable)
        table.add_columns("Title", "Source", "Year", "Status")
        table.show_header = True
        self._spinner_frame = 0
        self._spinner_timer = self.set_interval(0.15, self._tick_spinner)
        self._progress_stages: dict[str, dict[str, str]] = {}
        self._progress_source: str = ""
        self._impl_versions: dict[str, int] = {}

    def _tick_spinner(self) -> None:
        if not hasattr(self, "_progress_stages"):
            return
        has_running = any(
            info.get("status") in ("⟳",)
            for info in self._progress_stages.values()
        )
        if not has_running and self._progress_stages:
            return
        if not self._progress_stages:
            return
        self._spinner_frame = (self._spinner_frame + 1) % 4
        self._render_progress()

    async def on_tab_focus(self) -> None:
        await self._refresh_library()

    @on(Input.Submitted, "#search-input")
    async def on_search_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip():
            await self._run_search(event.value.strip())

    @on(Button.Pressed, "#search-btn")
    async def on_search_button(self) -> None:
        search_input = self.query_one("#search-input", Input)
        if search_input.value.strip():
            await self._run_search(search_input.value.strip())

    @on(Button.Pressed, "#clear-btn")
    async def on_clear(self) -> None:
        self._search_results = []
        await self._refresh_library()

    @on(Button.Pressed, "#collect-all-btn")
    async def on_collect_all(self) -> None:
        if self._search_results:
            await self._collect_all_results()

    @on(Button.Pressed, "#collect-btn")
    async def on_collect_selected(self) -> None:
        table = self.query_one("#papers-table", DataTable)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self._search_results):
            result = self._search_results[table.cursor_row]
            await self._collect_single(result)

    @on(Button.Pressed, "#distill-btn")
    async def on_distill_selected(self) -> None:
        paper_id = self._selected_paper_id()
        if paper_id:
            await self._distill_paper(paper_id)

    @on(Button.Pressed, "#implement-btn")
    async def on_implement_selected(self) -> None:
        paper_id = self._selected_paper_id()
        if paper_id:
            await self._implement_paper(paper_id)

    @on(Button.Pressed, "#prototype-btn")
    async def on_prototype_selected(self) -> None:
        paper_id = self._selected_paper_id()
        if paper_id:
            await self._prototype_paper(paper_id)

    @on(Button.Pressed, "#refresh-btn")
    async def on_refresh(self) -> None:
        await self._refresh_library()

    @on(Button.Pressed, "#delete-paper-btn")
    async def on_delete_paper(self) -> None:
        paper_id = self._selected_paper_id()
        if not paper_id:
            return
        paper = await self.app.orchestrator.db.get_paper(paper_id)
        if not paper:
            return

        from tui_agents.app.screens.confirm_modal import ConfirmModal

        async def on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            await self.app.orchestrator.delete_paper(paper_id)
            if paper_id in self._impl_versions:
                del self._impl_versions[paper_id]
            self.query_one("#progress-label", Label).update(f"Deleted: {paper.title[:60]}")
            await self._refresh_library()
            self._clear_detail_panel()

        self.app.push_screen(
            ConfirmModal(
                "Delete Paper",
                f"Delete '{paper.title[:50]}' and all related data?\n\n"
                f"This removes:\n"
                f"  • Distillation\n"
                f"  • Implementations\n"
                f"  • Prototype code\n"
                f"  • Downloaded PDF\n"
                f"  • ChromaDB embeddings\n\n"
                f"This cannot be undone.",
            ),
            on_confirm,
        )

    def _render_progress(self) -> None:
        if not self._progress_stages:
            return
        try:
            label = self.query_one("#progress-label", Label)
        except Exception:
            return
        lines: list[str] = []
        for stage, info in sorted(
            self._progress_stages.items(),
            key=lambda x: self.STAGE_ORDER.get(x[0], 50),
        ):
            status = info["status"]
            if status == "⟳":
                status = self.SPINNER[self._spinner_frame % len(self.SPINNER)]
            lines.append(f"  {status} [{stage}] {info['msg']} ({info['pct']})")
        lines.append("")
        label.update("\n".join(lines))

    async def update_progress(self, message: ProgressUpdate) -> None:
        if not hasattr(self, "_progress_stages") or not hasattr(self, "_progress_source"):
            self._progress_stages: dict[str, dict[str, str]] = {}
            self._progress_source: str = ""

        if message.source != self._progress_source or message.stage in ("loading", "search"):
            self._progress_stages = {}
            self._progress_source = message.source

        incoming_order = self.STAGE_ORDER.get(message.stage, 50)
        for stage, info in self._progress_stages.items():
            existing_order = self.STAGE_ORDER.get(stage, 50)
            if existing_order < incoming_order and info["status"] == "⟳":
                info["status"] = "✓"

        status = "✓" if message.percent >= 1.0 else ("✗" if message.stage == "error" else "⟳")
        self._progress_stages[message.stage] = {
            "msg": message.message_text,
            "pct": f"{int(message.percent * 100)}%",
            "status": status,
        }
        self._render_progress()

    async def _refresh_library(self) -> None:
        table = self.query_one("#papers-table", DataTable)
        table.clear()

        try:
            papers = await self.app.orchestrator.db.list_papers(limit=100)
        except Exception:
            papers = []

        from textual.widgets._data_table import DuplicateKey

        for paper in papers:
            status_icon = {
                "new": "⚪",
                "collected": "🟢",
                "distilled": "🟡",
                "implemented": "🔵",
                "prototyped": "🟣",
                "benchmarked": "✅",
            }.get(paper.status, "⚪")

            title = paper.title
            if len(title) > 60:
                title = title[:57] + "..."

            try:
                table.add_row(
                    title,
                    paper.source.value,
                    paper.published_date or "N/A",
                    f"{status_icon} {paper.status}",
                    key=paper.id,
                )
            except DuplicateKey:
                pass

        count = len(papers) if papers else 0
        label = self.query_one("#progress-label", Label)
        if not self._search_results:
            label.update(f"Library: {count} papers. Use search to find more.")

    async def on_search_results_ready(self, message: SearchResultsReady) -> None:
        table = self.query_one("#papers-table", DataTable)
        table.clear()

        for i, result in enumerate(message.results):
            title = result.title
            if len(title) > 60:
                title = title[:57] + "..."

            table.add_row(
                title,
                result.source,
                result.published_date or "N/A",
                "   search result",
                key=f"search-{i}",
            )

        label = self.query_one("#progress-label", Label)
        if message.results:
            label.update(f"Found {len(message.results)} papers. Click 'Collect All' to download and process.")
        else:
            label.update("No papers found. The search source may be unreachable or rate-limited.")

    async def on_papers_updated(self, message: PapersUpdated) -> None:
        await self._refresh_library()

    async def on_distillation_ready(self, message: DistillationReady) -> None:
        d = message.distillation
        label = self.query_one("#progress-label", Label)
        label.update(f"Distilled! Summary: {d.summary[:120]}...")
        await self._refresh_library()
        await self._move_cursor_to_paper(message.paper_id)

    @on(Button.Pressed, "#view-code-btn")
    async def on_view_code(self, event: Button.Pressed) -> None:
        await self._view_selected_code()

    @on(Button.Pressed, "#run-proto-btn")
    async def on_run_prototype(self) -> None:
        paper_id = self._selected_paper_id()
        if not paper_id:
            return
        paper = await self.app.orchestrator.db.get_paper(paper_id)
        if not paper or paper.status != "prototyped":
            return

        impls = await self.app.orchestrator.db.list_implementations(paper_id)
        version_idx = self._impl_versions.get(paper_id, len(impls) - 1)
        impl = impls[version_idx] if 0 <= version_idx < len(impls) else None
        if not impl:
            return

        from pathlib import Path

        from tui_agents.agents.runtime_estimator import RuntimeEstimator
        from tui_agents.app.screens.run_modal import RunModal

        code_dir = Path(self.app.orchestrator.config.code_dir) / paper_id / impl.id[:8]
        proto_path = code_dir / "prototype.py"
        prototype_code = proto_path.read_text() if proto_path.exists() else impl.code

        estimator = RuntimeEstimator(self.app.orchestrator.llm)
        estimate = await estimator.estimate(impl, prototype_code)
        est_seconds = estimate.get("estimate_seconds", 60)

        runner_config = self.app.orchestrator.config
        timeout = runner_config.get("runner", "timeout", default=300)
        memory_mb = runner_config.get("runner", "memory_mb", default=4096)

        modal = RunModal(
            paper_title=paper.title,
            code_preview=prototype_code,
            estimate_seconds=est_seconds,
            timeout=timeout,
            memory_mb=memory_mb,
        )

        async def on_run_confirm(result: str | None) -> None:
            if result == "start":
                await self._start_benchmark(paper_id, version_idx)

        self.app.push_screen(modal, on_run_confirm)

    @on(Button.Pressed, "#impl-prev-btn")
    async def on_impl_prev(self) -> None:
        await self._step_impl_version(-1)

    @on(Button.Pressed, "#impl-next-btn")
    async def on_impl_next(self) -> None:
        await self._step_impl_version(+1)

    @on(Button.Pressed, "#delete-impl-btn")
    async def on_delete_impl(self) -> None:
        await self._delete_selected_impl()

    async def on_implementation_ready(self, message: ImplementationReady) -> None:
        deps_str = ", ".join(message.dependencies[:3])
        label = self.query_one("#progress-label", Label)
        label.update(f"Implemented! {message.code_length} chars, deps: {deps_str}")
        await self._refresh_library()
        await self._move_cursor_to_paper(message.paper_id)
