from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine

from tui_agents.agents.base import BaseAgent
from tui_agents.llm.client import LLMClient
from tui_agents.llm.tools import PROTOTYPER_TOOLS
from tui_agents.storage.database import Database
from tui_agents.storage.models import Implementation, StageStatus
from tui_agents.storage.vector_store import VectorStore
from tui_agents.utils.config import Config


ProgressFn = Callable[[str, str, float], Coroutine[Any, Any, None]]

PROTOTYPER_SYSTEM_PROMPT = """You are an expert ML engineer tasked with creating a runnable prototype from a paper implementation. Your goal is to produce a self-contained Python script that demonstrates the implementation in action.

Follow these guidelines:
1. Create a single runnable Python script that imports and uses the implementation
2. Include a small synthetic dataset or use of a simple real dataset
3. Show the core workflow: data loading, model setup, training, and output
4. Add command-line argument support for key parameters
5. List all pip requirements needed to run the prototype
6. Provide clear usage instructions

Output a structured JSON response with these fields:
- script: Complete runnable Python script (single file, self-contained)
- requirements: List of pip-installable package names with versions
- usage_instructions: Step-by-step instructions to run the prototype
- expected_output: Description of what the user should see when running"""


class PrototyperAgent(BaseAgent):
    agent_type = "prototyper"

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
        self._benchmarks_dir = Path(config.benchmarks_dir)
        self._code_dir.mkdir(parents=True, exist_ok=True)
        self._benchmarks_dir.mkdir(parents=True, exist_ok=True)

    async def prototype(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any] | None:
        paper = await self.db.get_paper(paper_id)
        if not paper:
            if progress:
                await progress("error", f"Paper not found: {paper_id}", 0.0)
            return None

        implementation = await self.db.get_implementation(paper_id)
        if not implementation:
            if progress:
                await progress("error", f"No implementation found for paper: {paper_id}. Implement first.", 0.0)
            return None

        run_id = await self.start_run(paper_id)

        try:
            if progress:
                await progress("loading", f"Loading implementation for: {paper.title[:60]}", 0.05)

            if progress:
                await progress("generating", "Creating runnable prototype...", 0.1)

            result = await self._run_with_heartbeat(
                self._run_llm_prototype(implementation, paper_id, progress),
                progress, "generating",
            )

            if result:
                await self.db.update_paper_status(paper_id, "prototyped")

                self._save_prototype_files(paper_id, result)

                output = {
                    "prototype_id": str(uuid.uuid4()),
                    "script_length": len(result.get("script", "")),
                    "requirements": result.get("requirements", []),
                }
                await self.complete_run(output)

                if progress:
                    await progress("done", f"Prototype created: {paper.title[:60]}", 1.0)

                return result

            if progress:
                await progress("error", "LLM prototype creation returned no result", 0.0)
            return None

        except Exception as e:
            await self.fail_run(str(e))
            if progress:
                await progress("error", f"Prototype creation failed: {e}", 0.0)
            return None

    def _save_prototype_files(self, paper_id: str, result: dict[str, Any]) -> None:
        dest_dir = self._code_dir / paper_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        script = self.strip_code_fences(result.get("script", ""))
        if script:
            script_path = dest_dir / "prototype.py"
            script_path.write_text(script)

        requirements = result.get("requirements", [])
        if requirements:
            req_path = dest_dir / "requirements.txt"
            existing = set()
            if req_path.exists():
                existing = set(req_path.read_text().strip().split("\n"))
            all_reqs = list(existing | set(requirements))
            req_path.write_text("\n".join(all_reqs))

        instructions = result.get("usage_instructions", "")
        if instructions:
            readme_path = dest_dir / "README.md"
            readme_path.write_text(f"# Prototype\n\n{instructions}")

    async def _run_llm_prototype(
        self,
        implementation: Implementation,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any] | None:
        code_excerpt = implementation.code
        if len(code_excerpt) > 8000:
            code_excerpt = code_excerpt[:8000] + "\n\n# ... (code truncated for length)"

        deps_text = ", ".join(implementation.dependencies) if implementation.dependencies else "None specified"

        user_prompt = f"""Create a runnable prototype script from the following implementation.

## Implementation Code
```python
{code_excerpt}
```

## Known Dependencies
{deps_text}

Create a self-contained Python script that demonstrates the implementation. Provide your response as a JSON object."""

        schema = {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "Complete runnable Python script (single file, self-contained)",
                },
                "requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of pip dependency strings (e.g., 'torch>=2.0')",
                },
                "usage_instructions": {
                    "type": "string",
                    "description": "Step-by-step instructions to install dependencies and run the prototype",
                },
                "expected_output": {
                    "type": "string",
                    "description": "Description of what the user should see when running the prototype",
                },
            },
            "required": ["script", "requirements", "usage_instructions"],
        }

        try:
            result = await self.llm.chat_structured(
                system_prompt=PROTOTYPER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_schema=schema,
            )

            if "error" in result:
                return await self._fallback_tool_prototype(implementation, paper_id, progress)

            return result

        except Exception as e:
            if progress:
                await progress("error", f"Structured prototype failed: {e}, trying fallback...", 0.2)
            return await self._fallback_tool_prototype(implementation, paper_id, progress)

    async def _fallback_tool_prototype(
        self,
        implementation: Implementation,
        paper_id: str,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any] | None:
        code_excerpt = implementation.code
        if len(code_excerpt) > 8000:
            code_excerpt = code_excerpt[:8000] + "\n\n# ... (code truncated)"

        messages = [
            {"role": "system", "content": PROTOTYPER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Implementation code:\n```python\n{code_excerpt}\n```"},
        ]

        collected_data: dict[str, Any] = {}

        async def save_prototype_handler(**kwargs) -> dict[str, Any]:
            nonlocal collected_data
            collected_data = kwargs
            return {"status": "saved"}

        handler_map = {"save_prototype": save_prototype_handler}

        try:
            response = await self._call_llm(messages, PROTOTYPER_TOOLS)
            if response.has_tool_calls:
                await self._handle_tool_calls(
                    response, PROTOTYPER_TOOLS, handler_map, messages
                )
            elif response.content:
                try:
                    data = json.loads(response.content)
                    collected_data = data
                except json.JSONDecodeError:
                    pass

            if collected_data:
                return collected_data
        except Exception as e:
            if progress:
                await progress("error", f"Fallback prototype failed: {e}", 0.0)

        return None

    async def execute(self, paper_id: str, **kwargs) -> dict[str, Any]:
        progress_fn = kwargs.get("progress_fn")
        result = await self.prototype(paper_id, progress=progress_fn)
        if result:
            return {"status": "completed", "prototype_id": str(uuid.uuid4())}
        return {"status": "failed", "error": "Prototype creation returned no result"}
