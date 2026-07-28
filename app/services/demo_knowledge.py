from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KNOWLEDGE_ROOT = PROJECT_ROOT / "demo" / "knowledge"
ALLOWED_REVIEW_STATUSES = {"verified_demo", "unverified", "mock", "withdrawn"}


class DemoKnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    document_type: Literal["clinical_guideline"]
    year: int
    version: str = Field(min_length=1)
    review_status: Literal["verified_demo", "unverified", "mock", "withdrawn"]
    excerpt: str = Field(min_length=1)
    related_fields: list[str] = Field(min_length=1)
    citation_anchor: str = Field(min_length=1)
    source_url: str | None = None
    keywords: list[str] = Field(default_factory=list)

    def public_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["status_label"] = review_status_label(self.review_status)
        return payload


class DemoKnowledgeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    disclaimer: str = Field(min_length=1)
    sources: list[str] = Field(min_length=1)


def review_status_label(status: str) -> str:
    labels = {
        "verified_demo": "人工核验演示资料",
        "unverified": "来源待核验",
        "mock": "Mock 演示资料",
        "withdrawn": "资料已撤回，不作为当前参考",
    }
    return labels.get(status, "来源状态未知")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Knowledge file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Knowledge file is not valid JSON: {path}") from exc


def load_manifest(root: Path | None = None) -> DemoKnowledgeManifest:
    knowledge_root = root or DEFAULT_KNOWLEDGE_ROOT
    try:
        return DemoKnowledgeManifest.model_validate(_load_json(knowledge_root / "manifest.json"))
    except ValidationError as exc:
        raise ValueError(f"Knowledge manifest validation failed: {exc}") from exc


def load_sources(root: Path | None = None) -> list[DemoKnowledgeSource]:
    knowledge_root = root or DEFAULT_KNOWLEDGE_ROOT
    manifest = load_manifest(knowledge_root)
    seen: set[str] = set()
    sources: list[DemoKnowledgeSource] = []
    for relative_path in manifest.sources:
        source_path = (knowledge_root / relative_path).resolve()
        if knowledge_root.resolve() not in source_path.parents:
            raise ValueError(f"Knowledge source escapes manifest root: {relative_path}")
        try:
            source = DemoKnowledgeSource.model_validate(_load_json(source_path))
        except ValidationError as exc:
            raise ValueError(f"Knowledge source validation failed: {relative_path}: {exc}") from exc
        if source.review_status not in ALLOWED_REVIEW_STATUSES:
            raise ValueError(f"Knowledge source has invalid review_status: {source.source_id}")
        if source.source_id in seen:
            raise ValueError(f"Duplicate knowledge source_id: {source.source_id}")
        seen.add(source.source_id)
        sources.append(source)
    return sources


def get_source(source_id: str, root: Path | None = None) -> DemoKnowledgeSource | None:
    for source in load_sources(root):
        if source.source_id == source_id:
            return source
    return None


def retrieve_sources(
    *,
    query: str = "",
    related_fields: list[str] | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    normalized_query = query.lower()
    requested_fields = {field.strip() for field in related_fields or [] if field and field.strip()}
    results: list[dict[str, Any]] = []
    for source in load_sources(root):
        if source.review_status == "withdrawn":
            continue
        matched_fields = [field for field in source.related_fields if field in requested_fields]
        matched_keywords = [
            keyword
            for keyword in source.keywords
            if keyword and keyword.lower() in normalized_query
        ]
        if not matched_fields and not matched_keywords:
            continue
        reason_parts = []
        if matched_fields:
            reason_parts.append(f"关联字段：{'、'.join(matched_fields)}")
        if matched_keywords:
            reason_parts.append(f"命中关键词：{'、'.join(matched_keywords[:5])}")
        results.append(
            {
                **source.public_payload(),
                "matched_fields": matched_fields,
                "matched_keywords": matched_keywords,
                "match_reason": "；".join(reason_parts) or "确定性演示匹配",
            }
        )
    return results


def task_query_payload(task_result: dict[str, Any]) -> tuple[str, list[str]]:
    fields = task_result.get("fields") if isinstance(task_result, dict) else {}
    parts: list[str] = []
    related_fields: list[str] = []
    field_labels = {
        "chief_complaint": "主诉",
        "present_illness": "现病史",
        "accompanying_symptoms": "现病史",
        "candidate_diagnoses": "候选诊断（待医生确认）",
        "treatment_plan": "处理建议",
    }
    if isinstance(task_result, dict):
        for key in ("conversation_text", "draft"):
            value = task_result.get(key)
            if isinstance(value, str):
                parts.append(value)
    if isinstance(fields, dict):
        for key, field in fields.items():
            label = field_labels.get(key)
            if label and label not in related_fields:
                related_fields.append(label)
            if isinstance(field, dict):
                value = field.get("value") or field.get("hint")
                if isinstance(value, str):
                    parts.append(value)
            elif key == "candidate_diagnoses" and isinstance(field, list):
                for diagnosis in field:
                    if isinstance(diagnosis, dict):
                        parts.extend(
                            str(diagnosis.get(item) or "")
                            for item in ("name", "reason")
                        )
                        for list_key in ("risk_warnings", "suggested_checks", "follow_up_questions"):
                            values = diagnosis.get(list_key)
                            if isinstance(values, list):
                                parts.extend(str(item) for item in values)
    if "风险提示" not in related_fields:
        related_fields.append("风险提示")
    return "\n".join(part for part in parts if part), related_fields
