from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.auth import require_admin
from app.db import list_audit_chain_entries
from app.schemas.auth import AuthenticatedUser
from app.services.audit_anchor import verify_with_anchor


router = APIRouter(
    prefix="/security",
    tags=["security"],
    dependencies=[Depends(require_admin)],
)


@router.get("/audit-chain")
def read_audit_chain(
    limit: int = Query(default=50, ge=1, le=500),
    _admin: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    """Verification result plus the most recent hash-chained events.

    Verification also checks the latest external anchor when one exists, which
    is what detects a tail truncation the chain alone cannot notice.
    """
    return {
        "verification": verify_with_anchor(),
        "entries": list_audit_chain_entries(limit=limit),
    }


@router.get("/audit-chain/verify")
def verify(
    _admin: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    return verify_with_anchor()
