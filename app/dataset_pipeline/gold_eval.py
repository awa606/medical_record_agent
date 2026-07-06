"""基于人工 gold set 的字段抽取评估。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents import MedicalRecordOrchestrator
from app.dataset_pipeline.jsonl import read_jsonl
from app.dataset_pipeline.paths import ANNOTATION_DIR, OUTPUT_DIR, ensure_pipeline_dirs


FIELD_MAP = {
    "chief_complaint": "chief_complaint",
    "present_illness": "present_illness",
    "previous_treatment": "medication_history",
    "accompanying_symptoms": "accompanying_symptoms",
    "past_history": "past_history",
    "allergy_history": "allergy_history",
    "physical_exam": "items_to_complete",
}


def _has_value(value: Any) -> bool:
    """判断字段是否有有效值。"""

    if isinstance(value, dict):
        if value.get("missing") is True:
            return False
        return _has_value(value.get("value"))
    return value not in (None, "", [], {})


def _text_of(value: Any) -> str:
    """把字段值转成可比较文本。"""

    if isinstance(value, dict):
        return _text_of(value.get("value"))
    if isinstance(value, list):
        return " ".join(_text_of(item) for item in value)
    return str(value or "")


def _gold_fields(record: dict[str, Any]) -> dict[str, Any]:
    """兼容 gold_fields 和 pseudo_fields 两种输入，测试时可用伪字段兜底。"""

    return record.get("gold_fields") or record.get("pseudo_fields") or {}


def _predict_fields(record: dict[str, Any]) -> dict[str, Any]:
    """调用现有 MedicalRecordOrchestrator 生成字段抽取结果。"""

    conversation_text = f"医生：这次主要哪里不舒服？\n患者：{record.get('title', '')}。{record.get('question', '')}"
    result = MedicalRecordOrchestrator().run_from_text(conversation_text)
    fields = result["fields"]
    return fields.model_dump() if fields else {}


def evaluate_gold_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """计算 Precision、Recall、F1、字段完整率、证据命中率和幻觉率。"""

    true_positive = false_positive = false_negative = 0
    completed_fields = total_fields = 0
    evidence_hits = evidence_total = 0
    hallucinated = predicted_total = 0

    case_reports = []
    for record in records:
        gold = _gold_fields(record)
        predicted = _predict_fields(record)
        source_text = f"{record.get('title', '')} {record.get('question', '')}"

        case_tp = case_fp = case_fn = 0
        for predicted_key, gold_key in FIELD_MAP.items():
            gold_value = gold.get(gold_key)
            predicted_value = predicted.get(predicted_key)
            gold_has = _has_value(gold_value)
            predicted_has = _has_value(predicted_value)

            total_fields += 1
            if predicted_has:
                completed_fields += 1
                predicted_total += 1
                predicted_text = _text_of(predicted_value)
                if predicted_text and predicted_text in source_text:
                    evidence_hits += 1
                elif predicted_text:
                    hallucinated += 1
                evidence_total += 1

            if gold_has and predicted_has:
                true_positive += 1
                case_tp += 1
            elif predicted_has and not gold_has:
                false_positive += 1
                case_fp += 1
            elif gold_has and not predicted_has:
                false_negative += 1
                case_fn += 1

        case_reports.append(
            {
                "case_id": record.get("case_id"),
                "true_positive": case_tp,
                "false_positive": case_fp,
                "false_negative": case_fn,
            }
        )

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "aggregate": {
            "case_count": len(records),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "field_completeness": round(completed_fields / total_fields, 4) if total_fields else 0.0,
            "evidence_hit_rate": round(evidence_hits / evidence_total, 4) if evidence_total else 0.0,
            "hallucination_rate": round(hallucinated / predicted_total, 4) if predicted_total else 0.0,
        },
        "cases": case_reports,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    """渲染 Markdown 报告，便于课程项目展示。"""

    agg = report["aggregate"]
    lines = [
        "# Toyhom Gold Set 字段抽取评估报告",
        "",
        f"- 病例数：{agg['case_count']}",
        f"- Precision：{agg['precision']}",
        f"- Recall：{agg['recall']}",
        f"- F1：{agg['f1']}",
        f"- 字段完整率：{agg['field_completeness']}",
        f"- 证据片段命中率：{agg['evidence_hit_rate']}",
        f"- 幻觉率：{agg['hallucination_rate']}",
        "",
        "| case_id | TP | FP | FN |",
        "|---|---:|---:|---:|",
    ]
    for item in report["cases"]:
        lines.append(
            f"| {item.get('case_id')} | {item['true_positive']} | {item['false_positive']} | {item['false_negative']} |"
        )
    lines.append("")
    lines.append("> 说明：本报告基于人工 gold set，仅用于课程项目评测，不用于真实诊疗。")
    return "\n".join(lines)


def evaluate_on_gold_set(
    gold_path: Path = ANNOTATION_DIR / "gold_100.jsonl",
    output_path: Path = OUTPUT_DIR / "toyhom_gold_evaluation_report.md",
) -> dict[str, Any]:
    """读取 gold_100.jsonl 并输出评估报告。"""

    ensure_pipeline_dirs()
    records = read_jsonl(gold_path)
    report = evaluate_gold_records(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown_report(report), encoding="utf-8")
    return report
