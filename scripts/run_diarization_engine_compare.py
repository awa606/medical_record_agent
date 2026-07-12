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

MAX_ACCEPTABLE_MIXED_UTTERANCE_RATE = 0.30
MIN_ACCEPTABLE_BOUNDARY_F1 = 0.50
MAX_ACCEPTABLE_SPEAKER_COUNT_ERROR = 1


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
        payload["quality_gate"] = _quality_gate(payload)
        output = reports_dir / f"{_safe_name(engine)}_three_speaker_alimeeting_01.json"
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["report_path"] = str(output)
        results.append(payload)

    summary = {
        "scope": "v0.8.22 diarization quality gate",
        "sample_id": audio_path.stem,
        "sample_source": "AliMeeting Eval, CC BY-SA 4.0",
        "sample_boundary": "AliMeeting is a public meeting sample; it is used only to test multi-speaker diarization.",
        "audio_path_local_only": str(audio_path),
        "reference_rttm": str(reference_rttm),
        "asr_result": str(asr_result) if asr_result else None,
        "reference_turn_count": len(reference_turns),
        "reference_speaker_count": len({turn.speaker_id for turn in reference_turns}),
        "quality_gate_policy": {
            "max_mixed_utterance_rate": MAX_ACCEPTABLE_MIXED_UTTERANCE_RATE,
            "min_boundary_f1": MIN_ACCEPTABLE_BOUNDARY_F1,
            "max_speaker_count_error": MAX_ACCEPTABLE_SPEAKER_COUNT_ERROR,
            "decision_note": "Only engines passing this gate may be used as candidates for automatic speaker-role mapping.",
        },
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
    policy = summary.get("quality_gate_policy", {})
    lines = [
        "# Diarization Engine Comparison With Quality Gate",
        "",
        f"- Sample: `{summary['sample_id']}`",
        f"- Source: {summary['sample_source']}",
        f"- Boundary: {summary['sample_boundary']}",
        f"- Reference speaker count: `{summary['reference_speaker_count']}`",
        f"- Reference turn count: `{summary['reference_turn_count']}`",
        f"- Quality gate: mixed_utterance_rate <= `{policy.get('max_mixed_utterance_rate')}`, "
        f"boundary_f1 >= `{policy.get('min_boundary_f1')}`, "
        f"speaker_count_error <= `{policy.get('max_speaker_count_error')}`",
        "",
        "| Engine | Status | Gate | Turns | speaker_count_error | boundary_f1 | mixed_utterance_rate | role_consistency | DER | JER | RTF | RSS peak MB | Reason |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summary["results"]:
        gate = item.get("quality_gate", {})
        lines.append(
            "| {engine} | `{status}` | `{gate}` | {turns} | {speaker_error} | {boundary} | {mixed} | {role} | {der} | {jer} | {rtf} | {rss} | {reason} |".format(
                engine=item.get("engine") or item.get("requested_engine"),
                status=item.get("status"),
                gate=gate.get("decision", "-"),
                turns=_display(item.get("turn_count")),
                speaker_error=_display(item.get("speaker_count_error")),
                boundary=_display(item.get("boundary_f1")),
                mixed=_display(item.get("mixed_utterance_rate")),
                role=_display(item.get("role_consistency")),
                der=_display(item.get("der")),
                jer=_display(item.get("jer")),
                rtf=_display(item.get("rtf")),
                rss=_display(item.get("rss_peak_mb")),
                reason=(item.get("reason") or item.get("error") or gate.get("reason") or "-").replace("|", "/"),
            )
        )

    best = summary.get("best_candidate")
    lines.extend(["", "## Conclusion", ""])
    if best:
        lines.append(
            f"- Best current candidate: `{best['engine']}`. It passed the quality gate and was selected by mixed utterance rate, boundary F1, speaker count error, and RSS."
        )
    else:
        lines.append("- No measured engine passed the quality gate. Do not use these results for automatic doctor/patient role mapping.")
    lines.append("- This public meeting sample is only diarization evidence. It is not medical consultation accuracy evidence.")
    return "\n".join(lines) + "\n"


def _best_candidate(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in results
        if item.get("status") == "measured"
        and item.get("quality_gate", {}).get("decision") == "candidate_for_role_mapping"
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            item.get("mixed_utterance_rate", 1.0),
            -(item.get("boundary_f1") or 0.0),
            abs(item.get("speaker_count_error") or 0),
            item.get("rss_peak_mb") or float("inf"),
        ),
    )[0]


def _quality_gate(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("status") != "measured":
        return {
            "status": "not_evaluated",
            "decision": "blocked",
            "reason": item.get("reason") or item.get("error") or "engine did not produce a measured result",
        }

    mixed = item.get("mixed_utterance_rate")
    boundary = item.get("boundary_f1")
    speaker_error = item.get("speaker_count_error")
    checks = {
        "mixed_utterance_rate": {
            "value": mixed,
            "threshold": MAX_ACCEPTABLE_MIXED_UTTERANCE_RATE,
            "passed": mixed is not None and mixed <= MAX_ACCEPTABLE_MIXED_UTTERANCE_RATE,
        },
        "boundary_f1": {
            "value": boundary,
            "threshold": MIN_ACCEPTABLE_BOUNDARY_F1,
            "passed": boundary is not None and boundary >= MIN_ACCEPTABLE_BOUNDARY_F1,
        },
        "speaker_count_error": {
            "value": speaker_error,
            "threshold": MAX_ACCEPTABLE_SPEAKER_COUNT_ERROR,
            "passed": speaker_error is not None and abs(speaker_error) <= MAX_ACCEPTABLE_SPEAKER_COUNT_ERROR,
        },
    }
    failed = [name for name, check in checks.items() if not check["passed"]]
    if failed:
        return {
            "status": "evaluated",
            "decision": "reject_for_role_mapping",
            "reason": "failed checks: " + ", ".join(failed),
            "checks": checks,
        }
    return {
        "status": "evaluated",
        "decision": "candidate_for_role_mapping",
        "reason": "passed all quality gate checks",
        "checks": checks,
    }


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
