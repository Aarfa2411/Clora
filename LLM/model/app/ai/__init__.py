"""
app.ai — CLORA local inference engine package.
"""
from app.ai.models import (
    ModelCapabilities,
    ModelConfig,
    REGISTERED_MODELS,
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    UnsupportedModelError,
    resolve_model,
    list_models,
)
from app.ai.providers.ollama_provider import OllamaProvider
OllamaClient = OllamaProvider

from app.ai.inference import InferenceService, UnsafePromptError
from app.ai.prompts import build_system_prompt, list_tasks
from app.ai.guard import scan_prompt, sanitize, is_safe, PromptThreatLevel
from app.ai.langchain_adapter import get_chat_model, get_reasoning_model, get_json_model, bind_tools
from app.ai.sovereignty import SovereigntyEgressPolicy, CanonicalSHA256AuditChain
from app.ai.rbac import RBACManager, ToolAuthorizationGateway
from app.ai.registry import ModelRegistry, registry

__all__ = [
    "ModelCapabilities",
    "ModelConfig",
    "REGISTERED_MODELS",
    "DEFAULT_MODEL",
    "FALLBACK_MODEL",
    "UnsupportedModelError",
    "resolve_model",
    "list_models",
    "OllamaProvider",
    "OllamaClient",
    "InferenceService",
    "UnsafePromptError",
    "build_system_prompt",
    "list_tasks",
    "scan_prompt",
    "sanitize",
    "is_safe",
    "PromptThreatLevel",
    "get_chat_model",
    "get_reasoning_model",
    "get_json_model",
    "bind_tools",
    "SovereigntyEgressPolicy",
    "CanonicalSHA256AuditChain",
    "RBACManager",
    "ToolAuthorizationGateway",
    "ModelRegistry",
    "registry",
]
