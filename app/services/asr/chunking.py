from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.schemas import ASRResult, ASRSegment
from app.services.asr.ffmpeg_utils import find_ffmpeg_executable, find_ffprobe_executable


@dataclass(frozen=True)
class AudioChunk:
    index: int
    path: Path
    start_seconds: float
    duration_seconds: float


@dataclass(frozen=True)
class ChunkTranscription:
    chunk: AudioChunk
    result: ASRResult


def build_chunk_plan(total_seconds: float, chunk_seconds: int) -> list[tuple[float, float]]:
    if total_seconds <= 0:
        raise ValueError("total_seconds must be positive")
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be positive")

    chunks: list[tuple[float, float]] = []
    start = 0.0
    while start < total_seconds:
        duration = min(float(chunk_seconds), total_seconds - start)
        if duration <= 0:
            break
        chunks.append((round(start, 3), round(duration, 3)))
        start += duration
    return chunks


def split_audio_to_chunks(
    audio_path: Path,
    output_dir: Path,
    *,
    chunk_seconds: int = 300,
    ffmpeg_path: Path | None = None,
    ffprobe_path: Path | None = None,
) -> list[AudioChunk]:
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    ffmpeg = ffmpeg_path or find_ffmpeg_executable()
    ffprobe = ffprobe_path or find_ffprobe_executable()
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg not found. Run scripts/setup_ffmpeg_portable.py first.")
    if ffprobe is None:
        raise FileNotFoundError("ffprobe not found. Run scripts/setup_ffmpeg_portable.py first.")

    total_seconds = probe_audio_duration(audio_path, ffprobe)
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[AudioChunk] = []
    for index, (start_seconds, duration_seconds) in enumerate(
        build_chunk_plan(total_seconds, chunk_seconds),
        start=1,
    ):
        chunk_path = output_dir / f"{audio_path.stem}_chunk_{index:03d}.wav"
        _run_command(
            [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(start_seconds),
                "-t",
                str(duration_seconds),
                "-i",
                str(audio_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-sample_fmt",
                "s16",
                str(chunk_path),
            ]
        )
        chunks.append(
            AudioChunk(
                index=index,
                path=chunk_path,
                start_seconds=start_seconds,
                duration_seconds=duration_seconds,
            )
        )
    return chunks


def merge_chunk_transcriptions(
    audio_id: str,
    transcriptions: Iterable[ChunkTranscription],
    *,
    original_duration: float | None = None,
    engine_name: str | None = None,
) -> ASRResult:
    ordered = sorted(transcriptions, key=lambda item: item.chunk.index)
    if not ordered:
        raise ValueError("transcriptions must not be empty")

    text_parts: list[str] = []
    segments: list[ASRSegment] = []
    warnings: list[str] = ["ASR result was produced by chunked long-audio transcription."]
    expected_keywords: set[str] = set()
    recognized_keywords: set[str] = set()
    missing_keywords: set[str] = set()

    for item in ordered:
        result = item.result
        if result.text.strip():
            text_parts.append(result.text.strip())
        warnings.extend(result.warnings)
        keywords = result.medical_keywords or {}
        expected_keywords.update(keywords.get("expected") or [])
        recognized_keywords.update(keywords.get("recognized") or [])
        missing_keywords.update(keywords.get("missing") or [])

        for segment in result.segments:
            segments.append(
                ASRSegment(
                    speaker=segment.speaker,
                    role=segment.role,
                    text=segment.text,
                    start_time=_offset_time(segment.start_time, item.chunk.start_seconds),
                    end_time=_offset_time(segment.end_time, item.chunk.start_seconds),
                    confidence=segment.confidence,
                    needs_review=segment.needs_review,
                    reviewed_by_doctor=segment.reviewed_by_doctor,
                    original_text=segment.original_text,
                )
            )

    text = "\n".join(text_parts)
    return ASRResult(
        audio_id=audio_id,
        engine=engine_name or f"{ordered[0].result.engine}-chunked",
        text=text,
        conversation_text=_conversation_from_segments(segments, text),
        segments=segments,
        duration=original_duration or _infer_duration(segments),
        medical_keywords={
            "expected": sorted(expected_keywords),
            "recognized": sorted(recognized_keywords),
            "missing": sorted(missing_keywords - recognized_keywords),
        },
        warnings=sorted(set(warnings)),
        needs_review=any(item.result.needs_review for item in ordered),
    )


def probe_audio_duration(audio_path: Path, ffprobe_path: Path) -> float:
    completed = _run_command(
        [
            str(ffprobe_path),
            "-hide_banner",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture=True,
    )
    duration = float((completed.stdout or "0").strip())
    if duration <= 0:
        raise ValueError(f"ffprobe returned invalid duration for {audio_path}: {duration}")
    return round(duration, 3)


def _offset_time(value: float | None, offset: float) -> float | None:
    if value is None:
        return None
    return round(value + offset, 3)


def _infer_duration(segments: list[ASRSegment]) -> float | None:
    end_times = [segment.end_time for segment in segments if segment.end_time is not None]
    return max(end_times) if end_times else None


def _conversation_from_segments(segments: list[ASRSegment], fallback_text: str) -> str:
    if not segments:
        return fallback_text
    return "\n".join(f"[{segment.speaker or 'spk0'}] {segment.text}" for segment in segments)


def _run_command(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
