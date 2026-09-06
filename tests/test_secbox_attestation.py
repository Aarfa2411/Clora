"""
Tests for CLORA-SecBox Cryptographic Evidence Attestation and Verification.
SIH Problem Statement 26117 (MRPL)

Verifies:
1. CodingAgentLoop produces cryptographically signed attestation packages.
2. Canonical execution evidence binds policy, runtime tier, code_executed flag,
   input hashes, script hash, and artifact hashes.
3. Offline EvidenceVerifier verifies authentic proof packages.
4. Any 1-byte payload or artifact hash tampering fails signature verification.
"""

import json
from unittest.mock import MagicMock

from backend.sandbox.coding_agent import CodingAgentLoop
from backend.sandbox.sandbox_manager import (
    SandboxTier,
    SecBoxExecutionResult,
    TieredSandboxManager,
)
from security.attestation import EvidenceVerifier, get_attestor


def test_secbox_evidence_attestation_end_to_end(tmp_path):
    """Verifies that successful execution outputs a valid Ed25519 signature package."""
    mock_runtime = MagicMock()
    mock_runtime.generate.return_value = MagicMock(
        text="print('Compressor pressure ratio: 3.42')\nwith open('/workspace/output/metrics.txt', 'w') as f:\n    f.write('pressure_ratio=3.42')\n"
    )

    # Output file
    output_file = tmp_path / "metrics.txt"
    output_file.write_text("pressure_ratio=3.42", encoding="utf-8")

    mock_sandbox = MagicMock(spec=TieredSandboxManager)
    mock_sandbox.execute.return_value = SecBoxExecutionResult(
        exit_code=0,
        stdout="Compressor pressure ratio: 3.42",
        stderr="",
        execution_time_ms=450.0,
        result_status="SUCCESS",
        runtime_tier=SandboxTier.RESTRICTED_LOCAL,
        execution_mode="HOST_RESTRICTED",
        code_executed=True,
        generated_files=[str(output_file)],
        warning=None,
    )

    loop = CodingAgentLoop(
        runtime=mock_runtime,
        sandbox_manager=mock_sandbox,
        audit_file=str(tmp_path / "audit.jsonl"),
    )

    task_result = loop.run_coding_task(
        task_prompt="Calculate compressor pressure ratio and write to metrics.txt",
        input_files={"telemetry.csv": "timestamp,pressure\n1,3.42\n"},
        user_id="test_engineer",
        user_role="Plant_Engineer",
    )

    assert task_result.success is True
    assert task_result.status == "VERIFIED_SUCCESS"
    assert task_result.code_executed is True
    assert task_result.runtime_tier == "RESTRICTED_LOCAL"
    assert len(task_result.artifacts) == 1
    assert "metrics.txt" in task_result.artifact_hashes

    # Check attestation proof
    proof = task_result.attestation_proof
    assert proof is not None
    assert proof["algorithm"] == "Ed25519"
    assert "signature" in proof
    assert "canonical_payload" in proof

    # Verify canonical payload content
    payload_content = json.loads(proof["canonical_payload"]["content"])
    assert payload_content["execution_id"] == task_result.execution_id
    assert payload_content["code_executed"] is True
    assert payload_content["runtime_tier"] == "RESTRICTED_LOCAL"
    assert payload_content["network_mode"] == "NONE"
    assert "telemetry.csv" in payload_content["input_hashes"]
    assert "metrics.txt" in payload_content["artifact_hashes"]

    # Verify offline with EvidenceVerifier
    is_valid, msg, details = EvidenceVerifier.verify_proof(proof)
    assert is_valid is True
    assert "SIGNATURE VALID" in msg


def test_secbox_tamper_detection():
    """Verifies that altering 1 byte in canonical execution evidence rejects verification."""
    attestor = get_attestor()

    evidence_dict = {
        "execution_id": "SECBOX-9999",
        "script_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "input_hashes": {"input.csv": "abc123hash"},
        "artifact_hashes": {"chart.png": "def456hash"},
        "exit_code": 0,
        "runtime_tier": "HARDENED_CONTAINER",
        "code_executed": True,
        "policy_id": "STRICT_AIRGAP_V1",
        "network_mode": "NONE",
    }

    proof = attestor.sign_report(
        report_id="SECBOX-9999",
        content=json.dumps(evidence_dict, sort_keys=True),
        sources=["input.csv"],
        model="CLORA-SecBox (HARDENED_CONTAINER)",
        extra_metadata={"code_executed": True},
    )

    # Initial proof is valid
    is_valid, msg, _ = EvidenceVerifier.verify_proof(proof)
    assert is_valid is True

    # Tamper with 1 byte inside canonical_payload
    tampered_proof = json.loads(json.dumps(proof))
    tampered_evidence = json.loads(tampered_proof["canonical_payload"]["content"])
    # Adversary claims exit_code was 0 when it was modified or changes code_executed
    tampered_evidence["runtime_tier"] = "RESTRICTED_LOCAL"  # Changed tier!
    tampered_proof["canonical_payload"]["content"] = json.dumps(tampered_evidence, sort_keys=True)

    # Verification must fail
    is_valid, msg, _ = EvidenceVerifier.verify_proof(tampered_proof)
    assert is_valid is False
    assert "CONTENT MODIFIED" in msg


def test_secbox_safe_fallback_simulation_attestation():
    """Verifies that Tier 3 Safe Fallback produces an attestation explicitly recording code_executed=False."""
    attestor = get_attestor()

    evidence_dict = {
        "execution_id": "SECBOX-SIM-001",
        "script_hash": "simulated_script_hash",
        "input_hashes": {},
        "artifact_hashes": {},
        "exit_code": 0,
        "runtime_tier": "SAFE_FALLBACK",
        "execution_mode": "SIMULATION",
        "code_executed": False,  # Explicitly transparent
        "policy_id": "STRICT_AIRGAP_V1",
        "network_mode": "NONE",
    }

    proof = attestor.sign_report(
        report_id="SECBOX-SIM-001",
        content=json.dumps(evidence_dict, sort_keys=True),
        sources=[],
        model="CLORA-SecBox (SAFE_FALLBACK)",
        extra_metadata={"code_executed": False, "execution_mode": "SIMULATION"},
    )

    is_valid, msg, details = EvidenceVerifier.verify_proof(proof)
    assert is_valid is True

    # Audit payload explicitly declares no execution
    canonical = proof["canonical_payload"]
    assert canonical["metadata"]["code_executed"] is False
    assert canonical["metadata"]["execution_mode"] == "SIMULATION"
