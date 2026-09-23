from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from tui_agents.utils.config import Config
from tui_agents.utils.logging import get_logger

_log = get_logger(__name__)

DOCKERFILE_TEMPLATE = """FROM {image}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 2>&1
COPY . .
ENTRYPOINT ["python", "{entrypoint}"]
"""


class RunResult:
    def __init__(
        self,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = -1,
        elapsed_seconds: float = 0.0,
        timed_out: bool = False,
    ):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.elapsed_seconds = elapsed_seconds
        self.timed_out = timed_out

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class DockerRunner:
    def __init__(self, config: Config):
        self._timeout = config.get("runner", "timeout", default=300)
        self._memory_mb = config.get("runner", "memory_mb", default=4096)
        self._cpu_cores = config.get("runner", "cpu_cores", default=2)
        self._image = config.get("runner", "image", default="python:3.11-slim")

    async def check_docker(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        except FileNotFoundError:
            return False

    async def run(
        self,
        code_dir: Path,
        progress: Any = None,
        entrypoint: str = "prototype.py",
    ) -> RunResult:
        docker_ok = await self.check_docker()
        if not docker_ok:
            return RunResult(
                stderr="Docker is not installed or not running. Install Docker and try again.",
                exit_code=-1,
            )

        tag = f"tui-runner-{uuid.uuid4().hex[:8]}"
        work_dir = Path(tempfile.mkdtemp(prefix="tui-runner-"))
        cid_file = work_dir / "container.cid"

        try:
            self._prepare_context(code_dir, work_dir, entrypoint)

            start_time = asyncio.get_event_loop().time()

            if progress:
                await progress("building", "Building Docker image...", 0.0)

            try:
                build_out, build_rc = await asyncio.wait_for(
                    self._build(tag, work_dir),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                _log.warning(f"Docker build timed out after {self._timeout}s for {tag}")
                return RunResult(
                    stderr=f"Docker build timed out after {self._timeout}s.",
                    exit_code=-1,
                    elapsed_seconds=asyncio.get_event_loop().time() - start_time,
                    timed_out=True,
                )

            if build_rc != 0:
                return RunResult(
                    stderr=build_out.decode(errors="replace") if build_out else "",
                    exit_code=build_rc,
                    elapsed_seconds=asyncio.get_event_loop().time() - start_time,
                )

            if progress:
                await progress("running", f"Running {entrypoint} in Docker...", 0.0)

            try:
                run_proc = await asyncio.create_subprocess_exec(
                    "docker", "run", "--rm",
                    f"--memory={self._memory_mb}m",
                    f"--cpus={self._cpu_cores}",
                    "--network=none",
                    "--read-only",
                    "--tmpfs", "/tmp:size=512m",
                    "--pids-limit=256",
                    "--security-opt", "no-new-privileges",
                    "--user", "65534:65534",
                    "--cidfile", str(cid_file),
                    tag,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout_lines: list[str] = []
                stderr_lines: list[str] = []

                async def read_stream(stream, lines):
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        decoded = line.decode(errors="replace").rstrip()
                        lines.append(decoded)
                        if progress:
                            await progress("running_output", decoded, 0.0)

                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(run_proc.stdout, stdout_lines),
                        read_stream(run_proc.stderr, stderr_lines),
                    ),
                    timeout=self._timeout,
                )
                await run_proc.wait()

            except asyncio.TimeoutError:
                await self._stop_container(cid_file)
                if run_proc:
                    try:
                        run_proc.kill()
                    except ProcessLookupError:
                        pass
                return RunResult(
                    stdout="\n".join(stdout_lines) if stdout_lines else "",
                    stderr="\n".join(stderr_lines) if stderr_lines else "",
                    elapsed_seconds=asyncio.get_event_loop().time() - start_time,
                    timed_out=True,
                )

            elapsed = asyncio.get_event_loop().time() - start_time
            return RunResult(
                stdout="\n".join(stdout_lines),
                stderr="\n".join(stderr_lines),
                exit_code=run_proc.returncode,
                elapsed_seconds=elapsed,
            )

        finally:
            await self._cleanup_image(tag)
            try:
                shutil.rmtree(str(work_dir), ignore_errors=True)
            except Exception as e:
                _log.warning(f"Failed to remove work dir {work_dir}: {e}")

    def _prepare_context(self, code_dir: Path, work_dir: Path, entrypoint: str) -> None:
        """Copy source files and write the Dockerfile into work_dir."""
        for py_file in sorted(code_dir.glob("*.py")):
            shutil.copy(py_file, work_dir / py_file.name)

        req_src = code_dir / "requirements.txt"
        if req_src.exists():
            shutil.copy(req_src, work_dir / "requirements.txt")
        else:
            (work_dir / "requirements.txt").write_text("")

        dockerfile = work_dir / "Dockerfile"
        dockerfile.write_text(
            DOCKERFILE_TEMPLATE.format(image=self._image, entrypoint=entrypoint)
        )

    async def _build(self, tag: str, work_dir: Path) -> tuple[bytes | None, int]:
        proc = await asyncio.create_subprocess_exec(
            "docker", "build", "-t", tag, str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        if proc.returncode != 0:
            return out, proc.returncode
        return out, 0

    async def _stop_container(self, cid_file: Path) -> None:
        try:
            if cid_file.exists():
                cid = cid_file.read_text().strip()
                if cid:
                    proc = await asyncio.create_subprocess_exec(
                        "docker", "stop", "-t", "5", cid,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await proc.wait()
                    proc = await asyncio.create_subprocess_exec(
                        "docker", "rm", "-f", cid,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await proc.wait()
        except Exception as e:
            _log.warning(f"Failed to stop container from {cid_file}: {e}")

    async def _cleanup_image(self, tag: str) -> None:
        try:
            rm_proc = await asyncio.create_subprocess_exec(
                "docker", "rmi", "-f", tag,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await rm_proc.wait()
        except Exception as e:
            _log.warning(f"Failed to remove image {tag}: {e}")
