"""
Inference façade for CLORA.
Routes requests through ModelRegistry and handles prompt injection scanning.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Optional, Dict, Any, List

from app.ai.registry import registry, ModelRegistry
from app.ai.models import resolve_model, DEFAULT_MODEL
from app.ai.prompts import build_system_prompt
from app.ai.guard import scan_prompt, PromptThreatLevel

logger = logging.getLogger("indusai.inference")


class UnsafePromptError(ValueError):
    """Raised when a prompt fails prompt injection security scanning."""
    pass


class InferenceService:
    """
    Inference Service façade shared across FastAPI endpoints and agents.
    Enforces prompt injection scanning and delegates execution to ModelRegistry.
    """

    def __init__(self, model_registry: Optional[ModelRegistry] = None):
        self.registry = model_registry or registry

    async def close(self) -> None:
        pass

    async def run(
        self,
        prompt: str,
        *,
        task: str = "general",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[str]] = None,
        check_safety: bool = True,
        trace_id: str = "TRC-00000",
    ) -> Dict[str, Any]:
        """Run full non-streaming inference with prompt safety scan and telemetry."""
        if check_safety:
            scan_res = scan_prompt(prompt)
            if scan_res.level == PromptThreatLevel.HIGH:
                raise UnsafePromptError(f"Prompt injection security alert: {scan_res.reason}")
            prompt = scan_res.sanitized

        # Vision auto-routing
        if images and (model is None or model == DEFAULT_MODEL):
            model = "moondream"

        model_tag = resolve_model(model)
        system = build_system_prompt(task)

        return await self.registry.generate(
            prompt=prompt,
            model=model_tag,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            images=images,
            trace_id=trace_id,
        )

    async def health(self) -> bool:
        """Check status of primary provider."""
        status = await self.registry.health_check_all()
        return status.get("providers", {}).get("ollama") == "HEALTHY"
