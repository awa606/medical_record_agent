from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import require_current_user
from app.services.clinical_knowledge_base import (
    build_clinical_knowledge_base,
    list_clinical_references,
)


router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(require_current_user)],
)


@router.get("")
def read_clinical_knowledge_base() -> dict:
    return build_clinical_knowledge_base()


@router.get("/references")
def read_clinical_references() -> dict:
    return list_clinical_references()
