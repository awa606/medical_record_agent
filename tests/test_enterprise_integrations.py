from __future__ import annotations

import json
import unittest

from app.enterprise.audit import REDACTED, build_audit_event, redact_sensitive_fields
from app.enterprise.config import EnterpriseConfig
from app.enterprise.contracts import EMRWritebackPayload, RequestContext
from app.integrations import REAL_HOSPITAL_ADAPTERS
from app.integrations.emr import MockEMRAdapter, mock_emr_write_count, reset_mock_emr_writes
from app.integrations.factory import AdapterUnavailableError, create_emr_adapter
from app.integrations.his import MockHISAdapter
from app.integrations.identity import LocalIdentityProvider, MockOIDCIdentityProvider


class EnterpriseIntegrationContractTests(unittest.TestCase):
    def setUp(self):
        reset_mock_emr_writes()
        self.context = RequestContext(
            request_id="req-1",
            correlation_id="corr-1",
            actor_user_id=7,
            actor_role="doctor",
            organization_id="org-1",
            department_id="dept-1",
        )

    def test_local_identity_provider_contract(self):
        result = LocalIdentityProvider().authenticate(
            {
                "username": "doctor-a",
                "user_id": 7,
                "organization_id": "org-1",
                "department_ids": ["dept-1"],
            }
        )

        self.assertEqual(result.status, "authenticated")
        self.assertEqual(result.provider, "local")
        self.assertEqual(result.principal.subject, "local:7")
        self.assertEqual(result.principal.department_ids, ["dept-1"])

    def test_mock_oidc_provider_does_not_return_token_claim(self):
        accepted = MockOIDCIdentityProvider().authenticate({"token": "mock-valid-token"})
        rejected = MockOIDCIdentityProvider().authenticate({"token": "bad-token"})

        self.assertEqual(accepted.status, "authenticated")
        self.assertEqual(accepted.principal.claims["iss"], "mock-oidc")
        self.assertNotIn("token", accepted.principal.claims)
        self.assertEqual(rejected.status, "rejected")

    def test_mock_his_and_emr_contracts_are_deterministic(self):
        patient = MockHISAdapter().lookup_patient(
            deidentified_patient_id="SIM-000001",
            context=self.context,
        )
        self.assertEqual(patient.source, "mock_his")
        self.assertEqual(patient.deidentified_patient_id, "SIM-000001")

        payload = EMRWritebackPayload(
            task_id=1,
            approval_id=2,
            revision_id=3,
            idempotency_key="idem-1",
            record_hash="abc123",
            organization_id="org-1",
            department_id="dept-1",
        )
        receipt = MockEMRAdapter().write_record(payload=payload, context=self.context)

        self.assertEqual(receipt.adapter, "mock_emr")
        self.assertEqual(receipt.status, "accepted")
        self.assertEqual(receipt.receipt_id, "mock-emr-97eadac9c658d39d")
        self.assertEqual(mock_emr_write_count(), 1)

    def test_configured_real_adapter_is_not_fabricated(self):
        self.assertEqual(REAL_HOSPITAL_ADAPTERS, ())

        with self.assertRaises(AdapterUnavailableError):
            create_emr_adapter(EnterpriseConfig(enabled=True, emr_adapter="configured", emr_verified=True))

    def test_audit_redaction_removes_sensitive_fields(self):
        raw = {
            "token": "token-value",
            "password": "password-value",
            "authorization": "Bearer secret",
            "api_key": "api-key-value",
            "patient_name": "Patient Name",
            "patient": {"name": "Nested Patient", "text": "Nested text", "id": "SIM-1"},
            "draft": "draft text",
            "conversation_text": "conversation text",
            "safe_field": "kept",
        }

        redacted = redact_sensitive_fields(raw)
        event = build_audit_event(
            event_type="test_event",
            capability="audit_events",
            outcome="blocked",
            context=self.context,
            task_id=1,
            details=raw,
        )
        serialized = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)

        self.assertEqual(redacted["token"], REDACTED)
        self.assertEqual(redacted["patient"]["name"], REDACTED)
        self.assertEqual(redacted["patient"]["text"], REDACTED)
        self.assertEqual(redacted["patient"]["id"], "SIM-1")
        self.assertEqual(redacted["safe_field"], "kept")
        for secret in [
            "token-value",
            "password-value",
            "Bearer secret",
            "api-key-value",
            "Patient Name",
            "draft text",
            "conversation text",
        ]:
            self.assertNotIn(secret, serialized)


if __name__ == "__main__":
    unittest.main()
