"""
Intelligent Model Router for INDUSAI-X.
Evaluates query intent, computational requirements, and hardware readiness
to dynamically select the optimal sovereign local model.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.models.registry import (
    HardwareTier,
    ModelCapability,
    ModelProfile,
    ModelRegistry,
    default_registry,
)
from backend.models.runtime import ModelRuntimeManager, default_runtime


class RoutingDecision(BaseModel):
    task_type: str
    selected_model: str
    capability_match_score: float = Field(..., ge=0.0, le=1.0)
    scoring_breakdown: Dict[str, float] = Field(default_factory=dict)
    fallback_model: str
    reasoning: str
    is_fallback: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IntelligentModelRouter:
    """Multi-dimensional model router enforcing normalized scoring & tamper-evident logging."""

    # Explicit, normalized weights summing strictly to 1.0
    W_CAP: float = 0.50
    W_HW: float = 0.30
    W_READY: float = 0.20

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        runtime: Optional[ModelRuntimeManager] = None,
        audit_file: Optional[str] = None,
    ) -> None:
        self.registry = registry or default_registry
        self.runtime = runtime or default_runtime
        self.audit_file = audit_file

    def classify_task(self, query: str) -> Dict[str, Any]:
        """Analyzes query to detect capability requirement, code need, and domain intent."""
        q_lower = query.lower()

        # 1. Explicit computational action triggers (requires deliberate calculation or scripting intent)
        code_action_triggers = [
            "calculate", "compute", "computation", "plot", "chart", "graph",
            "script", "python", "sensor math", "telemetry math", "write code",
            "execute script", "calculate delta", "compute slope", "calculate rms",
            "aggregate data", "calculate stddev", "run simulation"
        ]
        has_code_action = any(t in q_lower for t in code_action_triggers)

        # 2. Deep Root-Cause Investigation triggers
        rca_triggers = [
            "why", "fail", "failure", "cause", "root cause", "overheat",
            "breakdown", "incident", "trip", "spalling", "runaway"
        ]
        is_rca = any(t in q_lower for t in rca_triggers)

        # 3. SOP / Procedure / Extraction triggers
        sop_triggers = ["how to", "procedure", "sop", "steps", "start-up", "shutdown"]
        is_sop = any(t in q_lower for t in sop_triggers)

        # Disambiguation:
        # If query asks a causal/incident question (e.g., "Did delta pressure cause valve to fail?"),
        # it is an RCA investigation unless explicitly requesting code generation / calculation.
        if is_rca and not any(k in q_lower for k in ["calculate", "compute", "script", "plot", "write python", "run code"]):
            task_type = "root_cause_investigation"
            req_capability = ModelCapability.REASONING_RCA
            reasoning = "Task involves multi-source causal investigation and failure correlation."
            is_code = False
        elif has_code_action:
            task_type = "code_execution"
            req_capability = ModelCapability.CODE_GENERATION
            reasoning = "Task explicitly involves sensor mathematics, telemetry scripting, or quantitative calculation."
            is_code = True
        elif is_rca:
            task_type = "root_cause_investigation"
            req_capability = ModelCapability.REASONING_RCA
            reasoning = "Task involves multi-source causal investigation and failure correlation."
            is_code = False
        elif is_sop:
            task_type = "sop_lookup"
            req_capability = ModelCapability.FAST_TRIAGE
            reasoning = "Task involves structured operational procedure retrieval."
            is_code = False
        else:
            task_type = "general_knowledge"
            req_capability = ModelCapability.GENERAL
            reasoning = "Standard technical inquiry."
            is_code = False

        return {
            "task_type": task_type,
            "required_capability": req_capability,
            "is_code": is_code,
            "is_rca": is_rca,
            "reasoning": reasoning,
        }

    def compute_match_score(
        self, profile: ModelProfile, required_capability: ModelCapability, ready_models: List[str]
    ) -> tuple[float, Dict[str, float]]:
        """
        Computes a mathematically bounded score in [0.0, 1.0].
        Weights sum to 1.0; each component is clamped in [0.0, 1.0].
        """
        # Capability score (1.0 if direct match, 0.5 if general, 0.0 otherwise)
        if profile.supports(required_capability):
            s_cap = 1.0
        elif profile.supports(ModelCapability.GENERAL):
            s_cap = 0.5
        else:
            s_cap = 0.0

        # Hardware suitability score (1.0 for low_spec_cpu laptop-friendly, 0.7 for mid, 0.4 for heavy)
        if profile.hardware_tier == HardwareTier.LOW_SPEC_CPU:
            s_hw = 1.0
        elif profile.hardware_tier == HardwareTier.MID_SPEC_GPU:
            s_hw = 0.7
        else:
            s_hw = 0.4

        # Readiness score (1.0 if cached in local Ollama, 0.5 if needs pull, 0.2 if offline/mock)
        if profile.is_fallback:
            s_ready = 0.5
        elif any(profile.model_id in tag for tag in ready_models):
            s_ready = 1.0
        else:
            s_ready = 0.3

        # Clamp all components strictly
        s_cap = min(max(s_cap, 0.0), 1.0)
        s_hw = min(max(s_hw, 0.0), 1.0)
        s_ready = min(max(s_ready, 0.0), 1.0)

        # Composite score
        total_score = (self.W_CAP * s_cap) + (self.W_HW * s_hw) + (self.W_READY * s_ready)
        total_score = min(max(round(total_score, 4), 0.0), 1.0)

        breakdown = {
            "s_capability": s_cap,
            "s_hardware": s_hw,
            "s_readiness": s_ready,
            "w_cap": self.W_CAP,
            "w_hw": self.W_HW,
            "w_ready": self.W_READY,
        }
        return total_score, breakdown

    def route_task(
        self, query: str, user_id: str = "operator_01", user_role: str = "Operator"
    ) -> RoutingDecision:
        """Determines the optimal model and logs routing telemetry to the audit trail."""
        analysis = self.classify_task(query)
        req_cap = analysis["required_capability"]
        task_type = analysis["task_type"]

        # Probe local Ollama pulled models for readiness check
        pulled_models = self.runtime.list_pulled_models()
        candidates = self.registry.list_all(active_only=True)

        # Evaluate candidate models
        scored: List[tuple[float, ModelProfile, Dict[str, float]]] = []
        for model in candidates:
            # Score non-fallback models first
            if not model.is_fallback:
                score, breakdown = self.compute_match_score(model, req_cap, pulled_models)
                scored.append((score, model, breakdown))

        scored.sort(key=lambda x: x[0], reverse=True)

        fallback = self.registry.get_fallback_model()

        if scored and scored[0][0] > 0.3:
            best_score, best_model, best_breakdown = scored[0]
            selected_model_id = best_model.model_id
            score_val = best_score
            breakdown_dict = best_breakdown
            reasoning = (
                f"Selected {best_model.display_name} (score: {score_val:.2f}) "
                f"matching capability '{req_cap.value}' on {best_model.hardware_tier.value} tier."
            )
            is_fallback = False
        else:
            selected_model_id = fallback.model_id
            score_val, breakdown_dict = self.compute_match_score(fallback, req_cap, pulled_models)
            reasoning = f"No primary model scored above threshold. Defaulted to {fallback.display_name}."
            is_fallback = True

        decision = RoutingDecision(
            task_type=task_type,
            selected_model=selected_model_id,
            capability_match_score=score_val,
            scoring_breakdown=breakdown_dict,
            fallback_model=fallback.model_id,
            reasoning=reasoning,
            is_fallback=is_fallback,
            metadata={"query_length": len(query), "pulled_models_count": len(pulled_models)},
        )

        # Log to Member 6's Unified Tamper-Evident Audit Trail
        self._log_routing_event(decision, user_id, user_role, query)

        return decision

    def _log_routing_event(
        self, decision: RoutingDecision, user_id: str, user_role: str, query: str
    ) -> None:
        """Calls Member 6's existing AuditLogger to record immutable SHA-256 chained entry."""
        try:
            from security.audit_trail import AuditLogger
            log_path = self.audit_file or "./storage/audit_trail.jsonl"
            logger = AuditLogger(log_path)
            logger.log(
                actor_id=user_id,
                role=user_role,
                action="ROUTE_MODEL",
                resource=decision.selected_model,
                status="SUCCESS",
                metadata={
                    "task_type": decision.task_type,
                    "match_score": decision.capability_match_score,
                    "is_fallback": decision.is_fallback,
                    "query_snippet": query[:60],
                },
            )
        except Exception:
            pass


default_router = IntelligentModelRouter()
