"""从问答标题和问题中构造伪病历字段。

这些字段只是规则生成的 pseudo_fields，用于课程项目的字段抽取测试和人工
标注预填，不作为医学真值或诊断依据。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.dataset_pipeline.jsonl import read_jsonl, write_jsonl
from app.dataset_pipeline.paths import PROCESSED_DIR, ensure_pipeline_dirs


SYMPTOM_PATTERNS = {
    "发热": r"发热|发烧|低烧|高烧|体温",
    "咳嗽": r"咳嗽|咳",
    "鼻塞": r"鼻塞",
    "流涕": r"流涕|流鼻涕|鼻涕",
    "咽痛": r"咽痛|嗓子疼|喉咙痛|咽喉痛",
    "怕冷": r"怕冷|恶寒|畏寒|发冷",
    "头痛": r"头痛|头疼",
    "乏力": r"乏力|没劲|无力",
    "咳痰": r"咳痰|有痰|黄痰|白痰",
}

NEGATIVE_PATTERNS = {
    "无发热": r"不发热|没有发热|没发烧|不发烧",
    "无咳嗽": r"不咳嗽|没有咳嗽|没咳嗽",
    "无流涕": r"不流鼻涕|没有鼻涕|没鼻涕",
}

HISTORY_PATTERN = re.compile(r"(高血压|糖尿病|哮喘|鼻炎|支气管炎|肺炎|过敏性鼻炎)")
MED_PATTERN = re.compile(r"(吃了|服用|口服|用了|喝了)([^。；，,\n]{1,18})")
ALLERGY_PATTERN = re.compile(r"(过敏史|药物过敏|青霉素过敏|头孢过敏)")
DURATION_PATTERN = re.compile(r"(\d+\s*(?:天|日|周|个月|年|小时)|半个月|一周|两天|三天|昨天|前天|今天|最近|近段时间)")


def _evidence(text: str, pattern: str | re.Pattern[str]) -> list[str]:
    """返回命中的原文证据片段，最多保留 5 条。"""

    regex = re.compile(pattern) if isinstance(pattern, str) else pattern
    snippets: list[str] = []
    for match in regex.finditer(text):
        start = max(0, match.start() - 12)
        end = min(len(text), match.end() + 12)
        snippet = text[start:end].strip()
        if snippet and snippet not in snippets:
            snippets.append(snippet)
        if len(snippets) >= 5:
            break
    return snippets


def _field(value: Any, evidence_text: list[str], hint: str = "由规则抽取，建议人工复核") -> dict[str, Any]:
    """统一 pseudo_fields 字段结构。"""

    missing = value in (None, "", [], {})
    return {
        "value": None if missing else value,
        "missing": missing,
        "hint": "建议补充标注" if missing else hint,
        "evidence_text": evidence_text,
    }


def extract_pseudo_fields(record: dict[str, Any]) -> dict[str, Any]:
    """从 title/question 中抽取伪病历字段。"""

    title = record.get("title") or ""
    question = record.get("question") or ""
    text = f"{title}。{question}".strip("。")

    symptoms = []
    symptom_evidence: list[str] = []
    for symptom, pattern in SYMPTOM_PATTERNS.items():
        evidence = _evidence(text, pattern)
        if evidence:
            symptoms.append(symptom)
            symptom_evidence.extend(evidence)

    negative_symptoms = []
    negative_evidence: list[str] = []
    for symptom, pattern in NEGATIVE_PATTERNS.items():
        evidence = _evidence(text, pattern)
        if evidence:
            negative_symptoms.append(symptom)
            negative_evidence.extend(evidence)

    duration_evidence = _evidence(text, DURATION_PATTERN)
    history_evidence = _evidence(text, HISTORY_PATTERN)
    med_evidence = _evidence(text, MED_PATTERN)
    allergy_evidence = _evidence(text, ALLERGY_PATTERN)

    missing_items = []
    if not allergy_evidence:
        missing_items.append("过敏史")
    if not history_evidence:
        missing_items.append("既往史")
    missing_items.extend(["查体", "舌象", "脉象"])

    return {
        "chief_complaint": _field(title or None, [title] if title else []),
        "present_illness": _field(question or None, [question] if question else []),
        "symptoms": _field(symptoms, symptom_evidence),
        "duration": _field(duration_evidence[0] if duration_evidence else None, duration_evidence),
        "accompanying_symptoms": _field(symptoms[1:] if len(symptoms) > 1 else [], symptom_evidence[1:]),
        "negative_symptoms": _field(negative_symptoms, negative_evidence),
        "past_history": _field(history_evidence, history_evidence),
        "medication_history": _field(med_evidence, med_evidence),
        "allergy_history": _field(allergy_evidence, allergy_evidence),
        "items_to_complete": _field(missing_items, missing_items, hint="规则提示的待补充项"),
    }


def build_pseudo_emr_dataset(
    input_path: Path = PROCESSED_DIR / "toyhom_cold_candidates.jsonl",
    output_path: Path = PROCESSED_DIR / "pseudo_emr_cases.jsonl",
) -> int:
    """为候选数据生成 pseudo_fields。"""

    ensure_pipeline_dirs()
    records = []
    for record in read_jsonl(input_path):
        enriched = dict(record)
        enriched["pseudo_fields"] = extract_pseudo_fields(record)
        enriched["pseudo_notice"] = "pseudo_fields 为规则生成，不作为人工真值或自动诊断依据。"
        records.append(enriched)
    return write_jsonl(output_path, records)
