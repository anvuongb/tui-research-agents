from textual.app import ComposeResult
from textual.containers import Container
from textual.widget import Widget
from textual.widgets import Static


class BenchmarksScreen(Widget):
    id = "benchmarks-screen"

    def compose(self) -> ComposeResult:
        with Container(classes="dashboard-container"):
            yield Static("📊 Benchmarks", classes="section-title")

            with Container(classes="card"):
                yield Static("No benchmark results yet", classes="card-subtitle")
                yield Static("")
                yield Static("Benchmarks are generated after the Prototyper", classes="list-item")
                yield Static("agent completes and the Benchmarker runs.", classes="list-item")

            yield Static("📈 Thresholds", classes="section-title")

            with Container(classes="card"):
                yield Static("Pass threshold: 0.7", classes="list-item")
                yield Static("Max loop iterations: 5", classes="list-item")
                yield Static("Benchmark iterations: 3", classes="list-item")

    def on_tab_focus(self) -> None:
        pass
