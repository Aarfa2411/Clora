"""
AgentState definition for CLORA 3-Stage LangGraph workflow.
Tracks execution state, trace IDs, claims, verification scores, sanction proposals, and audit hash chain.
"""

from typing import TypedDict, Any, Dict, List


class AgentState(TypedDict, total=False):
    # Context & User Metadata
    trace_id: str
    user_query: str
    user_id: str
    user_role: str

    # Stage 1: Planning & Tool Authorization
    intent: str
    plan: List[Dict[str, Any]]
    authorized_tools: List[str]
    iteration_count: int

    # Stage 2: Evidence & Telemetry Engine
    retrieved_docs: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]
    retrieved_evidence: List[Dict[str, Any]]
    telemetry_data: List[Dict[str, Any]]
    agent_outputs: Dict[str, Any]

    # Stage 3: Verification, Synthesis & Sanction
    draft_answer: str
    claims: List[Dict[str, Any]]
    verification_results: List[Dict[str, Any]]
    verification_status: str
    verification_score: float
    confidence: float
    guardrail_status: str

    final_answer: str
    sanction_proposal: Dict[str, Any]
    human_approval_required: bool
    human_approved: bool

    # Audit & Manifest Output
    audit_log: List[Dict[str, Any]]
    audit_chain_head: str
    evidence_manifest: Dict[str, Any]
