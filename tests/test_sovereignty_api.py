"""
Unit and integration tests for Sovereignty and Air-Gap API endpoints.
"""

import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes.sovereignty import router
from security.airgap_monitor import AirGapEnforcer, NetworkTrustProfile

app = FastAPI()
app.include_router(router, prefix="/api")
client = TestClient(app)


class TestSovereigntyApi(unittest.TestCase):

    def setUp(self):
        AirGapEnforcer.activate(NetworkTrustProfile.STRICT_AIRGAP)

    def tearDown(self):
        AirGapEnforcer.deactivate()

    def test_get_sovereignty_status(self):
        res = client.get("/api/sovereignty/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("sovereign_mode", data)
        self.assertIn("active_profile", data)
        self.assertIn("open_sockets", data)
        self.assertIn("root_integrity_hash", data)
        self.assertEqual(data["policy"], "APPLICATION_LEVEL_EGRESS_ENFORCED")

    def test_get_audit_trail(self):
        res = client.get("/api/sovereignty/audit-trail?limit=10")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("entries", data)
        self.assertIn("chain_valid", data)
        self.assertTrue(data["chain_valid"])

    def test_post_audit_now(self):
        res = client.post("/api/sovereignty/audit-now")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["audit_entry"]["stage"], "MANUAL_OPERATOR_SNAPSHOT")

    def test_post_simulate_violation(self):
        res = client.post("/api/sovereignty/simulate-violation?target_ip=1.1.1.1&target_port=443")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["simulation_result"], "INTERCEPTED_AND_BLOCKED")
        self.assertTrue(data["intercepted"])
        self.assertEqual(data["status"], "ALERT_TRIGGERED")

    def test_post_profile_change_auditable(self):
        res = client.post(
            "/api/sovereignty/profile",
            json={
                "profile": "INDUSTRIAL_LAN",
                "user_id": "supervisor_john",
                "justification": "Connecting to local refinery SCADA historian subnet 10.42.10.0/24"
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["new_profile"], "INDUSTRIAL_LAN")
        self.assertEqual(data["authorized_user"], "supervisor_john")

        # Revert back to strict
        client.post(
            "/api/sovereignty/profile",
            json={
                "profile": "STRICT_AIRGAP",
                "user_id": "supervisor_john",
                "justification": "Maintenance complete, re-locking to STRICT_AIRGAP"
            }
        )

    def test_get_attestation(self):
        res = client.get("/api/sovereignty/attestation")
        self.assertEqual(res.status_code, 200)
        content = res.text
        self.assertIn("NETWORK COMPLIANCE", content)
        self.assertIn("Level A (Application Egress Guard)", content)

    def test_attestation_identity_endpoint(self):
        res = client.get("/api/sovereignty/attestation/identity")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["key_id"].startswith("CLORA-ED25519-"))
        self.assertIn("BEGIN PUBLIC KEY", data["public_key_pem"])
        self.assertEqual(data["algorithm"], "Ed25519 (Curve25519)")

    def test_sign_and_verify_endpoints(self):
        # 1. Sign
        sign_res = client.post(
            "/api/sovereignty/attestation/sign",
            json={
                "report_id": "TEST-RPT-001",
                "content": "Bearing temperature normal at 65.4°C.",
                "sources": ["Telemetry.csv"],
                "model": "qwen2.5:3b (Local)",
            },
        )
        self.assertEqual(sign_res.status_code, 200)
        proof = sign_res.json()
        self.assertIn("signature", proof)
        self.assertIn("content_sha256", proof)

        # 2. Verify untouched
        verify_res = client.post("/api/sovereignty/attestation/verify", json=proof)
        self.assertEqual(verify_res.status_code, 200)
        self.assertTrue(verify_res.json()["valid"])
        self.assertEqual(verify_res.json()["status"], "SIGNATURE_VALID")

        # 3. Verify tampered
        proof["canonical_payload"]["content"] = "Bearing temperature breached 199.9°C."
        tamper_verify_res = client.post("/api/sovereignty/attestation/verify", json=proof)
        self.assertEqual(tamper_verify_res.status_code, 200)
        self.assertFalse(tamper_verify_res.json()["valid"])
        self.assertEqual(tamper_verify_res.json()["status"], "SIGNATURE_INVALID")

    def test_simulate_tamper_endpoint(self):
        res = client.post("/api/sovereignty/attestation/simulate-tamper")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["before_tampering"]["valid"])
        self.assertFalse(data["after_tampering"]["valid"])
        self.assertEqual(data["after_tampering"]["status"], "SIGNATURE_INVALID_CONTENT_MODIFIED")


if __name__ == "__main__":
    unittest.main()

