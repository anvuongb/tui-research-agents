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
ENTRYPOINT ["python", "prototype.py"]
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
    ) -> RunResult:
        docker_ok = await self.check_docker()
        if not docker_ok:
            return RunResult(
                stderr="Docker is not installed or not running. Install Docker and try again.",
                exit_code=-1,
            )

        tag = f"tui-runner-{uuid.uuid4().hex[:8]}"
        work_dir = Path(tempfile.mkdtemp(prefix="tui-runner-"))

        try:
            shutil.copy(code_dir / "prototype.py", work_dir / "prototype.py")
            req_src = code_dir / "requirements.txt"
            if req_src.exists():
                shutil.copy(req_src, work_dir / "requirements.txt")
            else:
                (work_dir / "requirements.txt").write_text("")

            dockerfile = work_dir / "Dockerfile"
            dockerfile.write_text(DOCKERFILE_TEMPLATE.format(image=self._image))

            start_time = asyncio.get_event_loop().time()

            if progress:
                await progress("building", "Building Docker image...", 0.0)

            build_proc = await asyncio.create_subprocess_exec(
                "docker", "build", "-t", tag, str(work_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            build_out, _ = await build_proc.communicate()
            if build_proc.returncode != 0:
                return RunResult(
                    stderr=build_out.decode(errors="replace"),
                    exit_code=build_proc.returncode,
                )

            if progress:
                await progress("running", "Running prototype in Docker...", 0.0)

            try:
                run_proc = await asyncio.create_subprocess_exec(
                    "docker", "run", "--rm",
                    f"--memory={self._memory_mb}m",
                    f"--cpus={self._cpu_cores}",
                    "--network=none",
                    "--read-only",
                    "--tmpfs", "/tmp:size=512m",
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
                run_proc.kill() if run_proc else None
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
            try:
                rm_proc = await asyncio.create_subprocess_exec(
                    "docker", "rmi", "-f", tag,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await rm_proc.wait()
            except Exception:
                pass

            try:
                shutil.rmtree(str(work_dir))
            except Exception:
                pass
