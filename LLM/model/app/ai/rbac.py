"""
RBAC Gateway & Tool Authorization Policy Enforcer for CLORA.
Defaults unauthenticated sessions to NONE/GUEST and validates tool permissions.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, Any, List, Optional

logger = logging.getLogger("indusai.rbac")


class UserRole(str, Enum):
    NONE = "NONE"
    GUEST = "GUEST"
    OPERATOR = "OPERATOR"
    ENGINEER = "ENGINEER"
    CHIEF_SANCTION_OFFICER = "CHIEF_SANCTION_OFFICER"
    ADMIN = "ADMIN"


class RiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Matrix of role permissions per document authorization tier
ROLE_DOCUMENT_PERMISSIONS: Dict[UserRole, List[str]] = {
    UserRole.NONE: [],
    UserRole.GUEST: ["public_notices"],
    UserRole.OPERATOR: ["public_notices", "equipment_sop", "telemetry_logs"],
    UserRole.ENGINEER: ["public_notices", "equipment_sop", "telemetry_logs", "maintenance_history", "engineering_drawings"],
    UserRole.CHIEF_SANCTION_OFFICER: ["public_notices", "equipment_sop", "telemetry_logs", "maintenance_history", "engineering_drawings", "budget_sanctions", "audit_trails"],
    UserRole.ADMIN: ["public_notices", "equipment_sop", "telemetry_logs", "maintenance_history", "engineering_drawings", "budget_sanctions", "audit_trails", "system_config"],
}

# Tool Risk & Approval Policy Matrix
TOOL_RISK_POLICY: Dict[str, Dict[str, Any]] = {
    "search_equipment_history": {"risk": RiskTier.LOW, "required_roles": [UserRole.OPERATOR, UserRole.ENGINEER, UserRole.CHIEF_SANCTION_OFFICER, UserRole.ADMIN], "human_approval": False},
    "retrieve_sop": {"risk": RiskTier.LOW, "required_roles": [UserRole.OPERATOR, UserRole.ENGINEER, UserRole.CHIEF_SANCTION_OFFICER, UserRole.ADMIN], "human_approval": False},
    "analyze_telemetry": {"risk": RiskTier.LOW, "required_roles": [UserRole.OPERATOR, UserRole.ENGINEER, UserRole.CHIEF_SANCTION_OFFICER, UserRole.ADMIN], "human_approval": False},
    "check_threshold_breach": {"risk": RiskTier.MEDIUM, "required_roles": [UserRole.ENGINEER, UserRole.CHIEF_SANCTION_OFFICER, UserRole.ADMIN], "human_approval": False},
    "generate_audit_report": {"risk": RiskTier.MEDIUM, "required_roles": [UserRole.ENGINEER, UserRole.CHIEF_SANCTION_OFFICER, UserRole.ADMIN], "human_approval": False},
    "recommend_maintenance_action": {"risk": RiskTier.HIGH, "required_roles": [UserRole.ENGINEER, UserRole.CHIEF_SANCTION_OFFICER, UserRole.ADMIN], "human_approval": True},
    "execute_operational_action": {"risk": RiskTier.CRITICAL, "required_roles": [UserRole.CHIEF_SANCTION_OFFICER, UserRole.ADMIN], "human_approval": True},
}


class RBACAuthorizationError(PermissionError):
    """Raised when an un-authorized role attempts document or tool access."""
    pass


class RBACManager:
    """Manages role resolution and pre-retrieval document access control."""

    @staticmethod
    def resolve_role(role_str: Optional[str]) -> UserRole:
        """Resolve a role string to UserRole. Defaults strictly to GUEST."""
        if not role_str:
            return UserRole.GUEST
        try:
            return UserRole(role_str.upper().strip())
        except ValueError:
            logger.warning("Unrecognized role '%s', defaulting to GUEST", role_str)
            return UserRole.GUEST

    @classmethod
    def filter_authorized_categories(cls, role: UserRole) -> List[str]:
        """Return authorized document categories for pre-retrieval filtering."""
        return ROLE_DOCUMENT_PERMISSIONS.get(role, [])

    @classmethod
    def is_document_authorized(cls, role: UserRole, category: str) -> bool:
        """Check if a specific document category is authorized for role."""
        allowed = cls.filter_authorized_categories(role)
        return category.lower() in [c.lower() for c in allowed]


class ToolAuthorizationGateway:
    """Policy-Gated Gateway enforcing tool permissions, parameter validation, and human approval boundaries."""

    @classmethod
    def authorize_tool(cls, tool_name: str, role: UserRole, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Validate role permissions, risk tier, parameter structure, and human approval requirement."""
        if tool_name not in TOOL_RISK_POLICY:
            raise RBACAuthorizationError(f"Tool '{tool_name}' is not registered in security policy.")

        policy = TOOL_RISK_POLICY[tool_name]
        allowed_roles = policy["required_roles"]

        if role not in allowed_roles:
            raise RBACAuthorizationError(
                f"Role '{role.value}' is not authorized to invoke tool '{tool_name}'. Allowed: {[r.value for r in allowed_roles]}"
            )

        # Basic parameter validation (ensure parameters is dict)
        if not isinstance(parameters, dict):
            raise ValueError(f"Invalid parameters for tool '{tool_name}': must be a key-value dict.")

        return {
            "authorized": True,
            "tool": tool_name,
            "risk_tier": policy["risk"].value,
            "requires_human_approval": policy["human_approval"],
            "role": role.value
        }
