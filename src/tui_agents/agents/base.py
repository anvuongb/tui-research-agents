from __future__ import annotations

import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Coroutine

from tui_agents.llm.client import LLMClient, LLMResponse
from tui_agents.storage.database import Database
from tui_agents.storage.models import AgentRun, StageStatus


class BaseAgent(ABC):
    def __init__(self, llm: LLMClient, database: Database):
        self.llm = llm
        self.db = database
        self._current_run: AgentRun | None = None

    @staticmethod
    def strip_code_fences(text: str) -> str:
        import re
        text = text.strip()
        text = re.sub(r"^\s*```(?:python|py|Python|Py)?\s*\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?\s*```\s*$", "", text)
        return text.strip()

    async def _run_with_heartbeat(
        self,
        coro: Coroutine[Any, Any, Any],
        progress: Callable[[str, str, float], Coroutine[Any, Any, None]] | None,
        stage: str,
        pct: float = 0.3,
    ) -> Any:
        start = time.monotonic()
        heartbeat_task: asyncio.Task | None = None

        async def _heartbeat() -> None:
            while True:
                await asyncio.sleep(5.0)
                elapsed = int(time.monotonic() - start)
                if progress:
                    await progress(stage, f"Still running... ({elapsed}s elapsed)", pct + min(elapsed * 0.01, 0.5))

        if progress:
            heartbeat_task = asyncio.create_task(_heartbeat())
        try:
            return await coro
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    @property
    @abstractmethod
    def agent_type(self) -> str:
        ...

    @property
    def current_run_id(self) -> str | None:
        return self._current_run.id if self._current_run else None

    async def start_run(self, paper_id: str, input_data: dict[str, Any] | None = None) -> str:
        run = AgentRun(
            id=str(uuid.uuid4()),
            paper_id=paper_id,
            agent_type=self.agent_type,
            input_data=input_data or {},
            status=StageStatus.IN_PROGRESS,
            started_at=datetime.now().isoformat(),
        )
        await self.db.create_agent_run(run)
        self._current_run = run
        return run.id

    async def complete_run(self, output_data: dict[str, Any]) -> None:
        if self._current_run:
            self._current_run.output_data = output_data
            self._current_run.status = StageStatus.COMPLETED
            self._current_run.completed_at = datetime.now().isoformat()
            await self.db.update_agent_run(self._current_run)

    async def fail_run(self, error_message: str) -> None:
        if self._current_run:
            self._current_run.status = StageStatus.FAILED
            self._current_run.error_message = error_message
            self._current_run.completed_at = datetime.now().isoformat()
            await self.db.update_agent_run(self._current_run)

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        return await self.llm.chat(
            messages=messages,
            tools=tools,
            temperature=temperature,
        )

    async def _handle_tool_calls(
        self,
        response: LLMResponse,
        tools: list[dict[str, Any]],
        handler_map: dict[str, callable],
        messages: list[dict[str, Any]],
        max_rounds: int = 5,
    ) -> str:
        current_messages = list(messages)
        current_messages.append({
            "role": "assistant",
            "content": response.content or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in response.tool_calls
            ],
        })

        rounds = 0
        last_content = response.content

        while response.has_tool_calls and rounds < max_rounds:
            for tc in response.tool_calls:
                tool_name = tc["name"]
                try:
                    args = json.loads(tc["arguments"])
                except json.JSONDecodeError:
                    args = {}

                if tool_name in handler_map:
                    result = await handler_map[tool_name](**args)
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    })
                else:
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps({"error": f"Unknown tool: {tool_name}"}),
                    })

            response = await self._call_llm(current_messages, tools)
            if response.content:
                last_content = response.content

            if response.has_tool_calls:
                current_messages.append({
                    "role": "assistant",
                    "content": response.content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in response.tool_calls
                    ],
                })

            rounds += 1

        return last_content or ""

    async def _collect_tool_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_name: str,
    ) -> dict[str, Any]:
        """Shared tool-call fallback: run one LLM tool round-trip and return
        the kwargs captured by `tool_name`, or parsed JSON content, or {}."""
        collected: dict[str, Any] = {}

        async def _handler(**kwargs) -> dict[str, Any]:
            nonlocal collected
            collected = kwargs
            return {"status": "saved"}

        response = await self._call_llm(messages, tools)
        if response.has_tool_calls:
            await self._handle_tool_calls(
                response, tools, {tool_name: _handler}, messages
            )
        elif response.content:
            try:
                collected = json.loads(response.content)
            except json.JSONDecodeError:
                pass
        return collected

    @abstractmethod
    async def execute(self, paper_id: str, **kwargs) -> dict[str, Any]:
        ...
