from __future__ import annotations

from typing import Protocol

from app.enterprise.contracts import HISPatientSummary, RequestContext


class HISAdapter(Protocol):
    adapter_name: str

    def lookup_patient(
        self,
        *,
        deidentified_patient_id: str,
        context: RequestContext,
    ) -> HISPatientSummary:
        """Lookup a deidentified patient in a mock HIS adapter."""


class MockHISAdapter:
    adapter_name = "mock_his"

    def lookup_patient(
        self,
        *,
        deidentified_patient_id: str,
        context: RequestContext,
    ) -> HISPatientSummary:
        return HISPatientSummary(
            deidentified_patient_id=deidentified_patient_id,
            organization_id=context.organization_id,
            department_id=context.department_id,
            source="mock_his",
            status="found",
        )
