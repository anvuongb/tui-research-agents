from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Static, Label, DataTable


class BenchmarksScreen(Vertical):
    id = "benchmarks-screen"

    def compose(self) -> ComposeResult:
        yield Static(" Benchmarks", classes="section-title")

        with Container(classes="card"):
            yield Label("Select a paper in the Papers tab to view its benchmarks", id="bench-paper-label")

        yield DataTable(id="benchmarks-table", cursor_type="row")

        yield Static(" Thresholds", classes="section-title")
        with Container(classes="card"):
            yield Static("Pass threshold: 0.7", classes="list-item")
            yield Static("Max loop iterations: 5", classes="list-item")

    def on_mount(self) -> None:
        table = self.query_one("#benchmarks-table", DataTable)
        table.add_columns("Paper", "Status", "Metrics", "Elapsed", "Passed")
        table.show_header = True

    async def on_tab_focus(self) -> None:
        await self._refresh_benchmarks()

    async def _refresh_benchmarks(self) -> None:
        table = self.query_one("#benchmarks-table", DataTable)
        table.clear()

        try:
            papers = await self.app.orchestrator.db.list_papers(status="benchmarked", limit=50)
            for paper in papers:
                benches = await self.app.orchestrator.db.get_benchmarks(paper.id)
                latest = benches[0] if benches else None
                if latest:
                    metrics_str = ", ".join(f"{k}: {v}" for k, v in list(latest.metrics.items())[:3])
                    if len(metrics_str) > 40:
                        metrics_str = metrics_str[:37] + "..."
                    elapsed = f"{int(float(str(latest.metrics.get('elapsed_seconds', 0))))}s" if "elapsed" in str(latest.metrics) else "N/A"
                    passed_icon = "PASS" if latest.passed_threshold else "FAIL"
                    table.add_row(
                        paper.title[:50],
                        paper.status,
                        metrics_str or "no metrics",
                        elapsed,
                        passed_icon,
                        key=paper.id,
                    )
        except Exception:
            pass

        label = self.query_one("#bench-paper-label", Label)
        rows = table.row_count
        label.update(f"{rows} benchmarked paper{'s' if rows != 1 else ''}")
