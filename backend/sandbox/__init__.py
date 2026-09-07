"""
CLORA-SecBox: Policy-Controlled, Air-Gapped Secure Execution Subsystem.
SIH Problem Statement 26117 (MRPL)
"""

from backend.sandbox.artifact_inspector import (
    ArtifactInspectionResult,
    ArtifactInspector,
    default_artifact_inspector,
)
from backend.sandbox.ast_guard import ASTCheckResult, ASTSecurityGuard, default_ast_guard
from backend.sandbox.coding_agent import CodingAgentLoop, CodingTaskResult, default_coding_loop
from backend.sandbox.docker_executor import ExecutionResult, SandboxExecutor, default_executor
from backend.sandbox.policy_engine import (
    DeterministicPolicyEngine,
    ExecutionRiskLevel,
    HITLTokenManager,
    PolicyEvaluationResult,
    SecurityPolicy,
    default_hitl_manager,
    default_policy_engine,
)
from backend.sandbox.restricted_host_executor import (
    HostExecutionResult,
    RestrictedHostExecutor,
    default_host_executor,
)
from backend.sandbox.sandbox_manager import (
    SandboxTier,
    SecBoxExecutionResult,
    TieredSandboxManager,
    default_sandbox_manager,
)

__all__ = [
    # Policy & HITL
    "ExecutionRiskLevel",
    "SecurityPolicy",
    "PolicyEvaluationResult",
    "DeterministicPolicyEngine",
    "default_policy_engine",
    "HITLTokenManager",
    "default_hitl_manager",
    # Tiered Sandbox Execution
    "SandboxTier",
    "SecBoxExecutionResult",
    "TieredSandboxManager",
    "default_sandbox_manager",
    # Executors
    "SandboxExecutor",
    "default_executor",
    "RestrictedHostExecutor",
    "default_host_executor",
    "ExecutionResult",
    "HostExecutionResult",
    # Pre-Flight & Artifact Guards
    "ASTSecurityGuard",
    "default_ast_guard",
    "ASTCheckResult",
    "ArtifactInspector",
    "default_artifact_inspector",
    "ArtifactInspectionResult",
    # Agent Loop
    "CodingAgentLoop",
    "CodingTaskResult",
    "default_coding_loop",
]
