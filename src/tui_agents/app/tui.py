from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from tui_agents.agents.orchestrator import Orchestrator
from tui_agents.app.messages import ProgressUpdate
from tui_agents.app.screens.benchmarks import BenchmarksScreen
from tui_agents.app.screens.config_screen import ConfigScreen
from tui_agents.app.screens.dashboard import DashboardScreen
from tui_agents.app.screens.papers import PapersScreen
from tui_agents.app.screens.pipeline import PipelineScreen


CSS = """
Screen {
    background: $surface;
}

Header {
    dock: top;
    background: $primary;
    color: $text;
}

Footer {
    dock: bottom;
    background: $primary-background;
    color: $text-muted;
}

TabbedContent {
    height: 1fr;
}

TabPane {
    padding: 0 2;
}

#dashboard-screen, #papers-screen, #pipeline-screen, #benchmarks-screen, #config-screen {
    overflow-y: auto;
}

.container {
    height: auto;
}

.status-bar {
    background: $primary-background;
    color: $text-muted;
    padding: 1 2;
    dock: bottom;
    height: 3;
}

.status-label {
    color: $text;
}

.status-value {
    color: $accent;
}

.section-title {
    color: $primary;
    text-style: bold;
    padding: 0;
}

.card {
    border: solid $primary-background;
    padding: 1 2;
    margin: 1 0;
}

.card-title {
    color: $accent;
    text-style: bold;
}

.card-subtitle {
    color: $text-muted;
}

.list-item {
    padding: 0 1;
    color: $text;
}

.list-item-alt {
    padding: 0 1;
    color: $text;
    background: $primary-background;
}

.status-pending {
    color: $warning;
}

.status-in-progress {
    color: $primary;
}

.status-completed {
    color: $success;
}

.status-failed {
    color: $error;
}

Input {
    margin: 1 0;
}

Button {
    margin: 0 1;
}

DataTable {
    height: 1fr;
}

#search-input {
    width: 100%;
    border: solid $accent;
    margin: 0;
}

#progress-label {
    color: $primary;
    padding: 0 1;
    background: $panel;
    min-height: 1;
    max-height: 12;
    margin: 0;
}

#search-bar {
    margin: 0;
    height: auto;
}

#detail-panel {
    background: $panel;
    padding: 1 2;
    border: solid $primary-background;
    height: 1fr;
}

#content-area {
    height: 1fr;
    margin: 1 0;
}

#content-area DataTable {
    width: 3fr;
}

#content-area #detail-panel {
    width: 2fr;
}

#impl-controls {
    height: auto;
    max-height: 5;
    min-height: 1;
}

#impl-controls Button {
    width: auto;
    # max-width: 5;
    min-width: 1;
    padding: 0 1;
}

#impl-controls Static {
    width: auto;
    padding: 0 1;
}

#detail-title {
    color: $accent;
    text-style: bold;
}

#detail-abstract {
    color: $text;
    margin: 1 0;
}

#action-bar {
    padding: 0 1;
    background: $panel;
    height: auto;
    align: center middle;
}

#search-bar {
    padding: 1 0;
    background: $panel;
    max-height: 20%;
}

.error-text {
    color: $error;
}
"""


class TuiAgentsApp(App):
    CSS = CSS
    TITLE = "TUI Agents — Research Paper Agent Pipeline"
    SUB_TITLE = "Collect • Distill • Implement • Prototype • Benchmark"

    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+d", "switch_tab('dashboard-tab')", "Dashboard", show=True),
        Binding("ctrl+p", "switch_tab('papers-tab')", "Papers", show=True),
        Binding("ctrl+l", "switch_tab('pipeline-tab')", "Pipeline", show=True),
        Binding("ctrl+b", "switch_tab('benchmarks-tab')", "Benchmarks", show=True),
        Binding("ctrl+g", "switch_tab('config-tab')", "Config", show=True),
    ]

    def __init__(self, orchestrator: Orchestrator):
        super().__init__()
        self.orchestrator = orchestrator
        self._last_switch_time: float = 0.0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            with TabPane(" Dashboard ", id="dashboard-tab"):
                yield DashboardScreen()
            with TabPane(" Papers ", id="papers-tab"):
                yield PapersScreen()
            with TabPane(" Pipeline ", id="pipeline-tab"):
                yield PipelineScreen()
            with TabPane(" Benchmarks ", id="benchmarks-tab"):
                yield BenchmarksScreen()
            with TabPane(" Config ", id="config-tab"):
                yield ConfigScreen()
        yield Footer()

    async def _focus_screen(self, pane_id: str) -> None:
        screen_mapping = {
            "dashboard-tab": "dashboard-screen",
            "papers-tab": "papers-screen",
            "pipeline-tab": "pipeline-screen",
            "benchmarks-tab": "benchmarks-screen",
            "config-tab": "config-screen",
        }
        screen_id = screen_mapping.get(pane_id)
        if screen_id:
            try:
                screen = self.query_one(f"#{screen_id}")
                if hasattr(screen, "on_tab_focus"):
                    await screen.on_tab_focus()
            except Exception:
                pass

    def action_switch_tab(self, tab_id: str) -> None:
        import time
        try:
            tabbed = self.query_one(TabbedContent)
            tabbed.active = tab_id
            self._last_switch_time = time.monotonic()
            self.set_timer(0.5, lambda: self._focus_screen(tab_id))
        except Exception:
            pass

    def on_mount(self) -> None:
        self.set_timer(0.5, lambda: self._focus_screen("dashboard-tab"))

    @on(TabbedContent.TabActivated)
    def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        pass

    async def on_progress_update(self, message: ProgressUpdate) -> None:
        papers_screen = self.query_one("#papers-screen", PapersScreen)
        if papers_screen:
            await papers_screen.update_progress(message)
