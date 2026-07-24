from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static
from textual.timer import Timer

from tui_agents.storage.models import StageStatus


class DashboardScreen(Vertical):
    id = "dashboard-screen"

    _refresh_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Static("Dashboard", classes="section-title")

        with Horizontal():
            with Vertical(classes="card"):
                yield Static("Papers", classes="card-title")
                yield Static("")
                yield Static(" Total: --", id="stat-total", classes="list-item")
                yield Static(" Collected: --", id="stat-collected", classes="list-item")
                yield Static(" Distilled: --", id="stat-distilled", classes="list-item")
                yield Static(" Implemented: --", id="stat-implemented", classes="list-item")

            with Vertical(classes="card"):
                yield Static("Pipeline Status", classes="card-title")
                yield Static("")
                yield Static(" In Progress: --", id="stat-in-progress", classes="list-item")
                yield Static(" Completed: --", id="stat-completed", classes="list-item")
                yield Static(" Failed: --", id="stat-failed", classes="list-item")

        yield Static("Pipeline Stages", classes="section-title")

        with Horizontal():
            for stage, icon in [
                ("Collector", "⬇"),
                ("Distiller", "🧠"),
                ("Implementer", "💻"),
                ("Prototyper", "🔧"),
                ("Benchmarker", "📊"),
            ]:
                with Vertical(classes="card"):
                    yield Static(f"{icon} {stage}", classes="card-title status-pending")
                    yield Static(" Pending", id=f"stage-{stage.lower()}", classes="card-subtitle")

        yield Static("Quick Actions", classes="section-title")

        with Horizontal():
            with Vertical(classes="card"):
                yield Static("Search Papers", classes="card-title")
                yield Static(" Switch to Papers tab (Ctrl+P)", classes="card-subtitle")

            with Vertical(classes="card"):
                yield Static("Run Pipeline", classes="card-title")
                yield Static(" Switch to Pipeline tab (Ctrl+L)", classes="card-subtitle")

    def on_mount(self) -> None:
        self._refresh_timer = self.set_interval(5.0, self._refresh_stats)

    async def on_tab_focus(self) -> None:
        await self._refresh_stats()

    async def _refresh_stats(self) -> None:
        try:
            db = self.app.orchestrator.db

            total = await db.count_papers()
            collected = await db.count_papers(status="collected")
            distilled = await db.count_papers(status="distilled")
            implemented = await db.count_papers(status="implemented")

            self.query_one("#stat-total", Static).update(f" Total: {total}")
            self.query_one("#stat-collected", Static).update(f" Collected: {collected}")
            self.query_one("#stat-distilled", Static).update(f" Distilled: {distilled}")
            self.query_one("#stat-implemented", Static).update(f" Implemented: {implemented}")

            in_progress = 0
            completed = 0
            failed = 0

            papers = await db.list_papers(limit=1000)
            for p in papers:
                run = await db.get_latest_run(p.id, "distiller") if False else None
            self.query_one("#stat-in-progress", Static).update(f" In Progress: {in_progress}")
            self.query_one("#stat-completed", Static).update(f" Completed: {completed}")
            self.query_one("#stat-failed", Static).update(f" Failed: {failed}")

        except Exception:
            pass
