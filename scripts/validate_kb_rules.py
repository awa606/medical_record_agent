"""Validate knowledge-rule behavior against curated non-clinical cases.

The report proves engineering consistency only: expected rule IDs are matched,
forbidden rule IDs are not matched, and outputs remain doctor-review candidates.
It does not prove clinical validity.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.knowledge_rules import infer_common_cold_candidates


KB_DIR = PROJECT_ROOT / "data" / "output" / "kb"
DEFAULT_CASES = KB_DIR / "rule_validation_cases.json"
DEFAULT_JSON_REPORT = KB_DIR / "rule_validation_report.json"
DEFAULT_MD_REPORT = KB_DIR / "rule_validation_report.md"
FORBIDDEN_OUTPUT_TERMS = ["最终诊断", "确诊", "自动处方"]


def validate_rule_cases(cases_path: Path = DEFAULT_CASES) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    results = [_validate_case(case) for case in cases]
    passed = sum(1 for item in results if item["passed"])
    return {
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": round(passed / len(results), 4) if results else 0.0,
            "clinical_validity": "not_claimed",
            "purpose": "engineering_rule_traceability",
        },
        "results": results,
    }


def _validate_case(case: dict[str, Any]) -> dict[str, Any]:
    candidates = infer_common_cold_candidates(str(case["conversation"]))
    matched_rule_ids = [candidate.rule_id for candidate in candidates if candidate.rule_id]
    expected_rule_ids = list(case.get("expected_rule_ids", []))
    forbidden_rule_ids = list(case.get("forbidden_rule_ids", []))
    expected_warning_terms = list(case.get("expected_warning_terms", []))
    candidate_text = _candidate_text(candidates)

    missing_expected = [
        rule_id for rule_id in expected_rule_ids
        if rule_id not in matched_rule_ids
    ]
    unexpected_forbidden = [
        rule_id for rule_id in forbidden_rule_ids
        if rule_id in matched_rule_ids
    ]
    unsafe_terms = [
        term for term in FORBIDDEN_OUTPUT_TERMS
        if term in candidate_text
    ]
    missing_warning_terms = [
        term for term in expected_warning_terms
        if term not in candidate_text
    ]
    bad_status = [
        candidate.name for candidate in candidates
        if candidate.status != "候选/待医生确认"
    ]
    no_candidate_failure = bool(case.get("expect_no_candidates")) and bool(candidates)

    passed = not any(
        [
            missing_expected,
            unexpected_forbidden,
            unsafe_terms,
            missing_warning_terms,
            bad_status,
            no_candidate_failure,
        ]
    )
    return {
        "case_id": case["case_id"],
        "title": case.get("title", ""),
        "passed": passed,
        "expected_rule_ids": expected_rule_ids,
        "matched_rule_ids": matched_rule_ids,
        "missing_expected": missing_expected,
        "unexpected_forbidden": unexpected_forbidden,
        "unsafe_terms": unsafe_terms,
        "missing_warning_terms": missing_warning_terms,
        "bad_status": bad_status,
        "candidates": [
            {
                "name": candidate.name,
                "status": candidate.status,
                "rule_id": candidate.rule_id,
                "confidence": candidate.confidence,
                "reason": candidate.reason,
                "risk_warnings": candidate.risk_warnings,
            }
            for candidate in candidates
        ],
    }


def _candidate_text(candidates: list[Any]) -> str:
    payload = [
        candidate.model_dump(mode="json") if hasattr(candidate, "model_dump") else candidate
        for candidate in candidates
    ]
    return json.dumps(payload, ensure_ascii=False)


def write_reports(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 知识库规则验证报告",
        "",
        "> 本报告只验证工程规则是否按预期命中，不证明医学诊断正确性。",
        "",
        "## 汇总",
        "",
        f"- 样例总数：{summary['total']}",
        f"- 通过：{summary['passed']}",
        f"- 失败：{summary['failed']}",
        f"- 通过率：{summary['pass_rate']}",
        f"- 临床有效性声明：{summary['clinical_validity']}",
        "",
        "## 样例结果",
        "",
        "| 样例 | 是否通过 | 期望规则 | 命中规则 | 失败原因 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in report["results"]:
        failure_parts = []
        for key in ["missing_expected", "unexpected_forbidden", "unsafe_terms", "missing_warning_terms", "bad_status"]:
            if result[key]:
                failure_parts.append(f"{key}: {'、'.join(result[key])}")
        failure = "；".join(failure_parts) or "无"
        lines.append(
            "| {case_id} | {passed} | {expected} | {matched} | {failure} |".format(
                case_id=result["case_id"],
                passed="通过" if result["passed"] else "失败",
                expected="、".join(result["expected_rule_ids"]) or "无",
                matched="、".join(result["matched_rule_ids"]) or "无",
                failure=failure,
            )
        )
    lines.extend(
        [
            "",
            "## 使用说明",
            "",
            "```powershell",
            "python scripts/validate_kb_rules.py",
            "```",
            "",
            "如果后续导入教材、指南或书籍知识，应先补充来源元数据和人工审核状态，再新增验证样例。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="验证知识库规则样例命中情况")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_REPORT)
    args = parser.parse_args()

    report = validate_rule_cases(args.cases)
    write_reports(report, args.json_output, args.md_output)
    summary = report["summary"]
    print("知识库规则验证完成：")
    print(f"- 样例总数: {summary['total']}")
    print(f"- 通过: {summary['passed']}")
    print(f"- 失败: {summary['failed']}")
    print(f"- JSON: {args.json_output}")
    print(f"- Markdown: {args.md_output}")
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
