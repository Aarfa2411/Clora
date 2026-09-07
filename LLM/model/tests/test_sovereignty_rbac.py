"""
Unit tests for Sovereignty Egress Policy, Canonical SHA-256 Audit Chain, and RBAC Gateway.
"""

import pytest
from app.ai.sovereignty import SovereigntyEgressPolicy, CanonicalSHA256AuditChain, SovereigntyViolationError
from app.ai.rbac import RBACManager, UserRole, ToolAuthorizationGateway, RBACAuthorizationError


def test_sovereignty_egress_policy_localhost():
    # Localhost should be permitted
    assert SovereigntyEgressPolicy.check_destination("http://localhost:11434") is True
    assert SovereigntyEgressPolicy.check_destination("http://127.0.0.1:8000") is True


def test_sovereignty_egress_policy_external_blocked():
    # External egress should be blocked under SOVEREIGN_MODE
    with pytest.raises(SovereigntyViolationError):
        SovereigntyEgressPolicy.check_destination("https://api.openai.com/v1/chat")


def test_canonical_sha256_audit_chain():
    chain = CanonicalSHA256AuditChain()
    
    e1 = chain.append_event("TEST_ACTION_1", resource="res_1", trace_id="TRC-01")
    assert e1["previous_hash"] == CanonicalSHA256AuditChain.GENESIS_HASH
    assert len(e1["current_hash"]) == 64

    e2 = chain.append_event("TEST_ACTION_2", resource="res_2", trace_id="TRC-02")
    assert e2["previous_hash"] == e1["current_hash"]
    
    # Structural verification should pass
    assert chain.verify_chain() is True


def test_rbac_default_role_guest():
    # Unauthenticated or empty role must default to GUEST
    role = RBACManager.resolve_role(None)
    assert role == UserRole.GUEST

    categories = RBACManager.filter_authorized_categories(UserRole.GUEST)
    assert categories == ["public_notices"]


def test_tool_authorization_gateway():
    # Engineer should be authorized for analyze_telemetry (LOW risk)
    auth = ToolAuthorizationGateway.authorize_tool("analyze_telemetry", UserRole.ENGINEER, {"unit_id": "P101"})
    assert auth["authorized"] is True

    # GUEST should be rejected for industrial tools
    with pytest.raises(RBACAuthorizationError):
        ToolAuthorizationGateway.authorize_tool("analyze_telemetry", UserRole.GUEST, {})
