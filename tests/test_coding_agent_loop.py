"""
Unit tests for Coding Agent Closed-Loop Verification.
"""

import os
import tempfile
import pytest
from backend.sandbox.coding_agent import CodingAgentLoop
from security.audit_trail import AuditLogger


class TestCodingAgentLoop:
    def test_successful_coding_execution(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            audit_file = tf.name

        try:
            loop = CodingAgentLoop(audit_file=audit_file)
            prompt = "Calculate the average temperature from data"
            result = loop.run_coding_task(
                task_prompt=prompt,
                user_id="eng_test",
                user_role="Plant_Engineer",
            )

            assert result.success is True
            assert result.status == "VERIFIED_SUCCESS"
            assert result.execution_result is not None
            assert result.execution_result.exit_code == 0
            assert result.total_attempts >= 1
            assert result.audit_logged is True

            # Verify Member 6 audit trail record
            import json
            records = []
            with open(audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line.strip()))
            assert len(records) >= 1
            assert any(r["action"] == "EXECUTE_SANDBOX_CODE" for r in records)

            # Cryptographic chain verification
            valid, corrupt_idx, msg = AuditLogger.verify_audit_trail(audit_file)
            assert valid is True
        finally:
            if os.path.exists(audit_file):
                os.remove(audit_file)

    def test_loop_wall_clock_timeout_budget(self):
        loop = CodingAgentLoop()
        # Set an ultra-tight budget of 0.001 seconds
        result = loop.run_coding_task(
            task_prompt="Run a complex simulation",
            total_wall_clock_cap_sec=0.0001,
        )

        assert result.success is False
        assert result.status == "TIMEOUT_BUDGET_EXCEEDED"
        assert "wall-clock budget" in result.error_summary.lower()
