"""Tests for LLMClient.chat_structured parsing and schema handling.

Covers the M7 fixes: json.dumps schema repr (not str()), code-fence
stripping before json.loads, and missing-API-key warning.
"""

import json

import pytest

from tui_agents.llm.client import LLMClient, _strip_code_fences
from tui_agents.utils.config import Config


class TestStripCodeFences:
    def test_strips_json_fence(self):
        assert _strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_plain_fence(self):
        assert _strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_uppercase_json_fence(self):
        assert _strip_code_fences('```JSON\n{"a": 1}\n```') == '{"a": 1}'

    def test_plain_json_untouched(self):
        assert _strip_code_fences('{"a": 1}') == '{"a": 1}'

    def test_strips_whitespace(self):
        assert _strip_code_fences('  {"a": 1}  ') == '{"a": 1}'


class TestChatStructuredParsing:
    """Test chat_structured against a stubbed AsyncOpenAI client."""

    @pytest.fixture
    def llm(self, tmp_config: Config) -> LLMClient:
        tmp_config._data.setdefault("llm", {})["api_key"] = "test-key"
        tmp_config._data["llm"]["model"] = "deepseek-v4-pro"
        return LLMClient(tmp_config)

    def _stub_client(self, llm: LLMClient, content: str, capture: dict):
        """Replace the AsyncOpenAI client with one that returns `content`."""

        class _Msg:
            def __init__(self, c):
                self.content = c

        class _Choice:
            def __init__(self, c):
                self.message = _Msg(c)

        class _Resp:
            def __init__(self, c):
                self.choices = [_Choice(c)]

        class _Completions:
            async def create(self, **kwargs):
                capture["kwargs"] = kwargs
                return _Resp(content)

        class _Chat:
            completions = _Completions()

        class _Client:
            chat = _Chat()

        llm._client = _Client()

    @pytest.mark.asyncio
    async def test_parses_fenced_json(self, llm):
        capture: dict = {}
        self._stub_client(llm, '```json\n{"ok": true}\n```', capture)
        result = await llm.chat_structured("sys", "user", {"type": "object"})
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_parses_bare_json(self, llm):
        capture: dict = {}
        self._stub_client(llm, '{"ok": false}', capture)
        result = await llm.chat_structured("sys", "user", {"type": "object"})
        assert result == {"ok": False}

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error_with_raw(self, llm):
        capture: dict = {}
        self._stub_client(llm, "not json at all", capture)
        result = await llm.chat_structured("sys", "user", {"type": "object"})
        assert "error" in result
        assert result["raw"] == "not json at all"

    @pytest.mark.asyncio
    async def test_non_openai_schema_uses_json_not_str(self, llm):
        """M7: schema must be embedded as JSON (double quotes), not Python repr."""
        capture: dict = {}
        self._stub_client(llm, "{}", capture)
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        await llm.chat_structured("sys", "base user prompt", schema)

        user_msg = capture["kwargs"]["messages"][1]["content"]
        # json.dumps produces "properties"; str(dict) produces 'properties'
        assert '"properties"' in user_msg
        assert "'properties'" not in user_msg

    @pytest.mark.asyncio
    async def test_openai_model_gets_response_format(self, llm):
        llm._model = "gpt-4o"
        capture: dict = {}
        self._stub_client(llm, "{}", capture)
        await llm.chat_structured("sys", "user", {"type": "object"})
        assert "response_format" in capture["kwargs"]
        assert capture["kwargs"]["response_format"]["type"] == "json_schema"

    @pytest.mark.asyncio
    async def test_missing_api_key_warns(self, caplog):
        import logging
        tmp = Config.__new__(Config)  # avoid loading yaml for this unit test
        tmp._data = {
            "llm": {
                "base_url": "https://api.example.com",
                "api_key": "",
                "model": "test-model",
                "temperature": 0.3,
                "max_tokens": 100,
                "timeout": 5,
            }
        }
        with caplog.at_level(logging.WARNING):
            LLMClient(tmp)
        assert any("API key" in r.message for r in caplog.records)
