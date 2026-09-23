from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static


class GitHubLinkModal(Screen):
    CSS = """
    Screen {
        align: center middle;
    }
    #modal-container {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, reason: str):
        super().__init__()
        self._reason = reason

    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Label("No matching references found", classes="card-title")
            yield Static("")
            yield Static(f"The GitHub search found repositories that may not\nbe related to this paper.\n")
            yield Static(f"Reason: {self._reason[:200]}", classes="card-subtitle")
            yield Static("")
            yield Label("Enter a GitHub URL to load instead:")
            yield Input(
                placeholder="github.com/user/repo",
                id="gh-url-input",
            )
            yield Static("")
            with Horizontal():
                yield Button("Skip — use what we found", id="skip-btn", variant="default")
                yield Button("Submit", id="submit-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit-btn":
            url = self.query_one("#gh-url-input", Input).value.strip()
            self.dismiss(url if url else None)
        elif event.button.id == "skip-btn":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        url = event.value.strip()
        self.dismiss(url if url else None)

    BINDINGS = [("escape", "skip", "Skip")]
    def action_skip(self) -> None:
        self.dismiss(None)
