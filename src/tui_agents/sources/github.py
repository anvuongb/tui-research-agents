from __future__ import annotations

import json
from typing import Any

import httpx

from tui_agents.utils.config import Config
from tui_agents.utils.logging import get_logger

_log = get_logger(__name__)


class GitHubClient:
    def __init__(self, config: Config):
        self._config = config
        token = config.get("github", "token", default="")
        if token and token != "${GITHUB_TOKEN}":
            self._headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "tui-research-agents",
            }
        else:
            self._headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "tui-research-agents",
            }
        self._max_repos = config.get("github", "max_repos", default=5)

    async def search_repos(
        self, title: str, keywords: str, max_results: int = 5
    ) -> list[dict[str, Any]]:
        query = f"{title} {keywords}"
        if len(query) > 190:
            query = query[:190]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    "https://api.github.com/search/repositories",
                    params={
                        "q": query,
                        "sort": "stars",
                        "order": "desc",
                        "per_page": min(max_results, 10),
                    },
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()

                results: list[dict[str, Any]] = []
                for item in data.get("items", []):
                    results.append({
                        "full_name": item.get("full_name", ""),
                        "name": item.get("name", ""),
                        "description": item.get("description", ""),
                        "url": item.get("html_url", ""),
                        "stars": item.get("stargazers_count", 0),
                        "language": item.get("language", ""),
                        "default_branch": item.get("default_branch", "main"),
                    })

                return results

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                _log.warning(f"GitHub rate limited (403). Consider setting GITHUB_TOKEN.")
            elif e.response.status_code == 404:
                pass
            else:
                _log.warning(f"GitHub search error: {e}")
            return []
        except Exception as e:
            _log.warning(f"GitHub search error: {e}")
            return []

    async def list_repo_files(
        self, full_name: str, path: str = ""
    ) -> list[dict[str, Any]]:
        url = f"https://api.github.com/repos/{full_name}/contents/{path}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers=self._headers, params={"per_page": 100})
                resp.raise_for_status()
                items = resp.json()
                if isinstance(items, dict):
                    return [items]
                return [{"name": i.get("name"), "path": i.get("path"),
                         "type": i.get("type"), "download_url": i.get("download_url")}
                        for i in items]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                _log.warning(f"GitHub repo not found: {full_name}")
            else:
                _log.warning(f"GitHub list files error: {e}")
            return []
        except Exception as e:
            _log.warning(f"GitHub list files error: {e}")
            return []

    async def _fetch_file_content(self, download_url: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(download_url, headers=self._headers)
                resp.raise_for_status()
                return resp.text
        except Exception:
            return None

    async def _gather_py_files(
        self, full_name: str, path: str = "", depth: int = 0
    ) -> list[dict[str, Any]]:
        if depth > 4:
            return []
        items = await self.list_repo_files(full_name, path)
        if not items:
            return []

        py_files: list[dict[str, Any]] = []
        for item in items:
            if item.get("type") == "file":
                name = item.get("name", "")
                if name.endswith(".py") or name in ("README.md", "setup.py", "pyproject.toml", "requirements.txt"):
                    download_url = item.get("download_url")
                    if download_url:
                        content = await self._fetch_file_content(download_url)
                        if content:
                            py_files.append({
                                "name": name,
                                "path": item.get("path"),
                                "content": content,
                            })
            elif item.get("type") == "dir":
                name = item.get("name", "")
                if name not in (".git", "__pycache__", ".github", "tests", "test"):
                    sub_files = await self._gather_py_files(full_name, item.get("path", ""), depth + 1)
                    py_files.extend(sub_files)

        return py_files

    async def load_repo_by_url(self, repo_url: str) -> dict[str, Any] | None:
        parts = repo_url.strip("/").split("/")
        if len(parts) >= 2:
            full_name = f"{parts[-2]}/{parts[-1]}"
            return await self.load_repo_code(full_name)
        return None

    async def load_repo_code(self, full_name: str) -> dict[str, Any] | None:
        try:
            all_files = await self._gather_py_files(full_name)
        except Exception as e:
            _log.warning(f"Failed to gather files from {full_name}: {e}")
            return None

        if not all_files:
            return None

        readme = ""
        py_content: list[str] = []
        config_content: list[str] = []
        test_content: list[str] = []

        for f in all_files:
            name = f.get("name", "")
            content = f.get("content", "")
            if name == "README.md":
                readme = content
            elif "test" in name.lower():
                test_content.append(f"# {name}\n{content}")
            elif name in ("setup.py", "pyproject.toml", "requirements.txt"):
                config_content.append(f"# {name}\n{content}")
            else:
                py_content.append(f"# {name}\n{content}")

        return {
            "full_name": full_name,
            "repo_url": f"https://github.com/{full_name}",
            "readme": readme[:4000] if readme else "",
            "code": "\n\n".join(py_content)[:30000],
            "config": "\n\n".join(config_content)[:2000],
            "tests": "\n\n".join(test_content)[:5000],
        }
