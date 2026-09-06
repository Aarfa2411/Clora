"""
Unit tests for Model Registry and Runtime Manager.
"""

import pytest
from backend.models.registry import (
    HardwareTier,
    ModelCapability,
    ModelProfile,
    ModelRegistry,
)
from backend.models.runtime import ModelRuntimeManager


class TestModelRegistry:
    def test_default_registry_contains_1b_4b_tier(self):
        reg = ModelRegistry()
        models = reg.list_all(active_only=True)
        model_ids = [m.model_id for m in models]

        assert "qwen2.5-coder:1.5b" in model_ids
        assert "qwen2.5:3b" in model_ids
        assert "llama3.2:1b" in model_ids
        assert "deterministic-airgap-mock" in model_ids

    def test_list_by_capability(self):
        reg = ModelRegistry()
        code_models = reg.list_by_capability(ModelCapability.CODE_GENERATION, include_fallback=False)
        assert len(code_models) >= 1
        assert any(m.model_id == "qwen2.5-coder:1.5b" for m in code_models)

        rca_models = reg.list_by_capability(ModelCapability.REASONING_RCA, include_fallback=False)
        assert any(m.model_id == "qwen2.5:3b" for m in rca_models)

    def test_get_fallback_model(self):
        reg = ModelRegistry()
        fallback = reg.get_fallback_model()
        assert fallback.is_fallback is True
        assert fallback.model_id == "deterministic-airgap-mock"


class TestModelRuntimeManager:
    def test_loud_fallback_activation(self):
        # Point to an intentionally down/invalid port to test loud fallback
        mgr = ModelRuntimeManager(ollama_base_url="http://127.0.0.1:54321")
        assert mgr.is_endpoint_reachable() is False

        # Request generation from non-existent live model
        res = mgr.generate(
            model_id="qwen2.5:3b",
            prompt="Why did the bearing fail?",
        )

        assert res.is_fallback is True
        assert res.model_id == "deterministic-airgap-mock"
        assert res.warning is not None
        assert "[FALLBACK MODE ACTIVE" in res.warning
        assert "Verified Findings" in res.text

    def test_deterministic_code_fallback(self):
        mgr = ModelRuntimeManager(ollama_base_url="http://127.0.0.1:54321")
        res = mgr.generate(
            model_id="qwen2.5-coder:1.5b",
            prompt="Calculate peak temperature from telemetry script",
        )

        assert res.is_fallback is True
        assert "import pandas as pd" in res.text
        assert "def analyze_telemetry():" in res.text
