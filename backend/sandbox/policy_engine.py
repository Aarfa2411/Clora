"""
CLORA-SecBox Deterministic Policy Engine & Cryptographically Bound HITL Token Subsystem.
Enforces rule-based security policy, capability check, and bound authorization tokens.
SIH Problem Statement 26117 (MRPL)
"""

import hashlib
import hmac
import os
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field


class ExecutionRiskLevel(str, Enum):
    LOW_RISK = "LOW_RISK"                  # Auto-executed within policy limits
    ELEVATED_RISK = "ELEVATED_RISK"        # Requires Human-In-The-Loop (HITL) supervisor approval
    PROHIBITED = "PROHIBITED"              # Forbidden; execution rejected immediately


class SecurityPolicy(BaseModel):
    """Immutable policy governing execution parameters and constraints."""
    policy_id: str = "POL-SECBOX-STD-01"
    version: str = "1.0.0"
    timeout_sec: float = 10.0
    memory_limit: str = "512m"
    cpu_limit: str = "1.0"
    pids_limit: int = 32
    max_output_files: int = 5
    max_total_size_mb: float = 10.0
    network_mode: str = "NONE"
    allow_restricted_host: bool = True
    approval_validity_sec: float = 300.0   # 5-minute expiry on HITL tokens


class PolicyEvaluationResult(BaseModel):
    """Result of deterministic policy inspection prior to sandbox launch."""
    risk_level: ExecutionRiskLevel
    allowed: bool
    requires_approval: bool
    policy_id: str
    violations: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    script_hash: str = ""
    input_hashes: Dict[str, str] = Field(default_factory=dict)


# Immediate hard rejection triggers (unforgivable security violations)
PROHIBITED_MODULES: Set[str] = {
    # Network / socket exfiltration
    "socket", "urllib", "requests", "http", "http.client", "urllib.request", "ftplib", "telnetlib", "smtplib",
    "aiohttp", "httpx", "paramiko", "asyncio.streams",
    # Subprocess / shell execution
    "subprocess", "pty", "multiprocessing", "os.system",
    # Dynamic loader & reflection modules
    "importlib", "ctypes", "inspect", "builtins", "_winapi", "_posixsubprocess",
}

PROHIBITED_BUILTINS: Set[str] = {
    "eval", "exec", "__import__", "compile", "breakpoint", "getattr", "setattr"
}


class DeterministicPolicyEngine:
    """
    Deterministic rule-based policy engine for industrial analytics scripts.
    Zero LLM hallucination: risk classification is governed by hardcoded, auditable rules.
    """

    def __init__(self, policy: Optional[SecurityPolicy] = None):
        self.policy = policy or SecurityPolicy()

    def evaluate(
        self,
        script_code: str,
        input_files: Optional[Dict[str, str]] = None,
        user_role: str = "Plant_Engineer",
    ) -> PolicyEvaluationResult:
        """
        Deterministically evaluates code against security rules.
        Returns PolicyEvaluationResult indicating ALLOW, REQUIRE_APPROVAL, or PROHIBITED.
        """
        script_hash = hashlib.sha256(script_code.encode("utf-8")).hexdigest()
        input_hashes = self._hash_input_files(input_files or {})

        violations: List[str] = []
        reasons: List[str] = []

        code_lower = script_code.lower()

        # 1. HARD RULE: Prohibited modules (immediate rejection)
        for mod in PROHIBITED_MODULES:
            if f"import {mod}" in code_lower or f"from {mod}" in code_lower:
                violations.append(f"CRITICAL: Forbidden module import detected: '{mod}'")

        # 2. HARD RULE: Forbidden builtins (eval, exec, __import__)
        for b in PROHIBITED_BUILTINS:
            # Check for direct calls or standalone references
            if f"{b}(" in code_lower:
                violations.append(f"CRITICAL: Forbidden builtin call detected: '{b}()'")

        # 3. HARD RULE: Forbidden write operations outside /workspace/output
        if "open(" in code_lower and ("'w'" in code_lower or '"w"' in code_lower or "'a'" in code_lower or '"a"' in code_lower):
            if "/workspace/output" not in script_code and "output" not in code_lower:
                violations.append("CRITICAL: File write detected targeting location outside authorized '/workspace/output'")

        # 4. HARD RULE: Path traversal
        if ".." in script_code:
            violations.append("CRITICAL: Potential path traversal ('..') detected in script")

        # If any hard rule was violated -> PROHIBITED
        if violations:
            return PolicyEvaluationResult(
                risk_level=ExecutionRiskLevel.PROHIBITED,
                allowed=False,
                requires_approval=False,
                policy_id=self.policy.policy_id,
                violations=violations,
                reasons=["Security policy violation: script contains forbidden network, execution, or path traversal operations."],
                script_hash=script_hash,
                input_hashes=input_hashes,
            )

        # 5. ELEVATED RISK RULES: Require Human-In-The-Loop Approval
        # Rule 5a: Large script complexity (> 2000 characters or > 60 lines)
        if len(script_code) > 2000 or len(script_code.splitlines()) > 60:
            reasons.append("Elevated complexity: script exceeds standard single-task length threshold (2000 chars / 60 lines).")

        # Rule 5b: Potentially high-resource loop constructs
        if "while " in code_lower:
            reasons.append("Resource caution: script contains 'while' loop construct requiring supervisor review.")

        # Rule 5c: Shell or system commands in comments or strings
        if any(w in code_lower for w in ["cmd.exe", "/bin/sh", "/bin/bash", "powershell"]):
            reasons.append("Suspicious shell token detected in code text.")

        # Rule 5d: Non-engineer roles attempting custom analytics scripts
        if user_role.lower() in ("operator", "field_technician") and len(script_code) > 500:
            reasons.append(f"Role constraint: User role '{user_role}' requires supervisory sign-off for custom analytical scripts.")

        if reasons:
            return PolicyEvaluationResult(
                risk_level=ExecutionRiskLevel.ELEVATED_RISK,
                allowed=False,
                requires_approval=True,
                policy_id=self.policy.policy_id,
                violations=[],
                reasons=reasons,
                script_hash=script_hash,
                input_hashes=input_hashes,
            )

        # 6. Default: Low-risk analytical computation (Permitted)
        return PolicyEvaluationResult(
            risk_level=ExecutionRiskLevel.LOW_RISK,
            allowed=True,
            requires_approval=False,
            policy_id=self.policy.policy_id,
            violations=[],
            reasons=["Standard read-only mathematical calculation on authorized workspace inputs."],
            script_hash=script_hash,
            input_hashes=input_hashes,
        )

    def _hash_input_files(self, input_files: Dict[str, str]) -> Dict[str, str]:
        """Computes SHA-256 fingerprint for all staged input data files."""
        result = {}
        for fname, path_or_content in input_files.items():
            if os.path.exists(path_or_content):
                with open(path_or_content, "rb") as f:
                    result[fname] = hashlib.sha256(f.read()).hexdigest()
            else:
                result[fname] = hashlib.sha256(path_or_content.encode("utf-8")).hexdigest()
        return result


class HITLTokenManager:
    """
    Issues and cryptographically validates Human-In-The-Loop approval tokens.
    Tokens are strictly bound to (execution_id, script_hash, input_hashes, policy_id, user_id, expiry).
    Any 1-byte alteration in script or inputs invalidates approval immediately.
    """

    def __init__(self, signing_secret: Optional[str] = None):
        # Derive or load internal HMAC secret (never exposed via API)
        self._secret = (signing_secret or os.getenv("CLORA_HITL_SECRET", "clora-sovereign-hitl-secret-key-2026")).encode("utf-8")

    def issue_approval_token(
        self,
        execution_id: str,
        script_hash: str,
        input_hashes: Dict[str, str],
        policy_id: str,
        approver_id: str,
        validity_sec: float = 300.0,
    ) -> Dict[str, Any]:
        """Generates a cryptographically bound approval record and HMAC signature."""
        now = time.time()
        expiry = now + validity_sec

        # Canonicalize inputs hash
        sorted_inputs = sorted(f"{k}:{v}" for k, v in input_hashes.items())
        combined_inputs_hash = hashlib.sha256(";".join(sorted_inputs).encode("utf-8")).hexdigest()

        # Construct bound payload
        payload_str = f"{execution_id}|{script_hash}|{combined_inputs_hash}|{policy_id}|{approver_id}|{expiry:.0f}"
        signature = hmac.new(self._secret, payload_str.encode("utf-8"), hashlib.sha256).hexdigest()

        return {
            "token": f"{signature}.{expiry:.0f}",
            "approval_token": f"{signature}.{expiry:.0f}",
            "execution_id": execution_id,
            "script_hash": script_hash,
            "inputs_hash": combined_inputs_hash,
            "policy_id": policy_id,
            "approver_id": approver_id,
            "issued_at": now,
            "expires_at": expiry,
        }

    def validate_approval_token(
        self,
        token: str,
        execution_id: str,
        script_hash: str,
        input_hashes: Dict[str, str],
        policy_id: str,
        approver_id: str,
    ) -> tuple[bool, str]:
        """
        Validates that the approval token:
        1. Is properly signed by the internal key.
        2. Matches the exact script hash and input hashes.
        3. Has not expired.
        """
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return False, "INVALID_TOKEN_FORMAT"
            signature, expiry_str = parts[0], parts[1]
            expiry = float(expiry_str)

            if time.time() > expiry:
                return False, "APPROVAL_TOKEN_EXPIRED"

            sorted_inputs = sorted(f"{k}:{v}" for k, v in input_hashes.items())
            combined_inputs_hash = hashlib.sha256(";".join(sorted_inputs).encode("utf-8")).hexdigest()

            payload_str = f"{execution_id}|{script_hash}|{combined_inputs_hash}|{policy_id}|{approver_id}|{expiry:.0f}"
            expected_sig = hmac.new(self._secret, payload_str.encode("utf-8"), hashlib.sha256).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return False, "TOKEN_PAYLOAD_MISMATCH (Script, inputs, or execution ID altered after approval)"

            return True, "APPROVAL_VALID"
        except Exception as e:
            return False, f"TOKEN_VALIDATION_ERROR: {str(e)}"


default_policy_engine = DeterministicPolicyEngine()
default_hitl_manager = HITLTokenManager()
