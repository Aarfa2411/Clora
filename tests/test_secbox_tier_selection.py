"""
Unit tests for CLORA-SecBox Backend-Controlled Tier Selection & Transparent Simulation.
"""

from backend.sandbox.policy_engine import ExecutionRiskLevel, SecurityPolicy
from backend.sandbox.sandbox_manager import SandboxTier, TieredSandboxManager


class TestSecBoxTierSelection:
    def test_selects_tier_1_when_docker_available(self, monkeypatch):
        manager = TieredSandboxManager()
        monkeypatch.setattr(manager.docker_executor, "is_docker_ready", lambda: True)

        policy = SecurityPolicy()
        tier = manager.select_best_available(policy, ExecutionRiskLevel.LOW_RISK)
        assert tier == SandboxTier.HARDENED_CONTAINER

    def test_selects_tier_2_when_docker_absent_and_host_permitted(self, monkeypatch):
        manager = TieredSandboxManager()
        monkeypatch.setattr(manager.docker_executor, "is_docker_ready", lambda: False)

        policy = SecurityPolicy(allow_restricted_host=True)
        tier = manager.select_best_available(policy, ExecutionRiskLevel.LOW_RISK)
        assert tier == SandboxTier.RESTRICTED_LOCAL

    def test_selects_tier_3_when_docker_absent_and_host_prohibited(self, monkeypatch):
        manager = TieredSandboxManager()
        monkeypatch.setattr(manager.docker_executor, "is_docker_ready", lambda: False)

        policy = SecurityPolicy(allow_restricted_host=False)
        tier = manager.select_best_available(policy, ExecutionRiskLevel.LOW_RISK)
        assert tier == SandboxTier.SAFE_FALLBACK

    def test_tier_3_simulation_reports_code_executed_false(self):
        manager = TieredSandboxManager()
        # Force Tier 3 execution
        result = manager.execute(
            script_code="import os\nprint('simulated')",
            forced_tier=SandboxTier.SAFE_FALLBACK,
        )

        assert result.runtime_tier == SandboxTier.SAFE_FALLBACK
        assert result.execution_mode == "SIMULATION"
        assert result.code_executed is False
        assert result.result_status == "SIMULATED"
        assert "SIMULATION MODE - NO CODE EXECUTED" in result.stdout

    def test_tier_2_executes_on_host_with_containment(self):
        manager = TieredSandboxManager()
        # Force Tier 2 execution
        code = "print('SECBOX_HOST_OK')\nx = 10 + 20\nprint(f'RESULT: {x}')"
        result = manager.execute(
            script_code=code,
            forced_tier=SandboxTier.RESTRICTED_LOCAL,
        )

        assert result.runtime_tier == SandboxTier.RESTRICTED_LOCAL
        assert result.execution_mode == "RESTRICTED_HOST"
        assert result.code_executed is True
        assert result.exit_code == 0
        assert "RESULT: 30" in result.stdout
