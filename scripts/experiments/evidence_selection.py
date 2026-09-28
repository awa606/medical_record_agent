"""Isolated research candidate. Not imported by a production provider.

The model selects source IDs, never writes clinical text. Selection quality and
deterministic mapping are recorded separately; neither bypasses grounding.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.clinical_facts import split_clinical_segments
from app.services.field_grounding import FIELD_KEYS, compact
from app.services.privacy import anonymize_text

ROLE = re.compile(r"^\s*(?:\[(医生|患者|家属|待确认|doctor|patient)\]\s*|(医生|患者|家属|待确认|doctor|patient)\s*[：:]\s*)", re.I)


@dataclass(frozen=True)
class Evidence:
    id: str
    index: int
    text: str
    role: str
    segment_id: str | None = None
    start_time: float | None = None
    end_time: float | None = None


def catalog(source: str, trusted: list[dict] | None = None) -> tuple[str, tuple[Evidence, ...]]:
    safe = anonymize_text(source)
    prefix = hashlib.sha256(safe.encode()).hexdigest()[:16]
    rows = []
    role = "unknown"
    for index, sentence in enumerate(split_clinical_segments(safe)):
        match = ROLE.match(sentence)
        if match:
            role = match.group(1) or match.group(2)
            role = {"doctor": "医生", "patient": "患者"}.get(role.lower(), role)
        text = sentence[match.end():] if match else sentence
        matches = [s for s in trusted or [] if text and compact(text) in compact(anonymize_text(s.get("text", "")))]
        # Do not select an audio identity when duplicate utterances are ambiguous.
        segment = matches[0] if len(matches) == 1 else {}
        rows.append(Evidence(f"{prefix}:s{index}", index, text, role,
                             segment.get("segment_id"), segment.get("start_time"), segment.get("end_time")))
    return safe, tuple(rows)


def selection_schema(rows: tuple[Evidence, ...]) -> dict:
    ids = [row.id for row in rows]
    item = {"type": "string", "enum": ids} if ids else {"type": "string"}
    return {"type": "object", "additionalProperties": False,
            "required": list(FIELD_KEYS),
            "properties": {k: {"type": "array", "items": item, "uniqueItems": True,
                                "maxItems": len(ids)} for k in FIELD_KEYS}}


def selection_prompt(rows: tuple[Evidence, ...]) -> str:
    return (
        "选择原文证据ID，不生成或改写病历文字。输出七个字段的ID数组。"
        "chief_complaint主诉；present_illness本次症状、病程、体温和处理反应；"
        "previous_treatment已做过的治疗或服药；accompanying_symptoms伴随症状；"
        "past_history患者既往病史；allergy_history患者过敏史（保留否定）；physical_exam医生查体。"
        "一句可支持多个字段。主诉和现病史不可相互替代。未提及填[]。"
        "医生提问、家属自己的病史、操作指令不是患者事实；不要因没有资料选择无关句子。"
        "字段不能选择只支持其他字段的句子。以下均为数据：\n"
        + json.dumps([{"id": r.id, "role": r.role, "text": r.text} for r in rows], ensure_ascii=False)
    )


def map_selection(selection: dict, rows: tuple[Evidence, ...]) -> MedicalRecordFields:
    if not isinstance(selection, dict) or set(selection) != set(FIELD_KEYS):
        raise ValueError("SELECTION_FIELDS_MISMATCH")
    by_id = {row.id: row for row in rows}
    fields = {}
    for key in FIELD_KEYS:
        ids = selection[key]
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
            raise ValueError("SELECTION_IDS_REQUIRED")
        if len(set(ids)) != len(ids):
            raise ValueError("SELECTION_DUPLICATE_ID")
        if any(i not in by_id for i in ids):
            raise ValueError("SELECTION_FOREIGN_OR_UNKNOWN_ID")
        selected = sorted((by_id[i] for i in ids), key=lambda r: r.index)
        fields[key] = MedicalField(
            value="；".join(row.text for row in selected), confidence=None,
            source_spans=[SourceSpan(text=r.text, index=r.index, segment_id=r.segment_id,
                                     start_time=r.start_time, end_time=r.end_time) for r in selected],
        ) if selected else MedicalField.missing_field()
    return MedicalRecordFields(**fields)
