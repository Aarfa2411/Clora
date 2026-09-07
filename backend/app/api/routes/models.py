"""
Model Management & Sandbox API Routes for INDUSAI-X.
Supports Ollama local runtime health, active model selection,
capability-based routing, and sandboxed code execution.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.schemas.models import ModelStatusResponse, SelectModelRequest
from backend.app.services.llm_service import llm_service
from backend.models.registry import ModelProfile, default_registry
from backend.models.router import RoutingDecision, default_router
from backend.models.runtime import default_runtime
from backend.sandbox.ast_guard import ASTCheckResult, default_ast_guard
from backend.sandbox.docker_executor import ExecutionResult, default_executor
from backend.sandbox.coding_agent import CodingTaskResult, default_coding_loop

router = APIRouter(tags=["Models & Inference Runtime"])


# ---------------------------------------------------------------------------
# Frontend Compatibility Routes (from origin/main)
# ---------------------------------------------------------------------------

@router.get(
    "/models",
    response_model=ModelStatusResponse,
    summary="Get Local Model Runtime & Available 1B-4B Models",
)
async def get_models():
    """
    Returns Ollama local runtime health, active 1B-4B quantized model,
    and detected available open-weight models without any cloud AI dependency.
    """
    status_data = await llm_service.get_status()
    return status_data


@router.get(
    "/models/active",
    summary="Get Current Active Model Name",
)
def get_active_model():
    """Returns the current model selected for industrial investigation queries."""
    return {
        "active_model": llm_service.active_model,
        "runtime": "ollama",
        "endpoint": llm_service.base_url,
    }


@router.post(
    "/models/select",
    summary="Switch Active Local Model",
)
def select_active_model(req: SelectModelRequest):
    """
    Dynamically select an active 1B-4B model (e.g. qwen2.5:3b, llama3.2:3b, phi3.5).
    """
    if not req.model_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model name must not be empty",
        )
    active = llm_service.set_active_model(req.model_name)
    return {
        "message": f"Active model set to '{active}'",
        "active_model": active,
    }


from backend.sandbox.policy_engine import (
    DeterministicPolicyEngine,
    ExecutionRiskLevel,
    HITLTokenManager,
    PolicyEvaluationResult,
    SecurityPolicy,
    default_hitl_manager,
    default_policy_engine,
)
from backend.sandbox.sandbox_manager import (
    SandboxTier,
    SecBoxExecutionResult,
    TieredSandboxManager,
    default_sandbox_manager,
)

# ---------------------------------------------------------------------------
# Multi-Model Registry & Intelligent Routing Routes
# ---------------------------------------------------------------------------

class RouteRequest(BaseModel):
    query: str
    user_id: str = "operator_01"
    user_role: str = "Operator"


class SandboxExecuteRequest(BaseModel):
    code: str
    input_files: Optional[Dict[str, str]] = None
    user_id: str = "engineer_01"
    user_role: str = "Plant_Engineer"


class CodingTaskRequest(BaseModel):
    task_prompt: str
    input_files: Optional[Dict[str, str]] = None
    user_id: str = "engineer_01"
    user_role: str = "Plant_Engineer"
    approval_token: Optional[str] = None
    approver_id: Optional[str] = None
    max_retries: int = 3
    total_wall_clock_cap_sec: float = 30.0


class RiskEvaluationRequest(BaseModel):
    script_code: str
    input_files: Optional[Dict[str, str]] = None
    user_role: str = "Plant_Engineer"


class RequestApprovalRequest(BaseModel):
    execution_id: str
    script_hash: str
    input_hashes: Dict[str, str] = Field(default_factory=dict)
    policy_id: str = "POL-SECBOX-STD-01"
    approver_id: str = "supervisor_01"
    validity_sec: float = 300.0


@router.get("/models/profiles", response_model=List[ModelProfile])
def list_registered_models():
    """Lists all registered sovereign model profiles with hardware tiers and capabilities."""
    return default_registry.list_all(active_only=False)


@router.get("/models/health")
def check_runtime_health():
    """Returns real-time Ollama daemon connectivity and cached models status."""
    return default_runtime.check_health()


@router.post("/models/route", response_model=RoutingDecision)
def evaluate_model_routing(req: RouteRequest):
    """Evaluates task intent and calculates capability match score for optimal model selection."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query string cannot be empty.")
    return default_router.route_task(
        query=req.query, user_id=req.user_id, user_role=req.user_role
    )


# ---------------------------------------------------------------------------
# CLORA-SecBox Policy-Controlled Execution Endpoints
# ---------------------------------------------------------------------------

@router.get("/sandbox/status")
def get_secbox_status():
    """Returns real-time SecBox execution capabilities, ready tiers, and active security policy."""
    docker_ready = default_sandbox_manager.docker_executor.is_docker_ready()
    active_policy = default_policy_engine.policy
    active_tier = default_sandbox_manager.select_best_available(
        active_policy, ExecutionRiskLevel.LOW_RISK
    )
    return {
        "system": "CLORA-SecBox Sovereign Execution Environment",
        "active_tier": active_tier.value,
        "tiers": {
            "tier_1_hardened_container": {
                "name": "Hardened Container Isolation (Docker/Podman)",
                "ready": docker_ready,
                "flags": ["--network none", "--read-only", "--cap-drop ALL", "--user 10001", "pids=32", "mem=512M"],
            },
            "tier_2_restricted_local": {
                "name": "Restricted Local Execution (OS Resource Containment)",
                "ready": True,
                "framing": "OS resource and process containment (Memory cap, process limit, env allowlist)",
            },
            "tier_3_safe_fallback": {
                "name": "Zero-Execution Safe Fallback (Deterministic Simulation)",
                "ready": True,
                "transparent_mode": "SIMULATION (code_executed=False)",
            },
        },
        "policy": active_policy.model_dump(),
    }


@router.post("/sandbox/evaluate-risk", response_model=PolicyEvaluationResult)
def evaluate_code_risk(req: RiskEvaluationRequest):
    """
    Deterministic rule-based pre-flight risk evaluation.
    Categorizes code into LOW_RISK (auto-execute), ELEVATED_RISK (HITL required), or PROHIBITED.
    """
    return default_policy_engine.evaluate(
        script_code=req.script_code,
        input_files=req.input_files,
        user_role=req.user_role,
    )


@router.post("/sandbox/request-approval")
def request_hitl_approval(req: RequestApprovalRequest):
    """
    Emits a cryptographically bound HMAC-SHA256 approval token for an elevated-risk task.
    Token is strictly bound to (execution_id, script_hash, input_hashes, policy_id, approver_id, expiry).
    """
    return default_hitl_manager.issue_approval_token(
        execution_id=req.execution_id,
        script_hash=req.script_hash,
        input_hashes=req.input_hashes,
        policy_id=req.policy_id,
        approver_id=req.approver_id,
        validity_sec=req.validity_sec,
    )


@router.post("/sandbox/coding-task", response_model=CodingTaskResult)
def execute_secbox_task(req: CodingTaskRequest):
    """
    Executes a policy-controlled autonomous code task with full SecBox protection:
    Policy check -> HITL gate -> AST filter -> Strongest backend tier -> Artifact inspect -> Ed25519 proof.
    """
    return default_coding_loop.run_coding_task(
        task_prompt=req.task_prompt,
        input_files=req.input_files,
        user_id=req.user_id,
        user_role=req.user_role,
        approval_token=req.approval_token,
        approver_id=req.approver_id,
        max_retries=req.max_retries,
        total_wall_clock_cap_sec=req.total_wall_clock_cap_sec,
    )


# Backwards compatibility aliases
@router.post("/models/sandbox/execute")
def execute_sandboxed_code_legacy(req: SandboxExecuteRequest):
    """Legacy direct execution endpoint."""
    exec_res = default_sandbox_manager.execute(
        script_code=req.code,
        input_files=req.input_files,
    )
    return {
        "execution": exec_res.model_dump(),
        "status": exec_res.result_status,
    }


@router.post("/models/sandbox/agent-loop", response_model=CodingTaskResult)
def run_coding_agent_loop_legacy(req: CodingTaskRequest):
    """Legacy alias for /sandbox/coding-task."""
    return execute_secbox_task(req)

