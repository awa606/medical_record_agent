from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.asr import ASRResult, ASRSegment, SpeakerRoleAssignment
from app.services.asr.role_quality import (
    SpeakerRoleQualityPolicy,
    legacy_speaker_role_quality_report,
)


CLINICAL_ROLES = {"医生", "患者", "其他"}
MANUAL_SOURCES = {"manual", "manual_speaker_map"}


def validate_speaker_role_quality(
    asr_result: ASRResult,
    *,
    expected_roles: dict[str, str] | None = None,
    confidence_threshold: float = 0.9,
    max_manual_confirmation_rate: float = 0.35,
    max_mixed_utterance_rate: float = 0.05,
) -> dict[str, Any]:
    policy = SpeakerRoleQualityPolicy(
        confidence_threshold=confidence_threshold,
        max_manual_confirmation_rate=max_manual_confirmation_rate,
        max_mixed_utterance_rate=max_mixed_utterance_rate,
    )
    return legacy_speaker_role_quality_report(
        asr_result,
        expected_roles=expected_roles,
        policy=policy,
    )


def _speaker_id(segment: ASRSegment) -> str:
    return str(segment.speaker_id or segment.speaker or "").strip()


def _is_low_confidence_clinical(segment: ASRSegment, threshold: float) -> bool:
    role = str(segment.role or "").strip()
    if role not in CLINICAL_ROLES:
        return False
    if segment.reviewed_by_doctor:
        return False
    if str(segment.role_source or "") in MANUAL_SOURCES:
        return False
    confidence = segment.role_confidence
    return confidence is None or confidence < threshold


def _role_accuracy(
    assignments: dict[str, SpeakerRoleAssignment],
    expected_roles: dict[str, str],
) -> float | None:
    if not expected_roles:
        return None
    total = 0
    correct = 0
    for speaker_id, expected in expected_roles.items():
        if expected not in CLINICAL_ROLES:
            continue
        total += 1
        actual = assignments.get(speaker_id)
        if actual and actual.role == expected:
            correct += 1
    return round(correct / total, 4) if total else None


def _looks_like_mixed_medical_utterance(text: str) -> bool:
    compact = "".join(str(text or "").split())
    if len(compact) < 10:
        return False
    doctor_markers = ("请问", "有没有", "是否", "哪里", "什么时候", "多少岁", "做什么工作")
    patient_markers = ("我是", "我有", "我发热", "我咳嗽", "没有", "吃过", "用过", "疼")
    return any(marker in compact for marker in doctor_markers) and any(
        marker in compact for marker in patient_markers
    )


def _compact(text: str, limit: int = 80) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else f"{value[:limit]}..."


def _recommendations(
    low_confidence_clinical: list[dict[str, Any]],
    unresolved_assignments: list[dict[str, Any]],
    mixed_candidates: list[dict[str, Any]],
    role_accuracy: float | None,
) -> list[str]:
    items: list[str] = []
    if low_confidence_clinical:
        items.append("低置信度自动角色不能直接显示为医生/患者，应降级为说话人 A/B/C。")
    if unresolved_assignments:
        items.append("生成病历前需要一次全局说话人角色映射确认。")
    if mixed_candidates:
        items.append("疑似混合语句需要继续优化 VAD/diarization 边界或拆句后处理。")
    if role_accuracy is not None and role_accuracy < 0.9:
        items.append("固定样本角色准确率未达门禁，应保留人工确认并重新评测模型路线。")
    if not items:
        items.append("当前 ASRResult 满足医生端安全展示门禁。")
    return items


def _load_expected_roles(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("speaker_roles"), dict):
        return {str(key): str(value) for key, value in payload["speaker_roles"].items()}
    if isinstance(payload, dict):
        return {str(key): str(value) for key, value in payload.items()}
    raise ValueError("expected roles file must be a JSON object")


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    gate = report["quality_gate"]
    lines = [
        "# 说话人角色质量门禁报告",
        "",
        f"- 状态：`{report['status']}`",
        f"- 稳定转写段数：{summary['segment_count']}",
        f"- 说话人数：{summary['speaker_count']} ({', '.join(summary['speaker_ids']) or '-'})",
        f"- 需全局确认率：{summary['manual_confirmation_rate']}",
        f"- 角色准确率：{summary['role_accuracy'] if summary['role_accuracy'] is not None else 'not_provided'}",
        f"- 疑似混合语句率：{summary['mixed_utterance_candidate_rate']}",
        "",
        "## 门禁项",
        "",
        f"- 低置信度临床角色段：{gate['low_confidence_clinical_role_count']}",
        f"- 未映射稳定说话人片段：{gate['unmapped_speaker_count']}",
        f"- 未完成说话人映射：{gate['unresolved_assignment_count']}",
        f"- 疑似混合语句：{gate['mixed_utterance_candidate_count']}（阈值 {gate['max_mixed_utterance_rate']}）",
        "",
        "## 建议",
        "",
    ]
    lines.extend(f"- {item}" for item in report["recommendations"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate speaker-role quality gate for ASRResult JSON.")
    parser.add_argument("--asr-result", type=Path, required=True)
    parser.add_argument("--expected-roles", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--confidence-threshold", type=float, default=0.9)
    parser.add_argument("--max-manual-confirmation-rate", type=float, default=0.35)
    parser.add_argument("--max-mixed-utterance-rate", type=float, default=0.05)
    args = parser.parse_args()

    payload = json.loads(args.asr_result.read_text(encoding="utf-8"))
    asr_result = ASRResult.model_validate(payload)
    report = validate_speaker_role_quality(
        asr_result,
        expected_roles=_load_expected_roles(args.expected_roles),
        confidence_threshold=args.confidence_threshold,
        max_manual_confirmation_rate=args.max_manual_confirmation_rate,
        max_mixed_utterance_rate=args.max_mixed_utterance_rate,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output_json)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
