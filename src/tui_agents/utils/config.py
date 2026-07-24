import os
import re
from pathlib import Path
from typing import Any

import yaml


_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: Any) -> Any:
    if isinstance(value, str):
        def _replace(m: re.Match) -> str:
            return os.environ.get(m.group(1), "")
        return _ENV_VAR_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


class Config:
    def __init__(self, path: str | Path | None = None):
        if path is None:
            path = Path("config/default.yaml")
        self._path = Path(path)
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"Config file not found: {self._path}")
        with open(self._path) as f:
            raw = yaml.safe_load(f) or {}
        self._data = _resolve_env_vars(raw)

    def get(self, *keys: str, default: Any = None) -> Any:
        node = self._data
        for key in keys:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return default
        return node

    @property
    def llm_base_url(self) -> str:
        return self.get("llm", "base_url", default="https://api.openai.com/v1")

    @property
    def llm_api_key(self) -> str:
        return self.get("llm", "api_key", default="")

    @property
    def llm_model(self) -> str:
        return self.get("llm", "model", default="gpt-4o-mini")

    @property
    def llm_temperature(self) -> float:
        return self.get("llm", "temperature", default=0.3)

    @property
    def llm_max_tokens(self) -> int:
        return self.get("llm", "max_tokens", default=4096)

    @property
    def llm_timeout(self) -> float:
        return self.get("llm", "timeout", default=120.0)

    @property
    def database_path(self) -> str:
        return self.get("storage", "database_path", default="./data/tui_agents.db")

    @property
    def data_dir(self) -> str:
        return self.get("storage", "data_dir", default="./data")

    @property
    def papers_dir(self) -> str:
        return self.get("storage", "papers_dir", default="./data/papers")

    @property
    def code_dir(self) -> str:
        return self.get("storage", "code_dir", default="./data/code")

    @property
    def benchmarks_dir(self) -> str:
        return self.get("storage", "benchmarks_dir", default="./data/benchmarks")

    @property
    def chroma_persist_dir(self) -> str:
        return self.get("vector_store", "chroma", "persist_directory", default="./data/chroma")

    @property
    def chroma_collection_name(self) -> str:
        return self.get("vector_store", "chroma", "collection_name", default="papers")

    @property
    def pipeline_stages(self) -> list[str]:
        return self.get("pipeline", "stages", default=["collector", "distiller", "implementer", "prototyper", "benchmarker"])

    @property
    def benchmark_iterations(self) -> int:
        return self.get("pipeline", "benchmark", "iterations", default=3)

    @property
    def benchmark_pass_threshold(self) -> float:
        return self.get("pipeline", "benchmark", "pass_threshold", default=0.7)

    @property
    def loop_max_iterations(self) -> int:
        return self.get("pipeline", "loop", "max_iterations", default=5)

    @property
    def arxiv_enabled(self) -> bool:
        return self.get("sources", "arxiv", "enabled", default=True)

    @property
    def semantic_scholar_enabled(self) -> bool:
        return self.get("sources", "semantic_scholar", "enabled", default=True)

    @property
    def semantic_scholar_api_key(self) -> str:
        return self.get("sources", "semantic_scholar", "api_key", default="")

    @property
    def local_pdf_enabled(self) -> bool:
        return self.get("sources", "local_pdf", "enabled", default=True)

    @property
    def local_pdf_watch_dir(self) -> str:
        return self.get("sources", "local_pdf", "watch_directory", default="./papers")


def load_config(path: str | Path | None = None) -> Config:
    return Config(path)
