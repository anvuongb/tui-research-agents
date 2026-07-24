from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from tui_agents.llm.client import LLMClient, LLMResponse
from tui_agents.storage.database import Database
from tui_agents.storage.models import AgentRun, StageStatus


class BaseAgent(ABC):
    def __init__(self, llm: LLMClient, database: Database):
        self.llm = llm
        self.db = database
        self._current_run: AgentRun | None = None

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

    @abstractmethod
    async def execute(self, paper_id: str, **kwargs) -> dict[str, Any]:
        ...
