from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.schemas import CandidateDiagnosis, SourceSpan


PROJECT_ROOT = Path(__file__).resolve().parents[2]
KB_OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "kb"
COMBINED_KB_PATH = PROJECT_ROOT / "data" / "output" / "common_cold_kb.json"

EXTRA_SYNONYMS = {
    "SYM_MILD_FEVER": ["有点发热", "轻微发热", "发热较轻", "发热不厉害"],
    "SYM_HIGHER_FEVER": ["发热明显", "发热比较明显", "高热", "热得厉害"],
    "SYM_CHILLS": ["怕冷明显", "很怕冷"],
    "SYM_SLIGHT_CHILLS": ["有点怕风", "轻微怕冷"],
    "SYM_NO_SWEAT": ["没有汗", "无汗", "基本不出汗"],
    "SYM_CLEAR_NASAL_DISCHARGE": ["清涕", "流清涕", "清水鼻涕"],
    "SYM_YELLOW_NASAL_DISCHARGE": ["黄涕", "流黄涕", "鼻涕有点黄"],
    "SYM_BODY_ACHE": ["身痛", "全身痛", "身上痛"],
    "SYM_SORE_THROAT": ["嗓子疼", "嗓子痛", "喉咙痛"],
    "SYM_YELLOW_SPUTUM": ["痰偏黄", "黄痰", "咳黄痰"],
}

URGENT_WARNING_TERMS = ["高热", "胸痛", "气促", "呼吸困难", "意识不清", "持续发热"]


@dataclass(frozen=True)
class SymptomMatch:
    symptom_id: str
    symptom_name: str
    span: SourceSpan


def _read_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_common_cold_tables() -> dict[str, list[dict[str, Any]]]:
    """Load the generated course knowledge base without creating new files."""

    table_names = ["disease", "syndrome", "symptom", "question_template", "rule_base"]
    if all((KB_OUTPUT_DIR / f"{name}.json").exists() for name in table_names):
        return {
            name: _read_json(KB_OUTPUT_DIR / f"{name}.json")
            for name in table_names
        }

    if COMBINED_KB_PATH.exists():
        combined = json.loads(COMBINED_KB_PATH.read_text(encoding="utf-8"))
        return {
            name: list(combined.get(name, []))
            for name in table_names
        }

    return {name: [] for name in table_names}


def infer_common_cold_candidates(
    conversation: str,
    segments: list[str] | None = None,
) -> list[CandidateDiagnosis]:
    tables = load_common_cold_tables()
    symptoms_by_id = {item["symptom_id"]: item for item in tables["symptom"]}
    diseases_by_id = {item["disease_id"]: item for item in tables["disease"]}
    syndromes_by_id = {item["syndrome_id"]: item for item in tables["syndrome"]}
    questions = tables["question_template"]

    matches = _match_symptoms(conversation, segments or [], symptoms_by_id)
    if not matches:
        return []

    candidates = []
    for rule in tables["rule_base"]:
        candidate = _candidate_from_rule(
            rule,
            matches,
            symptoms_by_id=symptoms_by_id,
            diseases_by_id=diseases_by_id,
            syndromes_by_id=syndromes_by_id,
            questions=questions,
            conversation=conversation,
        )
        if candidate is not None:
            candidates.append(candidate)

    candidates.sort(key=lambda item: item.confidence or 0.0, reverse=True)
    return candidates[:3]


def _split_segments(conversation: str) -> list[str]:
    parts = re.split(r"[。！？?!\n]+", conversation)
    return [part.strip(" ；;，,") for part in parts if part.strip(" ；;，,")]


def _match_symptoms(
    conversation: str,
    segments: list[str],
    symptoms_by_id: dict[str, dict[str, Any]],
) -> dict[str, SymptomMatch]:
    effective_segments = segments or _split_segments(conversation) or [conversation]
    matches: dict[str, SymptomMatch] = {}

    for symptom_id, symptom in symptoms_by_id.items():
        terms = _terms_for_symptom(symptom)
        for term in terms:
            span = _find_span(term, conversation, effective_segments)
            if span is not None:
                matches[symptom_id] = SymptomMatch(
                    symptom_id=symptom_id,
                    symptom_name=str(symptom.get("symptom_name") or symptom_id),
                    span=span,
                )
                break

    return matches


def _terms_for_symptom(symptom: dict[str, Any]) -> list[str]:
    symptom_id = str(symptom.get("symptom_id"))
    raw_terms = [
        symptom.get("symptom_name"),
        symptom.get("normalized_value"),
        *symptom.get("synonyms", []),
        *EXTRA_SYNONYMS.get(symptom_id, []),
    ]
    terms = []
    for term in raw_terms:
        if isinstance(term, str) and term and term not in terms:
            terms.append(term)
    return terms


def _find_span(term: str, conversation: str, segments: list[str]) -> SourceSpan | None:
    for index, segment in enumerate(segments):
        if term in segment:
            return SourceSpan(index=index, text=segment)
    if term in conversation:
        return SourceSpan(index=None, text=conversation[:160])
    return None


def _candidate_from_rule(
    rule: dict[str, Any],
    matches: dict[str, SymptomMatch],
    *,
    symptoms_by_id: dict[str, dict[str, Any]],
    diseases_by_id: dict[str, dict[str, Any]],
    syndromes_by_id: dict[str, dict[str, Any]],
    questions: list[dict[str, Any]],
    conversation: str,
) -> CandidateDiagnosis | None:
    positive_ids = list(rule.get("positive_symptom_ids", []))
    negative_ids = list(rule.get("negative_symptom_ids", []))
    matched_positive = [symptom_id for symptom_id in positive_ids if symptom_id in matches]
    matched_negative = [symptom_id for symptom_id in negative_ids if symptom_id in matches]

    if len(matched_positive) < 2:
        return None

    positive_ratio = len(matched_positive) / max(len(positive_ids), 1)
    negative_penalty = 0.16 * len(matched_negative)
    base_weight = float(rule.get("weight") or 0.6)
    confidence = max(0.0, min(0.95, base_weight * positive_ratio - negative_penalty))
    if confidence < 0.3:
        return None

    disease = diseases_by_id.get(str(rule.get("disease_id")), {})
    syndrome = syndromes_by_id.get(str(rule.get("syndrome_id")), {})
    disease_name = str(disease.get("disease_name") or "感冒")
    syndrome_name = str(syndrome.get("syndrome_name") or rule.get("decision_hint") or "候选证候")
    matched_names = [
        str(symptoms_by_id.get(symptom_id, {}).get("symptom_name") or symptom_id)
        for symptom_id in matched_positive
    ]

    return CandidateDiagnosis(
        name=f"{disease_name}（{syndrome_name}）",
        evidence=_merge_spans([matches[symptom_id].span for symptom_id in matched_positive]),
        reason=_build_reason(rule, matched_names, matched_negative, symptoms_by_id),
        rule_id=str(rule.get("rule_id") or ""),
        confidence=round(confidence, 2),
        suggested_checks=_suggested_checks(syndrome),
        medication_notes=_medication_notes(syndrome),
        risk_warnings=_risk_warnings(conversation, disease, syndrome),
        follow_up_questions=_follow_up_questions(
            positive_ids,
            matched_positive,
            questions,
        ),
    )


def _merge_spans(spans: list[SourceSpan]) -> list[SourceSpan]:
    merged: list[SourceSpan] = []
    seen: set[tuple[int | None, str]] = set()
    for span in spans:
        key = (span.index, span.text)
        if key not in seen:
            seen.add(key)
            merged.append(span)
    return merged


def _build_reason(
    rule: dict[str, Any],
    matched_names: list[str],
    matched_negative: list[str],
    symptoms_by_id: dict[str, dict[str, Any]],
) -> str:
    reason = str(rule.get("explanation") or rule.get("decision_hint") or "规则命中")
    if matched_names:
        reason = f"{reason} 命中症状：{'、'.join(matched_names)}。"
    if matched_negative:
        negative_names = [
            str(symptoms_by_id.get(symptom_id, {}).get("symptom_name") or symptom_id)
            for symptom_id in matched_negative
        ]
        reason = f"{reason} 同时存在需医生复核的反向线索：{'、'.join(negative_names)}。"
    return reason


def _suggested_checks(syndrome: dict[str, Any]) -> list[str]:
    checks = [
        "复测体温并记录热型。",
        "医生查体补充咽部、鼻部、肺部听诊。",
        "必要时由医生判断是否完善血常规、CRP 或病原学检查。",
    ]
    tongue = syndrome.get("tongue")
    pulse = syndrome.get("pulse")
    if tongue or pulse:
        checks.append(f"补充舌象和脉象：{tongue or '待补充'}，{pulse or '待补充'}。")
    return checks


def _medication_notes(syndrome: dict[str, Any]) -> list[str]:
    principle = syndrome.get("treatment_principle")
    if principle:
        return [f"规则提示治法方向为“{principle}”，具体治疗和用药需医生确认；系统不自动处方。"]
    return ["具体治疗和用药需医生确认；系统不自动处方。"]


def _risk_warnings(
    conversation: str,
    disease: dict[str, Any],
    syndrome: dict[str, Any],
) -> list[str]:
    warnings = [
        str(syndrome.get("course_note") or disease.get("safety_note") or "仅模拟知识库，不用于真实诊疗。")
    ]
    if any(term in conversation for term in URGENT_WARNING_TERMS):
        warnings.append("如持续高热、气促、胸痛、意识异常等，应由医生进一步评估。")
    return warnings


def _follow_up_questions(
    positive_ids: list[str],
    matched_positive: list[str],
    questions: list[dict[str, Any]],
) -> list[str]:
    missing_ids = [symptom_id for symptom_id in positive_ids if symptom_id not in matched_positive]
    followups: list[str] = []
    for question in sorted(questions, key=lambda item: int(item.get("question_order") or 0)):
        mapped_ids = set(question.get("maps_to_symptom_ids", []))
        if not mapped_ids.intersection(missing_ids):
            continue
        question_text = str(question.get("question_text") or "")
        if question_text and question_text not in followups:
            followups.append(question_text)
        if len(followups) >= 3:
            break
    return followups


__all__ = ["infer_common_cold_candidates", "load_common_cold_tables"]
