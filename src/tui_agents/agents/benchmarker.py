from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine

from tui_agents.agents.base import BaseAgent
from tui_agents.agents.runner import DockerRunner, RunResult
from tui_agents.agents.runtime_estimator import RuntimeEstimator
from tui_agents.llm.client import LLMClient
from tui_agents.storage.database import Database
from tui_agents.storage.models import BenchmarkResult, Implementation, StageStatus
from tui_agents.storage.vector_store import VectorStore
from tui_agents.utils.config import Config


ProgressFn = Callable[[str, str, float], Coroutine[Any, Any, None]]

BENCHMARKER_SYSTEM_PROMPT = """You are an expert ML engineer evaluating a paper implementation's performance. Your task is to generate a benchmark script, run it, and evaluate the results.

Follow these steps:
1. Generate a self-contained Python script (benchmark.py) that:
   - Imports the prototype
   - Runs the core compute/training loop
   - Captures key metrics (accuracy, loss, runtime, parameter count, FID for generative models)
   - Prints a single JSON line at the end with all metrics
   - Uses small synthetic data — runs CPU-only in Docker

2. After running, evaluate whether the results meet expectations:
   - Compare metrics to what the paper claims (or reasonable defaults)
   - Note any failures or anomalies
   - Suggest specific improvements for the next iteration

Output a structured JSON response:
- benchmark_script: Complete Python script that runs the prototype and prints JSON metrics
- expected_metrics: List of metric names the script will output
- target_values: Object mapping metric names to target values from the paper (or reasonable defaults)"""


class BenchmarkerAgent(BaseAgent):
    agent_type = "benchmarker"

    def __init__(
        self,
        llm: LLMClient,
        database: Database,
        vector_store: VectorStore,
        config: Config,
    ):
        super().__init__(llm, database)
        self.vector_store = vector_store
        self._runner = DockerRunner(config)
        self._estimator = RuntimeEstimator(llm)
        self._code_dir = Path(config.code_dir)
        self._benchmarks_dir = Path(config.benchmarks_dir)
        self._benchmarks_dir.mkdir(parents=True, exist_ok=True)

    async def benchmark(
        self,
        paper_id: str,
        progress: ProgressFn | None = None,
        impl_version_idx: int = 0,
    ) -> BenchmarkResult | None:
        paper = await self.db.get_paper(paper_id)
        if not paper:
            if progress:
                await progress("error", f"Paper not found: {paper_id}", 0.0)
            return None

        impls = await self.db.list_implementations(paper_id)
        if not impls or impl_version_idx >= len(impls):
            if progress:
                await progress("error", "No implementation found. Implement first.", 0.0)
            return None

        implementation = impls[impl_version_idx]
        run_id = await self.start_run(paper_id)

        try:
            if progress:
                await progress("loading", f"Loading implementation v{impl_version_idx+1}...", 0.05)

            impl_dir = self._code_dir / paper_id / implementation.id[:8]
            prototype_path = impl_dir / "prototype.py"
            prototype_code = ""
            if prototype_path.exists():
                prototype_code = prototype_path.read_text()

            if progress:
                await progress("estimating", "Estimating runtime...", 0.1)
            estimate = await self._estimator.estimate(implementation, prototype_code)

            if progress:
                await progress("generating", "Generating benchmark script...", 0.15)

            benchmark_script = await self._generate_benchmark(implementation, prototype_code, progress)

            if not benchmark_script:
                if progress:
                    await progress("error", "Failed to generate benchmark script", 0.0)
                return None

            bench_dir = self._benchmarks_dir / paper_id / run_id
            bench_dir.mkdir(parents=True, exist_ok=True)
            (bench_dir / "benchmark.py").write_text(benchmark_script)
            (bench_dir / "prototype.py").write_text(prototype_code)

            if progress:
                await progress("building", "Building Docker image...", 0.25)

            result = await self._runner.run(bench_dir, progress=progress)

            metrics = self._parse_metrics(result.stdout)

            if progress:
                await progress("evaluating", "Evaluating benchmark results...", 0.7)

            passed, analysis = await self._evaluate_results(
                paper.title, metrics, result, estimate, progress
            )

            bench = BenchmarkResult(
                id=str(uuid.uuid4()),
                paper_id=paper_id,
                run_id=run_id,
                metrics=metrics,
                compared_to_baseline=False,
                passed_threshold=passed,
                created_at=datetime.now().isoformat(),
            )

            await self.db.save_benchmark(bench)
            await self.db.update_paper_status(paper_id, "benchmarked")

            self._save_result_files(bench_dir, result, estimate, analysis)

            output = {
                "benchmark_id": bench.id,
                "metrics": metrics,
                "passed_threshold": passed,
                "elapsed": result.elapsed_seconds,
            }
            await self.complete_run(output)

            if progress:
                status_msg = "PASSED" if passed else "FAILED"
                await progress("done", f"Benchmark {status_msg}: {result.elapsed_seconds:.0f}s", 1.0)

            return bench

        except Exception as e:
            await self.fail_run(str(e))
            if progress:
                await progress("error", f"Benchmark failed: {e}", 0.0)
            return None

    def _parse_metrics(self, stdout: str) -> dict[str, Any]:
        lines = stdout.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {"raw_output": stdout[:500]}

    def _save_result_files(
        self,
        bench_dir: Path,
        result: RunResult,
        estimate: dict[str, Any],
        analysis: str = "",
    ) -> None:
        (bench_dir / "output.txt").write_text(result.stdout)
        (bench_dir / "error.txt").write_text(result.stderr)
        summary = {
            "exit_code": result.exit_code,
            "elapsed_seconds": result.elapsed_seconds,
            "timed_out": result.timed_out,
            "estimated_seconds": estimate.get("estimate_seconds"),
            "analysis": analysis,
        }
        (bench_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    async def _generate_benchmark(
        self,
        implementation: Implementation,
        prototype_code: str,
        progress: ProgressFn | None = None,
    ) -> str | None:
        code_excerpt = implementation.code
        if len(code_excerpt) > 6000:
            code_excerpt = code_excerpt[:6000] + "\n# ... (truncated)"

        proto_excerpt = prototype_code
        if len(proto_excerpt) > 3000:
            proto_excerpt = proto_excerpt[:3000] + "\n# ... (truncated)"

        user_prompt = f"""Generate a benchmark script for this ML implementation.

## Implementation Code
```python
{code_excerpt}
```

## Prototype Code
```python
{proto_excerpt}
```

## Dependencies
{', '.join(implementation.dependencies[:8])}

Create a self-contained benchmark.py that runs the prototype, captures metrics, and prints a single JSON line at the end. Use small synthetic data. The script runs CPU-only in Docker with 4GB RAM."""

        schema = {
            "type": "object",
            "properties": {
                "benchmark_script": {
                    "type": "string",
                    "description": "Complete self-contained Python benchmark script",
                },
                "expected_metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of metric names the script will output",
                },
                "target_values": {
                    "type": "object",
                    "description": "Target metric values from the paper or reasonable defaults",
                },
            },
            "required": ["benchmark_script", "expected_metrics"],
        }

        try:
            result = await self.llm.chat_structured(
                system_prompt=BENCHMARKER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_schema=schema,
                max_tokens=8192,
            )
            if "error" in result:
                return None
            return self.strip_code_fences(result.get("benchmark_script", ""))
        except Exception as e:
            if progress:
                await progress("error", f"Benchmark generation failed: {e}", 0.2)
            return None

    async def _evaluate_results(
        self,
        paper_title: str,
        metrics: dict[str, Any],
        result: RunResult,
        estimate: dict[str, Any],
        progress: ProgressFn | None = None,
    ) -> tuple[bool, str]:
        if result.timed_out:
            return False, "Execution timed out."
        if result.exit_code != 0:
            return False, f"Execution failed with exit code {result.exit_code}."

        if not metrics or list(metrics.keys()) == ["raw_output"]:
            return False, "Could not parse metrics from output."

        eval_prompt = f"""Evaluate these benchmark results.

Paper: {paper_title}
Metrics: {json.dumps(metrics)}
Elapsed: {result.elapsed_seconds:.1f}s
Estimated: {estimate.get('estimate_seconds', 'N/A')}s

Based on the metrics, did the implementation produce reasonable results?
A passing implementation should have plausible metric values (not NaN, not near-zero loss for complex tasks, reasonable runtime).

Respond with JSON:
- passed: boolean
- analysis: 2-3 sentences explaining the verdict and suggestions for improvement"""

        schema = {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "analysis": {"type": "string"},
            },
            "required": ["passed", "analysis"],
        }

        try:
            result_eval = await self.llm.chat_structured(
                system_prompt="You evaluate ML benchmark results.",
                user_prompt=eval_prompt,
                response_schema=schema,
                max_tokens=1024,
            )
            if "error" in result_eval:
                return False, "Could not evaluate results."
            return result_eval.get("passed", False), result_eval.get("analysis", "")
        except Exception:
            return False, "Could not evaluate results."

    async def execute(self, paper_id: str, **kwargs) -> dict[str, Any]:
        progress_fn = kwargs.get("progress_fn")
        impl_idx = kwargs.get("impl_version_idx", 0)
        bench = await self.benchmark(paper_id, progress=progress_fn, impl_version_idx=impl_idx)
        if bench:
            return {
                "status": "completed",
                "benchmark_id": bench.id,
                "metrics": bench.metrics,
                "passed_threshold": bench.passed_threshold,
            }
        return {"status": "failed", "error": "Benchmark returned no result"}
