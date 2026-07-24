import sys

from tui_agents.agents.orchestrator import Orchestrator
from tui_agents.app.tui import TuiAgentsApp
from tui_agents.llm.client import LLMClient
from tui_agents.storage.database import Database
from tui_agents.storage.vector_store import VectorStore
from tui_agents.utils.config import load_config
from tui_agents.utils.logging import setup_logging


def main() -> None:
    setup_logging()
    config = load_config()
    llm = LLMClient(config)
    database = Database(config.database_path)
    vector_store = VectorStore(
        persist_directory=config.chroma_persist_dir,
        collection_name=config.chroma_collection_name,
    )
    orchestrator = Orchestrator(
        config=config,
        database=database,
        vector_store=vector_store,
        llm=llm,
    )
    app = TuiAgentsApp(orchestrator)
    sys.exit(app.run())


if __name__ == "__main__":
    main()
