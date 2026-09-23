from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Label, Static

from tui_agents.app.messages import DistillationReady, PapersUpdated, ProgressUpdate


class PipelineScreen(Vertical):
    id = "pipeline-screen"

    def compose(self) -> ComposeResult:
        yield Static("Pipeline", classes="section-title")

        with Container(classes="card"):
            yield Static("Active Pipeline", classes="card-title")
            yield Static("")
            yield Label("No pipeline runs active", id="pipeline-status")

        yield Static("Pipeline Stages", classes="section-title")

        stages = [
            ("collector", "Collector", "Fetch papers from arXiv, Semantic Scholar, or local PDFs"),
            ("distiller", "Distiller", "Extract key insights, methodology, and contributions"),
            ("implementer", "Implementer", "Generate Python implementation code"),
            ("prototyper", "Prototyper", "Create runnable prototype scripts"),
            ("benchmarker", "Benchmarker", "Run benchmarks and evaluate results"),
        ]

        for stage_id, name, desc in stages:
            with Container(classes="card"):
                with Horizontal():
                    yield Static(f"⬇ {name}", classes="card-title status-pending", id=f"stage-title-{stage_id}")
                yield Static(f"  {desc}", classes="card-subtitle")
                yield Static(" Status: pending", id=f"stage-status-{stage_id}", classes="list-item")

        yield Static("Actions", classes="section-title")

        with Horizontal(id="pipeline-actions"):
            yield Button("Run Full Pipeline", id="run-pipeline-btn", variant="primary", disabled=True)
            yield Button("Run Next Stage", id="run-next-btn", variant="warning", disabled=True)

    def on_mount(self) -> None:
        self._update_stage_statuses("collector", "Ready")

    async def on_tab_focus(self) -> None:
        pass

    @on(ProgressUpdate)
    async def on_progress(self, message: ProgressUpdate) -> None:
        status = self.query_one("#pipeline-status", Label)
        status.update(f"[{message.stage}] {message.message_text} ({int(message.percent * 100)}%)")

        stage_map = {
            "search": "collector",
            "collect": "collector",
            "collecting": "collector",
            "extract": "collector",
            "download": "collector",
            "chunk": "collector",
            "embed": "collector",
            "distill": "distiller",
            "loading": "distiller",
            "analyzing": "distiller",
            "paper_text": "implementer",
            "github": "implementer",
            "evaluate": "implementer",
            "needs_github_link": "implementer",
            "generating": "implementer",
            "saving": "implementer",
            "implement": "implementer",
            "implementer": "implementer",
            "prototype": "prototyper",
            "prototyper": "prototyper",
            "benchmarker": "benchmarker",
            "estimating": "benchmarker",
            "building": "benchmarker",
            "running": "benchmarker",
            "running_output": "benchmarker",
            "evaluating": "benchmarker",
            "loop": "orchestrator",
            "pipeline": "orchestrator",
            "done": "orchestrator",
            "error": "orchestrator",
        }

        stage_id = stage_map.get(message.stage)
        if stage_id:
            status_text = message.message_text
            if message.percent >= 1.0:
                self._update_stage_statuses(stage_id, "Completed", "status-completed")
            else:
                self._update_stage_statuses(stage_id, status_text, "status-in-progress")

    def _update_stage_statuses(self, stage_id: str, status_text: str, css_class: str = "status-in-progress") -> None:
        title_widgets = self.query(f"#stage-title-{stage_id}")
        if title_widgets:
            title_widget = title_widgets.first(Static)
            title_widget.remove_class("status-pending")
            title_widget.add_class(css_class)

        status_widgets = self.query(f"#stage-status-{stage_id}")
        if status_widgets:
            status_widget = status_widgets.first(Static)
            status_widget.update(f" Status: {status_text}")

    @on(DistillationReady)
    async def on_distillation_ready(self, message: DistillationReady) -> None:
        self._update_stage_statuses("distiller", "Completed", "status-completed")

    @on(PapersUpdated)
    async def on_papers_updated(self, message: PapersUpdated) -> None:
        self._update_stage_statuses("collector", "Completed", "status-completed")
