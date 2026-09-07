"""
CLORA-SecBox Tiered Sandbox Manager.
Selects the strongest available execution tier based strictly on backend security policy.
Guarantees transparent reporting: Tier 3 simulation explicitly declares code_executed=False.
SIH Problem Statement 26117 (MRPL)
"""

import time
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from backend.sandbox.docker_executor import SandboxExecutor, default_executor
from backend.sandbox.policy_engine import ExecutionRiskLevel, SecurityPolicy
from backend.sandbox.restricted_host_executor import RestrictedHostExecutor, default_host_executor


class SandboxTier(str, Enum):
    HARDENED_CONTAINER = "HARDENED_CONTAINER"   # Tier 1: Container-grade kernel isolation (Docker/Podman)
    RESTRICTED_LOCAL = "RESTRICTED_LOCAL"       # Tier 2: OS resource and process containment (Job Objects / POSIX)
    SAFE_FALLBACK = "SAFE_FALLBACK"             # Tier 3: Zero-execution deterministic simulation


class SecBoxExecutionResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    generated_files: List[str] = Field(default_factory=list)
    runtime_tier: SandboxTier
    execution_mode: str                         # "CONTAINER" | "RESTRICTED_HOST" | "SIMULATION"
    code_executed: bool                         # False if simulation; True if actually run
    result_status: str                          # "SUCCESS" | "FAILURE" | "SIMULATED"
    warning: Optional[str] = None


class TieredSandboxManager:
    """
    Unified manager for SecBox execution tiers.
    Enforces that security tier selection is strictly backend-controlled.
    Neither the frontend nor the LLM can override or downgrade the execution tier.
    """

    def __init__(
        self,
        docker_executor: Optional[SandboxExecutor] = None,
        host_executor: Optional[RestrictedHostExecutor] = None,
    ) -> None:
        self.docker_executor = docker_executor or default_executor
        self.host_executor = host_executor or default_host_executor

    def select_best_available(
        self,
        policy: SecurityPolicy,
        risk_level: ExecutionRiskLevel,
    ) -> SandboxTier:
        """
        Deterministically selects the strongest permitted tier based on availability and policy:
        1. If Docker daemon and sandbox image are ready -> Tier 1 (HARDENED_CONTAINER)
        2. If Docker is absent and policy allows restricted host -> Tier 2 (RESTRICTED_LOCAL)
        3. Otherwise -> Tier 3 (SAFE_FALLBACK)
        """
        # Tier 1 check
        if self.docker_executor.is_docker_ready():
            return SandboxTier.HARDENED_CONTAINER

        # Tier 2 check
        if policy.allow_restricted_host and risk_level != ExecutionRiskLevel.PROHIBITED:
            return SandboxTier.RESTRICTED_LOCAL

        # Tier 3 fallback
        return SandboxTier.SAFE_FALLBACK

    def execute(
        self,
        script_code: str,
        input_files: Optional[Dict[str, str]] = None,
        policy: Optional[SecurityPolicy] = None,
        risk_level: ExecutionRiskLevel = ExecutionRiskLevel.LOW_RISK,
        forced_tier: Optional[SandboxTier] = None,
    ) -> SecBoxExecutionResult:
        """
        Executes code under the selected tier.
        Guarantees that Tier 3 simulation explicitly reports code_executed=False.
        """
        active_policy = policy or SecurityPolicy()
        t0 = time.time()

        # Backend determines the tier (or uses internal test override)
        tier = forced_tier or self.select_best_available(active_policy, risk_level)

        # ------------------------------------------------------------------
        # Tier 1: Hardened Container Execution
        # ------------------------------------------------------------------
        if tier == SandboxTier.HARDENED_CONTAINER:
            res = self.docker_executor._run_docker(
                host_in_dir=self._stage_inputs_temp(input_files or {}, script_code),
                host_out_dir=self._create_output_temp(),
                script_name="script.py",
            )
            elapsed_ms = (time.time() - t0) * 1000
            return SecBoxExecutionResult(
                exit_code=res.exit_code,
                stdout=res.stdout,
                stderr=res.stderr,
                execution_time_ms=round(elapsed_ms, 2),
                generated_files=res.generated_files,
                runtime_tier=SandboxTier.HARDENED_CONTAINER,
                execution_mode="CONTAINER",
                code_executed=True,
                result_status="SUCCESS" if res.exit_code == 0 else "FAILURE",
                warning=res.warning,
            )

        # ------------------------------------------------------------------
        # Tier 2: Restricted Local Execution (OS Resource Containment)
        # ------------------------------------------------------------------
        elif tier == SandboxTier.RESTRICTED_LOCAL:
            res = self.host_executor.run(
                script_code=script_code,
                input_files=input_files,
                script_name="script.py",
            )
            elapsed_ms = (time.time() - t0) * 1000
            return SecBoxExecutionResult(
                exit_code=res.exit_code,
                stdout=res.stdout,
                stderr=res.stderr,
                execution_time_ms=round(elapsed_ms, 2),
                generated_files=res.generated_files,
                runtime_tier=SandboxTier.RESTRICTED_LOCAL,
                execution_mode="RESTRICTED_HOST",
                code_executed=True,
                result_status="SUCCESS" if res.exit_code == 0 else "FAILURE",
                warning=res.warning,
            )

        # ------------------------------------------------------------------
        # Tier 3: Zero-Execution Safe Simulation (Transparent Reporting)
        # ------------------------------------------------------------------
        else:
            elapsed_ms = (time.time() - t0) * 1000
            simulated_stdout = (
                "[SIMULATION MODE - NO CODE EXECUTED ON HOST]\n"
                "MAX_TEMPERATURE: 104.2 C\n"
                "MAX_VIBRATION_RMS: 9.82 mm/s\n"
                "STATUS: DETERMINISTIC_OFFLINE_VERIFICATION"
            )
            return SecBoxExecutionResult(
                exit_code=0,
                stdout=simulated_stdout,
                stderr="",
                execution_time_ms=round(elapsed_ms, 2),
                generated_files=[],
                runtime_tier=SandboxTier.SAFE_FALLBACK,
                execution_mode="SIMULATION",
                code_executed=False,   # Strictly never claim execution happened
                result_status="SIMULATED",
                warning="[TIER 3 SAFE FALLBACK: Simulated execution. No code was executed on host or container.]",
            )

    def _stage_inputs_temp(self, input_files: Dict[str, str], script_code: str) -> str:
        import tempfile
        d = tempfile.mkdtemp(prefix="secbox_tier1_in_")
        with open(f"{d}/script.py", "w", encoding="utf-8") as f:
            f.write(script_code)
        for fname, content in input_files.items():
            with open(f"{d}/{fname}", "w", encoding="utf-8") as f:
                f.write(content)
        return d

    def _create_output_temp(self) -> str:
        import tempfile
        return tempfile.mkdtemp(prefix="secbox_tier1_out_")


default_sandbox_manager = TieredSandboxManager()
