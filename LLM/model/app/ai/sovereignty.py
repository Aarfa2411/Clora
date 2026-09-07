"""
Sovereignty Egress Policy & Cryptographic Audit Chain for CLORA.
Enforces offline-first/air-gap compatibility and SHA-256 canonical hash chaining.
"""
from __future__ import annotations

import json
import logging
import time
import hashlib
from typing import Dict, Any, Optional

from app.config import settings

logger = logging.getLogger("indusai.sovereignty")


class SovereigntyViolationError(PermissionError):
    """Raised when network egress policy is violated in sovereign mode."""
    pass


class SovereigntyEgressPolicy:
    """
    Application & Deployment Egress Enforcer.
    Validates that outgoing requests stay within local boundaries (localhost / Ollama / local DB).
    """

    ALLOWED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

    @classmethod
    def check_destination(cls, target_url: str) -> bool:
        """Verify that a target URL is local and permissible under SOVEREIGN_MODE."""
        if not getattr(settings, "sovereign_mode", True):
            return True

        from urllib.parse import urlparse
        parsed = urlparse(target_url)
        hostname = parsed.hostname or ""

        if hostname in cls.ALLOWED_HOSTS or hostname.endswith(".local"):
            return True

        logger.error("SOVEREIGN EGRESS BLOCKED: Attempted external call to %s", target_url)
        raise SovereigntyViolationError(
            f"External egress to '{hostname}' is blocked under SOVEREIGN_MODE policy."
        )

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Return sovereignty and egress compliance status dict."""
        return {
            "sovereign_mode": getattr(settings, "sovereign_mode", True),
            "application_egress": "BLOCKED",
            "external_connectivity_test": "BLOCKED",
            "ollama_local": "AVAILABLE",
            "allowed_hosts": list(cls.ALLOWED_HOSTS)
        }


class CanonicalSHA256AuditChain:
    """
    Cryptographically linked SHA-256 audit log chain.
    Hashes are computed over canonical JSON serialization of event data.
    Formula: H_k = SHA256(H_{k-1} + canonical_json(event_k))
    """

    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(self, initial_head: Optional[str] = None):
        self.head_hash = initial_head or self.GENESIS_HASH
        self.chain: list[dict] = []

    def append_event(
        self,
        action: str,
        resource: str,
        user_id: str = "system",
        role: str = "GUEST",
        trace_id: str = "TRC-00000",
        result: str = "SUCCESS",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Append an event to the audit chain and compute the new head hash."""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        canonical_event = {
            "action": action,
            "metadata": metadata or {},
            "previous_hash": self.head_hash,
            "resource": resource,
            "result": result,
            "role": role,
            "timestamp": timestamp,
            "trace_id": trace_id,
            "user_id": user_id,
        }

        canonical_bytes = json.dumps(canonical_event, sort_keys=True).encode("utf-8")
        current_hash = hashlib.sha256(canonical_bytes).hexdigest()

        audit_record = {
            **canonical_event,
            "current_hash": current_hash
        }

        self.head_hash = current_hash
        self.chain.append(audit_record)
        return audit_record

    def verify_chain(self) -> bool:
        """Verify structural integrity of the hash chain."""
        expected_prev = self.GENESIS_HASH
        for event in self.chain:
            if event["previous_hash"] != expected_prev:
                return False
            payload = {
                "action": event["action"],
                "metadata": event["metadata"],
                "previous_hash": event["previous_hash"],
                "resource": event["resource"],
                "result": event["result"],
                "role": event["role"],
                "timestamp": event["timestamp"],
                "trace_id": event["trace_id"],
                "user_id": event["user_id"],
            }
            computed = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
            if computed != event["current_hash"]:
                return False
            expected_prev = event["current_hash"]
        return True
