"""
LangChain / LangGraph adapter for CLORA.
Supplies model instances and registered industrial tool schemas.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence, Dict

from langchain_ollama import ChatOllama
from langchain_core.tools import BaseTool

from app.ai.models import DEFAULT_MODEL, FALLBACK_MODEL, resolve_model, _REGISTRY
from app.config import settings

logger = logging.getLogger("indusai.langchain")


# ---------------------------------------------------------------------------
# Model factories
# ---------------------------------------------------------------------------

def get_chat_model(
    model: str | None = None,
    temperature: float = 0.3,
    num_predict: int | None = None,
    format: str | None = None,
    **kwargs: Any,
) -> ChatOllama:
    """Return a pre-configured ChatOllama instance for LangGraph agents."""
    model = resolve_model(model)
    return ChatOllama(
        base_url=settings.ollama_base_url,
        model=model,
        temperature=temperature,
        num_predict=num_predict or settings.max_tokens,
        format=format or "",
        **kwargs,
    )


def get_reasoning_model(**kwargs: Any) -> ChatOllama:
    """Return the primary reasoning model (qwen2.5:3b > llama3.2:3b)."""
    for candidate in ["qwen2.5:3b", DEFAULT_MODEL, FALLBACK_MODEL]:
        if candidate and candidate in _REGISTRY:
            logger.info("Reasoning model selected: %s", candidate)
            return get_chat_model(model=candidate, temperature=0.1, **kwargs)
    return get_chat_model(temperature=0.1, **kwargs)


def get_json_model(model: str | None = None, **kwargs: Any) -> ChatOllama:
    """Return a model configured to output ONLY valid JSON."""
    return get_chat_model(model=model, temperature=0.0, format="json", **kwargs)


# ---------------------------------------------------------------------------
# Tool binding helper & Industrial Tool Schemas
# ---------------------------------------------------------------------------

def bind_tools(
    llm: ChatOllama,
    tools: Sequence[BaseTool | dict] | None = None,
) -> ChatOllama:
    """Bind tool-calling schemas to a ChatOllama instance."""
    if tools is None:
        tools = list(TOOL_SCHEMAS.values())
    return llm.bind_tools(tools)


# Industrial tool definitions for refinery maintenance and equipment investigation
TOOL_SCHEMAS: dict[str, dict] = {
    "search_equipment_history": {
        "type": "function",
        "function": {
            "name": "search_equipment_history",
            "description": "Search historical maintenance and inspection logs for an equipment tag (e.g., Pump P-101)",
            "parameters": {
                "type": "object",
                "properties": {
                    "equipment_tag": {"type": "string", "description": "Equipment tag (e.g. P-101, CDU-1, V-204)"},
                    "timeframe_days": {"type": "integer", "description": "Lookback window in days (default: 180)"},
                },
                "required": ["equipment_tag"],
            },
        },
    },
    "analyze_telemetry": {
        "type": "function",
        "function": {
            "name": "analyze_telemetry",
            "description": "Perform deterministic mathematical calculation on telemetry CSV data using Pandas/DuckDB",
            "parameters": {
                "type": "object",
                "properties": {
                    "unit_id": {"type": "string", "description": "Equipment or refinery unit tag"},
                    "parameter": {"type": "string", "description": "Telemetry parameter (vibration, temperature, pressure)"},
                },
                "required": ["unit_id", "parameter"],
            },
        },
    },
    "check_threshold_breach": {
        "type": "function",
        "function": {
            "name": "check_threshold_breach",
            "description": "Evaluate observed telemetry value against standard industrial safety thresholds",
            "parameters": {
                "type": "object",
                "properties": {
                    "parameter": {"type": "string", "description": "Telemetry parameter name"},
                    "observed_value": {"type": "number", "description": "Observed telemetry value"},
                    "threshold_limit": {"type": "number", "description": "Maximum safe operational threshold"},
                },
                "required": ["parameter", "observed_value", "threshold_limit"],
            },
        },
    },
    "retrieve_sop": {
        "type": "function",
        "function": {
            "name": "retrieve_sop",
            "description": "Retrieve standard operating procedures and technical manuals for equipment tag",
            "parameters": {
                "type": "object",
                "properties": {
                    "equipment_tag": {"type": "string", "description": "Target equipment tag"},
                },
                "required": ["equipment_tag"],
            },
        },
    },
    "generate_audit_report": {
        "type": "function",
        "function": {
            "name": "generate_audit_report",
            "description": "Compile verified evidence and telemetry into an auditable evidence package",
            "parameters": {
                "type": "object",
                "properties": {
                    "incident_id": {"type": "string", "description": "Incident reference ID"},
                },
                "required": ["incident_id"],
            },
        },
    },
}


def get_tool_schema(name: str) -> dict | None:
    return TOOL_SCHEMAS.get(name)


def list_tool_schemas() -> list[str]:
    return list(TOOL_SCHEMAS.keys())


TOOL_DEFINITIONS = TOOL_SCHEMAS
