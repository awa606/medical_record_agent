from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.api.auth import require_admin, require_current_user
from app.api.tasks import _assert_task_access
from app.db import get_task
from app.schemas.auth import AuthenticatedUser
from app.services.demo_knowledge import (
    get_source,
    load_manifest,
    load_sources,
    retrieve_sources,
    task_query_payload,
)
from app.services.privacy import anonymize_text
from app.services.knowledge_store import (
    DEFAULT_DISCLAIMER,
    get_knowledge_source,
    get_knowledge_document,
    import_text_document,
    knowledge_health,
    knowledge_index_available,
    knowledge_index_configured,
    list_knowledge_documents,
    list_knowledge_sources,
    retrieve_knowledge as retrieve_indexed_knowledge,
    set_knowledge_document_active,
    update_knowledge_document_metadata,
)


router = APIRouter(tags=["knowledge"], dependencies=[Depends(require_current_user)])


class KnowledgeRetrieveRequest(BaseModel):
    task_id: int | None = None
    query: str = ""
    related_fields: list[str] = Field(default_factory=list)


class KnowledgeAdminImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    title: str = Field(min_length=1, max_length=300)
    publisher: str = Field(min_length=1, max_length=200)
    source_url: AnyHttpUrl
    download_url: AnyHttpUrl | None = None
    published_at: str | None = Field(default=None, max_length=40)
    effective_date: str | None = Field(default=None, max_length=40)
    version: str = Field(min_length=1, max_length=120)
    usage_scope: str = Field(min_length=1, max_length=500)
    document_type: str = Field(default="clinical-reference", min_length=1, max_length=80)
    disease_scope: str = Field(default="", max_length=300)
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class KnowledgeAdminPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    publisher: str | None = Field(default=None, min_length=1, max_length=200)
    source_url: AnyHttpUrl | None = None
    download_url: AnyHttpUrl | None = None
    published_at: str | None = Field(default=None, max_length=40)
    effective_date: str | None = Field(default=None, max_length=40)
    usage_scope: str | None = Field(default=None, min_length=1, max_length=500)
    document_type: str | None = Field(default=None, min_length=1, max_length=80)
    disease_scope: str | None = Field(default=None, max_length=300)
    original_filename: str | None = Field(default=None, max_length=255)


class KnowledgeAdminTestSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    document_id: str | None = Field(default=None, max_length=220)
    limit: int = Field(default=5, ge=1, le=20)


def _knowledge_unavailable(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "message": "Knowledge reference sources are unavailable.",
            "error": str(exc),
        },
    )


def _admin_document_not_found(document_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Knowledge document not found: {document_id}")


def _validate_admin_import(payload: KnowledgeAdminImportRequest) -> None:
    if len(payload.content.encode("utf-8")) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Knowledge document exceeds the 2 MiB import limit")
    filename = payload.filename.lower()
    if not filename.endswith((".txt", ".md", ".markdown")):
        raise HTTPException(status_code=415, detail="Only UTF-8 TXT and Markdown files are supported")


def _task_result_for_evidence(task_id: int, request: Request) -> tuple[dict[str, Any], dict[str, Any]]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_task_access(task, request)
    try:
        result = json.loads(task.get("result_json") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Task has invalid generated result") from exc
    if not isinstance(result, dict) or not result:
        raise HTTPException(status_code=400, detail="Task has no generated result for evidence retrieval")
    return task, result


@router.get("/knowledge/sources")
def read_knowledge_sources(_user: AuthenticatedUser = Depends(require_current_user)) -> dict[str, Any]:
    if knowledge_index_configured():
        sources = list_knowledge_sources()
        return {
            "version": "official-index-v1",
            "scope": "带来源版本、页码和内容哈希的本地官方资料索引。",
            "disclaimer": DEFAULT_DISCLAIMER,
            "sources": sources,
        }
    try:
        manifest = load_manifest()
        sources = load_sources()
    except ValueError as exc:
        raise _knowledge_unavailable(exc) from exc
    return {
        "version": manifest.version,
        "scope": manifest.scope,
        "disclaimer": manifest.disclaimer,
        "sources": [source.public_payload() for source in sources],
    }


@router.get("/knowledge/sources/{source_id}")
def read_knowledge_source(source_id: str, _user: AuthenticatedUser = Depends(require_current_user)) -> dict[str, Any]:
    if knowledge_index_configured():
        source = get_knowledge_source(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Knowledge source not found")
        return source
    try:
        source = get_source(source_id)
    except ValueError as exc:
        raise _knowledge_unavailable(exc) from exc
    if source is None:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    return source.public_payload()


@router.post("/knowledge/retrieve")
def retrieve_knowledge(payload: KnowledgeRetrieveRequest, request: Request) -> dict[str, Any]:
    query = payload.query
    related_fields = list(payload.related_fields)
    if payload.task_id is not None:
        _task, result = _task_result_for_evidence(payload.task_id, request)
        task_query, task_fields = task_query_payload(result)
        query = "\n".join(part for part in [query, task_query] if part)
        for field in task_fields:
            if field not in related_fields:
                related_fields.append(field)
    if knowledge_index_configured():
        indexed = retrieve_indexed_knowledge(anonymize_text("\n".join([query, *related_fields]).strip()))
        results = indexed["results"]
        retrieval_mode = indexed["retrieval_mode"]
        disclaimer = DEFAULT_DISCLAIMER
    else:
        try:
            results = retrieve_sources(query=anonymize_text(query), related_fields=related_fields)
        except ValueError as exc:
            raise _knowledge_unavailable(exc) from exc
        retrieval_mode = "deterministic_demo"
        disclaimer = "相关知识参考仅用于人工核验演示，不作为自动诊断或治疗建议。"
    return {
        "query": payload.query,
        "related_fields": related_fields,
        "results": results,
        "count": len(results),
        "retrieval_mode": retrieval_mode,
        "disclaimer": disclaimer,
    }


@router.get("/tasks/{task_id}/evidence")
def read_task_evidence(task_id: int, request: Request) -> dict[str, Any]:
    task, result = _task_result_for_evidence(task_id, request)
    query, related_fields = task_query_payload(result)
    if knowledge_index_configured():
        indexed = retrieve_indexed_knowledge(anonymize_text("\n".join([query, *related_fields]).strip()))
        results = indexed["results"]
        retrieval_mode = indexed["retrieval_mode"]
        disclaimer = DEFAULT_DISCLAIMER
    else:
        try:
            results = retrieve_sources(query=anonymize_text(query), related_fields=related_fields)
        except ValueError as exc:
            raise _knowledge_unavailable(exc) from exc
        retrieval_mode = "deterministic_demo"
        disclaimer = "相关知识参考仅用于人工核验演示，不参与审核、revision 或导出门禁。"
    return {
        "task_id": task_id,
        "revision_id": task.get("current_record_revision_id"),
        "related_fields": related_fields,
        "results": results,
        "count": len(results),
        "retrieval_mode": retrieval_mode,
        "disclaimer": disclaimer,
    }


@router.get("/knowledge/admin/documents")
def read_admin_knowledge_documents(_admin: AuthenticatedUser = Depends(require_admin)) -> dict[str, Any]:
    documents = list_knowledge_documents()
    return {"documents": documents, "count": len(documents)}


@router.get("/knowledge/admin/documents/{document_id}")
def read_admin_knowledge_document(
    document_id: str,
    _admin: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    document = get_knowledge_document(document_id)
    if document is None:
        raise _admin_document_not_found(document_id)
    return document


@router.post("/knowledge/admin/import", status_code=status.HTTP_201_CREATED)
def import_admin_knowledge_document(
    payload: KnowledgeAdminImportRequest,
    admin: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    _validate_admin_import(payload)
    try:
        result = import_text_document(
            source={
                "source_id": payload.source_id,
                "title": payload.title,
                "publisher": payload.publisher,
                "source_url": str(payload.source_url),
                "download_url": str(payload.download_url) if payload.download_url else None,
                "published_at": payload.published_at,
                "effective_date": payload.effective_date,
                "version": payload.version,
                "usage_scope": payload.usage_scope,
                "document_type": payload.document_type,
                "disease_scope": payload.disease_scope,
            },
            filename=payload.filename,
            content=payload.content,
            actor_user_id=admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**result, "activation_required": True}


@router.patch("/knowledge/admin/documents/{document_id}")
def patch_admin_knowledge_document(
    document_id: str,
    payload: KnowledgeAdminPatchRequest,
    admin: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    metadata = {
        key: (str(value) if isinstance(value, AnyHttpUrl) else value)
        for key, value in payload.model_dump(exclude_unset=True).items()
    }
    try:
        return update_knowledge_document_metadata(document_id, metadata=metadata, actor_user_id=admin.id)
    except KeyError as exc:
        raise _admin_document_not_found(document_id) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/knowledge/admin/documents/{document_id}/enable")
def enable_admin_knowledge_document(
    document_id: str,
    admin: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return set_knowledge_document_active(document_id, active=True, actor_user_id=admin.id)
    except KeyError as exc:
        raise _admin_document_not_found(document_id) from exc


@router.post("/knowledge/admin/documents/{document_id}/disable")
def disable_admin_knowledge_document(
    document_id: str,
    admin: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return set_knowledge_document_active(document_id, active=False, actor_user_id=admin.id)
    except KeyError as exc:
        raise _admin_document_not_found(document_id) from exc


@router.get("/knowledge/admin/health")
def read_admin_knowledge_health(_admin: AuthenticatedUser = Depends(require_admin)) -> dict[str, Any]:
    return knowledge_health()


@router.post("/knowledge/admin/test-search")
def test_admin_knowledge_search(
    payload: KnowledgeAdminTestSearchRequest,
    _admin: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    if payload.document_id and get_knowledge_document(payload.document_id) is None:
        raise _admin_document_not_found(payload.document_id)
    result = retrieve_indexed_knowledge(
        anonymize_text(payload.query),
        limit=payload.limit,
        document_id=payload.document_id,
        include_inactive=True,
    )
    return {
        "query": payload.query,
        "document_id": payload.document_id,
        "results": result["results"],
        "count": len(result["results"]),
        "retrieval_mode": result["retrieval_mode"],
        "administrative_test_only": True,
        "disclaimer": DEFAULT_DISCLAIMER,
    }
