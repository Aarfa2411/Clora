"""
Mock Provider Implementation for Automated Testing & Integration CI.
STRICTLY FLAGGED test_only=True. Never used as a production LLM fallback.
"""
from __future__ import annotations

import time
from typing import Dict, Any, List, Optional
from app.ai.models import ModelCapabilities


class MockProvider:
    """Mock Provider strictly for unit testing and CI validation."""

    def __init__(self):
        self.model_name = "mock-sovereign"

    async def health(self) -> bool:
        return True

    def get_capabilities(self, model: str = "mock-sovereign") -> ModelCapabilities:
        return ModelCapabilities(
            name="mock-sovereign",
            label="Mock Engine (Unit Test Only)",
            context_length=4096,
            supports_tools=True,
            supports_json=True,
            supports_vision=True,
            local_only=True,
            network_required=False,
            test_only=True,
        )

    async def generate(
        self,
        prompt: str,
        model: str = "mock-sovereign",
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[str]] = None,
        trace_id: str = "TRC-TEST",
    ) -> Dict[str, Any]:
        """Return simulated structured test output."""
        return {
            "response": f"[MOCK TEST RESPONSE] Analysis for: '{prompt[:60]}...'",
            "model": model,
            "provider": "mock_test_only",
            "latency_ms": 15.0,
            "tokens_generated": 20,
            "tokens_per_second": 1333.3,
            "temperature": 0.0,
            "trace_id": trace_id,
            "done": True,
        }

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str = "mock-sovereign",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        trace_id: str = "TRC-TEST",
    ) -> Dict[str, Any]:
        return {
            "message": {"role": "assistant", "content": "[MOCK CHAT RESPONSE] Test completed."},
            "response": "[MOCK CHAT RESPONSE] Test completed.",
            "model": model,
            "provider": "mock_test_only",
            "latency_ms": 10.0,
            "tokens_generated": 10,
            "trace_id": trace_id,
        }
