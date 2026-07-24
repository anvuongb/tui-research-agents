from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Button, Header, Label, Static, TextArea


class CodeViewer(Screen):
    CSS = """
    Screen {
        background: $surface;
    }
    Vertical {
        height: 1fr;
    }
    TextArea {
        height: 85%;
    }
    #code-label {
        color: $accent;
        text-style: bold;
        padding: 1 2;
    }
    """

    def __init__(self, title: str, code: str, dependencies: list[str], source_url: str = ""):
        super().__init__()
        from tui_agents.agents.base import BaseAgent
        self._title = title
        self._code = BaseAgent.strip_code_fences(code)
        self._dependencies = dependencies
        self._source_url = source_url

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical():
            yield Label(f"Implementation: {self._title[:80]}", id="code-label")
            if self._source_url:
                yield Static(f"Source: {self._source_url}", classes="card-subtitle")
            yield TextArea.code_editor(
                text=self._code,
                language="python",
                read_only=True,
                show_line_numbers=True,
                theme="vscode_dark",
            )
            deps = ", ".join(self._dependencies[:8])
            if len(self._dependencies) > 8:
                deps += f" (+{len(self._dependencies) - 8} more)"
            yield Static(f"Dependencies: {deps}", classes="list-item")
            with Container():
                yield Button("Close", id="close-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.app.pop_screen()

    BINDINGS = [("escape", "dismiss", "Close")]
    def action_dismiss(self) -> None:
        self.app.pop_screen()
