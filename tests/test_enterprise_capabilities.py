from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

from app.enterprise.config import CAPABILITY_NAMES
from app.main import app


ENTERPRISE_ENV_KEYS = [
    "MRA_ENTERPRISE_ENABLED",
    "MRA_ENTERPRISE_IDENTITY_PROVIDER",
    "MRA_ENTERPRISE_IDENTITY_VERIFIED",
    "MRA_ENTERPRISE_HIS_ADAPTER",
    "MRA_ENTERPRISE_HIS_VERIFIED",
    "MRA_ENTERPRISE_EMR_ADAPTER",
    "MRA_ENTERPRISE_EMR_VERIFIED",
    "MRA_ENTERPRISE_AUDIT_ENABLED",
    "MRA_ENTERPRISE_AUDIT_VERIFIED",
    "MRA_ENTERPRISE_METRICS_ENABLED",
    "MRA_ENTERPRISE_METRICS_VERIFIED",
    "MRA_ENTERPRISE_BACKUP_RESTORE_ENABLED",
    "MRA_ENTERPRISE_BACKUP_RESTORE_VERIFIED",
    "MRA_ENTERPRISE_UPGRADE_ROLLBACK_ENABLED",
    "MRA_ENTERPRISE_UPGRADE_ROLLBACK_VERIFIED",
    "MRA_ENTERPRISE_EMR_ENDPOINT",
    "MRA_ENTERPRISE_EMR_API_KEY",
]
VALID_STATES = {"disabled", "mock", "configured_unverified", "verified"}


class EnterpriseCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.original_env = {key: os.environ.get(key) for key in ENTERPRISE_ENV_KEYS}
        for key in ENTERPRISE_ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_default_enterprise_capabilities_are_disabled(self):
        response = TestClient(app).get("/api/enterprise/capabilities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload), set(CAPABILITY_NAMES))
        self.assertEqual(set(payload.values()), {"disabled"})

    def test_mock_enabled_capabilities_report_mock_only(self):
        os.environ.update(
            {
                "MRA_ENTERPRISE_ENABLED": "1",
                "MRA_ENTERPRISE_IDENTITY_PROVIDER": "mock_oidc",
                "MRA_ENTERPRISE_HIS_ADAPTER": "mock",
                "MRA_ENTERPRISE_EMR_ADAPTER": "mock",
                "MRA_ENTERPRISE_AUDIT_ENABLED": "1",
                "MRA_ENTERPRISE_METRICS_ENABLED": "1",
                "MRA_ENTERPRISE_BACKUP_RESTORE_ENABLED": "1",
                "MRA_ENTERPRISE_UPGRADE_ROLLBACK_ENABLED": "1",
            }
        )

        payload = TestClient(app).get("/api/enterprise/capabilities").json()

        self.assertEqual(payload["identity_provider"], "mock")
        self.assertEqual(payload["his_adapter"], "mock")
        self.assertEqual(payload["emr_adapter"], "mock")
        self.assertEqual(payload["audit_events"], "mock")
        self.assertEqual(payload["metrics"], "mock")
        self.assertEqual(payload["backup_restore"], "mock")
        self.assertEqual(payload["upgrade_rollback"], "mock")

    def test_configured_unverified_status_does_not_expose_config(self):
        os.environ.update(
            {
                "MRA_ENTERPRISE_ENABLED": "1",
                "MRA_ENTERPRISE_IDENTITY_PROVIDER": "configured",
                "MRA_ENTERPRISE_HIS_ADAPTER": "configured",
                "MRA_ENTERPRISE_EMR_ADAPTER": "configured",
                "MRA_ENTERPRISE_EMR_ENDPOINT": "https://hospital.example.invalid/emr",
                "MRA_ENTERPRISE_EMR_API_KEY": "secret-key-value",
            }
        )

        response = TestClient(app).get("/api/enterprise/capabilities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["identity_provider"], "configured_unverified")
        self.assertEqual(payload["his_adapter"], "configured_unverified")
        self.assertEqual(payload["emr_adapter"], "configured_unverified")
        self.assertTrue(set(payload.values()).issubset(VALID_STATES))
        self.assertNotIn("hospital.example.invalid", response.text)
        self.assertNotIn("secret-key-value", response.text)

    def test_verified_status_is_explicit_and_still_shape_limited(self):
        os.environ.update(
            {
                "MRA_ENTERPRISE_ENABLED": "1",
                "MRA_ENTERPRISE_IDENTITY_PROVIDER": "configured",
                "MRA_ENTERPRISE_IDENTITY_VERIFIED": "1",
                "MRA_ENTERPRISE_HIS_ADAPTER": "configured",
                "MRA_ENTERPRISE_HIS_VERIFIED": "1",
                "MRA_ENTERPRISE_EMR_ADAPTER": "configured",
                "MRA_ENTERPRISE_EMR_VERIFIED": "1",
            }
        )

        payload = TestClient(app).get("/api/enterprise/capabilities").json()

        self.assertEqual(set(payload), set(CAPABILITY_NAMES))
        self.assertEqual(payload["identity_provider"], "verified")
        self.assertEqual(payload["his_adapter"], "verified")
        self.assertEqual(payload["emr_adapter"], "verified")


if __name__ == "__main__":
    unittest.main()
