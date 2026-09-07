"""
CLORA-SecBox Closed-Loop Coding & Policy-Controlled Execution Agent.
Coordinates Deterministic Policy Evaluation, HITL Approval Validation,
AST Pre-Flight Filtering, Tiered Sandbox Execution, Artifact Inspection,
and Cryptographic Attestation with the Shared Sovereign Trust Layer.
SIH Problem Statement 26117 (MRPL)
"""

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.models.router import IntelligentModelRouter, default_router
from backend.models.runtime import ModelRuntimeManager, default_runtime
from backend.sandbox.artifact_inspector import ArtifactInspector, default_artifact_inspector
from backend.sandbox.ast_guard import ASTSecurityGuard, default_ast_guard
from backend.sandbox.policy_engine import (
    DeterministicPolicyEngine,
    ExecutionRiskLevel,
    HITLTokenManager,
    SecurityPolicy,
    default_hitl_manager,
    default_policy_engine,
)
from backend.sandbox.sandbox_manager import (
    SecBoxExecutionResult,
    TieredSandboxManager,
    default_sandbox_manager,
)


from backend.calculation.schemas import (
    CalculationConfidenceLevel,
    CalculationPhase,
    CalculationSourceType,
    CalculationStep,
    StructuredCalculationResult,
)


class CodingTaskResult(BaseModel):
    success: bool
    status: str
    execution_id: str = ""
    final_code: str = ""
    execution_result: Optional[SecBoxExecutionResult] = None
    calculation_result: Optional[StructuredCalculationResult] = None
    runtime_tier: str = "HARDENED_CONTAINER"
    execution_mode: str = "CONTAINER"
    code_executed: bool = True
    risk_level: str = "LOW_RISK"
    total_attempts: int = 1
    total_elapsed_sec: float = 0.0
    model_used: str = ""
    artifacts: List[str] = Field(default_factory=list)
    artifact_hashes: Dict[str, str] = Field(default_factory=dict)
    attestation_proof: Optional[Dict[str, Any]] = None
    hitl_approval_required: bool = False
    approval_token_data: Optional[Dict[str, Any]] = None
    error_summary: Optional[str] = None
    audit_logged: bool = False


class CodingAgentLoop:
    """
    Orchestrates the entire policy-controlled code execution pipeline.
    Reuses existing shared trust layer: EvidenceAttestor, AirGapSentinel, and AuditLogger.
    """

    def __init__(
        self,
        router: Optional[IntelligentModelRouter] = None,
        runtime: Optional[ModelRuntimeManager] = None,
        policy_engine: Optional[DeterministicPolicyEngine] = None,
        hitl_manager: Optional[HITLTokenManager] = None,
        ast_guard: Optional[ASTSecurityGuard] = None,
        sandbox_manager: Optional[TieredSandboxManager] = None,
        artifact_inspector: Optional[ArtifactInspector] = None,
        audit_file: str = "./storage/audit_trail.jsonl",
    ) -> None:
        self.router = router or default_router
        self.runtime = runtime or default_runtime
        self.policy_engine = policy_engine or default_policy_engine
        self.hitl_manager = hitl_manager or default_hitl_manager
        self.ast_guard = ast_guard or default_ast_guard
        self.sandbox_manager = sandbox_manager or default_sandbox_manager
        self.artifact_inspector = artifact_inspector or default_artifact_inspector
        self.audit_file = audit_file

    def run_coding_task(
        self,
        task_prompt: str,
        input_files: Optional[Dict[str, str]] = None,
        user_id: str = "engineer_01",
        user_role: str = "Plant_Engineer",
        approval_token: Optional[str] = None,
        approver_id: Optional[str] = None,
        policy: Optional[SecurityPolicy] = None,
        max_retries: int = 3,
        total_wall_clock_cap_sec: float = 30.0,
    ) -> CodingTaskResult:
        """Executes the closed-loop agent with strict policy gating and cryptographic evidence attestation."""
        loop_start = time.time()
        active_policy = policy or self.policy_engine.policy
        execution_id = f"SECBOX-{int(time.time() * 1000)}"

        # 1. Route task to appropriate model
        routing = self.router.route_task(
            f"Code script: {task_prompt}", user_id=user_id, user_role=user_role
        )
        model_id = routing.selected_model

        current_code = ""
        prev_code_hash: Optional[int] = None
        last_error = ""
        last_exec_res: Optional[SecBoxExecutionResult] = None

        for attempt in range(1, max_retries + 1):
            # Check unified wall-clock budget
            elapsed = time.time() - loop_start
            if elapsed >= total_wall_clock_cap_sec:
                return CodingTaskResult(
                    success=False,
                    status="TIMEOUT_BUDGET_EXCEEDED",
                    execution_id=execution_id,
                    final_code=current_code,
                    execution_result=last_exec_res,
                    total_attempts=attempt - 1,
                    total_elapsed_sec=round(elapsed, 2),
                    model_used=model_id,
                    error_summary=f"Exceeded total wall-clock budget of {total_wall_clock_cap_sec}s.",
                )

            # 2. Generate or Self-Correct Code
            if attempt == 1:
                current_code = self._generate_initial_code(model_id, task_prompt)
            else:
                current_code = self._self_correct_code(model_id, task_prompt, current_code, last_error)

            # 3. Detect duplicate spinning
            code_hash = hash(current_code)
            if code_hash == prev_code_hash:
                elapsed = time.time() - loop_start
                return CodingTaskResult(
                    success=False,
                    status="HALTED_IDENTICAL_REGENERATION",
                    execution_id=execution_id,
                    final_code=current_code,
                    execution_result=last_exec_res,
                    total_attempts=attempt,
                    total_elapsed_sec=round(elapsed, 2),
                    model_used=model_id,
                    error_summary="Model produced identical code without fixing reported error.",
                )
            prev_code_hash = code_hash

            # 4. DETERMINISTIC POLICY ENGINE EVALUATION (Rule matrix, zero LLM bias)
            eval_res = self.policy_engine.evaluate(current_code, input_files=input_files, user_role=user_role)

            if eval_res.risk_level == ExecutionRiskLevel.PROHIBITED:
                elapsed = time.time() - loop_start
                result = CodingTaskResult(
                    success=False,
                    status="PROHIBITED",
                    execution_id=execution_id,
                    final_code=current_code,
                    risk_level=eval_res.risk_level.value,
                    code_executed=False,
                    total_attempts=attempt,
                    total_elapsed_sec=round(elapsed, 2),
                    model_used=model_id,
                    error_summary="; ".join(eval_res.violations),
                )
                self._log_audit_event(result, user_id, user_role, task_prompt, eval_res)
                return result

            if eval_res.risk_level == ExecutionRiskLevel.ELEVATED_RISK:
                # Check if cryptographically bound approval token was provided
                is_approved = False
                if approval_token and approver_id:
                    valid_token, msg = self.hitl_manager.validate_approval_token(
                        token=approval_token,
                        execution_id=execution_id,
                        script_hash=eval_res.script_hash,
                        input_hashes=eval_res.input_hashes,
                        policy_id=active_policy.policy_id,
                        approver_id=approver_id,
                    )
                    is_approved = valid_token

                if not is_approved:
                    # Issue a bound token request and pause execution
                    token_data = self.hitl_manager.issue_approval_token(
                        execution_id=execution_id,
                        script_hash=eval_res.script_hash,
                        input_hashes=eval_res.input_hashes,
                        policy_id=active_policy.policy_id,
                        approver_id=approver_id or "supervisor_pending",
                        validity_sec=active_policy.approval_validity_sec,
                    )
                    elapsed = time.time() - loop_start
                    result = CodingTaskResult(
                        success=False,
                        status="HITL_APPROVAL_REQUIRED",
                        execution_id=execution_id,
                        final_code=current_code,
                        risk_level=eval_res.risk_level.value,
                        code_executed=False,
                        hitl_approval_required=True,
                        approval_token_data=token_data,
                        total_attempts=attempt,
                        total_elapsed_sec=round(elapsed, 2),
                        model_used=model_id,
                        error_summary="Elevated risk detected. Execution halted pending supervisor cryptographic sign-off.",
                    )
                    self._log_audit_event(result, user_id, user_role, task_prompt, eval_res)
                    return result

            # 5. AST PRE-FLIGHT FILTER (Pre-execution attack surface reduction)
            ast_res = self.ast_guard.check(current_code)
            if not ast_res.valid:
                last_error = f"AST Validation Error: {ast_res.error_message}"
                continue

            # 6. TIERED SANDBOX EXECUTION (Backend selects strongest permitted tier)
            exec_res = self.sandbox_manager.execute(
                script_code=current_code,
                input_files=input_files,
                policy=active_policy,
                risk_level=eval_res.risk_level,
            )
            last_exec_res = exec_res

            # 7. ARTIFACT INSPECTION (Quotas, whitelist, magic-bytes, hashes)
            artifact_res = self.artifact_inspector.inspect(exec_res.generated_files)
            if not artifact_res.valid:
                last_error = f"Artifact Policy Violation: {'; '.join(artifact_res.violations)}"
                continue

            # 8. Check execution status
            if exec_res.exit_code == 0:
                elapsed = time.time() - loop_start

                # 9. INTEGRATE WITH SHARED SOVEREIGN TRUST LAYER
                attestation_proof = self._attest_execution_proof(
                    execution_id=execution_id,
                    script_code=current_code,
                    input_hashes=eval_res.input_hashes,
                    artifact_hashes=artifact_res.artifact_hashes,
                    exec_res=exec_res,
                    policy=active_policy,
                )

                calc_result = self._extract_calculation_result(exec_res, execution_id)

                result = CodingTaskResult(
                    success=True,
                    status="VERIFIED_SUCCESS" if exec_res.code_executed else "SIMULATED_SUCCESS",
                    execution_id=execution_id,
                    final_code=current_code,
                    execution_result=exec_res,
                    calculation_result=calc_result,
                    runtime_tier=exec_res.runtime_tier.value,
                    execution_mode=exec_res.execution_mode,
                    code_executed=exec_res.code_executed,
                    risk_level=eval_res.risk_level.value,
                    total_attempts=attempt,
                    total_elapsed_sec=round(elapsed, 2),
                    model_used=model_id,
                    artifacts=artifact_res.approved_files,
                    artifact_hashes=artifact_res.artifact_hashes,
                    attestation_proof=attestation_proof,
                    error_summary=None,
                    audit_logged=True,
                )
                self._log_audit_event(result, user_id, user_role, task_prompt, eval_res)
                return result
            else:
                last_error = f"Runtime Execution Traceback:\n{exec_res.stderr or exec_res.stdout}"

        # If retries exhausted
        elapsed = time.time() - loop_start
        failed_result = CodingTaskResult(
            success=False,
            status="MAX_RETRIES_EXCEEDED",
            execution_id=execution_id,
            final_code=current_code,
            execution_result=last_exec_res,
            total_attempts=max_retries,
            total_elapsed_sec=round(elapsed, 2),
            model_used=model_id,
            error_summary=last_error,
            audit_logged=True,
        )
        self._log_audit_event(failed_result, user_id, user_role, task_prompt, None)
        return failed_result

    def _attest_execution_proof(
        self,
        execution_id: str,
        script_code: str,
        input_hashes: Dict[str, str],
        artifact_hashes: Dict[str, str],
        exec_res: SecBoxExecutionResult,
        policy: SecurityPolicy,
    ) -> Dict[str, Any]:
        """Binds execution evidence and signs it with CLORA's local Ed25519 key."""
        try:
            from security.attestation import get_attestor
            attestor = get_attestor()

            # Canonical execution evidence payload
            canonical_evidence = {
                "execution_id": execution_id,
                "script_hash": hashlib.sha256(script_code.encode("utf-8")).hexdigest(),
                "input_hashes": input_hashes,
                "artifact_hashes": artifact_hashes,
                "exit_code": exec_res.exit_code,
                "runtime_tier": exec_res.runtime_tier.value,
                "execution_mode": exec_res.execution_mode,
                "code_executed": exec_res.code_executed,
                "policy_id": policy.policy_id,
                "timeout_limit": policy.timeout_sec,
                "memory_limit": policy.memory_limit,
                "network_mode": policy.network_mode,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            proof = attestor.sign_report(
                report_id=execution_id,
                content=json.dumps(canonical_evidence, sort_keys=True),
                sources=list(input_hashes.keys()),
                model=f"CLORA-SecBox ({exec_res.runtime_tier.value})",
                extra_metadata={
                    "code_executed": exec_res.code_executed,
                    "runtime_tier": exec_res.runtime_tier.value,
                    "execution_mode": exec_res.execution_mode,
                },
            )
            return proof
        except Exception:
            return {}

    def _extract_calculation_result(
        self, exec_res: SecBoxExecutionResult, execution_id: str
    ) -> Optional[StructuredCalculationResult]:
        """Extracts and validates machine-readable calculation_result.json if produced."""
        import os
        for path in exec_res.generated_files:
            if path.endswith("calculation_result.json") and os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return StructuredCalculationResult(**data)
                except Exception:
                    pass
        return None

    def _generate_initial_code(self, model_id: str, task_prompt: str) -> str:
        prompt = (
            f"Write a self-contained Python script to solve the following industrial engineering task:\n"
            f"{task_prompt}\n\n"
            f"Requirements:\n"
            f"- Use only standard libraries or pandas/numpy/matplotlib.\n"
            f"- If reading data, load from '/workspace/input/telemetry.csv'.\n"
            f"- If generating charts, save to '/workspace/output/chart.png'.\n"
            f"- For calculations, write machine-readable output to '/workspace/output/calculation_result.json' "
            f"containing 'calculation_name', 'final_metric', 'final_value', 'unit', and 'steps'.\n"
            f"- Print key findings and intermediate steps to stdout.\n"
            f"Return ONLY executable Python code."
        )
        res = self.runtime.generate(model_id, prompt=prompt, max_tokens=512)
        return self._clean_code(res.text)

    def _self_correct_code(
        self, model_id: str, task_prompt: str, failed_code: str, error_message: str
    ) -> str:
        prompt = (
            f"The following Python script failed execution:\n"
            f"```python\n{failed_code}\n```\n\n"
            f"Error Details:\n{error_message}\n\n"
            f"Fix the script to address this error for original task: '{task_prompt}'.\n"
            f"Do not use blocked modules or syntax errors. Return ONLY executable Python code."
        )
        res = self.runtime.generate(model_id, prompt=prompt, max_tokens=512)
        return self._clean_code(res.text)

    def _clean_code(self, raw_text: str) -> str:
        text = raw_text.strip()
        blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
        if blocks:
            best_block = max(blocks, key=lambda b: (len(b), "import " in b or "def " in b))
            return best_block.strip()
        if "```python" in text:
            return text.split("```python", 1)[1].split("```", 1)[0].strip()
        if "```" in text:
            return text.split("```", 1)[1].split("```", 1)[0].strip()
        return text

    def _log_audit_event(
        self,
        result: CodingTaskResult,
        user_id: str,
        user_role: str,
        task_prompt: str,
        eval_res: Optional[Any] = None,
    ) -> None:
        """Logs execution outcome and evidence to the shared monotonic SHA-256 audit ledger."""
        try:
            from security.audit_trail import AuditLogger
            logger = AuditLogger(self.audit_file)
            logger.log(
                actor_id=user_id,
                role=user_role,
                action="EXECUTE_SANDBOX_CODE",
                resource=result.execution_id or result.model_used,
                status="SUCCESS" if result.success else result.status,
                metadata={
                    "execution_id": result.execution_id,
                    "status": result.status,
                    "runtime_tier": result.runtime_tier,
                    "execution_mode": result.execution_mode,
                    "code_executed": result.code_executed,
                    "risk_level": result.risk_level,
                    "attempts": result.total_attempts,
                    "elapsed_sec": result.total_elapsed_sec,
                    "prompt_snippet": task_prompt[:60],
                    "artifacts_count": len(result.artifacts),
                },
            )
        except Exception:
            pass


default_coding_loop = CodingAgentLoop()
