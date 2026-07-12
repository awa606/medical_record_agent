"""Apply external diarization turns to an ASRResult and re-run postprocess."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.asr import ASRResult, DiarizationTurn
from app.services.asr.speaker_diarization import enhance_speaker_diarization
from scripts.evaluate_diarization import evaluate_turns, parse_rttm


DEFAULT_ASR_RESULT = (
    PROJECT_ROOT
    / "data"
    / "asr_eval"
    / "reports"
    / "v0_8_13_three_speaker_measured"
    / "three_speaker_alimeeting_01_funasr_raw_asr_result.json"
)
DEFAULT_TURNS_REPORT = (
    PROJECT_ROOT
    / "data"
    / "asr_eval"
    / "reports"
    / "v0_8_17_true_diarization_compare"
    / "pyannote_three_speaker_alimeeting_01.json"
)
DEFAULT_REFERENCE_RTTM = PROJECT_ROOT / "data" / "asr_eval" / "diarization_ground_truth" / "three_speaker_alimeeting_01.rttm"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "v0_8_18_diarization_asr_alignment"
OUTPUT_NAME = "three_speaker_alimeeting_01_aligned_asr_result.json"
SUMMARY_NAME = "alignment_summary.md"
SUMMARY_JSON = "alignment_summary.json"


def apply_diarization_turns_to_asr_result(
    *,
    asr_result_path: Path = DEFAULT_ASR_RESULT,
    turns_report_path: Path = DEFAULT_TURNS_REPORT,
    reference_rttm: Path | None = DEFAULT_REFERENCE_RTTM,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> dict[str, Any]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = reports_dir / OUTPUT_NAME
    summary_path = reports_dir / SUMMARY_NAME
    summary_json_path = reports_dir / SUMMARY_JSON

    payload: dict[str, Any] = {
        "scope": "v0.8.18 diarization-ASR alignment",
        "status": "failed",
        "asr_result": str(asr_result_path),
        "turns_report": str(turns_report_path),
        "output": str(output_path),
    }
    if not asr_result_path.exists():
        payload.update({"status": "skipped", "reason": f"ASRResult not found: {asr_result_path}"})
        _write_outputs(summary_json_path, summary_path, payload)
        return payload
    if not turns_report_path.exists():
        payload.update({"status": "skipped", "reason": f"turns report not found: {turns_report_path}"})
        _write_outputs(summary_json_path, summary_path, payload)
        return payload

    turns_payload = json.loads(turns_report_path.read_text(encoding="utf-8"))
    turns = _extract_turns(turns_payload)
    if not turns:
        payload.update(
            {
                "status": "skipped",
                "reason": "turns report has no hypothesis_turns; no external diarization boundary to apply",
                "engine": turns_payload.get("engine") or turns_payload.get("requested_engine"),
                "source_status": turns_payload.get("status"),
                "source_reason": turns_payload.get("reason"),
            }
        )
        _write_outputs(summary_json_path, summary_path, payload)
        return payload

    raw_result = ASRResult.model_validate_json(asr_result_path.read_text(encoding="utf-8"))
    before_segments = len(raw_result.segments)
    with_turns = raw_result.model_copy(update={"diarization_turns": turns})
    enhanced = enhance_speaker_diarization(with_turns)
    output_path.write_text(
        json.dumps(enhanced.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    payload.update(
        {
            "status": "measured",
            "engine": turns_payload.get("engine") or turns_payload.get("requested_engine"),
            "source_status": turns_payload.get("status"),
            "turn_count": len(turns),
            "segment_count_before": before_segments,
            "segment_count_after": len(enhanced.segments),
            "speaker_count_after": len({segment.speaker_id or segment.speaker for segment in enhanced.segments}),
            "needs_review": enhanced.needs_review,
        }
    )
    if reference_rttm and reference_rttm.exists():
        reference = parse_rttm(reference_rttm)
        payload["after_metrics"] = evaluate_turns(reference, enhanced.diarization_turns).__dict__
        if raw_result.diarization_turns:
            payload["before_metrics"] = evaluate_turns(reference, raw_result.diarization_turns).__dict__
        else:
            payload["before_metrics"] = {
                "status": "not_available",
                "reason": "raw ASRResult has no diarization_turns",
            }
    _write_outputs(summary_json_path, summary_path, payload)
    return payload


def _extract_turns(payload: dict[str, Any]) -> list[DiarizationTurn]:
    raw_turns = payload.get("hypothesis_turns") or payload.get("turns") or []
    return [DiarizationTurn.model_validate(item) for item in raw_turns]


def _write_outputs(json_path: Path, markdown_path: Path, payload: dict[str, Any]) -> None:
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# v0.8.18 Diarization 与 ASR 对齐报告",
        "",
        f"- 状态：`{payload.get('status')}`",
        f"- 引擎：`{payload.get('engine', '-')}`",
        f"- ASRResult：`{payload.get('asr_result')}`",
        f"- turns 报告：`{payload.get('turns_report')}`",
    ]
    for key in (
        "reason",
        "source_status",
        "source_reason",
        "turn_count",
        "segment_count_before",
        "segment_count_after",
        "speaker_count_after",
        "needs_review",
    ):
        if key in payload:
            lines.append(f"- {key}: `{payload[key]}`")
    if payload.get("before_metrics") or payload.get("after_metrics"):
        lines.extend(["", "## 指标", ""])
        lines.append(f"- before_metrics: `{payload.get('before_metrics', '-')}`")
        lines.append(f"- after_metrics: `{payload.get('after_metrics', '-')}`")
    lines.append("")
    lines.append("说明：本报告只验证外部 diarization 边界能否降低 ASR 混合语句，不代表 AliMeeting 会议样本的医疗问诊效果。")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply external diarization turns to ASRResult.")
    parser.add_argument("--asr-result", type=Path, default=DEFAULT_ASR_RESULT)
    parser.add_argument("--turns-report", type=Path, default=DEFAULT_TURNS_REPORT)
    parser.add_argument("--reference-rttm", type=Path, default=DEFAULT_REFERENCE_RTTM)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = apply_diarization_turns_to_asr_result(
        asr_result_path=args.asr_result,
        turns_report_path=args.turns_report,
        reference_rttm=args.reference_rttm,
        reports_dir=args.reports_dir,
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
