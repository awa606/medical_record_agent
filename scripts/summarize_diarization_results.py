from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "v0_8_8_diarization"
DEFAULT_DEPENDENCY_STATUS = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "v0_8_7_diarization" / "dependency_status.json"
DEFAULT_OUTPUT_JSON = DEFAULT_RESULTS_DIR / "diarization_summary.json"
DEFAULT_OUTPUT_MD = DEFAULT_RESULTS_DIR / "diarization_summary.md"

MEASURED_SAMPLE_IDS = {"fever_01", "chest_pain_01"}
PENDING_SAMPLES = [
    {
        "sample_id": "three_speaker_course_sample",
        "status": "pending_sample",
        "reason": "用户选择本轮只做两说话人样本；不合成三说话人样本。",
    }
]


def summarize_results(
    results_dir: Path = DEFAULT_RESULTS_DIR,
    dependency_status_path: Path = DEFAULT_DEPENDENCY_STATUS,
) -> dict[str, Any]:
    result_files = sorted(
        path
        for path in results_dir.glob("*.json")
        if path.name not in {"diarization_summary.json", "dependency_status.json"}
    )
    results = []
    for path in result_files:
        payload = _load_json(path)
        if "engine" not in payload or "status" not in payload:
            continue
        results.append(payload | {"report_file": path.name})
    measured = [item for item in results if item.get("status") == "measured"]
    annotated_samples = sorted(
        {
            _sample_id(item)
            for item in results
            if _sample_id(item) in MEASURED_SAMPLE_IDS
        }
    )
    dependency_status = _load_json(dependency_status_path) if dependency_status_path.exists() else {}
    summary = {
        "scope": "v0.8.8 two-speaker diarization evaluation",
        "sample_count": len(MEASURED_SAMPLE_IDS) + len(PENDING_SAMPLES),
        "annotated_sample_count": len(annotated_samples),
        "annotated_samples": annotated_samples,
        "pending_samples": PENDING_SAMPLES,
        "measured_result_count": len(measured),
        "results": [_normalize_result(item) for item in results],
        "dependency_status": _normalize_dependencies(dependency_status),
        "der_jer_status": _der_jer_status(results),
        "conclusion": _conclusion(measured),
    }
    return summary


def write_summary(summary: dict[str, Any], json_output: Path, markdown_output: Path) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(summary), encoding="utf-8")


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# v0.8.8 两说话人 Diarization 评测汇总",
        "",
        "> 本报告只覆盖 `fever_01` 与 `chest_pain_01` 两条两说话人课程样本；三说话人样本保持待补，不输出伪成绩。",
        "",
        "## 样本状态",
        "",
        f"- 总样本项：{summary['sample_count']}",
        f"- 已标注两说话人样本：{summary['annotated_sample_count']} / 2",
        f"- 已测结果数：{summary['measured_result_count']}",
        f"- DER/JER 状态：{summary['der_jer_status']}",
        "",
        "| 样本 | 状态 | 说明 |",
        "| --- | --- | --- |",
    ]
    for sample_id in summary["annotated_samples"]:
        lines.append(f"| `{sample_id}` | `annotated` | 已有人工 RTTM，并参与本轮评测 |")
    for item in summary["pending_samples"]:
        lines.append(f"| `{item['sample_id']}` | `{item['status']}` | {item['reason']} |")

    lines.extend(
        [
            "",
            "## 单样本结果",
            "",
            "| 样本 | 引擎 | 状态 | speaker_count_error | boundary_f1 | mixed_utterance_rate | role_consistency | DER | JER | RTF | 报告 |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |",
        ]
    )
    for item in summary["results"]:
        lines.append(
            "| {sample} | `{engine}` | `{status}` | {speaker_error} | {boundary} | {mixed} | {role} | {der} | {jer} | {rtf} | `{report}` |".format(
                sample=item["sample_id"],
                engine=item["engine"],
                status=item["status"],
                speaker_error=_display(item.get("speaker_count_error")),
                boundary=_display(item.get("boundary_f1")),
                mixed=_display(item.get("mixed_utterance_rate")),
                role=_display(item.get("role_consistency")),
                der=_display(item.get("der_status")),
                jer=_display(item.get("jer_status")),
                rtf=_display(item.get("rtf")),
                report=item["report_file"],
            )
        )
    if not summary["results"]:
        lines.append("| - | - | `no_results` | - | - | - | - | - | - | - | - |")

    lines.extend(
        [
            "",
            "## 依赖状态",
            "",
            "| 引擎 | 状态 | 说明 |",
            "| --- | --- | --- |",
        ]
    )
    for name, item in summary["dependency_status"].items():
        lines.append(f"| `{name}` | `{item['status']}` | {item['reason']} |")

    lines.extend(
        [
            "",
            "## 结论",
            "",
        ]
    )
    lines.extend(f"- {line}" for line in summary["conclusion"])
    return "\n".join(lines) + "\n"


def _normalize_result(item: dict[str, Any]) -> dict[str, Any]:
    sample_id = _sample_id(item)
    return {
        "sample_id": sample_id,
        "engine": item.get("engine", "unknown"),
        "status": item.get("status", "unknown"),
        "reason": item.get("reason"),
        "speaker_count_error": item.get("speaker_count_error"),
        "boundary_f1": item.get("boundary_f1"),
        "mixed_utterance_rate": item.get("mixed_utterance_rate"),
        "role_consistency": item.get("role_consistency"),
        "der": item.get("der"),
        "jer": item.get("jer"),
        "der_status": "measured" if item.get("der") is not None else "not_available",
        "jer_status": "measured" if item.get("jer") is not None else "not_available",
        "rtf": item.get("rtf"),
        "elapsed_seconds": item.get("elapsed_seconds"),
        "audio_duration_seconds": item.get("audio_duration_seconds"),
        "report_file": item.get("report_file"),
    }


def _normalize_dependencies(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    engines = payload.get("engines") if isinstance(payload, dict) else None
    if not isinstance(engines, dict):
        return {
            "pyannote": {"status": "unknown", "reason": "dependency report not found"},
            "three_d_speaker": {"status": "unknown", "reason": "dependency report not found"},
            "funasr_campp": {"status": "unknown", "reason": "dependency report not found"},
        }
    return {
        str(name): {
            "status": str(item.get("status", "unknown")),
            "reason": str(item.get("reason", "")),
        }
        for name, item in engines.items()
        if isinstance(item, dict)
    }


def _der_jer_status(results: list[dict[str, Any]]) -> str:
    if any(item.get("der") is not None or item.get("jer") is not None for item in results):
        return "measured"
    return "not_available"


def _conclusion(measured: list[dict[str, Any]]) -> list[str]:
    if not measured:
        return [
            "本轮尚未产生 measured diarization 结果。",
            "三说话人样本保持 pending_sample，不纳入本轮结论。",
        ]
    avg_boundary = _average(item.get("boundary_f1") for item in measured)
    avg_role = _average(item.get("role_consistency") for item in measured)
    return [
        "本轮只引用 fever_01 与 chest_pain_01 两条两说话人课程样本。",
        f"两说话人样本平均 boundary_f1 为 {_display(avg_boundary)}，平均 role_consistency 为 {_display(avg_role)}。",
        "三说话人样本仍为 pending_sample；不能把本轮结果扩展解释为三说话人成绩。",
        "pyannote 和 3D-Speaker 的缺依赖状态只说明本机未配置，不代表模型效果差。",
    ]


def _sample_id(item: dict[str, Any]) -> str:
    if isinstance(item.get("sample_id"), str):
        return item["sample_id"]
    report_file = str(item.get("report_file", ""))
    for sample_id in MEASURED_SAMPLE_IDS:
        if sample_id in report_file:
            return sample_id
    return "unknown"


def _average(values: Any) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, int | float)]
    return round(sum(numbers) / len(numbers), 4) if numbers else None


def _display(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize diarization evaluation JSON files.")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--dependency-status", type=Path, default=DEFAULT_DEPENDENCY_STATUS)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    summary = summarize_results(args.results_dir, args.dependency_status)
    write_summary(summary, args.output_json, args.output_md)
    print(json.dumps({"results": len(summary["results"]), "markdown": str(args.output_md)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
