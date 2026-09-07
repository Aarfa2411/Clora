"""
Inference API routes for CLORA Sovereign Engine.
Endpoints: generate, stream, models, switch, sovereignty status, deliverables.
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.ai.models import UnsupportedModelError, list_models, resolve_model, DEFAULT_MODEL
from app.ai.prompts import list_tasks
from app.ai.inference import InferenceService, UnsafePromptError
from app.ai.registry import registry
from app.ai.sovereignty import SovereigntyEgressPolicy

logger = logging.getLogger("indusai.routes")
router = APIRouter(tags=["inference"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="The user prompt to process")
    model: Optional[str] = Field(None, description="Model tag (uses default if omitted)")
    task: str = Field("general", description="Task type: general, summarize, classify, reason, extract")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=8192)
    images: Optional[List[str]] = Field(None, description="Optional base64 images for visual models")
    check_safety: bool = Field(True, description="Whether to check prompt safety")
    trace_id: Optional[str] = Field(None, description="Trace ID for telemetry and audit chain")


class GenerateResponse(BaseModel):
    model: str
    response: str
    tokens_generated: Optional[int] = None
    latency_ms: Optional[float] = None
    trace_id: Optional[str] = None
    done: bool = True


class SwitchModelRequest(BaseModel):
    model: str = Field(..., description="Target model tag to switch active default")


class DeliverableGenerateRequest(BaseModel):
    investigation_id: Optional[str] = Field(None, description="Investigation ID")
    trace_id: Optional[str] = Field(None, description="Trace ID")
    user_query: Optional[str] = Field(None, description="Query text")
    user_role: Optional[str] = Field("ENGINEER", description="User authorization role")
    format_type: str = Field("all", description="Output format: docx, xlsx, pptx, zip, all")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_service(request: Request) -> InferenceService:
    if hasattr(request.app.state, "inference") and request.app.state.inference is not None:
        return request.app.state.inference
    return InferenceService()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health", summary="Health check")
async def health():
    status = await registry.health_check_all()
    ollama_ok = status.get("providers", {}).get("ollama") == "HEALTHY"
    return {
        "status": "ok" if ollama_ok else "degraded",
        "sovereign_mode": True,
        "ollama": "reachable" if ollama_ok else "unreachable",
        "active_model": registry.active_model,
    }


@router.get("/sovereignty/status", summary="Sovereignty & Egress Policy Status")
async def sovereignty_status():
    return SovereigntyEgressPolicy.get_status()


@router.get("/models", summary="List registered models and capabilities")
async def get_models():
    return {
        "active_model": registry.active_model,
        "models": registry.list_registered_models()
    }


@router.post("/models/switch", summary="Resource-aware model switch with automatic rollback")
async def switch_model(body: SwitchModelRequest):
    try:
        res = await registry.switch_model(body.model)
        if not res["success"]:
            raise HTTPException(status_code=400, detail=f"Model switch failed: {res.get('reason')}")
        return res
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/generate", summary="Full text generation with telemetry", response_model=GenerateResponse)
async def generate(body: GenerateRequest, request: Request):
    service = _get_service(request)
    trace_id = body.trace_id or f"TRC-{int(request.state.get('start_time', 0)*1000)}" if hasattr(request.state, "start_time") else "TRC-00000"
    
    try:
        result = await service.run(
            prompt=body.prompt,
            task=body.task,
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            images=body.images,
            check_safety=body.check_safety,
            trace_id=trace_id,
        )
    except (UnsupportedModelError, UnsafePromptError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Inference failed")
        raise HTTPException(status_code=502, detail=f"Inference error: {exc}")

    return GenerateResponse(
        model=result.get("model", body.model or DEFAULT_MODEL),
        response=result.get("response", ""),
        tokens_generated=result.get("tokens_generated"),
        latency_ms=result.get("latency_ms"),
        trace_id=result.get("trace_id", trace_id),
    )


@router.post("/deliverables/generate", summary="Generate Auditable Evidence Package (DOCX/XLSX/PPTX/ZIP)")
async def generate_deliverables(body: DeliverableGenerateRequest):
    from data_intelligence.deliverable_engine import DeliverableEngine
    from backend.graph.workflow import build_workflow

    workflow = build_workflow()
    trace_id = body.trace_id or f"TRC-{int(logger.name.__hash__())}"
    
    # Run graph workflow to obtain state
    graph_state = await workflow.ainvoke({
        "user_query": body.user_query or "Investigate vibration breach for Pump P-101",
        "user_role": body.user_role or "ENGINEER",
        "trace_id": trace_id,
    })

    engine = DeliverableEngine()
    result = engine.generate_package(
        state=graph_state,
        output_dir="output/deliverables",
        format_type=body.format_type
    )

    return result
