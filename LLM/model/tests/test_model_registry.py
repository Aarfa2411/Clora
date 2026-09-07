"""
Unit tests for ModelRegistry, capability checking, and model switching.
"""

import asyncio
import pytest
from app.ai.registry import ModelRegistry
from app.ai.models import resolve_model, UnsupportedModelError


def test_model_registry_resolution():
    reg = ModelRegistry()
    assert reg.active_model == "llama3.2:3b"

    caps = reg.list_registered_models()
    assert len(caps) >= 4


def test_model_registry_generate_mock():
    reg = ModelRegistry()
    res = asyncio.run(reg.generate(
        prompt="Test prompt",
        model="mock-sovereign",
        provider_name="mock",
        trace_id="TEST-001"
    ))
    assert res["provider"] == "mock_test_only"
    assert "[MOCK TEST RESPONSE]" in res["response"]
    assert res["trace_id"] == "TEST-001"


def test_invalid_model_resolution():
    with pytest.raises(UnsupportedModelError):
        resolve_model("nonexistent_model_tag_xyz")
