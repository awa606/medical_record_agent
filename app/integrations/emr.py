from __future__ import annotations

import hashlib
from typing import Protocol

from app.enterprise.contracts import EMRWritebackPayload, EMRWritebackReceipt, RequestContext


MOCK_EMR_CREATED_AT = "2026-01-01T00:00:00+00:00"
_MOCK_EMR_WRITES: list[EMRWritebackReceipt] = []


class EMRAdapter(Protocol):
    adapter_name: str

    def write_record(
        self,
        *,
        payload: EMRWritebackPayload,
        context: RequestContext,
    ) -> EMRWritebackReceipt:
        """Write an approved record through a mock EMR adapter."""


class MockEMRAdapter:
    adapter_name = "mock_emr"

    def write_record(
        self,
        *,
        payload: EMRWritebackPayload,
        context: RequestContext,
    ) -> EMRWritebackReceipt:
        digest = hashlib.sha256(
            f"{payload.task_id}:{payload.approval_id}:{payload.idempotency_key}".encode("utf-8")
        ).hexdigest()[:16]
        receipt = EMRWritebackReceipt(
            receipt_id=f"mock-emr-{digest}",
            task_id=payload.task_id,
            approval_id=payload.approval_id,
            revision_id=payload.revision_id,
            idempotency_key=payload.idempotency_key,
            created_at=MOCK_EMR_CREATED_AT,
        )
        _MOCK_EMR_WRITES.append(receipt)
        return receipt


def mock_emr_write_count() -> int:
    return len(_MOCK_EMR_WRITES)


def reset_mock_emr_writes() -> None:
    _MOCK_EMR_WRITES.clear()
