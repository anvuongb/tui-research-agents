from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine

from tui_agents.agents.base import BaseAgent
from tui_agents.llm.client import LLMClient
from tui_agents.llm.tools import IMPLEMENTER_TOOLS
from tui_agents.storage.database import Database
from tui_agents.storage.models import Distillation, Implementation, StageStatus
from tui_agents.storage.vector_store import VectorStore
from tui_agents.utils.config import Config


ProgressFn = Callable[[str, str, float], Coroutine[Any, Any, None]]

IMPLEMENTER_SYSTEM_PROMPT = """You are an expert machine learning engineer specializing in implementing research papers, with deep expertise in diffusion models, optimal transport, and generative modeling. Your task is to implement the core methodology described in a paper distillation.

Follow these guidelines:
1. Focus on the core algorithm, loss function, and training procedure
2. Use PyTorch as the primary framework
3. Write clean, well-structured Python code with proper type hints
4. Include docstrings for classes and functions
5. Generate comprehensive PyTest test cases
6. List all required Python dependencies
7. Explain key design decisions in the implementation

Output a structured JSON response with these fields:
- code: Complete Python implementation (classes, functions, training loop)
- dependencies: List of pip-installable package names with versions
- tests: Complete PyTest test cases (at least 3 tests)
- explanation: 2-3 paragraphs explaining the architecture and design decisions"""


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

    async def implement(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> Implementation | None:
        paper = await self.db.get_paper(paper_id)
        if not paper:
            if progress:
                await progress("error", f"Paper not found: {paper_id}", 0.0)
            return None

        distillation = await self.db.get_distillation(paper_id)
        if not distillation:
            if progress:
                await progress("error", f"No distillation found for paper: {paper_id}. Distill first.", 0.0)
            return None

        run_id = await self.start_run(paper_id)

        try:
            if progress:
                await progress("loading", f"Loading distillation for: {paper.title[:60]}", 0.05)

            if progress:
                await progress("generating", "Generating implementation code...", 0.1)

            impl = await self._run_llm_implementation(distillation, paper_id, progress)

            if impl:
                impl.id = str(uuid.uuid4())
                impl.paper_id = paper_id
                impl.run_id = run_id
                impl.created_at = datetime.now().isoformat()

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

    async def _run_llm_implementation(
        self,
        distillation: Distillation,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> Implementation | None:
        contributions_text = "\n".join(f"- {c}" for c in distillation.contributions)
        equations_text = "\n".join(f"  {e}" for e in distillation.key_equations)

        user_prompt = f"""Implement the core methodology from the following paper distillation.

## Summary
{distillation.summary}

## Methodology
{distillation.methodology}

## Key Contributions
{contributions_text}

## Key Equations
{equations_text}

## Limitations
{', '.join(distillation.limitations) if distillation.limitations else 'None noted'}

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
            )

            if "error" in result:
                return await self._fallback_tool_implementation(distillation, paper_id, progress)

            return Implementation(
                id="",
                paper_id=paper_id,
                run_id="",
                code=result.get("code", "# No code generated"),
                dependencies=result.get("dependencies", []),
                tests=result.get("tests", ""),
                language="python",
            )

        except Exception as e:
            if progress:
                await progress("error", f"Structured implementation failed: {e}, trying fallback...", 0.2)
            return await self._fallback_tool_implementation(distillation, paper_id, progress)

    async def _fallback_tool_implementation(
        self,
        distillation: Distillation,
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
                    code=collected_data.get("code", "# No code generated"),
                    dependencies=collected_data.get("dependencies", []),
                    tests=collected_data.get("tests", ""),
                    language="python",
                )
        except Exception as e:
            if progress:
                await progress("error", f"Fallback implementation failed: {e}", 0.0)

        return None

    async def execute(self, paper_id: str, **kwargs) -> dict[str, Any]:
        progress_fn = kwargs.get("progress_fn")
        impl = await self.implement(paper_id, progress=progress_fn)
        if impl:
            return {
                "status": "completed",
                "implementation_id": impl.id,
                "code_length": len(impl.code),
                "dependencies": impl.dependencies,
            }
        return {"status": "failed", "error": "Implementation returned no result"}
