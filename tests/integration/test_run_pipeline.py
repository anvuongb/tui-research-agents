"""Tests for Orchestrator.run_pipeline retry loop.

Covers the H3 regression: benchmark analysis from iteration N must reach
the implementer's previous_benchmark_context on iteration N+1.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tui_agents.storage.models import (
    BenchmarkResult,
    Implementation,
    Paper,
    PaperSource,
)


def _impl(i: int) -> Implementation:
    return Implementation(
        id=f"impl-{i}",
        paper_id="pipe-paper",
        run_id=f"run-{i}",
        code=f"# version {i}",
        dependencies=["torch"],
    )


def _bench(passed: bool, analysis: str) -> BenchmarkResult:
    return BenchmarkResult(
        id="bench-x",
        paper_id="pipe-paper",
        run_id="run-x",
        metrics={"loss": 0.5},
        passed_threshold=passed,
        analysis=analysis,
    )


@pytest.mark.integration
class TestRunPipelineLoop:
    @pytest.mark.asyncio
    async def test_pass_on_first_iteration_stops(
        self, test_orchestrator, test_db
    ):
        orch = test_orchestrator
        await test_db.upsert_paper(Paper(
            id="pipe-paper", source=PaperSource.ARXIV, source_id="p.1",
            title="Pipe", authors=["A"], status="distilled",
        ))

        orch.implementer.implement = AsyncMock(return_value=_impl(1))
        orch.prototyper.prototype = AsyncMock(return_value={"script": "pass"})
        orch.benchmarker.benchmark = AsyncMock(return_value=_bench(True, "good"))

        # list_implementations needs a real row for impl_idx lookup
        await test_db.save_implementation(_impl(1))

        results = await orch.run_pipeline("pipe-paper")

        assert results["status"] == "passed"
        assert results["total_iterations"] == 1
        orch.implementer.implement.assert_called_once()
        # First iteration has no prior benchmark context
        _, kwargs = orch.implementer.implement.call_args
        assert kwargs.get("previous_benchmark_context") is None

    @pytest.mark.asyncio
    async def test_failed_benchmark_retries_with_analysis(
        self, test_orchestrator, test_db
    ):
        """H3 regression: analysis from a failed benchmark must appear in
        the next iteration's previous_benchmark_context."""
        orch = test_orchestrator
        orch.config._data["pipeline"]["loop"]["max_iterations"] = 3

        await test_db.upsert_paper(Paper(
            id="pipe-paper", source=PaperSource.ARXIV, source_id="p.1",
            title="Pipe", authors=["A"], status="distilled",
        ))

        analysis_1 = "First attempt: loss stuck at 0.9. Add dropout."
        analysis_2 = "Second attempt: still 0.7. Try lower LR."

        bench_calls = [
            _bench(False, analysis_1),
            _bench(True, analysis_2),
        ]

        orch.implementer.implement = AsyncMock(return_value=_impl(1))
        orch.prototyper.prototype = AsyncMock(return_value={"script": "pass"})
        orch.benchmarker.benchmark = AsyncMock(side_effect=bench_calls)

        impl1, impl2 = _impl(1), _impl(2)
        await test_db.save_implementation(impl1)
        await test_db.save_implementation(impl2)
        # list_implementations is called by run_pipeline; let the mock
        # orchestrator's db return both so impl_idx advances
        orch.implementer.implement = AsyncMock(side_effect=[impl1, impl2])

        results = await orch.run_pipeline("pipe-paper")

        assert results["status"] == "passed"
        assert results["total_iterations"] == 2

        # Second implement call must carry the first benchmark's analysis
        calls = orch.implementer.implement.call_args_list
        assert len(calls) == 2
        first_kwargs = calls[0].kwargs
        second_kwargs = calls[1].kwargs
        assert first_kwargs.get("previous_benchmark_context") is None
        ctx = second_kwargs.get("previous_benchmark_context")
        assert ctx is not None
        assert ctx["analysis"] == analysis_1
        assert ctx["passed"] is False
        assert ctx["previous_metrics"] == {"loss": 0.5}

    @pytest.mark.asyncio
    async def test_stops_at_max_iterations(
        self, test_orchestrator, test_db
    ):
        orch = test_orchestrator
        orch.config._data["pipeline"]["loop"]["max_iterations"] = 2

        await test_db.upsert_paper(Paper(
            id="pipe-paper", source=PaperSource.ARXIV, source_id="p.1",
            title="Pipe", authors=["A"], status="distilled",
        ))

        orch.implementer.implement = AsyncMock(return_value=_impl(1))
        orch.prototyper.prototype = AsyncMock(return_value={"script": "pass"})
        orch.benchmarker.benchmark = AsyncMock(
            return_value=_bench(False, "still broken")
        )
        await test_db.save_implementation(_impl(1))

        results = await orch.run_pipeline("pipe-paper")

        assert results["status"] == "max_iterations"
        assert results["total_iterations"] == 2

    @pytest.mark.asyncio
    async def test_implement_failure_breaks_loop(
        self, test_orchestrator, test_db
    ):
        orch = test_orchestrator
        await test_db.upsert_paper(Paper(
            id="pipe-paper", source=PaperSource.ARXIV, source_id="p.1",
            title="Pipe", authors=["A"], status="distilled",
        ))
        orch.implementer.implement = AsyncMock(return_value=None)
        orch.benchmarker.benchmark = AsyncMock()

        results = await orch.run_pipeline("pipe-paper")

        assert len(results["iterations"]) == 1
        assert results["iterations"][0]["implementer"]["completed"] is False
        orch.benchmarker.benchmark.assert_not_called()

    @pytest.mark.asyncio
    async def test_nonexistent_paper_returns_error(self, test_orchestrator):
        results = await test_orchestrator.run_pipeline("no-such-paper")
        assert results["status"] == "error"
