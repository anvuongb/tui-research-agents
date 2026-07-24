from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from tui_agents.utils.config import Config


_QUIET_LOG = True


class LLMResponse:
    def __init__(self, content: str, tool_calls: list[dict[str, Any]] | None = None):
        self.content = content
        self.tool_calls = tool_calls or []

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMClient:
    def __init__(self, config: Config):
        base_url = config.llm_base_url.rstrip("/")
        api_key = config.llm_api_key

        self._base_url = base_url
        self._api_key = api_key
        self._timeout = config.llm_timeout
        self._model = config.llm_model
        self._temperature = config.llm_temperature
        self._max_tokens = config.llm_max_tokens
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            api_key = self._api_key or "not-configured"
            self._client = AsyncOpenAI(
                base_url=self._base_url,
                api_key=api_key,
                timeout=self._timeout,
            )
        return self._client

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens or self._max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = await self._get_client().chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        content = message.content or ""
        tool_calls = []

        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                })

        return LLMResponse(content=content, tool_calls=tool_calls)

    async def chat_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        temperature: float | None = None,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": self._max_tokens,
        }

        response_format = None
        supported_models = ["gpt-4", "gpt-3.5", "o1", "o3", "o4"]
        if any(m in self._model.lower() for m in supported_models):
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": response_schema,
                    "strict": True,
                },
            }
        else:
            schema_str = str(response_schema)
            user_prompt = f"{user_prompt}\n\nRespond with valid JSON matching this schema:\n{schema_str}"
            kwargs["messages"][1]["content"] = user_prompt

        if response_format:
            kwargs["response_format"] = response_format
            kwargs["messages"][1]["content"] = (
                f"{user_prompt}\n\nRespond with valid JSON matching the required schema."
            )

        response = await self._get_client().chat.completions.create(**kwargs)
        content = response.choices[0].message.content or "{}"

        import json
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"error": "Failed to parse structured response", "raw": content}
