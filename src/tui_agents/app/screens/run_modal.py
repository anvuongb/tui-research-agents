from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Header, Label, Static, TextArea


class RunModal(Screen):
    CSS = """
    Screen {
        align: center middle;
    }
    #run-container {
        width: 80%;
        height: 90%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #run-output {
        height: 3fr;
        min-height: 10;
        border: solid $primary-background;
    }
    #run-output TextArea {
        height: 1fr;
    }
    #run-status {
        color: $accent;
        text-style: bold;
    }
    """

    def __init__(
        self,
        paper_title: str,
        code_preview: str,
        estimate_seconds: int,
        timeout: int = 300,
        memory_mb: int = 4096,
    ):
        super().__init__()
        self._paper_title = paper_title
        self._code_preview = code_preview[:8000]
        self._estimate = estimate_seconds
        self._timeout = timeout
        self._memory_mb = memory_mb
        self._confirmed = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="run-container"):
            yield Label(
                f"Run Prototype: {self._paper_title[:60]}", id="run-status"
            )
            yield Static(
                f"Estimated runtime: ~{self._estimate}s  |  Timeout: {self._timeout}s  |  Memory: {self._memory_mb}MB\n"
                f"Network: BLOCKED  |  Filesystem: READ-ONLY"
            )
            yield Static("")
            yield Label("Code Preview:", classes="card-title")
            with VerticalScroll(id="run-output"):
                yield TextArea.code_editor(
                    text=self._code_preview,
                    language="python",
                    read_only=True,
                    show_line_numbers=True,
                )
            yield Label("", id="run-progress")
            with Horizontal():
                yield Button("Cancel", id="cancel-btn", variant="default")
                yield Button("Run", id="run-btn", variant="primary")

    @on(Button.Pressed, "#run-btn")
    def on_run_pressed(self, event: Button.Pressed) -> None:
        if not self._confirmed:
            self._confirmed = True
            event.button.disabled = True
            self.query_one("#cancel-btn", Button).disabled = True
            self.dismiss("start")

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    BINDINGS = [("escape", "cancel", "Cancel")]
    def action_cancel(self) -> None:
        self.dismiss(None)
