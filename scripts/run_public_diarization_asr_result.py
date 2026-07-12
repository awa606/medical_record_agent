"""Generate ASRResult evidence for public multi-speaker diarization samples.

The script keeps source audio local and writes only lightweight JSON/Markdown
evidence. It is intentionally independent from the web app runtime so model
failures are recorded as measured/failed reports instead of blocking other
development work.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.asr import ASRResult
from app.services.asr import create_asr_engine
from app.services.asr.chunking import probe_audio_duration
from app.services.asr.ffmpeg_utils import find_ffprobe_executable
from app.services.asr.speaker_diarization import enhance_speaker_diarization
from scripts.run_local_asr_benchmark import _ResourceSampler


DEFAULT_AUDIO = PROJECT_ROOT / "data" / "asr_eval" / "public_diarization" / "audio" / "three_speaker_alimeeting_01.wav"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "v0_8_13_three_speaker_measured"
RAW_RESULT_NAME = "three_speaker_alimeeting_01_funasr_raw_asr_result.json"
ENHANCED_RESULT_NAME = "three_speaker_alimeeting_01_funasr_enhanced_asr_result.json"
SUMMARY_NAME = "three_speaker_alimeeting_01_asr_result_summary.md"


class _Engine(Protocol):
    name: str

    def transcribe(self, audio_id: str, audio_path: Path) -> ASRResult:
        ...


def run_public_diarization_asr_result(
    *,
    audio_path: Path = DEFAULT_AUDIO,
    report_dir: Path = DEFAULT_REPORT_DIR,
    engine_name: str = "funasr",
    engine_factory: Any = create_asr_engine,
) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    raw_output = report_dir / RAW_RESULT_NAME
    enhanced_output = report_dir / ENHANCED_RESULT_NAME
    summary_output = report_dir / SUMMARY_NAME

    payload: dict[str, Any] = {
        "sample_id": audio_path.stem,
        "scenario": "public_meeting_diarization",
        "source": "AliMeeting Eval, CC BY-SA 4.0",
        "engine": engine_name,
        "status": "failed",
        "audio_path": str(audio_path),
    }

    if not audio_path.exists():
        payload.update(
            {
                "status": "skipped",
                "error": f"audio file not found: {audio_path}",
            }
        )
        _write_summary(summary_output, payload)
        return payload

    started = time.perf_counter()
    try:
        engine: _Engine = engine_factory(engine_name)
        model_ready_at = time.perf_counter()
        with _ResourceSampler() as sampler:
            raw_result = engine.transcribe(audio_path.stem, audio_path)
        elapsed = time.perf_counter() - model_ready_at
        resources = sampler.metrics(elapsed)
        raw_result = raw_result.model_copy(
            update={
                "manifest_sample_id": audio_path.stem,
                "scenario": "public_meeting_diarization",
                "evaluate_diarization": True,
            }
        )
        enhanced_result = enhance_speaker_diarization(raw_result)
        raw_output.write_text(
            json.dumps(raw_result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        enhanced_output.write_text(
            json.dumps(enhanced_result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        duration = raw_result.duration or _probe_duration(audio_path)
        payload.update(
            {
                "status": "measured",
                "engine": raw_result.engine,
                "model_load_seconds": round(model_ready_at - started, 3),
                "elapsed_seconds": round(elapsed, 3),
                "audio_duration_seconds": duration,
                "rtf": round(elapsed / duration, 4) if duration else None,
                "raw_segments": len(raw_result.segments),
                "enhanced_segments": len(enhanced_result.segments),
                "raw_speaker_count": len({segment.speaker_id or segment.speaker for segment in raw_result.segments}),
                "enhanced_speaker_count": len({segment.speaker_id or segment.speaker for segment in enhanced_result.segments}),
                "raw_result": str(raw_output),
                "enhanced_result": str(enhanced_output),
                **resources,
            }
        )
    except Exception as exc:  # pragma: no cover - integration failure path
        payload.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})

    _write_summary(summary_output, payload)
    return payload


def _probe_duration(audio_path: Path) -> float | None:
    ffprobe = find_ffprobe_executable()
    if not ffprobe:
        return None
    try:
        return probe_audio_duration(audio_path, ffprobe)
    except Exception:
        return None


def _write_summary(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# v0.8.13 三说话人 ASRResult 实测摘要",
        "",
        "- 样本：`three_speaker_alimeeting_01.wav`",
        "- 来源：AliMeeting Eval，CC BY-SA 4.0",
        "- 场景边界：公开会议音频，只用于多说话人分离工程评测，不代表医疗问诊效果。",
        f"- 状态：`{payload.get('status')}`",
        f"- 引擎：`{payload.get('engine')}`",
    ]
    for key in (
        "audio_duration_seconds",
        "elapsed_seconds",
        "rtf",
        "rss_peak_mb",
        "cpu_process_percent",
        "raw_segments",
        "enhanced_segments",
        "raw_speaker_count",
        "enhanced_speaker_count",
        "error",
    ):
        if key in payload and payload[key] is not None:
            lines.append(f"- {key}: `{payload[key]}`")
    if payload.get("raw_result"):
        lines.append(f"- Raw ASRResult：`{payload['raw_result']}`")
    if payload.get("enhanced_result"):
        lines.append(f"- Enhanced ASRResult：`{payload['enhanced_result']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ASRResult for public diarization samples.")
    parser.add_argument("--audio", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--engine", default="funasr")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = run_public_diarization_asr_result(
        audio_path=args.audio,
        report_dir=args.reports_dir,
        engine_name=args.engine,
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("status") in {"measured", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
