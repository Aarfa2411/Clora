"""
Closed-Loop Coding & Verification Agent for INDUSAI-X.
Manages code generation, advisory AST pre-filtering, containerized execution,
autonomous self-correction feedback, loop-level 30s wall-clock caps, and tamper-evident audit logging.
"""

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.models.registry import ModelCapability
from backend.models.router import IntelligentModelRouter, default_router
from backend.models.runtime import ModelRuntimeManager, default_runtime
from backend.sandbox.ast_guard import ASTCheckResult, ASTSecurityGuard, default_ast_guard
from backend.sandbox.docker_executor import (
    ExecutionResult,
    SandboxExecutor,
    default_executor,
)


class CodingTaskResult(BaseModel):
    success: bool
    status: str
    final_code: str
    execution_result: Optional[ExecutionResult] = None
    total_attempts: int = 1
    total_elapsed_sec: float = 0.0
    model_used: str = ""
    error_summary: Optional[str] = None
    audit_logged: bool = False


class CodingAgentLoop:
    """Orchestrates closed-loop code generation, AST pre-filtering, execution, and self-correction."""

    def __init__(
        self,
        router: Optional[IntelligentModelRouter] = None,
        runtime: Optional[ModelRuntimeManager] = None,
        ast_guard: Optional[ASTSecurityGuard] = None,
        executor: Optional[SandboxExecutor] = None,
        audit_file: str = "demo_audit_trail.jsonl",
    ) -> None:
        self.router = router or default_router
        self.runtime = runtime or default_runtime
        self.ast_guard = ast_guard or default_ast_guard
        self.executor = executor or default_executor
        self.audit_file = audit_file

    def run_coding_task(
        self,
        task_prompt: str,
        input_files: Optional[Dict[str, str]] = None,
        user_id: str = "engineer_01",
        user_role: str = "Plant_Engineer",
        max_retries: int = 3,
        total_wall_clock_cap_sec: float = 30.0,
    ) -> CodingTaskResult:
        """Executes the closed-loop agent with strict wall-clock budget and re-validation."""
        loop_start = time.time()

        # 1. Route task to appropriate code-specialist model
        routing = self.router.route_task(
            f"Code script: {task_prompt}", user_id=user_id, user_role=user_role
        )
        model_id = routing.selected_model

        current_code = ""
        prev_code_hash: Optional[int] = None
        last_error = ""
        last_exec_res: Optional[ExecutionResult] = None

        for attempt in range(1, max_retries + 1):
            # Check unified wall-clock budget at every loop entry
            elapsed = time.time() - loop_start
            if elapsed >= total_wall_clock_cap_sec:
                return CodingTaskResult(
                    success=False,
                    status="TIMEOUT_BUDGET_EXCEEDED",
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

            # 3. Detect duplicate generation to prevent spinning
            code_hash = hash(current_code)
            if code_hash == prev_code_hash:
                elapsed = time.time() - loop_start
                return CodingTaskResult(
                    success=False,
                    status="HALTED_IDENTICAL_REGENERATION",
                    final_code=current_code,
                    execution_result=last_exec_res,
                    total_attempts=attempt,
                    total_elapsed_sec=round(elapsed, 2),
                    model_used=model_id,
                    error_summary="Model produced identical code without fixing reported error.",
                )
            prev_code_hash = code_hash

            # 4. Advisory AST Pre-Filter (Every retry MUST re-enter here)
            ast_res = self.ast_guard.check(current_code)
            if not ast_res.valid:
                last_error = f"AST Validation Error: {ast_res.error_message}"
                continue

            # 5. OS-Level Sandbox Execution
            exec_res = self.executor.run(current_code, input_files=input_files)
            last_exec_res = exec_res

            if exec_res.exit_code == 0:
                # Verified success!
                elapsed = time.time() - loop_start
                result = CodingTaskResult(
                    success=True,
                    status="VERIFIED_SUCCESS",
                    final_code=current_code,
                    execution_result=exec_res,
                    total_attempts=attempt,
                    total_elapsed_sec=round(elapsed, 2),
                    model_used=model_id,
                    error_summary=None,
                    audit_logged=True,
                )
                self._log_audit_event(result, user_id, user_role, task_prompt)
                return result
            else:
                last_error = f"Runtime Execution Traceback:\n{exec_res.stderr or exec_res.stdout}"

        # If retries exhausted
        elapsed = time.time() - loop_start
        failed_result = CodingTaskResult(
            success=False,
            status="MAX_RETRIES_EXCEEDED",
            final_code=current_code,
            execution_result=last_exec_res,
            total_attempts=max_retries,
            total_elapsed_sec=round(elapsed, 2),
            model_used=model_id,
            error_summary=last_error,
            audit_logged=True,
        )
        self._log_audit_event(failed_result, user_id, user_role, task_prompt)
        return failed_result

    def _generate_initial_code(self, model_id: str, task_prompt: str) -> str:
        prompt = (
            f"Write a self-contained Python script to solve the following industrial engineering task:\n"
            f"{task_prompt}\n\n"
            f"Requirements:\n"
            f"- Use only standard libraries or pandas/numpy/matplotlib.\n"
            f"- If reading data, load from '/workspace/input/telemetry.csv'.\n"
            f"- If generating charts, save to '/workspace/output/chart.png'.\n"
            f"- Print key findings to stdout.\n"
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
        """Extracts clean python code from markdown fence blocks."""
        text = raw_text.strip()
        if "```python" in text:
            parts = text.split("```python")
            if len(parts) > 1:
                return parts[1].split("```")[0].strip()
        elif "```" in text:
            parts = text.split("```")
            if len(parts) > 1:
                return parts[1].split("```")[0].strip()
        return text

    def _log_audit_event(
        self, result: CodingTaskResult, user_id: str, user_role: str, task_prompt: str
    ) -> None:
        """Logs coding execution result to Member 6's Unified Audit Trail."""
        try:
            from security.audit_trail import AuditLogger
            logger = AuditLogger(self.audit_file)
            logger.log(
                actor_id=user_id,
                role=user_role,
                action="EXECUTE_SANDBOX_CODE",
                resource=result.model_used,
                status="SUCCESS" if result.success else "FAILURE",
                metadata={
                    "status": result.status,
                    "attempts": result.total_attempts,
                    "elapsed_sec": result.total_elapsed_sec,
                    "prompt_snippet": task_prompt[:60],
                    "generated_files": result.execution_result.generated_files if result.execution_result else [],
                },
            )
        except Exception:
            pass


default_coding_loop = CodingAgentLoop()
