from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.asr import DiarizationTurn
from app.services.diarization import create_diarization_engine
from app.services.asr.chunking import probe_audio_duration
from app.services.asr.ffmpeg_utils import find_ffprobe_executable
from scripts.run_local_asr_benchmark import _ResourceSampler


@dataclass(frozen=True)
class DiarizationMetrics:
    speaker_count_error: int
    boundary_f1: float
    mixed_utterance_rate: float
    role_consistency: float
    der: float | None = None
    jer: float | None = None


def parse_rttm(path: Path) -> list[DiarizationTurn]:
    turns: list[DiarizationTurn] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 8 or parts[0] != "SPEAKER":
            raise ValueError(f"Invalid RTTM line: {line}")
        start = float(parts[3])
        duration = float(parts[4])
        turns.append(
            DiarizationTurn(
                start_time=start,
                end_time=start + duration,
                speaker_id=parts[7],
            )
        )
    return turns


def evaluate_turns(
    reference: list[DiarizationTurn],
    hypothesis: list[DiarizationTurn],
    *,
    boundary_tolerance_seconds: float = 0.5,
) -> DiarizationMetrics:
    reference_speakers = {turn.speaker_id for turn in reference}
    hypothesis_speakers = {turn.speaker_id for turn in hypothesis}
    reference_boundaries = sorted({turn.end_time for turn in reference[:-1]})
    hypothesis_boundaries = sorted({turn.end_time for turn in hypothesis[:-1]})
    matched = _match_boundaries(reference_boundaries, hypothesis_boundaries, boundary_tolerance_seconds)
    precision = matched / len(hypothesis_boundaries) if hypothesis_boundaries else float(not reference_boundaries)
    recall = matched / len(reference_boundaries) if reference_boundaries else float(not hypothesis_boundaries)
    boundary_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    mixed = sum(_is_mixed(turn, reference) for turn in hypothesis)
    der, jer = _optional_der_jer(reference, hypothesis)
    return DiarizationMetrics(
        speaker_count_error=len(hypothesis_speakers) - len(reference_speakers),
        boundary_f1=round(boundary_f1, 4),
        mixed_utterance_rate=round(mixed / len(hypothesis), 4) if hypothesis else 0.0,
        role_consistency=round(_speaker_consistency(reference, hypothesis), 4),
        der=der,
        jer=jer,
    )


def _match_boundaries(reference: list[float], hypothesis: list[float], tolerance: float) -> int:
    unused = set(range(len(hypothesis)))
    matched = 0
    for boundary in reference:
        candidate = min(
            unused,
            key=lambda index: abs(hypothesis[index] - boundary),
            default=None,
        )
        if candidate is not None and abs(hypothesis[candidate] - boundary) <= tolerance:
            unused.remove(candidate)
            matched += 1
    return matched


def _is_mixed(hypothesis: DiarizationTurn, reference: list[DiarizationTurn]) -> bool:
    speakers = {
        turn.speaker_id
        for turn in reference
        if _overlap_seconds(hypothesis, turn) >= 0.1
    }
    return len(speakers) > 1


def _overlap_seconds(left: DiarizationTurn, right: DiarizationTurn) -> float:
    return max(0.0, min(left.end_time, right.end_time) - max(left.start_time, right.start_time))


def _speaker_consistency(reference: list[DiarizationTurn], hypothesis: list[DiarizationTurn]) -> float:
    matched = 0.0
    total = 0.0
    for speaker in {turn.speaker_id for turn in hypothesis}:
        speaker_turns = [turn for turn in hypothesis if turn.speaker_id == speaker]
        overlaps: dict[str, float] = {}
        for hypothesis_turn in speaker_turns:
            for reference_turn in reference:
                overlap = _overlap_seconds(hypothesis_turn, reference_turn)
                if overlap:
                    overlaps[reference_turn.speaker_id] = overlaps.get(reference_turn.speaker_id, 0.0) + overlap
                    total += overlap
        matched += max(overlaps.values(), default=0.0)
    return matched / total if total else 0.0


def _optional_der_jer(
    reference: list[DiarizationTurn],
    hypothesis: list[DiarizationTurn],
) -> tuple[float | None, float | None]:
    try:
        metrics_spec = importlib.util.find_spec("pyannote.metrics")
    except ModuleNotFoundError:
        metrics_spec = None
    if metrics_spec is None:
        return None, None
    from pyannote.core import Annotation, Segment
    from pyannote.metrics.diarization import DiarizationErrorRate, JaccardErrorRate

    reference_annotation = Annotation()
    hypothesis_annotation = Annotation()
    for index, turn in enumerate(reference):
        reference_annotation[Segment(turn.start_time, turn.end_time), index] = turn.speaker_id
    for index, turn in enumerate(hypothesis):
        hypothesis_annotation[Segment(turn.start_time, turn.end_time), index] = turn.speaker_id
    der = float(DiarizationErrorRate()(reference_annotation, hypothesis_annotation))
    jer = float(JaccardErrorRate()(reference_annotation, hypothesis_annotation))
    return round(der, 4), round(jer, 4)


def evaluate_diarization_engine(
    *,
    engine_name: str,
    audio_path: Path,
    reference_rttm: Path,
    asr_result: Path | None = None,
) -> dict[str, Any]:
    engine = create_diarization_engine(engine_name, asr_result_path=asr_result)
    available, reason = engine.availability()
    payload: dict[str, Any] = {
        "engine": engine.name,
        "requested_engine": engine_name,
        "status": "skipped",
        "reason": reason,
    }
    if not available:
        return payload

    started = time.perf_counter()
    hypothesis: list[DiarizationTurn] = []
    try:
        with _ResourceSampler() as sampler:
            hypothesis = engine.diarize(audio_path)
        elapsed = time.perf_counter() - started
        resources = sampler.metrics(elapsed)
        ffprobe = find_ffprobe_executable()
        duration = probe_audio_duration(audio_path, ffprobe) if ffprobe else None
        reference = parse_rttm(reference_rttm)
        if reference and not hypothesis:
            return {
                "engine": engine.name,
                "requested_engine": engine_name,
                "status": "failed",
                "reason": "engine returned no diarization turns for a non-empty RTTM reference",
                "elapsed_seconds": round(elapsed, 3),
                "audio_duration_seconds": duration,
                "rtf": round(elapsed / duration, 4) if duration else None,
                "turn_count": 0,
                **resources,
            }

        metrics = evaluate_turns(reference, hypothesis)
        return {
            "engine": engine.name,
            "requested_engine": engine_name,
            "status": "measured",
            "elapsed_seconds": round(elapsed, 3),
            "audio_duration_seconds": duration,
            "rtf": round(elapsed / duration, 4) if duration else None,
            "turn_count": len(hypothesis),
            "hypothesis_turns": [
                turn.model_dump(mode="json") for turn in hypothesis
            ],
            **resources,
            **metrics.__dict__,
        }
    except Exception as exc:  # pragma: no cover - integration failure path
        elapsed = time.perf_counter() - started
        return {
            "engine": engine.name,
            "requested_engine": engine_name,
            "status": "failed",
            "reason": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": round(elapsed, 3),
            "turn_count": len(hypothesis),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate one diarization engine against human RTTM")
    parser.add_argument("--engine", required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--reference-rttm", type=Path, required=True)
    parser.add_argument("--asr-result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = evaluate_diarization_engine(
        engine_name=args.engine,
        audio_path=args.audio,
        reference_rttm=args.reference_rttm,
        asr_result=args.asr_result,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
