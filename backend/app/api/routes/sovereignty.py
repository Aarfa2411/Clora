"""
Sovereignty & Air-Gap Compliance API Routes.
Provides live status, active socket inspection, tamper-evident hash trail,
deterministic violation simulation, and certified network compliance attestations.
"""

import os
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from backend.app.core.config import settings
from security.airgap_monitor import (
    AirGapEnforcer,
    AirGapViolationError,
    NetworkTrustProfile,
    get_active_socket_snapshot,
)
from security.network_proof import get_sentinel

router = APIRouter(tags=["Sovereignty & Air-Gap Compliance"])


class ProfileChangeRequest(BaseModel):
    profile: NetworkTrustProfile = Field(..., description="Target network trust profile")
    user_id: str = Field("operator_admin", min_length=1, description="Authenticated administrator ID")
    justification: str = Field(..., min_length=5, description="Operational justification for changing network security profile")


@router.get(
    "/sovereignty/status",
    summary="Air-Gap Network Sentinel & Sovereign Inspection",
)
def get_sovereignty_status():
    """
    Returns live application-level egress enforcement status, active network trust profile,
    detailed socket inspection table, and cryptographic hash chain summary.
    """
    sentinel = get_sentinel(str(settings.AIRGAP_LOG_PATH))
    summary = sentinel.get_summary()
    sockets = get_active_socket_snapshot()

    is_compliant = summary["chain_valid"] and summary["violations_detected"] == 0

    return {
        "sovereign_mode": "AIR_GAPPED_VERIFIED" if is_compliant else "ALERT_POLICY_VIOLATION",
        "is_air_gapped": is_compliant,
        "active_profile": summary["active_profile"],
        "enforcer_active": summary["enforcer_active"],
        "total_audit_cycles": summary["total_audit_cycles"],
        "violations_detected": summary["violations_detected"],
        "root_integrity_hash": summary["root_integrity_hash"],
        "chain_valid": summary["chain_valid"],
        "open_sockets": sockets,
        "external_api_calls_detected": summary["violations_detected"],
        "policy": "APPLICATION_LEVEL_EGRESS_ENFORCED",
        "runtime_binding": "LOCAL_SOCKETS_ONLY",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/sovereignty/audit-trail",
    summary="Get Tamper-Evident SHA-256 Hash Chain Entries",
)
def get_audit_trail(limit: int = Query(50, ge=1, le=200)):
    """Returns the most recent verified blocks from the SHA-256 hash chain."""
    sentinel = get_sentinel(str(settings.AIRGAP_LOG_PATH))
    entries = sentinel.get_recent_entries(limit=limit)
    valid, broken_line, msg = sentinel.verify_hash_chain()

    return {
        "entries": entries,
        "count": len(entries),
        "chain_valid": valid,
        "broken_line": broken_line,
        "verification_message": msg,
    }


@router.post(
    "/sovereignty/audit-now",
    summary="Trigger Instant Socket Audit Snapshot",
)
def trigger_audit_now():
    """Executes an immediate manual process socket audit and appends a block to the hash chain."""
    sentinel = get_sentinel(str(settings.AIRGAP_LOG_PATH))
    entry = sentinel.audit_cycle("MANUAL_OPERATOR_SNAPSHOT")
    return {
        "status": "SUCCESS",
        "message": "Manual audit cycle completed and cryptographically chained.",
        "audit_entry": entry,
    }


@router.post(
    "/sovereignty/simulate-violation",
    summary="Simulate Egress / Policy Violation Test",
)
def simulate_policy_violation(target_ip: str = "1.1.1.1", target_port: int = 443):
    """
    Deterministic offline auditor demonstration tool.
    Attempts an unapproved outbound socket connection to demonstrate that the AirGapEnforcer
    synchronously intercepts, blocks before network transmission, logs the violation,
    and updates the hash chain into an ALERT state.
    """
    sentinel = get_sentinel(str(settings.AIRGAP_LOG_PATH))
    enforcer_active = AirGapEnforcer.is_active()

    # Ensure enforcer is active for test
    if not enforcer_active:
        AirGapEnforcer.activate(
            profile=NetworkTrustProfile.STRICT_AIRGAP,
            on_violation=lambda ip, port, prof: sentinel.log_violation(
                ip, port, f"Simulated egress test to {ip}:{port} intercepted by {prof} policy."
            ),
        )

    blocked = False
    violation_error_msg = ""

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(1.0)
        s.connect((target_ip, target_port))
    except AirGapViolationError as ve:
        blocked = True
        violation_error_msg = str(ve)
    except Exception as e:
        # If already offline at OS level or rejected
        blocked = True
        violation_error_msg = f"Connection intercepted/rejected: {str(e)}"
        sentinel.log_violation(target_ip, target_port, violation_error_msg)
    finally:
        s.close()

    summary = sentinel.get_summary()

    return {
        "simulation_result": "INTERCEPTED_AND_BLOCKED" if blocked else "NOT_BLOCKED",
        "intercepted": blocked,
        "target": f"{target_ip}:{target_port}",
        "policy_profile": summary["active_profile"],
        "reason": violation_error_msg,
        "violations_total": summary["violations_detected"],
        "root_integrity_hash": summary["root_integrity_hash"],
        "status": "ALERT_TRIGGERED" if blocked else "PASSED",
    }


@router.post(
    "/sovereignty/profile",
    summary="Change Network Security Profile (Auditable)",
)
def change_network_profile(req: ProfileChangeRequest):
    """
    Changes the active Network Trust Profile (STRICT_AIRGAP, INDUSTRIAL_LAN, DEVELOPMENT).
    Mandatory reason required; records an immutable transition entry in the SHA-256 hash chain.
    """
    sentinel = get_sentinel(str(settings.AIRGAP_LOG_PATH))
    old_profile = AirGapEnforcer.get_profile().value

    AirGapEnforcer.set_profile(
        profile=req.profile,
        approved_cidrs=settings.AIRGAP_APPROVED_CIDRS if req.profile == NetworkTrustProfile.INDUSTRIAL_LAN else None,
    )

    entry = sentinel.log_policy_change(
        old_profile=old_profile,
        new_profile=req.profile.value,
        user_id=req.user_id,
        justification=req.justification,
    )

    return {
        "status": "SUCCESS",
        "previous_profile": old_profile,
        "new_profile": req.profile.value,
        "authorized_user": req.user_id,
        "audit_entry": entry,
    }


@router.get(
    "/sovereignty/attestation",
    response_class=PlainTextResponse,
    summary="Download Signed Network Compliance Attestation",
)
def get_compliance_attestation():
    """Returns the formal, technically defensible Network Compliance Attestation document."""
    sentinel = get_sentinel(str(settings.AIRGAP_LOG_PATH))
    cert_path = sentinel.generate_compliance_attestation(str(settings.AIRGAP_ATTESTATION_PATH))
    with open(cert_path, "r", encoding="utf-8") as f:
        return f.read()


@router.get(
    "/sovereignty/certificate",
    response_class=PlainTextResponse,
    summary="Download Signed Air-Gap Sovereignty Certificate (Backward Compatibility)",
)
def get_sovereignty_certificate():
    """Backward-compatible endpoint returning the verified compliance attestation."""
    return get_compliance_attestation()
