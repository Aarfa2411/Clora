"""
OS-Level Containerized Sandbox Executor for INDUSAI-X.
Runs generated scripts under strict kernel-level network isolation,
read-only root with tmpfs cache, resource constraints, and split input/output mounts.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ExecutionResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    generated_files: List[str] = Field(default_factory=list)
    used_container: bool = True
    warning: Optional[str] = None


class SandboxExecutor:
    """Executes analytics scripts in a kernel-isolated container sandbox."""

    def __init__(
        self,
        image_name: str = "indusai-sandbox:latest",
        timeout_sec: float = 15.0,
        memory_limit: str = "512m",
        cpu_limit: str = "1.0",
    ) -> None:
        self.image_name = image_name
        self.timeout_sec = timeout_sec
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit

    def is_docker_ready(self) -> bool:
        """Verifies Docker daemon is running AND the sandbox image is cached locally."""
        try:
            p = subprocess.run(
                ["docker", "image", "inspect", self.image_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=1.5,
            )
            return p.returncode == 0
        except Exception:
            return False

    def run(
        self,
        script_code: str,
        input_files: Optional[Dict[str, str]] = None,
        script_name: str = "script.py",
    ) -> ExecutionResult:
        """
        Runs code in the sandbox.
        `input_files` is a dict of {filename: file_path_or_content}.
        """
        # Create isolated temporary host directories for input and output
        with tempfile.TemporaryDirectory(prefix="indusai_sbx_in_") as host_in_dir, \
             tempfile.TemporaryDirectory(prefix="indusai_sbx_out_") as host_out_dir:

            # 1. Write the target script
            script_path = os.path.join(host_in_dir, script_name)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script_code)

            # 2. Stage any input data files (e.g. telemetry.csv)
            if input_files:
                for fname, content_or_src in input_files.items():
                    dest = os.path.join(host_in_dir, fname)
                    if os.path.exists(content_or_src):
                        shutil.copy2(content_or_src, dest)
                    else:
                        with open(dest, "w", encoding="utf-8") as f:
                            f.write(content_or_src)

            # 3. Choose execution engine: Docker container vs. Subprocess Dev Fallback
            if self.is_docker_ready():
                return self._run_docker(host_in_dir, host_out_dir, script_name)
            else:
                return self._run_subprocess_dev_fallback(host_in_dir, host_out_dir, script_name)

    def _run_docker(
        self, host_in_dir: str, host_out_dir: str, script_name: str
    ) -> ExecutionResult:
        """Executes inside Docker with --network none, --read-only, and tmpfs cache."""
        print(f"[STATUS: Executing in isolated container sandbox ({self.image_name})...]")
        t0 = time.time()

        # Convert to standardized POSIX paths for Docker volume mounting
        in_mount = self._format_docker_mount_path(host_in_dir)
        out_mount = self._format_docker_mount_path(host_out_dir)

        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--pids-limit", "32",
            "--memory", self.memory_limit,
            "--memory-swap", self.memory_limit,
            "--cpus", self.cpu_limit,
            "--tmpfs", "/tmp:size=64m,noexec,nosuid,nodev",
            "--user", "10001:10001",
            "-v", f"{in_mount}:/workspace/input:ro",
            "-v", f"{out_mount}:/workspace/output:rw",
            "-w", "/workspace",
            self.image_name,
            f"/workspace/input/{script_name}",
        ]

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout_sec,
            )
            elapsed_ms = (time.time() - t0) * 1000
            gen_files = self._collect_output_files(host_out_dir)

            return ExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                execution_time_ms=round(elapsed_ms, 2),
                generated_files=gen_files,
                used_container=True,
                warning=None,
            )
        except subprocess.TimeoutExpired:
            elapsed_ms = (time.time() - t0) * 1000
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"Execution timed out after {self.timeout_sec}s budget.",
                execution_time_ms=round(elapsed_ms, 2),
                generated_files=[],
                used_container=True,
                warning="CONTAINER_TIMEOUT",
            )
        except Exception as e:
            elapsed_ms = (time.time() - t0) * 1000
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr=f"Container execution invocation error: {str(e)}",
                execution_time_ms=round(elapsed_ms, 2),
                generated_files=[],
                used_container=True,
                warning=f"CONTAINER_INVOCATION_ERROR: {str(e)}",
            )

    @staticmethod
    def _format_docker_mount_path(host_path: str) -> str:
        """Normalizes host path for Docker volume mounting across Linux, macOS, and Windows."""
        resolved = Path(host_path).resolve()
        posix_str = str(resolved).replace("\\", "/")
        # On Windows, normalize drive letters (e.g. C:/Users/... -> /c/Users/...) for Docker CLI compatibility
        if len(posix_str) >= 2 and posix_str[1] == ":":
            drive = posix_str[0].lower()
            return f"/{drive}{posix_str[2:]}"
        return posix_str

    def _run_subprocess_dev_fallback(
        self, host_in_dir: str, host_out_dir: str, script_name: str
    ) -> ExecutionResult:
        """Dev fallback runner when Docker is not active on the development machine."""
        allow_dev_fallback = os.getenv("ALLOW_INSECURE_DEV_FALLBACK", "true").lower() in ("true", "1", "yes")
        if not allow_dev_fallback:
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr="Execution blocked: Docker container isolation is required in production/strict mode (ALLOW_INSECURE_DEV_FALLBACK=false).",
                execution_time_ms=0.0,
                generated_files=[],
                used_container=False,
                warning="INSECURE_DEV_FALLBACK_PROHIBITED",
            )

        warning_msg = (
            "[DEV FALLBACK: Docker daemon/image absent. Running in restricted host subprocess. "
            "Kernel network isolation is disabled.]"
        )
        print(f"\n{warning_msg}\n")
        t0 = time.time()
        script_full_path = os.path.join(host_in_dir, script_name)

        # Configure environment variables to mock sandbox layout
        env = os.environ.copy()
        env["MPLCONFIGDIR"] = host_out_dir
        env["PYTHONPYCACHEPREFIX"] = host_out_dir
        env["INDUSAI_SANDBOX_INPUT"] = host_in_dir
        env["INDUSAI_SANDBOX_OUTPUT"] = host_out_dir

        try:
            proc = subprocess.run(
                [sys.executable, "-u", script_full_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=host_in_dir,
                env=env,
                text=True,
                timeout=self.timeout_sec,
            )
            elapsed_ms = (time.time() - t0) * 1000
            gen_files = self._collect_output_files(host_out_dir)

            return ExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                execution_time_ms=round(elapsed_ms, 2),
                generated_files=gen_files,
                used_container=False,
                warning=warning_msg,
            )
        except subprocess.TimeoutExpired:
            elapsed_ms = (time.time() - t0) * 1000
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"Execution timed out after {self.timeout_sec}s budget.",
                execution_time_ms=round(elapsed_ms, 2),
                generated_files=[],
                used_container=False,
                warning="SUBPROCESS_TIMEOUT",
            )
        except Exception as e:
            elapsed_ms = (time.time() - t0) * 1000
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr=f"Subprocess runner error: {str(e)}",
                execution_time_ms=round(elapsed_ms, 2),
                generated_files=[],
                used_container=False,
                warning=f"SUBPROCESS_ERROR: {str(e)}",
            )

    def _collect_output_files(self, output_dir: str) -> List[str]:
        """Discovers any artifact files generated into the output directory."""
        found = []
        if os.path.exists(output_dir):
            for root, _, files in os.walk(output_dir):
                for f in files:
                    found.append(os.path.join(root, f))
        return found


default_executor = SandboxExecutor()
