from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np

from app.schemas.asr import ASRResult, ASRSegment
from app.services.asr.evaluator import ASREvaluator
from app.services.asr.ffmpeg_utils import find_ffmpeg_executable, find_ffprobe_executable
from app.services.asr.funasr_engine import DEFAULT_HOTWORD_PATH
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
        self.model_id = model_id or os.environ.get("FUNASR_STREAMING_MODEL_ID") or "paraformer-zh-streaming"
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
            self._validate_raw_result(raw_result)
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
        self._validate_recognized_content(text, segments)
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

    def create_live_chunk_session(self, audio_id: str) -> FunASRLiveChunkSession:
        return FunASRLiveChunkSession(engine=self, audio_id=audio_id)

    def _load_model(self) -> Any:
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "FunASR streaming import failed. Install requirements-asr.txt before using engine=funasr."
            ) from exc
        kwargs: dict[str, Any] = {"model": self.model_id, "device": self.device}
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

    def _validate_raw_result(self, raw_result: Any) -> None:
        if raw_result is None:
            raise RuntimeError("ASR_RESULT_INVALID: FunASR streaming returned no result payload")
        if not isinstance(raw_result, (dict, list, str)):
            raise RuntimeError(
                "ASR_RESULT_INVALID: FunASR streaming result format is "
                f"{type(raw_result).__name__}, expected object, list, or text"
            )

    def _validate_recognized_content(self, text: str, segments: list[ASRSegment]) -> None:
        if text.strip():
            return
        if any(segment.text.strip() for segment in segments):
            return
        raise RuntimeError("ASR_RESULT_INVALID: FunASR streaming result did not contain recognized text")

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


@dataclass
class FunASRLiveChunkSession:
    """Stateful browser-recording stream backed by one FunASR cache.

    This is intentionally limited to provisional transcript events. The
    existing finalize/complete path still creates the official full-audio ASR
    result and downstream medical-record draft.
    """

    engine: FunASRStreamingEngine
    audio_id: str
    cache: dict[str, Any] = field(default_factory=dict)
    processed_samples: int = 0
    segment_count: int = 0
    current_segment_id: str | None = None
    current_text: str = ""
    current_start_seconds: float = 0.0
    current_revision: int = 0

    def transcribe_chunk(
        self,
        chunk_path: Path,
        *,
        sequence: int,
        chunk_started_at_ms: int | None = None,
        chunk_ended_at_ms: int | None = None,
        checksum: str | None = None,
    ) -> list[tuple[str, ASRSegment, dict[str, object]]]:
        events: list[tuple[str, ASRSegment, dict[str, object]]] = []
        chunk_start_seconds = (
            max(float(chunk_started_at_ms) / 1000.0, 0.0)
            if chunk_started_at_ms is not None
            else self.processed_samples / self.engine.config.sample_rate
        )
        chunk_end_seconds = (
            max(float(chunk_ended_at_ms) / 1000.0, chunk_start_seconds)
            if chunk_ended_at_ms is not None
            else None
        )

        for pcm_chunk in self.engine._iter_pcm_chunks(chunk_path):
            raw_result = self.engine.model.generate(
                input=pcm_chunk,
                cache=self.cache,
                is_final=False,
                chunk_size=list(self.engine.config.chunk_size),
                encoder_chunk_look_back=self.engine.config.encoder_chunk_look_back,
                decoder_chunk_look_back=self.engine.config.decoder_chunk_look_back,
            )
            self.engine._validate_raw_result(raw_result)
            self.processed_samples += len(pcm_chunk)
            processed_seconds = self.processed_samples / self.engine.config.sample_rate
            delta = self.engine._extract_text(raw_result)
            if not delta:
                continue
            if self.current_segment_id is None:
                self.segment_count += 1
                self.current_segment_id = f"{self.audio_id}-live-{self.segment_count:04d}"
                self.current_start_seconds = chunk_start_seconds
                self.current_revision = 0
            self.current_text = _append_streaming_text(self.current_text, delta)
            self.current_revision += 1
            partial = ASRSegment(
                segment_id=self.current_segment_id,
                revision=max(self.current_revision, 1),
                provisional=True,
                speaker="streaming",
                speaker_id="streaming",
                role=None,
                role_source="system_auto_inference",
                role_warning="系统自动推定",
                text=self.current_text.strip(),
                start_time=round(self.current_start_seconds, 3),
                end_time=round(min(chunk_end_seconds or processed_seconds, processed_seconds), 3),
                needs_review=True,
            )
            events.append(
                (
                    "transcript.partial",
                    partial,
                    {
                        "sequence": sequence,
                        "chunk_started_at_ms": chunk_started_at_ms,
                        "chunk_ended_at_ms": chunk_ended_at_ms,
                        "checksum": checksum,
                        "processed_audio_seconds": round(processed_seconds, 3),
                    },
                )
            )

        if self.current_segment_id and self.current_text.strip():
            stable_end = chunk_end_seconds or self.processed_samples / self.engine.config.sample_rate
            stable = ASRSegment(
                segment_id=self.current_segment_id,
                revision=max(self.current_revision + 1, 1),
                provisional=False,
                speaker="streaming",
                speaker_id="streaming",
                role=None,
                role_source="system_auto_inference",
                role_warning="系统自动推定",
                text=self.current_text.strip(),
                start_time=round(self.current_start_seconds, 3),
                end_time=round(stable_end, 3),
                needs_review=True,
            )
            events.append(
                (
                    "transcript.stable",
                    stable,
                    {
                        "sequence": sequence,
                        "chunk_started_at_ms": chunk_started_at_ms,
                        "chunk_ended_at_ms": chunk_ended_at_ms,
                        "checksum": checksum,
                        "processed_audio_seconds": round(stable_end, 3),
                    },
                )
            )
            self.current_segment_id = None
            self.current_text = ""
            self.current_revision = 0
        return events
