from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Button, DataTable, Input, Label, Static

from tui_agents.app.messages import (
    DistillationReady,
    ImplementationReady,
    PapersUpdated,
    ProgressUpdate,
    SearchResultsReady,
)
from tui_agents.sources.arxiv import SearchResult


class PapersScreen(Vertical):
    id = "papers-screen"

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
        table = self.query_one("#papers-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.coordinate_to_cell_key((table.cursor_row, 0))
            if row_key:
                row_id = row_key.row_key.value
                if row_id:
                    await self._distill_paper(str(row_id))

    @on(Button.Pressed, "#implement-btn")
    async def on_implement_selected(self) -> None:
        table = self.query_one("#papers-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.coordinate_to_cell_key((table.cursor_row, 0))
            if row_key:
                row_id = row_key.row_key.value
                if row_id:
                    await self._implement_paper(str(row_id))

    @on(Button.Pressed, "#prototype-btn")
    async def on_prototype_selected(self) -> None:
        table = self.query_one("#papers-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.coordinate_to_cell_key((table.cursor_row, 0))
            if row_key:
                row_id = row_key.row_key.value
                if row_id:
                    await self._prototype_paper(str(row_id))

    @on(Button.Pressed, "#refresh-btn")
    async def on_refresh(self) -> None:
        await self._refresh_library()

    @on(Button.Pressed, "#delete-paper-btn")
    async def on_delete_paper(self) -> None:
        table = self.query_one("#papers-table", DataTable)
        if table.cursor_row is None:
            return
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0))
        if not row_key or not row_key.row_key.value:
            return
        paper_id = str(row_key.row_key.value)
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
            self.query_one("#detail-title", Label).update("")
            self.query_one("#detail-authors", Static).update("")
            self.query_one("#detail-year", Static).update("")
            self.query_one("#detail-source", Static).update("")
            self.query_one("#detail-abstract", Static).update("")
            for wid in ("detail-distill-summary", "detail-distill-methodology",
                         "detail-distill-contributions", "detail-distill-limitations",
                         "detail-impl-summary"):
                self.query_one(f"#{wid}", Static).update("")
            self.query_one("#impl-controls").styles.display = "none"

        self.app.push_screen(
            ConfirmModal(
                "Delete Paper",
                f"Delete '{paper.title[:50]}' and all related data?\n\n"
                f"This removes:\n"
                f"  \u2022 Distillation\n"
                f"  \u2022 Implementations\n"
                f"  \u2022 Prototype code\n"
                f"  \u2022 Downloaded PDF\n"
                f"  \u2022 ChromaDB embeddings\n\n"
                f"This cannot be undone.",
            ),
            on_confirm,
        )

    @on(DataTable.RowHighlighted, "#papers-table")
    async def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        row_key = event.row_key
        if row_key and row_key.value:
            row_id = str(row_key.value)
            paper = await self.app.orchestrator.db.get_paper(row_id)
            if paper:
                self.query_one("#detail-title", Label).update(paper.title)
                self.query_one("#detail-authors", Static).update(
                    f"Authors: {', '.join(paper.authors[:5])}"
                )
                self.query_one("#detail-year", Static).update(
                    f"Published: {paper.published_date or 'N/A'}"
                )
                self.query_one("#detail-source", Static).update(
                    f"Source: {paper.source.value} | Status: {paper.status}"
                )
                abstract = paper.abstract[:800] + ("..." if len(paper.abstract) > 800 else "")
                self.query_one("#detail-abstract", Static).update(abstract)

                distillation = await self.app.orchestrator.db.get_distillation(row_id)
                if distillation:
                    summary = distillation.summary[:400] + ("..." if len(distillation.summary) > 400 else "")
                    self.query_one("#detail-distill-summary", Static).update(
                        f"\n[bold]Summary:[/] {summary}"
                    )
                    method = distillation.methodology[:300] + ("..." if len(distillation.methodology) > 300 else "")
                    self.query_one("#detail-distill-methodology", Static).update(
                        f"\n[bold]Methodology:[/] {method}"
                    )
                    contribs = "\n  - " + "\n  - ".join(distillation.contributions[:5])
                    self.query_one("#detail-distill-contributions", Static).update(
                        f"\n[bold]Contributions:[/]{contribs}"
                    )
                    lims = "\n  - " + "\n  - ".join(distillation.limitations[:3]) if distillation.limitations else " None noted"
                    self.query_one("#detail-distill-limitations", Static).update(
                        f"\n[bold]Limitations:[/]{lims}"
                    )
                else:
                    self.query_one("#detail-distill-summary", Static).update("")
                    self.query_one("#detail-distill-methodology", Static).update("")
                    self.query_one("#detail-distill-contributions", Static).update("")
                    self.query_one("#detail-distill-limitations", Static).update("")
            else:
                self.query_one("#detail-title", Label).update("")
                self.query_one("#detail-authors", Static).update("")
                self.query_one("#detail-year", Static).update("")
                self.query_one("#detail-source", Static).update("")
                self.query_one("#detail-abstract", Static).update("")
                for wid in ("detail-distill-summary", "detail-distill-methodology",
                             "detail-distill-contributions", "detail-distill-limitations",
                             "detail-impl-summary"):
                    try:
                        self.query_one(f"#{wid}", Static).update("")
                    except Exception:
                        pass
                self.query_one("#impl-controls").styles.display = "none"
                return

            impls = await self.app.orchestrator.db.list_implementations(row_id)

            if impls:
                version_idx = self._impl_versions.get(row_id, 0)
                if version_idx >= len(impls):
                    version_idx = len(impls) - 1
                self._impl_versions[row_id] = version_idx

                impl = impls[version_idx]
                deps = ", ".join(impl.dependencies[:5])
                self.query_one("#detail-impl-summary", Static).update(
                    f"\n[bold]Implementation v{version_idx+1}/{len(impls)}:[/] {len(impl.code)} chars, {len(impl.dependencies)} deps ({deps})"
                )
                self.query_one("#impl-version-label", Static).update(
                    f"v{version_idx+1}/{len(impls)}"
                )
                self.query_one("#impl-controls").styles.display = "block"

                prev_btn = self.query_one("#impl-prev-btn", Button)
                next_btn = self.query_one("#impl-next-btn", Button)
                view_btn = self.query_one("#view-code-btn", Button)
                delete_btn = self.query_one("#delete-impl-btn", Button)
                prev_btn.disabled = (version_idx == 0)
                next_btn.disabled = (version_idx >= len(impls) - 1)
                view_btn.disabled = False
                delete_btn.disabled = False
            else:
                self.query_one("#detail-impl-summary", Static).update(
                    "\n[bold]Implementation:[/] none yet \u2014 click Implement Selected"
                )
                self.query_one("#impl-version-label", Static).update("")
                self.query_one("#impl-controls").styles.display = "block"
                for bid in ("#impl-prev-btn", "#impl-next-btn", "#view-code-btn", "#delete-impl-btn"):
                    self.query_one(bid, Button).disabled = True

    SPINNER = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
    STAGE_ORDER = {
        "search": 0, "collecting": 1, "collect": 2, "download": 3, "extract": 4, "chunk": 5, "embed": 6,
        "loading": 7, "paper_text": 8, "analyzing": 9, "github": 10, "evaluate": 11,
        "generating": 12, "saving": 13, "done": 14, "pipeline": 15,
        "error": 98, "waiting_input": 99,
    }

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

                    self.app.call_from_thread(push_modal)
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
                        f"Prototype created", 1.0
                    ))
                    self.post_message(PapersUpdated())
            except Exception as e:
                self.post_message(ProgressUpdate("prototype", "error", str(e), 0))

        self.run_worker(prototype_worker(), exclusive=True)

    async def _refresh_library(self) -> None:
        table = self.query_one("#papers-table", DataTable)
        table.clear()

        try:
            papers = await self.app.orchestrator.db.list_papers(limit=100)
        except Exception:
            papers = []

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

            table.add_row(
                title,
                paper.source.value,
                paper.published_date or "N/A",
                f"{status_icon} {paper.status}",
                key=paper.id,
            )

        count = len(papers) if papers else 0
        label = self.query_one("#progress-label", Label)
        label.update(f"Library: {count} papers. Use search to find more.") if not self._search_results else None

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
                f"   search result",
                key=f"search-{i}",
            )

        label = self.query_one("#progress-label", Label)
        if message.results:
            label.update(f"Found {len(message.results)} papers. Click 'Collect All' to download and process.")
        else:
            label.update(f"No papers found. The search source may be unreachable or rate-limited.")

    async def on_papers_updated(self, message: PapersUpdated) -> None:
        await self._refresh_library()

    async def on_distillation_ready(self, message: DistillationReady) -> None:
        d = message.distillation
        label = self.query_one("#progress-label", Label)
        label.update(f"Distilled! Summary: {d.summary[:120]}...")
        await self._refresh_library()
        # Re-select the distilled paper to refresh the detail panel
        try:
            table = self.query_one("#papers-table", DataTable)
            for row_idx in range(table.row_count):
                key = table.coordinate_to_cell_key((row_idx, 0))
                if key and key.row_key.value == message.paper_id:
                    table.move_cursor(row=row_idx)
                    break
        except Exception:
            pass

    @on(Button.Pressed, "#view-code-btn")
    async def on_view_code(self, event: Button.Pressed) -> None:
        table = self.query_one("#papers-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.coordinate_to_cell_key((table.cursor_row, 0))
            if row_key and row_key.row_key.value:
                paper_id = str(row_key.row_key.value)
                impls = await self.app.orchestrator.db.list_implementations(paper_id)
                version_idx = self._impl_versions.get(paper_id, 0)
                if 0 <= version_idx < len(impls):
                    impl = impls[version_idx]
                    paper = await self.app.orchestrator.db.get_paper(paper_id)
                    if paper:
                        from tui_agents.app.screens.code_viewer import CodeViewer
                        await self.app.push_screen(CodeViewer(
                            title=paper.title,
                            code=impl.code,
                            dependencies=impl.dependencies,
                        ))

    @on(Button.Pressed, "#impl-prev-btn")
    async def on_impl_prev(self) -> None:
        table = self.query_one("#papers-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.coordinate_to_cell_key((table.cursor_row, 0))
            if row_key and row_key.row_key.value:
                paper_id = str(row_key.row_key.value)
                impls = await self.app.orchestrator.db.list_implementations(paper_id)
                idx = self._impl_versions.get(paper_id, 0)
                if idx > 0:
                    self._impl_versions[paper_id] = idx - 1
                    await self._refresh_detail_panel(paper_id)

    @on(Button.Pressed, "#impl-next-btn")
    async def on_impl_next(self) -> None:
        table = self.query_one("#papers-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.coordinate_to_cell_key((table.cursor_row, 0))
            if row_key and row_key.row_key.value:
                paper_id = str(row_key.row_key.value)
                impls = await self.app.orchestrator.db.list_implementations(paper_id)
                idx = self._impl_versions.get(paper_id, 0)
                if idx < len(impls) - 1:
                    self._impl_versions[paper_id] = idx + 1
                    await self._refresh_detail_panel(paper_id)

    @on(Button.Pressed, "#delete-impl-btn")
    async def on_delete_impl(self) -> None:
        table = self.query_one("#papers-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.coordinate_to_cell_key((table.cursor_row, 0))
            if row_key and row_key.row_key.value:
                paper_id = str(row_key.row_key.value)
                impls = await self.app.orchestrator.db.list_implementations(paper_id)
                idx = self._impl_versions.get(paper_id, 0)
                if 0 <= idx < len(impls):
                    impl = impls[idx]
                    await self.app.orchestrator.db.delete_implementation(impl.id)
                    if paper_id in self._impl_versions:
                        del self._impl_versions[paper_id]
                    await self._refresh_detail_panel(paper_id)

    async def _refresh_detail_panel(self, paper_id: str) -> None:
        table = self.query_one("#papers-table", DataTable)
        for row_idx in range(table.row_count):
            key = table.coordinate_to_cell_key((row_idx, 0))
            if key and key.row_key.value == paper_id:
                event = type("FakeEvent", (), {"row_key": key.row_key})()
                await self.on_row_highlighted(event)
                break

    async def on_implementation_ready(self, message: ImplementationReady) -> None:
        deps_str = ", ".join(message.dependencies[:3])
        label = self.query_one("#progress-label", Label)
        label.update(f"Implemented! {message.code_length} chars, deps: {deps_str}")
        await self._refresh_library()
        try:
            table = self.query_one("#papers-table", DataTable)
            for row_idx in range(table.row_count):
                key = table.coordinate_to_cell_key((row_idx, 0))
                if key and key.row_key.value == message.paper_id:
                    table.move_cursor(row=row_idx)
                    break
        except Exception:
            pass
