from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from app.schemas.asr import ASRResult, ASRSegment
from app.services.asr.evaluator import ASREvaluator
from app.services.asr.funasr_engine import DEFAULT_HOTWORD_PATH


DEPENDENCY_ERROR = (
    "Whisper dependencies are not installed. Install `requirements-asr-experimental.txt` "
    "inside `.venv-asr` before running engine=whisper."
)
FFMPEG_ERROR = (
    "Whisper requires a system ffmpeg executable. Install ffmpeg or choose another ASR engine."
)
DEFAULT_MODEL_NAME = "base"
ROLE_REVIEW_WARNING = (
    "Whisper does not provide reliable doctor/patient roles; please manually review roles."
)


class WhisperASREngine:
    name = "whisper-base"

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        language: str | None = None,
        hotword_path: str | Path | None = DEFAULT_HOTWORD_PATH,
        model_instance: Any | None = None,
    ) -> None:
        self.model_name = model_name or os.environ.get("WHISPER_MODEL") or DEFAULT_MODEL_NAME
        self.device = device or os.environ.get("WHISPER_DEVICE") or "cpu"
        self.language = language or os.environ.get("WHISPER_LANGUAGE") or "zh"
        self.hotwords = self._load_hotwords(hotword_path)
        if shutil.which("ffmpeg") is None and model_instance is None:
            raise RuntimeError(FFMPEG_ERROR)
        started_at = time.perf_counter()
        self.model = model_instance if model_instance is not None else self._load_model()
        self.model_load_time_seconds = round(time.perf_counter() - started_at, 3)
        self.name = f"whisper-{self.model_name}"

    def transcribe(self, audio_id: str, audio_path: Path) -> ASRResult:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        raw_result = self.model.transcribe(
            str(audio_path),
            language=self.language,
            fp16=self.device.startswith("cuda"),
        )
        text = self._extract_text(raw_result)
        segments = self._extract_segments(raw_result, text)
        keywords = ASREvaluator().keyword_metrics(self.hotwords, text)

        return ASRResult(
            audio_id=audio_id,
            engine=self.name,
            text=text,
            conversation_text=self._conversation_from_segments(segments, text),
            segments=segments,
            duration=self._infer_duration(segments),
            medical_keywords={
                "expected": keywords["expected"],
                "recognized": keywords["recognized"],
                "missing": keywords["missing"],
            },
            warnings=[ROLE_REVIEW_WARNING],
        )

    def _load_model(self) -> Any:
        try:
            import whisper
        except ImportError as exc:
            raise RuntimeError(DEPENDENCY_ERROR) from exc
        return whisper.load_model(self.model_name, device=self.device)

    def _load_hotwords(self, hotword_path: str | Path | None) -> list[str]:
        if hotword_path is None:
            return []
        path = Path(hotword_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        if not path.exists():
            return []
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _extract_text(self, raw_result: Any) -> str:
        if isinstance(raw_result, dict):
            text = raw_result.get("text")
            if isinstance(text, str):
                return text.strip()
            segments = raw_result.get("segments")
            if isinstance(segments, list):
                return "\n".join(segment.text for segment in self._segments_from_items(segments))
        if isinstance(raw_result, str):
            return raw_result.strip()
        return ""

    def _extract_segments(self, raw_result: Any, fallback_text: str) -> list[ASRSegment]:
        if isinstance(raw_result, dict):
            segments = self._segments_from_items(raw_result.get("segments"))
            if segments:
                return segments
        return [ASRSegment(speaker="whisper", role=None, text=fallback_text, needs_review=True)]

    def _segments_from_items(self, items: Any) -> list[ASRSegment]:
        if not isinstance(items, list):
            return []
        segments: list[ASRSegment] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                ASRSegment(
                    speaker="whisper",
                    role=None,
                    text=text,
                    start_time=self._optional_float(item.get("start")),
                    end_time=self._optional_float(item.get("end")),
                    confidence=self._optional_float(item.get("confidence")),
                    needs_review=True,
                )
            )
        return segments

    def _conversation_from_segments(self, segments: list[ASRSegment], fallback_text: str) -> str:
        if not segments:
            return f"[待校正] {fallback_text}"
        return "\n".join(f"[{segment.speaker or 'whisper'}] {segment.text}" for segment in segments)

    def _infer_duration(self, segments: list[ASRSegment]) -> float | None:
        end_times = [segment.end_time for segment in segments if segment.end_time is not None]
        return max(end_times) if end_times else None

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
