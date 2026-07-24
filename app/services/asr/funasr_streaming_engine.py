from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np

from app.schemas.asr import ASRResult, ASRSegment
from app.services.asr.evaluator import ASREvaluator
from app.services.asr.ffmpeg_utils import find_ffmpeg_executable, find_ffprobe_executable
from app.services.asr.funasr_engine import DEFAULT_HOTWORD_PATH, _disable_update_check
from app.services.asr.chunking import probe_audio_duration


ProgressCallback = Callable[[dict[str, object]], None]
SegmentCallback = Callable[[str, ASRSegment, dict[str, object]], None]


@dataclass(frozen=True)
class StreamingConfig:
    sample_rate: int = 16000
    chunk_size: tuple[int, int, int] = (0, 10, 5)
    encoder_chunk_look_back: int = 4
    decoder_chunk_look_back: int = 1
    segment_seconds: float = 6.0

    @property
    def chunk_samples(self) -> int:
        return self.chunk_size[1] * 960


class FunASRStreamingEngine:
    """Model-native streaming transcription for an already uploaded audio file."""

    name = "funasr-paraformer-zh-streaming"

    def __init__(
        self,
        *,
        model_id: str | None = None,
        device: str | None = None,
        hotword_path: str | Path | None = DEFAULT_HOTWORD_PATH,
        model_instance: Any | None = None,
        config: StreamingConfig | None = None,
    ) -> None:
        self.model_id = model_id or os.environ.get("FUNASR_STREAMING_MODEL_ID") or "ParaformerStreaming"
        self.device = device or os.environ.get("FUNASR_DEVICE") or "cpu"
        self.config = config or StreamingConfig(
            segment_seconds=_env_float("FUNASR_STREAMING_SEGMENT_SECONDS", 6.0)
        )
        self.hotwords = self._load_hotwords(hotword_path)
        started_at = time.perf_counter()
        self.model = model_instance if model_instance is not None else self._load_model()
        self.model_load_time_seconds = round(time.perf_counter() - started_at, 3)

    def transcribe_streaming(
        self,
        audio_id: str,
        audio_path: Path,
        *,
        on_progress: ProgressCallback | None = None,
        on_segment: SegmentCallback | None = None,
    ) -> ASRResult:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        duration = self._probe_duration(audio_path)
        started_at = time.perf_counter()
        cache: dict[str, Any] = {}
        segments: list[ASRSegment] = []
        current_id: str | None = None
        current_text = ""
        current_start = 0.0
        current_revision = 0

        def emit_progress(processed_seconds: float, *, phase: str = "streaming") -> None:
            if on_progress is None:
                return
            progress = min(processed_seconds / duration, 1.0) if duration else None
            on_progress(
                {
                    "phase": phase,
                    "processed_audio_seconds": round(processed_seconds, 3),
                    "audio_duration_seconds": duration,
                    "progress": round(progress, 4) if progress is not None else None,
                    "progress_kind": "actual" if progress is not None else "indeterminate",
                    "elapsed_seconds": round(time.perf_counter() - started_at, 3),
                }
            )

        processed_samples = 0
        for chunk, is_final in _with_final_flag(self._iter_pcm_chunks(audio_path)):
            raw_result = self.model.generate(
                input=chunk,
                cache=cache,
                is_final=is_final,
                chunk_size=list(self.config.chunk_size),
                encoder_chunk_look_back=self.config.encoder_chunk_look_back,
                decoder_chunk_look_back=self.config.decoder_chunk_look_back,
            )
            processed_samples += len(chunk)
            processed_seconds = min(processed_samples / self.config.sample_rate, duration or float("inf"))
            delta = self._extract_text(raw_result)
            if delta:
                if current_id is None:
                    current_id = f"{audio_id}-seg-{len(segments) + 1:04d}"
                    current_start = max(0.0, processed_seconds - len(chunk) / self.config.sample_rate)
                    current_revision = 0
                current_text = _append_streaming_text(current_text, delta)
                current_revision += 1
                flush_window = (
                    is_final
                    or processed_seconds - current_start >= self.config.segment_seconds
                    or _ends_sentence(current_text)
                )
                segment = ASRSegment(
                    segment_id=current_id,
                    revision=current_revision,
                    # Streaming text has no reliable speaker boundary. It remains
                    # provisional until the offline VAD/diarization pass replaces it.
                    provisional=True,
                    speaker="streaming",
                    speaker_id=None,
                    role=None,
                    text=current_text.strip(),
                    start_time=round(current_start, 3),
                    end_time=round(processed_seconds, 3),
                    needs_review=True,
                )
                if on_segment is not None:
                    event_name = "segment" if current_revision == 1 else "segment_update"
                    on_segment(
                        event_name,
                        segment,
                        {
                            "processed_audio_seconds": round(processed_seconds, 3),
                            "audio_duration_seconds": duration,
                        },
                    )
                if flush_window:
                    segments.append(segment)
                    current_id = None
                    current_text = ""
                    current_revision = 0
            emit_progress(processed_seconds)

        if current_id and current_text.strip():
            current_revision += 1
            final_segment = ASRSegment(
                segment_id=current_id,
                revision=current_revision,
                provisional=True,
                speaker="streaming",
                text=current_text.strip(),
                start_time=round(current_start, 3),
                end_time=duration,
                needs_review=True,
            )
            if on_segment is not None:
                on_segment(
                    "segment_update" if current_revision > 1 else "segment",
                    final_segment,
                    {
                        "processed_audio_seconds": duration or 0.0,
                        "audio_duration_seconds": duration,
                    },
                )
            segments.append(final_segment)

        emit_progress(duration or processed_samples / self.config.sample_rate, phase="streaming_completed")
        text = "".join(segment.text for segment in segments if segment.text.strip())
        keywords = ASREvaluator().keyword_metrics(self.hotwords, text)
        return ASRResult(
            audio_id=audio_id,
            engine=self.name,
            text=text,
            conversation_text="",
            segments=segments,
            duration=duration,
            medical_keywords={
                "expected": keywords["expected"],
                "recognized": keywords["recognized"],
                "missing": keywords["missing"],
            },
            needs_review=True,
            warnings=["Streaming text is provisional until speaker and punctuation reconciliation completes."],
        )

    def _load_model(self) -> Any:
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "FunASR streaming import failed. Install requirements-asr.txt before using engine=funasr."
            ) from exc
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "device": self.device,
            "disable_update": _disable_update_check(),
        }
        hub = os.environ.get("FUNASR_HUB")
        if hub:
            kwargs["hub"] = hub
        return AutoModel(**kwargs)

    def _iter_pcm_chunks(self, audio_path: Path) -> Iterator[np.ndarray]:
        ffmpeg = find_ffmpeg_executable()
        if ffmpeg is None:
            raise FileNotFoundError("ffmpeg not found. Run scripts/setup_ffmpeg_portable.py first.")
        command = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(audio_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(self.config.sample_rate),
            "-f",
            "f32le",
            "pipe:1",
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.stdout is None:
            raise RuntimeError("ffmpeg stdout pipe was not created")
        bytes_per_chunk = self.config.chunk_samples * 4
        try:
            while True:
                raw = process.stdout.read(bytes_per_chunk)
                if not raw:
                    break
                yield np.frombuffer(raw, dtype="<f4").copy()
        finally:
            process.stdout.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"ffmpeg audio decode failed: {stderr.strip()[:500]}")

    def _probe_duration(self, audio_path: Path) -> float | None:
        ffprobe = find_ffprobe_executable()
        if ffprobe is None:
            return None
        try:
            return probe_audio_duration(audio_path, ffprobe)
        except Exception:
            return None

    def _load_hotwords(self, hotword_path: str | Path | None) -> list[str]:
        if hotword_path is None:
            return []
        path = Path(hotword_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        if not path.exists():
            return []
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    @staticmethod
    def _extract_text(raw_result: Any) -> str:
        items = raw_result if isinstance(raw_result, list) else [raw_result]
        texts: list[str] = []
        for item in items:
            if isinstance(item, dict):
                value = item.get("text") or item.get("preds") or ""
                if isinstance(value, str):
                    texts.append(value.strip())
            elif isinstance(item, str):
                texts.append(item.strip())
        return "".join(text for text in texts if text)


def _with_final_flag(chunks: Iterator[np.ndarray]) -> Iterator[tuple[np.ndarray, bool]]:
    iterator = iter(chunks)
    try:
        current = next(iterator)
    except StopIteration:
        return
    for upcoming in iterator:
        yield current, False
        current = upcoming
    yield current, True


def _append_streaming_text(current: str, delta: str) -> str:
    clean_delta = delta.strip()
    if not current:
        return clean_delta
    if clean_delta.startswith(current):
        return clean_delta
    if current.endswith(clean_delta):
        return current
    return f"{current}{clean_delta}"


def _ends_sentence(text: str) -> bool:
    return bool(text) and text.rstrip().endswith(("。", "！", "？", "!", "?"))


def _env_float(name: str, default: float) -> float:
    try:
        value = float(str(os.environ.get(name, default)).strip())
    except ValueError:
        return default
    return value if value > 0 else default
