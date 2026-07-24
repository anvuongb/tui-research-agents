from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static

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
            else:
                yield Static(" Config file not found", classes="status-failed")

        with Container(classes="card"):
            yield Static("Storage", classes="card-title")
            yield Static("")
            if config:
                yield Static(f" Database: {config.database_path}", classes="list-item")
                yield Static(f" Vector Store: {config.chroma_persist_dir}", classes="list-item")
            else:
                yield Static(" Config file not found", classes="status-failed")

        yield Static("Edit config/default.yaml to change settings.", classes="card-subtitle")

    def on_tab_focus(self) -> None:
        pass
