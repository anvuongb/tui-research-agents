"""Tests for DockerRunner — entrypoint selection, context prep, and
hardening flags. Covers the C2 and H8 fixes.

Subprocess calls are mocked; no Docker daemon is required.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tui_agents.agents.runner import DOCKERFILE_TEMPLATE, DockerRunner, RunResult
from tui_agents.utils.config import Config


@pytest.fixture
def runner(tmp_config: Config) -> DockerRunner:
    return DockerRunner(tmp_config)


class TestDockerfileTemplate:
    def test_default_entrypoint_is_prototype(self):
        out = DOCKERFILE_TEMPLATE.format(image="python:3.11-slim", entrypoint="prototype.py")
        assert 'ENTRYPOINT ["python", "prototype.py"]' in out

    def test_benchmark_entrypoint(self):
        out = DOCKERFILE_TEMPLATE.format(image="python:3.11-slim", entrypoint="benchmark.py")
        assert 'ENTRYPOINT ["python", "benchmark.py"]' in out


class TestPrepareContext:
    def test_copies_all_py_files_and_requirements(self, runner: DockerRunner, tmp_path: Path):
        code_dir = tmp_path / "code"
        code_dir.mkdir()
        (code_dir / "prototype.py").write_text("print('proto')")
        (code_dir / "benchmark.py").write_text("print('bench')")
        (code_dir / "requirements.txt").write_text("torch>=2.0")
        (code_dir / "ignored.txt").write_text("not copied")

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        runner._prepare_context(code_dir, work_dir, "benchmark.py")

        assert (work_dir / "prototype.py").exists()
        assert (work_dir / "benchmark.py").exists()
        assert (work_dir / "requirements.txt").read_text() == "torch>=2.0"
        assert not (work_dir / "ignored.txt").exists()

        dockerfile = (work_dir / "Dockerfile").read_text()
        assert 'ENTRYPOINT ["python", "benchmark.py"]' in dockerfile

    def test_missing_requirements_gets_empty_file(self, runner: DockerRunner, tmp_path: Path):
        code_dir = tmp_path / "code"
        code_dir.mkdir()
        (code_dir / "prototype.py").write_text("pass")

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        runner._prepare_context(code_dir, work_dir, "prototype.py")

        assert (work_dir / "requirements.txt").exists()
        assert (work_dir / "requirements.txt").read_text() == ""

    def test_c2_regression_benchmark_dir_prepares_correctly(
        self, runner: DockerRunner, tmp_path: Path
    ):
        """C2 regression: a bench_dir with benchmark.py + prototype.py +
        requirements.txt must produce a Dockerfile whose entrypoint is
        benchmark.py (the original bug ran prototype.py instead)."""
        bench_dir = tmp_path / "bench"
        bench_dir.mkdir()
        (bench_dir / "benchmark.py").write_text("import prototype\nprint('{}')")
        (bench_dir / "prototype.py").write_text("def run(): pass")
        (bench_dir / "requirements.txt").write_text("numpy")

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        runner._prepare_context(bench_dir, work_dir, "benchmark.py")

        dockerfile = (work_dir / "Dockerfile").read_text()
        assert "benchmark.py" in dockerfile
        assert (work_dir / "benchmark.py").exists()
        assert (work_dir / "prototype.py").exists()
        assert (work_dir / "requirements.txt").read_text() == "numpy"


class TestRunCommandHardening:
    """Verify docker run receives the security flags (H8)."""

    @staticmethod
    def _make_proc():
        class _Stream:
            async def readline(self):
                return b""

        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"ok", b""))
        proc.wait = AsyncMock(return_value=0)
        proc.stdout = _Stream()
        proc.stderr = _Stream()
        return proc

    @pytest.mark.asyncio
    async def test_docker_run_includes_security_flags(self, runner: DockerRunner, tmp_path: Path):
        code_dir = tmp_path / "code"
        code_dir.mkdir()
        (code_dir / "prototype.py").write_text("print('hi')")

        run_calls: list[list[str]] = []

        async def fake_exec(*args, **kwargs):
            run_calls.append(list(args))
            return self._make_proc()

        with (
            patch.object(runner, "check_docker", AsyncMock(return_value=True)),
            patch("tui_agents.agents.runner.asyncio.create_subprocess_exec", side_effect=fake_exec),
        ):
            result = await runner.run(code_dir)

        docker_run_calls = [c for c in run_calls if c[:2] == ["docker", "run"]]
        assert docker_run_calls, "docker run was never invoked"
        args = docker_run_calls[0]
        assert "--network=none" in args
        assert "--read-only" in args
        assert "--pids-limit=256" in args
        assert "--security-opt" in args
        assert "no-new-privileges" in args
        assert "--user" in args
        assert "--cidfile" in args

    @pytest.mark.asyncio
    async def test_entrypoint_param_flows_to_dockerfile(
        self, runner: DockerRunner, tmp_path: Path
    ):
        """The entrypoint arg passed to run() must land in the Dockerfile."""
        code_dir = tmp_path / "code"
        code_dir.mkdir()
        (code_dir / "benchmark.py").write_text("print('{}')")
        (code_dir / "prototype.py").write_text("pass")

        written_dockerfiles: list[str] = []
        original_prepare = runner._prepare_context

        def spy_prepare(cd, wd, entrypoint):
            original_prepare(cd, wd, entrypoint)
            written_dockerfiles.append((wd / "Dockerfile").read_text())

        proc = self._make_proc()

        with (
            patch.object(runner, "check_docker", AsyncMock(return_value=True)),
            patch.object(runner, "_prepare_context", side_effect=spy_prepare),
            patch(
                "tui_agents.agents.runner.asyncio.create_subprocess_exec",
                AsyncMock(return_value=proc),
            ),
        ):
            await runner.run(code_dir, entrypoint="benchmark.py")

        assert written_dockerfiles
        assert 'ENTRYPOINT ["python", "benchmark.py"]' in written_dockerfiles[0]


class TestRunResult:
    def test_success_property(self):
        assert RunResult(exit_code=0).success
        assert not RunResult(exit_code=1).success
        assert not RunResult(exit_code=0, timed_out=True).success
