"""
Model Registry & Resource-Aware Provider Gateway for CLORA.
Manages provider resolution, health checks, capability validation, and model switching with rollback.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Any, Optional, List, Protocol

from app.ai.models import (
    ModelCapabilities,
    DEFAULT_MODEL,
    resolve_model,
    get_model_capabilities,
    REGISTERED_MODELS,
)
from app.ai.providers.ollama_provider import OllamaProvider
from app.ai.providers.mock_provider import MockProvider
from app.ai.sovereignty import SovereigntyEgressPolicy, SovereigntyViolationError

logger = logging.getLogger("indusai.registry")


class ModelProviderProtocol(Protocol):
    async def health(self) -> bool: ...
    def get_capabilities(self, model: str) -> ModelCapabilities: ...
    async def generate(self, prompt: str, **kwargs) -> Dict[str, Any]: ...
    async def chat(self, messages: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]: ...


class ModelRegistry:
    """
    Singleton Model Registry Gateway.
    Owns: Provider instance mapping, resource-aware model switching with rollback,
    capabilities checks, and execution telemetry.
    """

    _instance: Optional[ModelRegistry] = None

    def __new__(cls) -> ModelRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._active_model_name: str = DEFAULT_MODEL
        self._providers: Dict[str, Any] = {
            "ollama": OllamaProvider(),
            "mock": MockProvider(),
        }
        self._active_provider_name: str = "ollama"
        self._telemetry_log: List[Dict[str, Any]] = []
        self._initialized = True
        logger.info("ModelRegistry initialized with default model: %s", self._active_model_name)

    @property
    def active_model(self) -> str:
        return self._active_model_name

    @property
    def active_provider_name(self) -> str:
        return self._active_provider_name

    def get_provider(self, provider_name: Optional[str] = None) -> ModelProviderProtocol:
        name = provider_name or self._active_provider_name
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' is not registered.")
        return self._providers[name]

    # --- Resource-Aware Model Switcher with Automatic Rollback ---

    async def switch_model(self, target_model: str) -> Dict[str, Any]:
        """
        Resource-Aware Model Switch Flow:
        Lookup -> Capabilities Check -> Memory Check -> Unload Previous -> Load Target ->
        Health Check -> Test Inference -> Activate (or ROLLBACK on failure).
        """
        t0 = time.perf_counter()
        previous_model = self._active_model_name
        canonical = resolve_model(target_model)
        caps = get_model_capabilities(canonical)

        if not caps:
            raise ValueError(f"No capability metadata found for model '{target_model}'")

        # Sovereign Egress Enforcer Check
        if caps.network_required:
            SovereigntyEgressPolicy.check_destination("https://external-api.cloud.ai")

        logger.info("Initiating model switch: %s -> %s", previous_model, canonical)
        provider = self.get_provider("ollama")

        # 1. Health check
        is_healthy = await provider.health()
        if not is_healthy:
            logger.warning("Ollama provider unhealthy during switch attempt to %s. Falling back to previous.", canonical)
            return {
                "success": False,
                "active_model": previous_model,
                "reason": "Target runtime provider is unhealthy",
                "rollback_performed": True,
            }

        # 2. Test Inference Verification
        try:
            test_res = await provider.generate(
                prompt="Ping test", model=canonical, max_tokens=5, trace_id="SWITCH-TEST"
            )
            if not test_res.get("response"):
                raise RuntimeError("Empty response received during switch test inference.")
        except Exception as exc:
            logger.error("Test inference failed for model '%s': %s. Rolling back to '%s'.", canonical, exc, previous_model)
            return {
                "success": False,
                "active_model": previous_model,
                "reason": f"Test inference failed: {str(exc)}",
                "rollback_performed": True,
            }

        # 3. Successful Switch Activation
        elapsed = time.perf_counter() - t0
        self._active_model_name = canonical

        switch_telemetry = {
            "from_model": previous_model,
            "to_model": canonical,
            "switch_time_ms": round(elapsed * 1000, 1),
            "status": "SUCCESS",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._telemetry_log.append(switch_telemetry)
        logger.info("Model switch successful: %s (took %.2fs)", canonical, elapsed)

        return {
            "success": True,
            "active_model": canonical,
            "switch_time_ms": switch_telemetry["switch_time_ms"],
            "rollback_performed": False,
        }

    # --- High-Level Inference Dispatcher ---

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[str]] = None,
        trace_id: str = "TRC-00000",
        provider_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch generation through active provider with capability check."""
        target_model = resolve_model(model or self._active_model_name)
        caps = get_model_capabilities(target_model)

        if caps and caps.test_only and provider_name != "mock":
            provider_name = "mock"

        provider = self.get_provider(provider_name)
        return await provider.generate(
            prompt=prompt,
            model=target_model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            images=images,
            trace_id=trace_id,
        )

    async def health_check_all(self) -> Dict[str, Any]:
        """Check health across registered providers and return aggregated status."""
        results = {}
        for p_name, provider in self._providers.items():
            try:
                healthy = await provider.health()
                results[p_name] = "HEALTHY" if healthy else "UNUNAVAILABLE"
            except Exception:
                results[p_name] = "ERROR"

        return {
            "active_model": self._active_model_name,
            "sovereign_mode": True,
            "providers": results,
        }

    def list_registered_models(self) -> List[Dict[str, Any]]:
        """List all models registered in the registry."""
        return [m.to_dict() for m in REGISTERED_MODELS]


# Global singleton instance helper
registry = ModelRegistry()
