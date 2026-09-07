"""
Unit tests for EvidenceVerifier numerical claim matching and adaptive tolerance.
"""

import pytest
from backend.rag.evidence import Evidence, EvidencePack
from backend.verification.claim_extractor import Claim
from backend.verification.verifier import EvidenceVerifier


class TestNumericalVerifier:
    def setup_method(self):
        self.verifier = EvidenceVerifier()

    def test_numerical_match_within_adaptive_tolerance(self):
        # Target value 161250.0
        ev = Evidence(
            evidence_id="ev_calc_1",
            content="Calculated Reynolds Number. Reynolds Number: 161250.0 dimensionless. Status: VERIFIED_CONSISTENT.",
            source_document="Auditable Local Computation (DETERMINISTIC_FORMULA)",
            chunk_id="CALC-REYNOLDS-01",
            metadata={"final_value": 161250.0, "unit": "dimensionless"},
        )
        pack = EvidencePack(evidence=[ev])

        # Claim matches exact or close float representation
        claim = Claim(
            text="The calculated Reynolds number for the pipeline is 161250.",
            source="draft",
        )
        verified = self.verifier.verify_claim(claim, pack)
        assert verified.status == "SUPPORTED"
        assert verified.confidence >= 0.85
        assert "CALC-REYNOLDS-01" in verified.evidence_ids

    def test_numerical_mismatch_fails_verification(self):
        ev = Evidence(
            evidence_id="ev_calc_1",
            content="Calculated Reynolds Number. Reynolds Number: 161250.0 dimensionless.",
            source_document="Auditable Local Computation",
            chunk_id="CALC-REYNOLDS-01",
            metadata={"final_value": 161250.0},
        )
        pack = EvidencePack(evidence=[ev])

        # Hallucinated or erroneous number
        claim = Claim(
            text="The calculated Reynolds number for the pipeline is 42000.",
            source="draft",
        )
        verified = self.verifier.verify_claim(claim, pack)
        # Should NOT be supported because 42000 is way outside tolerance of 161250
        assert verified.status != "SUPPORTED"
