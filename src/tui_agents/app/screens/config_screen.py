from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Button, Label, Static

from tui_agents.utils.config import load_config


class ConfigScreen(Vertical):
    id = "config-screen"

    def compose(self) -> ComposeResult:
        try:
            config = load_config()
        except FileNotFoundError:
            config = None

        yield Static(" Configuration", classes="section-title")

        with Container(classes="card"):
            yield Static("LLM Settings", classes="card-title")
            yield Static("")
            if config:
                yield Static(f" Model: {config.llm_model}", classes="list-item")
                yield Static(f" Base URL: {config.llm_base_url}", classes="list-item")
                yield Static(f" Temperature: {config.llm_temperature}", classes="list-item")
            else:
                yield Static(" Config file not found", classes="status-failed")

        with Container(classes="card"):
            yield Static("Sources", classes="card-title")
            yield Static("")
            if config:
                yield Static(f" arXiv: {'Enabled' if config.arxiv_enabled else 'Disabled'}", classes="list-item")
                yield Static(f" Semantic Scholar: {'Enabled' if config.semantic_scholar_enabled else 'Disabled'}", classes="list-item")
                yield Static(f" Local PDF: {'Enabled' if config.local_pdf_enabled else 'Disabled'}", classes="list-item")
                yield Static(f" GitHub: {'Enabled' if config.get('github', 'enabled', default=True) else 'Disabled'}", classes="list-item")
            else:
                yield Static(" Config file not found", classes="status-failed")

        with Container(classes="card"):
            yield Static("Cache", classes="card-title")
            yield Static("")
            yield Static(f" GitHub TTL: {config.get('cache', 'github_ttl_seconds', default=86400)}s" if config else " Config not found", classes="list-item")
            yield Label("", id="cache-status")
            yield Button("Clear GitHub Cache", id="clear-cache-btn", variant="warning")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "clear-cache-btn":
            try:
                await self.app.orchestrator.db.clear_github_cache()
                self.query_one("#cache-status", Label).update(" Cache cleared.")
            except Exception as e:
                self.query_one("#cache-status", Label).update(f" Error: {e}")
