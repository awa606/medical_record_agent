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


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    name: str
    required_any: tuple[str, ...]
    supporting_any: tuple[str, ...]
    reason: str
    confidence: float
    suggested_checks: tuple[str, ...]
    medication_notes: tuple[str, ...]
    risk_warnings: tuple[str, ...]
    follow_up_questions: tuple[str, ...]


RULES = (
    RuleSpec(
        rule_id="R_WIND_COLD_001",
        name="感冒（风寒束表证）",
        required_any=("怕冷", "恶寒", "清涕", "清鼻涕", "无汗", "不出汗", "身痛", "全身酸痛"),
        supporting_any=("发热", "轻微发热", "鼻塞", "咳嗽"),
        reason="规则命中风寒相关症状，作为课程模拟知识库候选证候。",
        confidence=0.72,
        suggested_checks=(
            "复测体温并记录热型。",
            "医生查体补充咽部、鼻部、肺部听诊和舌脉情况。",
        ),
        medication_notes=(
            "治疗方向需医生确认并结合查体判断；系统不自动生成处方。",
        ),
        risk_warnings=(
            "若持续高热、胸痛、气促或精神状态异常，应由医生进一步评估。",
        ),
        follow_up_questions=(
            "是否明显怕冷或无汗？",
            "鼻涕颜色和咽痛程度如何？",
        ),
    ),
    RuleSpec(
        rule_id="R_WIND_HEAT_001",
        name="感冒（风热犯表证）",
        required_any=("咽痛", "嗓子疼", "嗓子痛", "黄涕", "鼻涕有点黄", "黄痰", "痰偏黄", "发热明显", "发热比较明显"),
        supporting_any=("咳嗽", "有点咳", "口渴", "头痛"),
        reason="规则命中风热相关症状，作为课程模拟知识库候选证候。",
        confidence=0.74,
        suggested_checks=(
            "复测体温并评估咽部充血、扁桃体和肺部情况。",
            "必要时由医生判断是否完善血常规、CRP 或病原学检查。",
        ),
        medication_notes=(
            "清热解表等治疗方向需医生确认；系统不自动生成处方。",
        ),
        risk_warnings=(
            "若高热不退、胸痛、气促或咳黄痰明显加重，需要医生复评感染风险。",
        ),
        follow_up_questions=(
            "咽痛是否明显？是否有黄涕或黄痰？",
            "是否伴随胸痛、气促或持续高热？",
        ),
    ),
    RuleSpec(
        rule_id="R_SUMMER_DAMP_001",
        name="感冒（暑湿困表证）",
        required_any=("暑湿", "身重", "胸闷", "恶心", "腹胀", "黏腻"),
        supporting_any=("发热", "头重", "乏力"),
        reason="规则命中暑湿相关症状，作为课程模拟知识库候选证候。",
        confidence=0.66,
        suggested_checks=("补充舌苔、脉象、体温和消化道症状评估。",),
        medication_notes=("具体治疗和用药必须由医生确认；系统不自动生成处方。",),
        risk_warnings=("若持续呕吐、脱水或意识异常，应及时由医生评估。",),
        follow_up_questions=("是否胸闷、恶心、腹胀或大便异常？",),
    ),
    RuleSpec(
        rule_id="R_QI_DEFICIENCY_001",
        name="感冒（气虚外感证）",
        required_any=("乏力", "气短", "容易出汗", "反复感冒", "自汗"),
        supporting_any=("发热", "怕风", "咳嗽"),
        reason="规则命中气虚相关症状，作为课程模拟知识库候选证候。",
        confidence=0.64,
        suggested_checks=("补充既往体质、舌脉、肺部听诊和基础疾病情况。",),
        medication_notes=("扶正解表等治疗方向需医生确认；系统不自动生成处方。",),
        risk_warnings=("若合并基础病或症状反复，应由医生评估进一步检查。",),
        follow_up_questions=("平时是否容易出汗、乏力或反复感冒？",),
    ),
)


def _read_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_common_cold_tables() -> dict[str, list[dict[str, Any]]]:
    """Load generated course KB tables when available.

    The v0.9 rule matcher below uses readable in-code rules as the stable
    product baseline. This loader is kept for documentation and future review.
    """

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
    effective_segments = segments or _split_segments(conversation)
    candidates: list[CandidateDiagnosis] = []
    for rule in RULES:
        required_hits = _hit_terms(conversation, rule.required_any)
        supporting_hits = _hit_terms(conversation, rule.supporting_any)
        if len(required_hits) < 2 and not (required_hits and supporting_hits):
            continue
        evidence = _evidence_spans(effective_segments, required_hits + supporting_hits, conversation)
        confidence = min(0.9, rule.confidence + 0.04 * max(0, len(required_hits) - 2))
        candidates.append(
            CandidateDiagnosis(
                name=rule.name,
                evidence=evidence,
                reason=f"{rule.reason} 命中症状：{'、'.join(required_hits + supporting_hits)}。",
                rule_id=rule.rule_id,
                confidence=round(confidence, 2),
                suggested_checks=list(rule.suggested_checks),
                medication_notes=list(rule.medication_notes),
                risk_warnings=list(rule.risk_warnings),
                follow_up_questions=list(rule.follow_up_questions),
            )
        )
    candidates.sort(key=lambda item: item.confidence or 0.0, reverse=True)
    return candidates[:3]


def _split_segments(conversation: str) -> list[str]:
    parts = re.split(r"[。！？!?\n]+", conversation)
    return [part.strip(" ，,") for part in parts if part.strip(" ，,")]


def _hit_terms(conversation: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in conversation]


def _evidence_spans(
    segments: list[str],
    terms: list[str],
    conversation: str,
) -> list[SourceSpan]:
    spans: list[SourceSpan] = []
    seen: set[tuple[int | None, str]] = set()
    for index, segment in enumerate(segments):
        if any(term in segment for term in terms):
            identity = (index, segment)
            if identity not in seen:
                seen.add(identity)
                spans.append(SourceSpan(index=index, text=segment))
    if not spans and conversation:
        spans.append(SourceSpan(index=None, text=conversation[:160]))
    return spans


__all__ = ["infer_common_cold_candidates", "load_common_cold_tables"]
