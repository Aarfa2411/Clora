"""
Unit tests for Coding Agent Closed-Loop Verification.
"""

import os
import tempfile

from backend.sandbox.coding_agent import CodingAgentLoop
from security.audit_trail import AuditLogger


class TestCodingAgentLoop:
    def test_successful_coding_execution(self, monkeypatch):
        # Eliminate network and docker poll latency in unit tests
        monkeypatch.setattr("backend.models.runtime.ModelRuntimeManager.is_endpoint_reachable", lambda self, timeout_sec=0.5: False)
        monkeypatch.setattr("backend.sandbox.docker_executor.SandboxExecutor.is_docker_ready", lambda self: False)

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

    def test_clean_code_multi_block_and_docstrings(self):
        loop = CodingAgentLoop()
        # Multi-block output with markdown explanation and python code
        raw = (
            "Here is the code to calculate vibration metrics:\n"
            "```\n"
            "telemetry_data = [1.2, 3.4]\n"
            "```\n\n"
            "```python\n"
            "import numpy as np\n"
            "def calculate_rms(v):\n"
            '    """Calculates RMS with ``` in docstring"""\n'
            "    return float(np.sqrt(np.mean(v**2)))\n"
            "print(calculate_rms(np.array([1.0, 2.0])))\n"
            "```\n\n"
            "Run using python script.py"
        )
        cleaned = loop._clean_code(raw)
        assert "def calculate_rms" in cleaned
        assert "import numpy as np" in cleaned
