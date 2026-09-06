"""
Automated unit tests for AirGapEnforcer and SHA-256 Tamper-Evident Hash Chain.
"""

import os
import socket
import unittest
from unittest.mock import MagicMock

from security.airgap_monitor import (
    AddressValidator,
    AirGapEnforcer,
    AirGapViolationError,
    NetworkTrustProfile,
    get_active_socket_snapshot,
)
from security.network_proof import AirGapSentinel, GENESIS_HASH


class TestAirGapEnforcer(unittest.TestCase):

    def setUp(self):
        AirGapEnforcer.deactivate()
        self.test_log = "tests/test_enforcer_audit.jsonl"
        if os.path.exists(self.test_log):
            os.remove(self.test_log)
        self.sentinel = AirGapSentinel(self.test_log)

    def tearDown(self):
        AirGapEnforcer.deactivate()
        if os.path.exists(self.test_log):
            os.remove(self.test_log)

    def test_address_validator_strict_airgap(self):
        val = AddressValidator(NetworkTrustProfile.STRICT_AIRGAP)
        approved, ip = val.is_destination_approved("127.0.0.1", 8000)
        self.assertTrue(approved)
        self.assertEqual(ip, "127.0.0.1")

        approved, ip = val.is_destination_approved("localhost", 11434)
        self.assertTrue(approved)

        approved, ip = val.is_destination_approved("192.168.1.100", 443)
        self.assertFalse(approved)

        approved, ip = val.is_destination_approved("8.8.8.8", 53)
        self.assertFalse(approved)

    def test_address_validator_industrial_lan(self):
        val = AddressValidator(
            NetworkTrustProfile.INDUSTRIAL_LAN,
            approved_cidrs=["10.42.10.0/24", "192.168.10.0/24"]
        )
        approved, ip = val.is_destination_approved("127.0.0.1", 8000)
        self.assertTrue(approved)

        # Approved subnet
        approved, ip = val.is_destination_approved("10.42.10.50", 502)
        self.assertTrue(approved)

        # Unapproved private subnet
        approved, ip = val.is_destination_approved("10.99.1.1", 502)
        self.assertFalse(approved)

        # Unapproved public IP
        approved, ip = val.is_destination_approved("1.1.1.1", 443)
        self.assertFalse(approved)

    def test_enforcer_blocks_unapproved_connection(self):
        violation_mock = MagicMock()
        AirGapEnforcer.activate(
            profile=NetworkTrustProfile.STRICT_AIRGAP,
            on_violation=violation_mock
        )

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with self.assertRaises(AirGapViolationError) as ctx:
                s.connect(("1.1.1.1", 443))

            self.assertEqual(ctx.exception.destination_ip, "1.1.1.1")
            self.assertEqual(ctx.exception.destination_port, 443)
            violation_mock.assert_called_once_with("1.1.1.1", 443, "STRICT_AIRGAP")
        finally:
            s.close()
            AirGapEnforcer.deactivate()

    def test_tamper_evident_hash_chain_validation(self):
        self.sentinel.audit_cycle("STAGE_1")
        self.sentinel.audit_cycle("STAGE_2")
        self.sentinel.log_violation("1.1.1.1", 443, "Test block")

        valid, line_no, msg = self.sentinel.verify_hash_chain()
        self.assertTrue(valid, msg)

        # Tamper test: modify one character in the log
        with open(self.test_log, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Modify first line payload
        tampered_line = lines[0].replace("STAGE_1", "TAMPERED_STAGE")
        lines[0] = tampered_line

        with open(self.test_log, "w", encoding="utf-8") as f:
            f.writelines(lines)

        valid_tampered, line_no, msg = self.sentinel.verify_hash_chain()
        self.assertFalse(valid_tampered)
        self.assertEqual(line_no, 0)
        self.assertIn("tampering detected", msg.lower())

    def test_active_socket_snapshot(self):
        sockets = get_active_socket_snapshot()
        self.assertIsInstance(sockets, list)
        for s in sockets:
            self.assertIn("protocol", s)
            self.assertIn("local_address", s)
            self.assertIn("compliance", s)


if __name__ == "__main__":
    unittest.main()
