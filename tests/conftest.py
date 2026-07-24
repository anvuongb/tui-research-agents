import os
import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio

from tui_agents.agents.orchestrator import Orchestrator
from tui_agents.llm.client import LLMClient
from tui_agents.storage.database import Database
from tui_agents.storage.vector_store import VectorStore
from tui_agents.utils.config import Config, load_config


def _make_test_config(tmpdir: str) -> Config:
    """Create an in-memory config pointing to temp directories."""
    config = load_config()
    config._data["storage"]["database_path"] = str(Path(tmpdir) / "test.db")
    config._data["storage"]["data_dir"] = tmpdir
    config._data["storage"]["papers_dir"] = str(Path(tmpdir) / "papers")
    config._data["storage"]["code_dir"] = str(Path(tmpdir) / "code")
    config._data["storage"]["benchmarks_dir"] = str(Path(tmpdir) / "benchmarks")
    config._data["vector_store"]["chroma"]["persist_directory"] = str(Path(tmpdir) / "chroma")
    config._data["vector_store"]["chroma"]["collection_name"] = "test_papers"
    return config


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def default_config(project_root: Path) -> Config:
    config_path = project_root / "config" / "default.yaml"
    return Config(config_path)


@pytest.fixture
def tmp_config(tmp_path: Path) -> Config:
    return _make_test_config(str(tmp_path))


@pytest_asyncio.fixture
async def test_db(tmp_config: Config) -> AsyncGenerator[Database, None]:
    db_path = tmp_config.database_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    yield db
    await db.close()


@pytest_asyncio.fixture
async def test_vector_store(tmp_config: Config) -> AsyncGenerator[VectorStore, None]:
    vs = VectorStore(
        persist_directory=tmp_config.chroma_persist_dir,
        collection_name=tmp_config.chroma_collection_name,
    )
    yield vs
    # ChromaDB clear() is skipped here — it blocks the event loop during teardown.
    # Data is cleaned automatically when pytest removes the tmp_path directory.


@pytest_asyncio.fixture
async def test_llm(tmp_config: Config) -> LLMClient:
    return LLMClient(tmp_config)


@pytest_asyncio.fixture
async def test_orchestrator(
    tmp_config: Config, test_db: Database, test_vector_store: VectorStore, test_llm: LLMClient
) -> Orchestrator:
    return Orchestrator(
        config=tmp_config,
        database=test_db,
        vector_store=test_vector_store,
        llm=test_llm,
    )
