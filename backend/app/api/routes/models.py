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
    max_retries: int = 3
    total_wall_clock_cap_sec: float = 30.0


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


@router.post("/models/sandbox/execute", response_model=Dict[str, Any])
def execute_sandboxed_code(req: SandboxExecuteRequest):
    """Executes code directly in the isolated sandbox with advisory AST validation."""
    ast_res = default_ast_guard.check(req.code)
    if not ast_res.valid:
        return {
            "ast_check": ast_res.model_dump(),
            "execution": None,
            "status": "AST_VALIDATION_FAILED",
        }

    exec_res = default_executor.run(req.code, input_files=req.input_files)
    return {
        "ast_check": ast_res.model_dump(),
        "execution": exec_res.model_dump(),
        "status": "SUCCESS" if exec_res.exit_code == 0 else "EXECUTION_FAILED",
    }


@router.post("/models/sandbox/agent-loop", response_model=CodingTaskResult)
def run_coding_agent_loop(req: CodingTaskRequest):
    """Runs closed-loop code generation, AST pre-filtering, execution, and self-correction."""
    return default_coding_loop.run_coding_task(
        task_prompt=req.task_prompt,
        input_files=req.input_files,
        user_id=req.user_id,
        user_role=req.user_role,
        max_retries=req.max_retries,
        total_wall_clock_cap_sec=req.total_wall_clock_cap_sec,
    )
