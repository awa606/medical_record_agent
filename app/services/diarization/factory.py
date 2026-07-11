from __future__ import annotations

from pathlib import Path

from app.services.diarization.funasr_campp import FunASRCamppResultAdapter
from app.services.diarization.pyannote_adapter import PyannoteCommunityAdapter
from app.services.diarization.three_d_speaker_adapter import ThreeDSpeakerAdapter


def create_diarization_engine(name: str, *, asr_result_path: Path | None = None):
    normalized = name.strip().lower()
    if normalized in {"funasr", "funasr_campp", "campp"}:
        return FunASRCamppResultAdapter(asr_result_path)
    if normalized in {"pyannote", "pyannote_community_1"}:
        return PyannoteCommunityAdapter()
    if normalized in {"3d-speaker", "three_d_speaker", "3dspeaker"}:
        return ThreeDSpeakerAdapter()
    raise ValueError(f"Unsupported diarization engine: {name}")
