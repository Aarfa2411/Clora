"""
Unit and integration tests for CLORA Ed25519 Evidence Attestation.
Verifies digital signing, canonical serialization, independent offline verification,
and deterministic tamper detection.
"""

import json
import os
import shutil
import unittest

from security.attestation import (
    Ed25519KeyManager,
    EvidenceAttestor,
    EvidenceVerifier,
    canonicalize_payload,
)


class TestEvidenceAttestation(unittest.TestCase):

    def setUp(self):
        self.test_keys_dir = "./tests/test_keys"
        if os.path.exists(self.test_keys_dir):
            shutil.rmtree(self.test_keys_dir)
        self.key_mgr = Ed25519KeyManager(keys_dir=self.test_keys_dir)
        self.attestor = EvidenceAttestor(self.key_mgr)

    def tearDown(self):
        if os.path.exists(self.test_keys_dir):
            shutil.rmtree(self.test_keys_dir)

    def test_key_generation_and_persistence(self):
        key_id = self.key_mgr.get_key_id()
        self.assertTrue(key_id.startswith("CLORA-ED25519-"))

        pub_pem = self.key_mgr.get_public_key_pem()
        self.assertIn("BEGIN PUBLIC KEY", pub_pem)

        # Ensure reload reads same key ID
        reloaded_mgr = Ed25519KeyManager(keys_dir=self.test_keys_dir)
        self.assertEqual(reloaded_mgr.get_key_id(), key_id)

    def test_canonical_serialization_deterministic(self):
        d1 = {"z": 1, "a": "test", "m": [3, 2, 1]}
        d2 = {"a": "test", "m": [3, 2, 1], "z": 1}
        bytes1 = canonicalize_payload(d1)
        bytes2 = canonicalize_payload(d2)
        self.assertEqual(bytes1, bytes2)
        self.assertEqual(bytes1, b'{"a":"test","m":[3,2,1],"z":1}')

    def test_sign_and_verify_valid_report(self):
        content = (
            "Equipment P-101 inboard roller bearing temperature reached 104.2°C, "
            "exceeding the 80.0°C maximum threshold."
        )
        proof = self.attestor.sign_report(
            report_id="RPT-MRPL-001",
            content=content,
            sources=["Pump_P101_Maintenance.pdf", "CDU_Vibration.csv"],
            model="qwen2.5:3b",
        )

        self.assertIn("signature", proof)
        self.assertIn("content_sha256", proof)
        self.assertIn("public_key_pem", proof)
        self.assertEqual(proof["key_id"], self.key_mgr.get_key_id())

        # Verify untouched proof
        valid, msg, details = EvidenceVerifier.verify_proof(proof)
        self.assertTrue(valid)
        self.assertIn("SIGNATURE VALID", msg)
        self.assertEqual(details["report_id"], "RPT-MRPL-001")

    def test_signature_fails_on_single_character_tampering(self):
        content = "Equipment temperature reached 80.0°C."
        proof = self.attestor.sign_report(
            report_id="RPT-TEMP-001",
            content=content,
            sources=["Sensor.pdf"],
        )

        # Modify one character: 80.0°C -> 90.0°C
        tampered_proof = json.loads(json.dumps(proof))
        tampered_proof["canonical_payload"]["content"] = "Equipment temperature reached 90.0°C."

        valid, msg, details = EvidenceVerifier.verify_proof(tampered_proof)
        self.assertFalse(valid)
        self.assertIn("CONTENT MODIFIED", msg)

    def test_signature_fails_on_hash_falsification(self):
        content = "Equipment temperature reached 80.0°C."
        proof = self.attestor.sign_report(
            report_id="RPT-HASH-001",
            content=content,
        )

        # Attacker modifies content and recomputes content_sha256 to bypass hash check
        tampered_proof = json.loads(json.dumps(proof))
        tampered_proof["canonical_payload"]["content"] = "Equipment temperature reached 90.0°C."
        recomputed_bytes = canonicalize_payload(tampered_proof["canonical_payload"])
        import hashlib
        tampered_proof["content_sha256"] = hashlib.sha256(recomputed_bytes).hexdigest()

        # The signature verification over canonical bytes must still catch the forgery
        valid, msg, details = EvidenceVerifier.verify_proof(tampered_proof)
        self.assertFalse(valid)
        self.assertIn("Signature verification failed", msg)

    def test_simulate_tampering_helper(self):
        content = "Pressure stable at 4.2 bar."
        proof = self.attestor.sign_report(
            report_id="RPT-SIM-001",
            content=content,
        )

        result = EvidenceVerifier.simulate_tampering(
            proof,
            modified_text="Pressure breached safety limit at 14.8 bar.",
        )

        self.assertTrue(result["before_tampering"]["valid"])
        self.assertEqual(result["before_tampering"]["status"], "SIGNATURE_VALID")

        self.assertFalse(result["after_tampering"]["valid"])
        self.assertEqual(
            result["after_tampering"]["status"], "SIGNATURE_INVALID_CONTENT_MODIFIED"
        )


if __name__ == "__main__":
    unittest.main()
