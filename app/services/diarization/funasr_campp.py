from __future__ import annotations

from pathlib import Path

from app.schemas.asr import ASRResult, DiarizationTurn


class FunASRCamppResultAdapter:
    """Adapts an existing FunASR VAD+punc+CAM++ result to common turns."""

    name = "funasr_campp"

    def __init__(self, result_path: Path | None = None) -> None:
        self.result_path = result_path

    def availability(self) -> tuple[bool, str]:
        if self.result_path is None:
            return False, "--asr-result is required for the FunASR CAM++ adapter"
        if not self.result_path.exists():
            return False, f"ASR result not found: {self.result_path}"
        return True, "existing FunASR result available"

    def diarize(self, _audio_path: Path) -> list[DiarizationTurn]:
        available, reason = self.availability()
        if not available:
            raise RuntimeError(reason)
        result = ASRResult.model_validate_json(self.result_path.read_text(encoding="utf-8"))
        if result.diarization_turns:
            return result.diarization_turns
        return [
            DiarizationTurn(
                start_time=float(segment.start_time),
                end_time=float(segment.end_time),
                speaker_id=segment.speaker_id or segment.speaker or "speaker_0",
                confidence=segment.speaker_confidence,
                overlap=segment.overlap,
            )
            for segment in result.segments
            if segment.start_time is not None and segment.end_time is not None
        ]
