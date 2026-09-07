"""
ABAC + Resource-Level Policy Engine and Tool Authorization Gateway for Clora (INDUSAI-X).
Decouples LLM tool requests from deterministic authorization checks.
"""

from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field


class ActorContext(BaseModel):
    """Execution identity of the actor requesting tool execution."""
    actor_type: Literal["user", "agent"]
    actor_id: str
    role: str  # admin, supervisor, engineer, analyst, viewer, agent_rag, agent_investigation, agent_engineering, agent_planner
    department: str = "operations"
    session_id: str = "default_session"
    active_task_id: Optional[str] = None


class ResourceContext(BaseModel):
    """Target resource specification."""
    workspace_id: str
    subfolder: Literal["input", "working", "output", "temp", "any"] = "working"
    rel_path: Optional[str] = None
    file_classification: Literal["public", "internal", "confidential", "critical_safety"] = "internal"
    is_critical_procedure: bool = False


class AuthorizationDecision(BaseModel):
    """Deterministic result of tool authorization inspection."""
    allowed: bool
    policy_id: str
    reason: str
    requires_hitl: bool = False


# Canonical Role Capability Matrix
ROLE_PERMISSIONS: Dict[str, Dict[str, Any]] = {
    "admin": {
        "allowed_tools": {"*"},
        "allowed_folders": {"input", "working", "output", "temp"},
        "can_overwrite_critical": True,
        "max_query_rows": 10000,
    },
    "supervisor": {
        "allowed_tools": {
            "file:read", "file:search", "file:list", "file:metadata",
            "file:write", "file:patch", "file:delete",
            "vision:ocr_ingest", "spreadsheet:query", "spreadsheet:calc", "spreadsheet:export"
        },
        "allowed_folders": {"input", "working", "output", "temp"},
        "can_overwrite_critical": True,
        "max_query_rows": 5000,
    },
    "engineer": {
        "allowed_tools": {
            "file:read", "file:search", "file:list", "file:metadata",
            "file:write", "file:patch",
            "vision:ocr_ingest", "spreadsheet:query", "spreadsheet:calc", "spreadsheet:export"
        },
        "allowed_folders": {"working", "output", "temp"},
        "can_overwrite_critical": False,  # Blocked from modifying critical safety procedures without supervisor elevation
        "max_query_rows": 2000,
    },
    "analyst": {
        "allowed_tools": {
            "file:read", "file:search", "file:list", "file:metadata",
            "spreadsheet:query", "spreadsheet:calc"
        },
        "allowed_folders": {"input", "working", "output", "temp"},
        "can_overwrite_critical": False,
        "max_query_rows": 2000,
    },
    "viewer": {
        "allowed_tools": {
            "file:read", "file:search", "file:list", "file:metadata",
            "spreadsheet:query"
        },
        "allowed_folders": {"input", "output"},
        "can_overwrite_critical": False,
        "max_query_rows": 500,
    },
    # Dedicated Agent Scopes
    "agent_rag": {
        "allowed_tools": {"file:read", "file:search", "file:list", "file:metadata"},
        "allowed_folders": {"input", "working", "output"},
        "can_overwrite_critical": False,
        "max_query_rows": 500,
    },
    "agent_investigation": {
        "allowed_tools": {
            "file:read", "file:search", "file:list", "file:metadata",
            "file:write", "spreadsheet:query", "spreadsheet:calc"
        },
        "allowed_folders": {"working", "temp"},
        "can_overwrite_critical": False,
        "max_query_rows": 2000,
    },
    "agent_engineering": {
        "allowed_tools": {
            "file:read", "file:search", "file:list", "file:metadata",
            "file:write", "spreadsheet:query", "spreadsheet:calc", "spreadsheet:export"
        },
        "allowed_folders": {"working", "output", "temp"},
        "can_overwrite_critical": False,
        "max_query_rows": 2000,
    },
    "agent_planner": {
        "allowed_tools": {"file:list", "file:metadata"},
        "allowed_folders": {"input", "working", "output", "temp"},
        "can_overwrite_critical": False,
        "max_query_rows": 100,
    },
}


class ToolAuthorizationGateway:
    """
    Deterministic Policy Engine.
    Enforces that 'the LLM requesting an action' is never equivalent to authorization.
    """

    @classmethod
    def evaluate(
        cls,
        actor: ActorContext,
        tool_name: str,
        resource: ResourceContext,
    ) -> AuthorizationDecision:
        role = actor.role.lower()
        if role not in ROLE_PERMISSIONS:
            return AuthorizationDecision(
                allowed=False,
                policy_id="POL_UNKNOWN_ROLE",
                reason=f"Unknown or unregistered role: {role}",
            )

        perms = ROLE_PERMISSIONS[role]
        allowed_tools = perms["allowed_tools"]

        # 1. Tool Permission Check
        if "*" not in allowed_tools and tool_name not in allowed_tools:
            return AuthorizationDecision(
                allowed=False,
                policy_id="POL_TOOL_DENIED",
                reason=f"Role '{role}' is not authorized to invoke tool '{tool_name}'",
            )

        # 2. Write / Target Folder Isolation Check
        if tool_name in {"file:write", "file:patch", "file:delete", "spreadsheet:export"}:
            if resource.subfolder == "input" and role != "admin":
                return AuthorizationDecision(
                    allowed=False,
                    policy_id="POL_INPUT_IMMUTABLE",
                    reason="The 'input/' folder contains immutable original artifacts and cannot be written to.",
                )

            if resource.subfolder not in perms["allowed_folders"]:
                return AuthorizationDecision(
                    allowed=False,
                    policy_id="POL_FOLDER_DENIED",
                    reason=f"Role '{role}' cannot write to folder '{resource.subfolder}/'",
                )

            # 3. Critical Safety Resource Guard (ABAC)
            if resource.is_critical_procedure and not perms["can_overwrite_critical"]:
                return AuthorizationDecision(
                    allowed=False,
                    policy_id="POL_CRITICAL_PROCEDURE_BLOCKED",
                    reason="Modification of critical safety procedures requires Supervisor/Admin elevation token.",
                    requires_hitl=True,
                )

        return AuthorizationDecision(
            allowed=True,
            policy_id=f"POL_ALLOW_{role.upper()}",
            reason=f"Authorized under {role} policy matrix",
        )
