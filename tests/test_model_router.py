"""
Unit tests for Intelligent Model Router.
"""

import os
import tempfile

from backend.models.registry import ModelCapability
from backend.models.router import IntelligentModelRouter


class TestIntelligentModelRouter:
    def test_routing_code_task(self):
        router = IntelligentModelRouter()
        query = "Calculate peak vibration RMS delta and slope for pump P-101 telemetry"
        decision = router.route_task(query)

        assert decision.task_type == "code_execution"
        assert decision.selected_model == "qwen2.5-coder:1.5b"
        assert 0.0 <= decision.capability_match_score <= 1.0

    def test_routing_rca_investigation(self):
        router = IntelligentModelRouter()
        query = "Why did Pump P-101 overheat and suffer catastrophic failure?"
        decision = router.route_task(query)

        assert decision.task_type == "root_cause_investigation"
        assert decision.selected_model == "qwen2.5:3b"
        assert 0.0 <= decision.capability_match_score <= 1.0

    def test_rca_with_delta_keyword_not_misclassified_as_code(self):
        router = IntelligentModelRouter()
        # Contains 'delta' and 'fail' / 'cause' - must NOT route to code_execution
        query = "Did the delta pressure cause the bypass valve to fail?"
        decision = router.route_task(query)

        assert decision.task_type == "root_cause_investigation"
        assert decision.selected_model == "qwen2.5:3b"

    def test_match_score_strictly_bounded_in_0_1(self):
        router = IntelligentModelRouter()
        # Verify component clamping and normalized weights
        for cap in ModelCapability:
            for m in router.registry.list_all():
                score, breakdown = router.compute_match_score(m, cap, ready_models=[])
                assert 0.0 <= score <= 1.0
                assert 0.0 <= breakdown["s_capability"] <= 1.0
                assert 0.0 <= breakdown["s_hardware"] <= 1.0
                assert 0.0 <= breakdown["s_readiness"] <= 1.0
                assert round(breakdown["w_cap"] + breakdown["w_hw"] + breakdown["w_ready"], 2) == 1.0

    def test_audit_log_recording(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            audit_path = tf.name

        try:
            router = IntelligentModelRouter(audit_file=audit_path)
            decision = router.route_task("Calculate temperature excursion", user_id="eng_test", user_role="Engineer")

            import json
            records = []
            with open(audit_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line.strip()))

            assert len(records) >= 1
            assert records[-1]["action"] == "ROUTE_MODEL"
            assert records[-1]["resource"] == decision.selected_model

            # Verify cryptographic chain integrity
            from security.audit_trail import AuditLogger
            valid, corrupt_idx, msg = AuditLogger.verify_audit_trail(audit_path)
            assert valid is True
        finally:
            if os.path.exists(audit_path):
                os.remove(audit_path)
