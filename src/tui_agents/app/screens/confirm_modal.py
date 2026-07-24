from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Header, Label, Static


class ConfirmModal(Screen):
    CSS = """
    Screen {
        align: center middle;
    }
    #confirm-container {
        width: 50;
        border: solid $error;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, title: str, message: str):
        super().__init__()
        self._title_text = title
        self._message = message

    def compose(self) -> ComposeResult:
        with Container(id="confirm-container"):
            yield Label(self._title_text, classes="card-title")
            yield Static("")
            yield Static(self._message)
            yield Static("")
            with Horizontal():
                yield Button("Cancel", id="cancel-btn", variant="default")
                yield Button("Delete", id="confirm-delete-btn", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-delete-btn":
            self.dismiss(True)
        elif event.button.id == "cancel-btn":
            self.dismiss(False)

    BINDINGS = [("escape", "cancel", "Cancel")]
    def action_cancel(self) -> None:
        self.dismiss(False)
