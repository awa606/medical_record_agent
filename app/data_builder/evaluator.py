"""字段抽取结果评估工具。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.data_builder.dialogue_generator import generate_dialogues
from app.data_builder.paths import OUTPUT_DIR, ensure_data_builder_dirs


@dataclass
class MetricCounts:
    """症状抽取的 TP/FP/FN 计数。"""

    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0

    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else 0.0

    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 0.0

    def f1(self) -> float:
        precision = self.precision()
        recall = self.recall()
        return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _case_list(payload: Any) -> list[dict[str, Any]]:
    """兼容 {"cases": [...]} 和直接列表两种输入格式。"""

    if isinstance(payload, dict) and "cases" in payload:
        return payload["cases"]
    if isinstance(payload, list):
        return payload
    raise ValueError("评估输入必须是 cases 列表或包含 cases 的 JSON 对象")


def _symptom_set(case: dict[str, Any], preferred_key: str) -> set[str]:
    """读取症状编号集合。"""

    value = case.get(preferred_key)
    if value is None and preferred_key == "predicted_symptom_ids":
        value = case.get("expected_symptom_ids")
    if value is None:
        return set()
    if isinstance(value, str):
        return {item.strip() for item in value.split("|") if item.strip()}
    return {str(item) for item in value}


def _field_completeness(predicted_case: dict[str, Any], gold_case: dict[str, Any]) -> float:
    """计算字段完整率。

    这里以 gold 的 expected_fields 为字段清单，预测结果中有非空值就视为该字段已抽取。
    如果预测文件暂未提供，脚本默认用模拟标准答案做演示评估。
    """

    gold_fields = gold_case.get("expected_fields") or gold_case.get("expected_fields_json") or {}
    predicted_fields = predicted_case.get("predicted_fields") or predicted_case.get("expected_fields") or {}
    if not gold_fields:
        return 0.0

    completed = 0
    for field_name in gold_fields.keys():
        value = predicted_fields.get(field_name)
        if value not in (None, "", [], {}):
            completed += 1
    return completed / len(gold_fields)


def evaluate_extraction(
    gold_path: Path = OUTPUT_DIR / "generated_dialogues.json",
    pred_path: Path | None = None,
    output_path: Path = OUTPUT_DIR / "evaluation_report.json",
) -> dict[str, Any]:
    """评估字段抽取结果，输出准确率、召回率、F1 和字段完整率。

    参数说明：
    - gold_path：标准答案文件，默认使用 generate_dialogues.py 生成的测试集；
    - pred_path：模型或规则抽取结果文件，可选；
    - output_path：评估报告输出位置。

    如果 pred_path 未提供，脚本会使用 gold 复制一份“演示预测”，便于在没有
    真实抽取模型时跑通全流程。后续接入模型后，只需要提供预测 JSON 即可。
    """

    ensure_data_builder_dirs()
    if not gold_path.exists():
        generate_dialogues(gold_path)

    gold_cases = _case_list(_load_json(gold_path))
    if pred_path and pred_path.exists():
        pred_cases = _case_list(_load_json(pred_path))
        demo_mode = False
    else:
        pred_cases = gold_cases
        demo_mode = True

    pred_by_id = {case["case_id"]: case for case in pred_cases}
    aggregate_counts = MetricCounts()
    case_reports: list[dict[str, Any]] = []
    completeness_values: list[float] = []

    for gold_case in gold_cases:
        case_id = gold_case["case_id"]
        predicted_case = pred_by_id.get(case_id, {})
        gold_symptoms = _symptom_set(gold_case, "expected_symptom_ids")
        predicted_symptoms = _symptom_set(predicted_case, "predicted_symptom_ids")

        counts = MetricCounts(
            true_positive=len(gold_symptoms & predicted_symptoms),
            false_positive=len(predicted_symptoms - gold_symptoms),
            false_negative=len(gold_symptoms - predicted_symptoms),
        )
        aggregate_counts.true_positive += counts.true_positive
        aggregate_counts.false_positive += counts.false_positive
        aggregate_counts.false_negative += counts.false_negative

        completeness = _field_completeness(predicted_case, gold_case)
        completeness_values.append(completeness)
        case_reports.append(
            {
                "case_id": case_id,
                "expected_syndrome_id": gold_case.get("expected_syndrome_id"),
                "precision": round(counts.precision(), 4),
                "recall": round(counts.recall(), 4),
                "f1": round(counts.f1(), 4),
                "field_completeness": round(completeness, 4),
                "true_positive": counts.true_positive,
                "false_positive": counts.false_positive,
                "false_negative": counts.false_negative,
            }
        )

    report = {
        "meta": {
            "gold_path": str(gold_path),
            "pred_path": str(pred_path) if pred_path else None,
            "demo_mode": demo_mode,
            "note": "demo_mode=true 表示暂未接入真实抽取结果，使用标准答案演示评估流程。",
        },
        "aggregate": {
            "precision": round(aggregate_counts.precision(), 4),
            "recall": round(aggregate_counts.recall(), 4),
            "f1": round(aggregate_counts.f1(), 4),
            "field_completeness": round(sum(completeness_values) / len(completeness_values), 4)
            if completeness_values
            else 0.0,
            "case_count": len(gold_cases),
        },
        "cases": case_reports,
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_path = output_path.with_suffix(".md")
    markdown_path.write_text(_render_markdown_report(report), encoding="utf-8")
    return report


def _render_markdown_report(report: dict[str, Any]) -> str:
    """生成便于课程展示的 Markdown 评估报告。"""

    aggregate = report["aggregate"]
    lines = [
        "# 字段抽取评估报告",
        "",
        f"- 病例数：{aggregate['case_count']}",
        f"- 准确率 Precision：{aggregate['precision']}",
        f"- 召回率 Recall：{aggregate['recall']}",
        f"- F1：{aggregate['f1']}",
        f"- 字段完整率：{aggregate['field_completeness']}",
        f"- 演示模式：{report['meta']['demo_mode']}",
        "",
        "| case_id | Precision | Recall | F1 | 字段完整率 |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in report["cases"]:
        lines.append(
            f"| {item['case_id']} | {item['precision']} | {item['recall']} | {item['f1']} | {item['field_completeness']} |"
        )
    lines.append("")
    lines.append("> 注：本报告仅用于课程项目模拟评估，不涉及真实患者数据。")
    return "\n".join(lines)
