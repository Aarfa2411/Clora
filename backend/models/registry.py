"""
Model Registry & Profile Catalog for INDUSAI-X.
Defines model capabilities, hardware requirements, and sovereign runtime profiles.
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ModelCapability(str, Enum):
    CODE_GENERATION = "code_generation"
    REASONING_RCA = "reasoning_rca"
    FAST_TRIAGE = "fast_triage"
    FACTUAL_EXTRACTION = "factual_extraction"
    GENERAL = "general"


class HardwareTier(str, Enum):
    LOW_SPEC_CPU = "low_spec_cpu"
    MID_SPEC_GPU = "mid_spec_gpu"
    HIGH_SPEC_GPU = "high_spec_gpu"


class ModelProfile(BaseModel):
    model_id: str
    display_name: str
    provider: str = "ollama"  # "ollama" | "mock"
    capabilities: List[ModelCapability] = Field(default_factory=list)
    hardware_tier: HardwareTier = HardwareTier.LOW_SPEC_CPU
    context_window: int = 8192
    timeout_seconds: float = 10.0
    quantization: str = "q4_k_m"
    is_active: bool = True
    is_fallback: bool = False
    description: str = ""

    def supports(self, capability: ModelCapability) -> bool:
        return capability in self.capabilities


class ModelRegistry:
    """In-memory catalog of all registered models and their operational profiles."""

    def __init__(self) -> None:
        self._models: Dict[str, ModelProfile] = {}
        self._register_default_profiles()

    def register(self, profile: ModelProfile) -> None:
        self._models[profile.model_id] = profile

    def get(self, model_id: str) -> Optional[ModelProfile]:
        return self._models.get(model_id)

    def list_all(self, active_only: bool = True) -> List[ModelProfile]:
        models = list(self._models.values())
        if active_only:
            return [m for m in models if m.is_active]
        return models

    def list_by_capability(
        self, capability: ModelCapability, include_fallback: bool = True
    ) -> List[ModelProfile]:
        matched = [
            m for m in self._models.values()
            if m.is_active and m.supports(capability)
        ]
        if not include_fallback:
            matched = [m for m in matched if not m.is_fallback]
        return matched

    def get_fallback_model(self) -> ModelProfile:
        fallback = next(
            (m for m in self._models.values() if m.is_fallback and m.is_active), None
        )
        if fallback is None:
            # Construct a safe emergency fallback
            fallback = ModelProfile(
                model_id="deterministic-airgap-mock",
                display_name="Air-Gap Mock Engine",
                provider="mock",
                capabilities=[
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING_RCA,
                    ModelCapability.FAST_TRIAGE,
                    ModelCapability.FACTUAL_EXTRACTION,
                    ModelCapability.GENERAL,
                ],
                is_fallback=True,
                description="Deterministic offline mock engine for air-gap simulation.",
            )
            self.register(fallback)
        return fallback

    def _register_default_profiles(self) -> None:
        """Initializes 1B-4B quantized models calibrated to laptop hardware."""
        # 1. Code Specialist Model (1.5B/3B)
        self.register(
            ModelProfile(
                model_id="qwen2.5-coder:1.5b",
                display_name="Qwen2.5 Coder 1.5B (Quantized)",
                provider="ollama",
                capabilities=[
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.GENERAL,
                ],
                hardware_tier=HardwareTier.LOW_SPEC_CPU,
                context_window=8192,
                timeout_seconds=12.0,
                quantization="q4_k_m",
                description="Specialist lightweight model for Python scripts, data transformations, and math.",
            )
        )

        # 2. Heavy Industrial Reasoning & Root-Cause Synthesizer (3B)
        self.register(
            ModelProfile(
                model_id="qwen2.5:3b",
                display_name="Qwen2.5 3B Instruct",
                provider="ollama",
                capabilities=[
                    ModelCapability.REASONING_RCA,
                    ModelCapability.FACTUAL_EXTRACTION,
                    ModelCapability.GENERAL,
                ],
                hardware_tier=HardwareTier.LOW_SPEC_CPU,
                context_window=8192,
                timeout_seconds=15.0,
                quantization="q4_k_m",
                description="Primary synthesizer for cross-source correlation, failure modes, and SOP retrieval.",
            )
        )

        # 3. High-throughput Fast Triage & Extraction Model (1B)
        self.register(
            ModelProfile(
                model_id="llama3.2:1b",
                display_name="Llama 3.2 1B Instruct",
                provider="ollama",
                capabilities=[
                    ModelCapability.FAST_TRIAGE,
                    ModelCapability.FACTUAL_EXTRACTION,
                ],
                hardware_tier=HardwareTier.LOW_SPEC_CPU,
                context_window=8192,
                timeout_seconds=6.0,
                quantization="q4_k_m",
                description="Ultra-fast query router, intent classifier, and atomic claim extractor.",
            )
        )

        # 4. Deterministic Air-Gap Fallback Simulation
        self.register(
            ModelProfile(
                model_id="deterministic-airgap-mock",
                display_name="Air-Gap Mock Engine (Fallback)",
                provider="mock",
                capabilities=[
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.REASONING_RCA,
                    ModelCapability.FAST_TRIAGE,
                    ModelCapability.FACTUAL_EXTRACTION,
                    ModelCapability.GENERAL,
                ],
                hardware_tier=HardwareTier.LOW_SPEC_CPU,
                context_window=4096,
                timeout_seconds=1.0,
                quantization="none",
                is_fallback=True,
                description="Loud deterministic simulation fallback for zero-dependency test/offline execution.",
            )
        )


default_registry = ModelRegistry()
