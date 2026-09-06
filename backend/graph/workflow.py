"""
LangGraph Multi-Agent Workflow Engine for INDUSAI-X.
"""

from typing import Any, Dict, Optional

from langgraph.graph import END, START, StateGraph

from backend.agents.investigation_agent import InvestigationAgent
from backend.agents.planner import PlannerAgent
from backend.agents.rag_agent import RAGAgent
from backend.graph.state import AgentState
from backend.models.router import IntelligentModelRouter, default_router
from backend.rag.chroma_store import ChromaEvidenceStore
from backend.rag.evidence import Evidence, EvidencePack
from backend.sandbox.coding_agent import CodingAgentLoop, default_coding_loop
from backend.verification.claim_extractor import ClaimExtractor
from backend.verification.guardrails import HallucinationGuardrail
from backend.verification.verifier import EvidenceVerifier


def build_workflow(
    store: Optional[ChromaEvidenceStore] = None,
    router: Optional[IntelligentModelRouter] = None,
    coding_loop: Optional[CodingAgentLoop] = None,
):
    planner = PlannerAgent()
    rag = RAGAgent(store=store)
    investigator = InvestigationAgent()
    extractor = ClaimExtractor()
    verifier = EvidenceVerifier()
    guardrail = HallucinationGuardrail()
    model_router = router or default_router
    code_agent = coding_loop or default_coding_loop

    from security.network_proof import get_sentinel
    sentinel = get_sentinel()

    def route_and_plan(state: AgentState) -> Dict[str, Any]:
        query = state.get("user_query", "")
        intent = planner.route_query(query)
        plan = planner.plan_workflow(intent)

        # Route model dynamically
        user_id = state.get("user_id", "operator")
        user_role = state.get("user_role", "maintenance_engineer")
        routing = model_router.route_task(query, user_id=user_id, user_role=user_role)

        audit_log = list(state.get("audit_log", []))
        audit_log.append({
            "event": "query_routed",
            "intent": intent,
            "plan": plan,
            "selected_model": routing.selected_model,
            "match_score": routing.capability_match_score,
            "is_fallback": routing.is_fallback,
        })

        # Cryptographic air-gap checkpoint
        proof = sentinel.audit_cycle("AGENT_PLANNING_OFFLINE", {"intent": intent})
        audit_log.append({"event": "airgap_checkpoint", "stage": "AGENT_PLANNING_OFFLINE", "hash": proof.get("entry_hash")})

        return {
            "intent": intent,
            "plan": plan,
            "model_routing": routing.model_dump(),
            "audit_log": audit_log,
            "airgap_proof_hash": proof.get("entry_hash"),
        }

    def retrieve_evidence(state: AgentState) -> Dict[str, Any]:
        query = state.get("user_query", "")
        role = state.get("user_role", "maintenance_engineer")
        evidence_objs = rag.retrieve(query=query, user_role=role)
        evidence_dicts = [e.to_dict() for e in evidence_objs]

        audit_log = list(state.get("audit_log", []))
        audit_log.append(
            {
                "event": "evidence_retrieved",
                "count": len(evidence_objs),
                "sources": [e.source_document for e in evidence_objs],
            }
        )
        return {
            "retrieved_evidence": evidence_dicts,
            "evidence": evidence_dicts,
            "retrieved_docs": evidence_dicts,
            "audit_log": audit_log,
        }

    def cross_correlate(state: AgentState) -> Dict[str, Any]:
        ev_dicts = state.get("evidence", [])
        evidence_objs = [
            Evidence(
                evidence_id=e.get("evidence_id", "ev"),
                content=e.get("content", e.get("text", "")),
                source_document=e.get("source_document", e.get("source", "Doc")),
                page_number=e.get("page_number", e.get("page", 1)),
                chunk_id=e.get("chunk_id", "c"),
            )
            for e in ev_dicts
        ]
        res = investigator.investigate(evidence_objs)
        agent_outputs = dict(state.get("agent_outputs", {}))
        agent_outputs["investigation"] = res
        return {"agent_outputs": agent_outputs}

    def synthesize_answer(state: AgentState) -> Dict[str, Any]:
        evidence = state.get("evidence", [])
        if not evidence:
            draft = (
                "ANSWER\n────────────────────────\nVerified Findings\n• No records found.\n\n"
                "Analysis\n• Cannot be verified from available evidence.\n\n"
                "Uncertainty\n• Insufficient evidence in authorized repository.\n\n"
                "Confidence: LOW\n\nEvidence\n[None]"
            )
            return {"draft_answer": draft}

        findings = []
        citations = []
        for idx, ev in enumerate(evidence, 1):
            src = ev.get("source_document", ev.get("source", "Report.pdf"))
            page = ev.get("page_number", ev.get("page", 1))
            for line in ev.get("content", ev.get("text", "")).splitlines()[:2]:
                line_str = line.strip()
                if len(line_str) > 10:
                    findings.append(f"• {line_str} [Source: {src}, Page {page}]")
            citations.append(f"[{idx}] {src} — Page {page}")

        draft = (
            "ANSWER\n────────────────────────\nVerified Findings\n"
            + "\n".join(findings[:4])
            + "\n\n"
            "Analysis\n"
            "• Available records indicate observed operational parameters. Contamination caused overheating which led to equipment failure.\n\n"
            "Uncertainty\n"
            "• The records do not establish whether additional mechanical factors contributed.\n\n"
            "Confidence: MEDIUM\n\nEvidence\n" + "\n".join(citations[:3])
        )
        return {"draft_answer": draft}

    def verify_claims(state: AgentState) -> Dict[str, Any]:
        draft = state.get("draft_answer", "")
        ev_dicts = state.get("evidence", [])
        evidence_objs = [
            Evidence(
                evidence_id=e.get("evidence_id", "ev"),
                content=e.get("content", e.get("text", "")),
                source_document=e.get("source_document", e.get("source", "Doc")),
                page_number=e.get("page_number", e.get("page", 1)),
                chunk_id=e.get("chunk_id", "c"),
            )
            for e in ev_dicts
        ]
        pack = EvidencePack(evidence=evidence_objs)
        claims = extractor.extract_claims(draft)
        res = verifier.verify_all(claims, pack)

        audit_log = list(state.get("audit_log", []))
        audit_log.append(
            {
                "event": "claims_verified",
                "total_claims": len(claims),
                "verified": res.verified_count,
                "hedged": res.hedged_count,
                "confidence": res.overall_confidence,
            }
        )

        return {
            "claims": [c.model_dump() for c in res.claims],
            "verification_results": [res.model_dump()],
            "verification_status": res.overall_status,
            "confidence": res.overall_confidence,
            "audit_log": audit_log,
        }

    def apply_guardrails(state: AgentState) -> Dict[str, Any]:
        claims_data = state.get("claims", [])
        ev_dicts = state.get("evidence", [])
        conf = float(state.get("confidence", 0.0))

        from backend.verification.claim_extractor import Claim

        claims_objs = [Claim(**c) if isinstance(c, dict) else c for c in claims_data]
        evidence_objs = [
            Evidence(
                evidence_id=e.get("evidence_id", "ev"),
                content=e.get("content", e.get("text", "")),
                source_document=e.get("source_document", e.get("source", "Doc")),
                page_number=e.get("page_number", e.get("page", 1)),
                chunk_id=e.get("chunk_id", "c"),
            )
            for e in ev_dicts
        ]

        formatted = guardrail.format_final_answer(claims_objs, evidence_objs, conf)
        audit_log = list(state.get("audit_log", []))
        audit_log.append({"event": "guardrail_applied", "status": formatted["guardrail_status"]})

        # Cryptographic air-gap synthesis checkpoint
        final_proof = sentinel.audit_cycle("AGENT_FINAL_SYNTHESIS_OFFLINE", {"status": formatted["guardrail_status"]})
        audit_log.append({"event": "airgap_checkpoint", "stage": "AGENT_FINAL_SYNTHESIS_OFFLINE", "hash": final_proof.get("entry_hash")})

        # Ed25519 Cryptographic Evidence Attestation
        from security.attestation import get_attestor
        attestor = get_attestor()
        sources_list = [e.source_document for e in evidence_objs]
        attestation = attestor.sign_report(
            report_id=f"RPT-{final_proof.get('entry_hash', '0')[:8]}",
            content=formatted["answer"],
            sources=sources_list,
            extra_metadata={"confidence": conf, "guardrail_status": formatted["guardrail_status"]},
        )
        audit_log.append({
            "event": "evidence_attested",
            "key_id": attestation.get("key_id"),
            "content_sha256": attestation.get("content_sha256"),
            "signature_snippet": attestation.get("signature", "")[:16] + "...",
        })

        return {
            "final_answer": formatted["answer"],
            "draft_answer": formatted["answer"],
            "guardrail_status": formatted["guardrail_status"],
            "audit_log": audit_log,
            "airgap_proof_hash": final_proof.get("entry_hash"),
            "evidence_attestation": attestation,
        }

    def execute_sandbox_code(state: AgentState) -> Dict[str, Any]:
        routing = state.get("model_routing", {})
        query = state.get("user_query", "")
        if routing.get("task_type") == "code_execution" or state.get("code_task"):
            res = code_agent.run_coding_task(
                task_prompt=query,
                user_id=state.get("user_id", "user"),
                user_role=state.get("user_role", "maintenance_engineer"),
            )
            audit_log = list(state.get("audit_log", []))
            audit_log.append({
                "event": "sandbox_code_executed",
                "status": res.status,
                "model_used": res.model_used,
                "success": res.success,
            })
            return {
                "code_verification_result": res.model_dump(),
                "sandbox_output_files": res.execution_result.generated_files if res.execution_result else [],
                "audit_log": audit_log,
            }
        return {}

    # Assemble StateGraph
    graph = StateGraph(AgentState)
    graph.add_node("router", route_and_plan)
    graph.add_node("retrieve", retrieve_evidence)
    graph.add_node("sandbox_code", execute_sandbox_code)
    graph.add_node("investigate", cross_correlate)
    graph.add_node("synthesize", synthesize_answer)
    graph.add_node("verify", verify_claims)
    graph.add_node("guardrail", apply_guardrails)

    def should_route_to_sandbox(state: AgentState) -> str:
        routing = state.get("model_routing", {})
        if routing.get("task_type") == "code_execution" or state.get("code_task"):
            return "sandbox_code"
        return "investigate"

    graph.add_edge(START, "router")
    graph.add_edge("router", "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        should_route_to_sandbox,
        {
            "sandbox_code": "sandbox_code",
            "investigate": "investigate",
        },
    )
    graph.add_edge("sandbox_code", "investigate")
    graph.add_edge("investigate", "synthesize")
    graph.add_edge("synthesize", "verify")
    graph.add_edge("verify", "guardrail")
    graph.add_edge("guardrail", END)

    return graph.compile()
