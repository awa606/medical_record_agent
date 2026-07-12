"""Run multiple diarization engines on the same public speaker sample.

The script writes lightweight JSON/Markdown evidence only. Source audio,
downloaded datasets, model weights, and local caches remain outside Git.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_diarization import evaluate_diarization_engine, parse_rttm


DEFAULT_AUDIO = PROJECT_ROOT / "data" / "asr_eval" / "public_diarization" / "audio" / "three_speaker_alimeeting_01.wav"
DEFAULT_REFERENCE_RTTM = PROJECT_ROOT / "data" / "asr_eval" / "diarization_ground_truth" / "three_speaker_alimeeting_01.rttm"
DEFAULT_ASR_RESULT = (
    PROJECT_ROOT
    / "data"
    / "asr_eval"
    / "reports"
    / "v0_8_13_three_speaker_measured"
    / "three_speaker_alimeeting_01_funasr_enhanced_asr_result.json"
)
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "v0_8_17_true_diarization_compare"
DEFAULT_ENGINES = ("funasr_campp", "pyannote", "three_d_speaker")
SUMMARY_JSON = "diarization_engine_compare_summary.json"
SUMMARY_MD = "diarization_engine_compare_summary.md"


Evaluator = Callable[..., dict[str, Any]]


def run_diarization_engine_compare(
    *,
    audio_path: Path = DEFAULT_AUDIO,
    reference_rttm: Path = DEFAULT_REFERENCE_RTTM,
    asr_result: Path | None = DEFAULT_ASR_RESULT,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    engines: Sequence[str] = DEFAULT_ENGINES,
    evaluator: Evaluator = evaluate_diarization_engine,
) -> dict[str, Any]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    reference_turns = parse_rttm(reference_rttm) if reference_rttm.exists() else []
    results: list[dict[str, Any]] = []

    for engine in engines:
        payload = evaluator(
            engine_name=engine,
            audio_path=audio_path,
            reference_rttm=reference_rttm,
            asr_result=asr_result if engine in {"funasr", "funasr_campp", "campp"} else None,
        )
        payload.setdefault("requested_engine", engine)
        payload.update(
            {
                "sample_id": audio_path.stem,
                "sample_source": "AliMeeting Eval, CC BY-SA 4.0",
                "sample_boundary": "public meeting diarization only; not a medical consultation accuracy result",
                "reference_turn_count": len(reference_turns),
                "reference_speaker_count": len({turn.speaker_id for turn in reference_turns}),
            }
        )
        output = reports_dir / f"{_safe_name(engine)}_three_speaker_alimeeting_01.json"
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["report_path"] = str(output)
        results.append(payload)

    summary = {
        "scope": "v0.8.17 true diarization engine comparison",
        "sample_id": audio_path.stem,
        "sample_source": "AliMeeting Eval, CC BY-SA 4.0",
        "sample_boundary": "AliMeeting is a public meeting sample; it is used only to test multi-speaker diarization.",
        "audio_path_local_only": str(audio_path),
        "reference_rttm": str(reference_rttm),
        "asr_result": str(asr_result) if asr_result else None,
        "reference_turn_count": len(reference_turns),
        "reference_speaker_count": len({turn.speaker_id for turn in reference_turns}),
        "results": results,
        "best_candidate": _best_candidate(results),
    }
    (reports_dir / SUMMARY_JSON).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (reports_dir / SUMMARY_MD).write_text(render_markdown(summary), encoding="utf-8")
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# v0.8.17 真实多说话人 Diarization 引擎对比",
        "",
        f"- 样本：`{summary['sample_id']}`",
        f"- 来源：{summary['sample_source']}",
        f"- 边界：{summary['sample_boundary']}",
        f"- 人工 RTTM speaker 数：`{summary['reference_speaker_count']}`",
        f"- 人工 RTTM turn 数：`{summary['reference_turn_count']}`",
        "",
        "| 引擎 | 状态 | turn 数 | speaker_count_error | boundary_f1 | mixed_utterance_rate | role_consistency | DER | JER | RTF | RSS 峰值 MB | 说明 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summary["results"]:
        lines.append(
            "| {engine} | `{status}` | {turns} | {speaker_error} | {boundary} | {mixed} | {role} | {der} | {jer} | {rtf} | {rss} | {reason} |".format(
                engine=item.get("engine") or item.get("requested_engine"),
                status=item.get("status"),
                turns=_display(item.get("turn_count")),
                speaker_error=_display(item.get("speaker_count_error")),
                boundary=_display(item.get("boundary_f1")),
                mixed=_display(item.get("mixed_utterance_rate")),
                role=_display(item.get("role_consistency")),
                der=_display(item.get("der")),
                jer=_display(item.get("jer")),
                rtf=_display(item.get("rtf")),
                rss=_display(item.get("rss_peak_mb")),
                reason=(item.get("reason") or item.get("error") or "-").replace("|", "/"),
            )
        )

    best = summary.get("best_candidate")
    lines.extend(["", "## 结论", ""])
    if best:
        lines.append(
            f"- 当前最佳候选：`{best['engine']}`，选择依据是 mixed utterance rate、boundary F1 和资源占用。"
        )
    else:
        lines.append("- 当前没有 measured 引擎；缺依赖或失败只说明本机环境未完成，不代表模型效果差。")
    lines.append("- 会议样本只用于多说话人分离评测，不能作为中文医患问诊准确率结论。")
    return "\n".join(lines) + "\n"


def _best_candidate(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    measured = [item for item in results if item.get("status") == "measured"]
    if not measured:
        return None
    return sorted(
        measured,
        key=lambda item: (
            item.get("mixed_utterance_rate", 1.0),
            -(item.get("boundary_f1") or 0.0),
            abs(item.get("speaker_count_error") or 0),
            item.get("rss_peak_mb") or float("inf"),
        ),
    )[0]


def _display(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip().lower()).strip("_") or "engine"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare diarization engines on one public multi-speaker sample.")
    parser.add_argument("--audio", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--reference-rttm", type=Path, default=DEFAULT_REFERENCE_RTTM)
    parser.add_argument("--asr-result", type=Path, default=DEFAULT_ASR_RESULT)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--engines", nargs="+", default=list(DEFAULT_ENGINES))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run_diarization_engine_compare(
        audio_path=args.audio,
        reference_rttm=args.reference_rttm,
        asr_result=args.asr_result,
        reports_dir=args.reports_dir,
        engines=args.engines,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
