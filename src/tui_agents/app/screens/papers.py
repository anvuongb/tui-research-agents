from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, DataTable, Input, Label, Static

from tui_agents.app.messages import (
    DistillationReady,
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

        yield DataTable(id="papers-table", cursor_type="row")

        with Vertical(id="detail-panel"):
            yield Label("Select a paper to view details", id="detail-title")
            yield Static("", id="detail-authors")
            yield Static("", id="detail-year")
            yield Static("", id="detail-source")
            yield Static("", id="detail-abstract")

        with Horizontal(id="action-bar"):
            yield Button("Collect Selected", id="collect-btn", variant="primary")
            yield Button("Distill Selected", id="distill-btn", variant="warning")
            yield Button("Refresh Library", id="refresh-btn", variant="default")

    def on_mount(self) -> None:
        table = self.query_one("#papers-table", DataTable)
        table.add_columns("Title", "Source", "Year", "Status")
        table.show_header = True

    async def on_tab_focus(self) -> None:
        await self._refresh_library()

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

    @on(Button.Pressed, "#refresh-btn")
    async def on_refresh(self) -> None:
        await self._refresh_library()

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

    async def update_progress(self, message: ProgressUpdate) -> None:
        label = self.query_one("#progress-label", Label)
        pct = int(message.percent * 100)
        label.update(f"[{message.stage}] {message.message_text} ({pct}%)")

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
