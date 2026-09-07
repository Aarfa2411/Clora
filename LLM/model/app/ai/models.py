"""
Model registry, capabilities, and configuration for INDUSAI-X / CLORA local inference.
Owns: model declarations, capabilities struct, and safe model resolution.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass(frozen=True)
class ModelCapabilities:
    name: str
    label: str
    context_length: int = 8192
    supports_tools: bool = True
    supports_json: bool = True
    supports_vision: bool = False
    local_only: bool = True
    network_required: bool = False
    is_default: bool = False
    is_fallback: bool = False
    test_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "context_length": self.context_length,
            "supports_tools": self.supports_tools,
            "supports_json": self.supports_json,
            "supports_vision": self.supports_vision,
            "local_only": self.local_only,
            "network_required": self.network_required,
            "is_default": self.is_default,
            "is_fallback": self.is_fallback,
            "test_only": self.test_only,
        }


# Dataclass alias for backwards compatibility
ModelConfig = ModelCapabilities


# --- Registered Models ---
REGISTERED_MODELS: List[ModelCapabilities] = [
    ModelCapabilities(
        name="llama3.2:3b",
        label="Llama 3.2 3B (Sovereign Primary)",
        context_length=8192,
        supports_tools=True,
        supports_json=True,
        supports_vision=False,
        local_only=True,
        network_required=False,
        is_default=True,
    ),
    ModelCapabilities(
        name="qwen2.5:3b",
        label="Qwen 2.5 3B (Structured Reasoning)",
        context_length=32768,
        supports_tools=True,
        supports_json=True,
        supports_vision=False,
        local_only=True,
        network_required=False,
    ),
    ModelCapabilities(
        name="phi3:mini",
        label="Phi-3 Mini (Fast Local Fallback)",
        context_length=4096,
        supports_tools=False,
        supports_json=True,
        supports_vision=False,
        local_only=True,
        network_required=False,
        is_fallback=True,
    ),
    ModelCapabilities(
        name="moondream",
        label="Moondream (Local Diagram/Vision)",
        context_length=2048,
        supports_tools=False,
        supports_json=False,
        supports_vision=True,
        local_only=True,
        network_required=False,
    ),
    ModelCapabilities(
        name="mock-sovereign",
        label="Mock Sovereign Engine (Unit Test Only)",
        context_length=4096,
        supports_tools=True,
        supports_json=True,
        supports_vision=True,
        local_only=True,
        network_required=False,
        test_only=True,
    ),
]

_REGISTRY = {m.name: m for m in REGISTERED_MODELS}

DEFAULT_MODEL = os.getenv("INDUSAI_DEFAULT_MODEL") or next(
    (m.name for m in REGISTERED_MODELS if m.is_default), REGISTERED_MODELS[0].name
)
FALLBACK_MODEL = os.getenv("INDUSAI_FALLBACK_MODEL") or next(
    (m.name for m in REGISTERED_MODELS if m.is_fallback), None
)


class UnsupportedModelError(Exception):
    pass


ALIASES = {
    "llama3.2": "llama3.2:3b",
    "llama3": "llama3.2:3b",
    "llama": "llama3.2:3b",
    "phi3": "phi3:mini",
    "phi": "phi3:mini",
    "qwen2.5": "qwen2.5:3b",
    "qwen": "qwen2.5:3b",
    "vision": "moondream",
    "mock": "mock-sovereign",
}


def resolve_model(requested: Optional[str]) -> str:
    """Validate requested model tag, or return default."""
    if requested is None:
        return DEFAULT_MODEL

    canonical = ALIASES.get(requested.lower().strip(), requested)
    if canonical not in _REGISTRY:
        raise UnsupportedModelError(
            f"Model '{requested}' is not registered. Available: {list(_REGISTRY.keys())}"
        )
    return canonical


def get_model_capabilities(model_name: str) -> Optional[ModelCapabilities]:
    """Retrieve capabilities for a model tag."""
    canonical = ALIASES.get(model_name.lower().strip(), model_name)
    return _REGISTRY.get(canonical)


def list_models() -> list[dict]:
    """For UI model selection dropdown."""
    return [m.to_dict() for m in REGISTERED_MODELS]
