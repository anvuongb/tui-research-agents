"""Tests for BenchmarkerAgent — C2 (entrypoint/requirements) and H3
(analysis persisted) regression coverage.

LLM and DockerRunner are mocked; no network or Docker daemon needed.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tui_agents.agents.benchmarker import BenchmarkerAgent
from tui_agents.storage.models import (
    BenchmarkResult,
    Implementation,
    Paper,
    PaperSource,
)


def _make_agent(test_llm, test_db, test_vector_store, tmp_config):
    return BenchmarkerAgent(test_llm, test_db, test_vector_store, tmp_config)


async def _seed_paper_and_impl(test_db, tmp_config, paper_id="bench-paper"):
    await test_db.upsert_paper(Paper(
        id=paper_id,
        source=PaperSource.ARXIV,
        source_id="arxiv:bench.1",
        title="Benchmark Paper",
        authors=["A"],
        status="prototyped",
    ))
    impl = Implementation(
        id="impl-bench-0123456789ab",
        paper_id=paper_id,
        run_id="run-1",
        code="def train(): return {'loss': 0.1}",
        dependencies=["torch>=2.0", "numpy"],
        tests="def test_train(): pass",
    )
    await test_db.save_implementation(impl)

    impl_dir = Path(tmp_config.code_dir) / paper_id / impl.id[:8]
    impl_dir.mkdir(parents=True, exist_ok=True)
    (impl_dir / "prototype.py").write_text("def run(): print('proto')")
    (impl_dir / "requirements.txt").write_text("torch>=2.0\nnumpy")
    return paper_id, impl


@pytest.mark.integration
class TestBenchmarkEntrypoint:
    @pytest.mark.asyncio
    async def test_benchmark_passes_entrypoint_and_writes_requirements(
        self, test_llm, test_db, test_vector_store, tmp_config
    ):
        """C2 regression: runner must be called with entrypoint='benchmark.py'
        and bench_dir must contain requirements.txt."""
        agent = _make_agent(test_llm, test_db, test_vector_store, tmp_config)
        paper_id, impl = await _seed_paper_and_impl(test_db, tmp_config)

        captured: dict = {}

        async def fake_estimate(implementation, prototype_code):
            return {"estimate_seconds": 10}

        async def fake_generate(implementation, prototype_code, progress=None):
            return "import prototype\nprint('{\"acc\": 0.9}')"

        async def fake_run(code_dir: Path, progress=None, entrypoint="prototype.py"):
            captured["entrypoint"] = entrypoint
            captured["files"] = sorted(p.name for p in code_dir.iterdir())
            captured["requirements"] = (code_dir / "requirements.txt").read_text()
            from tui_agents.agents.runner import RunResult
            return RunResult(stdout='{"acc": 0.9}', exit_code=0, elapsed_seconds=1.0)

        async def fake_eval(*args, **kwargs):
            return True, "Looks good."

        with (
            patch.object(agent._estimator, "estimate", side_effect=fake_estimate),
            patch.object(agent, "_generate_benchmark", side_effect=fake_generate),
            patch.object(agent._runner, "run", side_effect=fake_run),
            patch.object(agent, "_evaluate_results", side_effect=fake_eval),
        ):
            bench = await agent.benchmark(paper_id)

        assert bench is not None
        assert captured["entrypoint"] == "benchmark.py"
        assert "benchmark.py" in captured["files"]
        assert "prototype.py" in captured["files"]
        assert "requirements.txt" in captured["files"]
        assert "torch>=2.0" in captured["requirements"]


@pytest.mark.integration
class TestBenchmarkAnalysisPersistence:
    @pytest.mark.asyncio
    async def test_analysis_saved_and_roundtrips(
        self, test_llm, test_db, test_vector_store, tmp_config
    ):
        """H3 regression: analysis must be stored on BenchmarkResult and
        readable back from the DB (orchestrator feeds it to the retry prompt)."""
        agent = _make_agent(test_llm, test_db, test_vector_store, tmp_config)
        paper_id, impl = await _seed_paper_and_impl(test_db, tmp_config)

        analysis_text = "Loss plateaued at 0.5; increase learning rate and add warmup."

        async def fake_estimate(implementation, prototype_code):
            return {"estimate_seconds": 10}

        async def fake_generate(implementation, prototype_code, progress=None):
            return "print('{\"loss\": 0.5}')"

        async def fake_run(code_dir: Path, progress=None, entrypoint="prototype.py"):
            from tui_agents.agents.runner import RunResult
            return RunResult(stdout='{"loss": 0.5}', exit_code=0, elapsed_seconds=1.0)

        async def fake_eval(*args, **kwargs):
            return False, analysis_text

        with (
            patch.object(agent._estimator, "estimate", side_effect=fake_estimate),
            patch.object(agent, "_generate_benchmark", side_effect=fake_generate),
            patch.object(agent._runner, "run", side_effect=fake_run),
            patch.object(agent, "_evaluate_results", side_effect=fake_eval),
        ):
            bench = await agent.benchmark(paper_id)

        assert bench is not None
        assert bench.analysis == analysis_text
        assert bench.passed_threshold is False

        loaded = await test_db.get_latest_benchmark(paper_id)
        assert loaded is not None
        assert loaded.analysis == analysis_text

        all_benches = await test_db.get_benchmarks(paper_id)
        assert any(b.analysis == analysis_text for b in all_benches)


@pytest.mark.integration
class TestBenchmarkParseMetrics:
    @pytest.mark.asyncio
    async def test_parses_json_line_from_stdout(
        self, test_llm, test_db, test_vector_store, tmp_config
    ):
        agent = _make_agent(test_llm, test_db, test_vector_store, tmp_config)
        stdout = "starting...\nrunning...\n{\"acc\": 0.87, \"loss\": 0.12}"
        metrics = agent._parse_metrics(stdout)
        assert metrics == {"acc": 0.87, "loss": 0.12}

    @pytest.mark.asyncio
    async def test_unparseable_stdout_falls_back_to_raw(
        self, test_llm, test_db, test_vector_store, tmp_config
    ):
        agent = _make_agent(test_llm, test_db, test_vector_store, tmp_config)
        metrics = agent._parse_metrics("no json here")
        assert "raw_output" in metrics
