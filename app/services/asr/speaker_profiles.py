from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import threading
import uuid
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.schemas.asr import ASRResult, SpeakerRoleAssignment
from app.schemas.speaker_profile import DoctorSpeakerProfile
from app.services.asr.ffmpeg_utils import find_ffmpeg_executable, find_ffprobe_executable
from app.services.asr.chunking import probe_audio_duration


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROFILE_DIR = PROJECT_ROOT / "data" / "speaker_profiles"
MIN_ENROLLMENT_SECONDS = 8.0
DEFAULT_MATCH_THRESHOLD = 0.65

_MODEL_LOCK = threading.Lock()
_CAMPP_MODEL: Any | None = None


def speaker_profile_dir() -> Path:
    path = Path(os.environ.get("MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR", DEFAULT_PROFILE_DIR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_doctor_profile(
    audio_path: Path,
    *,
    name: str,
    extractor: Any | None = None,
) -> DoctorSpeakerProfile:
    duration = _audio_duration(audio_path)
    if duration < MIN_ENROLLMENT_SECONDS:
        raise ValueError(f"医生声纹有效语音至少需要 {MIN_ENROLLMENT_SECONDS:.0f} 秒")
    embedding = _extract_embedding(audio_path, extractor=extractor)
    profile_id = uuid.uuid4().hex
    created_at = datetime.now(UTC).isoformat()
    model_id = os.environ.get("CAMPP_SPEAKER_MODEL_ID", "cam++")
    payload = {
        "profile_id": profile_id,
        "name": name.strip() or "本机医生",
        "model": model_id,
        "embedding_dimension": len(embedding),
        "effective_speech_seconds": round(duration, 3),
        "created_at": created_at,
        "embedding": embedding,
    }
    _profile_path(profile_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return DoctorSpeakerProfile.model_validate(
        {key: value for key, value in payload.items() if key != "embedding"}
    )


def list_doctor_profiles() -> list[DoctorSpeakerProfile]:
    profiles: list[DoctorSpeakerProfile] = []
    for path in sorted(speaker_profile_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("embedding", None)
            profiles.append(DoctorSpeakerProfile.model_validate(data))
        except (ValueError, json.JSONDecodeError):
            continue
    return profiles


def delete_doctor_profile(profile_id: str) -> bool:
    path = _profile_path(profile_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def apply_doctor_voice_profile(
    result: ASRResult,
    audio_path: Path,
    profile_id: str | None,
    *,
    extractor: Any | None = None,
) -> ASRResult:
    if not profile_id or not result.speaker_assignments:
        return result
    profile = _load_profile_payload(profile_id)
    profile_embedding = [float(value) for value in profile["embedding"]]
    speaker_audio = _speaker_audio_arrays(result, audio_path)
    similarities: dict[str, float] = {}
    with tempfile.TemporaryDirectory(prefix="mra-speaker-match-") as temp_dir:
        for speaker_id, samples in speaker_audio.items():
            if len(samples) < 16000 * 2:
                continue
            sample_path = Path(temp_dir) / f"{speaker_id}.wav"
            _write_wav(sample_path, samples)
            embedding = _extract_embedding(sample_path, extractor=extractor)
            similarities[speaker_id] = cosine_similarity(profile_embedding, embedding)
    if not similarities:
        return result

    doctor_speaker, similarity = max(similarities.items(), key=lambda item: item[1])
    threshold = float(os.environ.get("DOCTOR_PROFILE_MATCH_THRESHOLD", DEFAULT_MATCH_THRESHOLD))
    updated = result.model_copy(deep=True)
    if similarity < threshold:
        for assignment in updated.speaker_assignments:
            assignment.requires_confirmation = True
            assignment.reason = (
                f"医生声纹最高相似度 {similarity:.2f} 低于阈值 {threshold:.2f}，需一次全局确认"
            )
        updated.needs_review = True
        return updated

    updated.speaker_assignments = _lock_doctor_assignment(
        updated.speaker_assignments,
        doctor_speaker,
        similarity,
    )
    role_map = {item.speaker_id: item for item in updated.speaker_assignments}
    for segment in updated.segments:
        assignment = role_map.get(segment.speaker_id or segment.speaker or "")
        if assignment is None:
            continue
        segment.role = assignment.role
        segment.role_confidence = assignment.confidence
        segment.role_source = assignment.source
        segment.role_note = assignment.reason
        segment.needs_review = assignment.requires_confirmation
    updated.needs_review = any(item.requires_confirmation for item in updated.speaker_assignments)
    updated.role_strategy = "doctor_voice_profile_then_global_role"
    return updated


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Speaker embeddings must have the same non-zero dimension")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return float(numerator / (left_norm * right_norm))


def _lock_doctor_assignment(
    assignments: list[SpeakerRoleAssignment],
    doctor_speaker: str,
    similarity: float,
) -> list[SpeakerRoleAssignment]:
    remaining = [item for item in assignments if item.speaker_id != doctor_speaker]
    updated = [
        SpeakerRoleAssignment(
            speaker_id=doctor_speaker,
            role="医生",
            confidence=max(0.9, min(0.99, similarity)),
            source="doctor_voice_profile",
            reason="与本机注册医生声纹匹配",
        )
    ]
    if len(remaining) == 1:
        item = remaining[0]
        updated.append(
            item.model_copy(
                update={
                    "role": "患者",
                    "confidence": max(item.confidence, 0.86),
                    "source": "doctor_profile_two_party_constraint",
                    "reason": "医生声纹已锁定，唯一剩余主要说话人按患者处理",
                    "requires_confirmation": False,
                }
            )
        )
    else:
        updated.extend(
            item.model_copy(
                update={"requires_confirmation": item.role not in {"患者", "其他"}}
            )
            for item in remaining
        )
    order = {item.speaker_id: index for index, item in enumerate(assignments)}
    return sorted(updated, key=lambda item: order.get(item.speaker_id, 999))


def _speaker_audio_arrays(result: ASRResult, audio_path: Path) -> dict[str, np.ndarray]:
    samples = _decode_pcm(audio_path)
    sample_rate = 16000
    grouped: dict[str, list[np.ndarray]] = {}
    for segment in result.segments:
        if segment.overlap or segment.start_time is None or segment.end_time is None:
            continue
        speaker = segment.speaker_id or segment.speaker
        if not speaker:
            continue
        start = max(0, int(float(segment.start_time) * sample_rate))
        end = min(len(samples), int(float(segment.end_time) * sample_rate))
        if end > start:
            grouped.setdefault(speaker, []).append(samples[start:end])
    return {
        speaker: np.concatenate(parts) if parts else np.zeros(0, dtype=np.int16)
        for speaker, parts in grouped.items()
    }


def _decode_pcm(audio_path: Path) -> np.ndarray:
    ffmpeg = find_ffmpeg_executable()
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg is required for speaker profile matching")
    completed = subprocess.run(
        [str(ffmpeg), "-v", "error", "-i", str(audio_path), "-f", "s16le", "-ac", "1", "-ar", "16000", "pipe:1"],
        check=True,
        capture_output=True,
    )
    return np.frombuffer(completed.stdout, dtype=np.int16)


def _write_wav(path: Path, samples: np.ndarray) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(samples.astype(np.int16, copy=False).tobytes())


def _extract_embedding(audio_path: Path, *, extractor: Any | None = None) -> list[float]:
    model = extractor or _campp_model()
    raw = model.generate(input=str(audio_path))
    if not raw or not isinstance(raw[0], dict) or "spk_embedding" not in raw[0]:
        raise RuntimeError("CAM++ did not return spk_embedding")
    value = raw[0]["spk_embedding"]
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    array = np.asarray(value, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(array))
    if not norm:
        raise RuntimeError("CAM++ returned an empty speaker embedding")
    return (array / norm).astype(float).tolist()


def _campp_model() -> Any:
    global _CAMPP_MODEL
    with _MODEL_LOCK:
        if _CAMPP_MODEL is None:
            try:
                from funasr import AutoModel
            except ImportError as exc:
                raise RuntimeError("FunASR/CAM++ is not installed") from exc
            _CAMPP_MODEL = AutoModel(
                model=os.environ.get("CAMPP_SPEAKER_MODEL_ID", "cam++"),
                device=os.environ.get("CAMPP_SPEAKER_DEVICE", "cpu"),
                disable_update=True,
            )
        return _CAMPP_MODEL


def _audio_duration(audio_path: Path) -> float:
    ffprobe = find_ffprobe_executable()
    if ffprobe is None:
        raise FileNotFoundError("ffprobe is required for speaker enrollment")
    return probe_audio_duration(audio_path, ffprobe)


def _profile_path(profile_id: str) -> Path:
    if not profile_id or Path(profile_id).name != profile_id:
        raise ValueError("Invalid speaker profile id")
    return speaker_profile_dir() / f"{profile_id}.json"


def _load_profile_payload(profile_id: str) -> dict[str, Any]:
    path = _profile_path(profile_id)
    if not path.exists():
        raise FileNotFoundError(f"Speaker profile not found: {profile_id}")
    return json.loads(path.read_text(encoding="utf-8"))
