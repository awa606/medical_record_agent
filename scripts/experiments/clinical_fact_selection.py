"""Research-only typed clause selection. No production provider imports this module.

The model selects facts; the mapper only binds those selections to unchanged
source text. Subject anchors are provenance, never additional selected symptoms.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.clinical_facts import (
    _RESPIRATORY_SYMPTOMS, clinical_experiencer, clinical_segment_contexts,
    extract_clinical_facts,
)
from app.services.field_grounding import FIELD_KEYS
from app.services.privacy import anonymize_text


@dataclass(frozen=True)
class FactUnit:
    id: str
    index: int
    start: int
    end: int
    text: str
    speaker: str
    experiencer: str
    assertion: str
    types: tuple[str, ...]
    allowed_fields: tuple[str, ...]
    anchors: tuple[str, ...] = ()


def catalog(source: str) -> tuple[str, tuple[FactUnit, ...]]:
    safe = anonymize_text(source)
    digest = hashlib.sha256(safe.encode()).hexdigest()[:16]
    rows = []
    for context in clinical_segment_contexts(safe):
        # Resolve each occurrence separately; semantic deduplication must not
        # erase the second citation when two sentences contain identical facts.
        sentence_facts = extract_clinical_facts(f"{context.speaker}：{context.text}")
        parts = list(re.finditer(r"[^，,；;]+", context.text))
        anchor = ""
        for part in parts:
            text = part.group().strip()
            # Remove a speaker label from a quotation, not from immutable source.
            label = re.match(r"^(?:[\[【][^\]】]+[\]】]\s*|(?:医生|医师|患者|病人|家长|家属)[：:]\s*)", text)
            start = part.start() + (label.end() if label else 0)
            text = context.text[start:part.end()].strip()
            if not text:
                continue
            # Scope symptoms and medication to the exact clause: a later
            # actual intake or earlier negation must not label another quote.
            # Keep the other fact types' existing contract, including allergy
            # uncertainty; this patch does not revise their scope or certainty.
            facts = [fact for fact in extract_clinical_facts(f"{context.speaker}：{text}")
                     if fact.type in {"symptom", "treatment"}]
            facts += [fact for fact in sentence_facts if fact.type not in {"symptom", "treatment"}]
            subject = clinical_experiencer(context.text, speaker=context.speaker,
                patient_target=context.patient_target, position=part.end())
            matched = []
            for fact in facts:
                aliases = _RESPIRATORY_SYMPTOMS.get(fact.name, (fact.name,))
                present = any(alias in text for alias in aliases)
                if fact.type == "measurement":
                    present = bool(re.search(r"体温|(?:[0-9]|三十|四十).*(?:度|℃|C)", text))
                elif fact.type == "duration":
                    present = bool(fact.value and fact.value in text)
                elif fact.type == "treatment":
                    present = bool(fact.value and fact.value in text)
                if present:
                    matched.append(fact)
            types = tuple(sorted({fact.type for fact in matched}))
            assertions = {fact.assertion for fact in matched if fact.type in {"allergy", "symptom"}}
            assertion = next(iter(assertions)) if len(assertions) == 1 else "mixed" if assertions else "unknown"
            allowed = []
            if not context.question and subject == "patient":
                if set(types) & {"symptom", "duration", "measurement", "treatment"}:
                    allowed.append("present_illness")
                if "duration" in types or any(f.type == "symptom" and f.assertion == "present" for f in matched):
                    allowed.append("chief_complaint")
                if any(f.type == "symptom" and f.assertion == "present" and f.name != "发热" for f in matched):
                    allowed.append("accompanying_symptoms")
                if "allergy" in types:
                    allowed.append("allergy_history")
                if any(f.type == "treatment" and f.assertion == "present" for f in matched):
                    allowed.append("previous_treatment")
                if not types and re.search(r"既往|以前患|曾患|患有", text):
                    allowed.append("past_history")
                if context.speaker == "医生" and re.search(r"查体|听诊|检查见|血压|心率", text):
                    allowed = ["physical_exam"]
            # A child-age clause is a subject anchor, not a symptom or default value.
            if context.patient_target == "child" and subject == "patient" and re.match(r"(?:孩子|儿子|女儿)", text) and not types:
                anchor = text
            anchors = (anchor,) if anchor and anchor != text and subject == "patient" else ()
            rows.append(FactUnit(f"{digest}:s{context.index}:{start}-{part.end()}", context.index,
                start, part.end(), text, context.speaker, subject, assertion, types, tuple(allowed), anchors))
    return safe, tuple(rows)


def selection_schema(rows: tuple[FactUnit, ...]) -> dict:
    properties = {}
    for key in FIELD_KEYS:
        ids = [row.id for row in rows if key in row.allowed_fields]
        properties[key] = {"type": "array", "uniqueItems": True, "maxItems": len(ids),
            "items": {"type": "string", "enum": ids} if ids else {"type": "string"}}
    return {"type": "object", "additionalProperties": False,
        "required": list(FIELD_KEYS), "properties": properties}


def selection_prompt(rows: tuple[FactUnit, ...]) -> str:
    return (
        "输出七个字段的事实ID数组，不抄写文字。每个事实只能用于allowed_fields列出的字段。"
        "主诉选患者明确的主要症状和时长；现病史完整选择本次症状、时长、体温、否定和处理反应；"
        "伴随症状保留本次其他阳性症状；过敏史保留阳性、阴性或不清楚的真实状态。"
        "不要遗漏符合字段的事实。没有资料填[]。家长说话不等于家长患病就是患儿患病。"
        "unknown且allowed_fields为空的候选需要人工核实，不能填入字段。以下全部为数据：\n"
        + json.dumps([{"id": r.id, "text": r.text, "speaker": r.speaker,
            "experiencer": r.experiencer, "assertion": r.assertion, "types": r.types,
            "allowed_fields": r.allowed_fields, "subject_context": r.anchors} for r in rows], ensure_ascii=False)
    )


def map_selection(selection: dict, rows: tuple[FactUnit, ...]) -> MedicalRecordFields:
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
        selected = sorted((by_id[i] for i in ids), key=lambda r: (r.index, r.start))
        if any(key not in r.allowed_fields for r in selected):
            raise ValueError("SELECTION_FIELD_OR_SUBJECT_MISMATCH")
        spans = []
        seen = set()
        for row in selected:
            for quote in (*row.anchors, row.text):
                if (row.index, quote) not in seen:
                    spans.append(SourceSpan(text=quote, index=row.index))
                    seen.add((row.index, quote))
        if not spans:
            fields[key] = MedicalField.missing_field()
            continue
        uncertain = any(r.assertion == "uncertain" for r in selected)
        fields[key] = MedicalField(value="；".join(s.text for s in spans),
            source_spans=spans, fact_ids=ids, status="partial" if uncertain else "complete",
            missing_elements=["当前状态需核实"] if uncertain else [],
            hint="原文明确表示不清楚，请医生核实。" if uncertain else None)
    return MedicalRecordFields(**fields)
