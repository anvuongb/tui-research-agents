"""Tests for Database.count_agent_runs_by_status (H7) and the
benchmark analysis column migration (H3)."""

import pytest

from tui_agents.storage.database import Database
from tui_agents.storage.models import (
    AgentRun,
    AgentType,
    BenchmarkResult,
    Paper,
    PaperSource,
    StageStatus,
)


@pytest.mark.integration
class TestCountAgentRunsByStatus:
    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_dict(self, test_db: Database):
        counts = await test_db.count_agent_runs_by_status()
        assert counts == {}

    @pytest.mark.asyncio
    async def test_counts_by_status(self, test_db: Database):
        await test_db.upsert_paper(Paper(
            id="p1", source=PaperSource.ARXIV, source_id="a1",
            title="T", authors=["A"],
        ))
        await test_db.upsert_paper(Paper(
            id="p2", source=PaperSource.ARXIV, source_id="a2",
            title="T2", authors=["A"],
        ))
        await test_db.upsert_paper(Paper(
            id="p3", source=PaperSource.ARXIV, source_id="a3",
            title="T3", authors=["A"],
        ))

        await test_db.create_agent_run(AgentRun(
            id="r1", paper_id="p1", agent_type=AgentType.DISTILLER,
            status=StageStatus.COMPLETED,
        ))
        await test_db.create_agent_run(AgentRun(
            id="r2", paper_id="p2", agent_type=AgentType.DISTILLER,
            status=StageStatus.IN_PROGRESS,
        ))
        await test_db.create_agent_run(AgentRun(
            id="r3", paper_id="p3", agent_type=AgentType.IMPLEMENTER,
            status=StageStatus.FAILED,
        ))

        counts = await test_db.count_agent_runs_by_status()
        assert counts.get("completed") == 1
        assert counts.get("in_progress") == 1
        assert counts.get("failed") == 1

    @pytest.mark.asyncio
    async def test_counts_only_latest_run_per_paper_agent(
        self, test_db: Database
    ):
        """If a paper is re-run, only the latest run counts."""
        await test_db.upsert_paper(Paper(
            id="p-retry", source=PaperSource.ARXIV, source_id="ar",
            title="Retry", authors=["A"],
        ))

        await test_db.create_agent_run(AgentRun(
            id="old", paper_id="p-retry", agent_type=AgentType.DISTILLER,
            status=StageStatus.FAILED, created_at="2024-01-01T00:00:00",
        ))
        await test_db.create_agent_run(AgentRun(
            id="new", paper_id="p-retry", agent_type=AgentType.DISTILLER,
            status=StageStatus.COMPLETED, created_at="2024-06-01T00:00:00",
        ))

        counts = await test_db.count_agent_runs_by_status()
        assert counts.get("completed") == 1
        assert counts.get("failed", 0) == 0


@pytest.mark.integration
class TestAnalysisColumnMigration:
    @pytest.mark.asyncio
    async def test_analysis_roundtrip(self, test_db: Database):
        await test_db.upsert_paper(Paper(
            id="m1", source=PaperSource.ARXIV, source_id="am1",
            title="M", authors=["A"],
        ))
        await test_db.create_agent_run(AgentRun(
            id="mr1", paper_id="m1", agent_type=AgentType.BENCHMARKER,
            status=StageStatus.COMPLETED,
        ))

        bench = BenchmarkResult(
            id="b1", paper_id="m1", run_id="mr1",
            metrics={"acc": 0.9}, passed_threshold=True,
            analysis="All metrics within expected range.",
        )
        await test_db.save_benchmark(bench)

        loaded = await test_db.get_latest_benchmark("m1")
        assert loaded is not None
        assert loaded.analysis == "All metrics within expected range."

    @pytest.mark.asyncio
    async def test_default_analysis_is_empty_string(self, test_db: Database):
        await test_db.upsert_paper(Paper(
            id="m2", source=PaperSource.ARXIV, source_id="am2",
            title="M2", authors=["A"],
        ))
        await test_db.create_agent_run(AgentRun(
            id="mr2", paper_id="m2", agent_type=AgentType.BENCHMARKER,
            status=StageStatus.COMPLETED,
        ))
        bench = BenchmarkResult(
            id="b2", paper_id="m2", run_id="mr2", metrics={},
        )
        await test_db.save_benchmark(bench)

        loaded = await test_db.get_latest_benchmark("m2")
        assert loaded is not None
        assert loaded.analysis == ""
