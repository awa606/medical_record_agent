from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.auth import require_current_user
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
from app.services.knowledge_store import (
    DEFAULT_DISCLAIMER,
    get_knowledge_source,
    knowledge_index_available,
    list_knowledge_sources,
    retrieve_knowledge as retrieve_indexed_knowledge,
)


router = APIRouter(tags=["knowledge"], dependencies=[Depends(require_current_user)])


class KnowledgeRetrieveRequest(BaseModel):
    task_id: int | None = None
    query: str = ""
    related_fields: list[str] = Field(default_factory=list)


def _knowledge_unavailable(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "message": "Knowledge reference sources are unavailable.",
            "error": str(exc),
        },
    )


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
    if knowledge_index_available():
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
    if knowledge_index_available():
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
    if knowledge_index_available():
        indexed = retrieve_indexed_knowledge("\n".join([query, *related_fields]).strip())
        results = indexed["results"]
        retrieval_mode = indexed["retrieval_mode"]
        disclaimer = DEFAULT_DISCLAIMER
    else:
        try:
            results = retrieve_sources(query=query, related_fields=related_fields)
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
    if knowledge_index_available():
        indexed = retrieve_indexed_knowledge("\n".join([query, *related_fields]).strip())
        results = indexed["results"]
        retrieval_mode = indexed["retrieval_mode"]
        disclaimer = DEFAULT_DISCLAIMER
    else:
        try:
            results = retrieve_sources(query=query, related_fields=related_fields)
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
