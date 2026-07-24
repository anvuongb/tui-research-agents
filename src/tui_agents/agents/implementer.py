from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine

from tui_agents.agents.base import BaseAgent
from tui_agents.llm.client import LLMClient
from tui_agents.llm.tools import IMPLEMENTER_TOOLS
from tui_agents.sources.github import GitHubClient
from tui_agents.storage.database import Database
from tui_agents.storage.models import Distillation, Implementation, StageStatus
from tui_agents.storage.vector_store import VectorStore
from tui_agents.utils.config import Config


ProgressFn = Callable[[str, str, float], Coroutine[Any, Any, None]]

IMPLEMENTER_SYSTEM_PROMPT = """You are an expert machine learning engineer specializing in implementing research papers, with deep expertise in diffusion models, optimal transport, and generative modeling.

You have access to three sources of information:
1. DISTILLATION: A structured summary of the paper's methodology
2. PAPER TEXT: The full scientific content of the paper (chunked)
3. GITHUB REFERENCES: Working implementations from existing repositories (if available)

Follow these guidelines:
1. Study the reference implementations to understand practical approaches
2. Identify what the references did well and what can be improved
3. Produce an implementation that combines the best ideas from references with the exact methodology from the paper
4. If no useful references exist, implement from scratch using the paper text
5. Cite the source if you base code on a reference implementation
6. Use PyTorch as the primary framework
7. Write clean, well-structured Python code with proper type hints
8. Include docstrings for classes and functions
9. Generate comprehensive PyTest test cases
10. List all required Python dependencies with versions
11. Explain key design decisions

Output a structured JSON response with these fields:
- code: Complete Python implementation (classes, functions, training loop)
- dependencies: List of pip-installable package names (e.g. 'torch>=2.0')
- tests: Complete PyTest test cases (at least 3 tests)
- explanation: 2-3 paragraphs explaining architecture and design decisions"""

EVALUATE_RELEVANCE_PROMPT = """You are evaluating whether GitHub search results are relevant to implementing a research paper.

Given:
1. The paper title and abstract
2. A list of GitHub repositories found by search

Determine:
- Are any of these repos implementing the SAME method described in the paper?
- Even if the paper title doesn't match exactly, does the repo implement similar concepts?

Respond with a JSON object:
- relevant: true if at least one repo appears to implement the paper's method or a very similar method
- reason: A brief explanation (1-2 sentences) of your assessment"""


class ImplementerAgent(BaseAgent):
    agent_type = "implementer"

    def __init__(
        self,
        llm: LLMClient,
        database: Database,
        vector_store: VectorStore,
        config: Config,
    ):
        super().__init__(llm, database)
        self.vector_store = vector_store
        self._code_dir = Path(config.code_dir)
        self._code_dir.mkdir(parents=True, exist_ok=True)
        self._github = GitHubClient(config) if config.get("github", "enabled", default=True) else None

    async def implement(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
        github_url: str | None = None,
        skip_eval: bool = False,
    ) -> Implementation | None:
        paper = await self.db.get_paper(paper_id)
        if not paper:
            if progress:
                await progress("error", f"Paper not found: {paper_id}", 0.0)
            return None

        distillation = await self.db.get_distillation(paper_id)
        if not distillation:
            if progress:
                await progress("error", f"No distillation found. Distill first.", 0.0)
            return None

        run_id = await self.start_run(paper_id)

        try:
            if progress:
                await progress("loading", f"Loading distillation for: {paper.title[:60]}", 0.05)

            if progress:
                await progress("paper_text", "Loading full paper text from database...", 0.08)
            paper_text = await self._load_paper_text(paper_id)

            ref_code: dict[str, Any] | None = None

            if github_url == "__skip_eval__":
                skip_eval = True

            if github_url:
                if progress:
                    await progress("github", f"Loading reference from: {github_url}", 0.15)
                ref_code = await self._github.load_repo_by_url(github_url) if self._github else None
            elif self._github:
                if progress:
                    await progress("github", "Searching GitHub for reference implementations...", 0.12)
                keywords = " ".join(distillation.contributions[:3]) if distillation.contributions else ""
                results = await self._cached_github_search(paper.title, keywords)
                if results:
                    if progress:
                        await progress("github", f"Found {len(results)} repos. Loading top match...", 0.18)
                    ref_code = await self._github.load_repo_code(results[0]["full_name"])

                    if ref_code and not skip_eval:
                        if progress:
                            await progress("evaluate", "Evaluating reference relevance...", 0.22)
                        relevance = await self._evaluate_references(paper, distillation, results)
                        if not relevance.get("relevant", False):
                            return None  # Signal: need user GitHub link

            context_chars = len(distillation.summary or "") + len(distillation.methodology or "") + len(paper_text or "") + len(ref_code.get("code", "") if ref_code else "")
            context_tokens = context_chars // 4
            gh_info = ""
            if ref_code and ref_code.get("full_name"):
                gh_info = f", referencing {ref_code['full_name']}"

            if progress:
                await progress("generating", f"Generating implementation (~{context_tokens} tokens input{gh_info})...", 0.30)

            impl = await self._run_with_heartbeat(
                self._run_llm_implementation(distillation, paper_text, ref_code, paper_id, progress),
                progress, "generating",
            )

            if impl:
                impl.id = str(uuid.uuid4())
                impl.paper_id = paper_id
                impl.run_id = run_id
                impl.created_at = datetime.now().isoformat()

                if progress:
                    await progress("saving", "Saving implementation to disk...", 0.85)

                await self.db.save_implementation(impl)
                await self.db.update_paper_status(paper_id, "implemented")

                self._save_code_file(paper_id, impl)

                output = {
                    "implementation_id": impl.id,
                    "code_length": len(impl.code),
                    "dependencies": impl.dependencies,
                }
                await self.complete_run(output)

                if progress:
                    await progress("done", f"Implementation complete: {paper.title[:60]}", 1.0)

                return impl

            if progress:
                await progress("error", "LLM implementation returned no result", 0.0)
            return None

        except Exception as e:
            await self.fail_run(str(e))
            if progress:
                await progress("error", f"Implementation failed: {e}", 0.0)
            return None

    def _save_code_file(self, paper_id: str, impl: Implementation) -> None:
        dest_dir = self._code_dir / paper_id / impl.id[:8]
        dest_dir.mkdir(parents=True, exist_ok=True)

        code_path = dest_dir / "implementation.py"
        code_path.write_text(impl.code)

        if impl.tests:
            test_path = dest_dir / "test_implementation.py"
            test_path.write_text(impl.tests)

        if impl.dependencies:
            req_path = dest_dir / "requirements.txt"
            req_path.write_text("\n".join(impl.dependencies))

    async def _load_paper_text(self, paper_id: str) -> str:
        try:
            data = self.vector_store.collection.get(
                where={"paper_id": paper_id},
                include=["documents", "metadatas"],
            )
            if not data or not data.get("documents"):
                return ""

            docs_with_index = []
            for doc, meta in zip(data["documents"], data["metadatas"]):
                if doc:
                    idx = int(meta.get("chunk_index", 0))
                    docs_with_index.append((idx, doc))
            docs_with_index.sort(key=lambda x: x[0])

            combined = "\n\n".join(doc for _, doc in docs_with_index)
            if len(combined) > 80000:
                combined = combined[:80000] + "\n\n[... text truncated ...]"
            return combined
        except Exception:
            return ""

    async def _cached_github_search(
        self, title: str, keywords: str
    ) -> list[dict[str, Any]]:
        cache_key = hashlib.sha256(f"{title}|{keywords}".encode()).hexdigest()[:16]

        cached = await self.db.get_cached_github(cache_key)
        if cached is not None:
            return cached

        results = await self._github.search_repos(title, keywords)
        ttl = self._github._config.get("cache", "github_ttl_seconds", default=86400)
        await self.db.set_cached_github(cache_key, results, ttl)

        return results

    async def _evaluate_references(
        self,
        paper: Any,
        distillation: Distillation,
        gh_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        repo_descriptions = "\n".join(
            f"- {r['full_name']}: {r.get('description', '')} ({r.get('language', '')}, {r.get('stars', 0)} stars)"
            for r in gh_results[:3]
        )

        user_prompt = f"""Paper Title: {paper.title}
Paper Abstract: {paper.abstract[:500]}

GitHub Search Results:
{repo_descriptions}

Are any of these repositories implementing this paper's method?"""

        schema = {
            "type": "object",
            "properties": {
                "relevant": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["relevant", "reason"],
        }

        try:
            result = await self.llm.chat_structured(
                system_prompt=EVALUATE_RELEVANCE_PROMPT,
                user_prompt=user_prompt,
                response_schema=schema,
            )
            if "error" not in result:
                return result
        except Exception:
            pass

        return {"relevant": True, "reason": "Could not evaluate; proceeding with references."}

    async def _run_llm_implementation(
        self,
        distillation: Distillation,
        paper_text: str,
        ref_code: dict[str, Any] | None,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> Implementation | None:
        contributions_text = "\n".join(f"- {c}" for c in distillation.contributions)
        equations_text = "\n".join(f"  {e}" for e in distillation.key_equations)

        github_section = ""
        if ref_code and ref_code.get("code"):
            repo_url = ref_code.get("repo_url", "")
            github_section = f"""
## GitHub Reference Implementation (from {repo_url})
### README
{ref_code.get('readme', '')[:2000]}

### Code
{ref_code.get('code', '')[:12000]}

### Config
{ref_code.get('config', '')[:1000]}

### Tests
{ref_code.get('tests', '')[:2000]}
"""

        paper_section = ""
        if paper_text:
            excerpt = paper_text[:20000]
            paper_section = f"""
## Paper Text
{excerpt}
"""

        user_prompt = f"""Implement the core methodology from the following paper.

## Distillation
### Summary
{distillation.summary}

### Methodology
{distillation.methodology}

### Key Contributions
{contributions_text}

### Key Equations
{equations_text}

### Limitations
{', '.join(distillation.limitations) if distillation.limitations else 'None noted'}
{paper_section}
{github_section}
Provide a complete Python implementation as a JSON object."""

        schema = {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Complete Python implementation code with classes, functions, and training loop",
                },
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of pip-installable package dependencies (e.g., 'torch>=2.0')",
                },
                "tests": {
                    "type": "string",
                    "description": "Complete PyTest test cases (at least 3) for the implementation",
                },
                "explanation": {
                    "type": "string",
                    "description": "2-3 paragraphs explaining the architecture and design decisions",
                },
            },
            "required": ["code", "dependencies", "explanation"],
        }

        try:
            result = await self.llm.chat_structured(
                system_prompt=IMPLEMENTER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_schema=schema,
                max_tokens=16384,
            )

            if "error" in result:
                err_msg = result.get("error", "unknown")
                raw = result.get("raw", "")[:200]
                if progress:
                    await progress("error", f"LLM error: {err_msg}. Raw: {raw}", 0.0)
                from tui_agents.utils.logging import get_logger
                get_logger().error(f"Implementer chat_structured failed: {err_msg} | raw: {raw}")
                return await self._fallback_tool_implementation(
                    distillation, paper_text, ref_code, paper_id, progress
                )

            if not result.get("code"):
                if progress:
                    await progress("error", "LLM returned empty code field", 0.0)
                from tui_agents.utils.logging import get_logger
                get_logger().error(f"Implementer returned no code. Keys: {list(result.keys())}")
                return None

            return Implementation(
                id="",
                paper_id=paper_id,
                run_id="",
                code=self.strip_code_fences(result.get("code", "# No code generated")),
                dependencies=result.get("dependencies", []),
                tests=self.strip_code_fences(result.get("tests", "")),
                language="python",
            )

        except Exception as e:
            if progress:
                await progress("error", f"Structured implementation failed: {e}", 0.5)
            from tui_agents.utils.logging import get_logger
            get_logger().exception("Implementer chat_structured exception")
            return await self._fallback_tool_implementation(
                distillation, paper_text, ref_code, paper_id, progress
            )

    async def _fallback_tool_implementation(
        self,
        distillation: Distillation,
        paper_text: str,
        ref_code: dict[str, Any] | None,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> Implementation | None:
        contributions_text = "\n".join(f"- {c}" for c in distillation.contributions)
        equations_text = "\n".join(f"  {e}" for e in distillation.key_equations)

        user_prompt = f"""Implement the core methodology from this paper distillation.

## Summary
{distillation.summary}

## Methodology
{distillation.methodology}

## Key Contributions
{contributions_text}

## Key Equations
{equations_text}"""

        if paper_text:
            user_prompt += f"\n\n## Paper Text\n{paper_text[:15000]}"

        if ref_code and ref_code.get("code"):
            user_prompt += f"\n\n## Reference Code\n{ref_code.get('code', '')[:8000]}"

        messages = [
            {"role": "system", "content": IMPLEMENTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        collected_data: dict[str, Any] = {}

        async def save_implementation_handler(**kwargs) -> dict[str, Any]:
            nonlocal collected_data
            collected_data = kwargs
            return {"status": "saved"}

        handler_map = {"save_implementation": save_implementation_handler}

        try:
            response = await self._call_llm(messages, IMPLEMENTER_TOOLS)
            if response.has_tool_calls:
                await self._handle_tool_calls(
                    response, IMPLEMENTER_TOOLS, handler_map, messages
                )
            elif response.content:
                try:
                    data = json.loads(response.content)
                    collected_data = data
                except json.JSONDecodeError:
                    pass

            if collected_data:
                return Implementation(
                    id="",
                    paper_id=paper_id,
                    run_id="",
                    code=self.strip_code_fences(collected_data.get("code", "# No code generated")),
                    dependencies=collected_data.get("dependencies", []),
                    tests=self.strip_code_fences(collected_data.get("tests", "")),
                    language="python",
                )
        except Exception as e:
            if progress:
                await progress("error", f"Fallback implementation failed: {e}", 0.0)

        return None

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        import re
        text = text.strip()
        text = re.sub(r"^```(?:python|py|)\s*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
        return text.strip()
        dest_dir = self._code_dir / paper_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        code_path = dest_dir / "implementation.py"
        code_path.write_text(impl.code)

        if impl.tests:
            test_path = dest_dir / "test_implementation.py"
            test_path.write_text(impl.tests)

        if impl.dependencies:
            req_path = dest_dir / "requirements.txt"
            req_path.write_text("\n".join(impl.dependencies))

    async def execute(self, paper_id: str, **kwargs) -> dict[str, Any]:
        progress_fn = kwargs.get("progress_fn")
        github_url = kwargs.get("github_url")
        skip_eval = kwargs.get("skip_eval", False)
        impl = await self.implement(paper_id, progress=progress_fn, github_url=github_url, skip_eval=skip_eval)
        if impl:
            return {
                "status": "completed",
                "implementation_id": impl.id,
                "code_length": len(impl.code),
                "dependencies": impl.dependencies,
            }
        return {"status": "failed", "error": "Implementation returned no result"}
