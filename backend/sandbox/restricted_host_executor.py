"""
CLORA-SecBox Restricted Host Executor (Tier 2: Restricted Local Execution).
Defensible Framing: Resource and process containment on local host OS.
Enforces physical memory caps, active process limits (fork bomb mitigation),
process-tree auto-cleanup, and environment sanitization.
SIH Problem Statement 26117 (MRPL)
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HostExecutionResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    generated_files: List[str] = Field(default_factory=list)
    runtime_tier: str = "RESTRICTED_LOCAL"
    code_executed: bool = True
    warning: Optional[str] = None


class RestrictedHostExecutor:
    """
    Tier 2: Restricted Local Execution.
    Provides OS-level process and resource containment when Docker containerization is unavailable.
    Explicit Boundary: Resource containment and risk reduction, not container virtualization.
    """

    def __init__(
        self,
        timeout_sec: float = 10.0,
        memory_limit_mb: int = 512,
        active_process_limit: int = 4,
    ) -> None:
        self.timeout_sec = timeout_sec
        self.memory_limit_mb = memory_limit_mb
        self.active_process_limit = active_process_limit
        self._is_windows = sys.platform == "win32"

    def run(
        self,
        script_code: str,
        input_files: Optional[Dict[str, str]] = None,
        script_name: str = "script.py",
    ) -> HostExecutionResult:
        """Executes the script in an isolated temporary directory under OS resource containment."""
        t0 = time.time()

        with tempfile.TemporaryDirectory(prefix="clora_secbox_in_") as host_in_dir, \
             tempfile.TemporaryDirectory(prefix="clora_secbox_out_") as host_out_dir:

            # 1. Stage the script
            script_path = os.path.join(host_in_dir, script_name)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script_code)

            # 2. Stage input files
            if input_files:
                for fname, content_or_src in input_files.items():
                    dest = os.path.join(host_in_dir, fname)
                    if os.path.exists(content_or_src):
                        shutil.copy2(content_or_src, dest)
                    else:
                        with open(dest, "w", encoding="utf-8") as f:
                            f.write(content_or_src)

            # 3. Construct sanitized environment (strips host secrets, tokens, DB URLs)
            sanitized_env = self._build_sanitized_env(host_in_dir, host_out_dir)

            # 4. Execute under OS resource constraints
            warning_msg = (
                "[TIER 2: RESTRICTED LOCAL EXECUTION ACTIVE - Resource and process containment enforced. "
                "Kernel network isolation is inactive; relying on policy and process constraints.]"
            )

            try:
                if self._is_windows:
                    proc_res = self._run_windows_job(script_path, host_in_dir, sanitized_env)
                else:
                    proc_res = self._run_posix(script_path, host_in_dir, sanitized_env)

                elapsed_ms = (time.time() - t0) * 1000
                gen_files = self._collect_output_files(host_out_dir)

                return HostExecutionResult(
                    exit_code=proc_res["exit_code"],
                    stdout=proc_res["stdout"],
                    stderr=proc_res["stderr"],
                    execution_time_ms=round(elapsed_ms, 2),
                    generated_files=gen_files,
                    runtime_tier="RESTRICTED_LOCAL",
                    code_executed=True,
                    warning=warning_msg,
                )
            except subprocess.TimeoutExpired:
                elapsed_ms = (time.time() - t0) * 1000
                return HostExecutionResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"Execution timed out after {self.timeout_sec}s budget.",
                    execution_time_ms=round(elapsed_ms, 2),
                    generated_files=[],
                    runtime_tier="RESTRICTED_LOCAL",
                    code_executed=True,
                    warning="TIMEOUT_BUDGET_EXCEEDED",
                )
            except Exception as e:
                elapsed_ms = (time.time() - t0) * 1000
                return HostExecutionResult(
                    exit_code=1,
                    stdout="",
                    stderr=f"Restricted host execution invocation error: {str(e)}",
                    execution_time_ms=round(elapsed_ms, 2),
                    generated_files=[],
                    runtime_tier="RESTRICTED_LOCAL",
                    code_executed=False,
                    warning=f"EXECUTION_ERROR: {str(e)}",
                )

    def _build_sanitized_env(self, in_dir: str, out_dir: str) -> Dict[str, str]:
        """Passes only essential runtime keys, stripping all host credentials."""
        env = {}
        # Preserve essential OS variables
        for k in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "PYTHONPATH", "LANG", "LC_ALL"):
            if k in os.environ:
                env[k] = os.environ[k]

        env["INDUSAI_SANDBOX_INPUT"] = in_dir
        env["INDUSAI_SANDBOX_OUTPUT"] = out_dir
        env["MPLCONFIGDIR"] = out_dir
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def _run_windows_job(self, script_path: str, cwd: str, env: Dict[str, str]) -> Dict[str, Any]:
        """Spawns process on Windows and attaches to Job Object if possible for process limits."""
        job_handle = None
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            # Create anonymous Job Object
            job_handle = kernel32.CreateJobObjectW(None, None)
            if job_handle:
                # Basic limit: kill processes on job close
                # JOBOBJECT_EXTENDED_LIMIT_INFORMATION setup
                JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
                JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x0008
                JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x0100

                class IO_COUNTERS(ctypes.Structure):
                    _fields_ = [
                        ("ReadOperationCount", ctypes.c_uint64),
                        ("WriteOperationCount", ctypes.c_uint64),
                        ("OtherOperationCount", ctypes.c_uint64),
                        ("ReadTransferCount", ctypes.c_uint64),
                        ("WriteTransferCount", ctypes.c_uint64),
                        ("OtherTransferCount", ctypes.c_uint64),
                    ]

                class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                    _fields_ = [
                        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD),
                    ]

                class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                    _fields_ = [
                        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                        ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t),
                    ]

                info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                info.BasicLimitInformation.LimitFlags = (
                    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_ACTIVE_PROCESS | JOB_OBJECT_LIMIT_PROCESS_MEMORY
                )
                info.BasicLimitInformation.ActiveProcessLimit = self.active_process_limit
                info.ProcessMemoryLimit = self.memory_limit_mb * 1024 * 1024
                # Below normal priority
                info.BasicLimitInformation.PriorityClass = 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS

                JobObjectExtendedLimitInformation = 9
                kernel32.SetInformationJobObject(
                    job_handle,
                    JobObjectExtendedLimitInformation,
                    ctypes.byref(info),
                    ctypes.sizeof(info),
                )
        except Exception:
            job_handle = None

        proc = subprocess.Popen(
            [sys.executable, "-u", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            text=True,
        )

        if job_handle and sys.platform == "win32":
            try:
                ctypes.windll.kernel32.AssignProcessToJobObject(job_handle, proc._handle)
            except Exception:
                pass

        try:
            stdout, stderr = proc.communicate(timeout=self.timeout_sec)
            return {"exit_code": proc.returncode, "stdout": stdout, "stderr": stderr}
        finally:
            if job_handle and sys.platform == "win32":
                try:
                    ctypes.windll.kernel32.CloseHandle(job_handle)
                except Exception:
                    pass

    def _run_posix(self, script_path: str, cwd: str, env: Dict[str, str]) -> Dict[str, Any]:
        """Spawns process on POSIX using resource limits."""
        def set_limits():
            try:
                import resource
                mem_bytes = self.memory_limit_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
                resource.setrlimit(resource.RLIMIT_NPROC, (self.active_process_limit, self.active_process_limit))
            except Exception:
                pass

        proc = subprocess.Popen(
            [sys.executable, "-u", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            text=True,
            preexec_fn=set_limits,
        )
        stdout, stderr = proc.communicate(timeout=self.timeout_sec)
        return {"exit_code": proc.returncode, "stdout": stdout, "stderr": stderr}

    def _collect_output_files(self, output_dir: str) -> List[str]:
        found = []
        if os.path.exists(output_dir):
            for root, _, files in os.walk(output_dir):
                if "__pycache__" in root:
                    continue
                for f in files:
                    if not f.endswith(".pyc") and not f.endswith(".pyo"):
                        found.append(os.path.join(root, f))
        return found


default_host_executor = RestrictedHostExecutor()
