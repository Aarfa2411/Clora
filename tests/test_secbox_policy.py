"""
Unit tests for CLORA-SecBox Deterministic Policy Engine & Cryptographically Bound HITL Tokens.
"""

from backend.sandbox.policy_engine import (
    DeterministicPolicyEngine,
    ExecutionRiskLevel,
    HITLTokenManager,
    SecurityPolicy,
)


class TestSecBoxPolicyEngine:
    def setup_method(self):
        self.policy = SecurityPolicy()
        self.engine = DeterministicPolicyEngine(self.policy)
        self.hitl = HITLTokenManager(signing_secret="test-secret-hitl-key")

    def test_prohibits_network_socket_imports(self):
        for mod in ["socket", "urllib", "requests", "http.client", "aiohttp", "httpx"]:
            code = f"import {mod}\nprint('network test')"
            res = self.engine.evaluate(code)
            assert res.risk_level == ExecutionRiskLevel.PROHIBITED
            assert res.allowed is False
            assert any(mod in v for v in res.violations)

    def test_prohibits_subprocess_and_shell_calls(self):
        code = "import subprocess\nsubprocess.run(['ls', '-la'])"
        res = self.engine.evaluate(code)
        assert res.risk_level == ExecutionRiskLevel.PROHIBITED
        assert any("subprocess" in v for v in res.violations)

    def test_prohibits_forbidden_builtins(self):
        for b in ["eval", "exec", "__import__", "compile"]:
            code = f"{b}('1 + 1')"
            res = self.engine.evaluate(code)
            assert res.risk_level == ExecutionRiskLevel.PROHIBITED
            assert any(b in v for v in res.violations)

    def test_prohibits_path_traversal(self):
        code = "with open('../../etc/shadow', 'r') as f: data = f.read()"
        res = self.engine.evaluate(code)
        assert res.risk_level == ExecutionRiskLevel.PROHIBITED
        assert any("path traversal" in v.lower() for v in res.violations)

    def test_elevates_risk_for_complex_scripts(self):
        # Long script with while loop
        code = (
            "import numpy as np\n"
            "# Multi-step complex process\n"
            "count = 0\n"
            "while count < 1000:\n"
            "    count += 1\n"
            + ("# comment padding line\n" * 65)
        )
        res = self.engine.evaluate(code)
        assert res.risk_level == ExecutionRiskLevel.ELEVATED_RISK
        assert res.requires_approval is True
        assert res.allowed is False

    def test_allows_standard_readonly_math(self):
        code = (
            "import pandas as pd\n"
            "import numpy as np\n"
            "df = pd.read_csv('/workspace/input/telemetry.csv')\n"
            "peak = df['bearing_temp_c'].max()\n"
            "print(f'PEAK: {peak}')\n"
        )
        res = self.engine.evaluate(code)
        assert res.risk_level == ExecutionRiskLevel.LOW_RISK
        assert res.allowed is True
        assert res.requires_approval is False

    def test_hitl_token_cryptographic_binding(self):
        execution_id = "EXE-SECBOX-9001"
        script_hash = "abc123scriptsha256"
        input_hashes = {"telemetry.csv": "inputhash789"}
        policy_id = "POL-SECBOX-STD-01"
        approver_id = "supervisor_singh"

        token_record = self.hitl.issue_approval_token(
            execution_id=execution_id,
            script_hash=script_hash,
            input_hashes=input_hashes,
            policy_id=policy_id,
            approver_id=approver_id,
            validity_sec=300.0,
        )
        token = token_record["token"]

        # 1. Exact match validates successfully
        valid, msg = self.hitl.validate_approval_token(
            token=token,
            execution_id=execution_id,
            script_hash=script_hash,
            input_hashes=input_hashes,
            policy_id=policy_id,
            approver_id=approver_id,
        )
        assert valid is True
        assert msg == "APPROVAL_VALID"

        # 2. Tampered script hash invalidates approval immediately
        tampered_script_hash = "tampered_script_hash_value"
        valid_tampered, msg_tampered = self.hitl.validate_approval_token(
            token=token,
            execution_id=execution_id,
            script_hash=tampered_script_hash,
            input_hashes=input_hashes,
            policy_id=policy_id,
            approver_id=approver_id,
        )
        assert valid_tampered is False
        assert "TOKEN_PAYLOAD_MISMATCH" in msg_tampered

        # 3. Tampered input hashes invalidate approval
        valid_input_tampered, _ = self.hitl.validate_approval_token(
            token=token,
            execution_id=execution_id,
            script_hash=script_hash,
            input_hashes={"telemetry.csv": "modified_content_hash"},
            policy_id=policy_id,
            approver_id=approver_id,
        )
        assert valid_input_tampered is False

    def test_hitl_token_expiry(self):
        execution_id = "EXE-EXPIRE-TEST"
        token_record = self.hitl.issue_approval_token(
            execution_id=execution_id,
            script_hash="h1",
            input_hashes={},
            policy_id="p1",
            approver_id="sup1",
            validity_sec=-1.0,  # Already expired
        )
        valid, msg = self.hitl.validate_approval_token(
            token=token_record["token"],
            execution_id=execution_id,
            script_hash="h1",
            input_hashes={},
            policy_id="p1",
            approver_id="sup1",
        )
        assert valid is False
        assert "APPROVAL_TOKEN_EXPIRED" in msg
