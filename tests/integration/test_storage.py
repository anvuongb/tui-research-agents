"""Integration tests for SQLite database operations.

Uses temporary databases — no persistent data is modified.
"""

import pytest
import pytest_asyncio

from tui_agents.storage.database import Database
from tui_agents.storage.models import (
    AgentRun,
    AgentType,
    BenchmarkResult,
    Distillation,
    Implementation,
    Paper,
    PaperSource,
    StageStatus,
)
from tui_agents.utils.config import Config


@pytest.mark.integration
class TestDatabase:
    @pytest.mark.asyncio
    async def test_upsert_and_get_paper(self, test_db: Database):
        paper = Paper(
            id="test-paper-1",
            source=PaperSource.ARXIV,
            source_id="arxiv:2401.00001",
            title="Test Paper on Diffusion Models",
            authors=["Alice Researcher", "Bob Scientist"],
            abstract="This paper explores diffusion models and optimal transport.",
            url="https://arxiv.org/abs/2401.00001",
            published_date="2024-01-15",
            tags=["diffusion", "optimal-transport"],
            status="collected",
        )
        await test_db.upsert_paper(paper)

        retrieved = await test_db.get_paper("test-paper-1")
        assert retrieved is not None
        assert retrieved.title == "Test Paper on Diffusion Models"
        assert retrieved.source == PaperSource.ARXIV
        assert len(retrieved.authors) == 2
        assert retrieved.status == "collected"

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, test_db: Database):
        paper = Paper(
            id="test-update-1",
            source=PaperSource.ARXIV,
            source_id="arxiv:2401.00002",
            title="Original Title",
            authors=["Author One"],
            status="new",
        )
        await test_db.upsert_paper(paper)

        paper.title = "Updated Title"
        paper.status = "collected"
        await test_db.upsert_paper(paper)

        retrieved = await test_db.get_paper("test-update-1")
        assert retrieved is not None
        assert retrieved.title == "Updated Title"
        assert retrieved.status == "collected"

    @pytest.mark.asyncio
    async def test_get_nonexistent_paper(self, test_db: Database):
        paper = await test_db.get_paper("nonexistent-id")
        assert paper is None

    @pytest.mark.asyncio
    async def test_list_papers(self, test_db: Database):
        for i in range(3):
            paper = Paper(
                id=f"list-test-{i}",
                source=PaperSource.ARXIV,
                source_id=f"arxiv:list.{i}",
                title=f"Paper {i}",
                authors=["Author"],
                status="collected",
            )
            await test_db.upsert_paper(paper)

        papers = await test_db.list_papers()
        assert len(papers) >= 3

    @pytest.mark.asyncio
    async def test_list_papers_filtered_by_status(self, test_db: Database):
        await test_db.upsert_paper(Paper(
            id="filter-collected", source=PaperSource.ARXIV, source_id="a",
            title="Collected", authors=["A"], status="collected",
        ))
        await test_db.upsert_paper(Paper(
            id="filter-distilled", source=PaperSource.ARXIV, source_id="b",
            title="Distilled", authors=["B"], status="distilled",
        ))

        collected = await test_db.list_papers(status="collected")
        distilled = await test_db.list_papers(status="distilled")

        assert any(p.id == "filter-collected" for p in collected)
        assert any(p.id == "filter-distilled" for p in distilled)

    @pytest.mark.asyncio
    async def test_count_papers(self, test_db: Database):
        initial = await test_db.count_papers()
        await test_db.upsert_paper(Paper(
            id="count-test", source=PaperSource.ARXIV, source_id="c",
            title="Count Test", authors=["A"], status="collected",
        ))
        assert await test_db.count_papers() == initial + 1

    @pytest.mark.asyncio
    async def test_update_paper_status(self, test_db: Database):
        await test_db.upsert_paper(Paper(
            id="status-test", source=PaperSource.ARXIV, source_id="s",
            title="Status Test", authors=["A"], status="new",
        ))
        await test_db.update_paper_status("status-test", "distilled")

        paper = await test_db.get_paper("status-test")
        assert paper is not None
        assert paper.status == "distilled"


@pytest.mark.integration
class TestAgentRuns:
    @pytest.mark.asyncio
    async def test_create_and_get_agent_run(self, test_db: Database):
        run = AgentRun(
            id="run-1",
            paper_id="paper-1",
            agent_type=AgentType.DISTILLER,
            input_data={"query": "test"},
            status=StageStatus.IN_PROGRESS,
        )
        await test_db.create_agent_run(run)

        retrieved = await test_db.get_agent_run("run-1")
        assert retrieved is not None
        assert retrieved.agent_type == AgentType.DISTILLER
        assert retrieved.status == StageStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_update_agent_run(self, test_db: Database):
        run = AgentRun(
            id="run-update",
            paper_id="paper-2",
            agent_type=AgentType.COLLECTOR,
            status=StageStatus.PENDING,
        )
        await test_db.create_agent_run(run)

        run.status = StageStatus.COMPLETED
        run.output_data = {"result": "done"}
        run.error_message = None
        await test_db.update_agent_run(run)

        retrieved = await test_db.get_agent_run("run-update")
        assert retrieved is not None
        assert retrieved.status == StageStatus.COMPLETED
        assert retrieved.output_data == {"result": "done"}

    @pytest.mark.asyncio
    async def test_get_runs_for_paper(self, test_db: Database):
        for i in range(2):
            run = AgentRun(
                id=f"paper-runs-{i}",
                paper_id="multi-run-paper",
                agent_type=AgentType.DISTILLER,
                status=StageStatus.COMPLETED,
            )
            await test_db.create_agent_run(run)

        runs = await test_db.get_runs_for_paper("multi-run-paper")
        assert len(runs) == 2

    @pytest.mark.asyncio
    async def test_get_latest_run(self, test_db: Database):
        await test_db.create_agent_run(AgentRun(
            id="old-run", paper_id="latest-test", agent_type=AgentType.DISTILLER,
            status=StageStatus.COMPLETED,
        ))
        await test_db.create_agent_run(AgentRun(
            id="new-run", paper_id="latest-test", agent_type=AgentType.DISTILLER,
            status=StageStatus.COMPLETED,
        ))

        latest = await test_db.get_latest_run("latest-test", "distiller")
        assert latest is not None
        assert latest.id == "new-run"


@pytest.mark.integration
class TestDistillationsAndImplementations:
    @pytest.mark.asyncio
    async def test_save_and_get_distillation(self, test_db: Database):
        d = Distillation(
            id="dist-1", paper_id="paper-1", run_id="run-1",
            summary="A summary of the paper.",
            methodology="Step 1, Step 2, Step 3.",
            contributions=["Contribution 1", "Contribution 2"],
            limitations=["Limitation 1"],
            key_equations=["$F = ma$"],
            related_work=["Related work A"],
        )
        await test_db.save_distillation(d)

        retrieved = await test_db.get_distillation("paper-1")
        assert retrieved is not None
        assert retrieved.summary == "A summary of the paper."
        assert len(retrieved.contributions) == 2

    @pytest.mark.asyncio
    async def test_save_and_get_implementation(self, test_db: Database):
        impl = Implementation(
            id="impl-1", paper_id="paper-1", run_id="run-1",
            code="def train(): pass",
            language="python",
            dependencies=["torch", "numpy"],
            tests="def test_train(): pass",
        )
        await test_db.save_implementation(impl)

        retrieved = await test_db.get_implementation("paper-1")
        assert retrieved is not None
        assert retrieved.code == "def train(): pass"
        assert "torch" in retrieved.dependencies

    @pytest.mark.asyncio
    async def test_get_nonexistent_distillation(self, test_db: Database):
        d = await test_db.get_distillation("nonexistent")
        assert d is None

    @pytest.mark.asyncio
    async def test_get_nonexistent_implementation(self, test_db: Database):
        impl = await test_db.get_implementation("nonexistent")
        assert impl is None


@pytest.mark.integration
class TestBenchmarks:
    @pytest.mark.asyncio
    async def test_save_and_get_benchmarks(self, test_db: Database):
        b1 = BenchmarkResult(
            id="bench-1", paper_id="paper-1", run_id="run-1",
            metrics={"accuracy": 0.95, "f1": 0.93},
            compared_to_baseline=True,
            passed_threshold=True,
        )
        b2 = BenchmarkResult(
            id="bench-2", paper_id="paper-1", run_id="run-2",
            metrics={"accuracy": 0.87},
            compared_to_baseline=True,
            passed_threshold=False,
        )
        await test_db.save_benchmark(b1)
        await test_db.save_benchmark(b2)

        benchmarks = await test_db.get_benchmarks("paper-1")
        assert len(benchmarks) == 2

    @pytest.mark.asyncio
    async def test_get_latest_benchmark(self, test_db: Database):
        await test_db.save_benchmark(BenchmarkResult(
            id="old-bench", paper_id="latest-bench", run_id="old",
            metrics={"score": 0.8},
        ))
        await test_db.save_benchmark(BenchmarkResult(
            id="new-bench", paper_id="latest-bench", run_id="new",
            metrics={"score": 0.9},
        ))

        latest = await test_db.get_latest_benchmark("latest-bench")
        assert latest is not None
        assert latest.id == "new-bench"
