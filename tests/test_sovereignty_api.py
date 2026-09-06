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


if __name__ == "__main__":
    unittest.main()
