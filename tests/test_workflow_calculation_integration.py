"""
Integration test for LangGraph Workflow Calculation Pipeline.
Verifies end-to-end flow:
User calculation query -> Routing -> Gateway -> Evidence Pack -> Cross-Correlate -> Claims Verification -> Synthesis -> Attestation.
"""

import pytest
from backend.graph.workflow import build_workflow


class TestWorkflowCalculationIntegration:
    def test_end_to_end_reynolds_calculation_workflow(self):
        graph = build_workflow()
        initial_state = {
            "user_query": (
                "Calculate the Reynolds number for pipeline L-204 with diameter 0.25m, "
                "velocity 2.4m/s, density 860 kg/m3, and viscosity 0.0032 Pa.s with steps"
            ),
            "user_id": "engineer_01",
            "user_role": "Plant_Engineer",
            "intent": "",
            "plan": [],
            "retrieved_docs": [],
            "evidence": [],
            "agent_outputs": {},
            "draft_answer": "",
            "claims": [],
            "verification_results": [],
            "confidence": 0.0,
            "guardrail_status": "PENDING",
            "final_answer": "",
            "audit_log": [],
        }

        final_state = graph.invoke(initial_state)

        # 1. Verify calculation executed and state populated
        assert "calculation_result" in final_state
        calc_res = final_state["calculation_result"]
        assert calc_res["calculation_name"] == "Reynolds Number"
        assert calc_res["final_value"] == 161250.0
        assert calc_res["confidence"] == "HIGH"
        assert len(calc_res["steps"]) >= 4

        # 2. Verify evidence pack contains auditable calculation evidence
        ev_list = final_state["evidence"]
        assert len(ev_list) >= 1
        assert any("Auditable Local Computation" in ev.get("source_document", "") for ev in ev_list)

        # 3. Verify final answer presents calculation steps to the engineer
        final_answer = final_state["final_answer"]
        assert "Verified Findings" in final_answer
        assert "161250" in final_answer
        assert "Reynolds" in final_answer
        assert "Auditable Local Computation" in final_answer

        # 4. Verify cryptographic evidence attestation
        assert "evidence_attestation" in final_state
        attestation = final_state["evidence_attestation"]
        assert "signature" in attestation
        from security.attestation import EvidenceVerifier as CryptoVerifier
        is_valid, _, _ = CryptoVerifier.verify_proof(attestation)
        assert is_valid is True
