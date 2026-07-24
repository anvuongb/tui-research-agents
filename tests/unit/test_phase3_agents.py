"""Tests for Implementer and Prototyper agents.

These test the agent lifecycle, prerequisites, file-saving logic,
and orchestrator integration. LLM calls are not mocked — tests focus
on code paths that don't require network access.
"""

import json
from pathlib import Path

import pytest

from tui_agents.agents.base import BaseAgent
from tui_agents.agents.implementer import IMPLEMENTER_SYSTEM_PROMPT, ImplementerAgent
from tui_agents.agents.orchestrator import Orchestrator
from tui_agents.agents.prototyper import PROTOTYPER_SYSTEM_PROMPT, PrototyperAgent
from tui_agents.storage.models import (
    AgentRun,
    AgentType,
    Distillation,
    Implementation,
    Paper,
    PaperSource,
    StageStatus,
)


class TestImplementerStructure:
    def test_inherits_from_base_agent(self):
        assert issubclass(ImplementerAgent, BaseAgent)

    def test_agent_type_is_implementer(self):
        assert ImplementerAgent.agent_type == "implementer"

    def test_system_prompt_is_not_empty(self):
        assert IMPLEMENTER_SYSTEM_PROMPT
        assert len(IMPLEMENTER_SYSTEM_PROMPT) > 100
        assert "PyTorch" in IMPLEMENTER_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_creator_sets_up_code_dir(self, test_llm, test_db,
                                              test_vector_store, tmp_config):
        agent = ImplementerAgent(test_llm, test_db, test_vector_store, tmp_config)
        assert agent._code_dir.exists()


class TestPrototyperStructure:
    def test_inherits_from_base_agent(self):
        assert issubclass(PrototyperAgent, BaseAgent)

    def test_agent_type_is_prototyper(self):
        assert PrototyperAgent.agent_type == "prototyper"

    def test_system_prompt_is_not_empty(self):
        assert PROTOTYPER_SYSTEM_PROMPT
        assert len(PROTOTYPER_SYSTEM_PROMPT) > 100
        assert "runnable" in PROTOTYPER_SYSTEM_PROMPT.lower()

    @pytest.mark.asyncio
    async def test_creator_sets_up_dirs(self, test_llm, test_db,
                                          test_vector_store, tmp_config):
        agent = PrototyperAgent(test_llm, test_db, test_vector_store, tmp_config)
        assert agent._code_dir.exists()
        assert agent._benchmarks_dir.exists()


class TestImplementerFileSave:
    @pytest.mark.asyncio
    async def test_save_code_file_writes_to_disk(self, test_llm, test_db,
                                                   test_vector_store, tmp_config):
        agent = ImplementerAgent(test_llm, test_db, test_vector_store, tmp_config)

        impl = Implementation(
            id="impl-test",
            paper_id="paper-test",
            run_id="run-test",
            code="def train(): pass\n\ndef test(): assert True",
            language="python",
            dependencies=["torch>=2.0", "numpy"],
            tests="def test_model(): pass",
        )
        agent._save_code_file("paper-test", impl)

        dest = agent._code_dir / "paper-test" / impl.id[:8]
        assert (dest / "implementation.py").exists()
        assert (dest / "test_implementation.py").exists()
        assert (dest / "requirements.txt").exists()

        code = (dest / "implementation.py").read_text()
        assert "def train():" in code

        reqs = (dest / "requirements.txt").read_text()
        assert "torch>=2.0" in reqs
        assert "numpy" in reqs

    @pytest.mark.asyncio
    async def test_save_code_file_without_tests(self, test_llm, test_db,
                                                  test_vector_store, tmp_config):
        agent = ImplementerAgent(test_llm, test_db, test_vector_store, tmp_config)

        impl = Implementation(
            id="impl-no-test",
            paper_id="paper-nt",
            run_id="run-nt",
            code="print('hello')",
            dependencies=[],
            tests="",
        )
        agent._save_code_file("paper-nt", impl)

        dest = agent._code_dir / "paper-nt" / impl.id[:8]
        assert (dest / "implementation.py").exists()
        assert not (dest / "test_implementation.py").exists()


class TestPrototyperFileSave:
    @pytest.mark.asyncio
    async def test_save_prototype_files(self, test_llm, test_db,
                                          test_vector_store, tmp_config):
        agent = PrototyperAgent(test_llm, test_db, test_vector_store, tmp_config)

        result = {
            "script": "import torch\nprint('prototype running')",
            "requirements": ["torch>=2.0", "matplotlib"],
            "usage_instructions": "Run: python prototype.py",
            "expected_output": "Prototype runs successfully",
        }
        agent._save_prototype_files("proto-test", result)

        dest = agent._code_dir / "proto-test"
        assert (dest / "prototype.py").exists()
        assert (dest / "requirements.txt").exists()
        assert (dest / "README.md").exists()

        script = (dest / "prototype.py").read_text()
        assert "import torch" in script

        readme = (dest / "README.md").read_text()
        assert "Run: python prototype.py" in readme

    @pytest.mark.asyncio
    async def test_requirements_merged_with_existing(self, test_llm, test_db,
                                                       test_vector_store, tmp_config):
        agent = PrototyperAgent(test_llm, test_db, test_vector_store, tmp_config)
        dest_dir = agent._code_dir / "merge-test"
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "requirements.txt").write_text("torch>=2.0\nnumpy")

        result = {
            "script": "pass",
            "requirements": ["torch>=2.0", "matplotlib", "numpy"],
            "usage_instructions": "",
        }
        agent._save_prototype_files("merge-test", result)

        reqs = (dest_dir / "requirements.txt").read_text().strip().split("\n")
        assert "torch>=2.0" in reqs
        assert "matplotlib" in reqs
        assert "numpy" in reqs


class TestPrerequisiteChecks:
    @pytest.mark.asyncio
    async def test_implementer_requires_distillation(self, test_llm, test_db,
                                                       test_vector_store, tmp_config):
        agent = ImplementerAgent(test_llm, test_db, test_vector_store, tmp_config)

        await test_db.upsert_paper(Paper(
            id="no-distill-paper",
            source=PaperSource.ARXIV,
            source_id="test.1",
            title="Paper without distillation",
            authors=["Author"],
            status="collected",
        ))

        result = await agent.implement("no-distill-paper")
        assert result is None

    @pytest.mark.asyncio
    async def test_prototyper_requires_implementation(self, test_llm, test_db,
                                                        test_vector_store, tmp_config):
        agent = PrototyperAgent(test_llm, test_db, test_vector_store, tmp_config)

        await test_db.upsert_paper(Paper(
            id="no-impl-paper",
            source=PaperSource.ARXIV,
            source_id="test.2",
            title="Paper without implementation",
            authors=["Author"],
            status="distilled",
        ))

        result = await agent.prototype("no-impl-paper")
        assert result is None

    @pytest.mark.asyncio
    async def test_implementer_fails_for_nonexistent_paper(self, test_llm, test_db,
                                                             test_vector_store, tmp_config):
        agent = ImplementerAgent(test_llm, test_db, test_vector_store, tmp_config)
        result = await agent.implement("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_prototyper_fails_for_nonexistent_paper(self, test_llm, test_db,
                                                            test_vector_store, tmp_config):
        agent = PrototyperAgent(test_llm, test_db, test_vector_store, tmp_config)
        result = await agent.prototype("nonexistent-id")
        assert result is None


class TestOrchestratorIntegration:
    @pytest.mark.asyncio
    async def test_orchestrator_has_all_four_agents(self, test_orchestrator):
        orch = test_orchestrator
        assert hasattr(orch, "collector")
        assert hasattr(orch, "distiller")
        assert hasattr(orch, "implementer")
        assert hasattr(orch, "prototyper")

    @pytest.mark.asyncio
    async def test_orchestrator_implement_method_exists(self, test_orchestrator):
        assert hasattr(test_orchestrator, "implement_paper")
        assert callable(test_orchestrator.implement_paper)

    @pytest.mark.asyncio
    async def test_orchestrator_prototype_method_exists(self, test_orchestrator):
        assert hasattr(test_orchestrator, "prototype_paper")
        assert callable(test_orchestrator.prototype_paper)
